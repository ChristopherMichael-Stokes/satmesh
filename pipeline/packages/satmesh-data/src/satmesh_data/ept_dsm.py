"""First-return DSM rasterised from USGS 3DEP lidar in Entwine Point Tile (EPT) form.

EPT (https://entwine.io/en/latest/entwine-point-tile.html) stores a project as an octree of LAZ
nodes keyed `D-X-Y-Z` under a cube `bounds`: node `D-X-Y-Z` spans `bounds_min + (X, Y, Z) * side`
to that plus `side`, with `side = (bounds_max - bounds_min) / 2**D`. Every point sits in exactly
one node, so the points of an area are the union of all nodes, at every depth, that meet it.
`ept-hierarchy/D-X-Y-Z.json` maps node keys to point counts; a count of -1 means the subtree is
listed in that key's own hierarchy file.

The DSM keeps, per pixel of a DTM window's grid, the highest first return that is neither ASPRS
noise (classes 7 and 18) nor withheld, as the Environment Agency builds its first-return DSM.
Pixels no such return falls in take the DTM height, and their count is recorded.
"""

import io
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, fields
from datetime import UTC, date, datetime, timedelta
from functools import cache
from pathlib import Path

import httpx
import laspy
import numpy as np
import rasterio
import shapely
from pydantic import BaseModel, ConfigDict
from pyproj import Transformer
from rasterio.transform import Affine

from satmesh_core import NAD83_2011, WGS84
from satmesh_data.http import DEFAULT_INITIAL_BACKOFF_S, RequestSchedule, checked, with_retry
from satmesh_data.usgs_dem import MetreGrid, years_in_name

logger = logging.getLogger(__name__)

EPT_SUBDIR = Path("ept")
DSM_WINDOWS_SUBDIR = Path("ept-dsm-windows")
PROJECT_INDEX_FILE = "resources.geojson"
ROOT_KEY = "0-0-0-0"
SUBTREE_ELSEWHERE = -1
# ASPRS LAS 1.4 R15 table 17: 7 low point (noise), 18 high noise
NOISE_CLASSES = (7, 18)
FIRST_RETURN = 1
# LAS 1.4 classification flags: bit 2 marks a withheld point, which processing should skip; EPT
# keeps the flags of point formats 6 and up in an extra `ClassFlags` dimension
CLASS_FLAGS_DIMENSION = "ClassFlags"
WITHHELD_FLAG = 0b100
# LAS 1.4: adjusted standard GPS time is GPS seconds since 1980-01-06T00:00Z minus 1e9; leap
# seconds (18 by 2020) are ignored, which cannot move a date by more than a day
GPS_EPOCH = datetime(1980, 1, 6, tzinfo=UTC)
ADJUSTED_GPS_TIME_OFFSET_S = 1e9
DSM_PROVENANCE_TAG = "DSM_PROVENANCE"
EPT_CRS = "EPSG:3857"
# Web Mercator metres around the grid when selecting points, so the grid's edge pixels keep their
# points whatever datum offset (about 1.3 m in the US) separates the two box conversions
EPT_BOX_PAD_M = 5.0
# node files of one window fetched at once; the shared request schedule still sets the rate
FETCH_WORKERS = 8


class EptCoverageError(Exception):
    """No EPT project covers a window."""


class EptProject(BaseModel):
    """One project of the USGS EPT index."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    url: str
    count: int

    @property
    def year(self) -> int:
        """Return the latest year in the project name, 0 if it names none."""
        return max(years_in_name(self.name), default=0)

    @property
    def base_url(self) -> str:
        """Return the URL of the directory holding `ept.json`."""
        return self.url.rsplit("/", 1)[0]


class DsmProvenance(BaseModel):
    """What built a DSM window: the EPT project, its returns and capture dates, the DTM share.

    The dates are None when the window held no return.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    project: str
    first_returns: int
    first_returns_per_m2: float
    filled_from_dtm_fraction: float
    acquired_from: date | None
    acquired_to: date | None


class _EptMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bounds: tuple[float, float, float, float, float, float]


@dataclass(frozen=True)
class LidarPoints:
    """Points of a lidar cloud as parallel arrays; `withheld` and the times are per point."""

    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    return_number: np.ndarray
    classification: np.ndarray
    withheld: np.ndarray
    gps_time: np.ndarray

    def where(self, keep: np.ndarray) -> "LidarPoints":
        """Return the points where `keep` is true."""
        return LidarPoints(
            self.x[keep],
            self.y[keep],
            self.z[keep],
            self.return_number[keep],
            self.classification[keep],
            self.withheld[keep],
            self.gps_time[keep],
        )


def surface_returns(points: LidarPoints) -> LidarPoints:
    """Return the first returns that are neither noise nor withheld."""
    keep = (
        (points.return_number == FIRST_RETURN)
        & ~np.isin(points.classification, NOISE_CLASSES)
        & ~points.withheld
    )
    return points.where(keep)


def highest_per_pixel(
    x: np.ndarray, y: np.ndarray, z: np.ndarray, transform: Affine, shape: tuple[int, int]
) -> np.ndarray:
    """Return the highest `z` falling in each pixel of a north-up grid; NaN where none falls.

    A point on a pixel's west or north edge belongs to that pixel.
    """
    columns = np.floor((x - transform.c) / transform.a).astype(np.int64)
    rows = np.floor((y - transform.f) / transform.e).astype(np.int64)
    inside = (rows >= 0) & (rows < shape[0]) & (columns >= 0) & (columns < shape[1])
    highest = np.full(shape[0] * shape[1], -np.inf)
    np.maximum.at(highest, rows[inside] * shape[1] + columns[inside], z[inside])
    highest[highest == -np.inf] = np.nan
    return highest.reshape(shape)


def acquisition_dates(gps_time: np.ndarray) -> tuple[date, date] | None:
    """Return the first and last capture dates of adjusted standard GPS times, None if empty."""
    if gps_time.size == 0:
        return None

    def to_date(seconds: float) -> date:
        return (GPS_EPOCH + timedelta(seconds=seconds + ADJUSTED_GPS_TIME_OFFSET_S)).date()

    return to_date(float(gps_time.min())), to_date(float(gps_time.max()))


def fetch_ept_dsm(  # noqa: PLR0913 (the project, the DTM it rides on and a fetch's edges)
    http: httpx.Client,
    schedule: RequestSchedule,
    project: EptProject,
    dtm_window: Path,
    cache_dir: Path,
    *,
    initial_backoff_s: float = DEFAULT_INITIAL_BACKOFF_S,
) -> Path:
    """Return a first-return DSM GeoTIFF on the grid of the DTM GeoTIFF `dtm_window`, cached.

    Points come from `project` (see `find_ept_project`). Tags record the project, the number of
    returns used, their capture dates and the number of pixels filled from the DTM.
    """
    path = cache_dir / DSM_WINDOWS_SUBDIR / dtm_window.name
    if path.exists():
        return path
    with rasterio.open(dtm_window) as src:
        dtm = src.read(1)
        transform = src.transform
        crs = src.crs.to_string()
        west, south, east, north = src.bounds
    reader = _EptReader(http, schedule, project, cache_dir / EPT_SUBDIR, initial_backoff_s)
    to_ept = Transformer.from_crs(crs, EPT_CRS, always_xy=True)
    ept_west, ept_south, ept_east, ept_north = to_ept.transform_bounds(west, south, east, north)
    points = surface_returns(
        reader.points_in(
            (
                ept_west - EPT_BOX_PAD_M,
                ept_south - EPT_BOX_PAD_M,
                ept_east + EPT_BOX_PAD_M,
                ept_north + EPT_BOX_PAD_M,
            )
        )
    )
    x, y = _ept_to_grid_crs(crs).transform(points.x, points.y)
    dsm = highest_per_pixel(x, y, points.z, transform, dtm.shape)
    empty = np.isnan(dsm)
    filled = int(empty.sum())
    dsm[empty] = dtm[empty]
    dates = acquisition_dates(points.gps_time)
    logger.info(
        "DSM window %s from %s: %d first returns, %d of %d pixels filled from the DTM",
        path.name,
        project.name,
        points.z.size,
        filled,
        dsm.size,
    )
    provenance = DsmProvenance(
        project=project.name,
        first_returns=points.z.size,
        first_returns_per_m2=points.z.size / (dsm.size * abs(transform.a * transform.e)),
        filled_from_dtm_fraction=filled / dsm.size,
        acquired_from=None if dates is None else dates[0],
        acquired_to=None if dates is None else dates[1],
    )
    _write(path, dsm.astype(np.float32), crs, transform, provenance)
    return path


def read_dsm_provenance(path: Path) -> "DsmProvenance":
    """Return the provenance `fetch_ept_dsm` recorded in a DSM window."""
    with rasterio.open(path) as src:
        return DsmProvenance.model_validate_json(src.tags()[DSM_PROVENANCE_TAG])


def _ept_to_grid_crs(grid_crs: str) -> "_TwoStep":
    # USGS EPT positions are the NAD83(2011) latitudes and longitudes of the delivered lidar,
    # projected to Web Mercator without a datum shift (measured: regions-results.md)
    return _TwoStep(
        Transformer.from_crs(EPT_CRS, WGS84, always_xy=True),
        Transformer.from_crs(NAD83_2011, grid_crs, always_xy=True),
    )


@dataclass(frozen=True)
class _TwoStep:
    first: Transformer
    second: Transformer

    def transform(self, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return self.second.transform(*self.first.transform(x, y))


def find_ept_project(  # noqa: PLR0913 (index access, the grid to cover and a fetch's edges)
    http: httpx.Client,
    schedule: RequestSchedule,
    index_url: str,
    grid: MetreGrid,
    cache_dir: Path,
    *,
    initial_backoff_s: float = DEFAULT_INITIAL_BACKOFF_S,
) -> EptProject:
    """Return the newest project of the GeoJSON index at `index_url` whose boundary holds `grid`.

    Newest is the latest year in the project name, ties going to the larger point count. Raises
    `EptCoverageError` when no boundary holds the grid.
    """
    cached = cache_dir / EPT_SUBDIR / PROJECT_INDEX_FILE
    _download(http, schedule, index_url, cached, initial_backoff_s)
    lon_lat = Transformer.from_crs(grid.crs, WGS84, always_xy=True).transform_bounds(
        grid.west, grid.south, grid.east, grid.north
    )
    window = shapely.box(*lon_lat)
    covering = [project for project, area in _index(cached) if area.contains(window)]
    if not covering:
        msg = f"no EPT project in {index_url} covers lon/lat {lon_lat}"
        raise EptCoverageError(msg)
    return max(covering, key=lambda project: (project.year, project.count))


@cache
def _index(path: Path) -> tuple[tuple[EptProject, shapely.Geometry], ...]:
    """Return each project of a cached index with its boundary; parsed once per process."""
    features = json.loads(path.read_text())["features"]
    return tuple(
        (
            EptProject.model_validate(feature["properties"]),
            shapely.geometry.shape(feature["geometry"]),
        )
        for feature in features
    )


class _EptReader:
    """Reads the points of one EPT project in a box, caching every file it fetches."""

    def __init__(
        self,
        http: httpx.Client,
        schedule: RequestSchedule,
        project: EptProject,
        cache_dir: Path,
        initial_backoff_s: float,
    ) -> None:
        self._http = http
        self._schedule = schedule
        self._project = project
        self._cache_dir = cache_dir / project.name
        self._initial_backoff_s = initial_backoff_s

    def points_in(self, box: tuple[float, float, float, float]) -> LidarPoints:
        """Return every point of the project inside `box` (EPT CRS, west, south, east, north)."""
        metadata = _EptMetadata.model_validate_json(self._file("ept.json").read_bytes())
        keys = self._nodes_meeting(metadata.bounds, box)
        with ThreadPoolExecutor(FETCH_WORKERS) as pool:
            files = list(pool.map(lambda key: self._file(f"ept-data/{key}.laz"), keys))
        batches = [_points_inside(_read_laz(file), box) for file in files]
        if not batches:
            msg = f"no node of {self._project.name} meets {box}"
            raise EptCoverageError(msg)
        return LidarPoints(
            *(
                np.concatenate([getattr(batch, field.name) for batch in batches])
                for field in fields(LidarPoints)
            )
        )

    def _nodes_meeting(
        self,
        cube: tuple[float, float, float, float, float, float],
        box: tuple[float, float, float, float],
    ) -> list[str]:
        found: list[str] = []
        pending = [ROOT_KEY]
        while pending:
            hierarchy = json.loads(self._file(f"ept-hierarchy/{pending.pop()}.json").read_text())
            for key, count in hierarchy.items():
                if not _node_meets(key, cube, box):
                    continue
                if count == SUBTREE_ELSEWHERE:
                    pending.append(key)
                elif count > 0:
                    found.append(key)
        return sorted(found)

    def _file(self, relative: str) -> Path:
        path = self._cache_dir / relative
        _download(
            self._http,
            self._schedule,
            f"{self._project.base_url}/{relative}",
            path,
            self._initial_backoff_s,
        )
        return path


def _node_meets(
    key: str,
    cube: tuple[float, float, float, float, float, float],
    box: tuple[float, float, float, float],
) -> bool:
    depth, x, y, _ = (int(part) for part in key.split("-"))
    min_x, min_y, _, max_x, max_y, _ = cube
    nodes_per_side = 1 << depth
    side_x, side_y = (max_x - min_x) / nodes_per_side, (max_y - min_y) / nodes_per_side
    west, south = min_x + x * side_x, min_y + y * side_y
    return (
        west <= box[2] and box[0] <= west + side_x and south <= box[3] and box[1] <= south + side_y
    )


def _read_laz(path: Path) -> LidarPoints:
    las = laspy.read(io.BytesIO(path.read_bytes()))
    withheld = np.asarray(las.withheld, dtype=bool)
    if CLASS_FLAGS_DIMENSION in las.point_format.dimension_names:
        withheld |= (np.asarray(las[CLASS_FLAGS_DIMENSION]) & WITHHELD_FLAG) != 0
    return LidarPoints(
        np.asarray(las.x),
        np.asarray(las.y),
        np.asarray(las.z),
        np.asarray(las.return_number),
        np.asarray(las.classification),
        withheld,
        np.asarray(las.gps_time),
    )


def _points_inside(points: LidarPoints, box: tuple[float, float, float, float]) -> LidarPoints:
    west, south, east, north = box
    return points.where(
        (points.x >= west) & (points.x <= east) & (points.y >= south) & (points.y <= north)
    )


def _download(
    http: httpx.Client,
    schedule: RequestSchedule,
    url: str,
    path: Path,
    initial_backoff_s: float,
) -> None:
    """Fetch `url` to `path` unless it is cached there."""
    if path.exists():
        return

    def attempt() -> httpx.Response:
        schedule.wait_for_slot()
        return checked(http.get(url))

    response = with_retry(attempt, initial_backoff_s)
    path.parent.mkdir(parents=True, exist_ok=True)
    # neighbouring windows fetched in parallel share nodes: each writer gets its own partial file
    partial = path.with_suffix(f"{path.suffix}.{uuid.uuid4().hex}.part")
    partial.write_bytes(response.content)
    partial.replace(path)


def _write(
    path: Path, dsm: np.ndarray, crs: str, transform: Affine, provenance: DsmProvenance
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    with rasterio.open(
        partial,
        "w",
        driver="GTiff",
        width=dsm.shape[1],
        height=dsm.shape[0],
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        compress="deflate",
    ) as dst:
        dst.write(dsm, 1)
        dst.update_tags(**{DSM_PROVENANCE_TAG: provenance.model_dump_json()})
    partial.replace(path)
