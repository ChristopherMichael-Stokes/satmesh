import json
import math
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path

import httpx
import mercantile
import pytest
from pydantic import ValidationError

from satmesh_data import (
    EsriClient,
    EsriSource,
    PlaceholderTileError,
    ZoomBeyondSourceError,
    choose_zoom,
)

PLACEHOLDER = (Path(__file__).parent / "data" / "esri-placeholder.bin").read_bytes()
REAL_TILE = b"\xff\xd8\xff\xe0 not a placeholder"
UPPER_AIRE_LON, UPPER_AIRE_LAT = -2.0015, 53.9236
UPPER_AIRE_TILE = mercantile.tile(UPPER_AIRE_LON, UPPER_AIRE_LAT, 19)


def citation(
    source: str, resolution: str, yyyymmdd: str, from_level: int, to_level: int
) -> dict[str, object]:
    """One layer 4 identify result as the live service returns it: every attribute a string."""
    return {
        "layerId": 4,
        "attributes": {
            "SOURCE_INFO": source,
            "RESOLUTION (M)": resolution,
            "DATE (YYYYMMDD)": yyyymmdd,
            "FROM_CACHE_LEVEL": str(from_level),
            "TO_CACHE_LEVEL": str(to_level),
            "DRAW_ORDER": "80",
        },
    }


# Live identify at Upper Aire, 2026-10-25, trimmed to the parsed fields plus one ignored field
UPPER_AIRE_IDENTIFY = {
    "results": [
        citation("TerraColor NextGen", "15", "Null", 0, 11),
        citation("Vivid", "0.34", "20250318", 12, 19),
    ]
}


def source(resolution_m: float, from_level: int, to_level: int) -> EsriSource:
    return EsriSource.model_validate(
        citation("test", str(resolution_m), "20250101", from_level, to_level)["attributes"]
    )


def web_mercator_gsd_m(zoom: int, lat: float) -> float:
    """Ground metres per pixel: 2 pi 6378137 m * cos(lat) / (256 * 2^zoom)."""
    return 2 * math.pi * 6378137 * math.cos(math.radians(lat)) / (256 << zoom)


class Server:
    """Records requests and answers each with the next queued response, or with `default`."""

    def __init__(self, default: Callable[[httpx.Request], httpx.Response]) -> None:
        self.requests: list[httpx.Request] = []
        self.queued: list[httpx.Response] = []
        self.default = default

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.queued.pop(0) if self.queued else self.default(request)


def client_for(server: Server, cache: Path, min_interval_s: float = 0.0) -> EsriClient:
    http = httpx.Client(transport=httpx.MockTransport(server))
    return EsriClient(http, cache, min_interval_s=min_interval_s, initial_backoff_s=0.0)


def tile_server(body: bytes) -> Server:
    return Server(lambda _: httpx.Response(200, content=body))


def test_identify_is_parsed_into_sources(tmp_path: Path) -> None:
    server = Server(lambda _: httpx.Response(200, json=UPPER_AIRE_IDENTIFY))
    terracolor, vivid = client_for(server, tmp_path).sources_at(UPPER_AIRE_LON, UPPER_AIRE_LAT)
    assert terracolor.capture_date is None
    assert (vivid.source_info, vivid.resolution_m, vivid.capture_date) == (
        "Vivid",
        0.34,
        date(2025, 3, 18),
    )
    assert (vivid.from_cache_level, vivid.to_cache_level) == (12, 19)
    assert server.requests[0].url.params["layers"] == "all:4"


def test_identify_error_body_is_rejected(tmp_path: Path) -> None:
    # ArcGIS reports errors as HTTP 200 with an error object
    error = {"error": {"code": 400, "message": "Invalid or missing input parameters."}}
    server = Server(lambda _: httpx.Response(200, content=json.dumps(error)))
    with pytest.raises(ValidationError):
        client_for(server, tmp_path).sources_at(UPPER_AIRE_LON, UPPER_AIRE_LAT)


def test_zoom_is_the_coarsest_reaching_source_resolution() -> None:
    sources = [EsriSource.model_validate(r["attributes"]) for r in UPPER_AIRE_IDENTIFY["results"]]
    zoom, chosen = choose_zoom(sources, UPPER_AIRE_LAT)
    assert chosen.source_info == "Vivid"
    assert (
        web_mercator_gsd_m(zoom, UPPER_AIRE_LAT)
        <= chosen.resolution_m
        < web_mercator_gsd_m(zoom - 1, UPPER_AIRE_LAT)
    )


def test_zoom_reaches_a_source_drawn_only_at_deep_levels() -> None:
    # Denver (S1): a 0.5 m source covers levels 12 to 19 and a 0.34 m source only level 20
    zoom, chosen = choose_zoom([source(0.5, 12, 19), source(0.34, 20, 20)], 39.74)
    assert (zoom, chosen.resolution_m) == (20, 0.34)


def test_zoom_is_capped_at_the_deepest_level() -> None:
    zoom, _ = choose_zoom([source(0.05, 12, 19)], 0.0)
    assert zoom == 19


def test_no_sources_is_an_error() -> None:
    with pytest.raises(ValueError, match="no imagery sources"):
        choose_zoom([], 0.0)


def test_cached_tile_needs_no_second_request(tmp_path: Path) -> None:
    server = tile_server(REAL_TILE)
    client = client_for(server, tmp_path)
    assert client.tile(UPPER_AIRE_TILE, max_zoom=19) == REAL_TILE
    assert client_for(server, tmp_path).tile(UPPER_AIRE_TILE, max_zoom=19) == REAL_TILE
    t = UPPER_AIRE_TILE
    assert [r.url.path for r in server.requests] == [
        f"/ArcGIS/rest/services/World_Imagery/MapServer/tile/{t.z}/{t.y}/{t.x}"
    ]


def test_placeholder_raises_and_is_not_cached(tmp_path: Path) -> None:
    server = tile_server(PLACEHOLDER)
    client = client_for(server, tmp_path)
    for _ in range(2):
        with pytest.raises(PlaceholderTileError):
            client.tile(UPPER_AIRE_TILE, max_zoom=19)
    assert len(server.requests) == 2
    assert not [p for p in tmp_path.rglob("*") if p.is_file()]


def test_zoom_past_the_source_makes_no_request(tmp_path: Path) -> None:
    server = tile_server(REAL_TILE)
    with pytest.raises(ZoomBeyondSourceError):
        client_for(server, tmp_path).tile(
            mercantile.tile(UPPER_AIRE_LON, UPPER_AIRE_LAT, 20), max_zoom=19
        )
    assert not server.requests


def test_server_error_is_retried(tmp_path: Path) -> None:
    server = tile_server(REAL_TILE)
    server.queued = [httpx.Response(503), httpx.Response(429)]
    assert client_for(server, tmp_path).tile(UPPER_AIRE_TILE, max_zoom=19) == REAL_TILE
    assert len(server.requests) == 3


def test_client_error_is_not_retried(tmp_path: Path) -> None:
    server = Server(lambda _: httpx.Response(404))
    with pytest.raises(httpx.HTTPStatusError):
        client_for(server, tmp_path).tile(UPPER_AIRE_TILE, max_zoom=19)
    assert len(server.requests) == 1


def test_requests_are_spaced_by_the_minimum_interval(tmp_path: Path) -> None:
    min_interval_s = 0.2
    server = tile_server(REAL_TILE)
    client = client_for(server, tmp_path, min_interval_s=min_interval_s)
    start = time.monotonic()
    for x_offset in range(3):
        client.tile(
            mercantile.Tile(UPPER_AIRE_TILE.x + x_offset, UPPER_AIRE_TILE.y, 19), max_zoom=19
        )
    assert time.monotonic() - start >= 2 * min_interval_s
