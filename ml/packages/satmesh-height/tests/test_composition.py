import numpy as np
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

from satmesh_height.composition import block_mean, nearest_up, variant_a, variant_b
from satmesh_height.kriging import (
    PointCovariance,
    fit_point_covariance,
    krige,
    krige_region,
)
from satmesh_height.pixtransform import ensemble

COVARIANCE = PointCovariance(sill=4.0, practical_range_pixels=7.0)
# float32 spacing at 200 m is 2^-16 = 1.5e-5; rounding a value to float32 errs by half of that
FLOAT32_ABSOLUTE_TOLERANCE = 1e-5
METRES = st.floats(-100.0, 100.0, width=32)
no_deadline = settings(deadline=None, max_examples=25, suppress_health_check=[HealthCheck.too_slow])


@st.composite
def scenes(draw: st.DrawFn) -> tuple[np.ndarray, np.ndarray, int]:
    """A PixTransform output, the source cell means and the factor."""
    factor = draw(st.integers(2, 4))
    rows, cols = draw(st.integers(1, 4)), draw(st.integers(1, 4))
    pix = draw(arrays(np.float64, (rows * factor, cols * factor), elements=METRES))
    source = draw(arrays(np.float64, (rows, cols), elements=METRES))
    return pix, source, factor


@given(st.data())
def test_block_mean_inverts_nearest_up(data: st.DataObject) -> None:
    factor = data.draw(st.integers(1, 5))
    coarse = data.draw(arrays(np.float64, (3, 2), elements=METRES))
    np.testing.assert_array_equal(block_mean(nearest_up(coarse, factor), factor), coarse)


@given(st.data())
def test_nearest_up_of_block_means_keeps_the_total(data: st.DataObject) -> None:
    factor = data.draw(st.integers(1, 4))
    fine = data.draw(arrays(np.float64, (2 * factor, 3 * factor), elements=METRES))
    flattened = nearest_up(block_mean(fine, factor), factor)
    np.testing.assert_allclose(flattened.sum(), fine.sum(), rtol=0, atol=1e-9)


def test_block_mean_of_a_known_grid() -> None:
    fine = np.arange(16, dtype=np.float64).reshape(4, 4)
    # top-left 2 x 2 block holds 0, 1, 4, 5
    np.testing.assert_allclose(block_mean(fine, 2), [[2.5, 4.5], [10.5, 12.5]])


@no_deadline
@given(scenes())
def test_variant_a_reproduces_the_source_to_float32_rounding(
    scene: tuple[np.ndarray, np.ndarray, int],
) -> None:
    pix, source, factor = scene
    result = variant_a(pix, source, factor).astype(np.float32)
    np.testing.assert_allclose(
        block_mean(result.astype(np.float64), factor),
        source,
        rtol=0,
        atol=FLOAT32_ABSOLUTE_TOLERANCE,
    )


@no_deadline
@given(scenes())
def test_variant_b_reproduces_the_source_to_float32_rounding(
    scene: tuple[np.ndarray, np.ndarray, int],
) -> None:
    pix, source, factor = scene
    result = variant_b(pix, source, factor, COVARIANCE).astype(np.float32)
    np.testing.assert_allclose(
        block_mean(result.astype(np.float64), factor),
        source,
        rtol=0,
        atol=FLOAT32_ABSOLUTE_TOLERANCE,
    )


@no_deadline
@given(scenes())
def test_variant_b_on_a_seed_mean_reproduces_the_source(
    scene: tuple[np.ndarray, np.ndarray, int],
) -> None:
    pix, source, factor = scene
    mean, _ = ensemble([pix.astype(np.float32), pix[::-1].astype(np.float32)])
    result = variant_b(mean, source, factor, COVARIANCE)
    np.testing.assert_allclose(
        block_mean(result, factor), source, rtol=0, atol=FLOAT32_ABSOLUTE_TOLERANCE
    )


@no_deadline
@given(st.integers(2, 5), arrays(np.float64, (4, 3), elements=METRES))
def test_kriging_is_coherent(factor: int, coarse: np.ndarray) -> None:
    np.testing.assert_allclose(
        block_mean(krige(coarse, factor, COVARIANCE), factor),
        coarse,
        rtol=0,
        atol=FLOAT32_ABSOLUTE_TOLERANCE,
    )


@no_deadline
@given(st.floats(-100, 100), st.integers(2, 4))
def test_kriging_a_constant_gives_that_constant(value: float, factor: int) -> None:
    result = krige(np.full((3, 3), value), factor, COVARIANCE)
    np.testing.assert_allclose(result, value, rtol=0, atol=1e-9)


def test_kriging_a_region_equals_the_same_pixels_of_the_whole() -> None:
    coarse = np.random.default_rng(0).normal(50, 5, (5, 5))
    whole = krige(coarse, 3, COVARIANCE, radius=2)
    region = krige_region(coarse, 3, COVARIANCE, (slice(1, 3), slice(2, 5)), radius=2)
    np.testing.assert_array_equal(region, whole[3:9, 6:15])


def test_fitted_covariance_is_positive_and_reusable_across_grids() -> None:
    rows, cols = np.mgrid[0:12, 0:12].astype(np.float64)
    smooth = 30 + 4 * np.sin(rows / 4) + 3 * np.cos(cols / 5)
    covariance = fit_point_covariance(smooth, 2)
    assert covariance.sill > 0
    assert covariance.practical_range_pixels > 0
    other = krige(smooth[:4, :4], 2, covariance)
    assert other.shape == (8, 8)
