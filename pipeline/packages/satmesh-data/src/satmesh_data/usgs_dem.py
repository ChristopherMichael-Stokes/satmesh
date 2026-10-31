"""USGS 3DEP bare-earth DEM windows on a 1 m NAD83(2011) UTM grid.

Listed tiles can be partly or wholly nodata, so a window is filled in steps, each step touching
only the pixels the ones before it left empty:

1. every 1 m project DEM COG the TNM Access API lists over the window, range-read in place; the
   tiles of the preferred year (the lidar flight the DSM comes from) first, then newest first;
2. holes small enough to be dropped returns rather than missing ground (see
   `SMALL_HOLE_MAX_FRACTION` and `SMALL_HOLE_MAX_ACROSS_M`), interpolated from the valid pixels
   around them with GDAL's inverse-distance `fillnodata`;
3. the 3DEP ImageServer `exportImage`, when its catalog holds a primary source of 1 m or finer
   there (it mosaics the best source it has);
4. the 1/3 arc-second seamless COGs (about 10 m), resampled bilinearly onto the 1 m grid.

A hole left after step 4 raises. The window records each source's share of its pixels and
resolution, and the interpolated fraction (`DemProvenance`).

3DEP labels its rasters NAD83 (EPSG:269xx, EPSG:4269) without a realisation; current 3DEP
projects are delivered in NAD83(2011), so coordinates are taken as NAD83(2011) unchanged, and
heights are NAVD88 metres.
"""

import json
import logging
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx
import numpy as np
import rasterio
import shapely
from affine import Affine
from pydantic import BaseModel, ConfigDict, Field
from pyproj import CRS, Geod
from pyproj.aoi import AreaOfInterest
from pyproj.database import query_utm_crs_info
from rasterio.enums import Resampling
from rasterio.features import shapes
from rasterio.fill import fillnodata
from rasterio.io import MemoryFile
from rasterio.vrt import WarpedVRT

from satmesh_core import NAD83_2011, Aoi
from satmesh_data.http import (
    DEFAULT_INITIAL_BACKOFF_S,
    USER_AGENT,
    RequestSchedule,
    RetryableStatusError,
    checked,
    with_retry,
)

logger = logging.getLogger(__name__)

PIXEL_SIZE_M = 1
NODATA_M = -999999.0
NAD83_2011_DATUM = "NAD83(2011)"
DEM_WINDOWS_SUBDIR = Path("dem-windows")
TNM_QUERIES_SUBDIR = Path("tnm-queries")
DEM_PROVENANCE_TAG = "DEM_PROVENANCE"
TNM_RESOLUTION_M = 1.0
# Interpolating a hole is acceptable only where the hole is a few dropped returns on open ground
# (a parked car, a puddle), not missing terrain. Owner's thresholds, a tunable: at most 0.1 % of
# the window (about 17 pixels of a 130 m leaf window) and every hole under 5 m across, measured
# as the diameter of the smallest circle holding it, so a 3 x 3 m hole (4.2 m) qualifies and a
# 4 x 4 m one (5.7 m) does not.
SMALL_HOLE_MAX_FRACTION = 0.001
SMALL_HOLE_MAX_ACROSS_M = 5.0
# fillnodata searches this many pixels from a hole pixel for valid ones; a hole under 5 m across
# has valid pixels within 3 px of every pixel, so twice that reaches all its edges
SMALL_HOLE_SEARCH_PX = 6
INTERPOLATED = "interpolated"
IMAGE_SERVER = "3dep-imageserver"
SEAMLESS = "3dep-seamless-13"
# the TNM download path is .../1m/Projects/{project}/TIFF/{file}
PROJECTS_PATH_SEGMENT = "Projects"
TNM_PAGE_SIZE = 50
TNM_ITEMS_KEY = "items"
IMAGE_SERVER_MAX_PIXELS = 8000
# catalog category of a source raster, as opposed to the service's own overviews (2)
IMAGE_SERVER_PRIMARY_CATEGORY = 1
FINEST_FALLBACK_PIXEL_M = 1.0
VSICURL_PREFIX = "/vsicurl/"
HTTP_SCHEMES = ("https://", "http://")
# a year in a project or product name, e.g. CO_DRCOG_2020_B20 or CO_DRCOG_2_2020
NAME_YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
# range reads of remote COGs: no directory listing, GDAL's own retry for transient HTTP errors
GDAL_REMOTE_OPTIONS = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_USERAGENT": USER_AGENT,
    "GDAL_HTTP_MAX_RETRY": "5",
    "GDAL_HTTP_RETRY_DELAY": "2",
}


class DemCoverageError(Exception):
    """No 3DEP source fills every pixel of a window."""


@dataclass(frozen=True)
class MetreGrid:
    """A north-up 1 m grid in a NAD83(2011) UTM CRS whose edges are whole metres."""

    crs: str
    west: int
    south: int
    east: int
    north: int

    @property
    def shape(self) -> tuple[int, int]:
        """Return `(rows, columns)`."""
        return (self.north - self.south) // PIXEL_SIZE_M, (self.east - self.west) // PIXEL_SIZE_M

    @property
    def transform(self) -> Affine:
        """Return the pixel-to-CRS transform; pixel (0, 0) is the north-west one."""
        return Affine(PIXEL_SIZE_M, 0, self.west, 0, -PIXEL_SIZE_M, self.north)

    @property
    def epsg(self) -> int:
        """Return the EPSG code of `crs`."""
        code = CRS.from_user_input(self.crs).to_epsg()
        if code is None:
            msg = f"{self.crs} has no EPSG code"
            raise ValueError(msg)
        return code

    @property
    def name(self) -> str:
        """Return a file-name key, e.g. `EPSG6342_500100_4399700_500400_4400000`."""
        return f"{self.crs.replace(':', '')}_{self.west}_{self.south}_{self.east}_{self.north}"


def grid_for(footprint: Aoi, margin_m: int) -> MetreGrid:
    """Return the 1 m grid covering `footprint` plus `margin_m`, in the UTM zone at its centre."""
    west, south, east, north = footprint.wgs84_bounds()
    crs = nad83_2011_utm_at((west + east) / 2, (south + north) / 2)
    x_min, y_min, x_max, y_max = footprint.bounds_in(crs)
    return MetreGrid(
        crs=crs,
        west=math.floor(x_min) - margin_m,
        south=math.floor(y_min) - margin_m,
        east=math.ceil(x_max) + margin_m,
        north=math.ceil(y_max) + margin_m,
    )


def nad83_2011_utm_at(lon: float, lat: float) -> str:
    """Return the NAD83(2011) UTM CRS (EPSG:6330 to 6348 in the US) of the zone holding a point."""
    zones = query_utm_crs_info(
        datum_name=NAD83_2011_DATUM, area_of_interest=AreaOfInterest(lon, lat, lon, lat)
    )
    if not zones:
        msg = f"no {NAD83_2011_DATUM} UTM zone at lon {lon}, lat {lat}"
        raise ValueError(msg)
    return f"{zones[0].auth_name}:{zones[0].code}"


@dataclass(frozen=True)
class DemSources:
    """Where the three 3DEP DEM sources live; `seamless_path_template` takes `{tile}`."""

    tnm_products_url: str
    tnm_dataset: str
    image_server_url: str
    seamless_path_template: str


class TnmProduct(BaseModel):
    """One DEM tile listed by the TNM Access API."""

    model_config = ConfigDict(extra="ignore")

    title: str
    download_url: str = Field(alias="downloadURL")
    publication_date: date = Field(alias="publicationDate")


class _TnmPage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total: int
    items: list[TnmProduct]


class _CatalogItem(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str = Field(alias="Name")
    low_pixel_size: float = Field(alias="LowPS")
    category: int = Field(alias="Category")


class _CatalogFeature(BaseModel):
    attributes: _CatalogItem


class _CatalogPage(BaseModel):
    features: list[_CatalogFeature]


class _Identify(BaseModel):
    """`identify` at a point: the mosaic value, every catalog item's value and the items."""

    model_config = ConfigDict(extra="ignore")

    value: str
    properties: dict[str, list[str]]
    catalog_items: _CatalogPage = Field(alias="catalogItems")


class DemSourceShare(BaseModel):
    """One source of a DEM window: its name, ground resolution (m) and share of the pixels."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    resolution_m: float
    share: float


class DemProvenance(BaseModel):
    """What filled a DEM window: sources in fill order and the interpolated pixel fraction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sources: tuple[DemSourceShare, ...]
    interpolated_fraction: float

    @property
    def effective_resolution_m(self) -> float:
        """Return the coarsest resolution among the sources."""
        return max(source.resolution_m for source in self.sources)


class Contribution(BaseModel):
    """Pixels one raster of `read_onto_grid` supplied, and the CRS it was labelled and read in."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int
    crs_note: str
    pixels: int


def fetch_dem_window(  # noqa: PLR0913 (one source's endpoints, the grid and the edges of a fetch)
    http: httpx.Client,
    schedule: RequestSchedule,
    sources: DemSources,
    grid: MetreGrid,
    cache_dir: Path,
    *,
    prefer_year: int | None = None,
    initial_backoff_s: float = DEFAULT_INITIAL_BACKOFF_S,
) -> Path:
    """Return a gap-free float32 GeoTIFF of NAVD88 heights (m) on `grid`, fetching it if not cached.

    Steps as in the module docstring; `prefer_year` orders the 1 m tiles. The `DEM_PROVENANCE`
    tag holds the window's `DemProvenance` as JSON. Raises `DemCoverageError` naming the window,
    the sources tried and the nodata fraction when the last source still leaves a hole.
    """
    path = cache_dir / DEM_WINDOWS_SUBDIR / f"{grid.name}.tif"
    if path.exists():
        return path
    products = find_tnm_products(
        http,
        schedule,
        sources,
        grid,
        cache_dir,
        prefer_year=prefer_year,
        initial_backoff_s=initial_backoff_s,
    )
    heights, used = read_onto_grid([gdal_path(p.download_url) for p in products], grid)
    shares = _project_shares(products, used, heights.size)
    interpolated = _interpolate_small_holes(heights, grid)
    tried = ["tnm-1m", INTERPOLATED]
    if (heights == NODATA_M).any() and _image_server_1m_items(
        http, schedule, sources.image_server_url, grid, initial_backoff_s
    ):
        tried.append(IMAGE_SERVER)
        image = export_image(http, schedule, sources.image_server_url, grid, initial_backoff_s)
        if pixels := _fill(heights, image):
            resolution = _image_server_resolution(
                http, schedule, sources.image_server_url, grid, initial_backoff_s
            )
            shares.append(
                DemSourceShare(
                    source=IMAGE_SERVER, resolution_m=resolution, share=pixels / heights.size
                )
            )
    if (heights == NODATA_M).any():
        tried.append(SEAMLESS)
        tiles = seamless_tiles(grid)
        paths = [sources.seamless_path_template.format(tile=tile) for tile in tiles]
        seamless, seamless_used = read_onto_grid(paths, grid)
        if pixels := _fill(heights, seamless):
            names = ", ".join(tiles[c.index] for c in seamless_used)
            shares.append(
                DemSourceShare(
                    source=f"{SEAMLESS}: {names}",
                    resolution_m=_pixel_height_m(paths[seamless_used[0].index]),
                    share=pixels / heights.size,
                )
            )
    holes = int((heights == NODATA_M).sum())
    if holes:
        msg = f"DEM window {grid.name}: {holes / heights.size:.2%} nodata after {', '.join(tried)}"
        raise DemCoverageError(msg)
    provenance = DemProvenance(sources=tuple(shares), interpolated_fraction=interpolated)
    logger.info("DEM window %s: %s", grid.name, provenance.model_dump_json())
    _write(path, heights, grid, provenance)
    return path


def read_dem_provenance(path: Path) -> DemProvenance:
    """Return the provenance `fetch_dem_window` recorded in a DEM window."""
    with rasterio.open(path) as src:
        return DemProvenance.model_validate_json(src.tags()[DEM_PROVENANCE_TAG])


def _project_shares(
    products: list[TnmProduct], used: list[Contribution], pixels: int
) -> list[DemSourceShare]:
    """Return each 1 m project's share of the window, in the order the tiles were read."""
    by_project: dict[str, int] = {}
    for contribution in used:
        project = project_of(products[contribution.index])
        by_project[project] = by_project.get(project, 0) + contribution.pixels
    return [
        DemSourceShare(source=f"tnm-1m: {project}", resolution_m=TNM_RESOLUTION_M, share=n / pixels)
        for project, n in by_project.items()
    ]


def gdal_path(url: str) -> str:
    """Return the GDAL path that range-reads `url` if it is HTTP(S), else `url` as a local path."""
    return VSICURL_PREFIX + url if url.startswith(HTTP_SCHEMES) else url


def project_of(product: TnmProduct) -> str:
    """Return the 3DEP project a tile belongs to, from its download path, else its title."""
    parts = product.download_url.split("/")
    if PROJECTS_PATH_SEGMENT in parts[:-1]:
        return parts[parts.index(PROJECTS_PATH_SEGMENT) + 1]
    return product.title


def _interpolate_small_holes(heights: np.ndarray, grid: MetreGrid) -> float:
    """Fill the holes of `heights` in place if they are all small; return the filled fraction.

    Does nothing unless some pixels are valid, the holes are under `SMALL_HOLE_MAX_FRACTION` of
    the window, and each is under `SMALL_HOLE_MAX_ACROSS_M` across.
    """
    empty = heights == NODATA_M
    count = int(empty.sum())
    if count == 0 or count >= SMALL_HOLE_MAX_FRACTION * empty.size:
        return 0.0
    for hole, _ in shapes(empty.astype(np.uint8), mask=empty, transform=grid.transform):
        across = 2 * shapely.minimum_bounding_radius(shapely.geometry.shape(hole))
        if across >= SMALL_HOLE_MAX_ACROSS_M:
            return 0.0
    filled = fillnodata(heights, mask=~empty, max_search_distance=SMALL_HOLE_SEARCH_PX)
    if (filled[empty] == NODATA_M).any():
        msg = f"fillnodata left holes in {grid.name}"
        raise DemCoverageError(msg)
    heights[empty] = filled[empty]
    return count / int(empty.size)


def _fill(heights: np.ndarray, layer: np.ndarray) -> int:
    """Fill the empty pixels of `heights` from `layer`; return how many were filled."""
    filled = (heights == NODATA_M) & (layer != NODATA_M)
    heights[filled] = layer[filled]
    return int(filled.sum())


def _pixel_height_m(path: str) -> float:
    """Return the north-south ground size (m) of a pixel of a geographic raster at its centre."""
    with rasterio.Env(**GDAL_REMOTE_OPTIONS), rasterio.open(path) as src:
        lon = (src.bounds.left + src.bounds.right) / 2
        lat = (src.bounds.bottom + src.bounds.top) / 2
        step = src.res[1]
    _, _, distance = Geod(ellps="GRS80").inv(lon, lat, lon, lat + step)
    return float(distance)


def years_in_name(name: str) -> list[int]:
    """Return the years a 3DEP project or product name holds, e.g. 2020 in CO_DRCOG_2020_B20."""
    return [int(year) for year in NAME_YEAR.findall(name)]


def find_tnm_products(  # noqa: PLR0913 (one source's endpoints, the grid and the edges of a fetch)
    http: httpx.Client,
    schedule: RequestSchedule,
    sources: DemSources,
    grid: MetreGrid,
    cache_dir: Path,
    *,
    prefer_year: int | None = None,
    initial_backoff_s: float = DEFAULT_INITIAL_BACKOFF_S,
) -> list[TnmProduct]:
    """Return the GeoTIFF DEM tiles the TNM API lists over `grid`, newest publication first.

    Tiles whose title names `prefer_year` come before all others.

    Every page of the answer is read; the list is cached per grid.
    """
    cached = cache_dir / TNM_QUERIES_SUBDIR / f"{grid.name}.json"
    if not cached.exists():
        west, south, east, north = Aoi(
            crs=grid.crs, west=grid.west, south=grid.south, east=grid.east, north=grid.north
        ).wgs84_bounds()
        items: list[TnmProduct] = []
        total = 1
        while len(items) < total:
            params = {
                "datasets": sources.tnm_dataset,
                "bbox": f"{west},{south},{east},{north}",
                "max": TNM_PAGE_SIZE,
                "offset": len(items),
            }
            page = _tnm_page(http, schedule, sources.tnm_products_url, params, initial_backoff_s)
            if not page.items:
                break
            total = page.total
            items.extend(page.items)
        cached.parent.mkdir(parents=True, exist_ok=True)
        partial = cached.with_suffix(".part")
        partial.write_text(json.dumps([p.model_dump(mode="json", by_alias=True) for p in items]))
        partial.replace(cached)
    products = [TnmProduct.model_validate(item) for item in json.loads(cached.read_text())]
    return sorted(
        (p for p in products if p.download_url.lower().endswith(".tif")),
        key=lambda p: (
            prefer_year in years_in_name(f"{p.title} {project_of(p)}"),
            p.publication_date,
        ),
        reverse=True,
    )


def _tnm_page(
    http: httpx.Client,
    schedule: RequestSchedule,
    url: str,
    params: Mapping[str, str | int | float],
    initial_backoff_s: float,
) -> _TnmPage:
    def attempt() -> _TnmPage:
        schedule.wait_for_slot()
        body = checked(http.get(url, params=params)).json()
        # the API answers some requests with status 200 and {"error": ...} or
        # {"errorMessage": "Search ... return fewer results"}; the same request then succeeds
        if not isinstance(body, dict) or TNM_ITEMS_KEY not in body:
            msg = f"TNM API answered {str(body)[:200]} for {params}"
            raise RetryableStatusError(msg)
        return _TnmPage.model_validate(body)

    return with_retry(attempt, initial_backoff_s)


def read_onto_grid(paths: list[str], grid: MetreGrid) -> tuple[np.ndarray, list[Contribution]]:
    """Return heights on `grid` from the GDAL rasters at `paths`, earlier paths taking precedence.

    Also returns, for each path that supplied at least one pixel, its index, the pixels it
    supplied and a note of the CRS it is labelled with and the one it was read as, e.g.
    `EPSG:26913 read as EPSG:6342`.

    Each raster is warped bilinearly onto the grid from its CRS taken as NAD83(2011): a UTM
    raster from the same zone lands pixel for pixel when its edges are on whole metres. Pixels no
    raster covers are `NODATA_M`.
    """
    heights = np.full(grid.shape, NODATA_M, dtype=np.float32)
    used: list[Contribution] = []
    with rasterio.Env(**GDAL_REMOTE_OPTIONS):
        for index, path in enumerate(paths):
            empty = heights == NODATA_M
            if not empty.any():
                break
            with rasterio.open(path) as src:
                labelled = CRS.from_wkt(src.crs.to_wkt())
                source_crs = _as_nad83_2011(labelled)
                with WarpedVRT(
                    src,
                    src_crs=source_crs,
                    src_nodata=src.nodata,
                    crs=grid.crs,
                    transform=grid.transform,
                    width=grid.shape[1],
                    height=grid.shape[0],
                    nodata=NODATA_M,
                    resampling=Resampling.bilinear,
                    dtype="float32",
                ) as warped:
                    layer = warped.read(1)
            supplied = empty & (layer != NODATA_M)
            if supplied.any():
                note = f"{_short_name(labelled)} read as {source_crs}"
                used.append(Contribution(index=index, crs_note=note, pixels=int(supplied.sum())))
            heights[supplied] = layer[supplied]
    return heights, used


def _short_name(crs: CRS) -> str:
    code = crs.to_authority()
    return f"{code[0]}:{code[1]}" if code is not None else crs.name


def _as_nad83_2011(crs: CRS) -> str:
    """Return the NAD83(2011) CRS a 3DEP raster labelled `crs` (NAD83 UTM or geographic) is in."""
    if crs.utm_zone is not None:
        zone = crs.utm_zone
        for info in query_utm_crs_info(datum_name=NAD83_2011_DATUM):
            if info.name.endswith(f"UTM zone {zone}"):
                return f"{info.auth_name}:{info.code}"
        msg = f"no {NAD83_2011_DATUM} UTM zone {zone}"
        raise ValueError(msg)
    if crs.is_geographic:
        return NAD83_2011
    msg = f"3DEP raster in {crs.name}: only UTM and geographic NAD83 are read"
    raise ValueError(msg)


def seamless_tiles(grid: MetreGrid) -> list[str]:
    """Return the 1-degree seamless tile names (`n40w105`: north edge, west edge) over `grid`."""
    west, south, east, north = Aoi(
        crs=grid.crs, west=grid.west, south=grid.south, east=grid.east, north=grid.north
    ).wgs84_bounds()
    return [
        f"{'n' if lat >= 0 else 's'}{abs(lat):02d}{'w' if lon < 0 else 'e'}{abs(lon):03d}"
        for lat in range(math.floor(south) + 1, math.floor(north) + 2)
        for lon in range(math.floor(west), math.floor(east) + 1)
    ]


def _image_server_1m_items(
    http: httpx.Client,
    schedule: RequestSchedule,
    url: str,
    grid: MetreGrid,
    initial_backoff_s: float,
) -> list[_CatalogItem]:
    """Return the primary catalog rasters of 1 m or finer that meet `grid`."""
    params = {
        "geometry": f"{grid.west},{grid.south},{grid.east},{grid.north}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": grid.epsg,
        # without it the service ignores the geometry and lists the whole catalog
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "Name,LowPS,Category",
        "returnGeometry": "false",
        "f": "json",
    }
    page = _CatalogPage.model_validate_json(
        _get(http, schedule, f"{url}/query", params, initial_backoff_s).content
    )
    return [
        f.attributes
        for f in page.features
        if f.attributes.category == IMAGE_SERVER_PRIMARY_CATEGORY
        and f.attributes.low_pixel_size <= FINEST_FALLBACK_PIXEL_M
    ]


def _image_server_resolution(
    http: httpx.Client,
    schedule: RequestSchedule,
    url: str,
    grid: MetreGrid,
    initial_backoff_s: float,
) -> float:
    """Return the resolution (m) of the catalog raster the mosaic serves at the grid's centre.

    `identify` lists every catalog item over the point with its own value beside the mosaic's
    value; the served raster is the primary item whose value equals the mosaic's, finest first.
    """
    x = (grid.west + grid.east) / 2
    y = (grid.south + grid.north) / 2
    params = {
        "geometry": json.dumps({"x": x, "y": y, "spatialReference": {"wkid": grid.epsg}}),
        "geometryType": "esriGeometryPoint",
        "returnCatalogItems": "true",
        "returnGeometry": "false",
        "f": "json",
    }
    answer = _Identify.model_validate_json(
        _get(http, schedule, f"{url}/identify", params, initial_backoff_s).content
    )
    values = answer.properties.get("Values", [])
    served = sorted(
        feature.attributes.low_pixel_size
        for feature, value in zip(answer.catalog_items.features, values, strict=False)
        if feature.attributes.category == IMAGE_SERVER_PRIMARY_CATEGORY and value == answer.value
    )
    if not served:
        msg = f"identify at {grid.name} names no primary raster with the mosaic value"
        raise ValueError(msg)
    return served[0]


def export_image(
    http: httpx.Client,
    schedule: RequestSchedule,
    url: str,
    grid: MetreGrid,
    initial_backoff_s: float = DEFAULT_INITIAL_BACKOFF_S,
) -> np.ndarray:
    """Return the ImageServer's best-available heights on `grid`; empty pixels are `NODATA_M`."""
    rows, columns = grid.shape
    if max(rows, columns) > IMAGE_SERVER_MAX_PIXELS:
        msg = f"{grid.name} is {columns} x {rows} px, past the {IMAGE_SERVER_MAX_PIXELS} px limit"
        raise ValueError(msg)
    epsg = grid.epsg
    params = {
        "bbox": f"{grid.west},{grid.south},{grid.east},{grid.north}",
        "bboxSR": epsg,
        "imageSR": epsg,
        "size": f"{columns},{rows}",
        "format": "tiff",
        "pixelType": "F32",
        "noData": NODATA_M,
        "interpolation": "RSP_BilinearInterpolation",
        "f": "image",
    }
    response = _get(http, schedule, f"{url}/exportImage", params, initial_backoff_s)
    with MemoryFile(response.content) as memory, memory.open() as src:
        if (src.height, src.width) != grid.shape or not src.transform.almost_equals(grid.transform):
            msg = f"exportImage returned {src.width} x {src.height} at {src.transform}"
            raise ValueError(msg)
        heights = src.read(1).astype(np.float32)
        if src.nodata is not None:
            heights[heights == src.nodata] = NODATA_M
    return heights


def _get(
    http: httpx.Client,
    schedule: RequestSchedule,
    url: str,
    params: Mapping[str, str | int | float],
    initial_backoff_s: float,
) -> httpx.Response:
    def attempt() -> httpx.Response:
        schedule.wait_for_slot()
        return checked(http.get(url, params=params))

    return with_retry(attempt, initial_backoff_s)


def _write(path: Path, heights: np.ndarray, grid: MetreGrid, provenance: DemProvenance) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    with rasterio.open(
        partial,
        "w",
        driver="GTiff",
        width=grid.shape[1],
        height=grid.shape[0],
        count=1,
        dtype="float32",
        crs=grid.crs,
        transform=grid.transform,
        compress="deflate",
    ) as dst:
        dst.write(heights, 1)
        dst.update_tags(**{DEM_PROVENANCE_TAG: provenance.model_dump_json()})
    partial.replace(path)
