"""Lidar intensity as a reference image for registering orthoimagery on the BNG grid.

First-return intensity from an EA point cloud shows roads, roofs, field boundaries and tree edges
without the orthoimage's shadows and colour, but its absolute scale differs between surveys
(median 26 to 477 across eight sites). The gradient magnitude of the interpolated intensity is
scale-free, and is what the Esri luma is matched against (`registration.py`).
"""

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import laspy
import numpy as np
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import KDTree

from satmesh_core import Aoi
from satmesh_eval.offset import GRID_M, row_strips

FIRST_RETURN = 1
CLASS_NOISE = 7  # ASPRS LAS classification
READ_CHUNK_POINTS = 5_000_000
# cells farther than this from any first return are lidar gaps (water, survey edge), left flat
MAX_GAP_M = 1.5
# smoothing before the Sobel gradient, in grid pixels (0.25 m)
GRADIENT_SIGMA_PX = 1.0
# robust display range of an image, as percentiles
LOW_PERCENTILE, HIGH_PERCENTILE = 1.0, 99.0
U8_MAX = 255.0


def read_first_return_intensity(
    laz_paths: Sequence[Path], boxes: Sequence[Aoi], margin_m: float
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Return, per box, the (N, 2) easting and northing and the intensity of first returns near it.

    Each file is read once. Points inside a box grown by `margin_m` are kept, in file order;
    noise-class points are dropped. All boxes' points are held in memory at once, about 25 bytes
    per point, which is 100 MB per square kilometre at the EA's 4 points/m2.
    """
    parts: list[list[tuple[np.ndarray, np.ndarray]]] = [[] for _ in boxes]
    for path in laz_paths:
        with laspy.open(path) as reader:
            for chunk in reader.chunk_iterator(READ_CHUNK_POINTS):
                first = (chunk.return_number == FIRST_RETURN) & (
                    chunk.classification != CLASS_NOISE
                )
                # plain arrays: laspy's scaled views return wrong rows for a mask with few hits
                x, y = np.asarray(chunk.x)[first], np.asarray(chunk.y)[first]
                intensity = np.asarray(chunk.intensity)[first]
                for box_parts, box in zip(parts, boxes, strict=True):
                    keep = (
                        (x >= box.west - margin_m)
                        & (x < box.east + margin_m)
                        & (y >= box.south - margin_m)
                        & (y < box.north + margin_m)
                    )
                    box_parts.append((np.column_stack([x[keep], y[keep]]), intensity[keep]))
    return [
        (
            np.concatenate([xy for xy, _ in box_parts]),
            np.concatenate([i for _, i in box_parts]).astype(np.float64),
        )
        for box_parts in parts
    ]


def intensity_gradient_image(
    xy: np.ndarray, intensity: np.ndarray, box: Aoi, grid_m: float = GRID_M
) -> np.ndarray:
    """Return the gradient magnitude of lidar intensity on the BNG grid of `box`, scaled to 0-255.

    Intensity is linearly interpolated between returns (Delaunay), cells beyond `MAX_GAP_M` of any
    return are held at the median, and the gradient is the Sobel magnitude after a Gaussian blur.
    Row 0 is the north row, matching `luminance_on_grid`.
    """
    cols, rows = round((box.east - box.west) / grid_m), round((box.north - box.south) / grid_m)
    easting = box.west + grid_m * (np.arange(cols) + 0.5)
    northing = box.north - grid_m * (np.arange(rows) + 0.5)
    ee, nn = np.meshgrid(easting, northing)
    image = _interpolate_in_threads(LinearNDInterpolator(xy, intensity, fill_value=np.nan), ee, nn)
    gap = (
        KDTree(xy).query(np.column_stack([ee.ravel(), nn.ravel()]), workers=-1)[0].reshape(ee.shape)
    )
    image[gap > MAX_GAP_M] = np.nan
    return gradient_magnitude_u8(image)


def _interpolate_in_threads(
    interpolate: LinearNDInterpolator, ee: np.ndarray, nn: np.ndarray
) -> np.ndarray:
    """Evaluate a built interpolator over row strips in threads sharing its triangulation."""
    # the first call builds the triangulation's barycentric transforms; threads racing there each
    # repeat that work
    interpolate(ee[:1, :1], nn[:1, :1])
    with ThreadPoolExecutor() as pool:
        return np.concatenate(
            list(pool.map(lambda rows: interpolate(ee[rows], nn[rows]), row_strips(ee.shape[0])))
        )


def gradient_magnitude_u8(image: np.ndarray) -> np.ndarray:
    """Return the Sobel gradient magnitude of `image` scaled to 0-255 by its 1st-99th percentiles.

    Non-finite pixels are held at the image median, so they have zero gradient and window
    selection treats them as missing data.
    """
    filled = np.where(np.isfinite(image), image, np.nanmedian(image)).astype(np.float32)
    blurred = cv2.GaussianBlur(filled, (0, 0), GRADIENT_SIGMA_PX)
    magnitude = np.hypot(cv2.Sobel(blurred, cv2.CV_32F, 1, 0), cv2.Sobel(blurred, cv2.CV_32F, 0, 1))
    low, high = np.nanpercentile(magnitude, [LOW_PERCENTILE, HIGH_PERCENTILE])
    scaled = np.clip((magnitude - low) / (high - low + np.finfo(np.float32).eps), 0.0, 1.0)
    return (scaled * U8_MAX).astype(np.float32)
