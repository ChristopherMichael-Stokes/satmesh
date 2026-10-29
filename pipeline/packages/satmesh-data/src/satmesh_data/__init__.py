"""Cached, throttled fetch of Esri World Imagery tiles and scenes and EA lidar surfaces; mosaics."""

from satmesh_data.ea_aerial import AerialTile, crop_aerial, fetch_aerial_ecws, find_aerial_tiles
from satmesh_data.ea_lidar import (
    EA_DSM,
    EA_DTM,
    EaLidarProduct,
    LidarCheckError,
    cached_lidar_path,
    check_lidar,
    fetch_ea_lidar,
)
from satmesh_data.ea_lidar_points import (
    PointCloudTile,
    fetch_point_cloud,
    find_point_cloud_tiles,
    os_tile_id,
    tile_ids_covering,
)
from satmesh_data.esri import (
    EsriClient,
    EsriSource,
    PlaceholderTileError,
    ZoomBeyondSourceError,
    choose_zoom,
    is_placeholder,
)
from satmesh_data.esri_scenes import (
    UNLABELLED,
    EsriQueryError,
    EsriScene,
    SceneId,
    SceneMap,
    fetch_scene_map,
)
from satmesh_data.http import USER_AGENT, RetryableStatusError, new_client
from satmesh_data.mosaic import WEB_MERCATOR, Raster, crop_to_aoi, decode_tile, mosaic_tiles

__all__ = [
    "EA_DSM",
    "EA_DTM",
    "UNLABELLED",
    "USER_AGENT",
    "WEB_MERCATOR",
    "AerialTile",
    "EaLidarProduct",
    "EsriClient",
    "EsriQueryError",
    "EsriScene",
    "EsriSource",
    "LidarCheckError",
    "PlaceholderTileError",
    "PointCloudTile",
    "Raster",
    "RetryableStatusError",
    "SceneId",
    "SceneMap",
    "ZoomBeyondSourceError",
    "cached_lidar_path",
    "check_lidar",
    "choose_zoom",
    "crop_aerial",
    "crop_to_aoi",
    "decode_tile",
    "fetch_aerial_ecws",
    "fetch_ea_lidar",
    "fetch_point_cloud",
    "fetch_scene_map",
    "find_aerial_tiles",
    "find_point_cloud_tiles",
    "is_placeholder",
    "mosaic_tiles",
    "new_client",
    "os_tile_id",
    "tile_ids_covering",
]
