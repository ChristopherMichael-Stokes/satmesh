import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from satmesh_core import BRITISH_NATIONAL_GRID, Aoi
from satmesh_data import (
    PointCloudTile,
    fetch_point_cloud,
    find_point_cloud_tiles,
    os_tile_id,
    tile_ids_covering,
)

# OS National Grid references worked out by hand from the 100 km lettering (SD = 300-400 km east,
# 400-500 km north) and the portal's own tile names for the surveyed sites
KNOWN_SQUARES = [
    ((399_500, 447_500), "SD9545"),
    ((400_500, 447_500), "SE0045"),
    ((448_500, 424_500), "SE4520"),
    ((299_500, 143_500), "SS9540"),
    ((587_500, 185_500), "TQ8585"),
    ((408_500, 641_500), "NU0540"),
    ((562_500, 328_500), "TF6025"),
    ((454_500, 319_500), "SK5015"),
    ((328_500, 376_500), "SJ2575"),
]


def listing(*entries: tuple[str, str, str]) -> bytes:
    return json.dumps(
        {
            "results": [
                {
                    "product": {"id": product},
                    "year": {"id": year},
                    "resolution": {"id": "1"},
                    "tile": {"id": tile},
                    "uri": f"https://example.test/{product}/{year}/{tile}",
                }
                for product, year, tile in entries
            ]
        }
    ).encode()


def zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


@pytest.mark.parametrize(("point", "square"), KNOWN_SQUARES)
def test_os_tile_id_matches_the_portal_names(point: tuple[float, float], square: str) -> None:
    assert os_tile_id(*point) == square


def test_a_box_across_a_square_edge_needs_both_squares() -> None:
    box = Aoi(crs=BRITISH_NATIONAL_GRID, west=399_500, south=447_000, east=400_500, north=448_000)
    assert tile_ids_covering(box) == ("SD9545", "SE0045")


def test_search_keeps_covering_squares_and_orders_national_programme_first() -> None:
    body = listing(
        ("lidar_point_cloud", "2023", "SD9545"),
        ("national_lidar_programme_point_cloud", "2020", "SD9545"),
        ("national_lidar_programme_point_cloud", "2018", "SD9545"),
        ("national_lidar_programme_point_cloud", "2020", "SD9550"),
        ("lidar_composite_dtm", "2022", "SD9545"),
    )
    http = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body)))
    box = Aoi(crs=BRITISH_NATIONAL_GRID, west=399_500, south=447_000, east=399_900, north=447_400)
    found = find_point_cloud_tiles(http, box, initial_backoff_s=0.0)
    assert list(found) == ["SD9545"]
    assert [(t.product, t.year) for t in found["SD9545"]] == [
        ("national_lidar_programme_point_cloud", 2020),
        ("national_lidar_programme_point_cloud", 2018),
        ("lidar_point_cloud", 2023),
    ]


def capture(product: str, year: int) -> PointCloudTile:
    return PointCloudTile(
        product=product, year=year, tile_id="SJ2575", uri=f"https://example.test/{product}/{year}"
    )


def test_a_404_capture_falls_through_to_the_next_and_is_cached(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "national" in str(request.url):
            return httpx.Response(404)
        return httpx.Response(200, content=zip_bytes({"a/b/x.laz": b"X", "readme.txt": b"t"}))

    http = httpx.Client(transport=httpx.MockTransport(handle))
    captures = (
        capture("national_lidar_programme_point_cloud", 2019),
        capture("lidar_point_cloud", 2023),
    )
    files = fetch_point_cloud(http, captures, tmp_path, initial_backoff_s=0.0)
    assert [f.name for f in files] == ["x.laz"]
    assert files[0].read_bytes() == b"X"
    assert not list(tmp_path.rglob("*.zip*"))
    assert fetch_point_cloud(http, captures, tmp_path, initial_backoff_s=0.0) == files
    assert len(requests) == 2


def test_download_past_the_cap_raises_and_leaves_nothing(tmp_path: Path) -> None:
    body = zip_bytes({"x.laz": b"x" * 5000})
    http = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body)))
    with pytest.raises(ValueError, match="byte download cap"):
        fetch_point_cloud(
            http,
            (capture("lidar_point_cloud", 2023),),
            tmp_path,
            max_bytes=100,
            initial_backoff_s=0.0,
        )
    assert not [p for p in tmp_path.rglob("*") if p.is_file()]


def test_every_capture_404_raises_file_not_found(tmp_path: Path) -> None:
    http = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(404)))
    with pytest.raises(FileNotFoundError, match="404"):
        fetch_point_cloud(
            http, (capture("lidar_point_cloud", 2023),), tmp_path, initial_backoff_s=0.0
        )
