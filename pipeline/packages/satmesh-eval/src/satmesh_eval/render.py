"""Orthographic top-down render of a store's finest nodes in BNG, for comparison with imagery.

Each leaf is moved to (easting, northing, ODN height) through pyproj directly, then rays are cast
straight down at the centres of a regular BNG grid with trimesh's Embree intersector; each hit
takes the colour of the node's texture at the hit's barycentric UV, bilinearly.
"""

import io
from dataclasses import dataclass
from pathlib import Path

import mercantile
import numpy as np
import pygltflib
from PIL import Image
from pyproj import Transformer
from scipy.ndimage import map_coordinates
from trimesh import Trimesh
from trimesh.ray.ray_pyembree import RayMeshIntersector
from trimesh.triangles import points_to_barycentric

from satmesh_core import Aoi
from satmesh_eval.offset import LUMA_709
from satmesh_tiles import NodeRecord, node_paths, read_record
from satmesh_tiles.area import leaf_records

ECEF = "EPSG:4978"
BNG_ODN = "EPSG:7405"
RAY_START_ABOVE_M = 10.0
GLTF_VEC3, GLTF_VEC2 = 3, 2


@dataclass(frozen=True)
class LeafMesh:
    """One leaf in BNG metres with its UVs (glTF, origin top-left) and texture."""

    tile: mercantile.Tile
    mesh: Trimesh
    uv: np.ndarray
    texture: np.ndarray


def load_leaf(store_dir: Path, tile: mercantile.Tile, record: NodeRecord) -> LeafMesh:
    """Read a node's GLB and place its vertices in BNG easting, northing and ODN height."""
    gltf = pygltflib.GLTF2().load(str(node_paths(store_dir, tile)[0]))
    blob = gltf.binary_blob()
    primitive = gltf.meshes[0].primitives[0]

    def accessor(index: int, dtype: type, width: int) -> np.ndarray:
        spec = gltf.accessors[index]
        view = gltf.bufferViews[spec.bufferView]
        return np.frombuffer(blob, dtype, spec.count * width, view.byteOffset).reshape(-1, width)

    local = accessor(primitive.attributes.POSITION, np.float32, GLTF_VEC3).astype(np.float64)
    uv = accessor(primitive.attributes.TEXCOORD_0, np.float32, GLTF_VEC2).astype(np.float64)
    index_spec = gltf.accessors[primitive.indices]
    index_dtype = {5123: np.uint16, 5125: np.uint32}[index_spec.componentType]
    faces = accessor(primitive.indices, index_dtype, 1).reshape(-1, 3).astype(np.int64)
    enu = np.column_stack([local[:, 0], -local[:, 2], local[:, 1]])
    ecef = (np.array(record.enu_to_ecef) @ np.column_stack([enu, np.ones(len(enu))]).T).T[:, :3]
    easting, northing, height = Transformer.from_crs(ECEF, BNG_ODN, always_xy=True).transform(
        *ecef.T
    )
    image_view = gltf.bufferViews[gltf.images[0].bufferView]
    data = blob[image_view.byteOffset : image_view.byteOffset + image_view.byteLength]
    texture = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
    mesh = Trimesh(np.column_stack([easting, northing, height]), faces, process=False)
    return LeafMesh(tile, mesh, uv, texture)


def load_store(store_dir: Path) -> list[LeafMesh]:
    """Load every finest-level node of the store."""
    return [
        load_leaf(store_dir, tile, read_record(store_dir, tile)) for tile in leaf_records(store_dir)
    ]


def render_luma(leaves: list[LeafMesh], box: Aoi, grid_m: float) -> np.ndarray:
    """Top-down luma of `leaves` on the BNG grid of `box`; NaN where no leaf covers a cell."""
    cols, rows = round((box.east - box.west) / grid_m), round((box.north - box.south) / grid_m)
    out = np.full((rows, cols), np.nan)
    eastings = box.west + grid_m * (np.arange(cols) + 0.5)
    northings = box.north - grid_m * (np.arange(rows) + 0.5)
    for leaf in leaves:
        (e0, n0, _), (e1, n1, top) = leaf.mesh.bounds
        c_idx = np.nonzero((eastings >= e0) & (eastings <= e1))[0]
        r_idx = np.nonzero((northings >= n0) & (northings <= n1))[0]
        if c_idx.size == 0 or r_idx.size == 0:
            continue
        rr, cc = np.meshgrid(r_idx, c_idx, indexing="ij")
        rr, cc = rr.ravel(), cc.ravel()
        rr, cc = rr[np.isnan(out[rr, cc])], cc[np.isnan(out[rr, cc])]
        origins = np.column_stack(
            [eastings[cc], northings[rr], np.full(len(rr), top + RAY_START_ABOVE_M)]
        )
        hit_points, ray_index, triangle = RayMeshIntersector(leaf.mesh).intersects_location(
            origins, np.tile([0.0, 0.0, -1.0], (len(origins), 1)), multiple_hits=False
        )
        out[rr[ray_index], cc[ray_index]] = _luma_at(leaf, hit_points, triangle)
    return out


def _luma_at(leaf: LeafMesh, points: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    corners = leaf.mesh.vertices[leaf.mesh.faces[triangles]]
    weights = points_to_barycentric(corners, points)
    uv = np.einsum("nk,nkd->nd", weights, leaf.uv[leaf.mesh.faces[triangles]])
    height, width = leaf.texture.shape[:2]
    # texel centres sit at +0.5 px: u = (col + 0.5) / width
    cols, rows = uv[:, 0] * width - 0.5, uv[:, 1] * height - 0.5
    rgb = np.stack(
        [
            map_coordinates(leaf.texture[..., band], [rows, cols], order=1, mode="nearest")
            for band in range(3)
        ],
        axis=1,
    )
    return rgb @ LUMA_709
