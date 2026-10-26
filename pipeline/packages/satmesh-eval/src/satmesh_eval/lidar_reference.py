"""Lidar intensity as a reference image for registering orthoimagery on the BNG grid.

First-return intensity from an EA point cloud shows roads, roofs, field boundaries and tree edges
without the orthoimage's shadows and colour, but its absolute scale differs between surveys
(median 26 to 477 across eight sites). The gradient magnitude of the interpolated intensity is
scale-free, and is what the Esri luma is matched against (`registration.py`).
"""

from collections.abc import Sequence
from pathlib import Path

import cv2
import laspy
import numpy as np
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import KDTree

from satmesh_core import Aoi
from satmesh_eval.offset import GRID_M

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
    laz_paths: Sequence[Path], box: Aoi, margin_m: float
) -> tuple[np.ndarray, np.ndarray]:
    """Return the (N, 2) easting and northing and the intensity of first returns near `box`.

    Points inside `box` grown by `margin_m` are kept; noise-class points are dropped.
    """
    xy_parts, intensity_parts = [], []
    for path in laz_paths:
        with laspy.open(path) as reader:
            for chunk in reader.chunk_iterator(READ_CHUNK_POINTS):
                keep = (
                    (chunk.return_number == FIRST_RETURN)
                    & (chunk.classification != CLASS_NOISE)
                    & (chunk.x >= box.west - margin_m)
                    & (chunk.x < box.east + margin_m)
                    & (chunk.y >= box.south - margin_m)
                    & (chunk.y < box.north + margin_m)
                )
                xy_parts.append(np.column_stack([chunk.x[keep], chunk.y[keep]]))
                intensity_parts.append(np.asarray(chunk.intensity[keep], np.float64))
    return np.concatenate(xy_parts), np.concatenate(intensity_parts)


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
    image = LinearNDInterpolator(xy, intensity, fill_value=np.nan)(ee, nn)
    gap = KDTree(xy).query(np.column_stack([ee.ravel(), nn.ravel()]))[0].reshape(ee.shape)
    image[gap > MAX_GAP_M] = np.nan
    return gradient_magnitude_u8(image)


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
