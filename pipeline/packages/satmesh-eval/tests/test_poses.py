import json
from pathlib import Path

import pytest

from satmesh_eval.camera import CameraPose, Intrinsics
from satmesh_eval.poses import read_pose_file

INTRINSICS = {
    "width_px": 1280,
    "height_px": 960,
    "focal_x_px": 915.0,
    "focal_y_px": 915.0,
    "principal_x_px": 640.0,
    "principal_y_px": 480.0,
    "radial_distortion": [-0.12, 0.03],
}
LINE = {
    "photo": "a.jpg",
    "latitude_deg": 53.72,
    "longitude_deg": -1.27,
    "ellipsoidal_height_m": 82.5,
    "heading_deg": 90.0,
    "pitch_deg": -20.0,
    "roll_deg": 1.5,
    "intrinsics": INTRINSICS,
}


def write(tmp_path: Path, *lines: object) -> Path:
    path = tmp_path / "poses.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
    return path


def test_a_line_reads_as_the_camera_modules_types(tmp_path: Path) -> None:
    prior = {k: v for k, v in LINE.items() if k not in ("photo", "intrinsics")} | {
        "heading_deg": 93.0
    }

    first, second = read_pose_file(write(tmp_path, LINE, LINE | {"photo": "b.jpg", "prior": prior}))

    assert first.to_pose() == CameraPose(53.72, -1.27, 82.5, 90.0, -20.0, 1.5)
    assert first.intrinsics.to_intrinsics() == Intrinsics(
        1280, 960, 915.0, 915.0, 640.0, 480.0, (-0.12, 0.03)
    )
    assert first.prior is None
    assert second.prior is not None
    assert second.prior.to_pose().heading_deg == 93.0


def test_blank_lines_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "poses.jsonl"
    path.write_text("\n" + json.dumps(LINE) + "\n\n")

    assert len(read_pose_file(path)) == 1


@pytest.mark.parametrize(
    ("line", "fragment"),
    [
        (LINE | {"latitude_deg": 95.0}, "latitude_deg"),
        (LINE | {"extra": 1}, "extra"),
        ({k: v for k, v in LINE.items() if k != "roll_deg"}, "roll_deg"),
        (LINE | {"intrinsics": INTRINSICS | {"focal_x_px": 0.0}}, "focal_x_px"),
    ],
)
def test_a_bad_line_is_reported_with_its_line_number_and_field(
    tmp_path: Path, line: dict[str, object], fragment: str
) -> None:
    path = write(tmp_path, LINE, line)

    with pytest.raises(ValueError, match=rf"(?s)poses\.jsonl:2: .*{fragment}"):
        read_pose_file(path)


def test_a_photo_named_twice_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"more than once: a\.jpg"):
        read_pose_file(write(tmp_path, LINE, LINE))


def test_a_file_without_records_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "poses.jsonl"
    path.write_text("\n")

    with pytest.raises(ValueError, match="no records"):
        read_pose_file(path)
