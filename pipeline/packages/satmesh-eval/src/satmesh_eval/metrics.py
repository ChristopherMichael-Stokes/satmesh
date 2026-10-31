"""Metrics of the localisation harness: pose recall, and match agreement at the known pose.

At the known pose the reference is rendered where the photo was taken and the photo is matched
against it. With a faithful render every match sits at the same pixel in both images; a large
consistent displacement means the render puts content at the wrong place (georegistration), and
cells of the image without any agreeing match mean content the render lacks.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median

import cv2
import numpy as np
import numpy.typing as npt

from satmesh_eval.camera import Intrinsics
from satmesh_eval.localise import RECALL_THRESHOLDS, Correspondences, PoseError
from satmesh_eval.matching import Matches
from satmesh_eval.perspective import RenderResult

CELLS_PER_SIDE = 8
# Reporting split of render depth (metres along the optical axis): near, middle and far field.
DEPTH_BAND_EDGES_M = (25.0, 100.0)
# MAGSAC++ threshold on epipolar distance, the setting of the Image Matching Challenge baselines;
# it separates matches that obey one rigid camera geometry from mismatches.
GEOMETRIC_THRESHOLD_PX = 2.0
GEOMETRIC_CONFIDENCE = 0.999
GEOMETRIC_ITERATIONS = 10000
MINIMUM_EPIPOLAR_MATCHES = 8


@dataclass(frozen=True)
class DepthBandCoverage:
    """Agreeing matches in one band of render depth; `upper_m` is None for the last band."""

    lower_m: float
    upper_m: float | None
    hit_pixel_fraction: float
    inlier_count: int
    cell_coverage: float | None


@dataclass(frozen=True)
class KnownPoseMetrics:
    """Match agreement of a photo with a render at the photo's true pose.

    `median_displacement_px` is over the inliers (None without any), `hit_fraction` is the share
    of the frame the render covers (not sky), and `cell_coverage` is the share of the
    `CELLS_PER_SIDE` squared image cells holding an inlier among cells the render covers. Each
    band's `cell_coverage` counts only cells with render pixels in that band (None if none).
    """

    match_count: int
    inlier_count: int
    median_displacement_px: float | None
    hit_fraction: float
    cell_coverage: float | None
    bands: tuple[DepthBandCoverage, ...]


@dataclass(frozen=True)
class RecallSummary:
    """Poses within each of `RECALL_THRESHOLDS` out of `photo_count`, and the median error.

    `solved_count` photos produced an accepted pose; `median_translation_m` is over those.
    """

    photo_count: int
    solved_count: int
    recalled: tuple[int, ...]
    median_translation_m: float | None
    median_rotation_deg: float | None


def known_pose_metrics(matches: Matches, render: RenderResult) -> KnownPoseMetrics:
    """Agreement of `matches` (photo points_a, render points_b) with the render of the true pose."""
    inliers = _epipolar_inliers(matches)
    displacements = np.linalg.norm(matches.points_a[inliers] - matches.points_b[inliers], axis=1)
    height, width = render.hit_mask.shape
    inlier_cells = _cell_of(matches.points_b[inliers], width, height)
    inlier_depth = _depth_at(render, matches.points_b[inliers])
    hit_cells = _cell_of_hits(render.hit_mask)
    return KnownPoseMetrics(
        match_count=len(matches),
        inlier_count=int(inliers.sum()),
        median_displacement_px=float(np.median(displacements)) if len(displacements) else None,
        hit_fraction=float(render.hit_mask.mean()),
        cell_coverage=_coverage(hit_cells, inlier_cells),
        bands=_bands(render, hit_cells, inlier_cells, inlier_depth),
    )


def pose_recall(errors: Sequence[PoseError | None]) -> RecallSummary:
    """Recall at `RECALL_THRESHOLDS` over photos; None marks a photo with no accepted pose."""
    solved = [error for error in errors if error is not None]
    return RecallSummary(
        photo_count=len(errors),
        solved_count=len(solved),
        recalled=tuple(
            sum(error.within(metres, degrees) for error in solved)
            for metres, degrees in RECALL_THRESHOLDS
        ),
        median_translation_m=median(e.translation_m for e in solved) if solved else None,
        median_rotation_deg=median(e.rotation_deg for e in solved) if solved else None,
    )


def _epipolar_inliers(matches: Matches) -> npt.NDArray[np.bool_]:
    """Matches that obey one epipolar geometry; a pure shift (or no motion) has none to fit."""
    none = np.zeros(len(matches), dtype=bool)
    if len(matches) < MINIMUM_EPIPOLAR_MATCHES:
        return none
    try:
        _, mask = cv2.findFundamentalMat(
            matches.points_a,
            matches.points_b,
            cv2.USAC_MAGSAC,
            GEOMETRIC_THRESHOLD_PX,
            GEOMETRIC_CONFIDENCE,
            GEOMETRIC_ITERATIONS,
        )
    except cv2.error:  # a perfect render gives identical points, where F is undefined
        return _near_median_shift(matches)
    if mask is None:
        return none
    return np.asarray(mask.ravel() > 0, dtype=bool)


def _near_median_shift(matches: Matches) -> npt.NDArray[np.bool_]:
    shifts = matches.points_b - matches.points_a
    distance = np.linalg.norm(shifts - np.median(shifts, axis=0), axis=1)
    return np.asarray(distance <= GEOMETRIC_THRESHOLD_PX, dtype=bool)


def _cell_of(points: npt.NDArray[np.float64], width: int, height: int) -> npt.NDArray[np.intp]:
    """Flat cell index of each pixel position, clipped into the grid."""
    columns = np.clip(
        (points[:, 0] / width * CELLS_PER_SIDE).astype(np.intp), 0, CELLS_PER_SIDE - 1
    )
    rows = np.clip((points[:, 1] / height * CELLS_PER_SIDE).astype(np.intp), 0, CELLS_PER_SIDE - 1)
    return rows * CELLS_PER_SIDE + columns


def _cell_of_hits(hit_mask: npt.NDArray[np.bool_]) -> npt.NDArray[np.intp]:
    rows, columns = np.nonzero(hit_mask)
    height, width = hit_mask.shape
    return _cell_of(np.column_stack([columns + 0.5, rows + 0.5]).astype(np.float64), width, height)


def _depth_at(render: RenderResult, points: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    height, width = render.z_depth_m.shape
    columns = np.clip(points[:, 0].astype(np.intp), 0, width - 1)
    rows = np.clip(points[:, 1].astype(np.intp), 0, height - 1)
    return render.z_depth_m[rows, columns]


def _coverage(
    covered_cells: npt.NDArray[np.intp], inlier_cells: npt.NDArray[np.intp]
) -> float | None:
    """Share of the cells in `covered_cells` that appear in `inlier_cells`; None if no cells."""
    cells = np.unique(covered_cells)
    if len(cells) == 0:
        return None
    return float(np.isin(cells, inlier_cells).mean())


def _bands(
    render: RenderResult,
    hit_cells: npt.NDArray[np.intp],
    inlier_cells: npt.NDArray[np.intp],
    inlier_depth: npt.NDArray[np.float64],
) -> tuple[DepthBandCoverage, ...]:
    lowers = (0.0, *DEPTH_BAND_EDGES_M)
    uppers = (*DEPTH_BAND_EDGES_M, np.inf)
    hit_depth = render.z_depth_m[render.hit_mask]
    bands = []
    for lower, upper in zip(lowers, uppers, strict=True):
        in_band = (hit_depth >= lower) & (hit_depth < upper)
        inlier_in_band = (inlier_depth >= lower) & (inlier_depth < upper)
        bands.append(
            DepthBandCoverage(
                lower_m=lower,
                upper_m=None if np.isinf(upper) else upper,
                hit_pixel_fraction=float(in_band.sum() / render.hit_mask.size),
                inlier_count=int(inlier_in_band.sum()),
                cell_coverage=_coverage(hit_cells[in_band], inlier_cells[inlier_in_band]),
            )
        )
    return tuple(bands)


def reprojection_error_px(
    correspondences: Correspondences,
    intrinsics: Intrinsics,
    centre_enu: npt.NDArray[np.float64],
    camera_to_enu: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Pixel distance of each correspondence's 3D point, seen from a pose, to its photo pixel.

    Infinite for points behind the camera.
    """
    in_camera = (correspondences.world_points - centre_enu) @ camera_to_enu
    ahead = in_camera[:, 2] > 0.0
    homogeneous = in_camera @ intrinsics.matrix().T
    projected = homogeneous[:, :2] / np.where(ahead, homogeneous[:, 2], 1.0)[:, None]
    distance = np.linalg.norm(projected - correspondences.photo_points, axis=1)
    return np.where(ahead, distance, np.inf)
