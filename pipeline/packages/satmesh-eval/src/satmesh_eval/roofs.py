"""Per-building offset of Esri roofs from their lidar footprint, with each roof's eave height.

Buildings are the 4-connected components of the normalised DSM (first-return DSM minus DTM) above
`MIN_ROOF_HEIGHT_M` that look like a building: large enough, compact (solidity against the convex
hull, fill of the minimum-area rectangle) and smooth (median absolute Laplacian of the DSM inside,
which separates roofs from tree crowns). Each building's DSM gradient magnitude, with a margin of
ground around it, is the template; normalised cross-correlation (`skimage.feature.match_template`)
against the Esri luma gradient magnitude within `SEARCH_RADIUS_M` gives the roof's displacement,
refined to subpixel by a parabola through the peak. A match is kept when its peak is high enough
and no other local maximum comes close to it.

The thresholds were declared before any offset was seen (S0b, `agent-docs/e9-results.md`).
Offsets are the displacement of the Esri roof from the lidar one, metres east and north (positive:
Esri east and north of the lidar), the convention of `offset.py`.
"""

from dataclasses import dataclass

import cv2
import numpy as np
from scipy import ndimage
from skimage.feature import match_template

from satmesh_core import BRITISH_NATIONAL_GRID, Aoi
from satmesh_eval.lidar_reference import gradient_magnitude_u8
from satmesh_eval.offset import GRID_M

LIDAR_GRID_M = 1.0  # EA DSM and DTM pixel
MIN_ROOF_HEIGHT_M = 3.0
MIN_AREA_M2 = 40.0
MAX_AREA_M2 = 20_000.0
MIN_SOLIDITY = 0.75  # area over convex hull area
MIN_RECTANGLE_FILL = 0.60  # area over minimum-area rectangle area
# median |Laplacian| of the 1 m DSM inside a footprint: set at the gap in the S0b histogram (clean
# roofs at most 0.21, tree crowns from 0.29, mostly above 2)
MAX_ROUGHNESS_M = 0.30
# ground around the footprint in the template, so its outline is matched against the Esri edges
TEMPLATE_MARGIN_M = 8.0
# past the 2.8 m largest Esri displacement measured at eight sites (registration.py), plus lean
SEARCH_RADIUS_M = 4.0
EDGE_SMOOTHING_PX = 2.0
# gradient magnitude, 0 to 255: a flat template has no outline to match
MIN_TEMPLATE_STD = 1e-3
MIN_PEAK = 0.30
MAX_RUNNER_UP_RATIO = 0.90
RUNNER_UP_RADIUS_PX = 6
# the eave, not the ridge, bounds the roof outline the template matches
EAVE_PERCENTILE = 10.0
MIN_INNER_PX = 5
LAPLACIAN = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=float)


@dataclass(frozen=True)
class RoofOffset:
    """One building's Esri displacement against its lidar footprint, in BNG metres.

    `easting_m`, `northing_m` is the centre of the footprint's bounding box; `eave_height_m` is the
    `EAVE_PERCENTILE` of the roof's height above ground; `peak` is the correlation at the match.
    """

    easting_m: float
    northing_m: float
    eave_height_m: float
    east_m: float
    north_m: float
    peak: float


@dataclass(frozen=True)
class _Footprint:
    rows: slice
    cols: slice
    mask: np.ndarray
    eave_height_m: float


def roof_offsets(
    surface: np.ndarray, ground: np.ndarray, esri_luma: np.ndarray, box: Aoi
) -> list[RoofOffset]:
    """Return the accepted roof offsets over `box`.

    `surface` and `ground` are the DSM and DTM on the `LIDAR_GRID_M` grid of `box` (north up, NaN
    for no data); `esri_luma` is the Esri luma on the `GRID_M` grid of the same box.
    """
    if box.crs != BRITISH_NATIONAL_GRID:
        msg = f"roofs are matched on the {BRITISH_NATIONAL_GRID} grid, got {box.crs}"
        raise ValueError(msg)
    scale = round(LIDAR_GRID_M / GRID_M)
    if esri_luma.shape != (surface.shape[0] * scale, surface.shape[1] * scale):
        msg = f"luma {esri_luma.shape} is not the lidar grid {surface.shape} times {scale}"
        raise ValueError(msg)
    surface, ground = np.nan_to_num(surface), np.nan_to_num(ground)
    reference = _edges(_upsampled(surface, scale))
    esri = _edges(esri_luma)
    offsets = []
    for footprint in _buildings(surface, ground):
        match = _match(reference, esri, _template_window(footprint, scale))
        if match is None:
            continue
        east_m, north_m, peak = match
        offsets.append(
            RoofOffset(
                easting_m=box.west
                + LIDAR_GRID_M * (footprint.cols.start + footprint.cols.stop) / 2,
                northing_m=box.north
                - LIDAR_GRID_M * (footprint.rows.start + footprint.rows.stop) / 2,
                eave_height_m=footprint.eave_height_m,
                east_m=east_m,
                north_m=north_m,
                peak=peak,
            )
        )
    return offsets


def _buildings(surface: np.ndarray, ground: np.ndarray) -> list[_Footprint]:
    raised = surface - ground
    labels, _ = ndimage.label(raised > MIN_ROOF_HEIGHT_M)
    roughness = np.abs(ndimage.convolve(surface, LAPLACIAN, mode="nearest"))
    footprints = []
    for index, (rows, cols) in enumerate(ndimage.find_objects(labels), start=1):
        mask = labels[rows, cols] == index
        if not _building_shaped(mask, rows, cols, labels.shape):
            continue
        inner = ndimage.binary_erosion(mask, iterations=1)
        if inner.sum() < MIN_INNER_PX:
            inner = mask
        if np.median(roughness[rows, cols][inner]) > MAX_ROUGHNESS_M:
            continue
        eave = float(np.percentile(raised[rows, cols][inner], EAVE_PERCENTILE))
        footprints.append(_Footprint(rows, cols, mask, eave))
    return footprints


def _building_shaped(mask: np.ndarray, rows: slice, cols: slice, shape: tuple[int, ...]) -> bool:
    area_m2 = float(mask.sum()) * LIDAR_GRID_M**2
    if not MIN_AREA_M2 <= area_m2 <= MAX_AREA_M2:
        return False
    if rows.start == 0 or cols.start == 0 or rows.stop == shape[0] or cols.stop == shape[1]:
        return False
    contours, _ = cv2.findContours(
        np.pad(mask, 1).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
    )
    outline = max(contours, key=cv2.contourArea)
    hull_px = cv2.contourArea(cv2.convexHull(outline))
    _, (width, height), _ = cv2.minAreaRect(outline)
    area_px = float(mask.sum())
    return (
        hull_px > 0
        and width * height > 0
        and area_px / hull_px >= MIN_SOLIDITY
        and area_px / (width * height) >= MIN_RECTANGLE_FILL
    )


def _upsampled(image: np.ndarray, scale: int) -> np.ndarray:
    # bilinear at the fine grid's pixel centres, in coarse pixel coordinates
    rows = (np.arange(image.shape[0] * scale) + 0.5) / scale - 0.5
    cols = (np.arange(image.shape[1] * scale) + 0.5) / scale - 0.5
    return ndimage.map_coordinates(
        image, np.meshgrid(rows, cols, indexing="ij"), order=1, mode="nearest"
    )


def _edges(image: np.ndarray) -> np.ndarray:
    return ndimage.gaussian_filter(gradient_magnitude_u8(image), EDGE_SMOOTHING_PX)


def _template_window(footprint: _Footprint, scale: int) -> tuple[slice, slice]:
    margin_px = int(TEMPLATE_MARGIN_M / GRID_M)
    return (
        slice(footprint.rows.start * scale - margin_px, footprint.rows.stop * scale + margin_px),
        slice(footprint.cols.start * scale - margin_px, footprint.cols.stop * scale + margin_px),
    )


def _match(
    reference: np.ndarray, esri: np.ndarray, window: tuple[slice, slice]
) -> tuple[float, float, float] | None:
    rows, cols = window
    radius_px = int(SEARCH_RADIUS_M / GRID_M)
    if (
        rows.start - radius_px < 0
        or cols.start - radius_px < 0
        or rows.stop + radius_px > reference.shape[0]
        or cols.stop + radius_px > reference.shape[1]
    ):
        return None
    template = reference[rows, cols]
    if template.std() < MIN_TEMPLATE_STD:
        return None
    search = esri[
        rows.start - radius_px : rows.stop + radius_px,
        cols.start - radius_px : cols.stop + radius_px,
    ]
    ncc = match_template(search, template, pad_input=False)
    peak_r, peak_c = (int(i) for i in np.unravel_index(np.argmax(ncc), ncc.shape))
    peak = float(ncc[peak_r, peak_c])
    if peak_r in {0, ncc.shape[0] - 1} or peak_c in {0, ncc.shape[1] - 1}:
        return None
    if peak < MIN_PEAK or _runner_up_ratio(ncc, peak_r, peak_c) > MAX_RUNNER_UP_RATIO:
        return None
    sub_r = _parabola_vertex(*ncc[peak_r - 1 : peak_r + 2, peak_c])
    sub_c = _parabola_vertex(*ncc[peak_r, peak_c - 1 : peak_c + 2])
    east_m = (peak_c + sub_c - radius_px) * GRID_M
    north_m = -(peak_r + sub_r - radius_px) * GRID_M
    return float(east_m), float(north_m), peak


def _runner_up_ratio(ncc: np.ndarray, peak_r: int, peak_c: int) -> float:
    local_max = (ncc == ndimage.maximum_filter(ncc, size=2 * RUNNER_UP_RADIUS_PX + 1)) & (ncc > 0)
    local_max[peak_r, peak_c] = False
    return float(ncc[local_max].max() / ncc[peak_r, peak_c]) if local_max.any() else 0.0


def _parabola_vertex(before: float, at: float, after: float) -> float:
    """Offset of the vertex of the parabola through three equally spaced samples, in samples."""
    return 0.5 * (before - after) / (before - 2 * at + after)
