"""Height error of a mesh against a reference raster, by vertical ray casting.

Rays go straight down at every pixel centre of the reference; the error is the mesh height at that
position minus the raster value. Unlike the pipeline check, which compares the mesh's own vertices
with the raster, this measures the surface between vertices at the raster's own sample points, so
it includes what the store's resampling and triangulation lose.
"""

import numpy as np
from rasterio.transform import Affine
from trimesh import Trimesh
from trimesh.ray.ray_pyembree import RayMeshIntersector

RAY_START_ABOVE_M = 10.0
DOWN = np.array([0.0, 0.0, -1.0])


def surface_height_error(
    mesh: Trimesh, reference: np.ndarray, transform: Affine, margin_px: int = 0
) -> np.ndarray:
    """Return mesh height minus `reference` at each pixel centre, NaN where the mesh has no surface.

    The outer `margin_px` pixels are left NaN, where a leaf may stop short of the raster's edge.
    """
    rows, cols = reference.shape
    r, c = np.meshgrid(
        np.arange(margin_px, rows - margin_px),
        np.arange(margin_px, cols - margin_px),
        indexing="ij",
    )
    r, c = r.ravel(), c.ravel()
    top = max(float(mesh.bounds[1, 2]), float(np.nanmax(reference))) + RAY_START_ABOVE_M
    origins = np.column_stack(
        [
            transform.c + transform.a * (c + 0.5),
            transform.f + transform.e * (r + 0.5),
            np.full(len(r), top),
        ]
    )
    points, ray_index, _ = RayMeshIntersector(mesh).intersects_location(
        origins, np.tile(DOWN, (len(r), 1)), multiple_hits=False
    )
    error = np.full(reference.shape, np.nan)
    error[r[ray_index], c[ray_index]] = points[:, 2] - reference[r[ray_index], c[ray_index]]
    return error
