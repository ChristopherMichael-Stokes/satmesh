import json
from pathlib import Path

import numpy as np
import pytest
import scene

from satmesh_eval.camera import camera_centre_and_rotation
from satmesh_eval.poses import read_pose_file
from satmesh_track.lens import CameraPoseEnu, Lens, LensEstimate
from satmesh_track.outputs import (
    CALIBRATION_FILE,
    POSES_FILE,
    REPORT_FILE,
    REVIEW_FILE,
    horizontal_fov_deg,
    write_outputs,
)
from satmesh_track.photos import LoadedPhoto
from satmesh_track.tracker import PhotoImage, PhotoStatus, SearchEvent, TrackedPhoto, TrackResult

ORIGINAL_W, ORIGINAL_H = 1280, 960
WORKING_W, WORKING_H = 640, 480
WORKING_FOCAL_PX = 450.0
POSE_TOLERANCE_M = 1e-3  # geodetic round trip of a pose a few hundred metres from the origin


def loaded(name: str) -> LoadedPhoto:
    rgb = np.zeros((WORKING_H, WORKING_W, 3), dtype=np.uint8)
    return LoadedPhoto(PhotoImage(name, rgb), ORIGINAL_W, ORIGINAL_H)


def tracked(name: str, status: PhotoStatus, east: float | None) -> TrackedPhoto:
    pose = None
    if east is not None:
        # a camera 40 m up looking north, pitched 35 degrees down: columns right, down, forward
        pitch = np.radians(35)
        right, forward = np.array([1.0, 0.0, 0.0]), np.array([0.0, np.cos(pitch), -np.sin(pitch)])
        rotation = np.column_stack([right, np.cross(forward, right), forward])
        pose = CameraPoseEnu(np.array([east, -50.0, 40.0]), rotation)
    return TrackedPhoto(
        name, status, pose, 400 if pose is not None else 0, 1.5 if pose is not None else None
    )


def result_for(focal_px: float = WORKING_FOCAL_PX) -> TrackResult:
    lens = Lens(focal_px, -0.1, 0.02, WORKING_W, WORKING_H)
    covariance = np.diag([4.0, 1e-4, 1e-4])
    photos = (
        tracked("a.png", PhotoStatus.TRACKED, -10.0),
        tracked("b.png", PhotoStatus.RELOCALISED, 10.0),
        tracked("c.png", PhotoStatus.REJECTED, 30.0),
        tracked("d.png", PhotoStatus.LOST, None),
    )
    return TrackResult(
        LensEstimate(lens, covariance), photos, (SearchEvent("b.png", 100.0, 40, recovered=True),)
    )


def test_the_pose_file_reads_back_with_the_original_size_lens(tmp_path: Path) -> None:
    result = result_for()
    photos = [loaded(p.name) for p in result.photos]

    write_outputs(tmp_path, result, photos, scene.area_frame())

    records = read_pose_file(tmp_path / POSES_FILE)
    assert [r.photo for r in records] == ["a.png", "b.png"]  # rejected and lost photos have no pose
    intrinsics = records[0].intrinsics.to_intrinsics()
    assert intrinsics.focal_x_px == pytest.approx(2 * WORKING_FOCAL_PX)
    assert (intrinsics.width_px, intrinsics.height_px) == (ORIGINAL_W, ORIGINAL_H)
    assert intrinsics.radial_distortion == (-0.1, 0.02)
    centre, _ = camera_centre_and_rotation(records[1].to_pose(), scene.area_frame())
    assert np.allclose(centre, [10.0, -50.0, 40.0], atol=POSE_TOLERANCE_M)


def test_the_calibration_scales_the_focal_length_and_its_uncertainty(tmp_path: Path) -> None:
    result = result_for()

    write_outputs(tmp_path, result, [loaded(p.name) for p in result.photos], scene.area_frame())

    calibration = json.loads((tmp_path / CALIBRATION_FILE).read_text())
    assert calibration["focal_px"] == pytest.approx(900.0)
    assert calibration["focal_sigma_px"] == pytest.approx(
        4.0
    )  # sqrt(4) = 2 working pixels, times 2
    assert calibration["covariance_focal_k1_k2"][1][1] == pytest.approx(1e-4)
    assert calibration["horizontal_fov_deg"] == pytest.approx(
        horizontal_fov_deg(Lens(900.0, 0, 0, ORIGINAL_W, ORIGINAL_H))
    )
    assert calibration["warnings"] == []


def test_a_field_of_view_beyond_110_degrees_is_warned_about(tmp_path: Path) -> None:
    result = result_for(focal_px=150.0)  # 2 atan(640 / 300) = 129 degrees on the original width

    write_outputs(tmp_path, result, [loaded(p.name) for p in result.photos], scene.area_frame())

    calibration = json.loads((tmp_path / CALIBRATION_FILE).read_text())
    assert "fisheye" in calibration["warnings"][0]


def test_the_report_lists_every_photo_and_the_review_page_embeds_the_run(tmp_path: Path) -> None:
    result = result_for()

    write_outputs(tmp_path, result, [loaded(p.name) for p in result.photos], scene.area_frame())

    report = json.loads((tmp_path / REPORT_FILE).read_text())
    assert [p["status"] for p in report["photos"]] == ["tracked", "relocalised", "rejected", "lost"]
    assert report["searches"][0]["photo"] == "b.png"
    page = (tmp_path / REVIEW_FILE).read_text()
    data = json.loads(page.split("const D=", 1)[1].split(";\nconst $", 1)[0])
    assert [p["name"] for p in data["photos"]] == ["a.png", "b.png", "c.png", "d.png"]
    assert data["photos"][3]["east"] is None
    assert page.count("</script>") == 1
