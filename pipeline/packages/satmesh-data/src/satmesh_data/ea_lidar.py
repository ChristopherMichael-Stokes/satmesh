"""Environment Agency LIDAR Composite 1 m DTM and first-return DSM for England, by WCS 2.0.1."""

from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np
import rasterio
from pyproj import CRS

from satmesh_core import BRITISH_NATIONAL_GRID, Aoi
from satmesh_data.http import DEFAULT_INITIAL_BACKOFF_S, checked, with_retry


@dataclass(frozen=True)
class EaLidarProduct:
    """One EA LIDAR Composite WCS coverage."""

    wcs_url: str
    coverage_id: str


EA_DTM = EaLidarProduct(
    "https://environment.data.gov.uk/spatialdata/lidar-composite-digital-terrain-model-dtm-1m/wcs",
    "13787b9a-26a4-4775-8523-806d13af58fc__Lidar_Composite_Elevation_DTM_1m",
)
EA_DSM = EaLidarProduct(
    "https://environment.data.gov.uk/spatialdata/"
    "lidar-composite-digital-surface-model-first-return-dsm-1m/wcs",
    "df4e3ec3-315e-48aa-aaaf-b5ae74d7b2bb__Lidar_Composite_Elevation_FZ_DSM_1m",
)
PIXEL_SIZE_M = 1.0
CACHE_SUBDIR = Path("ea-lidar-composite")


class LidarCheckError(Exception):
    """The WCS returned a raster that is not the requested 1 m BNG grid, or that has gaps."""


def fetch_ea_lidar(
    http: httpx.Client,
    box: Aoi,
    cache_dir: Path,
    product: EaLidarProduct,
    initial_backoff_s: float = DEFAULT_INITIAL_BACKOFF_S,
) -> Path:
    """Return the path of a GeoTIFF of `product` heights (m) over `box`, fetching it if not cached.

    `box` must be in BNG with whole-metre edges, so it lands on the 1 m grid. A response that fails
    `check_lidar` raises `LidarCheckError` and is not cached.
    """
    if box.crs != BRITISH_NATIONAL_GRID:
        msg = f"EA lidar boxes are in {BRITISH_NATIONAL_GRID}, got {box.crs}"
        raise ValueError(msg)
    edges = (box.west, box.south, box.east, box.north)
    if not all(edge.is_integer() for edge in edges):
        msg = f"EA lidar box edges must be whole metres, got {edges}"
        raise ValueError(msg)
    west, south, east, north = (int(edge) for edge in edges)
    path = cached_lidar_path(cache_dir, product, f"{west}_{south}_{east}_{north}.tif")
    if path.exists():
        return path
    params = httpx.QueryParams(
        [
            ("service", "WCS"),
            ("version", "2.0.1"),
            ("request", "GetCoverage"),
            ("coverageId", product.coverage_id),
            ("format", "image/tiff"),
            ("subset", f"E({west},{east})"),
            ("subset", f"N({south},{north})"),
        ]
    )
    response = with_retry(
        lambda: checked(http.get(product.wcs_url, params=params)), initial_backoff_s
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    partial.write_bytes(response.content)
    try:
        check_lidar(partial, box)
    except LidarCheckError:
        partial.unlink()
        raise
    partial.replace(path)
    return path


def cached_lidar_path(cache_dir: Path, product: EaLidarProduct, file_name: str) -> Path:
    """Return where the cache keeps the `product` GeoTIFF called `file_name`."""
    return cache_dir / CACHE_SUBDIR / product.coverage_id / file_name


def check_lidar(path: Path, box: Aoi) -> None:
    """Raise `LidarCheckError` unless `path` is a gap-free 1 m BNG raster of exactly `box`."""
    with rasterio.open(path) as src:
        if src.crs is None or not CRS.from_wkt(src.crs.to_wkt()).equals(
            BRITISH_NATIONAL_GRID, ignore_axis_order=True
        ):
            msg = f"CRS is {src.crs}, not {BRITISH_NATIONAL_GRID}"
            raise LidarCheckError(msg)
        if src.res != (PIXEL_SIZE_M, PIXEL_SIZE_M):
            msg = f"pixel size is {src.res}, not {PIXEL_SIZE_M} m"
            raise LidarCheckError(msg)
        bounds = tuple(src.bounds)
        if bounds != (box.west, box.south, box.east, box.north):
            msg = f"bounds are {bounds}, not the requested box"
            raise LidarCheckError(msg)
        gaps = int(np.ma.count_masked(src.read(1, masked=True)))
    if gaps:
        msg = f"{gaps} nodata pixels"
        raise LidarCheckError(msg)
