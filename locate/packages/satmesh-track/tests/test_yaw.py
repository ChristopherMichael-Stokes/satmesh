import math

import numpy as np
import pytest

from satmesh_track.yaw import (
    chained_offsets_deg,
    focal_for_field_of_view,
    heading_change_deg,
    pair_heading_change_deg,
    rotation_from_essential,
    rotation_from_homography,
)

WIDTH, HEIGHT, FOCAL = 1280, 720, 1000.0
CAMERA = np.array([[FOCAL, 0.0, WIDTH / 2], [0.0, FOCAL, HEIGHT / 2], [0.0, 0.0, 1.0]])
PITCH_DEG = -35.0
POINTS = 300
# exact correspondences: RANSAC keeps all of them and the error is the solver's round-off
EXACT_TOLERANCE_DEG = 0.05


def camera_to_world(heading_deg: float, pitch_deg: float) -> np.ndarray:
    """Columns right, down, forward in east-north-up: heading clockwise from north, pitch up."""
    h, p = math.radians(heading_deg), math.radians(pitch_deg)
    forward = np.array([math.sin(h) * math.cos(p), math.cos(h) * math.cos(p), math.sin(p)])
    right = np.array([math.cos(h), -math.sin(h), 0.0])
    return np.column_stack([right, np.cross(forward, right), forward])


def project(points_world: np.ndarray, centre: np.ndarray, rotation: np.ndarray) -> np.ndarray:
    in_camera = (points_world - centre) @ rotation
    return (in_camera[:, :2] / in_camera[:, 2:]) * FOCAL + np.array([WIDTH / 2, HEIGHT / 2])


def correspondences(
    heading_change: float, translation: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Pixels of scene points 100 to 400 m in front of camera a, seen by a and by b.

    Camera b is camera a turned by `heading_change` about the vertical and moved by
    `translation` (east, north, up metres).
    """
    rng = np.random.default_rng(3)
    pixels = rng.uniform([100.0, 100.0], [WIDTH - 100.0, HEIGHT - 100.0], (POINTS, 2))
    depth = rng.uniform(100.0, 400.0, POINTS)
    rays = np.column_stack([(pixels - [WIDTH / 2, HEIGHT / 2]) / FOCAL, np.ones(POINTS)])
    rotation_a = camera_to_world(10.0, PITCH_DEG)
    world = (rays * depth[:, None]) @ rotation_a.T
    rotation_b = camera_to_world(10.0 + heading_change, PITCH_DEG)
    return project(world, np.zeros(3), rotation_a), project(world, translation, rotation_b)


def test_the_focal_length_spans_the_field_of_view() -> None:
    assert focal_for_field_of_view(1280, 90.0) == pytest.approx(640.0)


@pytest.mark.parametrize("heading_change", [-20.0, -4.0, 7.0, 25.0])
def test_a_pure_yaw_is_recovered_from_the_rotation_only_homography(heading_change: float) -> None:
    points_a, points_b = correspondences(heading_change, np.zeros(3))

    rotation = rotation_from_homography(points_a, points_b, CAMERA)

    assert rotation is not None
    assert heading_change_deg(rotation, PITCH_DEG) == pytest.approx(
        heading_change, abs=EXACT_TOLERANCE_DEG
    )


@pytest.mark.parametrize("heading_change", [-15.0, 6.0, 30.0])
def test_a_yaw_with_translation_is_recovered_from_the_essential_matrix(
    heading_change: float,
) -> None:
    points_a, points_b = correspondences(heading_change, np.array([12.0, 20.0, 3.0]))

    rotation = rotation_from_essential(points_a, points_b, CAMERA)

    assert rotation is not None
    assert heading_change_deg(rotation, PITCH_DEG) == pytest.approx(
        heading_change, abs=EXACT_TOLERANCE_DEG
    )


def test_agree_takes_the_essential_estimate_when_the_homography_is_close() -> None:
    # 5 m forward against 100 to 400 m depth: the homography is near, not exact
    points_a, points_b = correspondences(9.0, np.array([0.0, 5.0, 0.0]))

    estimate = pair_heading_change_deg(
        points_a, points_b, CAMERA, pitch_deg=PITCH_DEG, method="agree", agreement_deg=5.0
    )

    assert estimate == pytest.approx(9.0, abs=EXACT_TOLERANCE_DEG)


def test_agree_gives_nothing_when_the_estimates_differ() -> None:
    # 60 m sideways against 100 to 400 m depth: no single homography explains the parallax
    points_a, points_b = correspondences(9.0, np.array([60.0, 0.0, 0.0]))

    homography = pair_heading_change_deg(
        points_a, points_b, CAMERA, pitch_deg=PITCH_DEG, method="homography", agreement_deg=5.0
    )
    agreed = pair_heading_change_deg(
        points_a, points_b, CAMERA, pitch_deg=PITCH_DEG, method="agree", agreement_deg=5.0
    )

    assert homography is not None
    assert abs(homography - 9.0) > 5.0
    assert agreed is None


def test_too_few_matches_give_no_estimate() -> None:
    points_a, points_b = correspondences(5.0, np.array([5.0, 0.0, 0.0]))

    estimate = pair_heading_change_deg(
        points_a[:10],
        points_b[:10],
        CAMERA,
        pitch_deg=PITCH_DEG,
        method="essential",
        agreement_deg=5.0,
    )

    assert estimate is None


def test_offsets_chain_consecutive_changes_from_the_first_frame() -> None:
    assert chained_offsets_deg([5.0, -2.0, 7.5]) == (0.0, 5.0, 3.0, 10.5)
    assert chained_offsets_deg([]) == (0.0,)
    assert chained_offsets_deg([5.0, None, 7.5]) is None
