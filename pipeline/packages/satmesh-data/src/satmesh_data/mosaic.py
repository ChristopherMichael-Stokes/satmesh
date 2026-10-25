"""Esri tiles stitched into one georeferenced Web Mercator raster, cropped to an AOI."""

import math
import warnings
from dataclasses import dataclass
from typing import NamedTuple

import mercantile
import numpy as np
from affine import Affine
from rasterio.errors import NotGeoreferencedWarning
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds

from satmesh_core import Aoi
from satmesh_data.esri import EsriClient

WEB_MERCATOR = "EPSG:3857"
TILE_PX = 256
RGB_BANDS = 3
RASTER_AXES = 3  # band, row, col


@dataclass(frozen=True)
class Raster:
    """RGB pixels `(band, row, col)` in uint8, placed by `transform` in `crs` units."""

    pixels: np.ndarray
    transform: Affine
    crs: str

    def __post_init__(self) -> None:
        """Reject anything but a non-empty 3-band uint8 array."""
        shape = self.pixels.shape
        if (
            self.pixels.dtype != np.uint8
            or len(shape) != RASTER_AXES
            or shape[0] != RGB_BANDS
            or 0 in shape
        ):
            msg = f"expected uint8 (3, rows, cols), got {self.pixels.dtype} {self.pixels.shape}"
            raise ValueError(msg)


def mosaic_tiles(client: EsriClient, tiles: list[mercantile.Tile], max_zoom: int) -> Raster:
    """Fetch `tiles` and stitch them into one EPSG:3857 raster.

    The tiles must share one zoom and fill a rectangle, as `covering_tiles` returns them.
    """
    xs, ys = _tile_rectangle(tiles)
    pixels = np.empty((RGB_BANDS, len(ys) * TILE_PX, len(xs) * TILE_PX), np.uint8)
    for tile in tiles:
        row, col = (tile.y - ys[0]) * TILE_PX, (tile.x - xs[0]) * TILE_PX
        pixels[:, row : row + TILE_PX, col : col + TILE_PX] = decode_tile(
            client.tile(tile, max_zoom)
        )
    zoom = tiles[0].z
    upper_left = mercantile.xy_bounds(mercantile.Tile(xs[0], ys[0], zoom))
    lower_right = mercantile.xy_bounds(mercantile.Tile(xs[-1], ys[-1], zoom))
    transform = from_bounds(
        upper_left.left,
        lower_right.bottom,
        lower_right.right,
        upper_left.top,
        pixels.shape[2],
        pixels.shape[1],
    )
    return Raster(pixels, transform, WEB_MERCATOR)


def crop_to_aoi(raster: Raster, aoi: Aoi, margin_m: float) -> Raster:
    """Return the smallest whole-pixel window of `raster` holding `aoi` grown by `margin_m`.

    The margin is in ground metres.

    Raises `ValueError` if `raster` does not cover the grown AOI.
    """
    west, south, east, north = aoi.grown(margin_m).bounds_in(raster.crs)
    window = _outward_window(raster.transform, west, south, east, north)
    rows, cols = raster.pixels.shape[1:]
    if window.row < 0 or window.col < 0 or window.row_end > rows or window.col_end > cols:
        msg = f"raster does not cover the AOI grown by {margin_m} m: {window} in {rows} x {cols} px"
        raise ValueError(msg)
    pixels = raster.pixels[:, window.row : window.row_end, window.col : window.col_end].copy()
    return Raster(pixels, raster.transform @ Affine.translation(window.col, window.row), raster.crs)


def decode_tile(data: bytes) -> np.ndarray:
    """Decode one tile image to uint8 `(3, 256, 256)`."""
    # a tile image carries no georeference; its place comes from (z, y, x)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with MemoryFile(data) as memory, memory.open() as src:
            pixels = src.read()
    if pixels.shape != (RGB_BANDS, TILE_PX, TILE_PX) or pixels.dtype != np.uint8:
        msg = f"tile decoded to {pixels.dtype} {pixels.shape}, expected uint8 (3, 256, 256)"
        raise ValueError(msg)
    return pixels


def _tile_rectangle(tiles: list[mercantile.Tile]) -> tuple[list[int], list[int]]:
    if not tiles:
        msg = "no tiles"
        raise ValueError(msg)
    zooms = {tile.z for tile in tiles}
    if len(zooms) != 1:
        msg = f"tiles span zooms {sorted(zooms)}"
        raise ValueError(msg)
    xs, ys = sorted({tile.x for tile in tiles}), sorted({tile.y for tile in tiles})
    full = {(x, y) for x in range(xs[0], xs[-1] + 1) for y in range(ys[0], ys[-1] + 1)}
    if {(tile.x, tile.y) for tile in tiles} != full:
        msg = f"tiles do not fill the rectangle x {xs[0]}..{xs[-1]}, y {ys[0]}..{ys[-1]}"
        raise ValueError(msg)
    return list(range(xs[0], xs[-1] + 1)), list(range(ys[0], ys[-1] + 1))


class _PixelWindow(NamedTuple):
    row: int
    col: int
    row_end: int
    col_end: int


def _outward_window(
    transform: Affine, west: float, south: float, east: float, north: float
) -> _PixelWindow:
    """Whole-pixel window enclosing the box, for a north-up `transform`."""
    col_start, row_start = ~transform @ (west, north)
    col_stop, row_stop = ~transform @ (east, south)
    return _PixelWindow(
        math.floor(row_start), math.floor(col_start), math.ceil(row_stop), math.ceil(col_stop)
    )
