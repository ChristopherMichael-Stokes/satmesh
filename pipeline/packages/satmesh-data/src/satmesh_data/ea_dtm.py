"""Environment Agency LIDAR Composite 1 m DTM for England, by WCS 2.0.1 GetCoverage."""

from pathlib import Path

import httpx
import numpy as np
import rasterio
from pyproj import CRS

from satmesh_core import BRITISH_NATIONAL_GRID, Aoi
from satmesh_data.http import DEFAULT_INITIAL_BACKOFF_S, checked, with_retry

WCS_URL = (
    "https://environment.data.gov.uk/spatialdata/lidar-composite-digital-terrain-model-dtm-1m/wcs"
)
DTM_COVERAGE_ID = "13787b9a-26a4-4775-8523-806d13af58fc__Lidar_Composite_Elevation_DTM_1m"
PIXEL_SIZE_M = 1.0
CACHE_SUBDIR = Path("ea-lidar-composite")


class DtmCheckError(Exception):
    """The WCS returned a raster that is not the requested 1 m BNG grid, or that has gaps."""


def fetch_ea_dtm(
    http: httpx.Client,
    box: Aoi,
    cache_dir: Path,
    initial_backoff_s: float = DEFAULT_INITIAL_BACKOFF_S,
) -> Path:
    """Return the path of a GeoTIFF of heights in metres covering `box`, fetching it if not cached.

    `box` must be in BNG with whole-metre edges, so it lands on the 1 m grid. A response that fails
    `check_dtm` raises `DtmCheckError` and is not cached.
    """
    if box.crs != BRITISH_NATIONAL_GRID:
        msg = f"EA DTM boxes are in {BRITISH_NATIONAL_GRID}, got {box.crs}"
        raise ValueError(msg)
    edges = (box.west, box.south, box.east, box.north)
    if not all(edge.is_integer() for edge in edges):
        msg = f"EA DTM box edges must be whole metres, got {edges}"
        raise ValueError(msg)
    west, south, east, north = (int(edge) for edge in edges)
    path = cache_dir / CACHE_SUBDIR / DTM_COVERAGE_ID / f"{west}_{south}_{east}_{north}.tif"
    if path.exists():
        return path
    params = httpx.QueryParams(
        [
            ("service", "WCS"),
            ("version", "2.0.1"),
            ("request", "GetCoverage"),
            ("coverageId", DTM_COVERAGE_ID),
            ("format", "image/tiff"),
            ("subset", f"E({west},{east})"),
            ("subset", f"N({south},{north})"),
        ]
    )
    response = with_retry(lambda: checked(http.get(WCS_URL, params=params)), initial_backoff_s)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    partial.write_bytes(response.content)
    try:
        check_dtm(partial, box)
    except DtmCheckError:
        partial.unlink()
        raise
    partial.replace(path)
    return path


def check_dtm(path: Path, box: Aoi) -> None:
    """Raise `DtmCheckError` unless `path` is a gap-free 1 m BNG raster bounded exactly by `box`."""
    with rasterio.open(path) as src:
        if src.crs is None or not CRS.from_wkt(src.crs.to_wkt()).equals(
            BRITISH_NATIONAL_GRID, ignore_axis_order=True
        ):
            msg = f"CRS is {src.crs}, not {BRITISH_NATIONAL_GRID}"
            raise DtmCheckError(msg)
        if src.res != (PIXEL_SIZE_M, PIXEL_SIZE_M):
            msg = f"pixel size is {src.res}, not {PIXEL_SIZE_M} m"
            raise DtmCheckError(msg)
        bounds = tuple(src.bounds)
        if bounds != (box.west, box.south, box.east, box.north):
            msg = f"bounds are {bounds}, not the requested box"
            raise DtmCheckError(msg)
        gaps = int(np.ma.count_masked(src.read(1, masked=True)))
    if gaps:
        msg = f"{gaps} nodata pixels"
        raise DtmCheckError(msg)
