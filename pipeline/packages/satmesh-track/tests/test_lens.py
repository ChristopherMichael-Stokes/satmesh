import cv2
import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from satmesh_track.lens import (
    CameraPoseEnu,
    FrameObservations,
    Lens,
    LensConfig,
    LensFit,
    fit_lens,
)

WIDTH_PX, HEIGHT_PX = 1280, 960
TRUE_LENS = Lens(1000.0, -0.15, 0.04, WIDTH_PX, HEIGHT_PX)
INITIAL_LENS = Lens(1.08 * TRUE_LENS.focal_px, 0.0, 0.0, WIDTH_PX, HEIGHT_PX)
FRAME_COUNT = 16
STEP_M = 12.0
HEIGHT_M = 60.0
LOOK_AHEAD_M = 90.0  # 34 degrees below the horizon
POINTS_PER_FRAME = 150
POOL_SIZE = 4000
SCENE_HALF_EXTENT_M = 200.0
RELIEF_M = 25.0
POSE_PERTURBATION_M, POSE_PERTURBATION_DEG = 0.5, 0.5
CLEAN_RELATIVE_TOLERANCE = 1e-3  # Levenberg-Marquardt stops at a relative error change of 1e-5
SIGMAS_ALLOWED = 4.0


def look_at(centre: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Camera-to-ENU rotation with columns right, down, forward, z up."""
    forward = (target - centre) / np.linalg.norm(target - centre)
    right = np.cross(forward, [0.0, 0.0, 1.0])
    right /= np.linalg.norm(right)
    return np.column_stack([right, np.cross(forward, right), forward])


def project(lens: Lens, pose: CameraPoseEnu, points: np.ndarray) -> np.ndarray:
    """Pixels from OpenCV's own projection with the lens' distortion, independent of the graph."""
    world_to_camera = pose.camera_to_enu.T
    rvec, _ = cv2.Rodrigues(world_to_camera)
    camera_matrix = np.array(
        [[lens.focal_px, 0, WIDTH_PX / 2], [0, lens.focal_px, HEIGHT_PX / 2], [0, 0, 1.0]]
    )
    pixels, _ = cv2.projectPoints(
        points,
        rvec,
        -world_to_camera @ pose.centre_enu,
        camera_matrix,
        np.array([lens.k1, lens.k2, 0, 0, 0.0]),
    )
    return pixels.reshape(-1, 2)


def scene_points(rng: np.random.Generator, *, flat: bool) -> np.ndarray:
    xy = rng.uniform(-SCENE_HALF_EXTENT_M, SCENE_HALF_EXTENT_M, (POOL_SIZE, 2))
    relief = np.zeros(POOL_SIZE) if flat else RELIEF_M * rng.random(POOL_SIZE)
    return np.column_stack([xy, relief])


def true_poses(*, nadir: bool) -> list[CameraPoseEnu]:
    poses = []
    for index in range(FRAME_COUNT):
        centre = np.array([-100.0 + STEP_M * index, -150.0, HEIGHT_M])
        target = (
            np.array([centre[0] + 1e-3, centre[1], 0.0])
            if nadir
            else np.array([centre[0], centre[1] + LOOK_AHEAD_M, 0.0])
        )
        poses.append(CameraPoseEnu(centre, look_at(centre, target)))
    return poses


def observe(
    poses: list[CameraPoseEnu], pool: np.ndarray, rng: np.random.Generator, pixel_noise_px: float
) -> list[FrameObservations]:
    frames = []
    for index, pose in enumerate(poses):
        pixels = project(TRUE_LENS, pose, pool)
        depth = (pool - pose.centre_enu) @ pose.camera_to_enu[:, 2]
        visible = (
            (depth > 1.0)
            & (pixels[:, 0] > 0)
            & (pixels[:, 0] < WIDTH_PX)
            & (pixels[:, 1] > 0)
            & (pixels[:, 1] < HEIGHT_PX)
        )
        chosen = np.flatnonzero(visible)[:POINTS_PER_FRAME]
        noisy = pixels[chosen] + rng.normal(0.0, pixel_noise_px, (len(chosen), 2))
        frames.append(FrameObservations(index, perturbed(pose, rng), noisy, pool[chosen]))
    return frames


def perturbed(pose: CameraPoseEnu, rng: np.random.Generator) -> CameraPoseEnu:
    turn = Rotation.from_rotvec(np.radians(POSE_PERTURBATION_DEG) * rng.normal(size=3))
    return CameraPoseEnu(
        pose.centre_enu + POSE_PERTURBATION_M * rng.normal(size=3),
        turn.as_matrix() @ pose.camera_to_enu,
    )


def fit(
    *,
    pixel_noise_px: float,
    nadir: bool = False,
    flat: bool = False,
    config: LensConfig | None = None,
) -> tuple[LensFit, list[FrameObservations], list[CameraPoseEnu]]:
    rng = np.random.default_rng(3)
    poses = true_poses(nadir=nadir)
    frames = observe(poses, scene_points(rng, flat=flat), rng, pixel_noise_px)
    config = config or LensConfig(pixel_sigma_px=max(pixel_noise_px, 0.5), mesh_error_m=0.1)
    return fit_lens(frames, INITIAL_LENS, config), frames, poses


def test_noise_free_matches_give_back_the_lens_and_the_poses() -> None:
    result, _, poses = fit(pixel_noise_px=0.0)

    lens = result.estimate.lens
    assert lens.focal_px == pytest.approx(TRUE_LENS.focal_px, rel=CLEAN_RELATIVE_TOLERANCE)
    assert lens.k1 == pytest.approx(TRUE_LENS.k1, abs=CLEAN_RELATIVE_TOLERANCE)
    assert lens.k2 == pytest.approx(TRUE_LENS.k2, abs=CLEAN_RELATIVE_TOLERANCE)
    assert result.rejected == ()
    for index, pose in enumerate(poses):
        assert result.poses[index].centre_enu == pytest.approx(pose.centre_enu, abs=0.05)


def test_the_error_with_pixel_noise_is_within_the_reported_uncertainty() -> None:
    result, _, _ = fit(pixel_noise_px=1.0)

    estimate = result.estimate
    sigma = np.sqrt(np.diag(estimate.covariance))
    truth = np.array([TRUE_LENS.focal_px, TRUE_LENS.k1, TRUE_LENS.k2])
    fitted = np.array([estimate.lens.focal_px, estimate.lens.k1, estimate.lens.k2])
    assert np.all(np.abs(fitted - truth) <= SIGMAS_ALLOWED * sigma)
    assert estimate.focal_sigma_px / truth[0] < 0.01  # oblique views determine the focal length


def test_a_frame_of_bad_matches_is_rejected_and_the_lens_is_unharmed() -> None:
    rng = np.random.default_rng(3)
    poses = true_poses(nadir=False)
    frames = observe(poses, scene_points(rng, flat=False), rng, 0.5)
    spoiled = frames[7]
    pixels = spoiled.pixels.copy()
    bad = rng.choice(len(pixels), int(0.7 * len(pixels)), replace=False)
    pixels[bad] = rng.uniform([0, 0], [WIDTH_PX, HEIGHT_PX], (len(bad), 2))
    frames[7] = FrameObservations(7, spoiled.pose, pixels, spoiled.points_enu)

    result = fit_lens(frames, INITIAL_LENS, LensConfig(pixel_sigma_px=0.5, mesh_error_m=0.1))

    assert result.rejected == (7,)
    sigma = result.estimate.focal_sigma_px
    assert abs(result.estimate.lens.focal_px - TRUE_LENS.focal_px) <= SIGMAS_ALLOWED * sigma


def test_a_frame_in_the_wrong_place_is_rejected_by_its_position_jump() -> None:
    rng = np.random.default_rng(3)
    poses = true_poses(nadir=False)
    frames = observe(poses, scene_points(rng, flat=False), rng, 0.5)
    moved = frames[8]
    shift = np.array([15.0, 0.0, 0.0])
    frames[8] = FrameObservations(
        8,
        CameraPoseEnu(moved.pose.centre_enu + shift, moved.pose.camera_to_enu),
        moved.pixels,
        moved.points_enu + shift,
    )

    result = fit_lens(frames, INITIAL_LENS, LensConfig(pixel_sigma_px=0.5, mesh_error_m=0.1))

    assert 8 in result.rejected
    assert len(result.rejected) <= 2


def test_straight_down_views_of_flat_ground_leave_the_focal_length_undetermined() -> None:
    oblique, _, _ = fit(pixel_noise_px=1.0)
    nadir, _, _ = fit(pixel_noise_px=1.0, nadir=True, flat=True)

    # a straight-down camera over a plane cannot tell focal length from height (photo-only P0b)
    assert nadir.estimate.focal_sigma_px > 3 * oblique.estimate.focal_sigma_px
