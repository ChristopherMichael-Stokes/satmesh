"""Area of interest, metric CRS and Web Mercator tile geometry shared by all satmesh packages."""

from satmesh_core.aoi import BRITISH_NATIONAL_GRID, WGS84, Aoi, metric_crs
from satmesh_core.gsd import ground_sample_distance_m, zoom_for_resolution
from satmesh_core.tiles import covering_tiles

__all__ = [
    "BRITISH_NATIONAL_GRID",
    "WGS84",
    "Aoi",
    "covering_tiles",
    "ground_sample_distance_m",
    "metric_crs",
    "zoom_for_resolution",
]
