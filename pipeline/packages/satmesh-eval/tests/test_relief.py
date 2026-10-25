import numpy as np
import pytest

from satmesh_eval.offset import ShiftField
from satmesh_eval.relief import raised_fraction_by_window, split_by_relief


def test_raised_share_and_mean_height_per_window() -> None:
    ground = np.zeros((8, 8))
    surface = ground.copy()
    surface[:4, :4] = 5.0  # one 4 x 4 block of raised pixels fills the first 4 px window
    fraction, height = raised_fraction_by_window(
        surface, ground, pixel_m=1.0, window_m=4.0, step_m=4.0
    )
    assert fraction.shape == (2, 2)
    np.testing.assert_allclose(fraction, [[1.0, 0.0], [0.0, 0.0]])
    np.testing.assert_allclose(height, [[5.0, 0.0], [0.0, 0.0]])


def test_split_separates_leaning_objects_from_open_ground() -> None:
    fraction = np.array([[0.0, 0.0, 0.5], [0.0, 0.9, 0.5]])
    height = np.array([[0.0, 0.1, 6.0], [0.2, 9.0, 7.0]])
    north = np.array([[1.9, 2.0, 3.2], [2.1, 3.4, 3.3]])
    field = ShiftField(np.zeros_like(north), north, np.ones_like(north))
    split = split_by_relief(field, fraction, height)
    assert split.open_ground is not None
    assert split.objects is not None
    assert split.open_ground.north_m == pytest.approx(2.0)
    assert split.objects.north_m == pytest.approx(3.3)
    assert split.north_against_height_rho == pytest.approx(1.0)


def test_a_class_with_no_reliable_window_is_none() -> None:
    fraction = np.zeros((2, 2))
    heights = np.arange(4.0).reshape(2, 2)
    field = ShiftField(np.ones((2, 2)), heights, np.ones((2, 2)))
    assert split_by_relief(field, fraction, heights).objects is None


def test_mismatched_grids_raise() -> None:
    field = ShiftField(np.ones((2, 2)), np.ones((2, 2)), np.ones((2, 2)))
    with pytest.raises(ValueError, match="window grids differ"):
        split_by_relief(field, np.zeros((3, 3)), np.zeros((3, 3)))
