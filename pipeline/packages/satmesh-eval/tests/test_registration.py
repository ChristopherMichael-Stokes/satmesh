import numpy as np
import pytest
from scipy.ndimage import fourier_shift, gaussian_filter

from satmesh_core import BRITISH_NATIONAL_GRID, Aoi
from satmesh_eval.lidar_reference import gradient_magnitude_u8, intensity_gradient_image
from satmesh_eval.offset import GRID_M
from satmesh_eval.registration import (
    METHOD_RESIDUAL_M,
    TARGET_CELL_SIDE_M,
    UNCORRECTED_ERROR_BOUND_M,
    cell_boxes,
    cell_correction,
)

SIDE_PX = 1024
BOX = Aoi(crs=BRITISH_NATIONAL_GRID, west=399_000, south=447_000, east=399_256, north=447_256)
EAST_M, NORTH_M = 1.3, -0.6
# phase correlation recovers an exact Fourier shift to 1 / 100 px (offset.py); the median of many
# windows adds nothing, so the grid pixel over 50 bounds it
SHIFT_TOLERANCE_M = GRID_M / 50


def texture(seed: int) -> np.ndarray:
    """Band-limited noise on a periodic grid scaled to 0-255, so a Fourier shift of it is exact."""
    noise = gaussian_filter(
        np.random.default_rng(seed).normal(size=(SIDE_PX, SIDE_PX)), 2.0, mode="wrap"
    )
    scaled = (noise - noise.min()) / np.ptp(noise) * 255.0
    return scaled.astype(np.float32)


def displaced(image: np.ndarray, east_m: float, north_m: float) -> np.ndarray:
    """`image` with its content moved east and north: rows run south, so north is up the rows."""
    shifted = fourier_shift(np.fft.fftn(image), (-north_m / GRID_M, east_m / GRID_M))
    return np.fft.ifftn(shifted).real.astype(np.float32)


def test_a_displaced_image_is_measured_and_bounded_above_the_method_residual() -> None:
    reference = texture(0)
    cell, windows = cell_correction(BOX, reference, displaced(reference, EAST_M, NORTH_M))
    assert cell.status == "corrected"
    assert abs(cell.displacement_east_m - EAST_M) < SHIFT_TOLERANCE_M
    assert abs(cell.displacement_north_m - NORTH_M) < SHIFT_TOLERANCE_M
    assert METHOD_RESIDUAL_M <= cell.error_bound_m < 2 * METHOD_RESIDUAL_M
    assert cell.windows_used / cell.windows_total > 0.9
    assert windows is not None
    assert int(np.isfinite(windows.east_m).sum()) == cell.windows_used


def test_unrelated_images_leave_the_cell_uncorrected_with_the_survey_bound() -> None:
    cell, _ = cell_correction(BOX, texture(1), texture(2))
    assert cell.status == "uncorrected"
    assert (cell.displacement_east_m, cell.displacement_north_m) == (0.0, 0.0)
    assert cell.error_bound_m == UNCORRECTED_ERROR_BOUND_M


def test_flat_images_leave_the_cell_uncorrected() -> None:
    flat = np.zeros((SIDE_PX, SIDE_PX), np.float32)
    cell, windows = cell_correction(BOX, flat, flat)
    assert cell.status == "uncorrected"
    assert windows is None


def test_intensity_step_gives_a_gradient_ridge_on_the_edge() -> None:
    box = Aoi(crs=BRITISH_NATIONAL_GRID, west=1000, south=2000, east=1040, north=2040)
    easting, northing = np.meshgrid(np.arange(1000, 1040, 0.5), np.arange(2000, 2040, 0.5))
    xy = np.column_stack([easting.ravel(), northing.ravel()])
    step_east = 1020.0
    intensity = np.where(xy[:, 0] < step_east, 100.0, 400.0)
    image = intensity_gradient_image(xy, intensity, box)
    ridge_column = int(np.argmax(image.mean(axis=0)))
    ridge_east = box.west + (ridge_column + 0.5) * GRID_M
    assert abs(ridge_east - step_east) <= 1.0
    assert image.max() <= 255.0


def test_gradient_ignores_non_finite_pixels() -> None:
    image = np.tile(np.linspace(0, 100, 64, dtype=np.float32), (64, 1))
    image[10:20, 10:20] = np.nan
    assert np.isfinite(gradient_magnitude_u8(image)).all()


def area(width_m: float, height_m: float) -> Aoi:
    return Aoi(
        crs=BRITISH_NATIONAL_GRID,
        west=399_000,
        south=447_000,
        east=399_000 + width_m,
        north=447_000 + height_m,
    )


@pytest.mark.parametrize(
    ("width_m", "height_m", "columns", "rows"),
    [
        (500, 500, 1, 1),
        (1000, 1000, 1, 1),
        (1700, 600, 2, 1),
        (2400, 3600, 2, 4),
        (2501, 1003, 3, 1),
    ],
)
def test_cells_split_the_area_evenly_with_sides_near_the_target(
    width_m: float, height_m: float, columns: int, rows: int
) -> None:
    cells = cell_boxes(area(width_m, height_m))
    assert len(cells) == columns * rows
    assert sum((c.east - c.west) * (c.north - c.south) for c in cells) == pytest.approx(
        width_m * height_m
    )
    for cell in cells:
        for side in (cell.east - cell.west, cell.north - cell.south):
            assert 0.5 * TARGET_CELL_SIDE_M <= side <= 1.5 * TARGET_CELL_SIDE_M
        # on the 1 m lidar grid, so roofs can be matched over the cell itself
        assert all(edge.is_integer() for edge in (cell.west, cell.south, cell.east, cell.north))
