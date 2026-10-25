"""Pipeline height check: do a stored node's vertices sit at the heights of the EA rasters?

The mesh is built from the first-return DSM, so a node's terrain vertices must reproduce the DSM
(bilinear) at their own BNG position, and its ground grid must reproduce the DTM. This checks the
georeference chain (ENU, ECEF, OSTN15 and OSGM15), the UVs' sibling positions and the ground-grid
transform with a path independent of the build: pyproj called directly and a separate sampler. It
does not measure the lidar's own accuracy.
"""

from dataclasses import dataclass
from pathlib import Path

import mercantile
import numpy as np
import pygltflib
import rasterio
from pyproj import Transformer
from pyproj.transformer import TransformerGroup
from scipy.interpolate import RegularGridInterpolator

from satmesh_data import EA_DSM, EA_DTM, cached_lidar_path
from satmesh_eval.heights import HeightScore, score_heights
from satmesh_tiles import NodeRecord, ground_path, node_paths, read_record

ECEF = "EPSG:4978"
BNG_ODN = "EPSG:7405"
BNG = "EPSG:27700"
GLTF_POSITION_WIDTH = 3


class GridMissingError(Exception):
    """PROJ lacks the OSTN15 or OSGM15 grid, so a check would silently use a worse fallback."""


@dataclass(frozen=True)
class NodeHeightCheck:
    """Height differences of one node against the cached EA rasters (estimate minus raster, m)."""

    tile: mercantile.Tile
    vertices_against_dsm: HeightScore
    ground_grid_against_dtm: HeightScore


def check_store(store_dir: Path, cache_dir: Path) -> list[NodeHeightCheck]:
    """Check every node of the store against the lidar rasters in `cache_dir`."""
    group = TransformerGroup(ECEF, BNG_ODN, always_xy=True)
    if not group.best_available:
        msg = f"PROJ has no OSTN15 and OSGM15 grids for {ECEF} to {BNG_ODN}; run `pyproj sync`"
        raise GridMissingError(msg)
    return [check_node(store_dir, cache_dir, tile) for tile in _stored_tiles(store_dir)]


def check_node(store_dir: Path, cache_dir: Path, tile: mercantile.Tile) -> NodeHeightCheck:
    """Compare one node's terrain vertices with the DSM and its ground grid with the DTM."""
    record = read_record(store_dir, tile)
    dsm = _interpolator(cached_lidar_path(cache_dir, EA_DSM, record.dsm), "linear")
    dtm = _interpolator(cached_lidar_path(cache_dir, EA_DTM, record.dtm), "linear")
    easting, northing, odn = _vertex_bng_odn(node_paths(store_dir, tile)[0], record)
    ground_e, ground_n, ground_odn = _ground_bng_odn(ground_path(store_dir, tile))
    return NodeHeightCheck(
        tile,
        score_heights(odn - dsm((northing, easting))),
        score_heights(ground_odn - dtm((ground_n, ground_e))),
    )


def _stored_tiles(store_dir: Path) -> list[mercantile.Tile]:
    return sorted(
        mercantile.Tile(int(path.parent.name), int(path.stem), int(path.parent.parent.name))
        for path in (store_dir / "nodes").glob("*/*/*.json")
    )


def _vertex_bng_odn(
    glb_path: Path, record: NodeRecord
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    gltf = pygltflib.GLTF2().load(str(glb_path))
    accessor = gltf.accessors[gltf.meshes[0].primitives[0].attributes.POSITION]
    view = gltf.bufferViews[accessor.bufferView]
    local = (
        np.frombuffer(
            gltf.binary_blob(), np.float32, accessor.count * GLTF_POSITION_WIDTH, view.byteOffset
        )
        .reshape(-1, GLTF_POSITION_WIDTH)[: record.terrain_vertices]
        .astype(np.float64)
    )
    enu = np.column_stack([local[:, 0], -local[:, 2], local[:, 1]])
    ecef = (np.array(record.enu_to_ecef) @ np.column_stack([enu, np.ones(len(enu))]).T).T[:, :3]
    return Transformer.from_crs(ECEF, BNG_ODN, always_xy=True).transform(*ecef.T)


def _ground_bng_odn(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    with rasterio.open(path) as src:
        heights = src.read(1).astype(np.float64)
        rows, cols = np.indices(src.shape)
        x, y = src.xy(rows.ravel(), cols.ravel())
        grid_crs = src.crs
    easting, northing = Transformer.from_crs(grid_crs, BNG, always_xy=True).transform(
        np.array(x), np.array(y)
    )
    return easting, northing, heights.ravel()


def _interpolator(path: Path, method: str) -> RegularGridInterpolator:
    with rasterio.open(path) as src:
        heights = src.read(1).astype(np.float64)
        transform = src.transform
    rows, cols = heights.shape
    eastings = transform.c + transform.a * (np.arange(cols) + 0.5)
    northings = transform.f + transform.e * (np.arange(rows) + 0.5)
    # RegularGridInterpolator wants ascending axes; northings descend down the rows
    return RegularGridInterpolator((northings[::-1], eastings), heights[::-1], method=method)
