import os
from pathlib import Path
from typing import override

import numpy as np
import pytest
import scene

from satmesh_eval.camera import camera_centre_and_rotation
from satmesh_eval.matching import onnx_matcher
from satmesh_eval.perspective import GroundExtent, render
from satmesh_locate.megaloc import DESCRIPTOR_SIZE, MegaLocDescriber
from satmesh_track.first_fix import (
    GridConfig,
    descriptor_cache_path,
    find_start,
    grid_descriptors,
    grid_poses,
)
from satmesh_track.tracker import PhotoImage, Scene, TrackConfig, TrackingContext

MEGALOC_VARIABLE, XFEAT_VARIABLE = "MEGALOC_MODEL", "XFEAT_MODEL_DIR"
SMALL_GRID = GridConfig(heights_above_ground_m=(50.0,), pitches_deg=(-35.0,), heading_count=4)
BOUNDS = GroundExtent(-70.0, 70.0, -70.0, 70.0)
START_TOLERANCE_M = (
    5.0  # acceptance criterion of the plan for a first fix; the lens graph refines it
)


class CountingDescriber(MegaLocDescriber):
    """Describes an image by its mean colour channels, repeated; counts the images it sees."""

    def __init__(self) -> None:
        self.seen = 0

    @override
    def describe(self, images):
        self.seen += len(images)
        rows = np.array(
            [
                np.resize(np.asarray(i, dtype=np.float32).mean(axis=(0, 1)), DESCRIPTOR_SIZE)
                for i in images
            ]
        )
        return rows / np.linalg.norm(rows, axis=1, keepdims=True)


def counting_scene() -> tuple[Scene, list[int]]:
    renders: list[int] = []

    def renderer(intrinsics, pose, max_range_m):
        renders.append(1)
        return render(scene.town(), intrinsics, pose, max_range_m)

    return Scene(renderer, scene.area_frame(), scene.ground_height), renders


def test_the_grid_has_every_position_height_pitch_and_heading_once() -> None:
    config = GridConfig(
        heights_above_ground_m=(25.0, 50.0), pitches_deg=(-25.0, -45.0), heading_count=4
    )

    poses = grid_poses(config, BOUNDS, scene.ground_height)

    # positions -70, 0, 70 on each axis
    assert len(poses) == 9 * 2 * 2 * 4
    assert len(
        {(p.east_m, p.north_m, p.height_above_ground_m, p.heading_deg, p.pitch_deg) for p in poses}
    ) == len(poses)


def test_positions_outside_the_scene_are_left_out_of_the_grid() -> None:
    wide = GroundExtent(-300.0, 300.0, -10.0, 10.0)

    poses = grid_poses(SMALL_GRID, wide, scene.ground_height)

    assert max(abs(p.east_m) for p in poses) <= scene.GROUND_HALF_EXTENT_M


def test_descriptors_are_built_once_and_then_read_from_the_cache(tmp_path: Path) -> None:
    grid = grid_poses(SMALL_GRID, GroundExtent(0.0, 70.0, 0.0, 0.0), scene.ground_height)
    model = tmp_path / "model.onnx"
    model.write_bytes(b"weights")
    cache = descriptor_cache_path(
        tmp_path, "town", SMALL_GRID, (scene.WIDTH_PX, scene.HEIGHT_PX), model
    )
    tracker_scene, renders = counting_scene()
    describer = CountingDescriber()
    arguments = (
        grid,
        tracker_scene,
        describer,
        (scene.WIDTH_PX, scene.HEIGHT_PX),
        200.0,
        cache,
        scene.MAX_RANGE_M,
    )

    first = grid_descriptors(*arguments)
    second = grid_descriptors(*arguments)

    assert len(renders) == len(grid) == describer.seen
    assert np.allclose(first, second, atol=1e-3)  # stored as float16


def test_the_cache_name_changes_with_the_grid_the_image_size_and_the_model(tmp_path: Path) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(b"weights")
    base = descriptor_cache_path(tmp_path, "town", SMALL_GRID, (320, 240), model)
    other_grid = GridConfig(spacing_m=50.0, heights_above_ground_m=(50.0,))
    model.write_bytes(b"other weights")

    assert descriptor_cache_path(tmp_path, "town", other_grid, (320, 240), model) != base
    assert descriptor_cache_path(tmp_path, "town", SMALL_GRID, (640, 480), model) != base
    assert descriptor_cache_path(tmp_path, "town", SMALL_GRID, (320, 240), model) != base


@pytest.mark.skipif(
    MEGALOC_VARIABLE not in os.environ or XFEAT_VARIABLE not in os.environ,
    reason=f"{MEGALOC_VARIABLE} and {XFEAT_VARIABLE} not set",
)
def test_the_first_photo_is_localised_from_the_grid_with_no_prior(tmp_path: Path) -> None:
    describer = MegaLocDescriber(Path(os.environ[MEGALOC_VARIABLE]))
    matcher = onnx_matcher(Path(os.environ[XFEAT_VARIABLE]))
    truth = scene.pose_at(-20.0, -60.0, 0.0)
    photo = PhotoImage("first.png", scene.photograph(truth))
    tracker_scene, _ = counting_scene()
    grid = grid_poses(SMALL_GRID, BOUNDS, scene.ground_height)
    cache = tmp_path / "cache.npz"
    descriptors = grid_descriptors(
        grid,
        tracker_scene,
        describer,
        (scene.WIDTH_PX, scene.HEIGHT_PX),
        220.0,
        cache,
        scene.MAX_RANGE_M,
    )

    start = find_start(
        photo,
        grid,
        descriptors,
        describer,
        TrackingContext(tracker_scene, matcher, TrackConfig()),
        5,
    )

    centre, _ = camera_centre_and_rotation(start, scene.area_frame())
    truth_centre, _ = camera_centre_and_rotation(truth, scene.area_frame())
    assert np.linalg.norm(centre - truth_centre) < START_TOLERANCE_M
