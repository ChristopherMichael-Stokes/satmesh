"""Cached, throttled fetch of Esri World Imagery tiles and EA lidar DTMs; tile mosaics."""

from satmesh_data.ea_dtm import DtmCheckError, check_dtm, fetch_ea_dtm
from satmesh_data.esri import (
    EsriClient,
    EsriSource,
    PlaceholderTileError,
    ZoomBeyondSourceError,
    choose_zoom,
    is_placeholder,
)
from satmesh_data.http import USER_AGENT, RetryableStatusError, new_client
from satmesh_data.mosaic import WEB_MERCATOR, Raster, crop_to_aoi, decode_tile, mosaic_tiles

__all__ = [
    "USER_AGENT",
    "WEB_MERCATOR",
    "DtmCheckError",
    "EsriClient",
    "EsriSource",
    "PlaceholderTileError",
    "Raster",
    "RetryableStatusError",
    "ZoomBeyondSourceError",
    "check_dtm",
    "choose_zoom",
    "crop_to_aoi",
    "decode_tile",
    "fetch_ea_dtm",
    "is_placeholder",
    "mosaic_tiles",
    "new_client",
]
