"""Region-independent access to the DSM and ground model of an area, chosen from the registry."""

import math
from dataclasses import dataclass
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict

from satmesh_core import BRITISH_NATIONAL_GRID, NAVD88_HEIGHT, Aoi
from satmesh_data.cog_tiles import fetch_cog_window
from satmesh_data.ea_lidar import EaLidarProduct, fetch_ea_lidar
from satmesh_data.ept_dsm import (
    DsmProvenance,
    fetch_ept_dsm,
    find_ept_project,
    read_dsm_provenance,
)
from satmesh_data.ground_tiles import fetch_ground_window
from satmesh_data.http import RequestSchedule
from satmesh_data.registry import (
    CogTilesSource,
    CogTilesWithZipGroundSource,
    EaWcsSource,
    RegistryEntry,
    SurfaceSource,
    TnmDemWithEptDsmSource,
    load_registry,
    select_from,
)
from satmesh_data.usgs_dem import (
    DemProvenance,
    DemSources,
    fetch_dem_window,
    grid_for,
    read_dem_provenance,
)

# the tiler's box rounding to whole metres plus a margin so bilinear sampling at the footprint
# edge has neighbours on every side
EA_BOX_MARGIN_M = 5
US_BOX_MARGIN_M = 5
# USGS publishes no rate limit for the TNM API, the ImageServer or the lidar bucket; 20 requests a
# second keeps a build's few thousand small requests polite. One schedule for the whole process,
# since every build thread shares the same hosts.
USGS_MIN_INTERVAL_S = 0.05
USGS_SCHEDULE = RequestSchedule(USGS_MIN_INTERVAL_S)


@dataclass(frozen=True)
class Surface:
    """A single-band float GeoTIFF of heights in metres.

    The pixel grid is in `xy_crs`; `height_crs` is the PROJ compound CRS (horizontal part
    included, e.g. `EPSG:7405` or `EPSG:4326+3855`) whose vertical datum the heights refer to.
    """

    path: Path
    xy_crs: str
    height_crs: str


class SurfaceProvenance(BaseModel):
    """How a lidar-built DSM and its DTM were assembled, for sources that record it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dsm: DsmProvenance
    dtm: DemProvenance


@dataclass(frozen=True)
class SurfacePair:
    """The surface and ground rasters of one area and where they came from.

    `ground_is_surface` marks a source with only a surface model: `dsm` and `dtm` are then the
    same file. `provenance` is None for sources whose rasters come ready-made (EA, GLO-30).
    """

    dsm: Surface
    dtm: Surface
    source: str
    attribution: str
    ground_is_surface: bool
    provenance: SurfaceProvenance | None


def select_surface_source(footprint: Aoi) -> SurfaceSource:
    """Return the registry entry `fetch_surfaces` would use for `footprint`.

    The entry is the first whose coverage includes the footprint centre. Raises
    `SourceSelectionError` when none does or the entry covers only part of the footprint.
    """
    return select_from(load_registry(), footprint)


def fetch_surfaces(http: httpx.Client, footprint: Aoi, cache_dir: Path) -> SurfacePair:
    """Return rasters covering `footprint`, fetching them if not cached.

    The adapter adds the margin its grid needs around `footprint`. Rasters have no nodata.
    """
    return fetch_surfaces_from_source(
        http, select_from(load_registry(), footprint), footprint, cache_dir
    )


def fetch_surfaces_from_source(
    http: httpx.Client, source: RegistryEntry, footprint: Aoi, cache_dir: Path
) -> SurfacePair:
    """Return rasters covering `footprint` from `source`, which need not come from the registry."""
    provenance = None
    match source:
        case EaWcsSource():
            dsm, dtm = _fetch_ea_wcs(http, footprint, cache_dir, source)
        case CogTilesSource():
            dsm = dtm = _fetch_cog_tiles(http, footprint, cache_dir, source)
        case CogTilesWithZipGroundSource():
            dsm, dtm = _fetch_cog_tiles_with_zip_ground(http, footprint, cache_dir, source)
        case TnmDemWithEptDsmSource():
            dsm, dtm = _fetch_tnm_dem_with_ept_dsm(http, footprint, cache_dir, source)
            provenance = SurfaceProvenance(
                dsm=read_dsm_provenance(dsm.path), dtm=read_dem_provenance(dtm.path)
            )
    return SurfacePair(
        dsm=dsm,
        dtm=dtm,
        source=source.name,
        attribution=source.attribution,
        ground_is_surface=source.ground_is_surface,
        provenance=provenance,
    )


def _fetch_ea_wcs(
    http: httpx.Client, footprint: Aoi, cache_dir: Path, source: EaWcsSource
) -> tuple[Surface, Surface]:
    west, south, east, north = footprint.bounds_in(BRITISH_NATIONAL_GRID)
    box = Aoi(
        crs=BRITISH_NATIONAL_GRID,
        west=math.floor(west) - EA_BOX_MARGIN_M,
        south=math.floor(south) - EA_BOX_MARGIN_M,
        east=math.ceil(east) + EA_BOX_MARGIN_M,
        north=math.ceil(north) + EA_BOX_MARGIN_M,
    )

    def fetch(wcs_url: str, coverage_id: str) -> Surface:
        path = fetch_ea_lidar(http, box, cache_dir, EaLidarProduct(wcs_url, coverage_id))
        return Surface(path, source.xy_crs, source.height_crs)

    return (
        fetch(source.dsm_wcs_url, source.dsm_coverage_id),
        fetch(source.dtm_wcs_url, source.dtm_coverage_id),
    )


def _fetch_cog_tiles(
    http: httpx.Client, footprint: Aoi, cache_dir: Path, source: CogTilesSource
) -> Surface:
    path = fetch_cog_window(
        http, source.url_template, footprint.wgs84_bounds(), cache_dir / source.name
    )
    return Surface(path, source.xy_crs, source.height_crs)


def _fetch_cog_tiles_with_zip_ground(
    http: httpx.Client, footprint: Aoi, cache_dir: Path, source: CogTilesWithZipGroundSource
) -> tuple[Surface, Surface]:
    source_dir = cache_dir / source.name
    dsm_path = fetch_cog_window(http, source.url_template, footprint.wgs84_bounds(), source_dir)
    dtm_path = fetch_ground_window(
        http, source.ground_path_template, source.ground_index_url, dsm_path, source_dir
    )
    return (
        Surface(dsm_path, source.xy_crs, source.height_crs),
        Surface(dtm_path, source.xy_crs, source.height_crs),
    )


def _fetch_tnm_dem_with_ept_dsm(
    http: httpx.Client, footprint: Aoi, cache_dir: Path, source: TnmDemWithEptDsmSource
) -> tuple[Surface, Surface]:
    source_dir = cache_dir / source.name
    grid = grid_for(footprint, US_BOX_MARGIN_M)
    dem_sources = DemSources(
        source.tnm_products_url,
        source.tnm_dataset,
        source.image_server_url,
        source.seamless_path_template,
    )
    # the DTM prefers the 1 m DEM project of the lidar year the DSM is built from
    project = find_ept_project(http, USGS_SCHEDULE, source.ept_index_url, grid, source_dir)
    dtm_path = fetch_dem_window(
        http, USGS_SCHEDULE, dem_sources, grid, source_dir, prefer_year=project.year
    )
    dsm_path = fetch_ept_dsm(http, USGS_SCHEDULE, project, dtm_path, source_dir)
    height_crs = f"{grid.crs}+{NAVD88_HEIGHT.removeprefix('EPSG:')}"
    return Surface(dsm_path, grid.crs, height_crs), Surface(dtm_path, grid.crs, height_crs)
