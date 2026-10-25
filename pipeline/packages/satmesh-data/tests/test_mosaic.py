import math
import warnings
from pathlib import Path

import httpx
import mercantile
import numpy as np
import pytest
from rasterio.errors import NotGeoreferencedWarning
from rasterio.io import MemoryFile

from satmesh_core import BRITISH_NATIONAL_GRID, Aoi, covering_tiles
from satmesh_data import EsriClient, Raster, crop_to_aoi, mosaic_tiles

ZOOM = 19
TILE_PX = 256
# 40 m square at Upper Aire, BNG metres
AOI = Aoi(crs=BRITISH_NATIONAL_GRID, west=399980, south=447480, east=400020, north=447520)
MARGIN_M = 5.0
# Web Mercator (EPSG:3857) on the WGS 84 sphere radius: x runs from -pi R to pi R
HALF_WORLD_M = math.pi * 6378137


def tile_colour(x: int, y: int) -> tuple[int, int, int]:
    return (x % 251, y % 241, (x + y) % 239)


def png_tile(x: int, y: int) -> bytes:
    """Solid-colour PNG: lossless, so decoded pixels are exactly `tile_colour`."""
    pixels = np.empty((3, TILE_PX, TILE_PX), np.uint8)
    pixels[:] = np.array(tile_colour(x, y), np.uint8)[:, None, None]
    with warnings.catch_warnings(), MemoryFile() as memory:
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with memory.open(
            driver="PNG", width=TILE_PX, height=TILE_PX, count=3, dtype="uint8"
        ) as dst:
            dst.write(pixels)
        data = memory.read()
    assert isinstance(data, bytes)
    return data


def tile_client(cache: Path) -> EsriClient:
    def handle(request: httpx.Request) -> httpx.Response:
        *_, _z, y, x = request.url.path.split("/")
        return httpx.Response(200, content=png_tile(int(x), int(y)))

    http = httpx.Client(transport=httpx.MockTransport(handle))
    return EsriClient(http, cache, min_interval_s=0.0, initial_backoff_s=0.0)


@pytest.fixture
def mosaic(tmp_path: Path) -> Raster:
    return mosaic_tiles(tile_client(tmp_path), covering_tiles(AOI, ZOOM, MARGIN_M), max_zoom=ZOOM)


def test_mosaic_places_each_tile_at_its_index(mosaic: Raster) -> None:
    tiles = covering_tiles(AOI, ZOOM, MARGIN_M)
    x0, y0 = min(t.x for t in tiles), min(t.y for t in tiles)
    for t in tiles:
        row, col = (t.y - y0) * TILE_PX, (t.x - x0) * TILE_PX
        block = mosaic.pixels[:, row : row + TILE_PX, col : col + TILE_PX]
        assert (block == np.array(tile_colour(t.x, t.y))[:, None, None]).all()


def test_mosaic_is_georeferenced_on_the_web_mercator_grid(mosaic: Raster) -> None:
    tiles = covering_tiles(AOI, ZOOM, MARGIN_M)
    tile_m = 2 * HALF_WORLD_M / 2**ZOOM
    x0, y0 = min(t.x for t in tiles), min(t.y for t in tiles)
    assert mosaic.crs == "EPSG:3857"
    t = mosaic.transform
    # rel 1e-9: pixel size is an edge-coordinate difference (float64, order 2e7 m)
    # divided by the pixel count
    assert (t.a, t.e) == pytest.approx((tile_m / TILE_PX, -tile_m / TILE_PX), rel=1e-9)
    # 1e-6 m: float64 rounding on coordinates of order 2e7 m
    assert (t.c, t.f) == pytest.approx(
        (-HALF_WORLD_M + x0 * tile_m, HALF_WORLD_M - y0 * tile_m), abs=1e-6
    )


def test_crop_is_the_smallest_pixel_window_holding_the_grown_aoi(mosaic: Raster) -> None:
    crop = crop_to_aoi(mosaic, AOI, MARGIN_M)
    west, south, east, north = AOI.grown(MARGIN_M).bounds_in("EPSG:3857")
    pixel_m = crop.transform.a
    rows, cols = crop.pixels.shape[1:]
    crop_west, crop_north = crop.transform.c, crop.transform.f
    crop_east, crop_south = crop_west + cols * pixel_m, crop_north - rows * pixel_m
    assert crop_west <= west < crop_west + pixel_m
    assert crop_east - pixel_m < east <= crop_east
    assert crop_south <= south < crop_south + pixel_m
    assert crop_north - pixel_m < north <= crop_north
    col = round((crop_west - mosaic.transform.c) / pixel_m)
    row = round((mosaic.transform.f - crop_north) / pixel_m)
    assert (crop.pixels == mosaic.pixels[:, row : row + rows, col : col + cols]).all()


def test_crop_beyond_the_mosaic_is_an_error(mosaic: Raster) -> None:
    with pytest.raises(ValueError, match="does not cover"):
        crop_to_aoi(mosaic, AOI, margin_m=500.0)


def test_tiles_must_fill_a_rectangle(tmp_path: Path) -> None:
    tiles = covering_tiles(AOI, ZOOM, MARGIN_M)
    assert len(tiles) > 1
    with pytest.raises(ValueError, match="rectangle"):
        mosaic_tiles(tile_client(tmp_path), tiles[1:], max_zoom=ZOOM)


def test_tiles_must_share_a_zoom(tmp_path: Path) -> None:
    tiles = [mercantile.Tile(1, 1, ZOOM), mercantile.Tile(1, 1, ZOOM - 1)]
    with pytest.raises(ValueError, match="zooms"):
        mosaic_tiles(tile_client(tmp_path), tiles, max_zoom=ZOOM)
