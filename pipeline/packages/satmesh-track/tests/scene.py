"""Synthetic town and flight for the tracker tests: textured ground, buildings, a distorted lens."""

from functools import cache

import cv2
import numpy as np
from trimesh import Trimesh
from trimesh.creation import box

from satmesh_core import EnuFrame, geodetic_to_ecef
from satmesh_eval.camera import CameraPose, Intrinsics, pose_from_enu
from satmesh_eval.perspective import AreaScene, GroundExtent, SceneLeaf, flat_plane_scene, render
from satmesh_track.lens import Lens

LATITUDE_DEG, LONGITUDE_DEG, ORIGIN_HEIGHT_M = 53.72, -1.27, 40.0
GROUND_HALF_EXTENT_M = 150.0
GROUND_TEXTURE_PX = 2000  # 0.15 m per texel, fine enough for SIFT from a camera 40 m up
BUILDING_SIDE_M = 14.0
BUILDING_TEXTURE_PX = 256
BYTE_MAX = 255.0
WIDTH_PX, HEIGHT_PX = 320, 240
TRUE_LENS = Lens(220.0, -0.12, 0.03, WIDTH_PX, HEIGHT_PX)
WIDE_MARGIN = 1.3  # the ideal image rendered before distortion is this much larger
CAMERA_HEIGHT_M = 40.0
CAMERA_PITCH_DEG = -35.0
MAX_RANGE_M = 400.0


def pinhole() -> Intrinsics:
    """The true lens without its distortion: what the tracker renders references with."""
    f = TRUE_LENS.focal_px
    return Intrinsics(WIDTH_PX, HEIGHT_PX, f, f, WIDTH_PX / 2, HEIGHT_PX / 2, ())


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
def town() -> AreaScene:
    """Ground plus a jittered grid of buildings, so views have relief and recognisable places."""
    half = GROUND_HALF_EXTENT_M
    ground = flat_plane_scene(
        area_frame(),
        0.0,
        blotchy_texture(GROUND_TEXTURE_PX, 1),
        GroundExtent(-half, half, -half, half),
    )
    rng = np.random.default_rng(5)
    leaves = list(ground.leaves)
    for index, (east, north) in enumerate(
        (e, n) for e in range(-135, 136, 45) for n in range(-135, 136, 45)
    ):
        height = float(rng.uniform(8.0, 28.0))
        mesh = box((BUILDING_SIDE_M, BUILDING_SIDE_M, height))
        mesh.apply_translation(
            (east + rng.uniform(-10, 10), north + rng.uniform(-10, 10), height / 2)
        )
        uv = (mesh.vertices[:, :2] - mesh.bounds[0, :2]) / BUILDING_SIDE_M
        texture = blotchy_texture(BUILDING_TEXTURE_PX, 10 + index)
        leaves.append(SceneLeaf(Trimesh(mesh.vertices, mesh.faces, process=False), uv, texture))
    return AreaScene(tuple(leaves), ground.frame)


def ground_height(east_m: float, north_m: float) -> float:
    if abs(east_m) > GROUND_HALF_EXTENT_M or abs(north_m) > GROUND_HALF_EXTENT_M:
        msg = "outside the scene"
        raise ValueError(msg)
    return 0.0


def pose_at(east_m: float, north_m: float, heading_deg: float) -> CameraPose:
    centre = np.array([east_m, north_m, CAMERA_HEIGHT_M])
    return pose_from_enu(area_frame(), centre, heading_deg, CAMERA_PITCH_DEG, 0.0)


def photograph(pose: CameraPose) -> np.ndarray:
    """The scene through `TRUE_LENS`: an ideal wide render resampled to the distorted image."""
    wide_w, wide_h = int(WIDTH_PX * WIDE_MARGIN), int(HEIGHT_PX * WIDE_MARGIN)
    ideal = Intrinsics(
        wide_w, wide_h, TRUE_LENS.focal_px, TRUE_LENS.focal_px, wide_w / 2, wide_h / 2, ()
    )
    wide = render(town(), ideal, pose, MAX_RANGE_M).rgb
    columns, rows = np.meshgrid(np.arange(WIDTH_PX) + 0.5, np.arange(HEIGHT_PX) + 0.5)
    camera_matrix = TRUE_LENS.intrinsics().matrix()
    normalised = cv2.undistortPoints(
        np.stack([columns, rows], -1).reshape(-1, 1, 2),
        camera_matrix,
        np.array([TRUE_LENS.k1, TRUE_LENS.k2, 0, 0, 0.0]),
        criteria=(cv2.TERM_CRITERIA_COUNT + cv2.TERM_CRITERIA_EPS, 100, 1e-12),
    ).reshape(HEIGHT_PX, WIDTH_PX, 2)
    map_x = (normalised[..., 0] * TRUE_LENS.focal_px + wide_w / 2 - 0.5).astype(np.float32)
    map_y = (normalised[..., 1] * TRUE_LENS.focal_px + wide_h / 2 - 0.5).astype(np.float32)
    return np.asarray(cv2.remap(wide, map_x, map_y, cv2.INTER_LINEAR), dtype=np.uint8)
