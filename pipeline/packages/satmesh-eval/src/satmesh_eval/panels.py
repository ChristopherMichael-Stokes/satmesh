"""Images and match lines of one localisation, encoded for the review page."""

from dataclasses import dataclass

import cv2
import numpy as np
import numpy.typing as npt

from satmesh_eval.camera import Intrinsics
from satmesh_eval.localise import Localisation, MatchingViews, lifted_mask
from satmesh_eval.metrics import reprojection_error_px

PANEL_HEIGHT_PX = 330
JPEG_QUALITY = 72
MAX_DRAWN_MATCHES = 70
AGREEMENT_PX = (
    3.0  # a match agrees when the true pose puts its 3D point this close to the photo pixel
)


@dataclass(frozen=True)
class MatchLine:
    """A match as fractions of the photo view's and the reference's width and height."""

    photo_x: float
    photo_y: float
    reference_x: float
    reference_y: float
    agrees_with_true_pose: bool


@dataclass(frozen=True)
class FixPanels:
    """JPEG bytes of the photo as matched, the reference render and its depth, and match lines.

    `depth_range_m` is the (nearest, farthest) depth the grey levels of `depth_jpeg` span; misses
    are black.
    """

    photo_view_jpeg: bytes
    reference_jpeg: bytes
    depth_jpeg: bytes
    depth_range_m: tuple[float, float]
    lines: tuple[MatchLine, ...]


def encode_photo(image: npt.NDArray[np.uint8]) -> bytes:
    """Thumbnail JPEG of an RGB image."""
    return _jpeg(image)


def encode_panels(
    views: MatchingViews,
    localisation: Localisation,
    intrinsics: Intrinsics,
    true_centre_enu: npt.NDArray[np.float64],
    true_camera_to_enu: npt.NDArray[np.float64],
) -> FixPanels:
    """Panels of one localisation, matches judged against the true pose."""
    render = views.reference.render
    depth = render.z_depth_m
    near, far = (
        (float(np.nanmin(depth)), float(np.nanmax(depth))) if render.hit_mask.any() else (0.0, 1.0)
    )
    grey = np.where(render.hit_mask, 1.0 + 254.0 * (depth - near) / max(far - near, 1e-9), 0.0)
    return FixPanels(
        photo_view_jpeg=_jpeg(views.photo_view),
        reference_jpeg=_jpeg(render.rgb),
        depth_jpeg=_jpeg(np.repeat(np.nan_to_num(grey)[..., None], 3, axis=2).astype(np.uint8)),
        depth_range_m=(near, far),
        lines=_lines(views, localisation, intrinsics, true_centre_enu, true_camera_to_enu),
    )


def _lines(
    views: MatchingViews,
    localisation: Localisation,
    intrinsics: Intrinsics,
    true_centre_enu: npt.NDArray[np.float64],
    true_camera_to_enu: npt.NDArray[np.float64],
) -> tuple[MatchLine, ...]:
    matches = localisation.matches
    lifted = lifted_mask(matches, views)
    agrees = (
        reprojection_error_px(
            localisation.correspondences, intrinsics, true_centre_enu, true_camera_to_enu
        )
        <= AGREEMENT_PX
    )
    photo_height, photo_width = views.photo_view.shape[:2]
    reference_height, reference_width = views.reference.render.rgb.shape[:2]
    points_a, points_b = matches.points_a[lifted], matches.points_b[lifted]
    drawn = (
        np.unique(
            np.linspace(0, len(points_a) - 1, min(MAX_DRAWN_MATCHES, len(points_a))).astype(int)
        )
        if len(points_a)
        else []
    )
    return tuple(
        MatchLine(
            float(points_a[i, 0] / photo_width),
            float(points_a[i, 1] / photo_height),
            float(points_b[i, 0] / reference_width),
            float(points_b[i, 1] / reference_height),
            bool(agrees[i]),
        )
        for i in drawn
    )


def _jpeg(rgb: npt.NDArray[np.uint8]) -> bytes:
    height, width = rgb.shape[:2]
    scale = PANEL_HEIGHT_PX / height
    size = (round(width * scale), PANEL_HEIGHT_PX)
    thumbnail = cv2.resize(rgb, size, interpolation=cv2.INTER_AREA)
    _, encoded = cv2.imencode(
        ".jpg", cv2.cvtColor(thumbnail, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
    )
    return encoded.tobytes()
