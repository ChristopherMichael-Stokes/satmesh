"""3D Tiles 1.1 tileset over a store: one explicit tree of glTF-content tiles."""

import itertools
import json
from pathlib import Path
from typing import Any

import mercantile
import numpy as np

from satmesh_tiles.node import NodeRecord
from satmesh_tiles.tiler import (
    STORE_NODE_DIR,
    node_paths,
    read_record,
    require_current_correction,
)

TILESET_FILE = "tileset.json"
TILESET_VERSION = "1.1"
BOX_CORNER_SIGNS = np.array(list(itertools.product((-1.0, 1.0), repeat=3)))


def export_3dtiles(store_dir: Path) -> Path:
    """Write `tileset.json` into `store_dir` and return its path.

    Content URIs are the store's own GLBs, so the store directory served as static files is a
    tileset. The tree is rebuilt from the nodes present: a node's children are its four Web Mercator
    children when all four exist, and roots are nodes whose parent is absent. Raises
    `StaleCorrectionError` for a store corrected under an older correction schema.
    """
    require_current_correction(store_dir)
    tiles = stored_tiles(store_dir)
    if not tiles:
        msg = f"no nodes in store {store_dir}"
        raise ValueError(msg)
    records = {tile: read_record(store_dir, tile) for tile in tiles}
    roots = sorted(tile for tile in tiles if mercantile.parent(tile) not in tiles)
    container = _matrix(records[roots[0]])
    built = [_tile_json(tile, records, container, store_dir) for tile in roots]
    low, high = _bounds_in(container, np.concatenate([corners for _, corners in built]))
    # no content to show, so the container's error is its extent and it always refines
    error = float(np.linalg.norm(high - low))
    root = {
        "transform": _column_major(container),
        "boundingVolume": {"box": _box_json(low, high)},
        "geometricError": error,
        "refine": "REPLACE",
        "children": [tile_json for tile_json, _ in built],
    }
    path = store_dir / TILESET_FILE
    document = {"asset": {"version": TILESET_VERSION}, "geometricError": error, "root": root}
    path.write_text(json.dumps(document, indent=1))
    return path


def _tile_json(
    tile: mercantile.Tile,
    records: dict[mercantile.Tile, NodeRecord],
    parent_matrix: np.ndarray,
    store_dir: Path,
) -> tuple[dict[str, Any], np.ndarray]:
    """Return the tile's JSON and the ECEF corners of its bounding box.

    The box is the union of the node's own vertices and its children's boxes, so a culled parent
    never hides a child.
    """
    record = records[tile]
    matrix = _matrix(record)
    own = _ecef_corners_of_box(matrix, np.array(record.enu_min), np.array(record.enu_max))
    kids = [kid for kid in mercantile.children(tile) if kid in records]
    built = [_tile_json(kid, records, matrix, store_dir) for kid in kids]
    corners = np.concatenate([own, *(c for _, c in built)])
    low, high = _bounds_in(matrix, corners)
    texel_m = (record.enu_max[0] - record.enu_min[0]) / record.texture_px[0]
    tile_json: dict[str, Any] = {
        "transform": _column_major(np.linalg.inv(parent_matrix) @ matrix),
        "boundingVolume": {"box": _box_json(low, high)},
        "geometricError": max(record.max_error_m, texel_m),
        "refine": "REPLACE",
        "content": {"uri": node_paths(store_dir, tile)[0].relative_to(store_dir).as_posix()},
    }
    if built:
        tile_json["children"] = [child for child, _ in built]
    return tile_json, _ecef_corners_of_box(matrix, low, high)


def stored_tiles(store_dir: Path) -> set[mercantile.Tile]:
    """Return every node that has a record in the store."""
    return {
        mercantile.Tile(int(record.parent.name), int(record.stem), int(record.parent.parent.name))
        for record in (store_dir / STORE_NODE_DIR).glob("*/*/*.json")
    }


def _matrix(record: NodeRecord) -> np.ndarray:
    return np.array(record.enu_to_ecef)


def _column_major(matrix: np.ndarray) -> list[float]:
    return [float(v) for v in matrix.T.flatten()]


def _ecef_corners_of_box(matrix: np.ndarray, low: np.ndarray, high: np.ndarray) -> np.ndarray:
    centre, half = (low + high) / 2, (high - low) / 2
    local = centre + BOX_CORNER_SIGNS * half
    return (matrix @ np.column_stack([local, np.ones(len(local))]).T).T[:, :3]


def _bounds_in(matrix: np.ndarray, ecef: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return the axis-aligned bounds of ECEF points in the frame whose ENU-to-ECEF is `matrix`."""
    local = (np.linalg.inv(matrix) @ np.column_stack([ecef, np.ones(len(ecef))]).T).T[:, :3]
    return local.min(axis=0), local.max(axis=0)


def _box_json(low: np.ndarray, high: np.ndarray) -> list[float]:
    """3D Tiles box: centre, then the three half-axis vectors, axis-aligned in the tile's frame."""
    centre, half = (low + high) / 2, (high - low) / 2
    return [
        *(float(v) for v in centre),
        float(half[0]),
        0.0,
        0.0,
        0.0,
        float(half[1]),
        0.0,
        0.0,
        0.0,
        float(half[2]),
    ]
