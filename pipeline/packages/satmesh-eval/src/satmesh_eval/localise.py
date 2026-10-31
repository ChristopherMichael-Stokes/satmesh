"""Localise a photo against a rendered reference: match, lift through the render's depth, solve.

The method is MeshLoc (Panek, Kukelova and Sattler, "MeshLoc: Mesh-Based Visual Localization",
ECCV 2022, arXiv 2207.10762): match the query against a render of the mesh, give each matched
render pixel the 3D point the render's depth puts there, and solve the query pose from the 2D-3D
pairs with perspective-n-point inside RANSAC. MeshLoc renders at retrieved database poses; here
the render is made at a prior pose and the result is compared with the photo's known pose.
"""

from dataclasses import dataclass

import cv2
import numpy as np
import numpy.typing as npt
from scipy.spatial.transform import Rotation

from satmesh_eval.camera import Intrinsics
from satmesh_eval.matching import Matcher, Matches
from satmesh_eval.perspective import RenderResult

REPROJECTION_THRESHOLD_PX = 20.0  # MeshLoc's RANSAC inlier threshold
RANSAC_CONFIDENCE = 0.9999
RANSAC_ITERATIONS = 10000
MINIMAL_SOLVER_POINTS = 4  # OpenCV's RANSAC takes minimal samples of at least four points
# MeshLoc's pose-recall operating points (Aachen Day-Night): metres and degrees
RECALL_THRESHOLDS = ((0.25, 2.0), (0.5, 5.0), (5.0, 10.0))


@dataclass(frozen=True)
class ReferenceView:
    """A render and the camera that made it, in area ENU metres."""

    render: RenderResult
    intrinsics: Intrinsics
    centre_enu: npt.NDArray[np.float64]
    camera_to_enu: npt.NDArray[np.float64]


@dataclass(frozen=True)
class MatchingViews:
    """The two images that get matched and how matches map back to the photo.

    `photo_view` is the photo as matched: the photo itself, or the photo warped into the
    reference's view. `photo_from_photo_view` is the 3 x 3 homography taking pixels of
    `photo_view` to pixels of the photo (identity when it is the photo).
    """

    photo_view: npt.NDArray[np.uint8]
    reference: ReferenceView
    photo_from_photo_view: npt.NDArray[np.float64]


@dataclass(frozen=True)
class Correspondences:
    """Photo pixels (N, 2) paired with the area-ENU points (N, 3) they should see."""

    photo_points: npt.NDArray[np.float64]
    world_points: npt.NDArray[np.float64]


@dataclass(frozen=True)
class PoseEstimate:
    """Camera pose in area ENU with the correspondences that agree with it."""

    centre_enu: npt.NDArray[np.float64]
    camera_to_enu: npt.NDArray[np.float64]
    inlier_mask: npt.NDArray[np.bool_]


@dataclass(frozen=True)
class PoseError:
    """Distance between camera centres (metres) and the angle between attitudes (degrees)."""

    translation_m: float
    rotation_deg: float

    def within(self, translation_m: float, rotation_deg: float) -> bool:
        """Whether both errors are at or below the thresholds."""
        return self.translation_m <= translation_m and self.rotation_deg <= rotation_deg


@dataclass(frozen=True)
class Localisation:
    """Outcome of one photo against one reference; `estimate` is None when no pose was found."""

    match_count: int
    correspondences: Correspondences
    estimate: PoseEstimate | None


def localise(views: MatchingViews, photo_intrinsics: Intrinsics, matcher: Matcher) -> Localisation:
    """Match `views`, lift the matches and solve the photo's pose."""
    matches = matcher(views.photo_view, views.reference.render.rgb)
    correspondences = lift_matches(matches, views)
    estimate = solve_pose(correspondences, photo_intrinsics)
    return Localisation(len(matches), correspondences, estimate)


def lift_matches(matches: Matches, views: MatchingViews) -> Correspondences:
    """Pair photo pixels with the 3D points the reference's depth gives their matched pixels.

    A reference pixel (u, v) with optical-axis depth z is the camera-space point
    z K^-1 (u, v, 1), then R x + c in area ENU. The nearest pixel's depth is used; matches on
    pixels the render missed are dropped.
    """
    reference = views.reference
    columns, rows = np.floor(matches.points_b).astype(int).T
    height, width = reference.render.z_depth_m.shape
    inside = (rows >= 0) & (rows < height) & (columns >= 0) & (columns < width)
    depth = np.full(len(matches), np.nan)
    depth[inside] = reference.render.z_depth_m[rows[inside], columns[inside]]
    lifted = np.isfinite(depth)
    pixels = np.column_stack([matches.points_b[lifted], np.ones(lifted.sum())])
    in_camera = (pixels @ np.linalg.inv(reference.intrinsics.matrix()).T) * depth[lifted, None]
    world = in_camera @ reference.camera_to_enu.T + reference.centre_enu
    photo_points = _apply_homography(views.photo_from_photo_view, matches.points_a[lifted])
    return Correspondences(photo_points, world)


def solve_pose(
    correspondences: Correspondences,
    intrinsics: Intrinsics,
    reprojection_threshold_px: float = REPROJECTION_THRESHOLD_PX,
) -> PoseEstimate | None:
    """Perspective-n-point inside RANSAC, refined on the inliers; None if no pose is found.

    The solver is SQPnP (Terzakis and Lourakis, "A Consistently Fast and Globally Optimal Solution
    to the Perspective-n-Point Problem", ECCV 2020), which also handles coplanar points: a flat
    reference puts every point on one plane, where P3P solutions flip to the wrong side of it.
    The inliers are refined by Levenberg-Marquardt on reprojection error. The photo is assumed
    undistorted.
    """
    if len(correspondences.photo_points) < MINIMAL_SOLVER_POINTS:
        return None
    found, rotation_vector, translation, inliers = cv2.solvePnPRansac(
        correspondences.world_points,
        correspondences.photo_points,
        intrinsics.matrix(),
        None,
        iterationsCount=RANSAC_ITERATIONS,
        reprojectionError=reprojection_threshold_px,
        confidence=RANSAC_CONFIDENCE,
        flags=cv2.SOLVEPNP_SQPNP,
    )
    if not found:
        return None
    inlier_index = inliers.ravel().astype(np.intp)
    rotation_vector, translation = cv2.solvePnPRefineLM(
        correspondences.world_points[inlier_index],
        correspondences.photo_points[inlier_index],
        intrinsics.matrix(),
        None,
        rotation_vector,
        translation,
    )
    world_to_camera, _ = cv2.Rodrigues(rotation_vector)
    inlier_mask = np.zeros(len(correspondences.photo_points), dtype=bool)
    inlier_mask[inlier_index] = True
    return PoseEstimate(
        centre_enu=np.asarray((-world_to_camera.T @ translation).ravel(), dtype=np.float64),
        camera_to_enu=np.asarray(world_to_camera.T, dtype=np.float64),
        inlier_mask=inlier_mask,
    )


def pose_error(
    estimate: PoseEstimate,
    true_centre_enu: npt.NDArray[np.float64],
    true_camera_to_enu: npt.NDArray[np.float64],
) -> PoseError:
    """Camera-centre distance and the rotation angle of R_estimated^T R_true."""
    relative = Rotation.from_matrix(estimate.camera_to_enu.T @ true_camera_to_enu)
    return PoseError(
        translation_m=float(np.linalg.norm(estimate.centre_enu - true_centre_enu)),
        rotation_deg=float(np.degrees(relative.magnitude())),
    )


def _apply_homography(
    homography: npt.NDArray[np.float64], points: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    homogeneous = np.column_stack([points, np.ones(len(points))]) @ homography.T
    return homogeneous[:, :2] / homogeneous[:, 2:3]
