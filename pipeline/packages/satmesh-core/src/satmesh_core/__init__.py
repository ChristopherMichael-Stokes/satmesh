"""Area of interest, metric CRS and Web Mercator tile geometry shared by all satmesh packages."""

from satmesh_core.aoi import BRITISH_NATIONAL_GRID, WGS84, Aoi, metric_crs
from satmesh_core.georef import (
    BNG_ODN,
    NAD83_2011,
    NAD83_2011_TO_WGS84_EPOCH,
    NAVD88_HEIGHT,
    EnuFrame,
    GridMissingError,
    ecef_to_geodetic,
    ellipsoidal_height_from,
    geodetic_to_ecef,
    require_best_transformer,
    wgs84_to,
)
from satmesh_core.gsd import ground_sample_distance_m, zoom_for_resolution
from satmesh_core.progress import ProgressReport
from satmesh_core.tiles import covering_tiles

__all__ = [
    "BNG_ODN",
    "BRITISH_NATIONAL_GRID",
    "NAD83_2011",
    "NAD83_2011_TO_WGS84_EPOCH",
    "NAVD88_HEIGHT",
    "WGS84",
    "Aoi",
    "EnuFrame",
    "GridMissingError",
    "ProgressReport",
    "covering_tiles",
    "ecef_to_geodetic",
    "ellipsoidal_height_from",
    "geodetic_to_ecef",
    "ground_sample_distance_m",
    "metric_crs",
    "require_best_transformer",
    "wgs84_to",
    "zoom_for_resolution",
]
