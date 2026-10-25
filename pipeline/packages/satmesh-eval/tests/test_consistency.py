import numpy as np
import pytest
from scipy.ndimage import gaussian_filter, shift

from satmesh_eval.consistency import consistency

SCALE = 4
SIZE = 64


def _source() -> np.ndarray:
    rng = np.random.default_rng(3)
    smooth = gaussian_filter(rng.uniform(0, 255, (SIZE, SIZE, 3)), (1, 1, 0))
    return 40 + 0.6 * smooth


def _upsampled(image: np.ndarray) -> np.ndarray:
    return np.repeat(np.repeat(image, SCALE, axis=0), SCALE, axis=1)


def test_a_replicated_source_is_perfectly_consistent() -> None:
    result = consistency(_upsampled(_source()), _source())
    assert result.mean_abs_difference == pytest.approx(0.0, abs=1e-4)
    assert result.mean_spectral_angle_deg == pytest.approx(0.0, abs=0.05)
    assert abs(result.shift_east_px) < 0.02
    assert abs(result.shift_north_px) < 0.02


def test_detail_that_averages_to_zero_leaves_it_consistent() -> None:
    # +-d checkerboard at the enhanced grid's own pixel scale: block means are untouched
    pattern = np.indices((SIZE * SCALE,) * 2).sum(axis=0) % 2 * 2 - 1
    enhanced = _upsampled(_source()) + 10.0 * pattern[:, :, None]
    assert consistency(enhanced, _source()).mean_abs_difference == pytest.approx(0.0, abs=1e-4)


def test_a_constant_brightening_shows_as_that_difference() -> None:
    enhanced = _upsampled(_source()) + 6.0
    assert consistency(enhanced, _source()).mean_abs_difference == pytest.approx(6.0, abs=1e-4)


def test_a_known_shift_is_recovered_east_and_north() -> None:
    # the enhanced image is moved 8 enhanced pixels (2 source pixels) east and 4 (1 source pixel)
    # north: rows run south, so north is a negative row shift
    moved = shift(_upsampled(_source()), (-4, 8, 0), order=0, mode="nearest")
    result = consistency(moved, _source())
    assert result.shift_east_px == pytest.approx(2.0, abs=0.1)
    assert result.shift_north_px == pytest.approx(1.0, abs=0.1)


def test_a_size_that_is_not_a_multiple_raises() -> None:
    with pytest.raises(ValueError, match="integer multiple"):
        consistency(np.zeros((SIZE * SCALE + 1, SIZE * SCALE, 3)), _source())
