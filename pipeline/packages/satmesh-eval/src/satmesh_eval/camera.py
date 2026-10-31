"""Perspective camera model: intrinsics with radial distortion, WGS 84 pose, per-pixel rays.

Camera axes follow OpenCV: x right, y down, z forward (the optical axis). Pixel coordinates are
continuous with the centre of pixel (column c, row r) at (c + 0.5, r + 0.5), so the image spans
[0, width_px] x [0, height_px].
"""

import math
from dataclasses import dataclass

import cv2
import numpy as np

from satmesh_core import EnuFrame, ecef_to_geodetic, geodetic_to_ecef

UNDISTORT_MAX_ITERATIONS = 100
UNDISTORT_TOLERANCE = 1e-12  # normalised image units; far below the 0.01 px the tests resolve
UNDISTORT_CRITERIA = (
    cv2.TERM_CRITERIA_COUNT + cv2.TERM_CRITERIA_EPS,
    UNDISTORT_MAX_ITERATIONS,
    UNDISTORT_TOLERANCE,
)


@dataclass(frozen=True)
class Intrinsics:
    """Pinhole intrinsics in pixels with OpenCV radial distortion.

    `radial_distortion` is (k1, k2) or (k1, k2, k3) of the OpenCV model
    x_d = x (1 + k1 r^2 + k2 r^4 + k3 r^6) on normalised coordinates, r^2 = x^2 + y^2; empty means
    no distortion.
    """

    width_px: int
    height_px: int
    focal_x_px: float
    focal_y_px: float
    principal_x_px: float
    principal_y_px: float
    radial_distortion: tuple[float, ...]

    def matrix(self) -> np.ndarray:
        """Return the 3 x 3 camera matrix K."""
        return np.array(
            [
                [self.focal_x_px, 0.0, self.principal_x_px],
                [0.0, self.focal_y_px, self.principal_y_px],
                [0.0, 0.0, 1.0],
            ]
        )


@dataclass(frozen=True)
class CameraPose:
    """Camera position (WGS 84) and attitude in the local east-north-up frame at that position.

    `heading_deg` runs clockwise from north, `pitch_deg` is positive upward, `roll_deg` is
    positive clockwise about the forward axis seen from behind the camera (the right-hand side of
    the image tips down).
    """

    latitude_deg: float
    longitude_deg: float
    ellipsoidal_height_m: float
    heading_deg: float
    pitch_deg: float
    roll_deg: float


def camera_centre_and_rotation(pose: CameraPose, area: EnuFrame) -> tuple[np.ndarray, np.ndarray]:
    """Return the camera centre in `area` ENU metres and the 3 x 3 camera-to-area-ENU rotation.

    The rotation's columns are the camera axes (right, down, forward) in area ENU (x east,
    y north, z up). At zero roll, right is horizontal, forward is
    (sin h cos p, cos h cos p, sin p) for heading h and pitch p, and down = forward x right.
    Roll r then turns right and down about forward: right' = right cos r + down sin r,
    down' = down cos r - right sin r. The attitude is defined in the ENU frame at
    the camera, which differs from the area frame by Earth curvature (about 0.01 degrees per km);
    the rotation is carried through ECEF.
    """
    ecef = np.array(
        geodetic_to_ecef().transform(
            pose.longitude_deg, pose.latitude_deg, pose.ellipsoidal_height_m
        )
    )
    local = EnuFrame.at(ecef, pose.longitude_deg, pose.latitude_deg)
    camera_to_local = _local_attitude(pose.heading_deg, pose.pitch_deg, pose.roll_deg)
    camera_to_area = area.east_north_up @ local.east_north_up.T @ camera_to_local
    return area.to_enu(ecef[None, :])[0], camera_to_area


def pose_from_enu(
    area: EnuFrame, centre_enu: np.ndarray, heading_deg: float, pitch_deg: float, roll_deg: float
) -> CameraPose:
    """Pose whose centre is the `area` ENU point `centre_enu`, with the given attitude angles."""
    ecef = area.origin_ecef + area.east_north_up.T @ centre_enu
    longitude, latitude, height = ecef_to_geodetic().transform(*ecef)
    return CameraPose(latitude, longitude, height, heading_deg, pitch_deg, roll_deg)


@dataclass(frozen=True)
class PoseOffset:
    """A displacement in the camera's local ENU (metres) and attitude angle increments (degrees)."""

    east_m: float
    north_m: float
    up_m: float
    heading_deg: float
    pitch_deg: float
    roll_deg: float


def offset_pose(pose: CameraPose, offset: PoseOffset) -> CameraPose:
    """`pose` moved by `offset`: the displacement in its own local ENU, the angles added."""
    ecef = np.array(
        geodetic_to_ecef().transform(
            pose.longitude_deg, pose.latitude_deg, pose.ellipsoidal_height_m
        )
    )
    local = EnuFrame.at(ecef, pose.longitude_deg, pose.latitude_deg)
    displacement = np.array([offset.east_m, offset.north_m, offset.up_m])
    moved = ecef + local.east_north_up.T @ displacement
    longitude, latitude, height = ecef_to_geodetic().transform(*moved)
    return CameraPose(
        latitude,
        longitude,
        height,
        pose.heading_deg + offset.heading_deg,
        pose.pitch_deg + offset.pitch_deg,
        pose.roll_deg + offset.roll_deg,
    )


def pixel_rays(
    intrinsics: Intrinsics, camera_to_enu: np.ndarray, rows: range | None = None
) -> np.ndarray:
    """Unit ray directions in ENU through pixel centres, shape (len(rows), width_px, 3).

    `rows` selects image rows (default all) so callers can render in chunks. Distortion is removed
    with `cv2.undistortPoints`.
    """
    rows = range(intrinsics.height_px) if rows is None else rows
    columns = np.arange(intrinsics.width_px) + 0.5
    pixels = np.stack(np.meshgrid(columns, np.asarray(rows) + 0.5), axis=-1).reshape(-1, 1, 2)
    distortion = _opencv_coefficients(intrinsics.radial_distortion)
    normalised = cv2.undistortPoints(
        pixels, intrinsics.matrix(), distortion, criteria=UNDISTORT_CRITERIA
    ).reshape(-1, 2)
    in_camera = np.column_stack([normalised, np.ones(len(normalised))])
    in_camera /= np.linalg.norm(in_camera, axis=1, keepdims=True)
    return (in_camera @ camera_to_enu.T).reshape(len(rows), intrinsics.width_px, 3)


def _local_attitude(heading_deg: float, pitch_deg: float, roll_deg: float) -> np.ndarray:
    """Camera-to-ENU rotation (columns right, down, forward) in the camera's own ENU frame."""
    heading, pitch, roll = (math.radians(a) for a in (heading_deg, pitch_deg, roll_deg))
    forward = np.array(
        [math.sin(heading) * math.cos(pitch), math.cos(heading) * math.cos(pitch), math.sin(pitch)]
    )
    right = np.array([math.cos(heading), -math.sin(heading), 0.0])
    up = np.cross(right, forward)
    rolled_right = right * math.cos(roll) - up * math.sin(roll)
    rolled_up = up * math.cos(roll) + right * math.sin(roll)
    return np.column_stack([rolled_right, -rolled_up, forward])


def _opencv_coefficients(radial_distortion: tuple[float, ...]) -> np.ndarray | None:
    """OpenCV's coefficient order (k1, k2, p1, p2, k3) with no tangential terms."""
    if not radial_distortion:
        return None
    k1, k2, *k3 = radial_distortion
    return np.array([k1, k2, 0.0, 0.0, *k3])
