"""Position correction of a store's imagery: Esri displacement removed per vertex through its UVs.

Esri imagery sits metres from true ground position, and a raised point (roof, tree crown) further
still, because each satellite scene was taken off nadir and orthorectified onto a bare-earth DEM.
A point at height h above the ground is displaced by

    d(h) = t + l h,

with t (m, east and north) the scene's ground shift and l (m per m) its lean, positive when the
imagery lies east and north of the ground (`satmesh_eval.scene_lean`). The corrected texture at a
ground point p is Esri(p + d(h(p))), so each vertex samples its texture d(h) away from where it
stands; the pixels themselves are never resampled.

A `CorrectionField` holds one `SceneLean` per Esri scene (date and sensor) and the ground shift
measured in each rectangular cell of British National Grid. A vertex in a scene whose lean was
applied takes that scene's t and l; any other vertex takes the ground shift of the cell holding its
node's centre, with no lean, or nothing where the cell could not be measured.
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self

import mercantile
import numpy as np
import rasterio
from pydantic import BaseModel, ConfigDict, model_validator
from pyproj import Transformer

from satmesh_core import (
    BNG_ODN,
    BRITISH_NATIONAL_GRID,
    WGS84,
    ProgressReport,
    ecef_to_geodetic,
    ellipsoidal_height_from,
    wgs84_to,
)
from satmesh_data import UNLABELLED, WEB_MERCATOR, SceneId, SceneMap
from satmesh_mesh import read_vertices, with_texture_coordinates
from satmesh_tiles.node import MAX_LEAN, NodeRecord, PositionRecord
from satmesh_tiles.tiler import (
    CORRECTION_FILE,
    CORRECTION_SCHEMA_VERSION,
    ground_path,
    node_paths,
    read_record,
    require_current_correction,
    write_atomically,
)
from satmesh_tiles.tileset import stored_tiles

CellStatus = Literal["corrected", "uncorrected"]
POSITIONAL_ERROR_FILE = "positional_error.json"
UPDATE_PHASE = "updating tiles"
# a vertex's position, read back from float32 glTF, lands this close to its build-grid node; the
# float32 rounding is under 1e-4 of a grid step for the largest stored tiles
GRID_INDEX_TOLERANCE = 0.01
ERROR_BOUND_MEANING = (
    "95 % radial bound on the position error of the imagery, in metres: error_bound_m on open "
    "ground, plus error_bound_per_height per metre of height above ground for raised objects "
    "(roofs, tree crowns)."
)


class CellCorrection(BaseModel):
    """The Esri ground displacement measured in one rectangular BNG cell, or why it could not be.

    `displacement_east_m` and `displacement_north_m` are positive when the imagery is displaced
    east and north of the ground; both are zero when `status` is "uncorrected".
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    west_m: float
    south_m: float
    east_m: float
    north_m: float
    status: CellStatus
    displacement_east_m: float
    displacement_north_m: float
    error_bound_m: float
    windows_used: int
    windows_total: int


class LeanFit(BaseModel):
    """Fitted ground shift t (m) and lean l (m per m) of a scene, with 95 % bootstrap intervals.

    `azimuth_deg` is the direction raised points are displaced to, clockwise from grid north;
    its interval may run past 360 when it straddles north. `lean_radius_95` (m per m) is the 95th
    percentile of the distance of the bootstrap leans from the fitted lean. `roof_residual_m` is
    the median distance of the roof offsets from the fitted model.

    `ground_error_bound_m` is B_t = sqrt(w_E^2 + w_N^2 + r_m^2), with w_E, w_N the larger half of
    the 95 % bootstrap interval of t_E and t_N about the fit and r_m the registration method
    residual, the same propagation as a cell's bound. At height h the bound is
    B(h) = B_t + `lean_radius_95` h: a sum, not a quadrature, because t and l are fitted jointly
    and their errors are correlated; each term is a 95 % bound on its own, so B(h) holds whenever
    both do (at least 90 % by the union bound).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    t_east_m: float
    t_north_m: float
    lean_east: float
    lean_north: float
    k: float
    azimuth_deg: float
    t_east_interval_m: tuple[float, float]
    t_north_interval_m: tuple[float, float]
    k_interval: tuple[float, float]
    azimuth_interval_deg: tuple[float, float]
    lean_radius_95: float
    ground_error_bound_m: float
    at_cap: bool
    roof_residual_m: float
    bootstrap_draws: int


class SceneLean(BaseModel):
    """The lean of one Esri scene: applied, or rejected with the reason (and the fit, if any).

    A rejected scene's vertices keep the per-cell ground shift with no lean.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    scene: SceneId
    status: Literal["applied", "rejected"]
    reason: str | None
    fit: LeanFit | None
    roof_count: int
    window_count: int

    @model_validator(mode="after")
    def _status_matches(self) -> Self:
        if self.status == "applied" and (self.fit is None or self.reason is not None):
            msg = "an applied lean has a fit and no rejection reason"
            raise ValueError(msg)
        if self.status == "rejected" and self.reason is None:
            msg = "a rejected lean names its reason"
            raise ValueError(msg)
        return self


class CorrectionField(BaseModel):
    """Scene leans and cell ground shifts over an area, with the bound outside every cell.

    `scene_release` is the Esri release whose scene footprints labelled the measurements; None
    when the lean was not measured, and then `scenes` is empty.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[2] = CORRECTION_SCHEMA_VERSION
    uncorrected_error_bound_m: float
    cells: tuple[CellCorrection, ...]
    scene_release: str | None
    scenes: tuple[SceneLean, ...]

    @model_validator(mode="after")
    def _scenes_need_a_release(self) -> Self:
        if self.scene_release is None and self.scenes:
            msg = "scene leans name the Esri release their footprints came from"
            raise ValueError(msg)
        return self

    def cell_at(self, easting_m: float, northing_m: float) -> CellCorrection | None:
        """Return the cell holding a BNG point, or None outside every cell."""
        for cell in self.cells:
            if cell.west_m <= easting_m < cell.east_m and cell.south_m <= northing_m < cell.north_m:
                return cell
        return None

    def applied_leans(self) -> dict[SceneId, LeanFit]:
        """Return the fit of every scene whose lean is applied."""
        return {s.scene: s.fit for s in self.scenes if s.status == "applied" and s.fit is not None}


@dataclass(frozen=True)
class CorrectionSummary:
    """Nodes of a store by the correction at their centre, and vertices by what they took."""

    lean: int
    corrected: int
    uncorrected: int
    vertices: int
    lean_vertices: int
    past_texture_edge: int


@dataclass(frozen=True)
class _Displacement:
    """What one outcome removes, d = (east_m, north_m) + (lean_east, lean_north) h; its bound."""

    status: Literal["lean", "corrected", "uncorrected"]
    east_m: float
    north_m: float
    lean_east: float
    lean_north: float
    error_bound_m: float
    error_bound_per_height: float


@dataclass(frozen=True)
class _NodeUpdate:
    uv: np.ndarray
    position: PositionRecord
    lean_vertices: int


@dataclass(frozen=True)
class _Transforms:
    """PROJ transformers between the store's frames, built once: each needs its grids opened."""

    ecef_to_geodetic: Transformer
    bng_odn_to_wgs84: Transformer
    wgs84_to_bng: Transformer
    to_web_mercator: Transformer
    to_wgs84: Transformer

    @classmethod
    def build(cls) -> "_Transforms":
        return cls(
            ecef_to_geodetic(),
            ellipsoidal_height_from(BNG_ODN),
            wgs84_to(BRITISH_NATIONAL_GRID),
            Transformer.from_crs(WGS84, WEB_MERCATOR, always_xy=True),
            Transformer.from_crs(WEB_MERCATOR, WGS84, always_xy=True),
        )


def apply_correction(
    store_dir: Path, field: CorrectionField, scene_map: SceneMap | None, report: ProgressReport
) -> CorrectionSummary:
    """Set every node's texture coordinates to the corrected position and record it.

    Each vertex's coordinate is computed from its build-grid position, so a repeat or a revised
    field lands where a single application would. `scene_map` (in BNG) labels the vertices with
    their Esri scene; it may be None only when no lean in `field` is applied. Vertices whose
    coordinate leaves 0..1 sample the texture's edge pixels (clamp-to-edge sampler). The GLB is
    written before the record. `report` is called with phase "updating tiles" before the first
    node and after each one.
    """
    require_current_correction(store_dir)
    leans = field.applied_leans()
    if leans and (scene_map is None or scene_map.crs != BRITISH_NATIONAL_GRID):
        msg = f"applied scene leans need the scene map in {BRITISH_NATIONAL_GRID}"
        raise ValueError(msg)
    (store_dir / CORRECTION_FILE).write_text(field.model_dump_json(indent=1))
    transforms = _Transforms.build()
    counts = {"lean": 0, "corrected": 0, "uncorrected": 0}
    vertices = lean_vertices = outside = 0
    tiles = sorted(stored_tiles(store_dir))
    report(UPDATE_PHASE, 0, len(tiles))
    for done, tile in enumerate(tiles, start=1):
        record = read_record(store_dir, tile)
        glb_path, record_path = node_paths(store_dir, tile)
        glb = glb_path.read_bytes()
        update = _node_update(store_dir, tile, record, glb, field, leans, scene_map, transforms)
        write_atomically(glb_path, with_texture_coordinates(glb, update.uv))
        updated = record.model_copy(update={"position": update.position})
        write_atomically(record_path, updated.model_dump_json(indent=1).encode())
        counts[update.position.status] += 1
        vertices += len(update.uv)
        lean_vertices += update.lean_vertices
        outside += _past_texture_edge(update.uv, record.texture_px)
        report(UPDATE_PHASE, done, len(tiles))
    return CorrectionSummary(
        counts["lean"], counts["corrected"], counts["uncorrected"], vertices, lean_vertices, outside
    )


def _node_update(  # noqa: PLR0913, PLR0917 (one node's inputs, the field and the shared transforms)
    store_dir: Path,
    tile: mercantile.Tile,
    record: NodeRecord,
    glb: bytes,
    field: CorrectionField,
    leans: dict[SceneId, LeanFit],
    scene_map: SceneMap | None,
    transforms: _Transforms,
) -> _NodeUpdate:
    positions, _ = read_vertices(glb)
    if len(positions) != record.vertices:
        msg = f"node {tile} GLB has {len(positions)} vertices, its record {record.vertices}"
        raise ValueError(msg)
    grid = _vertex_grid(tile, record, positions, transforms)
    with rasterio.open(ground_path(store_dir, tile)) as src:
        ground = src.read(1).astype(np.float64)
    heights = _heights_above_ground(grid, ground, record.terrain_vertices)
    centre_e, centre_n = _centre_bng(tile, transforms)
    ground_only = _cell_displacement(field, centre_e, centre_n)
    choice = _SceneChoice.of(scene_map, leans, ground_only)
    taken = choice.per_vertex(grid.easting_m, grid.northing_m)
    displacement = _removed_displacement(taken, heights)
    moved = _texture_fractions(
        tile, grid.easting_m + displacement[:, 0], grid.northing_m + displacement[:, 1], transforms
    )
    here = _texture_fractions(tile, grid.easting_m, grid.northing_m, transforms)
    last = _grid_last_index(record)
    base = np.column_stack([grid.cols / last, 1 - grid.rows / last])
    scene, at_centre = choice.at(centre_e, centre_n)
    position = PositionRecord(
        status=at_centre.status,
        scene=scene,
        east_m=at_centre.east_m,
        north_m=at_centre.north_m,
        lean_east=at_centre.lean_east,
        lean_north=at_centre.lean_north,
        error_bound_m=max(d.error_bound_m for d in taken),
        error_bound_per_height=max(d.error_bound_per_height for d in taken),
    )
    lean_vertices = sum(d.status == "lean" for d in taken)
    return _NodeUpdate(base + moved - here, position, lean_vertices)


@dataclass(frozen=True)
class _SceneChoice:
    """Which displacement a point takes: its scene's lean where applied, else the ground shift."""

    scene_map: SceneMap | None
    by_label: tuple[_Displacement, ...]
    ground_only: _Displacement

    @classmethod
    def of(
        cls, scene_map: SceneMap | None, leans: dict[SceneId, LeanFit], ground_only: _Displacement
    ) -> "_SceneChoice":
        scenes = scene_map.scenes if scene_map is not None else ()
        by_label = tuple(
            _lean_displacement(leans[s.scene_id]) if s.scene_id in leans else ground_only
            for s in scenes
        )
        return cls(scene_map, by_label, ground_only)

    def per_vertex(self, easting_m: np.ndarray, northing_m: np.ndarray) -> list[_Displacement]:
        labels = self._labels(easting_m, northing_m)
        return [self.ground_only if i == UNLABELLED else self.by_label[i] for i in labels.tolist()]

    def at(self, easting_m: float, northing_m: float) -> tuple[SceneId | None, _Displacement]:
        label = int(self._labels(np.array([easting_m]), np.array([northing_m]))[0])
        if label == UNLABELLED or self.scene_map is None:
            return None, self.ground_only
        return self.scene_map.scenes[label].scene_id, self.by_label[label]

    def _labels(self, easting_m: np.ndarray, northing_m: np.ndarray) -> np.ndarray:
        if self.scene_map is None:
            return np.full(len(easting_m), UNLABELLED)
        return self.scene_map.labels_at(easting_m, northing_m)


def _removed_displacement(taken: list[_Displacement], heights: np.ndarray) -> np.ndarray:
    """Return d = t + l h (m, east and north) per vertex from what each vertex takes."""
    t = np.array([[d.east_m, d.north_m] for d in taken])
    lean = np.array([[d.lean_east, d.lean_north] for d in taken])
    return t + lean * heights[:, None]


def _past_texture_edge(uv: np.ndarray, texture_px: tuple[int, int]) -> int:
    """Count vertices sampling more than a pixel beyond the texture, where clamping smears it."""
    pixel = 1 / np.array(texture_px, dtype=np.float64)
    return int(((uv < -pixel) | (uv > 1 + pixel)).any(axis=1).sum())


@dataclass(frozen=True)
class _VertexGrid:
    """Each vertex's build-grid node (row 0 north) and its BNG position and ODN height."""

    rows: np.ndarray
    cols: np.ndarray
    easting_m: np.ndarray
    northing_m: np.ndarray
    odn_height_m: np.ndarray


def _vertex_grid(
    tile: mercantile.Tile, record: NodeRecord, positions: np.ndarray, transforms: _Transforms
) -> _VertexGrid:
    """Locate each glTF vertex on the node's build grid, through ECEF and the store's grids.

    Skirt vertices hang straight below a boundary vertex and land on its grid node.
    """
    enu = np.column_stack([positions[:, 0], -positions[:, 2], positions[:, 1]])
    ecef = (np.array(record.enu_to_ecef) @ np.column_stack([enu, np.ones(len(enu))]).T)[:3]
    lon, lat, ellipsoidal = transforms.ecef_to_geodetic.transform(*ecef)
    easting, northing, odn = transforms.bng_odn_to_wgs84.transform(
        lon, lat, ellipsoidal, direction="INVERSE"
    )
    x, y = transforms.to_web_mercator.transform(lon, lat)
    bounds = mercantile.xy_bounds(tile)
    last = _grid_last_index(record)
    cols = (x - bounds.left) / (bounds.right - bounds.left) * last
    rows = (bounds.top - y) / (bounds.top - bounds.bottom) * last
    nearest_cols, nearest_rows = np.rint(cols), np.rint(rows)
    off_grid = max(np.abs(cols - nearest_cols).max(), np.abs(rows - nearest_rows).max())
    if off_grid > GRID_INDEX_TOLERANCE:
        msg = f"node {tile} vertices lie {off_grid:.3f} grid steps off its build grid"
        raise ValueError(msg)
    return _VertexGrid(
        nearest_rows.astype(int),
        nearest_cols.astype(int),
        np.asarray(easting),
        np.asarray(northing),
        np.asarray(odn),
    )


def _grid_last_index(record: NodeRecord) -> int:
    side = math.isqrt(record.grid_nodes)
    if side * side != record.grid_nodes:
        msg = f"node grid of {record.grid_nodes} nodes is not square"
        raise ValueError(msg)
    return side - 1


def _heights_above_ground(
    grid: _VertexGrid, ground: np.ndarray, terrain_vertices: int
) -> np.ndarray:
    """Return DSM minus DTM at each vertex; a skirt vertex takes the height of the one above it."""
    terrain = slice(0, terrain_vertices)
    by_node = np.full(ground.shape, np.nan)
    by_node[grid.rows[terrain], grid.cols[terrain]] = (
        grid.odn_height_m[terrain] - ground[grid.rows[terrain], grid.cols[terrain]]
    )
    heights = by_node[grid.rows, grid.cols]
    if not np.isfinite(heights).all():
        msg = "a skirt vertex has no terrain vertex above it"
        raise ValueError(msg)
    return heights


def _lean_displacement(fit: LeanFit) -> _Displacement:
    return _Displacement(
        "lean",
        fit.t_east_m,
        fit.t_north_m,
        fit.lean_east,
        fit.lean_north,
        fit.ground_error_bound_m,
        fit.lean_radius_95,
    )


def _cell_displacement(
    field: CorrectionField, easting_m: float, northing_m: float
) -> _Displacement:
    cell = field.cell_at(easting_m, northing_m)
    if cell is None or cell.status == "uncorrected":
        bound = field.uncorrected_error_bound_m if cell is None else cell.error_bound_m
        return _Displacement("uncorrected", 0.0, 0.0, 0.0, 0.0, bound, MAX_LEAN)
    return _Displacement(
        "corrected",
        cell.displacement_east_m,
        cell.displacement_north_m,
        0.0,
        0.0,
        cell.error_bound_m,
        MAX_LEAN,
    )


def _texture_fractions(
    tile: mercantile.Tile, easting_m: np.ndarray, northing_m: np.ndarray, transforms: _Transforms
) -> np.ndarray:
    """Return the texture coordinates (v up) of BNG points in a node's Web Mercator texture.

    The difference between a vertex's point and the point d away is J d with J the exact local
    Jacobian from BNG metres to texture coordinates, with no linearisation over the node.
    """
    lon, lat = transforms.wgs84_to_bng.transform(easting_m, northing_m, direction="INVERSE")
    x, y = transforms.to_web_mercator.transform(lon, lat)
    bounds = mercantile.xy_bounds(tile)
    return np.column_stack(
        [
            (np.asarray(x) - bounds.left) / (bounds.right - bounds.left),
            (np.asarray(y) - bounds.bottom) / (bounds.top - bounds.bottom),
        ]
    )


def _centre_bng(tile: mercantile.Tile, transforms: _Transforms) -> tuple[float, float]:
    bounds = mercantile.xy_bounds(tile)
    lon, lat = transforms.to_wgs84.transform(
        (bounds.left + bounds.right) / 2, (bounds.top + bounds.bottom) / 2
    )
    easting, northing = transforms.wgs84_to_bng.transform(lon, lat)
    return float(easting), float(northing)


def write_positional_error(store_dir: Path, out_path: Path) -> None:
    """Write the position error bound of every finest-level node of a store as JSON."""
    require_current_correction(store_dir)
    tiles = sorted(stored_tiles(store_dir))
    if not tiles:
        msg = f"no nodes in store {store_dir}"
        raise ValueError(msg)
    finest = max(tile.z for tile in tiles)
    positions = {tile: read_record(store_dir, tile).position for tile in tiles if tile.z == finest}
    measured = [p for p in positions.values() if p is not None]
    report = {
        "meaning": ERROR_BOUND_MEANING,
        "unmeasured_nodes": len(positions) - len(measured),
        "max_error_bound_m": max((p.error_bound_m for p in measured), default=None),
        "max_error_bound_per_height": max(
            (p.error_bound_per_height for p in measured), default=None
        ),
        "nodes": [
            {"z": tile.z, "x": tile.x, "y": tile.y} | _position_json(position)
            for tile, position in positions.items()
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=1))


def _position_json(position: PositionRecord | None) -> dict[str, object]:
    if position is None:
        return {"status": "unmeasured"}
    scene = None if position.scene is None else str(position.scene)
    return position.model_dump(mode="json") | {"scene": scene}
