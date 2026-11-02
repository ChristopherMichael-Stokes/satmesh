from pathlib import Path

import pytest
from starlette.testclient import TestClient

from satmesh_locate.events import (
    EVENTS_FILE,
    Bounds,
    Event,
    EventWriter,
    GridLevel,
    Priors,
    RunEnd,
    RunStart,
    StageEnd,
    StageStart,
)
from satmesh_monitor.app import create_app
from satmesh_monitor.mercator import Tile
from satmesh_monitor.tiles import tile_path

JPEG_MAGIC = b"\xff\xd8\xff"


def run_start(photos: list[str]) -> RunStart:
    return RunStart(
        time_s=0.0,
        origin_latitude_deg=50.86,
        origin_longitude_deg=0.45,
        bounds=Bounds(east_min_m=-100.0, east_max_m=100.0, north_min_m=-100.0, north_max_m=100.0),
        priors=Priors(position=None, heading_deg=None, pitch_deg=None, height_m=None),
        photos=photos,
        levels=[GridLevel(level=1, spacing_m=280.0, positions=1, views=60)],
    )


def client_for(tmp_path: Path, photos: Path | None = None) -> TestClient:
    return TestClient(
        create_app(tmp_path / "run", tmp_path / "imagery", tmp_path / "assembled", photos)
    )


def write_run(tmp_path: Path, events: list[Event]) -> EventWriter:
    run = tmp_path / "run"
    run.mkdir(exist_ok=True)
    writer = EventWriter(run / EVENTS_FILE)
    for event in events:
        writer.write(event)
    return writer


def test_an_unknown_run_directory_is_refused(tmp_path: Path) -> None:
    with pytest.raises(NotADirectoryError):
        client_for(tmp_path)


def test_a_run_directory_without_events_yet_has_none(tmp_path: Path) -> None:
    (tmp_path / "run").mkdir()

    body = client_for(tmp_path).get("/api/events").json()

    assert body == {"events": [], "total": 0, "finished": False, "has_photos": False}


def test_a_finished_run_is_listed_whole_and_marked_finished(tmp_path: Path) -> None:
    write_run(
        tmp_path,
        [run_start([]), StageStart(time_s=1.0, stage="a", units=3), RunEnd(time_s=2.0, ok=True)],
    ).close()

    body = client_for(tmp_path).get("/api/events").json()

    assert [event["kind"] for event in body["events"]] == ["run_start", "stage_start", "run_end"]
    assert body["total"] == 3
    assert body["finished"] is True


def test_a_growing_file_is_followed_with_after(tmp_path: Path) -> None:
    writer = write_run(tmp_path, [run_start([]), StageStart(time_s=1.0, stage="a", units=3)])
    client = client_for(tmp_path)

    first = client.get("/api/events", params={"after": 0}).json()
    writer.write(StageEnd(time_s=2.0, stage="a"))
    second = client.get("/api/events", params={"after": first["total"]}).json()
    writer.write(RunEnd(time_s=3.0, ok=False))
    third = client.get("/api/events", params={"after": second["total"]}).json()
    writer.close()

    assert (first["total"], first["finished"]) == (2, False)
    assert [event["kind"] for event in second["events"]] == ["stage_end"]
    assert (second["total"], second["finished"]) == (3, False)
    assert [event["kind"] for event in third["events"]] == ["run_end"]
    assert (third["total"], third["finished"]) == (4, True)


def test_an_unfinished_last_line_is_left_for_the_next_call(tmp_path: Path) -> None:
    writer = write_run(tmp_path, [run_start([])])
    with (tmp_path / "run" / EVENTS_FILE).open("a", encoding="utf-8") as raw:
        raw.write(StageEnd(time_s=2.0, stage="a").model_dump_json()[:15])
    client = client_for(tmp_path)

    assert client.get("/api/events").json()["total"] == 1

    with (tmp_path / "run" / EVENTS_FILE).open("a", encoding="utf-8") as raw:
        raw.write(StageEnd(time_s=2.0, stage="a").model_dump_json()[15:] + "\n")
    writer.close()
    assert client.get("/api/events").json()["total"] == 2


def test_a_cached_tile_is_served_and_an_absent_one_is_404(tmp_path: Path) -> None:
    (tmp_path / "run").mkdir()
    path = tile_path(tmp_path / "imagery", Tile(18, 5, 6))
    path.parent.mkdir(parents=True)
    path.write_bytes(JPEG_MAGIC + b"tile")
    client = client_for(tmp_path)

    hit = client.get("/tiles/18/5/6.jpg")
    miss = client.get("/tiles/18/5/7.jpg")

    assert hit.status_code == 200
    assert hit.headers["content-type"] == "image/jpeg"
    assert hit.content == JPEG_MAGIC + b"tile"
    assert miss.status_code == 404


def test_only_photos_the_run_declared_are_served(tmp_path: Path) -> None:
    photos = tmp_path / "photos"
    photos.mkdir()
    (photos / "f001.jpg").write_bytes(b"photo")
    (tmp_path / "secret.txt").write_bytes(b"secret")
    (photos / "other.jpg").write_bytes(b"undeclared")
    write_run(tmp_path, [run_start(["f001.jpg"])]).close()
    client = client_for(tmp_path, photos)

    assert client.get("/api/photo/f001.jpg").content == b"photo"
    assert client.get("/api/photo/other.jpg").status_code == 404
    assert client.get("/api/photo/..%2Fsecret.txt").status_code == 404
    assert client.get("/api/photo/../secret.txt").status_code == 404


def test_photos_are_not_served_without_a_photos_directory(tmp_path: Path) -> None:
    write_run(tmp_path, [run_start(["f001.jpg"])]).close()

    assert client_for(tmp_path).get("/api/photo/f001.jpg").status_code == 404


def test_the_page_and_its_scripts_are_revalidated_on_every_load(tmp_path: Path) -> None:
    (tmp_path / "run").mkdir()
    client = client_for(tmp_path)

    assert client.get("/").headers["Cache-Control"] == "no-cache"
    assert client.get("/static/main.js").headers["Cache-Control"] == "no-cache"
