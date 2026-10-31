"""Perspective textured RGB and depth render of a tile store's finest leaves from a camera pose.

All leaves sit in one area ENU frame (x east, y north, z up, metres): the tangent plane at the mean
of the leaves' ECEF origins, the same frame `satmesh_tiles.area.export_area_glb` writes. Rays are
cast with trimesh's Embree intersector; the first hit over all leaves in range wins, and its colour
is the leaf texture sampled bilinearly at the barycentric UV. Depth is metres along the ray.
"""

from dataclasses import dataclass
from pathlib import Path

import mercantile
import numpy as np
import trimesh
from trimesh import Trimesh
from trimesh.ray.ray_pyembree import RayMeshIntersector

from satmesh_core import EnuFrame
from satmesh_eval.camera import CameraPose, Intrinsics, camera_centre_and_rotation, pixel_rays
from satmesh_eval.render import interpolated_uv, texture_rgb_at
from satmesh_tiles import node_paths
from satmesh_tiles.area import ENU_TO_GLTF, area_frame, leaf_records

ROWS_PER_CHUNK = 64  # 64 rows of a 1920 px image: 123k rays, a few tens of MB of intermediates
NO_HIT = -1
BYTE_MAX = 255.0


@dataclass(frozen=True)
class SceneLeaf:
    """One leaf in area ENU metres, with per-vertex UVs (glTF: origin top-left) and its texture."""

    mesh: Trimesh
    uv: np.ndarray
    texture: np.ndarray


@dataclass(frozen=True)
class AreaScene:
    """Textured leaves in a single area ENU frame."""

    leaves: tuple[SceneLeaf, ...]
    frame: EnuFrame

    def leaves_in_view(self, centre_enu: np.ndarray, max_range_m: float) -> tuple[int, ...]:
        """Indices of leaves whose bounding box meets the `max_range_m` cube around the camera."""
        low, high = centre_enu - max_range_m, centre_enu + max_range_m
        return tuple(
            index
            for index, leaf in enumerate(self.leaves)
            if np.all(leaf.mesh.bounds[1] >= low) and np.all(leaf.mesh.bounds[0] <= high)
        )


@dataclass(frozen=True)
class GroundExtent:
    """Rectangle in area ENU metres."""

    west_m: float
    east_m: float
    south_m: float
    north_m: float


@dataclass(frozen=True)
class RenderResult:
    """Images of one render. Misses are black in `rgb` and NaN in the depths.

    `depth_m` is the distance along the ray (range); `z_depth_m` is the distance along the optical
    axis, the depth to use when lifting a pixel with `K^-1 (u, v, 1)`.
    """

    rgb: np.ndarray
    depth_m: np.ndarray
    z_depth_m: np.ndarray
    hit_mask: np.ndarray


def load_area_scene(store_dir: Path) -> AreaScene:
    """Load the finest-level leaves of a store into their shared area ENU frame."""
    records = leaf_records(store_dir)
    frame = area_frame(records)
    to_area_enu = np.linalg.inv(frame.enu_to_ecef_matrix())
    leaves = []
    for tile, record in records.items():
        gltf_to_area = to_area_enu @ np.array(record.enu_to_ecef) @ np.linalg.inv(ENU_TO_GLTF)
        geometry = next(iter(trimesh.load_scene(node_paths(store_dir, tile)[0]).geometry.values()))
        vertices = trimesh.transformations.transform_points(geometry.vertices, gltf_to_area)
        uv = np.array(geometry.visual.uv, dtype=np.float64)
        uv[:, 1] = 1.0 - uv[:, 1]  # trimesh flips v on load; back to the glTF top-left origin
        texture = np.asarray(geometry.visual.material.baseColorTexture.convert("RGB"))
        leaves.append(SceneLeaf(Trimesh(vertices, geometry.faces, process=False), uv, texture))
    return AreaScene(tuple(leaves), frame)


def load_leaf_texture(store_dir: Path, tile: mercantile.Tile) -> np.ndarray:
    """RGB texture of one leaf's GLB."""
    geometry = next(iter(trimesh.load_scene(node_paths(store_dir, tile)[0]).geometry.values()))
    return np.asarray(geometry.visual.material.baseColorTexture.convert("RGB"))


def flat_plane_scene(
    frame: EnuFrame, height_m: float, texture: np.ndarray, extent: GroundExtent
) -> AreaScene:
    """A horizontal plane at area-ENU `height_m` covering `extent`, draped with `texture`.

    The texture's outer edges fall on the extent's edges, its top row at the north edge.
    """
    vertices = np.array(
        [
            [extent.west_m, extent.south_m, height_m],
            [extent.east_m, extent.south_m, height_m],
            [extent.east_m, extent.north_m, height_m],
            [extent.west_m, extent.north_m, height_m],
        ]
    )
    faces = np.array([[0, 1, 2], [0, 2, 3]])
    uv = np.array([[0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]])
    return AreaScene((SceneLeaf(Trimesh(vertices, faces, process=False), uv, texture),), frame)


def render(
    scene: AreaScene, intrinsics: Intrinsics, pose: CameraPose, max_range_m: float
) -> RenderResult:
    """Render `scene` from `pose`; hits farther than `max_range_m` along the ray count as misses."""
    centre, camera_to_enu = camera_centre_and_rotation(pose, scene.frame)
    in_view = scene.leaves_in_view(centre, max_range_m)
    intersectors = {index: RayMeshIntersector(scene.leaves[index].mesh) for index in in_view}
    shape = (intrinsics.height_px, intrinsics.width_px)
    result = RenderResult(
        rgb=np.zeros((*shape, 3), np.uint8),
        depth_m=np.full(shape, np.nan, np.float32),
        z_depth_m=np.full(shape, np.nan, np.float32),
        hit_mask=np.zeros(shape, bool),
    )
    for start in range(0, intrinsics.height_px, ROWS_PER_CHUNK):
        rows = range(start, min(start + ROWS_PER_CHUNK, intrinsics.height_px))
        directions = pixel_rays(intrinsics, camera_to_enu, rows).reshape(-1, 3)
        chunk = _render_rows(scene, intersectors, centre, directions, max_range_m)
        chunk.store(result, rows, centre, camera_to_enu[:, 2])
    return result


@dataclass(frozen=True)
class _Chunk:
    rgb: np.ndarray
    ranges: np.ndarray
    points: np.ndarray
    triangle: np.ndarray
    leaf: np.ndarray

    def store(
        self, result: RenderResult, rows: range, centre: np.ndarray, forward: np.ndarray
    ) -> None:
        shape = (len(rows), result.rgb.shape[1])
        hit = self.leaf != NO_HIT
        z_depths = np.where(hit, (self.points - centre) @ forward, np.nan)
        window = slice(rows.start, rows.stop)
        result.rgb[window] = self.rgb.reshape(*shape, 3)
        result.depth_m[window] = self.ranges.reshape(shape)
        result.z_depth_m[window] = z_depths.reshape(shape)
        result.hit_mask[window] = self.leaf.reshape(shape) != NO_HIT


def _render_rows(
    scene: AreaScene,
    intersectors: dict[int, RayMeshIntersector],
    centre: np.ndarray,
    directions: np.ndarray,
    max_range_m: float,
) -> _Chunk:
    count = len(directions)
    origins = np.tile(centre, (count, 1))
    nearest = np.full(count, np.inf)
    leaf = np.full(count, NO_HIT, np.int32)
    triangle = np.full(count, NO_HIT, np.int32)
    points = np.zeros((count, 3))
    for index, intersector in intersectors.items():
        hit_points, ray, hit_triangle = intersector.intersects_location(
            origins, directions, multiple_hits=False
        )
        ranges = np.linalg.norm(hit_points - centre, axis=1)
        closer = (ranges <= max_range_m) & (ranges < nearest[ray])
        ray, hit_points = ray[closer], hit_points[closer]
        nearest[ray] = ranges[closer]
        leaf[ray], triangle[ray], points[ray] = index, hit_triangle[closer], hit_points
    hit = leaf != NO_HIT
    rgb = np.zeros((count, 3), np.uint8)
    for index in np.unique(leaf[hit]):
        rgb[leaf == index] = _colours(
            scene.leaves[index], points[leaf == index], triangle[leaf == index]
        )
    return _Chunk(
        rgb,
        np.where(hit, nearest, np.nan),
        points,
        triangle,
        leaf,
    )


def _colours(leaf: SceneLeaf, points: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    uv = interpolated_uv(leaf.mesh, leaf.uv, points, triangles)
    return np.clip(np.rint(texture_rgb_at(leaf.texture, uv)), 0, BYTE_MAX).astype(np.uint8)
