import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from satmesh_core import BRITISH_NATIONAL_GRID, WGS84, Aoi
from satmesh_data import AerialTile, crop_aerial, fetch_aerial_ecws, find_aerial_tiles

SEARCH_BODY = {
    "count": 3,
    "results": [
        {
            "product": {"id": "lidar_composite_dtm"},
            "year": {"id": "2022"},
            "resolution": {"id": "1"},
            "tile": {"id": "SD9545"},
            "uri": "https://example.test/lidar",
        },
        {
            "product": {"id": "vertical_aerial_photography_tiles_rgb"},
            "year": {"id": "2008"},
            "resolution": {"id": "0.4"},
            "tile": {"id": "SD9545"},
            "uri": "https://example.test/rgb2008",
        },
        {
            "product": {"id": "vertical_aerial_photography_tiles_rgbn"},
            "year": {"id": "2020"},
            "resolution": {"id": "0.1"},
            "tile": {"id": "SD9545"},
            "uri": "https://example.test/rgbn2020",
        },
    ],
}
TILE = AerialTile(
    product="vertical_aerial_photography_tiles_rgbn",
    year=2020,
    resolution_m=0.1,
    tile_id="SD9545",
    uri="https://example.test/rgbn2020",
)


def zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def serving(body: bytes, requests: list[httpx.Request]) -> httpx.Client:
    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=body)

    return httpx.Client(transport=httpx.MockTransport(handle))


def test_search_posts_geojson_and_keeps_only_aerial_products_newest_first() -> None:
    requests: list[httpx.Request] = []
    http = serving(json.dumps(SEARCH_BODY).encode(), requests)
    tiles = find_aerial_tiles(http, (-2.01, 53.92, -1.99, 53.93), initial_backoff_s=0.0)
    assert [(t.year, t.resolution_m) for t in tiles] == [(2020, 0.1), (2008, 0.4)]
    (request,) = requests
    assert request.headers["content-type"] == "application/geo+json"
    ring = json.loads(request.content)["coordinates"][0]
    assert ring[0] == ring[-1] == [-2.01, 53.92]
    assert [-1.99, 53.93] in ring


def test_zip_is_unpacked_to_flat_ecw_names_cached_and_deleted(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    body = zip_bytes({"a.ecw": b"A", "../../escape.ecw": b"B", "notes.txt": b"x"})
    http = serving(body, requests)
    ecws = fetch_aerial_ecws(http, TILE, tmp_path, initial_backoff_s=0.0)
    assert [p.name for p in ecws] == ["a.ecw", "escape.ecw"]
    assert ecws[0].read_bytes() == b"A"
    assert not list(tmp_path.rglob("*.zip*"))
    assert not (tmp_path.parent / "escape.ecw").exists()
    assert fetch_aerial_ecws(http, TILE, tmp_path, initial_backoff_s=0.0) == ecws
    assert len(requests) == 1


def test_download_past_the_cap_raises_and_leaves_nothing(tmp_path: Path) -> None:
    http = serving(zip_bytes({"a.ecw": b"x" * 5000}), [])
    with pytest.raises(ValueError, match="byte download cap"):
        fetch_aerial_ecws(http, TILE, tmp_path, max_bytes=100, initial_backoff_s=0.0)
    assert not [p for p in tmp_path.rglob("*") if p.is_file()]


def test_crop_needs_a_bng_box(tmp_path: Path) -> None:
    box = Aoi(crs=WGS84, west=-2.0, south=53.9, east=-1.99, north=53.91)
    with pytest.raises(ValueError, match=BRITISH_NATIONAL_GRID):
        crop_aerial((), box, tmp_path / "out.tif", tmp_path)
