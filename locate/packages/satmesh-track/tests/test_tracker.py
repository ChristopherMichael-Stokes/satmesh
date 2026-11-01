import os
from pathlib import Path

import numpy as np
import pytest
import scene

from satmesh_eval.camera import camera_centre_and_rotation
from satmesh_eval.matching import onnx_matcher, sift_match
from satmesh_eval.perspective import render
from satmesh_track.search import SearchConfig
from satmesh_track.tracker import (
    PhotoImage,
    PhotoStatus,
    Scene,
    TrackConfig,
    TrackingContext,
    track,
)

STEP_M = 10.0
FLIGHT_START = (-40.0, -100.0)
PHOTO_COUNT = 8
MODEL_DIR_VARIABLE = "XFEAT_MODEL_DIR"
FOCAL_TOLERANCE = 0.02  # acceptance criterion of the plan: focal length within 2 %
POSITION_TOLERANCE_M = 1.0  # acceptance criterion of the plan: poses within 1 m
RECOVERY_TOLERANCE_M = 2.0  # the gap test finds the track again; the flight test asserts accuracy


def tracker_scene() -> Scene:
    def renderer(intrinsics, pose, max_range_m):
        return render(scene.town(), intrinsics, pose, max_range_m)

    return Scene(renderer, scene.area_frame(), scene.ground_height)


def flight_poses(count: int):
    return [scene.pose_at(FLIGHT_START[0], FLIGHT_START[1] + STEP_M * i, 0.0) for i in range(count)]


def test_a_flight_is_tracked_and_the_lens_is_recovered() -> None:
    poses = flight_poses(PHOTO_COUNT)
    photos = [PhotoImage(f"{i}.png", scene.photograph(pose)) for i, pose in enumerate(poses)]
    start = poses[0]  # a first fix; the offset of the search that provides it is tested elsewhere

    result = track(photos, start, TrackingContext(tracker_scene(), sift_match))

    assert [p.status for p in result.photos] == [PhotoStatus.TRACKED] * PHOTO_COUNT
    assert result.lens.lens.focal_px == pytest.approx(scene.TRUE_LENS.focal_px, rel=FOCAL_TOLERANCE)
    for tracked, pose in zip(result.photos, poses, strict=True):
        centre, _ = camera_centre_and_rotation(pose, scene.area_frame())
        assert tracked.pose is not None
        assert np.linalg.norm(tracked.pose.centre_enu - centre) < POSITION_TOLERANCE_M


def test_isolated_unusable_photos_do_not_add_up_to_a_failed_track() -> None:
    poses = flight_poses(PHOTO_COUNT)
    unusable = {2, 5}
    photos = [
        PhotoImage(
            f"{i}.png",
            np.full_like(scene.photograph(pose), 128) if i in unusable else scene.photograph(pose),
        )
        for i, pose in enumerate(poses)
    ]
    cheap_search = SearchConfig(heading_count=1, height_factors=(1.0,))
    config = TrackConfig(search=cheap_search, max_failed_searches=len(unusable))

    result = track(photos, poses[0], TrackingContext(tracker_scene(), sift_match, config))

    statuses = [p.status for p in result.photos]
    assert [i for i, status in enumerate(statuses) if status is PhotoStatus.LOST] == sorted(
        unusable
    )
    assert statuses.count(PhotoStatus.TRACKED) == PHOTO_COUNT - len(unusable)


@pytest.mark.skipif(MODEL_DIR_VARIABLE not in os.environ, reason=f"{MODEL_DIR_VARIABLE} not set")
def test_a_turn_inside_a_gap_is_recovered_by_the_local_search() -> None:
    # SIFT's basin on this small scene is under 25 m, so the search grid would be too fine to test
    matcher = onnx_matcher(Path(os.environ[MODEL_DIR_VARIABLE]))
    # north for four photos, then east; photos 4 to 6 are missing, so constant velocity predicts
    # (-40, 40) while the camera is at (40, -40): 113 m off, outside the 50 m basin
    path = [(-40.0, -100.0 + 20.0 * i, 0.0) for i in range(4)] + [
        (-20.0 + 20.0 * i, -40.0, 90.0) for i in range(3, 6)
    ]
    steps = [0, 1, 2, 3, 7, 8, 9]
    poses = [scene.pose_at(*p) for p in path]
    photos = [
        PhotoImage(f"{step}.png", scene.photograph(pose), step)
        for step, pose in zip(steps, poses, strict=True)
    ]
    config = TrackConfig(search=SearchConfig(heading_count=4, height_factors=(1.0,), top_k=3))

    result = track(photos, poses[0], TrackingContext(tracker_scene(), matcher, config))

    assert [e.recovered for e in result.searches] == [True]
    assert [p.status for p in result.photos][4] == PhotoStatus.RELOCALISED
    assert all(p.status != PhotoStatus.LOST for p in result.photos)
    for tracked, pose in zip(result.photos, poses, strict=True):
        centre, _ = camera_centre_and_rotation(pose, scene.area_frame())
        assert tracked.pose is not None
        assert np.linalg.norm(tracked.pose.centre_enu - centre) < RECOVERY_TOLERANCE_M
