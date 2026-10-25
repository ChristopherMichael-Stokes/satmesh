"""Horizontal offset between two orthoimages, by phase correlation in a grid of windows.

Both images are resampled to one BNG grid and reduced to Rec. 709 luma. Each window pair goes to
`skimage.registration.phase_cross_correlation` (Kuglin and Hines 1975; subpixel by matrix-multiply
DFT upsampling, Guizar-Sicairos, Thurman and Fienup 2008, Opt. Lett. 33, 156), accurate to
1/`UPSAMPLE_FACTOR` pixel. The window shifts are summarised by median and NMAD with a block
bootstrap interval over the window grid, because orthophotos carry spatially varying residuals and
one number is only a summary of the field.

Phase-correlation shifts alone are unreliable on real pairs (different dates, leaf state and
shadows): flat or changed windows return confident-looking wrong shifts, and skimage's `error` is
1 for every window under phase normalisation. Each window therefore also gets the correlation
peak height from `cv2.phaseCorrelate` (its `response`), and only windows above the 99th percentile
of the response between unrelated windows of the same two images are kept.

Offsets are the displacement of the second ("other") image relative to the first ("reference"), in
metres east and north: other(x) = reference(x - offset).
"""

from dataclasses import dataclass

import cv2
import numpy as np
from geoutils.stats import nmad
from pyproj import CRS, Transformer
from pyproj.transformer import TransformerGroup
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from scipy.ndimage import gaussian_filter, map_coordinates
from skimage.registration import phase_cross_correlation

from satmesh_core import BRITISH_NATIONAL_GRID, Aoi
from satmesh_data import Raster
from satmesh_eval.heights import block_bootstrap_interval

LUMA_709 = np.array([0.2126, 0.7152, 0.0722])
# both sources reduced to this ground pixel: coarser than Esri z19 at 54 N (0.176 m) so neither
# image is upsampled, and finer than the offsets measured (about 2 m) to resolve them (tunable)
GRID_M = 0.25
# 64 m windows hold several fields, hedges or buildings (tunable)
WINDOW_PX = 256
WINDOW_STEP_PX = WINDOW_PX // 2
UPSAMPLE_FACTOR = 100  # shift resolution 0.01 px (tunable)
# flat grass and shadow carry no phase information; luma standard deviation, 0 to 255 (tunable)
MIN_WINDOW_STD = 8.0
# a shift past a quarter window is a failed match, not an offset
MAX_SHIFT_FRACTION_OF_WINDOW = 0.25
NODATA_FRACTION_LIMIT = 0.01
BOOTSTRAP_BLOCK_WINDOWS = 4
# Gaussian sigma, in source pixels, per source-pixels-per-grid-cell: half the decimation ratio is
# the usual anti-alias width before bilinear sampling
SMOOTHING_SIGMA_PER_GRID_RATIO = 0.5
NULL_PERCENTILE = 99.0  # false-match rate of 1 % among unrelated windows (tunable)
NULL_PAIRS = 400
NULL_SEPARATION_WINDOWS = 2  # unrelated windows lie at least this many windows apart


@dataclass(frozen=True)
class ShiftField:
    """Window shifts in metres on the window grid; NaN where a window was rejected."""

    east_m: np.ndarray
    north_m: np.ndarray
    response: np.ndarray


@dataclass(frozen=True)
class OffsetEstimate:
    """Median offset of the shift field with spread and a bootstrap interval, in metres."""

    east_m: float
    north_m: float
    east_nmad_m: float
    north_nmad_m: float
    east_interval_m: tuple[float, float]
    north_interval_m: tuple[float, float]
    windows_used: int
    windows_total: int
    response_threshold: float


def luminance_on_grid(raster: Raster, box: Aoi, grid_m: float = GRID_M) -> np.ndarray:
    """Resample `raster` to the BNG grid of `box` and return its luma.

    A BNG raster is area-averaged. Any other CRS goes through PROJ's best transformation, which
    must include OSTN15: GDAL as bundled with rasterio has no UK grids and falls back to a
    Helmert shift that is 1.5 to 2 m off in Great Britain, as large as the offset measured. Those
    pixels are smoothed to the grid's scale and sampled bilinearly.
    """
    if box.crs != BRITISH_NATIONAL_GRID:
        msg = f"the comparison grid is in {BRITISH_NATIONAL_GRID}, got {box.crs}"
        raise ValueError(msg)
    cols, rows = round((box.east - box.west) / grid_m), round((box.north - box.south) / grid_m)
    if CRS.from_user_input(raster.crs) == CRS.from_user_input(BRITISH_NATIONAL_GRID):
        resampled = np.zeros((raster.pixels.shape[0], rows, cols), np.float32)
        reproject(
            raster.pixels,
            resampled,
            src_transform=raster.transform,
            src_crs=raster.crs,
            dst_transform=from_origin(box.west, box.north, grid_m, grid_m),
            dst_crs=BRITISH_NATIONAL_GRID,
            resampling=Resampling.average,
        )
    else:
        resampled = _sample_through_proj(raster, box, grid_m, rows, cols)
    return np.tensordot(LUMA_709, resampled, axes=1)


def _sample_through_proj(
    raster: Raster, box: Aoi, grid_m: float, rows: int, cols: int
) -> np.ndarray:
    group = TransformerGroup(BRITISH_NATIONAL_GRID, raster.crs, always_xy=True)
    if not group.best_available:
        msg = f"PROJ lacks the grids for {BRITISH_NATIONAL_GRID} to {raster.crs}; run `pyproj sync`"
        raise ValueError(msg)
    eastings = box.west + grid_m * (np.arange(cols) + 0.5)
    northings = box.north - grid_m * (np.arange(rows) + 0.5)
    x, y = group.transformers[0].transform(*np.meshgrid(eastings, northings))
    inverse = ~raster.transform
    source_cols, source_rows = inverse @ (x, y)
    # source pixels are smaller than the grid's: smooth over the ratio before sampling
    sigma_px = SMOOTHING_SIGMA_PER_GRID_RATIO * grid_m / _source_ground_pixel_m(raster, box)
    return np.stack(
        [
            map_coordinates(
                gaussian_filter(band.astype(np.float32), sigma_px),
                [source_rows, source_cols],
                order=1,
                mode="nearest",
            )
            for band in raster.pixels
        ]
    )


def _source_ground_pixel_m(raster: Raster, box: Aoi) -> float:
    """Ground size of one source pixel at the box centre, from two points one pixel apart."""
    centre_e, centre_n = (box.west + box.east) / 2, (box.south + box.north) / 2
    to_source = Transformer.from_crs(BRITISH_NATIONAL_GRID, raster.crs, always_xy=True)
    to_bng = Transformer.from_crs(raster.crs, BRITISH_NATIONAL_GRID, always_xy=True)
    x, y = to_source.transform(centre_e, centre_n)
    e1, n1 = to_bng.transform(x + abs(raster.transform.a), y)
    return float(np.hypot(e1 - centre_e, n1 - centre_n))


def window_shifts(  # noqa: PLR0913 (window-grid settings, each a tunable)
    reference: np.ndarray,
    other: np.ndarray,
    *,
    grid_m: float = GRID_M,
    window_px: int = WINDOW_PX,
    step_px: int = WINDOW_STEP_PX,
    upsample_factor: int = UPSAMPLE_FACTOR,
) -> ShiftField:
    """Return the offset of `other` against `reference` in every window of a regular grid."""
    if reference.shape != other.shape:
        msg = f"images differ in shape: {reference.shape} and {other.shape}"
        raise ValueError(msg)
    starts_r = range(0, reference.shape[0] - window_px + 1, step_px)
    starts_c = range(0, reference.shape[1] - window_px + 1, step_px)
    east = np.full((len(starts_r), len(starts_c)), np.nan)
    north = np.full_like(east, np.nan)
    response = np.full_like(east, np.nan)
    limit_px = MAX_SHIFT_FRACTION_OF_WINDOW * window_px
    taper = np.outer(np.hanning(window_px), np.hanning(window_px))
    for i, r in enumerate(starts_r):
        for j, c in enumerate(starts_c):
            ref_w = reference[r : r + window_px, c : c + window_px]
            oth_w = other[r : r + window_px, c : c + window_px]
            if not (_usable(ref_w) and _usable(oth_w)):
                continue
            shift, _, _ = phase_cross_correlation(
                _tapered(ref_w, taper),
                _tapered(oth_w, taper),
                upsample_factor=upsample_factor,
                normalization="phase",
            )
            if np.hypot(*shift) > limit_px:
                continue
            response[i, j] = _peak_response(ref_w, oth_w)
            # skimage returns the shift that registers `other` onto `reference`; rows run south
            east[i, j] = -shift[1] * grid_m
            north[i, j] = shift[0] * grid_m
    return ShiftField(east, north, response)


def null_response_threshold(
    reference: np.ndarray,
    other: np.ndarray,
    window_px: int = WINDOW_PX,
    seed: int = 0,
) -> float:
    """Return the `NULL_PERCENTILE` of the peak response between unrelated windows.

    Pairs a window of `reference` with a window of `other` at least `NULL_SEPARATION_WINDOWS`
    windows away, among the textured windows only, so any correlation peak is chance.
    """
    rng = np.random.default_rng(seed)
    rows, cols = reference.shape[0] - window_px, reference.shape[1] - window_px
    responses: list[float] = []
    for _ in range(NULL_PAIRS * 20):
        r1, c1, r2, c2 = (int(rng.integers(limit + 1)) for limit in (rows, cols, rows, cols))
        if max(abs(r1 - r2), abs(c1 - c2)) < NULL_SEPARATION_WINDOWS * window_px:
            continue
        a = reference[r1 : r1 + window_px, c1 : c1 + window_px]
        b = other[r2 : r2 + window_px, c2 : c2 + window_px]
        if _usable(a) and _usable(b):
            responses.append(_peak_response(a, b))
        if len(responses) == NULL_PAIRS:
            break
    if len(responses) < NULL_PAIRS // 4:
        msg = f"only {len(responses)} textured unrelated window pairs found"
        raise ValueError(msg)
    return float(np.percentile(responses, NULL_PERCENTILE))


def reliable(field: ShiftField, threshold: float) -> ShiftField:
    """Keep the windows whose peak response is at least `threshold`; the rest become NaN."""
    keep = field.response >= threshold
    return ShiftField(
        np.where(keep, field.east_m, np.nan),
        np.where(keep, field.north_m, np.nan),
        np.where(keep, field.response, np.nan),
    )


def measure_offset(
    reference: np.ndarray, other: np.ndarray, grid_m: float = GRID_M
) -> tuple[OffsetEstimate, ShiftField]:
    """Offset of `other` against `reference` (same grid, luma): reliable windows, summarised."""
    threshold = null_response_threshold(reference, other)
    field = reliable(window_shifts(reference, other, grid_m=grid_m), threshold)
    return summarise(field, threshold), field


def summarise(
    field: ShiftField,
    response_threshold: float = 0.0,
    block_windows: int = BOOTSTRAP_BLOCK_WINDOWS,
    seed: int = 0,
) -> OffsetEstimate:
    """Median, NMAD and block-bootstrap interval of a shift field; raises if every window failed."""
    used = int(np.isfinite(field.east_m).sum())
    if used == 0:
        msg = "no window produced a usable shift"
        raise ValueError(msg)
    return OffsetEstimate(
        east_m=float(np.nanmedian(field.east_m)),
        north_m=float(np.nanmedian(field.north_m)),
        east_nmad_m=float(nmad(field.east_m[np.isfinite(field.east_m)])),
        north_nmad_m=float(nmad(field.north_m[np.isfinite(field.north_m)])),
        east_interval_m=block_bootstrap_interval(field.east_m, block_windows, np.median, seed=seed),
        north_interval_m=block_bootstrap_interval(
            field.north_m, block_windows, np.median, seed=seed
        ),
        windows_used=used,
        windows_total=field.east_m.size,
        response_threshold=response_threshold,
    )


def _peak_response(first: np.ndarray, second: np.ndarray) -> float:
    window = cv2.createHanningWindow(first.shape[::-1], cv2.CV_64F)
    _, response = cv2.phaseCorrelate(
        first.astype(np.float64) - first.mean(), second.astype(np.float64) - second.mean(), window
    )
    return float(response)


def _tapered(window: np.ndarray, taper: np.ndarray) -> np.ndarray:
    # window edges are not periodic: without the taper their discontinuity makes the zero-shift
    # peak dominate
    return (window - window.mean()) * taper


def _usable(window: np.ndarray) -> bool:
    return bool(window.std() >= MIN_WINDOW_STD and (window == 0).mean() <= NODATA_FRACTION_LIMIT)
