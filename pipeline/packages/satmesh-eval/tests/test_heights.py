import numpy as np
import pytest
from rasterio.transform import from_origin

from satmesh_eval.heights import (
    block_bootstrap_interval,
    score_by_stratum,
    score_heights,
)
from satmesh_eval.strata import SLOPE_CLASS_NAMES, raised_object_mask, slope_classes


def test_score_matches_the_definitions_worked_by_hand() -> None:
    # sorted |dh| = 0 1 1 3 3; median 0; MAD = median(3 1 0 1 3) = 1; n = 5
    # p68.3: ceil(0.683 * 5) = 4th value = 3; p95: ceil(4.75) = 5th value = 3; RMSE sqrt(20 / 5)
    score = score_heights(np.array([-3.0, -1.0, 0.0, 1.0, 3.0]))
    assert score.count == 5
    assert score.median_m == 0.0
    assert score.nmad_m == pytest.approx(1.4826)
    assert score.quantile_683_m == 3.0
    assert score.quantile_95_m == 3.0
    assert score.rmse_m == pytest.approx(2.0)


def test_nmad_ignores_an_outlier_that_rmse_does_not() -> None:
    errors = np.array([-3.0, -1.0, 0.0, 1.0, 3.0, 1000.0])
    score = score_heights(errors)
    # sorted -3 -1 0 1 3 1000: median (0 + 1) / 2 = 0.5; |dh - 0.5| sorted 0.5 0.5 1.5 2.5 3.5 999.5
    assert score.median_m == pytest.approx(0.5)
    assert score.nmad_m < 5
    assert score.rmse_m > 400


def test_nan_is_ignored_and_all_nan_raises() -> None:
    assert score_heights(np.array([np.nan, 2.0, 2.0])).count == 2
    with pytest.raises(ValueError, match="no finite"):
        score_heights(np.full(4, np.nan))


def test_strata_are_scored_separately_and_empty_ones_dropped() -> None:
    errors = np.array([1.0, 1.0, -2.0, -2.0])
    labels = np.array([0, 0, 1, 1])
    scores = score_by_stratum(errors, labels, {0: "a", 1: "b", 2: "c"})
    assert set(scores) == {"a", "b"}
    assert scores["a"].median_m == 1.0
    assert scores["b"].median_m == -2.0


def test_block_bootstrap_is_wider_than_a_pixel_bootstrap_when_errors_are_blocky() -> None:
    rng = np.random.default_rng(1)
    block = 10
    # each 10 x 10 block shares one error drawn from N(0, 1): the median's true spread is that
    # of 100 blocks (about 1.25 / sqrt(100) = 0.125), a pixel bootstrap would see 10,000 samples
    # and report about a tenth of that
    errors = np.kron(rng.normal(size=(10, 10)), np.ones((block, block)))
    low, high = block_bootstrap_interval(errors, block, np.median, draws=500)
    pixel_low, pixel_high = block_bootstrap_interval(errors, 1, np.median, draws=500)
    assert high - low > 3 * (pixel_high - pixel_low)
    assert low <= float(np.median(errors)) <= high


def test_slope_classes_follow_a_plane_of_known_angle() -> None:
    # a plane rising 1 m per 1 m pixel is 45 degrees: the steepest class
    rows, cols = 20, 20
    heights = np.tile(np.arange(cols, dtype=np.float64), (rows, 1))
    labels = slope_classes(heights, from_origin(0, rows, 1, 1), 27700)
    steepest = max(SLOPE_CLASS_NAMES)
    assert (labels[5:-5, 5:-5] == steepest).all()
    flat = slope_classes(np.zeros((rows, cols)), from_origin(0, rows, 1, 1), 27700)
    assert (flat[5:-5, 5:-5] == 0).all()


def test_raised_objects_are_above_the_threshold() -> None:
    ground = np.zeros(3)
    surface = np.array([0.0, 2.0, 2.5])
    np.testing.assert_array_equal(raised_object_mask(surface, ground, 2.0), [False, False, True])
