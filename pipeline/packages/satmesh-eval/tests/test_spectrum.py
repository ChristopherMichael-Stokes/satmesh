import numpy as np
import pytest
from rasterio.transform import from_origin
from scipy.ndimage import gaussian_filter

from satmesh_core import Aoi
from satmesh_data import Raster
from satmesh_eval.spectrum import (
    REFERENCE_BAND_CYCLES_PER_M,
    SampledWindow,
    band_power,
    detail_ratio,
    native_windows,
    stable_windows,
)

PIXEL_M = 0.25
SIDE_PX = 256
BLUR_SIGMA_M = 0.2


def _windows(images: list[np.ndarray]) -> list[SampledWindow]:
    return [SampledWindow(image, 0.0, 0.0) for image in images]


def _noise(seed: int) -> np.ndarray:
    return 50 * np.random.default_rng(seed).standard_normal((SIDE_PX, SIDE_PX)) + 128


def test_a_gaussian_blur_loses_power_as_its_transfer_function_says() -> None:
    # Gaussian of sigma s metres has |H(f)|^2 = exp(-4 pi^2 s^2 f^2); white noise has a flat
    # spectrum, so the normalised ratio is |H|^2 at the band's frequencies over |H|^2 at the
    # reference band's, which is within a few percent of 1
    sharp = [_noise(seed) for seed in range(40)]
    blurred = [gaussian_filter(image, BLUR_SIGMA_M / PIXEL_M) for image in sharp]
    edges = (0.5, 0.6)
    ratio = detail_ratio(_windows(blurred), PIXEL_M, _windows(sharp), PIXEL_M, edges).ratio[0]
    centre = np.mean(edges)
    reference_centre = np.mean(REFERENCE_BAND_CYCLES_PER_M)
    transfer = lambda f: np.exp(-4 * np.pi**2 * BLUR_SIGMA_M**2 * f**2)  # noqa: E731
    assert ratio == pytest.approx(transfer(centre) / transfer(reference_centre), rel=0.05)


def test_bands_past_an_images_nyquist_are_nan() -> None:
    coarse = _windows([_noise(seed) for seed in range(5)])
    power = band_power(coarse, 0.5, ((0.25, 0.5), (1.5, 2.0)))
    assert np.isfinite(power[0])
    assert np.isnan(power[1])


def test_identical_windows_have_a_ratio_of_one() -> None:
    windows = _windows([_noise(seed) for seed in range(5)])
    assert detail_ratio(windows, PIXEL_M, windows, PIXEL_M, (0.5, 1.0)).ratio[0] == pytest.approx(1)


def _noise_raster() -> tuple[Raster, Aoi]:
    pixels = np.random.default_rng(0).integers(0, 256, (3, 256, 256)).astype(np.uint8)
    transform = from_origin(400_000.0, 450_000.0, 0.5, 0.5)
    return Raster(pixels, transform, "EPSG:27700"), Aoi(
        crs="EPSG:27700", west=400_000, south=449_872, east=400_128, north=450_000
    )


def test_windows_tile_the_box_and_report_their_centres_in_british_national_grid() -> None:
    raster, box = _noise_raster()
    windows = native_windows(raster, box, window_m=32.0)
    assert len(windows) == 16
    assert windows[0].luma.shape == (64, 64)
    assert (windows[0].easting, windows[0].northing) == pytest.approx((400_016.0, 449_984.0))


def test_a_window_near_an_excluded_cell_is_dropped_and_a_distant_one_kept() -> None:
    raster, box = _noise_raster()
    windows = native_windows(raster, box, window_m=32.0)
    transform = from_origin(400_000.0, 450_000.0, 1.0, 1.0)
    excluded = np.zeros((128, 128), dtype=bool)
    excluded[4, 4] = True  # 4 m from the north-west corner, inside the first window
    kept = stable_windows(windows, excluded, transform, window_m=32.0)
    centres = {(w.easting, w.northing) for w in kept}
    assert (windows[0].easting, windows[0].northing) not in centres
    assert (windows[-1].easting, windows[-1].northing) in centres
