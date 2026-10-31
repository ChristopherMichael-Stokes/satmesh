import numpy as np
import scene

from satmesh_eval.camera import camera_centre_and_rotation
from satmesh_eval.matching import sift_match
from satmesh_eval.perspective import render
from satmesh_track.search import SearchConfig, best_candidates, candidate_poses, search_radius_m

CONFIG = SearchConfig(spacing_m=70.0, margin_m=60.0, height_factors=(1.0, 0.5), heading_count=4)


def test_the_radius_is_the_margin_plus_the_missed_steps_at_the_typical_step() -> None:
    assert search_radius_m(CONFIG, 12.0, 4) == 60.0 + 1.2 * 12.0 * 4


def test_candidates_cover_the_circle_in_every_height_and_heading() -> None:
    poses = candidate_poses(
        CONFIG,
        scene.area_frame(),
        scene.ground_height,
        np.array([0.0, 0.0]),
        100.0,
        [40.0, 20.0],
        -35.0,
    )

    # offsets -70, 0, 70 on each axis: all nine are within 100 m (70 * sqrt 2 = 99); the 20 m
    # height is raised to the 25 m floor so two heights stay distinct; four headings 90 degrees
    # apart
    assert len(poses) == 9 * 2 * 4
    frame = scene.area_frame()
    centres = np.array([camera_centre_and_rotation(p, frame)[0] for p in poses])
    assert sorted({round(float(h), 1) for h in centres[:, 2]}) == [25.0, 40.0]
    assert sorted({round(p.heading_deg) % 360 for p in poses}) == [0, 90, 180, 270]
    assert (
        np.isclose(centres[:, 0], 0.0, atol=1e-6).sum() == 3 * 2 * 4
    )  # the column through the centre


def test_positions_outside_the_scene_are_left_out() -> None:
    far = np.array([scene.GROUND_HALF_EXTENT_M, 0.0])

    poses = candidate_poses(
        CONFIG, scene.area_frame(), scene.ground_height, far, 100.0, [40.0], -35.0
    )

    frame = scene.area_frame()
    easts = [camera_centre_and_rotation(p, frame)[0][0] for p in poses]
    assert max(easts) <= scene.GROUND_HALF_EXTENT_M + 1e-6
    assert len(poses) == 6 * 4  # east offsets -70 and 0 only, three north offsets each


def test_the_render_from_the_photos_own_pose_ranks_first() -> None:
    truth = scene.pose_at(-20.0, -60.0, 0.0)
    photo = render(scene.town(), scene.pinhole(), truth, scene.MAX_RANGE_M).rgb
    others = [scene.pose_at(60.0, 40.0, 0.0), scene.pose_at(-20.0, -60.0, 180.0)]

    best = best_candidates(
        SearchConfig(top_k=1),
        photo,
        [others[0], truth, others[1]],
        lambda intrinsics, pose, max_range_m: render(scene.town(), intrinsics, pose, max_range_m),
        sift_match,
        scene.pinhole(),
        scene.MAX_RANGE_M,
    )

    assert best == [truth]
