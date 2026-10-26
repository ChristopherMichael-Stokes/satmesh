"""Area of interest, metric CRS and Web Mercator tile geometry shared by all satmesh packages."""

from satmesh_core.aoi import BRITISH_NATIONAL_GRID, WGS84, Aoi, metric_crs
from satmesh_core.georef import (
    EnuFrame,
    GridMissingError,
    bng_odn_to_wgs84,
    ecef_to_geodetic,
    geodetic_to_ecef,
    require_best_transformer,
    wgs84_to_bng,
)
from satmesh_core.gsd import ground_sample_distance_m, zoom_for_resolution
from satmesh_core.progress import ProgressReport
from satmesh_core.tiles import covering_tiles

__all__ = [
    "BRITISH_NATIONAL_GRID",
    "WGS84",
    "Aoi",
    "EnuFrame",
    "GridMissingError",
    "ProgressReport",
    "bng_odn_to_wgs84",
    "covering_tiles",
    "ecef_to_geodetic",
    "geodetic_to_ecef",
    "ground_sample_distance_m",
    "metric_crs",
    "require_best_transformer",
    "wgs84_to_bng",
    "zoom_for_resolution",
]
