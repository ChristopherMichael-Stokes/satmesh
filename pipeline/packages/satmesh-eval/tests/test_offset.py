import numpy as np
import pytest
from pyproj import Transformer
from rasterio.transform import from_origin
from scipy.ndimage import fourier_shift, gaussian_filter

from satmesh_core import BRITISH_NATIONAL_GRID, Aoi
from satmesh_data import Raster
from satmesh_eval.offset import (
    GRID_M,
    UPSAMPLE_FACTOR,
    ShiftField,
    luminance_on_grid,
    null_response_threshold,
    reliable,
    summarise,
    window_shifts,
)

# skimage documents registration accurate to 1 / upsample_factor pixel
SHIFT_TOLERANCE_M = GRID_M / UPSAMPLE_FACTOR * 1.5


def texture(side_px: int = 768) -> np.ndarray:
    """Band-limited noise on a periodic grid, so a Fourier shift of it is exact."""
    noise = np.random.default_rng(0).normal(size=(side_px, side_px))
    return gaussian_filter(noise, 2.0, mode="wrap") * 60 + 120


def displaced(image: np.ndarray, east_m: float, north_m: float) -> np.ndarray:
    """`image` with its content moved east and north: rows run south, so north is up the rows."""
    shifted = fourier_shift(np.fft.fftn(image), (-north_m / GRID_M, east_m / GRID_M))
    return np.fft.ifftn(shifted).real


@pytest.mark.parametrize(("east_m", "north_m"), [(2.4, -0.8), (-1.137, 0.523), (0.0, 0.0)])
def test_a_known_displacement_is_recovered_in_every_window(east_m: float, north_m: float) -> None:
    reference = texture()
    field = window_shifts(reference, displaced(reference, east_m, north_m))
    assert np.isfinite(field.east_m).all()
    assert np.abs(field.east_m - east_m).max() < SHIFT_TOLERANCE_M
    assert np.abs(field.north_m - north_m).max() < SHIFT_TOLERANCE_M


def test_flat_windows_and_failed_matches_are_rejected() -> None:
    reference = texture()
    other = displaced(reference, 1.0, 0.0)
    reference[:, :256] = 100.0  # first window column carries no texture
    field = window_shifts(reference, other)
    assert np.isnan(field.east_m[:, 0]).all()
    assert np.isfinite(field.east_m[:, 2:]).all()
    # a shift past a quarter of the 64 m window is no offset
    far = window_shifts(texture(), displaced(texture(), 20.0, 0.0))
    assert np.isnan(far.east_m).all()


def test_summary_is_the_median_with_a_wider_interval_than_a_single_window() -> None:
    east = np.array([[2.0, 2.2, 2.4], [2.0, 2.2, 2.4], [np.nan, 2.2, 9.0]])
    estimate = summarise(ShiftField(east, -east / 2, np.ones_like(east)), block_windows=1)
    assert estimate.east_m == pytest.approx(2.2)
    assert estimate.north_m == pytest.approx(-1.1)
    assert (estimate.windows_used, estimate.windows_total) == (8, 9)
    assert estimate.east_interval_m[0] <= 2.2 <= estimate.east_interval_m[1]


def test_summary_of_nothing_raises() -> None:
    nothing = np.full((2, 2), np.nan)
    with pytest.raises(ValueError, match="no window"):
        summarise(ShiftField(nothing, nothing, nothing))


def test_resampling_averages_to_the_box_grid_and_takes_luma() -> None:
    box = Aoi(crs=BRITISH_NATIONAL_GRID, west=1000, south=2000, east=1010, north=2010)
    pixels = np.zeros((3, 100, 100), np.uint8)  # 0.1 m pixels
    pixels[:] = np.array([200, 100, 50], np.uint8)[:, None, None]
    raster = Raster(pixels, from_origin(1000, 2010, 0.1, 0.1), BRITISH_NATIONAL_GRID)
    luma = luminance_on_grid(raster, box, grid_m=0.5)
    assert luma.shape == (20, 20)
    # Rec. 709: 0.2126 * 200 + 0.7152 * 100 + 0.0722 * 50
    assert luma == pytest.approx(0.2126 * 200 + 0.7152 * 100 + 0.0722 * 50, abs=1e-3)


def test_unrelated_textures_set_a_threshold_that_true_matches_clear() -> None:
    reference = texture(1024)
    unrelated = gaussian_filter(np.random.default_rng(5).normal(size=(1024, 1024)), 2.0) * 60 + 120
    threshold = null_response_threshold(reference, unrelated)
    matched = window_shifts(reference, displaced(reference, 1.0, 0.5))
    assert threshold < np.nanmin(matched.response)
    noise_windows = window_shifts(reference, unrelated)
    assert np.isfinite(reliable(noise_windows, threshold).east_m).mean() < 0.1


def test_a_web_mercator_raster_lands_where_the_ostn15_transformation_puts_it() -> None:
    # a bright 3 x 3 px square at a known WGS84 point on a dark Web Mercator raster; the expected
    # BNG cell is pyproj's own best (OSTN15) transformation of that point
    lon, lat = -2.0015, 53.9236
    to_mercator = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    x0, y0 = to_mercator.transform(lon, lat)
    px = 0.3  # Web Mercator metres per pixel, about 0.18 m on the ground at 54 N
    side = 600
    pixels = np.zeros((3, side, side), np.uint8)
    centre = side // 2
    pixels[:, centre - 1 : centre + 2, centre - 1 : centre + 2] = 255
    transform = from_origin(x0 - px * (centre + 0.5), y0 + px * (centre + 0.5), px, px)
    raster = Raster(pixels, transform, "EPSG:3857")
    expected_e, expected_n = Transformer.from_crs(
        "EPSG:4326", BRITISH_NATIONAL_GRID, always_xy=True
    ).transform(lon, lat)
    box = Aoi(
        crs=BRITISH_NATIONAL_GRID,
        west=round(expected_e) - 20,
        south=round(expected_n) - 20,
        east=round(expected_e) + 20,
        north=round(expected_n) + 20,
    )
    luma = luminance_on_grid(raster, box, grid_m=0.25)
    row, col = np.unravel_index(np.argmax(luma), luma.shape)
    peak_e = box.west + (col + 0.5) * 0.25
    peak_n = box.north - (row + 0.5) * 0.25
    assert abs(peak_e - expected_e) < 0.3
    assert abs(peak_n - expected_n) < 0.3
