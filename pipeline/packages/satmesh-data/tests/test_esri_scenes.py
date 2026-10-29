import copy
import json
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import numpy as np
import pytest
from affine import Affine

from satmesh_core import BRITISH_NATIONAL_GRID, Aoi
from satmesh_data import (
    UNLABELLED,
    EsriClient,
    EsriQueryError,
    SceneId,
    SceneMap,
    fetch_scene_map,
)

DATA = Path(__file__).parent / "data"


def bng_box(west: float, south: float, east: float, north: float) -> Aoi:
    return Aoi(crs=BRITISH_NATIONAL_GRID, west=west, south=south, east=east, north=north)


# Live layer 4 envelope queries of 2026-10-29 (Southend 1 km box at z19, Ferrybridge lidar tile
# SE4520 at z18), clipped to the box plus 100 m so the outlines inside the box are as served
SOUTHEND = json.loads((DATA / "esri-scenes-southend-z19.json").read_text())
FERRYBRIDGE = json.loads((DATA / "esri-scenes-ferrybridge-z18.json").read_text())
SOUTHEND_BOX = bng_box(587000, 185000, 588000, 186000)
FERRYBRIDGE_BOX = Aoi(
    crs=BRITISH_NATIONAL_GRID, west=445000, south=420000, east=450000, north=425000
)
# lean2 town box: labelled wholly 20250716 LG01 by rasterising the unclipped z19 footprints
FERRYBRIDGE_TOWN = Aoi(
    crs=BRITISH_NATIONAL_GRID, west=448500, south=423500, east=449500, north=424500
)


class Layer4:
    """Answers geometry-free queries with the release of `features` and others with `pages`."""

    def __init__(self, features: list[dict[str, Any]], page_size: int | None = None) -> None:
        self.features = features
        self.page_size = page_size or len(features)
        self.requests: list[dict[str, list[str]]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        query = parse_qs(request.url.query.decode())
        self.requests.append(query)
        offset = int(query["resultOffset"][0])
        if query["returnGeometry"] == ["false"]:
            page = [
                {"attributes": {k: f["attributes"][k] for k in ("OBJECTID", "ReleaseName")}}
                for f in self.features
            ]
            return httpx.Response(200, json={"features": page})
        page = self.features[offset : offset + self.page_size]
        body: dict[str, Any] = {"features": page}
        if offset + self.page_size < len(self.features):
            body["exceededTransferLimit"] = True
        return httpx.Response(200, json=body)


def client(server: Layer4 | httpx.MockTransport, tmp_path: Path) -> EsriClient:
    transport = server if isinstance(server, httpx.MockTransport) else httpx.MockTransport(server)
    return EsriClient(httpx.Client(transport=transport), tmp_path, min_interval_s=0.0)


def bng_map(features: list[dict[str, Any]], box: Aoi, zoom: int, tmp_path: Path) -> SceneMap:
    return fetch_scene_map(client(Layer4(features), tmp_path), box, zoom, tmp_path).in_crs(
        BRITISH_NATIONAL_GRID
    )


def square(west: float, south: float, side: float) -> list[list[float]]:
    return [
        [west, south],
        [west, south + side],
        [west + side, south + side],
        [west + side, south],
        [west, south],
    ]


def feature(
    object_id: int, rings: list[list[list[float]]], yyyymmdd: int = 20250101
) -> dict[str, Any]:
    return {
        "attributes": {
            "OBJECTID": object_id,
            "SRC_DATE": yyyymmdd,
            "SRC_RES": 0.5,
            "SRC_ACC": 8.5,
            "SRC_DESC": "WV02",
            "MinMapLevel": 12,
            "MaxMapLevel": 19,
            "ReleaseName": "Raster Basemaps 2026.R01",
        },
        "geometry": {"rings": rings},
    }


def test_polygons_sharing_a_date_and_sensor_form_one_scene(tmp_path: Path) -> None:
    scenes = bng_map(FERRYBRIDGE["features"], FERRYBRIDGE_BOX, 18, tmp_path).scenes

    # read off the fixture's SRC_DATE and SRC_DESC by hand
    expected = {
        SceneId(capture_date=date(2025, 4, 29), sensor="WV02"): {4146032},
        SceneId(capture_date=date(2025, 7, 16), sensor="LG01"): {4146033, 4205965, 4205968},
        SceneId(capture_date=date(2022, 7, 16), sensor="WV02"): {
            4205895,
            4205898,
            4205904,
            4205911,
            4205912,
            4205916,
        },
        SceneId(capture_date=date(2025, 6, 30), sensor="LG02"): {4205962, 4205963},
    }
    assert {s.scene_id: set(s.object_ids) for s in scenes} == expected


def test_footprints_of_one_zoom_tile_the_area_without_overlap(tmp_path: Path) -> None:
    shares = bng_map(FERRYBRIDGE["features"], FERRYBRIDGE_BOX, 18, tmp_path).shares(FERRYBRIDGE_BOX)

    # disjoint footprints covering the box; 1e-6 is the float noise of the polygon overlaps
    assert sum(shares.values()) == pytest.approx(1.0, abs=1e-6)
    assert list(shares.values()) == sorted(shares.values(), reverse=True)


def test_known_boxes_get_the_scenes_lean2_rasterised(tmp_path: Path) -> None:
    ferrybridge = bng_map(FERRYBRIDGE["features"], FERRYBRIDGE_BOX, 18, tmp_path / "f")
    southend = bng_map(SOUTHEND["features"], SOUTHEND_BOX, 19, tmp_path / "s")

    lg01 = SceneId(capture_date=date(2025, 7, 16), sensor="LG01")
    ge01 = SceneId(capture_date=date(2025, 7, 12), sensor="GE01")
    assert ferrybridge.shares(FERRYBRIDGE_TOWN)[lg01] == pytest.approx(1.0, abs=1e-6)
    # two polygons with lean2 shares 0.437365 and 0.562635 of the box: one scene
    assert southend.shares(SOUTHEND_BOX) == pytest.approx({ge01: 1.0}, abs=1e-6)


def test_grid_labels_agree_with_point_labels_at_pixel_centres(tmp_path: Path) -> None:
    scene_map = bng_map(FERRYBRIDGE["features"], FERRYBRIDGE_BOX, 18, tmp_path)
    pixel_m = 50.0
    side = round((FERRYBRIDGE_BOX.east - FERRYBRIDGE_BOX.west) / pixel_m)
    transform = Affine(pixel_m, 0, FERRYBRIDGE_BOX.west, 0, -pixel_m, FERRYBRIDGE_BOX.north)

    grid = scene_map.label_grid(transform, (side, side))
    centres = (np.arange(side) + 0.5) * pixel_m
    x, y = np.meshgrid(FERRYBRIDGE_BOX.west + centres, FERRYBRIDGE_BOX.north - centres)
    points = scene_map.labels_at(x, y)

    # a pixel centre within float noise of a seam may fall either side
    assert (grid == points).mean() > 0.995
    assert len(np.unique(points)) == len(scene_map.scenes)


def test_holes_and_islands_follow_even_odd_fill(tmp_path: Path) -> None:
    outer, hole, island = (
        square(0.0, 50.0, 0.01),
        square(0.002, 50.002, 0.006),
        square(0.004, 50.004, 0.002),
    )
    box = Aoi(crs="EPSG:4326", west=0.0, south=50.0, east=0.01, north=50.01)
    scene_map = fetch_scene_map(
        client(Layer4([feature(1, [outer, hole, island])]), tmp_path), box, 19, tmp_path
    )

    labels = scene_map.labels_at(np.array([0.001, 0.003, 0.005, 0.02]), np.full(4, 50.005))

    assert labels.tolist() == [0, UNLABELLED, 0, UNLABELLED]


def test_footprints_are_cached_per_release(tmp_path: Path) -> None:
    features = copy.deepcopy(SOUTHEND["features"])
    server = Layer4(features)
    esri = client(server, tmp_path)

    first = fetch_scene_map(esri, SOUTHEND_BOX, 19, tmp_path)
    second = fetch_scene_map(esri, SOUTHEND_BOX, 19, tmp_path)
    for f in features:
        f["attributes"]["ReleaseName"] = "Raster Basemaps 2026.R02"
    third = fetch_scene_map(esri, SOUTHEND_BOX, 19, tmp_path)

    geometry_requests = [q["returnGeometry"] for q in server.requests]
    assert geometry_requests == [["false"], ["true"], ["false"], ["false"], ["true"]]
    assert first == second
    assert (first.release, third.release) == (
        "Raster Basemaps 2026.R01",
        "Raster Basemaps 2026.R02",
    )


def test_query_names_the_zoom_envelope_and_generalisation(tmp_path: Path) -> None:
    server = Layer4(SOUTHEND["features"])
    fetch_scene_map(client(server, tmp_path), SOUTHEND_BOX, 19, tmp_path)

    query = server.requests[-1]
    west, south, east, north = SOUTHEND_BOX.wgs84_bounds()
    assert query["where"] == ["MinMapLevel<=19 AND MaxMapLevel>=19"]
    assert [float(v) for v in query["geometry"][0].split(",")] == pytest.approx(
        [west, south, east, north]
    )
    assert query["geometryType"] == ["esriGeometryEnvelope"]
    assert (query["inSR"], query["outSR"]) == (["4326"], ["4326"])
    assert float(query["maxAllowableOffset"][0]) == pytest.approx(1e-5)


def test_pages_are_followed_until_the_transfer_limit_clears(tmp_path: Path) -> None:
    server = Layer4(FERRYBRIDGE["features"], page_size=5)
    scene_map = fetch_scene_map(client(server, tmp_path), FERRYBRIDGE_BOX, 18, tmp_path)

    offsets = [q["resultOffset"] for q in server.requests if q["returnGeometry"] == ["true"]]
    assert offsets == [["0"], ["5"], ["10"]]
    assert sum(len(s.object_ids) for s in scene_map.scenes) == len(FERRYBRIDGE["features"])


def test_an_error_body_with_status_200_raises(tmp_path: Path) -> None:
    error = {"error": {"code": 400, "message": "Failed to execute query.", "details": []}}
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=error))

    with pytest.raises(EsriQueryError, match="Failed to execute query"):
        fetch_scene_map(client(transport, tmp_path), SOUTHEND_BOX, 19, tmp_path)
