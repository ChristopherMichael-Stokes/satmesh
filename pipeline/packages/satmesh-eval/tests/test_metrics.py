import numpy as np
import pytest

from satmesh_eval.localise import PoseError
from satmesh_eval.matching import Matches
from satmesh_eval.metrics import CELLS_PER_SIDE, known_pose_metrics, pose_recall
from satmesh_eval.perspective import RenderResult

WIDTH_PX, HEIGHT_PX, FOCAL_PX = 640, 480, 400.0
SIDEWAYS_M, FORWARD_M = 0.5, 0.2  # the photo camera sits this far from the render camera


def render_with_depth(left_m: float, right_m: float) -> RenderResult:
    z = np.full((HEIGHT_PX, WIDTH_PX), right_m)
    z[:, : WIDTH_PX // 2] = left_m
    return RenderResult(
        np.zeros((HEIGHT_PX, WIDTH_PX, 3), np.uint8), z, z, np.ones((HEIGHT_PX, WIDTH_PX), bool)
    )


def left_half_matches(rng: np.random.Generator, per_cell: int) -> tuple[Matches, np.ndarray]:
    """Matches for render pixels in every left-half cell, and their distances in pixels.

    The photo pixels are what a camera moved sideways and forward sees for 3D points at 8 to 20 m
    depth under the render pixels; the distances are worked out from the pinhole equations.
    """
    cell_w, cell_h = WIDTH_PX / CELLS_PER_SIDE, HEIGHT_PX / CELLS_PER_SIDE
    cells = [(c, r) for r in range(CELLS_PER_SIDE) for c in range(CELLS_PER_SIDE // 2)]
    render_px = np.array(
        [
            [(c + rng.uniform(0.1, 0.9)) * cell_w, (r + rng.uniform(0.1, 0.9)) * cell_h]
            for c, r in cells
            for _ in range(per_cell)
        ]
    )
    depth = rng.uniform(8.0, 20.0, len(render_px))
    x = (render_px[:, 0] - WIDTH_PX / 2) / FOCAL_PX * depth
    y = (render_px[:, 1] - HEIGHT_PX / 2) / FOCAL_PX * depth
    photo_depth = depth - FORWARD_M
    photo_px = np.column_stack(
        [
            FOCAL_PX * (x - SIDEWAYS_M) / photo_depth + WIDTH_PX / 2,
            FOCAL_PX * y / photo_depth + HEIGHT_PX / 2,
        ]
    )
    return Matches(photo_px, render_px), np.linalg.norm(photo_px - render_px, axis=1)


def test_displacement_and_coverage_of_matches_from_a_known_two_camera_geometry() -> None:
    rng = np.random.default_rng(0)
    matches, distance_px = left_half_matches(rng, per_cell=3)
    outliers = rng.choice(len(matches), len(matches) // 4, replace=False)
    wrong = matches.points_a.copy()
    wrong[outliers] = rng.uniform([0, 0], [WIDTH_PX, HEIGHT_PX], (len(outliers), 2))
    keep = np.setdiff1d(np.arange(len(matches)), outliers)

    metrics = known_pose_metrics(Matches(wrong, matches.points_b), render_with_depth(15.0, 150.0))

    assert metrics.match_count == len(matches)
    assert metrics.inlier_count >= int(0.9 * len(keep))
    assert metrics.median_displacement_px == pytest.approx(np.median(distance_px[keep]), rel=0.1)
    assert metrics.hit_fraction == 1.0
    assert metrics.cell_coverage == pytest.approx(0.5)  # the 32 left cells of 64
    near, middle, far = metrics.bands
    assert (near.upper_m, middle.upper_m, far.upper_m) == (25.0, 100.0, None)
    assert near.hit_pixel_fraction == pytest.approx(0.5)
    assert near.cell_coverage == pytest.approx(1.0)
    assert (middle.hit_pixel_fraction, middle.cell_coverage) == (0.0, None)
    assert far.hit_pixel_fraction == pytest.approx(0.5)
    assert (far.inlier_count, far.cell_coverage) == (0, 0.0)


def test_too_few_matches_give_no_inliers_and_no_displacement() -> None:
    matches = Matches(np.array([[10.0, 10.0]] * 3), np.array([[12.0, 10.0]] * 3))

    metrics = known_pose_metrics(matches, render_with_depth(15.0, 15.0))

    assert (metrics.inlier_count, metrics.median_displacement_px) == (0, None)
    assert metrics.cell_coverage == 0.0


def test_recall_counts_poses_within_each_threshold_and_ignores_unsolved_ones() -> None:
    errors = [
        PoseError(0.1, 1.0),  # within all three
        PoseError(0.4, 1.0),  # translation fails the first
        PoseError(0.4, 6.0),  # rotation fails the first and second
        PoseError(9.0, 1.0),  # beyond all
        None,
    ]

    summary = pose_recall(errors)

    assert summary.photo_count == 5
    assert summary.solved_count == 4
    assert summary.recalled == (1, 2, 3)
    assert summary.median_translation_m == pytest.approx(0.4)
    assert summary.median_rotation_deg == pytest.approx(1.0)


def test_recall_without_any_solved_pose_has_no_median() -> None:
    summary = pose_recall([None, None])

    assert (summary.solved_count, summary.recalled) == (0, (0, 0, 0))
    assert summary.median_translation_m is None
