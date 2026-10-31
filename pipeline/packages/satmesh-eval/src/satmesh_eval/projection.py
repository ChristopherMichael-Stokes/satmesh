"""Viewing transforms and frustum culling for a pinhole camera in WebGPU clip-space conventions.

World space is area ENU (x east, y north, z up, metres), camera space follows OpenCV (x right,
y down, z forward). Normalised device coordinates run x, y in [-1, 1] with y = +1 at the top image
row, and depth in [0, 1] from the near plane to the far plane (WebGPU, not OpenGL's [-1, 1]).
Matrices act on column vectors; `matrix @ [x, y, z, 1]` gives clip coordinates.
"""

import numpy as np

from satmesh_eval.camera import Intrinsics

FRUSTUM_PLANE_COUNT = 6


def view_matrix(centre_enu: np.ndarray, camera_to_enu: np.ndarray) -> np.ndarray:
    """4 x 4 matrix taking area ENU points to camera space: R^T (p - c)."""
    to_camera = camera_to_enu.T
    view = np.eye(4)
    view[:3, :3] = to_camera
    view[:3, 3] = -to_camera @ centre_enu
    return view


def projection_matrix(intrinsics: Intrinsics, near_m: float, far_m: float) -> np.ndarray:
    """4 x 4 matrix taking camera-space points to WebGPU clip space.

    With pixel u = f_x X / Z + c_x and v = f_y Y / Z + c_y, the NDC are
    x = 2 u / W - 1 and y = 1 - 2 v / H, and depth = far (Z - near) / (Z (far - near)), which is 0
    at Z = near and 1 at Z = far. Clip w = Z. Pixel centres sit at half-integers (see
    `satmesh_eval.camera`), matching the NDC mapping of the framebuffer.
    """
    width, height = intrinsics.width_px, intrinsics.height_px
    projection = np.zeros((4, 4))
    projection[0, 0] = 2.0 * intrinsics.focal_x_px / width
    projection[0, 2] = 2.0 * intrinsics.principal_x_px / width - 1.0
    projection[1, 1] = -2.0 * intrinsics.focal_y_px / height
    projection[1, 2] = 1.0 - 2.0 * intrinsics.principal_y_px / height
    projection[2, 2] = far_m / (far_m - near_m)
    projection[2, 3] = -far_m * near_m / (far_m - near_m)
    projection[3, 2] = 1.0
    return projection


def frustum_planes(clip_from_world: np.ndarray) -> np.ndarray:
    """The six inward-facing planes (a, b, c, d) of the view volume, one per row.

    A point p is inside plane i when `planes[i] @ [p, 1] >= 0`. Rows come from the Gribb-Hartmann
    extraction (Gribb and Hartmann, "Fast Extraction of Viewing Frustum Planes from the
    World-View-Projection Matrix", 2001) adapted to depth in [0, 1]: left w + x, right w - x,
    bottom w + y, top w - y, near z, far w - z.
    """
    x, y, z, w = clip_from_world
    return np.stack([w + x, w - x, w + y, w - y, z, w - z])


def boxes_in_frustum(
    planes: np.ndarray, lower_corners: np.ndarray, upper_corners: np.ndarray
) -> np.ndarray:
    """Boolean mask of the axis-aligned boxes that are not entirely outside any plane.

    Per plane the box corner farthest along the plane normal is tested; if even that corner is
    behind the plane the box is outside. Conservative: a box near a frustum edge can pass without
    touching the volume.
    """
    normals, offsets = planes[:, :3], planes[:, 3]
    farthest = np.where(
        normals[None, :, :] >= 0.0, upper_corners[:, None, :], lower_corners[:, None, :]
    )
    signed_distance = np.einsum("bpk,pk->bp", farthest, normals) + offsets
    return np.all(signed_distance >= 0.0, axis=1)


def boxes_within_range(
    centre: np.ndarray, max_range_m: float, lower_corners: np.ndarray, upper_corners: np.ndarray
) -> np.ndarray:
    """Boolean mask of the axis-aligned boxes whose nearest point is within `max_range_m`."""
    nearest = np.clip(centre, lower_corners, upper_corners)
    return np.linalg.norm(nearest - centre, axis=1) <= max_range_m
