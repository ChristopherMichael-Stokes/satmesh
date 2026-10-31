"""The images a photo is matched against, for the flat, bare-earth and full-surface references.

Three references render a scene from the prior pose, so the photo is matched in its own view:
the ortho on a flat plane, on the DTM, or on the DSM mesh. The fourth works in a top-down view:
the photo is warped onto the ground plane by the plane-induced homography, and the ortho on a
flat plane is rendered by a camera looking straight down. For a plane the nadir render is the
ortho itself, scaled.

Plane-induced homography: a plane point P = (X, Y, h) satisfies P - c = X e1 + Y e2 + (h e3 - c)
in area ENU, so a camera with intrinsics K, rotation R (camera to ENU) and centre c maps (X, Y, 1)
to pixels as M = K R^T [e1, e2, h e3 - c]. A pixel of camera 1 maps to camera 2 by M2 M1^-1
(Hartley and Zisserman, "Multiple View Geometry", 2nd ed., section 13.1).
"""

import math
from collections.abc import Callable
from dataclasses import dataclass

import cv2
import numpy as np
import numpy.typing as npt

from satmesh_core import EnuFrame
from satmesh_eval.camera import (
    CameraPose,
    Intrinsics,
    camera_centre_and_rotation,
    pixel_rays,
    pose_from_enu,
)
from satmesh_eval.localise import MatchingViews, ReferenceView
from satmesh_eval.perspective import RenderResult

Renderer = Callable[[Intrinsics, CameraPose, float], RenderResult]


@dataclass(frozen=True)
class PhotoQuery:
    """A photo, its undistorted pinhole intrinsics and the prior pose references are rendered at."""

    image: npt.NDArray[np.uint8]
    intrinsics: Intrinsics
    prior: CameraPose
    area: EnuFrame


NADIR_HEIGHT_M = (
    100.0  # any height gives the same flat-plane image; this keeps clear of the near plane
)
NADIR_LONG_SIDE_PX = 1280  # longest side of the nadir view, the size the matchers work at
FOOTPRINT_PIXEL_STRIDE = 16
MINIMUM_FOOTPRINT_POINTS = 100
NADIR_HEADING_DEG = 0.0  # image up is north
NADIR_PITCH_DEG = -90.0
PIXEL_CENTRE_OFFSET = 0.5  # camera.py puts pixel centres at +0.5, cv2.warpPerspective at integers


def perspective_views(query: PhotoQuery, render: Renderer, max_range_m: float) -> MatchingViews:
    """The photo against a render of a scene from the prior pose, with the photo's intrinsics."""
    centre, camera_to_enu = camera_centre_and_rotation(query.prior, query.area)
    reference = ReferenceView(
        render(query.intrinsics, query.prior, max_range_m), query.intrinsics, centre, camera_to_enu
    )
    return MatchingViews(query.image, reference, np.eye(3))


def nadir_views(
    query: PhotoQuery,
    flat_render: Renderer,
    plane_height_m: float,
    ground_sample_m: float,
    max_range_m: float,
) -> MatchingViews:
    """The photo warped onto the ground plane at `plane_height_m`, against the ortho from above.

    The nadir camera is centred over the ground the prior pose sees within `max_range_m` and sized
    to cover it, at `ground_sample_m` per pixel or coarser if that would pass
    `NADIR_LONG_SIDE_PX`. Raises `ValueError` if the prior sees too little ground.
    """
    intrinsics = query.intrinsics
    centre, camera_to_enu = camera_centre_and_rotation(query.prior, query.area)
    low, high = _ground_footprint(intrinsics, centre, camera_to_enu, plane_height_m, max_range_m)
    middle = (low + high) / 2.0
    nadir_pose = pose_from_enu(
        query.area,
        np.array([*middle, plane_height_m + NADIR_HEIGHT_M]),
        NADIR_HEADING_DEG,
        NADIR_PITCH_DEG,
        0.0,
    )
    nadir_centre, nadir_to_enu = camera_centre_and_rotation(nadir_pose, query.area)
    nadir_intrinsics = _nadir_intrinsics(high - low, ground_sample_m)
    reference = ReferenceView(
        flat_render(nadir_intrinsics, nadir_pose, 2.0 * NADIR_HEIGHT_M),
        nadir_intrinsics,
        nadir_centre,
        nadir_to_enu,
    )
    plane_from_photo = _plane_projection(intrinsics, camera_to_enu, centre, plane_height_m)
    plane_from_nadir = _plane_projection(
        nadir_intrinsics, nadir_to_enu, nadir_centre, plane_height_m
    )
    nadir_from_photo = plane_from_nadir @ np.linalg.inv(plane_from_photo)
    warped = np.asarray(
        cv2.warpPerspective(
            query.image,
            _in_integer_centres(nadir_from_photo),
            (nadir_intrinsics.width_px, nadir_intrinsics.height_px),
        ),
        dtype=np.uint8,
    )
    return MatchingViews(warped, reference, np.linalg.inv(nadir_from_photo))


def _ground_footprint(
    intrinsics: Intrinsics,
    centre: npt.NDArray[np.float64],
    camera_to_enu: npt.NDArray[np.float64],
    plane_height_m: float,
    max_range_m: float,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """South-west and north-east corners of the plane points the camera sees within range."""
    rays = pixel_rays(intrinsics, camera_to_enu).reshape(-1, 3)[:: FOOTPRINT_PIXEL_STRIDE**2]
    looking_down = rays[:, 2] < 0.0
    distance = (plane_height_m - centre[2]) / rays[looking_down, 2]
    points = centre + rays[looking_down] * distance[:, None]
    seen = points[distance <= max_range_m, :2]
    if len(seen) < MINIMUM_FOOTPRINT_POINTS:
        msg = f"the camera sees {len(seen)} sampled ground points within {max_range_m} m"
        raise ValueError(msg)
    return seen.min(axis=0), seen.max(axis=0)


def _nadir_intrinsics(span_m: npt.NDArray[np.float64], ground_sample_m: float) -> Intrinsics:
    sample_m = max(ground_sample_m, float(span_m.max()) / NADIR_LONG_SIDE_PX)
    width, height = (math.ceil(extent / sample_m) for extent in span_m)
    focal = NADIR_HEIGHT_M / sample_m
    return Intrinsics(width, height, focal, focal, width / 2.0, height / 2.0, ())


def _plane_projection(
    intrinsics: Intrinsics,
    camera_to_enu: npt.NDArray[np.float64],
    centre: npt.NDArray[np.float64],
    plane_height_m: float,
) -> npt.NDArray[np.float64]:
    """3 x 3 matrix taking plane coordinates (X, Y, 1) to homogeneous pixels."""
    plane_basis = np.column_stack(
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, plane_height_m] - centre]
    )
    return intrinsics.matrix() @ camera_to_enu.T @ plane_basis


def _in_integer_centres(homography: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """The homography for pixel coordinates with centres at integers instead of half-integers."""
    shift = np.array(
        [[1.0, 0.0, PIXEL_CENTRE_OFFSET], [0.0, 1.0, PIXEL_CENTRE_OFFSET], [0.0, 0.0, 1.0]]
    )
    return np.linalg.inv(shift) @ homography @ shift
