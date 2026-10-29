"""Esri World Imagery scene footprints: which capture each point of the basemap was drawn from.

One envelope `query` on layer 4 (Citations) returns every footprint drawn at a zoom over an area,
with its capture date, sensor and release. A scene is one capture, keyed by date and sensor:
several footprint polygons can share one (two at Southend, six at Ferrybridge), and all of them
carry the same satellite geometry. At one zoom the footprints are disjoint, so a point lies in at
most one scene.
"""

import functools
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, override

import numpy as np
import rasterio.features
import shapely
from affine import Affine
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from satmesh_core import WGS84, Aoi, require_best_transformer
from satmesh_data.esri import EsriClient

CACHE_SUBDIR = Path("esri-world-imagery") / "scenes"
UNLABELLED = -1
# footprints come back generalised to this many degrees (about 1 m in England): the full outline
# of one Southend polygon is otherwise several MB, and 1 m is the lidar grid the labels serve
MAX_ALLOWABLE_OFFSET_DEG = 1e-5
GEOMETRY_PRECISION_DIGITS = 6
AOI_KEY_DIGITS = 6


class EsriQueryError(Exception):
    """Esri answered a query with HTTP 200 and an error body."""


class SceneId(BaseModel):
    """One satellite capture: its acquisition date and sensor (e.g. GE01, WV02)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    capture_date: date
    sensor: str

    @override
    def __str__(self) -> str:
        """Return `YYYYMMDD SENSOR`, the form Esri's attributes use."""
        return f"{self.capture_date:%Y%m%d} {self.sensor}"


class _Attributes(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    object_id: int = Field(alias="OBJECTID")
    capture_date: date = Field(alias="SRC_DATE")
    resolution_m: float = Field(alias="SRC_RES")
    accuracy_m: float = Field(alias="SRC_ACC")
    sensor: str = Field(alias="SRC_DESC")
    min_zoom: int = Field(alias="MinMapLevel")
    max_zoom: int = Field(alias="MaxMapLevel")
    release: str = Field(alias="ReleaseName")

    @field_validator("capture_date", mode="before")
    @classmethod
    def _parse_yyyymmdd(cls, value: Any) -> date:  # noqa: ANN401 (raw JSON before validation)
        return datetime.strptime(str(value), "%Y%m%d").date()  # noqa: DTZ007 (a calendar date)


class _Geometry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    rings: list[list[tuple[float, float]]]


class _Feature(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    attributes: _Attributes
    geometry: _Geometry


class _ReleaseFeature(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    attributes: dict[str, str | int]


class _ErrorDetail(BaseModel):
    code: int
    message: str


class _Page(BaseModel):
    model_config = ConfigDict(extra="ignore")

    features: list[dict[str, Any]] = []
    exceeded_transfer_limit: bool = Field(default=False, alias="exceededTransferLimit")
    error: _ErrorDetail | None = None


_FEATURES = TypeAdapter(list[_Feature])


@dataclass(frozen=True)
class EsriScene:
    """The footprint of one scene at one zoom, in its map's CRS, from every polygon sharing it."""

    scene_id: SceneId
    resolution_m: float
    accuracy_m: float
    object_ids: tuple[int, ...]
    footprint: shapely.MultiPolygon


@dataclass(frozen=True)
class SceneMap:
    """The scenes Esri draws at `zoom` over an area, with footprints in `crs`."""

    crs: str
    zoom: int
    release: str
    scenes: tuple[EsriScene, ...]

    def in_crs(self, crs: str) -> "SceneMap":
        """Return the map with footprints reprojected to `crs` by PROJ's best transformation.

        Raises `GridMissingError` when that transformation needs a grid that is not installed
        (OSTN15 for BNG: the fallback Helmert shift is off by about 1.5 m).
        """
        transformer = require_best_transformer(self.crs, crs)

        def project(xy: np.ndarray) -> np.ndarray:
            return np.column_stack(transformer.transform(xy[:, 0], xy[:, 1]))

        scenes = tuple(
            EsriScene(
                s.scene_id,
                s.resolution_m,
                s.accuracy_m,
                s.object_ids,
                _polygonal(shapely.transform(s.footprint, project)),
            )
            for s in self.scenes
        )
        return SceneMap(crs, self.zoom, self.release, scenes)

    def labels_at(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Return, per point `(x, y)` in `crs`, its index in `scenes`, or `UNLABELLED` if none."""
        labels = np.full(np.shape(x), UNLABELLED, dtype=np.int32)
        for index, scene in enumerate(self.scenes):
            labels[(labels == UNLABELLED) & shapely.contains_xy(scene.footprint, x, y)] = index
        return labels

    def label_grid(self, transform: Affine, shape: tuple[int, int]) -> np.ndarray:
        """Return the scene index (or `UNLABELLED`) of each pixel centre of a raster in `crs`."""
        if not self.scenes:
            return np.full(shape, UNLABELLED, dtype=np.int32)
        shifted = rasterio.features.rasterize(
            [(s.footprint, index + 1) for index, s in enumerate(self.scenes)],
            out_shape=shape,
            transform=transform,
            fill=0,
            dtype="int32",
        )
        return shifted - 1

    def shares(self, area: Aoi) -> dict[SceneId, float]:
        """Return each scene's share of `area`'s ground area, largest first; `area` is in `crs`."""
        if area.crs != self.crs:
            msg = f"area is in {area.crs}, the footprints in {self.crs}"
            raise ValueError(msg)
        box = shapely.box(area.west, area.south, area.east, area.north)
        shares = {s.scene_id: s.footprint.intersection(box).area / box.area for s in self.scenes}
        return dict(sorted(shares.items(), key=lambda item: -item[1]))


def fetch_scene_map(esri: EsriClient, area: Aoi, zoom: int, cache_dir: Path) -> SceneMap:
    """Return the scenes drawn at `zoom` over `area`, in WGS84 longitude and latitude.

    A geometry-free query first names the release; the footprints are then read from the cache
    under that release, area and zoom, or queried and cached. A new Esri release therefore
    fetches new footprints, and a cached release costs one small request.
    """
    bounds = area.wgs84_bounds()
    release = _release_name(esri, bounds, zoom)
    path = cache_dir / CACHE_SUBDIR / _slug(release) / f"{_area_key(bounds)}-z{zoom}.json"
    if not path.exists():
        served = list(_query(esri, bounds, zoom, geometry=True))
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(".part")
        partial.write_text(json.dumps(served))
        partial.replace(path)
    return SceneMap(WGS84, zoom, release, _group(_FEATURES.validate_json(path.read_bytes())))


def _release_name(esri: EsriClient, bounds: tuple[float, float, float, float], zoom: int) -> str:
    features = [
        _ReleaseFeature.model_validate(f) for f in _query(esri, bounds, zoom, geometry=False)
    ]
    return "+".join(sorted({str(f.attributes["ReleaseName"]) for f in features}))


def _query(
    esri: EsriClient, bounds: tuple[float, float, float, float], zoom: int, *, geometry: bool
) -> Iterator[dict[str, Any]]:
    west, south, east, north = bounds
    params: dict[str, str | int | float] = {
        "geometry": f"{west},{south},{east},{north}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "where": f"MinMapLevel<={zoom} AND MaxMapLevel>={zoom}",
        "outFields": "*" if geometry else "OBJECTID,ReleaseName",
        "returnGeometry": "true" if geometry else "false",
        "orderByFields": "OBJECTID",
        "f": "json",
    }
    if geometry:
        params |= {
            "outSR": 4326,
            "geometryPrecision": GEOMETRY_PRECISION_DIGITS,
            "maxAllowableOffset": MAX_ALLOWABLE_OFFSET_DEG,
        }
    offset = 0
    while True:
        page = _Page.model_validate_json(esri.query_citations({**params, "resultOffset": offset}))
        if page.error is not None:
            msg = f"layer 4 query failed: {page.error.code} {page.error.message}"
            raise EsriQueryError(msg)
        yield from page.features
        if not page.exceeded_transfer_limit:
            return
        offset += len(page.features)


def _group(features: list[_Feature]) -> tuple[EsriScene, ...]:
    by_scene: dict[SceneId, list[_Feature]] = {}
    for feature in features:
        a = feature.attributes
        by_scene.setdefault(SceneId(capture_date=a.capture_date, sensor=a.sensor), []).append(
            feature
        )
    return tuple(
        EsriScene(
            scene_id=scene_id,
            resolution_m=members[0].attributes.resolution_m,
            accuracy_m=members[0].attributes.accuracy_m,
            object_ids=tuple(f.attributes.object_id for f in members),
            footprint=_polygonal(shapely.union_all([_even_odd(f.geometry.rings) for f in members])),
        )
        for scene_id, members in by_scene.items()
    )


def _even_odd(rings: list[list[tuple[float, float]]]) -> shapely.MultiPolygon:
    # holes and islands in holes occur; even-odd fill handles any nesting without trusting ring
    # orientation
    areas = [_polygonal(shapely.make_valid(shapely.Polygon(ring))) for ring in rings]
    return _polygonal(functools.reduce(shapely.symmetric_difference, areas, shapely.Polygon()))


def _polygonal(geometry: object) -> shapely.MultiPolygon:
    # make_valid can return a collection of polygons, multipolygons and stray lines; two levels of
    # get_parts reach every polygon
    parts = shapely.get_parts(shapely.get_parts(geometry))
    return shapely.MultiPolygon([p for p in parts if isinstance(p, shapely.Polygon)])


def _area_key(bounds: tuple[float, float, float, float]) -> str:
    return "_".join(f"{v:.{AOI_KEY_DIGITS}f}" for v in bounds)


def _slug(release: str) -> str:
    return re.sub(r"[^A-Za-z0-9.+-]+", "_", release)
