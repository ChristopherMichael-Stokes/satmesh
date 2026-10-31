import math
import os
from collections.abc import Callable
from functools import cache
from pathlib import Path

import cv2
import numpy as np
import pytest
from trimesh import Trimesh
from trimesh.creation import box

from satmesh_core import EnuFrame, geodetic_to_ecef
from satmesh_eval.camera import (
    CameraPose,
    Intrinsics,
    PoseOffset,
    camera_centre_and_rotation,
    offset_pose,
    pose_from_enu,
)
from satmesh_eval.localise import (
    RECALL_THRESHOLDS,
    Correspondences,
    PoseEstimate,
    localise,
    pose_error,
    solve_pose,
)
from satmesh_eval.matching import Matcher, XFeatLighterGlueMatcher, sift_match
from satmesh_eval.perspective import AreaScene, GroundExtent, SceneLeaf, flat_plane_scene, render
from satmesh_eval.references import PhotoQuery, Renderer, nadir_views, perspective_views

LATITUDE_DEG, LONGITUDE_DEG, ORIGIN_HEIGHT_M = 53.72, -1.27, 40.0
PLANE_HALF_EXTENT_M = 100.0
TEXTURE_SIDE_PX = 2000  # 0.1 m per texel
WIDTH_PX, HEIGHT_PX, FOCAL_PX = 640, 480, 400.0
INTRINSICS = Intrinsics(WIDTH_PX, HEIGHT_PX, FOCAL_PX, FOCAL_PX, WIDTH_PX / 2, HEIGHT_PX / 2, ())
MAX_RANGE_M = 300.0
CAMERA_HEIGHT_M = 25.0
CAMERA_NORTH_M = -20.0
CAMERA_PITCH_DEG = -25.0
BUILDINGS = (  # east, north, height (m)
    (-25.0, 30.0, 25.0),
    (15.0, 40.0, 30.0),
    (-5.0, 60.0, 20.0),
    (35.0, 70.0, 28.0),
    (-40.0, 75.0, 22.0),
)
BUILDING_SIDE_M = 15.0
BUILDING_TEXTURE_PX = 256
GROUND_SAMPLE_M = 0.2
PRIOR_OFFSET = PoseOffset(2.0, -2.0, 0.5, 3.0, 1.0, 0.0)
MODEL_DIR_VARIABLE = "XFEAT_MODEL_DIR"
RELIGHT_GAIN, RELIGHT_GAMMA, BLUR_SIGMA_PX = 0.7, 1.3, 1.5
BYTE_MAX = 255.0


def area_frame() -> EnuFrame:
    ecef = np.array(geodetic_to_ecef().transform(LONGITUDE_DEG, LATITUDE_DEG, ORIGIN_HEIGHT_M))
    return EnuFrame.at(ecef, LONGITUDE_DEG, LATITUDE_DEG)


@cache
def blotchy_texture(side_px: int, seed: int) -> np.ndarray:
    """Noise smoothed at four scales, so corners exist at every scale a matcher looks at."""
    rng = np.random.default_rng(seed)
    channels = []
    for _ in range(3):
        field = np.zeros((side_px, side_px))
        for sigma_px in (side_px / 300, side_px / 100, side_px / 30, side_px / 10):
            noise = rng.standard_normal((side_px, side_px)).astype(np.float32)
            smooth = cv2.GaussianBlur(noise, (0, 0), sigma_px)
            field += smooth / smooth.std()
        channels.append(field)
    stacked = np.stack(channels, axis=-1)
    scaled = (stacked - stacked.min()) / (stacked.max() - stacked.min())
    return np.rint(BYTE_MAX * scaled).astype(np.uint8)


@cache
def ground_only() -> AreaScene:
    half = PLANE_HALF_EXTENT_M
    texture = blotchy_texture(TEXTURE_SIDE_PX, 1)
    return flat_plane_scene(area_frame(), 0.0, texture, GroundExtent(-half, half, -half, half))


@cache
def with_buildings() -> AreaScene:
    ground = ground_only()
    leaves = list(ground.leaves)
    for index, (east, north, height) in enumerate(BUILDINGS):
        mesh = box((BUILDING_SIDE_M, BUILDING_SIDE_M, height))
        mesh.apply_translation((east, north, height / 2))
        uv = (mesh.vertices[:, :2] - mesh.bounds[0, :2]) / BUILDING_SIDE_M
        texture = blotchy_texture(BUILDING_TEXTURE_PX, 10 + index)
        leaves.append(SceneLeaf(Trimesh(mesh.vertices, mesh.faces, process=False), uv, texture))
    return AreaScene(tuple(leaves), ground.frame)


def truth_pose() -> CameraPose:
    centre = np.array([0.0, CAMERA_NORTH_M, CAMERA_HEIGHT_M])
    return pose_from_enu(area_frame(), centre, 0.0, CAMERA_PITCH_DEG, 0.0)


def embree_renderer(scene: AreaScene) -> Renderer:
    return lambda intrinsics, pose, max_range_m: render(scene, intrinsics, pose, max_range_m)


def relit_and_blurred(photo: np.ndarray) -> np.ndarray:
    """Gain and gamma, then a Gaussian blur: a stand-in for the domain gap."""
    toned = BYTE_MAX * (RELIGHT_GAIN * (photo / BYTE_MAX)) ** RELIGHT_GAMMA
    return cv2.GaussianBlur(np.rint(toned).astype(np.uint8), (0, 0), BLUR_SIGMA_PX)


def unchanged(photo: np.ndarray) -> np.ndarray:
    return photo


def surface_localisation_error(
    matcher: Matcher, photo_transform: Callable[[np.ndarray], np.ndarray]
) -> tuple[float, float]:
    scene = with_buildings()
    truth = truth_pose()
    photo = photo_transform(render(scene, INTRINSICS, truth, MAX_RANGE_M).rgb)
    prior = offset_pose(truth, PRIOR_OFFSET)
    query = PhotoQuery(photo, INTRINSICS, prior, scene.frame)
    views = perspective_views(query, embree_renderer(scene), MAX_RANGE_M)
    result = localise(views, INTRINSICS, matcher)
    assert result.estimate is not None
    centre, camera_to_enu = camera_centre_and_rotation(truth, scene.frame)
    error = pose_error(result.estimate, centre, camera_to_enu)
    return error.translation_m, error.rotation_deg


def test_offset_pose_moves_the_centre_by_the_offset_and_adds_the_angles() -> None:
    area = area_frame()
    truth = truth_pose()
    moved = offset_pose(truth, PoseOffset(3.0, -4.0, 12.0, 2.0, -1.0, 0.5))

    centre, _ = camera_centre_and_rotation(truth, area)
    moved_centre, _ = camera_centre_and_rotation(moved, area)

    # 3-4-12 is a 13 m vector; curvature over 13 m is far below a millimetre
    assert np.linalg.norm(moved_centre - centre) == pytest.approx(13.0, abs=1e-3)
    assert (moved.heading_deg, moved.pitch_deg, moved.roll_deg) == pytest.approx(
        (2.0, CAMERA_PITCH_DEG - 1.0, 0.5)
    )


def test_pose_error_of_a_known_turn_and_shift() -> None:
    turn = math.radians(3.0)
    rotation = np.array(
        [
            [math.cos(turn), -math.sin(turn), 0.0],
            [math.sin(turn), math.cos(turn), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    estimate = PoseEstimate(np.array([0.3, 0.4, 0.0]), rotation, np.ones(1, dtype=bool))

    error = pose_error(estimate, np.zeros(3), np.eye(3))

    assert error.translation_m == pytest.approx(0.5)
    assert error.rotation_deg == pytest.approx(3.0)


def test_solve_pose_recovers_a_pose_from_projected_points_with_outliers() -> None:
    rng = np.random.default_rng(0)
    yaw = math.radians(20.0)
    # camera axes (right, down, forward) in ENU for a camera looking along a horizontal heading
    forward = np.array([math.sin(yaw), math.cos(yaw), 0.0])
    right = np.array([math.cos(yaw), -math.sin(yaw), 0.0])
    camera_to_enu = np.column_stack([right, [0.0, 0.0, -1.0], forward])
    centre = np.array([5.0, -3.0, 25.0])
    points = rng.uniform(-40.0, 40.0, (300, 3)) + forward * 60.0 + centre
    in_camera = (points - centre) @ camera_to_enu
    homogeneous = in_camera @ INTRINSICS.matrix().T
    pixels = homogeneous[:, :2] / homogeneous[:, 2:3] + rng.normal(0.0, 0.3, (300, 2))
    outliers = rng.choice(300, 90, replace=False)
    pixels[outliers] = rng.uniform(0.0, [WIDTH_PX, HEIGHT_PX], (90, 2))

    estimate = solve_pose(Correspondences(pixels, points), INTRINSICS)

    assert estimate is not None
    assert pose_error(estimate, centre, camera_to_enu).within(0.05, 0.1)
    assert estimate.inlier_mask[outliers].sum() <= len(outliers) // 10


def test_the_nadir_warp_of_a_flat_scene_photo_is_the_flat_render_from_above() -> None:
    scene = ground_only()
    truth = truth_pose()
    photo = render(scene, INTRINSICS, truth, MAX_RANGE_M).rgb
    query = PhotoQuery(photo, INTRINSICS, truth, scene.frame)
    views = nadir_views(query, embree_renderer(scene), 0.0, GROUND_SAMPLE_M, MAX_RANGE_M)

    warped = views.photo_view.astype(float)
    above = views.reference.render.rgb.astype(float)
    covered = (views.photo_view.sum(axis=2) > 0).astype(np.uint8)
    valid = cv2.erode(covered, np.ones((9, 9), np.uint8)).astype(bool)
    valid &= views.reference.render.hit_mask

    # the photo was itself sampled from the ortho, so the warp differs from the nadir render by
    # resampling only; a shifted or mirrored warp is off by the texture's own contrast
    assert valid.sum() > 10_000
    assert np.median(np.abs(warped[valid] - above[valid])) < 12.0


def test_sift_recovers_the_pose_from_a_surface_render() -> None:
    translation_m, rotation_deg = surface_localisation_error(sift_match, unchanged)

    assert translation_m <= RECALL_THRESHOLDS[0][0]
    assert rotation_deg <= RECALL_THRESHOLDS[0][1]


@pytest.mark.skipif(MODEL_DIR_VARIABLE not in os.environ, reason=f"{MODEL_DIR_VARIABLE} not set")
def test_xfeat_with_lighterglue_recovers_the_pose_when_the_photo_is_relit_and_blurred() -> None:
    model_dir = Path(os.environ[MODEL_DIR_VARIABLE])
    matcher = XFeatLighterGlueMatcher(
        model_dir / "xfeat_1280x960_k2048_b1.onnx", model_dir / "lighterglue_k2048_b1.onnx"
    )

    translation_m, rotation_deg = surface_localisation_error(matcher, relit_and_blurred)

    assert translation_m <= RECALL_THRESHOLDS[1][0]
    assert rotation_deg <= RECALL_THRESHOLDS[1][1]
