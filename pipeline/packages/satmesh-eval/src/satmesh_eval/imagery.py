"""Imagery inputs of the comparisons: an EA aerial crop and an Esri mosaic over the same box."""

from pathlib import Path

import mercantile
import rasterio

from satmesh_core import Aoi
from satmesh_data import EsriClient, Raster, mosaic_tiles

RGB_BANDS = (1, 2, 3)


def read_rgb_geotiff(path: Path) -> Raster:
    """Read the first three bands of a GeoTIFF as an RGB `Raster` in the file's own CRS."""
    with rasterio.open(path) as src:
        return Raster(src.read(list(RGB_BANDS)), src.transform, src.crs.to_string())


def esri_raster_over(client: EsriClient, box: Aoi, zoom: int) -> Raster:
    """Return the Esri tiles at `zoom` that cover `box`, stitched in EPSG:3857."""
    tiles = list(mercantile.tiles(*box.wgs84_bounds(), [zoom]))
    return mosaic_tiles(client, tiles, zoom)
