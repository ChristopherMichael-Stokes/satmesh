"""Raw lidar first returns as an independent height reference.

The EA 1 m DSM is a rasterisation of the point cloud, so it cannot judge a surface built from it.
Points held out of a surface's construction can: the height error of a mesh at a held-out point is
the mesh height there minus the point's height, between the raster's pixel centres.
"""

from dataclasses import dataclass
from pathlib import Path

import laspy
import numpy as np
from trimesh import Trimesh
from trimesh.ray.ray_pyembree import RayMeshIntersector

from satmesh_core import Aoi

# ASPRS LAS classification codes
CLASS_GROUND = 2
CLASS_VEGETATION = (3, 4, 5)
CLASS_BUILDING = 6
CLASS_NOISE = 7
FIRST_RETURN = 1
READ_CHUNK_POINTS = 5_000_000
RAY_START_ABOVE_M = 10.0
DOWN = np.array([0.0, 0.0, -1.0])


@dataclass(frozen=True)
class FirstReturns:
    """First-return points in the file's projected coordinates, with their LAS classes."""

    xyz: np.ndarray
    classification: np.ndarray


def read_first_returns(path: Path, box: Aoi) -> FirstReturns:
    """Read the first returns inside `box` (same CRS as the file), dropping noise-class points."""
    xyz_parts, class_parts = [], []
    with laspy.open(path) as reader:
        for chunk in reader.chunk_iterator(READ_CHUNK_POINTS):
            keep = (
                (chunk.return_number == FIRST_RETURN)
                & (chunk.classification != CLASS_NOISE)
                & (chunk.x >= box.west)
                & (chunk.x < box.east)
                & (chunk.y >= box.south)
                & (chunk.y < box.north)
            )
            xyz_parts.append(np.column_stack([chunk.x[keep], chunk.y[keep], chunk.z[keep]]))
            class_parts.append(np.asarray(chunk.classification[keep]))
    return FirstReturns(np.concatenate(xyz_parts), np.concatenate(class_parts))


def split_holdout(
    points: FirstReturns, fraction: float, seed: int
) -> tuple[FirstReturns, FirstReturns]:
    """Return (kept, held out), the held-out part a random `fraction` of the points."""
    held = np.random.default_rng(seed).random(len(points.xyz)) < fraction
    return (
        FirstReturns(points.xyz[~held], points.classification[~held]),
        FirstReturns(points.xyz[held], points.classification[held]),
    )


def height_error_at_points(mesh: Trimesh, xyz: np.ndarray) -> np.ndarray:
    """Return mesh height minus point height at each point's position, NaN where no surface."""
    top = max(float(mesh.bounds[1, 2]), float(xyz[:, 2].max())) + RAY_START_ABOVE_M
    origins = np.column_stack([xyz[:, :2], np.full(len(xyz), top)])
    points, ray_index, _ = RayMeshIntersector(mesh).intersects_location(
        origins, np.tile(DOWN, (len(xyz), 1)), multiple_hits=False
    )
    error = np.full(len(xyz), np.nan)
    error[ray_index] = points[:, 2] - xyz[ray_index, 2]
    return error
