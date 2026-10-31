"""FABDEM-style bare-earth tiles read in place from zip blocks, on a surface window's grid.

FABDEM is GLO-30 with forests and buildings removed, so its tiles share GLO-30's point-registered
pixel grid. A ground window is the FABDEM heights over exactly the bounds of a surface window,
which makes both rasters pixel-for-pixel identical in shape and transform. Pixels FABDEM leaves
empty (sea and large water) take the surface window's value, which GLO-30 flattens over water.
"""

import json
import logging
import re
from pathlib import Path

import httpx
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.merge import merge
from rasterio.transform import Affine

from satmesh_data.cog_tiles import (
    GEOGRAPHIC_CRS,
    NODATA_M,
    POINT_GEO_OPTION,
    TileId,
    tiles_covering,
)
from satmesh_data.http import DEFAULT_INITIAL_BACKOFF_S, checked, with_retry

logger = logging.getLogger(__name__)

GROUND_WINDOWS_SUBDIR = Path("ground-windows")
BLOCK_INDEX_FILE = "ground-blocks.json"
FILLED_PIXELS_TAG = "FILLED_FROM_SURFACE_PIXELS"
# Zip members are read by range requests: the listing request GDAL would make for the 1.7 GB blocks
# is skipped and only .zip and .tif URLs are probed
GDAL_ZIP_OPTIONS = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".zip,.tif",
}
# the index names tiles with a three-digit latitude, e.g. N015E044 for the file N15E044_*.tif
INDEX_TILE_NAME = re.compile(r"(?P<ns>[NS])(?P<lat>\d{3})(?P<ew>[EW])(?P<lon>\d{3})")
BLOCK_NAME_SEPARATOR = "_"


def fetch_ground_window(  # noqa: PLR0913, PLR0917 (one source's access parameters)
    http: httpx.Client,
    path_template: str,
    index_url: str,
    surface_window: Path,
    cache_dir: Path,
    initial_backoff_s: float = DEFAULT_INITIAL_BACKOFF_S,
) -> Path:
    """Return a GeoTIFF of ground heights (m) on the grid of the GeoTIFF `surface_window`.

    Tiles absent from the index are treated as empty. Empty pixels are filled from
    `surface_window` and counted in the `FILLED_FROM_SURFACE_PIXELS` tag and the log. A window with
    no ground pixel at all raises `ValueError`. Windows are cached under `cache_dir/ground-windows`
    by the surface window's file name.
    """
    path = cache_dir / GROUND_WINDOWS_SUBDIR / surface_window.name
    if path.exists():
        return path
    with rasterio.open(surface_window) as surface_src:
        surface = surface_src.read(1)
        bounds = tuple(surface_src.bounds)
        transform = surface_src.transform
        res = surface_src.res
    index = _block_index(http, index_url, cache_dir, initial_backoff_s)
    tiles = [tile for tile in tiles_covering(bounds, res) if tile in index]
    paths = [path_template.format(block=index[tile], tile=tile.compact_name) for tile in tiles]
    ground = _read_ground(paths, bounds, res)
    if ground.shape != surface.shape:
        msg = f"ground window is {ground.shape}, surface window {surface.shape}"
        raise ValueError(msg)
    empty = ground == NODATA_M
    filled = int(empty.sum())
    if filled == empty.size:
        msg = f"no ground heights in {surface_window.name}: tiles {[t.name for t in tiles]}"
        raise ValueError(msg)
    ground[empty] = surface[empty]
    logger.info(
        "ground window %s: %d of %d pixels filled from the surface", path.name, filled, ground.size
    )
    _write(path, ground, transform, filled)
    return path


def _block_index(
    http: httpx.Client, index_url: str, cache_dir: Path, initial_backoff_s: float
) -> dict[TileId, str]:
    """Return each ground tile's block name, from the cached index or the downloaded GeoJSON."""
    cached = cache_dir / BLOCK_INDEX_FILE
    if not cached.exists():
        response = with_retry(lambda: checked(http.get(index_url)), initial_backoff_s)
        entries = [
            (tile.south, tile.west, block)
            for tile, block in (
                _index_entry(feature["properties"]) for feature in response.json()["features"]
            )
        ]
        cache_dir.mkdir(parents=True, exist_ok=True)
        partial = cached.with_suffix(".part")
        partial.write_text(json.dumps(entries))
        partial.replace(cached)
    return {
        TileId(south=south, west=west): block
        for south, west, block in json.loads(cached.read_text())
    }


def _index_entry(properties: dict[str, str]) -> tuple[TileId, str]:
    name = properties["tile_name"]
    match = INDEX_TILE_NAME.fullmatch(name)
    if match is None:
        msg = f"unexpected tile name {name!r} in the ground index"
        raise ValueError(msg)
    lat, lon = int(match["lat"]), int(match["lon"])
    tile = TileId(
        south=lat if match["ns"] == "N" else -lat, west=lon if match["ew"] == "E" else -lon
    )
    return tile, properties["zipfile_name"].split(BLOCK_NAME_SEPARATOR)[0]


def _read_ground(
    paths: list[str],
    bounds: tuple[float, float, float, float],
    res: tuple[float, float],
) -> np.ndarray:
    """Return the tiles' heights over `bounds` on the grid of resolution `res`; gaps NODATA_M."""
    with rasterio.Env(**GDAL_ZIP_OPTIONS, **POINT_GEO_OPTION):
        sources = [rasterio.open(path) for path in paths]
        try:
            data, _ = merge(
                sources,
                bounds=bounds,
                res=res,
                nodata=NODATA_M,
                dtype="float32",
                resampling=Resampling.nearest,
            )
        finally:
            for src in sources:
                src.close()
    return data[0]


def _write(path: Path, ground: np.ndarray, transform: Affine, filled: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    with rasterio.open(
        partial,
        "w",
        driver="GTiff",
        width=ground.shape[1],
        height=ground.shape[0],
        count=1,
        dtype="float32",
        crs=GEOGRAPHIC_CRS,
        transform=transform,
        compress="deflate",
    ) as dst:
        dst.write(ground, 1)
        dst.update_tags(**{FILLED_PIXELS_TAG: str(filled)})
    partial.replace(path)
