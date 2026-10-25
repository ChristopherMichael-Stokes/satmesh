import io
from pathlib import Path

import httpx
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from satmesh_core import BRITISH_NATIONAL_GRID, WGS84, Aoi
from satmesh_data import EA_DSM, EA_DTM, LidarCheckError, fetch_ea_lidar

BOX = Aoi(crs=BRITISH_NATIONAL_GRID, west=399500, south=447000, east=399520, north=447010)
# WCS GeoTIFF nodata value, as observed live (float32 lowest)
WCS_NODATA = -3.4028235e38


def geotiff(
    crs: str = BRITISH_NATIONAL_GRID,
    west: float = BOX.west,
    north: float = BOX.north,
    nodata_pixels: int = 0,
) -> bytes:
    width, height = int(BOX.east - BOX.west), int(BOX.north - BOX.south)
    heights = np.linspace(100.0, 120.0, width * height, dtype=np.float32).reshape(height, width)
    heights.flat[:nodata_pixels] = WCS_NODATA
    buffer = io.BytesIO()
    with rasterio.open(
        buffer,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="float32",
        crs=crs,
        transform=from_origin(west, north, 1.0, 1.0),
        nodata=WCS_NODATA,
    ) as dst:
        dst.write(heights, 1)
    return buffer.getvalue()


def serving(body: bytes, requests: list[httpx.Request]) -> httpx.Client:
    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=body)

    return httpx.Client(transport=httpx.MockTransport(handle))


def cached_files(cache: Path) -> list[Path]:
    return [p for p in cache.rglob("*") if p.is_file()]


def test_lidar_is_fetched_by_bng_subset_and_cached(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    http = serving(geotiff(), requests)
    path = fetch_ea_lidar(http, BOX, tmp_path, EA_DTM, initial_backoff_s=0.0)
    assert fetch_ea_lidar(http, BOX, tmp_path, EA_DTM, initial_backoff_s=0.0) == path
    assert len(requests) == 1
    params = requests[0].url.params
    assert params.get_list("subset") == ["E(399500,399520)", "N(447000,447010)"]
    assert params["coverageId"].endswith("Lidar_Composite_Elevation_DTM_1m")
    with rasterio.open(path) as src:
        assert tuple(src.bounds) == (399500, 447000, 399520, 447010)
        assert src.read(1).min() == pytest.approx(100.0)


@pytest.mark.parametrize(
    ("name", "body", "match"),
    [
        ("wrong CRS", geotiff(crs="EPSG:3857"), "CRS"),
        ("shifted grid", geotiff(west=BOX.west + 1), "bounds"),
        ("nodata", geotiff(nodata_pixels=3), "3 nodata"),
    ],
)
def test_bad_raster_raises_and_is_not_cached(
    tmp_path: Path, name: str, body: bytes, match: str
) -> None:
    with pytest.raises(LidarCheckError, match=match):
        fetch_ea_lidar(serving(body, []), BOX, tmp_path, EA_DTM, initial_backoff_s=0.0)
    assert not cached_files(tmp_path), name


def test_box_must_be_bng() -> None:
    box = Aoi(crs=WGS84, west=-2.0, south=53.9, east=-1.99, north=53.91)
    with pytest.raises(ValueError, match=BRITISH_NATIONAL_GRID):
        fetch_ea_lidar(serving(b"", []), box, Path("unused"), EA_DTM)


def test_box_must_be_on_the_metre_grid() -> None:
    box = Aoi(crs=BRITISH_NATIONAL_GRID, west=399500.5, south=447000, east=399520, north=447010)
    with pytest.raises(ValueError, match="whole metres"):
        fetch_ea_lidar(serving(b"", []), box, Path("unused"), EA_DTM)


def test_dsm_and_dtm_use_their_own_coverage_and_cache_entries(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    http = serving(geotiff(), requests)
    dtm = fetch_ea_lidar(http, BOX, tmp_path, EA_DTM, initial_backoff_s=0.0)
    dsm = fetch_ea_lidar(http, BOX, tmp_path, EA_DSM, initial_backoff_s=0.0)
    assert dtm != dsm
    assert [r.url.params["coverageId"] for r in requests] == [
        EA_DTM.coverage_id,
        EA_DSM.coverage_id,
    ]
    assert str(requests[1].url).startswith(EA_DSM.wcs_url)
