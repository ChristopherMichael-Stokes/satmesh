import io
import json
import zipfile
from pathlib import Path

import httpx
import numpy as np
import numpy.typing as npt
import pytest
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from satmesh_core import BRITISH_NATIONAL_GRID, WGS84, Aoi
from satmesh_data import (
    CogTilesWithZipGroundSource,
    Surface,
    TileMissingError,
    fetch_cog_window,
    fetch_surfaces,
    fetch_surfaces_from_source,
)

TILE_URL = "https://tiles.test/{ns}{lat:02d}_{ew}{lon:03d}.tif"
TILE_PIXELS = 100
PIXEL_DEG = 1 / TILE_PIXELS
PEAK_M = 5000.0
GROUND_NODATA_M = -9999.0


def centre_height(lon: npt.ArrayLike, lat: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """A plane in degrees, so any pixel's expected height follows from its centre alone."""
    return 1000.0 + 10.0 * np.asarray(lon, dtype=float) + 3.0 * np.asarray(lat, dtype=float)


def tile_bytes(
    south: int,
    west: int,
    peak: tuple[int, int] | None = None,
    ground_offset_m: float | None = None,
    hole: tuple[slice, slice] | None = None,
) -> bytes:
    """A point-registered tile: pixel (0, 0) centred on (west, south + 1), as GDAL reads GLO-30.

    GDAL's geotransform for it has its origin half a pixel outside the corner.
    """
    rows = np.arange(TILE_PIXELS, dtype=np.float64)[:, np.newaxis]
    cols = np.arange(TILE_PIXELS, dtype=np.float64)[np.newaxis, :]
    heights = np.asarray(
        centre_height(west + cols * PIXEL_DEG, south + 1 - rows * PIXEL_DEG), dtype=np.float32
    )
    if peak is not None:
        heights[peak] = PEAK_M
    if ground_offset_m is not None:
        heights += np.float32(ground_offset_m)
    if hole is not None:
        heights[hole] = GROUND_NODATA_M
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            width=TILE_PIXELS,
            height=TILE_PIXELS,
            count=1,
            dtype="float32",
            crs=WGS84,
            transform=from_origin(
                west - PIXEL_DEG / 2, south + 1 + PIXEL_DEG / 2, PIXEL_DEG, PIXEL_DEG
            ),
        ) as dst:
            dst.write(heights, 1)
            dst.update_tags(AREA_OR_POINT="Point")
        return bytes(memory.read())


class TileServer:
    """Serves the tiles it was given by file name and counts requests."""

    def __init__(self, tiles: dict[str, bytes]) -> None:
        self.tiles = tiles
        self.requests: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        name = request.url.path.removeprefix("/").removesuffix(".tif")
        self.requests.append(name)
        if name not in self.tiles:
            return httpx.Response(404)
        return httpx.Response(200, content=self.tiles[name])

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


def test_window_samples_at_pixel_centres_equal_the_pixel_values(tmp_path: Path) -> None:
    peak_row, peak_col = 30, 40
    server = TileServer({"N15_E044": tile_bytes(15, 44, (peak_row, peak_col))})
    centre_lon, centre_lat = 44 + peak_col * PIXEL_DEG, 16 - peak_row * PIXEL_DEG
    footprint = (centre_lon - 0.03, centre_lat - 0.03, centre_lon + 0.03, centre_lat + 0.03)
    path = fetch_cog_window(server.client(), TILE_URL, footprint, tmp_path)
    with rasterio.open(path) as src:
        transform, heights, crs = src.transform, src.read(1), src.crs
    assert crs.to_epsg() == 4326
    # downstream bilinear sampling indexes at (coordinate - origin) / size - 0.5; an integer index
    # there means the sample at a pixel centre is that pixel's value with no blending
    column = (centre_lon - transform.c) / transform.a - 0.5
    row = (centre_lat - transform.f) / transform.e - 0.5
    assert column == pytest.approx(round(column), abs=1e-6)
    assert row == pytest.approx(round(row), abs=1e-6)
    assert heights[round(row), round(column)] == pytest.approx(PEAK_M)
    next_lon = centre_lon + PIXEL_DEG
    assert heights[round(row), round(column) + 1] == pytest.approx(
        float(centre_height(next_lon, centre_lat)), abs=1e-2
    )


def test_window_covers_footprint_plus_two_pixels_on_the_tile_grid(tmp_path: Path) -> None:
    server = TileServer({"N15_E044": tile_bytes(15, 44)})
    footprint = (44.2, 15.3, 44.4, 15.5)
    with rasterio.open(fetch_cog_window(server.client(), TILE_URL, footprint, tmp_path)) as src:
        left, bottom, right, top = src.bounds
        res = src.res
    margin = 2 * PIXEL_DEG
    assert res == pytest.approx((PIXEL_DEG, PIXEL_DEG))
    assert footprint[0] - margin - PIXEL_DEG < left <= footprint[0] - margin
    assert footprint[2] + margin <= right < footprint[2] + margin + PIXEL_DEG
    assert footprint[1] - margin - PIXEL_DEG < bottom <= footprint[1] - margin
    assert footprint[3] + margin <= top < footprint[3] + margin + PIXEL_DEG
    # pixel edges sit at integer degrees minus half a pixel
    offset = (left - (44 - PIXEL_DEG / 2)) / PIXEL_DEG
    assert offset == pytest.approx(round(offset), abs=1e-6)


def test_window_across_a_tile_boundary_is_seamless_and_cached(tmp_path: Path) -> None:
    server = TileServer({"N15_E044": tile_bytes(15, 44), "N15_E045": tile_bytes(15, 45)})
    footprint = (44.97, 15.4, 45.03, 15.45)
    http = server.client()
    path = fetch_cog_window(http, TILE_URL, footprint, tmp_path)
    assert sorted(server.requests) == ["N15_E044", "N15_E045"]
    with rasterio.open(path) as src:
        transform, heights = src.transform, src.read(1)
    rows, cols = np.mgrid[0 : heights.shape[0], 0 : heights.shape[1]]
    lons = transform.c + (cols + 0.5) * transform.a
    lats = transform.f + (rows + 0.5) * transform.e
    assert np.allclose(heights, centre_height(lons, lats), atol=1e-2)
    assert fetch_cog_window(http, TILE_URL, footprint, tmp_path) == path
    assert len(server.requests) == 2
    other = fetch_cog_window(http, TILE_URL, (44.98, 15.4, 45.02, 15.45), tmp_path)
    assert other != path
    assert len(server.requests) == 2
    assert not list(tmp_path.rglob("*.part"))


def test_window_needing_a_missing_tile_raises_naming_it(tmp_path: Path) -> None:
    server = TileServer({"N15_E044": tile_bytes(15, 44)})
    with pytest.raises(TileMissingError, match="N15_E045"):
        fetch_cog_window(server.client(), TILE_URL, (44.97, 15.4, 45.03, 15.45), tmp_path)
    assert not list(tmp_path.rglob("*.part"))


def test_southern_and_western_tiles_are_named_by_hemisphere(tmp_path: Path) -> None:
    server = TileServer({"S01_W002": tile_bytes(-1, -2)})
    fetch_cog_window(server.client(), TILE_URL, (-1.6, -0.6, -1.4, -0.4), tmp_path)
    assert server.requests == ["S01_W002"]


def test_fetch_surfaces_over_glo30_returns_one_dsm_surface(tmp_path: Path) -> None:
    footprint = Aoi(crs=WGS84, west=10.2, south=50.3, east=10.22, north=50.32)

    def serve_any_tile(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=tile_bytes(50, 10))

    http = httpx.Client(transport=httpx.MockTransport(serve_any_tile))
    pair = fetch_surfaces(http, footprint, tmp_path)
    assert pair.source == "copernicus-glo30"
    assert pair.ground_is_surface
    assert pair.dsm == pair.dtm
    assert (pair.dsm.xy_crs, pair.dsm.height_crs) == (WGS84, "EPSG:4326+3855")
    assert pair.dsm.path.is_relative_to(tmp_path)


def test_fetch_surfaces_over_great_britain_requests_the_margined_bng_box(tmp_path: Path) -> None:
    footprint = Aoi(
        crs=BRITISH_NATIONAL_GRID, west=399500.4, south=447000.2, east=399520.0, north=447009.6
    )
    # whole metres out, then 5 m more each side
    west, south, east, north = 399495, 446995, 399525, 447015
    requests: list[httpx.Request] = []

    def serve_subset(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        buffer = io.BytesIO()
        with rasterio.open(
            buffer,
            "w",
            driver="GTiff",
            width=east - west,
            height=north - south,
            count=1,
            dtype="float32",
            crs=BRITISH_NATIONAL_GRID,
            transform=from_origin(west, north, 1.0, 1.0),
        ) as dst:
            dst.write(np.full((north - south, east - west), 50.0, dtype="float32"), 1)
        return httpx.Response(200, content=buffer.getvalue())

    http = httpx.Client(transport=httpx.MockTransport(serve_subset))
    pair = fetch_surfaces(http, footprint, tmp_path)
    assert pair.source == "ea-lidar-composite"
    assert not pair.ground_is_surface
    assert pair.dsm.path != pair.dtm.path
    assert pair.dtm.height_crs == "EPSG:7405"
    subsets = {tuple(r.url.params.get_list("subset")) for r in requests}
    assert subsets == {(f"E({west},{east})", f"N({south},{north})")}


def test_margin_tile_missing_beside_the_coast_drops_the_margin_on_that_side(tmp_path: Path) -> None:
    server = TileServer({"N15_E044": tile_bytes(15, 44)})
    footprint = (44.003, 15.3, 44.2, 15.5)
    path = fetch_cog_window(server.client(), TILE_URL, footprint, tmp_path)
    assert "N15_E043" in server.requests
    with rasterio.open(path) as src:
        left, bottom, right, top = src.bounds
        heights = src.read(1)
    # the tile's first pixel starts half a pixel west of 44.0
    assert left == pytest.approx(44 - PIXEL_DEG / 2)
    assert bottom < footprint[1]
    assert right > footprint[2]
    assert top > footprint[3]
    assert heights.min() > 0


def test_footprint_tile_missing_raises_even_when_the_margin_tile_exists(tmp_path: Path) -> None:
    server = TileServer({"N15_E044": tile_bytes(15, 44)})
    with pytest.raises(TileMissingError, match="N15_E043"):
        fetch_cog_window(server.client(), TILE_URL, (43.99, 15.3, 44.2, 15.5), tmp_path)


GROUND_BLOCK = "N10E040-N20E050"
GROUND_OFFSET_M = -5.0


def ground_source(zip_dir: Path) -> CogTilesWithZipGroundSource:
    return CogTilesWithZipGroundSource.model_validate(
        {
            "name": "test-ground",
            "adapter": "cog_tiles_with_zip_ground",
            "covers": [[0.0, 0.0, 90.0, 90.0]],
            "xy_crs": WGS84,
            "height_crs": "EPSG:4326+3855",
            "ground_is_surface": False,
            "licence": "l",
            "attribution": "a",
            "url_template": TILE_URL,
            "ground_path_template": f"/vsizip/{zip_dir}/{{block}}.zip/{{tile}}_FABDEM_V1-2.tif",
            "ground_index_url": "https://index.test/tiles.geojson",
        }
    )


def write_ground_zip(zip_dir: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(zip_dir / f"{GROUND_BLOCK}.zip", "w", zipfile.ZIP_STORED) as archive:
        for name, data in members.items():
            archive.writestr(f"{name}_FABDEM_V1-2.tif", data)


def index_geojson(tile_names: list[str]) -> bytes:
    """The FABDEM tile index lists tiles with a three-digit latitude."""
    features = [
        {
            "type": "Feature",
            "properties": {
                "tile_name": name,
                "file_name": f"{name}_FABDEM_V1-2.tif",
                "zipfile_name": f"{GROUND_BLOCK}_FABDEM_V1-2.zip",
            },
        }
        for name in tile_names
    ]
    return json.dumps({"type": "FeatureCollection", "features": features}).encode()


class GroundServers:
    """Serves GLO-30-style tiles and the ground index, counting requests per host."""

    def __init__(self, surface_tiles: dict[str, bytes], index_tiles: list[str]) -> None:
        self.surface = TileServer(surface_tiles)
        self.index_requests = 0
        self.index = index_geojson(index_tiles)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "index.test":
            self.index_requests += 1
            return httpx.Response(200, content=self.index)
        return self.surface(request)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


def read_window(surface: Surface) -> tuple[np.ndarray, rasterio.Affine, dict[str, str]]:
    with rasterio.open(surface.path) as src:
        return src.read(1), src.transform, src.tags()


def test_ground_comes_from_the_ground_tiles_on_the_surface_grid(tmp_path: Path) -> None:
    hole = (slice(30, 32), slice(40, 43))
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    write_ground_zip(
        zip_dir, {"N15E044": tile_bytes(15, 44, ground_offset_m=GROUND_OFFSET_M, hole=hole)}
    )
    servers = GroundServers({"N15_E044": tile_bytes(15, 44)}, ["N015E044"])
    footprint = Aoi(crs=WGS84, west=44.37, south=15.67, east=44.43, north=15.73)
    pair = fetch_surfaces_from_source(
        servers.client(), ground_source(zip_dir), footprint, tmp_path / "cache"
    )
    assert not pair.ground_is_surface
    assert pair.dsm.path != pair.dtm.path
    assert pair.dtm.height_crs == "EPSG:4326+3855"
    surface, surface_transform, _ = read_window(pair.dsm)
    ground, ground_transform, tags = read_window(pair.dtm)
    assert ground.shape == surface.shape
    assert ground_transform == surface_transform
    rows, cols = np.indices(surface.shape)
    lons = surface_transform.c + (cols + 0.5) * surface_transform.a
    lats = surface_transform.f + (rows + 0.5) * surface_transform.e
    # the hole covers tile rows 30-31 and columns 40-42: centres lon 44.40-44.42, lat 15.69-15.70
    in_hole = (
        (lons > 44.40 - PIXEL_DEG / 2)
        & (lons < 44.42 + PIXEL_DEG / 2)
        & (lats > 15.69 - PIXEL_DEG / 2)
        & (lats < 15.70 + PIXEL_DEG / 2)
    )
    assert in_hole.sum() == 6
    assert np.allclose(ground[in_hole], surface[in_hole])
    assert np.allclose(ground[~in_hole], surface[~in_hole] + GROUND_OFFSET_M, atol=1e-2)
    assert tags["FILLED_FROM_SURFACE_PIXELS"] == "6"


def test_ground_tile_absent_from_the_index_is_filled_from_the_surface(tmp_path: Path) -> None:
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    write_ground_zip(zip_dir, {"N15E044": tile_bytes(15, 44, ground_offset_m=GROUND_OFFSET_M)})
    servers = GroundServers(
        {"N15_E044": tile_bytes(15, 44), "N15_E045": tile_bytes(15, 45)}, ["N015E044"]
    )
    footprint = Aoi(crs=WGS84, west=44.97, south=15.4, east=45.03, north=15.45)
    pair = fetch_surfaces_from_source(
        servers.client(), ground_source(zip_dir), footprint, tmp_path / "cache"
    )
    surface, transform, _ = read_window(pair.dsm)
    ground, _, tags = read_window(pair.dtm)
    cols = np.indices(surface.shape)[1]
    east_of_tile = transform.c + (cols + 0.5) * transform.a > 45.0 - PIXEL_DEG / 2
    assert east_of_tile.any()
    assert np.allclose(ground[east_of_tile], surface[east_of_tile])
    assert np.allclose(ground[~east_of_tile], surface[~east_of_tile] + GROUND_OFFSET_M, atol=1e-2)
    assert int(tags["FILLED_FROM_SURFACE_PIXELS"]) == int(east_of_tile.sum())


def test_ground_window_without_any_ground_height_raises(tmp_path: Path) -> None:
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    write_ground_zip(
        zip_dir,
        {"N15E044": tile_bytes(15, 44, ground_offset_m=0.0, hole=(slice(None), slice(None)))},
    )
    servers = GroundServers({"N15_E044": tile_bytes(15, 44)}, ["N015E044"])
    footprint = Aoi(crs=WGS84, west=44.37, south=15.67, east=44.43, north=15.73)
    with pytest.raises(ValueError, match="no ground heights"):
        fetch_surfaces_from_source(
            servers.client(), ground_source(zip_dir), footprint, tmp_path / "cache"
        )


def test_ground_index_and_windows_are_fetched_once(tmp_path: Path) -> None:
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    write_ground_zip(zip_dir, {"N15E044": tile_bytes(15, 44, ground_offset_m=GROUND_OFFSET_M)})
    servers = GroundServers({"N15_E044": tile_bytes(15, 44)}, ["N015E044"])
    http = servers.client()
    source = ground_source(zip_dir)
    first = fetch_surfaces_from_source(
        http,
        source,
        Aoi(crs=WGS84, west=44.37, south=15.67, east=44.43, north=15.73),
        tmp_path / "c",
    )
    again = fetch_surfaces_from_source(
        http,
        source,
        Aoi(crs=WGS84, west=44.37, south=15.67, east=44.43, north=15.73),
        tmp_path / "c",
    )
    other = fetch_surfaces_from_source(
        http,
        source,
        Aoi(crs=WGS84, west=44.38, south=15.67, east=44.43, north=15.73),
        tmp_path / "c",
    )
    assert again == first
    assert other.dtm.path != first.dtm.path
    assert servers.index_requests == 1
    assert servers.surface.requests == ["N15_E044"]
