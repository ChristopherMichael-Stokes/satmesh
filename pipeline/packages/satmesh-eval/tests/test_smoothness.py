import numpy as np
import pytest
from rasterio.transform import from_origin

from satmesh_eval.smoothness import smoothness_score, weighted_quantile
from satmesh_eval.visibility import raster_mesh

TRANSFORM = from_origin(1000.0, 1060.0, 1.0, 1.0)
SLOPE = 0.2
SIZE = 60


def _ramp() -> np.ndarray:
    # surface rising 0.2 m per metre toward the east and 0.1 toward the north: aspect not a
    # multiple of 45 degrees
    cols = np.arange(SIZE)[None, :] + 0.5
    rows = np.arange(SIZE)[:, None] + 0.5
    return 100.0 + SLOPE * cols + 0.1 * (SIZE - rows)


def _staircase(ramp: np.ndarray, step_px: int) -> np.ndarray:
    # every step_px x step_px block takes the ramp's value at its own corner pixel
    index = (np.arange(SIZE) // step_px) * step_px
    return ramp[np.ix_(index, index)]


def test_a_mesh_equal_to_a_ramp_has_no_normal_error_and_no_flat_facets() -> None:
    ramp = _ramp()
    score = smoothness_score(raster_mesh(ramp, TRANSFORM), ramp, ramp - 0.1, TRANSFORM)
    assert score.open_normal_p90_deg == pytest.approx(0.0, abs=1e-4)
    assert score.flat_on_slope_fraction == 0.0
    assert score.grid_aspect_excess == pytest.approx(0.0, abs=1e-9)


def test_a_staircase_over_a_ramp_has_large_normal_error_and_flat_facets() -> None:
    ramp = _ramp()
    stairs = _staircase(ramp, 3)
    score = smoothness_score(raster_mesh(stairs, TRANSFORM), ramp, ramp - 0.1, TRANSFORM)
    assert score.open_normal_median_deg > 5.0
    assert score.flat_on_slope_fraction > 0.3
    assert score.grid_aspect_excess > 0.3


def test_weighted_quantile_counts_weights_not_samples() -> None:
    values = np.array([1.0, 2.0, 3.0])
    weights = np.array([1.0, 1.0, 8.0])
    assert weighted_quantile(values, weights, 0.5) == 3.0
    assert weighted_quantile(values, np.ones(3), 0.5) == 2.0
