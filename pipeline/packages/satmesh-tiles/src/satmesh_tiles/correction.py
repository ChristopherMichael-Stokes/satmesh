"""Position correction of a store's imagery: per-cell Esri displacement applied to node UVs.

Esri imagery sits metres from true ground position, by an amount that differs between places. A
`CorrectionField` holds the displacement measured in each rectangular cell of British National Grid
(positive east and north: the imagery is displaced that way from the ground). Applying it moves
where every node's vertices sample their texture, so the pixels themselves are never resampled.
Nodes in cells where the displacement could not be measured keep their texture position and carry
the largest displacement seen in the survey as their error bound.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import mercantile
from pydantic import BaseModel, ConfigDict
from pyproj import Transformer

from satmesh_core import WGS84, ProgressReport, wgs84_to_bng
from satmesh_data import WEB_MERCATOR
from satmesh_mesh import shift_texture_coordinates
from satmesh_tiles.node import PositionRecord
from satmesh_tiles.tiler import node_paths, read_record, write_atomically
from satmesh_tiles.tileset import stored_tiles

CellStatus = Literal["corrected", "uncorrected"]
CORRECTION_FILE = "correction.json"
POSITIONAL_ERROR_FILE = "positional_error.json"
UPDATE_PHASE = "updating tiles"
ERROR_BOUND_MEANING = (
    "95 % radial bound on the position error of the imagery on open ground, in metres. Raised "
    "objects (roofs, tree crowns) lean in the source imagery and are not corrected."
)


class CellCorrection(BaseModel):
    """The Esri displacement measured in one rectangular BNG cell, or why it could not be.

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


class CorrectionField(BaseModel):
    """Cell corrections over an area, with the bound for places outside every cell."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    uncorrected_error_bound_m: float
    cells: tuple[CellCorrection, ...]

    def position_at(self, easting_m: float, northing_m: float) -> PositionRecord:
        """Return the correction of the cell holding a BNG point; uncorrected outside every cell."""
        for cell in self.cells:
            if cell.west_m <= easting_m < cell.east_m and cell.south_m <= northing_m < cell.north_m:
                return PositionRecord(
                    status=cell.status,
                    east_m=cell.displacement_east_m,
                    north_m=cell.displacement_north_m,
                    error_bound_m=cell.error_bound_m,
                )
        return PositionRecord(
            status="uncorrected",
            east_m=0.0,
            north_m=0.0,
            error_bound_m=self.uncorrected_error_bound_m,
        )


@dataclass(frozen=True)
class CorrectionSummary:
    """Nodes of a store by outcome of applying a correction."""

    corrected: int
    uncorrected: int
    rewritten: int


def apply_correction(
    store_dir: Path, field: CorrectionField, report: ProgressReport
) -> CorrectionSummary:
    """Move every node's texture coordinates to the corrected position and record it.

    Safe to repeat or to follow with a revised field: each node moves by the difference between
    the correction in its record and the new one. The GLB is written before the record, so an
    interrupted run is redone, not skipped. `report` is called with phase "updating tiles" before
    the first node and after each one.
    """
    (store_dir / CORRECTION_FILE).write_text(field.model_dump_json(indent=1))
    corrected = uncorrected = rewritten = 0
    tiles = sorted(stored_tiles(store_dir))
    report(UPDATE_PHASE, 0, len(tiles))
    for done, tile in enumerate(tiles, start=1):
        record = read_record(store_dir, tile)
        centre_e, centre_n = _centre_bng(tile)
        position = field.position_at(centre_e, centre_n)
        corrected += position.status == "corrected"
        uncorrected += position.status == "uncorrected"
        if record.position == position:
            report(UPDATE_PHASE, done, len(tiles))
            continue
        before = record.position or PositionRecord(
            status="uncorrected", east_m=0.0, north_m=0.0, error_bound_m=0.0
        )
        du, dv = (
            after - was
            for after, was in zip(
                _texture_fractions(tile, position.east_m, position.north_m),
                _texture_fractions(tile, before.east_m, before.north_m),
                strict=True,
            )
        )
        glb_path, record_path = node_paths(store_dir, tile)
        if du or dv:
            write_atomically(glb_path, shift_texture_coordinates(glb_path.read_bytes(), du, dv))
        updated = record.model_copy(update={"position": position})
        write_atomically(record_path, updated.model_dump_json(indent=1).encode())
        rewritten += 1
        report(UPDATE_PHASE, done, len(tiles))
    return CorrectionSummary(corrected, uncorrected, rewritten)


def write_positional_error(store_dir: Path, out_path: Path) -> None:
    """Write the position error bound of every finest-level node of a store as JSON."""
    tiles = sorted(stored_tiles(store_dir))
    if not tiles:
        msg = f"no nodes in store {store_dir}"
        raise ValueError(msg)
    finest = max(tile.z for tile in tiles)
    nodes = []
    for tile in (t for t in tiles if t.z == finest):
        position = read_record(store_dir, tile).position
        nodes.append(
            {
                "z": tile.z,
                "x": tile.x,
                "y": tile.y,
                "status": position.status if position else "unmeasured",
                "east_m": position.east_m if position else None,
                "north_m": position.north_m if position else None,
                "error_bound_m": position.error_bound_m if position else None,
            }
        )
    bounds = [n["error_bound_m"] for n in nodes if n["error_bound_m"] is not None]
    report = {
        "meaning": ERROR_BOUND_MEANING,
        "unmeasured_nodes": sum(n["status"] == "unmeasured" for n in nodes),
        "max_error_bound_m": max(bounds) if bounds else None,
        "nodes": nodes,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=1))


def _centre_bng(tile: mercantile.Tile) -> tuple[float, float]:
    bounds = mercantile.xy_bounds(tile)
    to_wgs84 = Transformer.from_crs(WEB_MERCATOR, WGS84, always_xy=True)
    lon, lat = to_wgs84.transform(
        (bounds.left + bounds.right) / 2, (bounds.top + bounds.bottom) / 2
    )
    easting, northing = wgs84_to_bng().transform(lon, lat)
    return float(easting), float(northing)


def _texture_fractions(tile: mercantile.Tile, east_m: float, north_m: float) -> tuple[float, float]:
    """Return the (east, north) texture-coordinate change that samples `east_m`, `north_m` away.

    A feature displaced east and north in the imagery is found by sampling east and north of the
    vertex, so the ground displacement at the node's centre, expressed in the tile's Web Mercator
    frame, as a fraction of the tile's width and height.
    """
    bounds = mercantile.xy_bounds(tile)
    to_wgs84 = Transformer.from_crs(WEB_MERCATOR, WGS84, always_xy=True)
    to_web_mercator = Transformer.from_crs(WGS84, WEB_MERCATOR, always_xy=True)
    centre_x, centre_y = (bounds.left + bounds.right) / 2, (bounds.top + bounds.bottom) / 2
    easting, northing = wgs84_to_bng().transform(*to_wgs84.transform(centre_x, centre_y))
    lon, lat = wgs84_to_bng().transform(easting + east_m, northing + north_m, direction="INVERSE")
    moved_x, moved_y = to_web_mercator.transform(lon, lat)
    return (
        float((moved_x - centre_x) / (bounds.right - bounds.left)),
        float((moved_y - centre_y) / (bounds.top - bounds.bottom)),
    )
