from pathlib import Path

import pytest
from pydantic import ValidationError

from satmesh_locate.events import (
    Bounds,
    Candidate,
    Candidates,
    Cell,
    CellBatch,
    Event,
    EventWriter,
    Fix,
    FusionFrame,
    FusionWindow,
    GridLevel,
    Interval,
    PositionPrior,
    PriorRelaxed,
    Priors,
    RunEnd,
    RunStart,
    StageEnd,
    StageStart,
    VerificationResult,
    VerificationStart,
    read_events,
)


def a_run() -> list[Event]:
    return [
        RunStart(
            time_s=0.0,
            origin_latitude_deg=50.86,
            origin_longitude_deg=0.45,
            bounds=Bounds(
                east_min_m=-1250.0, east_max_m=1250.0, north_min_m=-1250.0, north_max_m=1250.0
            ),
            priors=Priors(
                position=PositionPrior(east_m=0.0, north_m=0.0, radius_m=500.0),
                heading_deg=Interval(centre=30.0, half_width=45.0),
                pitch_deg=None,
                height_m=Interval(centre=100.0, half_width=20.0),
            ),
            photos=["f001.jpg"],
            levels=[GridLevel(level=1, spacing_m=280.0, positions=121, views=7260)],
        ),
        FusionWindow(
            time_s=0.5,
            frames=[
                FusionFrame(photo="f001.jpg", yaw_offset_deg=0.0, lattice_offset_deg=0.0),
                FusionFrame(photo="f003.jpg", yaw_offset_deg=14.2, lattice_offset_deg=0.0),
            ],
        ),
        StageStart(time_s=0.1, stage="level 1: render", units=7260),
        CellBatch(
            time_s=1.0,
            level=1,
            cells=[Cell(east_m=0.0, north_m=0.0, state="described", similarity=0.21)],
        ),
        StageEnd(time_s=2.0, stage="level 1: render"),
        Candidates(
            time_s=2.1,
            level=1,
            places=[
                Candidate(
                    rank=1,
                    east_m=0.0,
                    north_m=0.0,
                    height_m=90.0,
                    heading_deg=30.0,
                    pitch_deg=-35.0,
                    similarity=0.21,
                    frame_similarities=[0.1, None, 0.11],
                )
            ],
        ),
        VerificationStart(time_s=3.0, rank=1),
        VerificationResult(
            time_s=4.0, rank=1, inliers=388, frames_tracked=12, frames_total=12, accepted=True
        ),
        PriorRelaxed(time_s=4.1, prior="heading", half_width_before=45.0, half_width_after=90.0),
        Fix(
            time_s=4.2,
            east_m=1.0,
            north_m=2.0,
            height_m=60.0,
            heading_deg=28.0,
            pitch_deg=-25.0,
            inliers=388,
        ),
        RunEnd(time_s=4.3, ok=True),
    ]


def test_events_written_by_the_writer_are_read_back_equal(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    events = a_run()

    with EventWriter(path) as writer:
        for event in events:
            writer.write(event)

    assert list(read_events(path)) == events


def test_a_growing_file_is_readable_and_an_unfinished_last_line_waits(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    first, second = a_run()[:2]

    writer = EventWriter(path)
    writer.write(first)
    assert list(read_events(path)) == [first]

    with path.open("a", encoding="utf-8") as raw:
        raw.write(second.model_dump_json()[:20])
    assert list(read_events(path)) == [first]

    writer.close()


def test_a_misspelt_field_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(
        '{"kind": "run_end", "time_s": 1.0, "ok": true, "okay": true}\n', encoding="utf-8"
    )

    with pytest.raises(ValidationError):
        list(read_events(path))


def test_another_schema_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    start = a_run()[0].model_dump_json().replace('"schema_version":1', '"schema_version":2')
    path.write_text(start + "\n", encoding="utf-8")

    with pytest.raises(ValidationError):
        list(read_events(path))
