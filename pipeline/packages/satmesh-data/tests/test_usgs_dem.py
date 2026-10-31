import json
from pathlib import Path

import httpx
import numpy as np
import numpy.typing as npt
import pytest
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from satmesh_core import WGS84, Aoi
from satmesh_data import (
    DemCoverageError,
    DemSources,
    MetreGrid,
    RequestSchedule,
    fetch_dem_window,
    grid_for,
)
from satmesh_data.usgs_dem import (
    IMAGE_SERVER,
    IMAGE_SERVER_MAX_PIXELS,
    SMALL_HOLE_MAX_FRACTION,
    export_image,
    find_tnm_products,
    read_dem_provenance,
    read_onto_grid,
    seamless_tiles,
)

NAD83_UTM_13N = "EPSG:26913"
NAD83_2011_UTM_13N = "EPSG:6342"
NAD83_GEOGRAPHIC = "EPSG:4269"
# the real tile USGS_1M_13_x50y440_CO_DRCOG_2020_B20: 10012 px from (499993.9999999989,
# 4400005.999985854), whole metres up to float fuzz that the read must absorb; the fixture keeps
# its origin and labelling and holds only its north-west corner
TILE_WEST, TILE_NORTH = 499993.9999999989, 4400005.999985854
TILE_PIXELS = 400
NODATA = -999999.0
SOURCES = DemSources(
    tnm_products_url="https://tnm.test/api/v1/products",
    tnm_dataset="Digital Elevation Model (DEM) 1 meter",
    image_server_url="https://images.test/ImageServer",
    seamless_path_template="unused/{tile}.tif",
)
NO_WAIT = RequestSchedule(0.0)
IMAGE_SERVER_SOURCE_PS = 1.0
EVERYTHING = (slice(None), slice(None))


def plane(easting: npt.ArrayLike, northing: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """Heights linear in position, so a pixel's expected value follows from its centre alone."""
    e, n = np.asarray(easting, dtype=float), np.asarray(northing, dtype=float)
    return 1600.0 + 0.01 * (e - 500000.0) - 0.02 * (n - 4400000.0)


def utm_tile(path: Path, offset_m: float = 0.0, hole: tuple[slice, slice] | None = None) -> Path:
    """A 1 m tile in NAD83 UTM 13N at the real tile origin, heights `plane` + `offset_m`."""
    centres = np.arange(TILE_PIXELS) + 0.5
    east, north = np.meshgrid(TILE_WEST + centres, TILE_NORTH - centres)
    heights = (plane(east, north) + offset_m).astype(np.float32)
    if hole is not None:
        heights[hole] = NODATA
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=TILE_PIXELS,
        height=TILE_PIXELS,
        count=1,
        dtype="float32",
        crs=NAD83_UTM_13N,
        transform=from_origin(TILE_WEST, TILE_NORTH, 1.0, 1.0),
        nodata=NODATA,
    ) as dst:
        dst.write(heights, 1)
    return path


def project_tile(
    root: Path, project: str, offset_m: float = 0.0, hole: tuple[slice, slice] | None = None
) -> Path:
    """A tile at the TNM download layout `.../Projects/{project}/TIFF/{file}`."""
    path = root / "Projects" / project / "TIFF" / f"USGS_1M_13_x50y440_{project}.tif"
    return utm_tile(path, offset_m, hole)


def leaf_grid() -> MetreGrid:
    """A 130 x 130 m window inside the tile, the size of a z18 leaf's window at Denver."""
    return MetreGrid(NAD83_2011_UTM_13N, 500100, 4399750, 500230, 4399880)


def tile_slices(grid: MetreGrid, rows: slice, columns: slice) -> tuple[slice, slice]:
    """The tile's rows and columns under the grid's `rows` and `columns`; the fuzz rounds away."""
    first_row = round(TILE_NORTH - grid.north)
    first_column = round(grid.west - TILE_WEST)
    return (
        slice(first_row + rows.start, first_row + rows.stop),
        slice(first_column + columns.start, first_column + columns.stop),
    )


def pixel_centres(grid: MetreGrid) -> tuple[np.ndarray, np.ndarray]:
    rows, columns = grid.shape
    return np.meshgrid(grid.west + np.arange(columns) + 0.5, grid.north - np.arange(rows) - 0.5)


def seamless_tile(path: Path, west: float, height_m: float, pixel_deg: float) -> Path:
    """A NAD83 geographic tile whose north-west corner is (west, 40 N), of constant height."""
    side = round(1 / pixel_deg)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=side,
        height=side,
        count=1,
        dtype="float32",
        crs=NAD83_GEOGRAPHIC,
        transform=from_origin(west, 40.0, pixel_deg, pixel_deg),
    ) as dst:
        dst.write(np.full((side, side), height_m, dtype=np.float32), 1)
    return path


def with_seamless_template(template: str) -> DemSources:
    return DemSources(
        SOURCES.tnm_products_url, SOURCES.tnm_dataset, SOURCES.image_server_url, template
    )


def test_tile_pixels_land_on_the_grid_unresampled(tmp_path: Path) -> None:
    grid = leaf_grid()
    heights, used = read_onto_grid([str(utm_tile(tmp_path / "a.tif"))], grid)
    assert [(c.index, c.crs_note, c.pixels) for c in used] == [
        (0, f"{NAD83_UTM_13N} read as {NAD83_2011_UTM_13N}", 130 * 130)
    ]
    # float32 heights near 1600 m resolve about 1e-4 m
    np.testing.assert_allclose(heights, plane(*pixel_centres(grid)), atol=1e-3)


def test_an_all_nodata_tile_listed_first_supplies_nothing(tmp_path: Path) -> None:
    grid = leaf_grid()
    empty = utm_tile(tmp_path / "empty.tif", hole=EVERYTHING)
    heights, used = read_onto_grid([str(empty), str(utm_tile(tmp_path / "a.tif"))], grid)
    assert [c.index for c in used] == [1]
    np.testing.assert_allclose(heights, plane(*pixel_centres(grid)), atol=1e-3)


class Usgs:
    """TNM API, ImageServer catalog, identify and exportImage; records every request path."""

    def __init__(self, products: list[dict[str, str]], catalog_low_ps: float) -> None:
        self.products = products
        self.catalog_low_ps = catalog_low_ps
        self.image = b""
        self.requests: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.requests.append(path)
        if path.endswith("/products"):
            offset = int(request.url.params["offset"])
            size = int(request.url.params["max"])
            page = self.products[offset : offset + size]
            return httpx.Response(200, json={"total": len(self.products), "items": page})
        if path.endswith("/query"):
            item = {"Name": "x", "LowPS": self.catalog_low_ps, "Category": 1}
            return httpx.Response(200, json={"features": [{"attributes": item}]})
        if path.endswith("/identify"):
            # an overview and the primary source; the mosaic value is the primary one's
            items = [
                {"attributes": {"Name": "Ov", "LowPS": 75.0, "Category": 2}},
                {"attributes": {"Name": "x", "LowPS": IMAGE_SERVER_SOURCE_PS, "Category": 1}},
            ]
            answer = {
                "value": "1601.5",
                "properties": {"Values": ["1590", "1601.5"]},
                "catalogItems": {"features": items},
            }
            return httpx.Response(200, json=answer)
        if path.endswith("/exportImage"):
            return httpx.Response(200, content=self.image)
        return httpx.Response(404)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


def product(title: str, url: str, published: str) -> dict[str, str]:
    return {"title": title, "downloadURL": url, "publicationDate": published, "extra": "x"}


def geotiff_on(grid: MetreGrid, heights: np.ndarray) -> bytes:
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            width=grid.shape[1],
            height=grid.shape[0],
            count=1,
            dtype="float32",
            crs=grid.crs,
            transform=grid.transform,
            nodata=NODATA,
        ) as dst:
            dst.write(heights.astype(np.float32), 1)
        return bytes(memory.read())


def test_an_all_nodata_1m_tile_falls_back_to_the_image_server(tmp_path: Path) -> None:
    grid = leaf_grid()
    expected = plane(*pixel_centres(grid))
    empty = project_tile(tmp_path, "NM_Empty_2017", hole=EVERYTHING)
    server = Usgs([product("empty", str(empty), "2022-01-01")], catalog_low_ps=1.0)
    server.image = geotiff_on(grid, expected)
    path = fetch_dem_window(server.client(), NO_WAIT, SOURCES, grid, tmp_path)
    with rasterio.open(path) as src:
        np.testing.assert_allclose(src.read(1), expected, atol=1e-3)
    provenance = read_dem_provenance(path)
    assert [(s.source, s.resolution_m, s.share) for s in provenance.sources] == [
        (IMAGE_SERVER, IMAGE_SERVER_SOURCE_PS, 1.0)
    ]


def test_a_second_project_fills_the_nodata_of_the_first(tmp_path: Path) -> None:
    grid = leaf_grid()
    # the preferred project lacks the window's west 30 columns; the other one is 5 m higher
    first = project_tile(
        tmp_path, "CO_DRCOG_2020_B20", hole=tile_slices(grid, slice(0, 130), slice(0, 30))
    )
    second = project_tile(tmp_path, "CO_Forest_D23", offset_m=5.0)
    listed = [
        product("forest", str(second), "2024-06-01"),
        product("drcog", str(first), "2022-02-10"),
    ]
    server = Usgs(listed, catalog_low_ps=1.0)
    path = fetch_dem_window(server.client(), NO_WAIT, SOURCES, grid, tmp_path, prefer_year=2020)
    expected = plane(*pixel_centres(grid))
    expected[:, :30] += 5.0
    with rasterio.open(path) as src:
        np.testing.assert_allclose(src.read(1), expected, atol=1e-3)
    provenance = read_dem_provenance(path)
    assert [(s.source, s.resolution_m) for s in provenance.sources] == [
        ("tnm-1m: CO_DRCOG_2020_B20", 1.0),
        ("tnm-1m: CO_Forest_D23", 1.0),
    ]
    assert [s.share for s in provenance.sources] == pytest.approx([100 / 130, 30 / 130])
    assert provenance.interpolated_fraction == 0.0
    assert not any(p.endswith("/exportImage") for p in server.requests)


def test_a_3m_hole_is_interpolated_from_the_ground_around_it(tmp_path: Path) -> None:
    grid = leaf_grid()
    hole = tile_slices(grid, slice(60, 63), slice(60, 63))
    tile = project_tile(tmp_path, "CO_DRCOG_2020_B20", hole=hole)
    server = Usgs([product("drcog", str(tile), "2022-02-10")], catalog_low_ps=1.0)
    path = fetch_dem_window(server.client(), NO_WAIT, SOURCES, grid, tmp_path)
    with rasterio.open(path) as src:
        heights = src.read(1)
    # inverse-distance weights over the plane stay within its range across the hole: slopes of
    # 0.01 and 0.02 over at most 5 m change heights by under 0.15 m
    np.testing.assert_allclose(heights, plane(*pixel_centres(grid)), atol=0.15)
    provenance = read_dem_provenance(path)
    assert SMALL_HOLE_MAX_FRACTION > 9 / 130**2
    assert provenance.interpolated_fraction == pytest.approx(9 / 130**2)
    assert [s.source for s in provenance.sources] == ["tnm-1m: CO_DRCOG_2020_B20"]
    assert not any(p.endswith("/exportImage") for p in server.requests)


def test_a_30m_hole_falls_through_to_the_image_server(tmp_path: Path) -> None:
    grid = leaf_grid()
    hole = tile_slices(grid, slice(50, 80), slice(50, 80))
    tile = project_tile(tmp_path, "CO_DRCOG_2020_B20", hole=hole)
    server = Usgs([product("drcog", str(tile), "2022-02-10")], catalog_low_ps=1.0)
    expected = plane(*pixel_centres(grid))
    server.image = geotiff_on(grid, expected + 0.25)
    path = fetch_dem_window(server.client(), NO_WAIT, SOURCES, grid, tmp_path)
    with rasterio.open(path) as src:
        heights = src.read(1)
    expected[50:80, 50:80] += 0.25
    np.testing.assert_allclose(heights, expected, atol=1e-3)
    provenance = read_dem_provenance(path)
    assert [s.source for s in provenance.sources] == ["tnm-1m: CO_DRCOG_2020_B20", IMAGE_SERVER]
    assert [s.share for s in provenance.sources] == pytest.approx([1 - 900 / 130**2, 900 / 130**2])
    assert provenance.interpolated_fraction == 0.0


def test_without_any_1m_source_the_seamless_tile_is_resampled(tmp_path: Path) -> None:
    pixel_deg = 1 / 900
    seamless_tile(tmp_path / "n40w105.tif", -105.0, 1601.5, pixel_deg)
    sources = with_seamless_template(str(tmp_path / "{tile}.tif"))
    server = Usgs([], catalog_low_ps=10.3)
    path = fetch_dem_window(server.client(), NO_WAIT, sources, leaf_grid(), tmp_path)
    with rasterio.open(path) as src:
        np.testing.assert_allclose(src.read(1), 1601.5, atol=1e-3)
    (share,) = read_dem_provenance(path).sources
    assert share.source == "3dep-seamless-13: n40w105"
    # 1/900 degree of latitude near 39.5 N on GRS80: 111.0 km / 900, about 123.4 m
    assert share.resolution_m == pytest.approx(123.4, abs=0.5)
    assert not any(p.endswith("/exportImage") for p in server.requests)


def test_a_hole_left_by_the_last_source_raises_naming_window_and_fraction(
    tmp_path: Path,
) -> None:
    grid = leaf_grid()
    heights = plane(*pixel_centres(grid))
    heights[:13, :] = NODATA
    server = Usgs([], catalog_low_ps=1.0)
    server.image = geotiff_on(grid, heights)
    # the seamless file holds 110 to 109 W only, so it adds nothing at 105 W
    seamless_tile(tmp_path / "n40w105.tif", -110.0, 1.0, 0.1)
    sources = with_seamless_template(str(tmp_path / "{tile}.tif"))
    with pytest.raises(DemCoverageError, match=rf"{grid.name}: 10.00% nodata after .*seamless"):
        fetch_dem_window(server.client(), NO_WAIT, sources, grid, tmp_path)


def test_tiles_of_the_preferred_year_come_before_newer_ones(tmp_path: Path) -> None:
    listed = [
        product("USGS 1 Meter 13 x50y440 CO_DRCOG_2020_B20", "https://s3.test/a.tif", "2022-02-10"),
        product("USGS 1 Meter 13 x50y440 CO_Forest_D23", "https://s3.test/b.tif", "2024-06-01"),
    ]
    server = Usgs(listed, catalog_low_ps=1.0)
    found = find_tnm_products(
        server.client(), NO_WAIT, SOURCES, leaf_grid(), tmp_path, prefer_year=2020
    )
    assert [p.download_url for p in found] == ["https://s3.test/a.tif", "https://s3.test/b.tif"]


def test_tnm_products_are_read_across_pages_newest_first_and_cached(tmp_path: Path) -> None:
    listed = [
        product("old", "https://s3.test/old.tif", "2015-01-01"),
        product("new", "https://s3.test/new.tif", "2022-02-10"),
        product("zip", "https://s3.test/new.zip", "2023-01-01"),
    ]
    server = Usgs(listed, catalog_low_ps=1.0)
    http = server.client()
    grid = leaf_grid()
    found = find_tnm_products(http, NO_WAIT, SOURCES, grid, tmp_path)
    assert [p.title for p in found] == ["new", "old"]
    pages = len(server.requests)
    assert find_tnm_products(http, NO_WAIT, SOURCES, grid, tmp_path) == found
    assert len(server.requests) == pages
    (cached,) = (tmp_path / "tnm-queries").glob("*.json")
    assert [item["title"] for item in json.loads(cached.read_text())] == ["old", "new", "zip"]


def test_an_error_answered_with_status_200_is_retried(tmp_path: Path) -> None:
    answers = iter(
        [
            httpx.Response(200, json={"error": "Expecting value", "toastType": "warning"}),
            httpx.Response(200, json={"total": 0, "items": []}),
        ]
    )
    http = httpx.Client(transport=httpx.MockTransport(lambda _: next(answers)))
    found = find_tnm_products(http, NO_WAIT, SOURCES, leaf_grid(), tmp_path, initial_backoff_s=0)
    assert found == []


def test_grid_is_in_the_nad83_2011_zone_of_the_centre_with_whole_metre_edges() -> None:
    footprint = Aoi(crs=WGS84, west=-105.0, south=39.74, east=-104.99, north=39.75)
    grid = grid_for(footprint, 5)
    assert grid.crs == NAD83_2011_UTM_13N
    west, south, east, north = footprint.bounds_in(NAD83_2011_UTM_13N)
    assert west - 6 < grid.west <= west - 5
    assert north + 5 <= grid.north < north + 6
    assert grid.south <= south - 5
    assert east + 5 <= grid.east
    assert (grid.transform.a, grid.transform.e) == (1.0, -1.0)
    assert (grid.transform.c, grid.transform.f) == (grid.west, grid.north)


def test_seamless_tiles_are_named_by_north_and_west_edges() -> None:
    # 39.74 to 39.75 N, 104.99 to 104.98 W lies in the 1-degree cell 39-40 N, 105-104 W
    footprint = Aoi(crs=WGS84, west=-104.99, south=39.74, east=-104.98, north=39.75)
    assert seamless_tiles(grid_for(footprint, 5)) == ["n40w105"]


def test_image_requests_past_the_service_limit_are_refused() -> None:
    side = IMAGE_SERVER_MAX_PIXELS + 1
    grid = MetreGrid(NAD83_2011_UTM_13N, 500000, 4390000, 500000 + side, 4390010)
    server = Usgs([], catalog_low_ps=1.0)
    with pytest.raises(ValueError, match="8000 px"):
        export_image(server.client(), NO_WAIT, SOURCES.image_server_url, grid)
    assert server.requests == []
