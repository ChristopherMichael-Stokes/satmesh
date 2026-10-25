"""Texture detail by the radially averaged power spectrum of luma, each image at its own scale.

Each image is cut into non-overlapping square windows of one ground size, tapered with a Hann
window with the mean removed, and the squared magnitude of the 2D FFT is averaged over windows and
over the samples whose radial frequency (cycles per metre of ground) falls in a band. Frequencies
past an image's Nyquist (half a cycle per ground pixel) have no data and give NaN. A spectrum is
divided by its own mean power in a low-frequency reference band, which cancels contrast and date
differences between captures. This is the method of S6 (`s6-results.md`); it is practice, not a
published protocol, and it reads date and scene change as lost detail.
"""

from dataclasses import dataclass
from itertools import pairwise

import numpy as np
from pyproj import Transformer
from rasterio.transform import Affine
from scipy import ndimage

from satmesh_core import BRITISH_NATIONAL_GRID, Aoi
from satmesh_data import Raster
from satmesh_eval.offset import LUMA_709, MIN_WINDOW_STD, source_ground_pixel_m

# ground size of one window: sets the lowest resolvable frequency (1 / WINDOW_M) (tunable)
WINDOW_M = 64.0
# mean power here normalises a spectrum: periods 4 to 20 m, below any detail under test (S6)
REFERENCE_BAND_CYCLES_PER_M = (0.05, 0.25)
# bands of S6, cycles per metre; the last passes Esri z19's Nyquist (2.85) and ends at EA's (5.0)
DETAIL_BAND_EDGES_CYCLES_PER_M = (0.25, 0.5, 1.0, 1.5, 2.85, 5.0)


@dataclass(frozen=True)
class SampledWindow:
    """A luma window and the BNG position of its centre."""

    luma: np.ndarray
    easting: float
    northing: float


@dataclass(frozen=True)
class DetailRatio:
    """Normalised power of one image over another, per band; NaN where either has no data."""

    band_edges_cycles_per_m: tuple[float, ...]
    ratio: np.ndarray
    windows_other: int
    windows_reference: int


def native_windows(raster: Raster, box: Aoi, window_m: float = WINDOW_M) -> list[SampledWindow]:
    """Cut the part of `raster` inside `box` into windows of `window_m` ground size, native pixels.

    Windows with too little contrast to carry texture (flat grass, shadow, water) and windows
    with no data are dropped.
    """
    to_raster = Transformer.from_crs(BRITISH_NATIONAL_GRID, raster.crs, always_xy=True)
    to_bng = Transformer.from_crs(raster.crs, BRITISH_NATIONAL_GRID, always_xy=True)
    luma = np.tensordot(LUMA_709, raster.pixels.astype(np.float64), axes=1)
    side_px = round(window_m / source_ground_pixel_m(raster, box))
    row_start, row_stop, col_start, col_stop = _box_pixel_bounds(raster, box, to_raster, luma.shape)
    windows = []
    for row in range(row_start, row_stop - side_px + 1, side_px):
        for col in range(col_start, col_stop - side_px + 1, side_px):
            tile = luma[row : row + side_px, col : col + side_px]
            if tile.std() < MIN_WINDOW_STD or (tile == 0).any():
                continue
            x, y = raster.transform @ (col + side_px / 2, row + side_px / 2)
            easting, northing = to_bng.transform(x, y)
            windows.append(SampledWindow(tile, easting, northing))
    return windows


def stable_windows(
    windows: list[SampledWindow], excluded: np.ndarray, transform: Affine, window_m: float
) -> list[SampledWindow]:
    """Keep windows whose whole footprint lies clear of `excluded`.

    `excluded` is a BNG raster placed by `transform`. It is dilated by the window's half-diagonal
    so that a window centre outside it means the footprint is.
    """
    radius_cells = int(np.ceil(window_m * np.sqrt(2) / 2 / abs(transform.a)))
    axis = np.arange(-radius_cells, radius_cells + 1)
    disc = np.hypot(*np.meshgrid(axis, axis)) <= radius_cells
    blocked = ndimage.binary_dilation(excluded, structure=disc)
    kept = []
    for window in windows:
        col, row = (int(v) for v in ~transform @ (window.easting, window.northing))
        if 0 <= row < blocked.shape[0] and 0 <= col < blocked.shape[1] and not blocked[row, col]:
            kept.append(window)
    return kept


def band_power(
    windows: list[SampledWindow], pixel_m: float, bands: tuple[tuple[float, float], ...]
) -> np.ndarray:
    """Mean tapered-FFT power per frequency band (cycles per metre), NaN past Nyquist."""
    side = windows[0].luma.shape[0]
    taper = np.outer(np.hanning(side), np.hanning(side))
    frequency = np.hypot(*np.meshgrid(*(np.fft.fftfreq(side, d=pixel_m),) * 2))
    nyquist = 0.5 / pixel_m
    total = np.zeros((side, side))
    for window in windows:
        total += np.abs(np.fft.fft2((window.luma - window.luma.mean()) * taper)) ** 2
    mean_power = total / len(windows)
    return np.array(
        [
            mean_power[(frequency >= low) & (frequency < min(high, nyquist))].mean()
            if low < nyquist
            else np.nan
            for low, high in bands
        ]
    )


def detail_ratio(
    other: list[SampledWindow],
    other_pixel_m: float,
    reference: list[SampledWindow],
    reference_pixel_m: float,
    edges: tuple[float, ...] = DETAIL_BAND_EDGES_CYCLES_PER_M,
) -> DetailRatio:
    """Normalised power of `other` over `reference` in each band between `edges`."""
    bands = (REFERENCE_BAND_CYCLES_PER_M, *pairwise(edges))
    power_other = band_power(other, other_pixel_m, bands)
    power_reference = band_power(reference, reference_pixel_m, bands)
    ratio = (power_other[1:] / power_other[0]) / (power_reference[1:] / power_reference[0])
    return DetailRatio(edges, ratio, len(other), len(reference))


def _box_pixel_bounds(
    raster: Raster, box: Aoi, to_raster: Transformer, shape: tuple[int, int]
) -> tuple[int, int, int, int]:
    """Return (row start, row stop, column start, column stop) of the pixels inside `box`."""
    corners = [
        to_raster.transform(x, y) for x in (box.west, box.east) for y in (box.south, box.north)
    ]
    cols, rows = ~raster.transform @ np.array(corners).T
    return (
        max(0, int(np.ceil(rows.min()))),
        min(shape[0], int(np.floor(rows.max()))),
        max(0, int(np.ceil(cols.min()))),
        min(shape[1], int(np.floor(cols.max()))),
    )
