import io
import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import laspy
import numpy as np
import pytest
import rasterio
from pyproj import Transformer

from satmesh_data import (
    EptCoverageError,
    MetreGrid,
    RequestSchedule,
    fetch_ept_dsm,
    find_ept_project,
)
from satmesh_data.ept_dsm import highest_per_pixel, read_dsm_provenance

NAD83_2011_UTM_13N = "EPSG:6342"
GRID = MetreGrid(NAD83_2011_UTM_13N, 500100, 4399750, 500110, 4399760)
DTM_HEIGHT_M = 1600.0
NO_WAIT = RequestSchedule(0.0)
INDEX_URL = "https://index.test/resources.geojson"
BUCKET = "https://lidar.test/usgs-lidar-public"
# ASPRS classes: 1 unclassified, 2 ground, 6 building, 7 low noise, 18 high noise
UNCLASSIFIED, GROUND, BUILDING, LOW_NOISE, HIGH_NOISE = 1, 2, 6, 7, 18
WITHHELD_FLAG = 0b100
CAPTURE = datetime(2020, 5, 27, 12, tzinfo=UTC)
# LAS 1.4 adjusted standard GPS time: seconds since 1980-01-06T00:00Z minus 1e9
CAPTURE_GPS_TIME = (CAPTURE - datetime(1980, 1, 6, tzinfo=UTC)).total_seconds() - 1e9


def test_each_pixel_keeps_its_highest_point_and_owns_its_west_and_north_edges() -> None:
    transform = GRID.transform
    x = np.array([500100.5, 500100.5, 500101.0, 500109.99, 500200.0])
    y = np.array([4399759.5, 4399759.5, 4399759.0, 4399750.01, 4399755.0])
    z = np.array([10.0, 12.0, 7.0, 3.0, 99.0])
    highest = highest_per_pixel(x, y, z, transform, GRID.shape)
    assert highest[0, 0] == 12.0
    # x = 500101 is the west edge of column 1 and y = 4399759 the north edge of row 1
    assert highest[1, 1] == 7.0
    assert highest[9, 9] == 3.0
    assert np.isnan(highest).sum() == 100 - 3


def nad83_to_ept(easting: np.ndarray, northing: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """USGS EPT Web Mercator: NAD83(2011) latitude and longitude projected with no datum shift."""
    lon, lat = Transformer.from_crs(NAD83_2011_UTM_13N, "EPSG:6318", always_xy=True).transform(
        easting, northing
    )
    return Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform(lon, lat)


def laz(points: list[tuple[float, float, float, int, int, int]]) -> bytes:
    """LAZ like USGS EPT nodes: LAS 1.2 point format 1 with a `ClassFlags` extra byte.

    Each point is (easting, northing, z, return number, class, class flags) in NAD83(2011) UTM 13N.
    """
    header = laspy.LasHeader(point_format=1, version="1.2")
    header.add_extra_dim(laspy.ExtraBytesParams(name="ClassFlags", type=np.uint8))
    header.scales = np.array([0.001, 0.001, 0.001])
    header.offsets = np.array([-11671581.0, 4826462.0, 2364.0])
    las = laspy.LasData(header)
    columns = np.array(points, dtype=float).T
    las.x, las.y = nad83_to_ept(columns[0], columns[1])
    las.z = columns[2]
    las.return_number = columns[3].astype(np.uint8)
    las.number_of_returns = np.maximum(columns[3], 1).astype(np.uint8)
    las.classification = columns[4].astype(np.uint8)
    las.ClassFlags = columns[5].astype(np.uint8)
    las.gps_time = np.full(len(points), CAPTURE_GPS_TIME)
    out = io.BytesIO()
    las.write(out, do_compress=True)
    return out.getvalue()


def pixel_centre(row: int, column: int) -> tuple[float, float]:
    return GRID.west + column + 0.5, GRID.north - row - 0.5


def ept_cube() -> list[float]:
    """A 1024 m EPT cube whose south-west child node (1-0-0-0) holds the grid."""
    west, south = nad83_to_ept(np.array([GRID.west - 100.0]), np.array([GRID.south - 100.0]))
    return [float(west[0]), float(south[0]), 0.0, west[0] + 1024.0, south[0] + 1024.0, 1024.0]


def box_polygon(west: float, south: float, east: float, north: float) -> dict[str, object]:
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"type": "MultiPolygon", "coordinates": [[ring]]}


class EptServer:
    """An EPT index with three projects and the files of the two that cover the grid."""

    def __init__(self) -> None:
        self.requests: list[str] = []
        covering = box_polygon(-105.1, 39.6, -104.9, 39.8)
        index = {
            "features": [
                {"properties": self.project("CO_Old_2013", 5), "geometry": covering},
                {"properties": self.project("CO_New_2_2020", 9), "geometry": covering},
                {
                    "properties": self.project("NV_Far_2024", 9),
                    "geometry": box_polygon(-115.0, 39.0, -114.0, 40.0),
                },
            ]
        }
        row_col = pixel_centre(2, 3)
        mixed = pixel_centre(5, 5)
        self.files: dict[str, bytes] = {
            "/resources.geojson": json.dumps(index).encode(),
            "/usgs-lidar-public/CO_New_2_2020/ept.json": json.dumps(
                {"bounds": ept_cube()}
            ).encode(),
            "/usgs-lidar-public/CO_New_2_2020/ept-hierarchy/0-0-0-0.json": json.dumps(
                {"0-0-0-0": 2, "1-0-0-0": -1, "1-1-1-0": 1}
            ).encode(),
            "/usgs-lidar-public/CO_New_2_2020/ept-hierarchy/1-0-0-0.json": json.dumps(
                {"1-0-0-0": 6}
            ).encode(),
            "/usgs-lidar-public/CO_New_2_2020/ept-data/0-0-0-0.laz": laz(
                [(*mixed, 1605.0, 1, GROUND, 0), (*row_col, 1610.0, 1, BUILDING, 0)]
            ),
            "/usgs-lidar-public/CO_New_2_2020/ept-data/1-0-0-0.laz": laz(
                [
                    (*row_col, 1612.0, 1, BUILDING, 0),
                    (*row_col, 1620.0, 2, BUILDING, 0),
                    (*row_col, 1630.0, 1, LOW_NOISE, 0),
                    (*row_col, 1650.0, 1, HIGH_NOISE, 0),
                    (*row_col, 1640.0, 1, UNCLASSIFIED, WITHHELD_FLAG),
                    (*mixed, 1607.0, 1, GROUND, 0),
                ]
            ),
        }

    @staticmethod
    def project(name: str, count: int) -> dict[str, object]:
        return {"name": name, "id": 0, "count": count, "url": f"{BUCKET}/{name}/ept.json"}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request.url.path)
        content = self.files.get(request.url.path)
        return httpx.Response(404) if content is None else httpx.Response(200, content=content)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


def dtm_window(path: Path) -> Path:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=GRID.shape[1],
        height=GRID.shape[0],
        count=1,
        dtype="float32",
        crs=GRID.crs,
        transform=GRID.transform,
    ) as dst:
        dst.write(np.full(GRID.shape, DTM_HEIGHT_M, dtype=np.float32), 1)
    return path


def test_dsm_keeps_the_highest_clean_first_return_and_fills_the_rest_from_the_dtm(
    tmp_path: Path,
) -> None:
    server = EptServer()
    http = server.client()
    project = find_ept_project(http, NO_WAIT, INDEX_URL, GRID, tmp_path)
    assert project.name == "CO_New_2_2020"
    dtm = dtm_window(tmp_path / f"{GRID.name}.tif")
    path = fetch_ept_dsm(http, NO_WAIT, project, dtm, tmp_path)
    with rasterio.open(path) as src:
        dsm = src.read(1)
        assert src.crs.to_string() == NAD83_2011_UTM_13N
        assert src.transform == GRID.transform
    # second returns, noise and withheld points are higher but never count
    assert dsm[2, 3] == pytest.approx(1612.0, abs=1e-3)
    # both octree depths hold points of the window
    assert dsm[5, 5] == pytest.approx(1607.0, abs=1e-3)
    others = np.ones(GRID.shape, dtype=bool)
    others[2, 3] = others[5, 5] = False
    assert (dsm[others] == DTM_HEIGHT_M).all()
    provenance = read_dsm_provenance(path)
    assert provenance.project == "CO_New_2_2020"
    assert provenance.first_returns == 4
    assert provenance.filled_from_dtm_fraction == pytest.approx(98 / 100)
    assert provenance.acquired_from == provenance.acquired_to == date(2020, 5, 27)
    # node 1-1-1-0 lies outside the window and is never fetched
    assert not any("1-1-1-0" in request for request in server.requests)
    fetched = len(server.requests)
    assert fetch_ept_dsm(http, NO_WAIT, project, dtm, tmp_path) == path
    assert len(server.requests) == fetched


def test_a_window_no_project_covers_raises(tmp_path: Path) -> None:
    far = MetreGrid("EPSG:6348", 500000, 4500000, 500010, 4500010)
    with pytest.raises(EptCoverageError, match="no EPT project"):
        find_ept_project(EptServer().client(), NO_WAIT, INDEX_URL, far, tmp_path)
