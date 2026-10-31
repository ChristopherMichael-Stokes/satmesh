"""Bare-earth (DTM) and flat-plane scenes from a store, draped with the same leaf textures.

Each leaf of a store carries its DSM mesh, its texture and a ground (DTM) height grid on the same
Web Mercator node grid as the DSM. These scenes keep the texture and replace the geometry, so a
render differs from the DSM render only by what the geometry puts where.
"""

from pathlib import Path

import mercantile
import numpy as np
import rasterio
from pyproj import Transformer
from trimesh import Trimesh
from trimesh.ray.ray_pyembree import RayMeshIntersector

from satmesh_core import WGS84, geodetic_to_ecef
from satmesh_data import WEB_MERCATOR
from satmesh_eval.perspective import AreaScene, SceneLeaf, load_leaf_texture
from satmesh_tiles.area import area_frame, leaf_records
from satmesh_tiles.tiler import ground_path

GROUND_GRID_STRIDE = 4  # 0.5 m DTM nodes every 2 m; bare earth is smooth at that scale


def load_ground_scene(store_dir: Path, stride: int = GROUND_GRID_STRIDE) -> AreaScene:
    """Bare-earth scene: every leaf's DTM grid, every `stride`-th node, draped with its texture.

    Grid node (row, column), row 0 north, sits at the Web Mercator position of that node of the
    tile and at the DTM height in the source's vertical datum, moved to the ellipsoid by the
    record's geoid separation (constant over a tile to millimetres). Texture coordinates follow
    the node grid: u = column / last, v = row / last in glTF's top-left convention.
    """
    records = leaf_records(store_dir)
    frame = area_frame(records)
    to_wgs84 = Transformer.from_crs(WEB_MERCATOR, WGS84, always_xy=True)
    leaves = []
    for tile, record in records.items():
        with rasterio.open(ground_path(store_dir, tile)) as source:
            heights = source.read(1)
        rows, columns = _strided_indices(heights.shape[0], stride)
        bounds = mercantile.xy_bounds(tile)
        last = heights.shape[0] - 1
        x = bounds.left + (bounds.right - bounds.left) * columns / last
        y = bounds.top - (bounds.top - bounds.bottom) * rows / last
        grid_x, grid_y = np.meshgrid(x, y)
        longitude, latitude = to_wgs84.transform(grid_x, grid_y)
        ellipsoidal = heights[np.ix_(rows, columns)] + record.geoid_separation_m
        ecef = np.stack(geodetic_to_ecef().transform(longitude, latitude, ellipsoidal), axis=-1)
        vertices = frame.to_enu(ecef.reshape(-1, 3))
        uv = np.stack(np.meshgrid(columns / last, rows / last), axis=-1).reshape(-1, 2)
        leaves.append(
            SceneLeaf(
                Trimesh(vertices, _grid_triangles(len(rows), len(columns)), process=False),
                uv,
                load_leaf_texture(store_dir, tile),
            )
        )
    return AreaScene(tuple(leaves), frame)


def flattened(scene: AreaScene, height_m: float) -> AreaScene:
    """`scene` with every vertex moved to the horizontal plane at area-ENU `height_m`."""
    leaves = []
    for leaf in scene.leaves:
        vertices = np.array(leaf.mesh.vertices)
        vertices[:, 2] = height_m
        leaves.append(
            SceneLeaf(Trimesh(vertices, leaf.mesh.faces, process=False), leaf.uv, leaf.texture)
        )
    return AreaScene(tuple(leaves), scene.frame)


def ground_height_m(scene: AreaScene, east_m: float, north_m: float) -> float:
    """Height of the highest surface of `scene` above area-ENU (east, north), by a vertical ray.

    Raises `ValueError` if no leaf covers the point.
    """
    heights = []
    for leaf in scene.leaves:
        low, high = leaf.mesh.bounds
        if not (low[0] <= east_m <= high[0] and low[1] <= north_m <= high[1]):
            continue
        hits, _, _ = RayMeshIntersector(leaf.mesh).intersects_location(
            np.array([[east_m, north_m, high[2] + 1.0]]), np.array([[0.0, 0.0, -1.0]])
        )
        heights.extend(hits[:, 2])
    if not heights:
        msg = f"no leaf covers ({east_m}, {north_m})"
        raise ValueError(msg)
    return float(max(heights))


def _strided_indices(count: int, stride: int) -> tuple[np.ndarray, np.ndarray]:
    """Row and column indices 0, stride, ... ending on the last node, so tile edges stay shared."""
    indices = np.unique(np.append(np.arange(0, count, stride), count - 1))
    return indices, indices


def _grid_triangles(rows: int, columns: int) -> np.ndarray:
    """Two triangles per cell of a row-major vertex grid, wound counter-clockwise seen from above.

    Row 0 is north, so the vertex below-right of (r, c) is (r + 1, c + 1) and the winding is
    (r, c) -> (r + 1, c) -> (r, c + 1) for the south-west triangle.
    """
    index = np.arange(rows * columns).reshape(rows, columns)
    top_left, top_right = index[:-1, :-1].ravel(), index[:-1, 1:].ravel()
    bottom_left, bottom_right = index[1:, :-1].ravel(), index[1:, 1:].ravel()
    return np.concatenate(
        [
            np.stack([top_left, bottom_left, top_right], axis=1),
            np.stack([top_right, bottom_left, bottom_right], axis=1),
        ]
    )
