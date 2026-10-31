import numpy as np
import pytest

from satmesh_eval.camera import Intrinsics
from satmesh_eval.projection import (
    boxes_in_frustum,
    boxes_within_range,
    frustum_planes,
    projection_matrix,
    view_matrix,
)

WIDTH, HEIGHT = 640, 480
INTRINSICS = Intrinsics(WIDTH, HEIGHT, 500.0, 520.0, 330.0, 250.0, ())
NEAR_M, FAR_M = 0.5, 400.0


def clip_from_camera(point: np.ndarray) -> np.ndarray:
    return projection_matrix(INTRINSICS, NEAR_M, FAR_M) @ np.append(point, 1.0)


def test_projected_point_lands_on_the_pinhole_pixel() -> None:
    x, y, z = 3.0, -2.0, 25.0
    clip = clip_from_camera(np.array([x, y, z]))

    ndc = clip[:3] / clip[3]

    column = INTRINSICS.focal_x_px * x / z + INTRINSICS.principal_x_px
    row = INTRINSICS.focal_y_px * y / z + INTRINSICS.principal_y_px
    assert (ndc[0] + 1.0) / 2.0 * WIDTH == pytest.approx(column)
    assert (1.0 - ndc[1]) / 2.0 * HEIGHT == pytest.approx(row)


def test_depth_is_zero_at_the_near_plane_and_one_at_the_far_plane() -> None:
    near = clip_from_camera(np.array([0.0, 0.0, NEAR_M]))
    far = clip_from_camera(np.array([0.0, 0.0, FAR_M]))

    assert near[2] / near[3] == pytest.approx(0.0, abs=1e-12)
    assert far[2] / far[3] == pytest.approx(1.0)


def test_view_matrix_takes_the_camera_centre_to_the_origin_and_forward_to_plus_z() -> None:
    centre = np.array([10.0, 20.0, 30.0])
    camera_to_enu = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]])  # looks north

    view = view_matrix(centre, camera_to_enu)

    assert (view @ np.append(centre, 1.0))[:3] == pytest.approx(0.0)
    ahead = centre + 7.0 * camera_to_enu[:, 2]
    assert (view @ np.append(ahead, 1.0))[:3] == pytest.approx([0.0, 0.0, 7.0])


def looking_north_planes() -> tuple[np.ndarray, np.ndarray]:
    centre = np.zeros(3)
    camera_to_enu = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]])
    clip = projection_matrix(INTRINSICS, NEAR_M, FAR_M) @ view_matrix(centre, camera_to_enu)
    return frustum_planes(clip), centre


def box_around(centre: list[float], half: float = 0.1) -> tuple[list[float], list[float]]:
    return [c - half for c in centre], [c + half for c in centre]


@pytest.mark.parametrize(
    ("centre", "expected"),
    [
        ([0.0, 50.0, 0.0], [True]),  # straight ahead
        ([0.0, -50.0, 0.0], [False]),  # behind
        ([500.0, 50.0, 0.0], [False]),  # far to the east of a 50 m view
        ([0.0, 500.0, 0.0], [False]),  # beyond the far plane
        ([0.0, 50.0, 400.0], [False]),  # far above
        ([0.0, 0.3, 0.0], [False]),  # in front of the near plane
    ],
)
def test_box_visibility_follows_the_view_volume(centre: list[float], expected: list[bool]) -> None:
    planes, _ = looking_north_planes()
    low, high = box_around(centre)

    mask = boxes_in_frustum(planes, np.array([low]), np.array([high]))

    assert mask.tolist() == expected


def test_a_large_box_straddling_the_volume_is_kept() -> None:
    planes, _ = looking_north_planes()
    low, high = box_around([300.0, 50.0, 0.0], half=290.0)

    assert boxes_in_frustum(planes, np.array([low]), np.array([high])).tolist() == [True]


def test_range_test_uses_the_nearest_point_of_the_box() -> None:
    lower = np.array([[10.0, 0.0, 0.0], [10.0, 0.0, 0.0]])
    upper = np.array([[20.0, 5.0, 5.0], [20.0, 5.0, 5.0]])

    near_enough = boxes_within_range(np.array([0.0, 0.0, 0.0]), 10.0, lower, upper)
    too_far = boxes_within_range(np.array([0.0, 0.0, 0.0]), 9.99, lower, upper)

    assert near_enough.tolist() == [True, True]
    assert too_far.tolist() == [False, False]
