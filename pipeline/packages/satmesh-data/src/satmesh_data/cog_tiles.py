"""Surface models published as 1-degree GeoTIFF tiles named by their south-west corner.

Copernicus GLO-30 tiles are point-registered (`AREA_OR_POINT=Point`): pixel (0, 0) is centred on
the tile's north-west integer-degree corner, so the pixel at row i, column j of tile (lat, lon) is
centred on lon + j * dx, lat + 1 - i * dy. GDAL reads that as a geotransform origin half a pixel
outside the corner, which makes `centre = origin + (index + 0.5) * pixel size` hold for every pixel.
Everything here goes through the GDAL geotransform, so windows keep that convention.
"""

import math
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.merge import merge
from rasterio.transform import Affine

from satmesh_data.http import DEFAULT_INITIAL_BACKOFF_S, checked, with_retry

GEOGRAPHIC_CRS = "EPSG:4326"
NODATA_M = -9999.0
MARGIN_PIXELS = 2
# GLO-30 pixel size at latitudes below 50 degrees, the finest the product has: 1 arc-second
NOMINAL_PIXEL_DEG = 1 / 3600
TILES_SUBDIR = Path("tiles")
WINDOWS_SUBDIR = Path("windows")
HTTP_NOT_FOUND = 404
# GDAL can be told to ignore the point-registration half-pixel shift; the shift must be applied
# pixel-index slack when snapping a window edge that already lies on a pixel edge
SNAP_TOLERANCE_PIXELS = 1e-6
POINT_GEO_OPTION = {"GTIFF_POINT_GEO_IGNORE": "FALSE"}


class TileMissingError(Exception):
    """The server has no tile for a 1-degree cell, which for GLO-30 means open sea."""


@dataclass(frozen=True)
class TileId:
    """A 1-degree tile, named by the integer degrees of its south-west corner."""

    south: int
    west: int

    @property
    def name(self) -> str:
        """Return e.g. `N15_E044`."""
        ns = "N" if self.south >= 0 else "S"
        ew = "E" if self.west >= 0 else "W"
        return f"{ns}{abs(self.south):02d}_{ew}{abs(self.west):03d}"

    @property
    def compact_name(self) -> str:
        """Return the name without the underscore, e.g. `N15E044`, as FABDEM files are named."""
        return self.name.replace("_", "")

    def url(self, url_template: str) -> str:
        """Return `url_template` filled with this tile's hemisphere letters and whole degrees."""
        return url_template.format(
            ns="N" if self.south >= 0 else "S",
            lat=abs(self.south),
            ew="E" if self.west >= 0 else "W",
            lon=abs(self.west),
        )


def fetch_cog_window(
    http: httpx.Client,
    url_template: str,
    footprint: tuple[float, float, float, float],
    cache_dir: Path,
    initial_backoff_s: float = DEFAULT_INITIAL_BACKOFF_S,
) -> Path:
    """Return a float32 EPSG:4326 GeoTIFF (m) covering `footprint` plus two pixels, from the tiles.

    `footprint` is `(west, south, east, north)` in degrees. Whole tiles are cached under
    `cache_dir/tiles`, windows under `cache_dir/windows`. The window is aligned to the tiles'
    pixel grid, so no height is resampled unless neighbouring tiles differ in pixel size. A tile the
    footprint itself needs and the server lacks raises `TileMissingError`. A tile needed only for
    the margin and lacked by the server (open sea beside a coast) drops the margin on that side. A
    window with a hole raises `ValueError`.
    """
    key = "_".join(f"{edge:.7f}" for edge in footprint)
    path = cache_dir / WINDOWS_SUBDIR / f"{key}.tif"
    if path.exists():
        return path
    tiles: dict[TileId, Path | None] = {}
    pixel_deg = (NOMINAL_PIXEL_DEG, NOMINAL_PIXEL_DEG)
    # tile extents depend on pixel size, which is known only once a tile is read
    while missing := [
        tile
        for tile in tiles_covering(_expanded(footprint, pixel_deg), pixel_deg)
        if tile not in tiles
    ]:
        for tile in missing:
            tiles[tile] = _download_tile(http, url_template, tile, cache_dir, initial_backoff_s)
        present = [path for path in tiles.values() if path is not None]
        if present:
            pixel_deg = _coarsest_pixel(present)
    required = tiles_covering(footprint, pixel_deg)
    for tile in required:
        if tiles[tile] is None:
            msg = f"no tile {tile.name} at {tile.url(url_template)}: open sea"
            raise TileMissingError(msg)
    window = _clamped_to_required(
        _expanded(footprint, pixel_deg),
        required,
        [tile for tile, path in tiles.items() if path is None],
        pixel_deg,
    )
    present = [path for path in tiles.values() if path is not None]
    heights, transform = _merged_window(present, window)
    if (heights == NODATA_M).any():
        msg = f"tiles {[tile.name for tile in tiles]} leave a hole in window {window}"
        raise ValueError(msg)
    _write_window(path, heights, transform)
    return path


def _expanded(
    box: tuple[float, float, float, float], pixel_deg: tuple[float, float]
) -> tuple[float, float, float, float]:
    west, south, east, north = box
    dx, dy = (MARGIN_PIXELS * size for size in pixel_deg)
    return west - dx, south - dy, east + dx, north + dy


def tiles_covering(
    box: tuple[float, float, float, float], pixel_deg: tuple[float, float]
) -> list[TileId]:
    """Return the tiles whose pixel extents meet `box`.

    A tile's pixels span [west - dx/2, west + 1 - dx/2) in longitude and (south + dy/2,
    north + dy/2] in latitude, because pixel centres sit on the integer-degree lines.
    """
    west, south, east, north = box
    half_x, half_y = pixel_deg[0] / 2, pixel_deg[1] / 2
    first_west = math.floor(west + half_x)
    last_west = math.ceil(east + half_x) - 1
    first_south = math.ceil(south - half_y) - 1
    last_south = math.ceil(north - half_y) - 1
    return [
        TileId(south=lat, west=lon)
        for lat in range(first_south, last_south + 1)
        for lon in range(first_west, last_west + 1)
    ]


def _clamped_to_required(
    window: tuple[float, float, float, float],
    required: list[TileId],
    absent: list[TileId],
    pixel_deg: tuple[float, float],
) -> tuple[float, float, float, float]:
    """Return `window` cut back to the required tiles' pixel extent where a neighbour is absent."""
    half_x, half_y = pixel_deg[0] / 2, pixel_deg[1] / 2
    west, south, east, north = window
    first_west, last_west = min(t.west for t in required), max(t.west for t in required)
    first_south, last_south = min(t.south for t in required), max(t.south for t in required)
    if any(t.west < first_west for t in absent):
        west = max(west, first_west - half_x)
    if any(t.west > last_west for t in absent):
        east = min(east, last_west + 1 - half_x)
    if any(t.south < first_south for t in absent):
        south = max(south, first_south + half_y)
    if any(t.south > last_south for t in absent):
        north = min(north, last_south + 1 + half_y)
    return west, south, east, north


def _download_tile(
    http: httpx.Client,
    url_template: str,
    tile: TileId,
    cache_dir: Path,
    initial_backoff_s: float,
) -> Path | None:
    """Return the cached tile file, downloading it first; None when the server has no such tile."""
    path = cache_dir / TILES_SUBDIR / f"{tile.name}.tif"
    if path.exists():
        return path
    try:
        response = with_retry(lambda: checked(http.get(tile.url(url_template))), initial_backoff_s)
    except httpx.HTTPStatusError as error:
        if error.response.status_code != HTTP_NOT_FOUND:
            raise
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    partial.write_bytes(response.content)
    partial.replace(path)
    return path


def _coarsest_pixel(paths: list[Path]) -> tuple[float, float]:
    sizes: list[tuple[float, float]] = []
    for path in paths:
        with rasterio.Env(**POINT_GEO_OPTION), rasterio.open(path) as src:
            res_x, res_y = src.res
            sizes.append((float(res_x), float(res_y)))
    return max(x for x, _ in sizes), max(y for _, y in sizes)


def _merged_window(
    paths: list[Path], window: tuple[float, float, float, float]
) -> tuple[np.ndarray, Affine]:
    """Return the tiles' heights over `window` grown to the finest tile's pixel grid."""
    with rasterio.Env(**POINT_GEO_OPTION):
        sources = [rasterio.open(path) for path in paths]
        try:
            finest = min(sources, key=lambda src: src.res)
            res_x, res_y = finest.res
            origin = finest.transform
            west, south, east, north = window
            snapped = (
                origin.c + math.floor((west - origin.c) / res_x + SNAP_TOLERANCE_PIXELS) * res_x,
                origin.f - math.ceil((origin.f - south) / res_y - SNAP_TOLERANCE_PIXELS) * res_y,
                origin.c + math.ceil((east - origin.c) / res_x - SNAP_TOLERANCE_PIXELS) * res_x,
                origin.f - math.floor((origin.f - north) / res_y + SNAP_TOLERANCE_PIXELS) * res_y,
            )
            data, transform = merge(
                sources,
                bounds=snapped,
                res=(res_x, res_y),
                nodata=NODATA_M,
                dtype="float32",
                resampling=Resampling.bilinear,
            )
        finally:
            for src in sources:
                src.close()
    return data[0], transform


def _write_window(path: Path, heights: np.ndarray, transform: Affine) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    with rasterio.open(
        partial,
        "w",
        driver="GTiff",
        width=heights.shape[1],
        height=heights.shape[0],
        count=1,
        dtype="float32",
        crs=GEOGRAPHIC_CRS,
        transform=transform,
        compress="deflate",
    ) as dst:
        dst.write(heights, 1)
    partial.replace(path)
