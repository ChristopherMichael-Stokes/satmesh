"""Heading change between video frames from feature matches, with no pose and an approximate lens.

The relative rotation of two frames comes from the matched pixels in one of two ways:

- essential matrix: five-point RANSAC (Nister, "An efficient solution to the five-point relative
  pose problem", PAMI 2004; OpenCV `findEssentialMat`) and `recoverPose`, which keeps the
  decomposition with the points in front of both cameras. Degenerate with no translation.
- rotation-only homography: for a camera that only turns, x_b ~ K R K^-1 x_a, so
  R ~ K^-1 H K, scaled to unit determinant and projected onto the nearest rotation by SVD
  (R = U V^T of the scaled matrix). Holds while the motion is close to a pure rotation.

`R` maps camera-a coordinates to camera-b coordinates (x_b = R x_a + t, camera axes right, down,
forward). The camera itself turns by R^T; its heading change is the component of R^T's rotation
vector along the world vertical, whose direction in camera a is (0, -cos d, -sin d) for a camera
pitched down by d. Heading runs clockwise from above, as in `satmesh_eval.camera`, hence the sign.
On the Bexhill clip at 2 s apart the essential estimate is within 1.3 degrees (median) of the
tracker's heading change with an 80 degree nominal lens, the homography within 0.3 degrees.
"""

import math
from collections.abc import Sequence
from itertools import pairwise

import cv2
import numpy as np
import numpy.typing as npt

from satmesh_eval.matching import Matcher
from satmesh_track.priors import YawMethod

FloatArray = npt.NDArray[np.float64]

ESSENTIAL_RANSAC_PX = 1.0
HOMOGRAPHY_RANSAC_PX = 3.0  # three times the essential threshold, as measured on the Bexhill clip
RANSAC_CONFIDENCE = 0.999
MIN_YAW_MATCHES = 20  # fewer matches leave the rotation unreliable; pairs below are not estimated
ROTATION_SHAPE = (3, 3)


def focal_for_field_of_view(width_px: int, horizontal_fov_deg: float) -> float:
    """Focal length in pixels of a `width_px` image spanning `horizontal_fov_deg`."""
    return (width_px / 2) / math.tan(math.radians(horizontal_fov_deg) / 2)


def rotation_from_essential(
    points_a: FloatArray, points_b: FloatArray, camera_matrix: FloatArray
) -> FloatArray | None:
    """Rotation from frame a to frame b by the essential matrix; None if none is found."""
    essential, mask = cv2.findEssentialMat(
        points_a,
        points_b,
        camera_matrix,
        method=cv2.RANSAC,
        prob=RANSAC_CONFIDENCE,
        threshold=ESSENTIAL_RANSAC_PX,
    )
    # None when RANSAC finds nothing (the stubs miss it), stacked 3 x 3 blocks when ambiguous
    if np.shape(essential) != ROTATION_SHAPE:
        return None
    _, rotation, _, _ = cv2.recoverPose(essential, points_a, points_b, camera_matrix, mask=mask)
    return np.asarray(rotation, dtype=np.float64)


def rotation_from_homography(
    points_a: FloatArray, points_b: FloatArray, camera_matrix: FloatArray
) -> FloatArray | None:
    """Rotation from frame a to frame b by a rotation-only homography; None if none is found."""
    homography, _ = cv2.findHomography(points_a, points_b, cv2.RANSAC, HOMOGRAPHY_RANSAC_PX)
    if np.shape(homography) != ROTATION_SHAPE:  # None when RANSAC finds nothing
        return None
    conjugated = np.linalg.inv(camera_matrix) @ np.asarray(homography) @ camera_matrix
    scaled = conjugated / np.cbrt(np.linalg.det(conjugated))
    left, _, right = np.linalg.svd(scaled)
    rotation = left @ right
    return rotation if np.linalg.det(rotation) > 0 else -rotation


def heading_change_deg(rotation_a_to_b: FloatArray, pitch_deg: float) -> float:
    """Heading change of the camera, degrees clockwise from above, from a point rotation a to b."""
    down = math.radians(-pitch_deg)
    up_in_camera = np.array([0.0, -math.cos(down), -math.sin(down)])
    camera_turn, _ = cv2.Rodrigues(rotation_a_to_b.T)
    return -math.degrees(float(np.ravel(camera_turn) @ up_in_camera))


def pair_heading_change_deg(  # noqa: PLR0913 (two point sets, the lens, pitch, method, agreement)
    points_a: FloatArray,
    points_b: FloatArray,
    camera_matrix: FloatArray,
    *,
    pitch_deg: float,
    method: YawMethod,
    agreement_deg: float,
) -> float | None:
    """Heading change from frame a to frame b; None if the pair gives no trusted estimate.

    `agree` takes the essential estimate only when the homography's is within `agreement_deg`.
    """
    if len(points_a) < MIN_YAW_MATCHES:
        return None
    estimates: dict[str, float | None] = {}
    for name, estimator in (
        ("essential", rotation_from_essential),
        ("homography", rotation_from_homography),
    ):
        if method in {name, "agree"}:
            rotation = estimator(points_a, points_b, camera_matrix)
            estimates[name] = None if rotation is None else heading_change_deg(rotation, pitch_deg)
    if method != "agree":
        return estimates[method]
    essential, homography = estimates["essential"], estimates["homography"]
    if essential is None or homography is None or abs(essential - homography) > agreement_deg:
        return None
    return essential


def chained_offsets_deg(changes: Sequence[float | None]) -> tuple[float, ...] | None:
    """Offsets of each frame's heading from frame 0's, summing consecutive changes.

    None if any change is missing: a gap leaves the later frames' offsets unknown.
    """
    offsets: list[float] = [0.0]
    for change in changes:
        if change is None:
            return None
        offsets.append(offsets[-1] + change)
    return tuple(offsets)


def window_offsets_deg(  # noqa: PLR0913 (frames, matcher, lens, pitch, method, agreement)
    frames: Sequence[npt.NDArray[np.uint8]],
    matcher: Matcher,
    camera_matrix: FloatArray,
    *,
    pitch_deg: float,
    method: YawMethod,
    agreement_deg: float,
) -> tuple[float, ...] | None:
    """Heading offsets of the frames from the first, matched pair by pair; None if a pair fails."""
    changes = []
    for frame_a, frame_b in pairwise(frames):
        matches = matcher(frame_a, frame_b)
        changes.append(
            pair_heading_change_deg(
                matches.points_a,
                matches.points_b,
                camera_matrix,
                pitch_deg=pitch_deg,
                method=method,
                agreement_deg=agreement_deg,
            )
        )
    return chained_offsets_deg(changes)
