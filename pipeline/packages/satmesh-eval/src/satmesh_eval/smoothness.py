"""Facet-level smoothness of a mesh against a reference height raster.

Height errors sampled at the reference's own pixel centres cannot see terracing: a mesh made by
nearest-pixel sampling hits every centre exactly yet is flat on each pixel and steps between them.
These scores look at the mesh's facets, whose centroids fall between pixel centres.

Facet normal error follows demcompare's angular difference, cos(theta) = n_mesh . n_ref, with the
mesh normal from the facet and the reference normal from Horn's gradient of the raster (Horn 1981,
"Hill shading and the reflectance map") sampled bilinearly at the centroid. Grid-direction aspect
excess follows demcompare's slope-orientation histogram, whose peaks at multiples of 45 degrees
mark artefacts of the sampling grid. Flat facets on sloped ground are the terrace signature
(Hengl et al. 2003, padi terraces).
"""

from dataclasses import dataclass

import numpy as np
from rasterio.transform import Affine
from scipy import ndimage
from trimesh import Trimesh

# Horn's 3x3 kernel: Sobel response divided by 8 pixel sizes gives the gradient
HORN_DIVISOR = 8.0
# an open-ground facet this steep is a skirt wall, not terrain (tunable)
SKIRT_SLOPE_DEG = 80.0
# surface less than this above the ground counts as open ground (tunable)
OPEN_GROUND_HEIGHT_M = 0.5
# surface this far above the ground counts as a raised object (tunable)
RAISED_HEIGHT_M = 2.0
# a facet flatter than this is flat; a reference steeper than FLAT_ON_SLOPE_DEG makes it a terrace
FLAT_FACET_DEG = 0.5
FLAT_ON_SLOPE_DEG = 5.0
# aspect within this of a multiple of 45 degrees is grid-aligned (tunable)
GRID_ASPECT_TOLERANCE_DEG = 2.0
GRID_ASPECT_STEP_DEG = 45.0
UPPER_QUANTILE = 0.9


@dataclass(frozen=True)
class SmoothnessScore:
    """Smoothness of one mesh against one reference.

    Normal errors are in degrees, area weighted. The flat fraction and aspect excess are area
    fractions on open ground; excess is the mesh's grid-aligned share minus the reference's.
    """

    open_normal_median_deg: float
    open_normal_p90_deg: float
    raised_normal_median_deg: float
    raised_normal_p90_deg: float
    flat_on_slope_fraction: float
    grid_aspect_excess: float


def horn_gradient(heights: np.ndarray, transform: Affine) -> tuple[np.ndarray, np.ndarray]:
    """Return (east, north) height gradients, metres per metre, from Horn's 3x3 kernel."""
    east = ndimage.sobel(heights, axis=1, mode="nearest") / (HORN_DIVISOR * transform.a)
    north = ndimage.sobel(heights, axis=0, mode="nearest") / (HORN_DIVISOR * transform.e)
    return east, north


def _sample(raster: np.ndarray, transform: Affine, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    cols = (x - transform.c) / transform.a - 0.5
    rows = (y - transform.f) / transform.e - 0.5
    return ndimage.map_coordinates(raster, [rows, cols], order=1, mode="nearest")


def _slope_deg(east: np.ndarray, north: np.ndarray) -> np.ndarray:
    return np.degrees(np.arctan(np.hypot(east, north)))


def _aspect_deg(east: np.ndarray, north: np.ndarray) -> np.ndarray:
    """Compass direction the surface faces, degrees clockwise from north."""
    return np.degrees(np.arctan2(-east, -north)) % 360.0


def _grid_aligned(aspect_deg: np.ndarray) -> np.ndarray:
    offset = np.abs(
        (aspect_deg + GRID_ASPECT_STEP_DEG / 2) % GRID_ASPECT_STEP_DEG - GRID_ASPECT_STEP_DEG / 2
    )
    return offset <= GRID_ASPECT_TOLERANCE_DEG


def weighted_quantile(values: np.ndarray, weights: np.ndarray, quantile: float) -> float:
    """Return the smallest value whose cumulative weight reaches `quantile` of the total."""
    if values.size == 0:
        return float("nan")
    order = np.argsort(values)
    cumulative = np.cumsum(weights[order])
    return float(values[order][np.searchsorted(cumulative, quantile * cumulative[-1])])


def smoothness_score(
    mesh: Trimesh, surface: np.ndarray, ground: np.ndarray, transform: Affine
) -> SmoothnessScore:
    """Score `mesh` against the first-return `surface` raster, using `ground` for strata.

    The mesh must be in the raster's projected coordinates with heights in the raster's datum.
    """
    east, north = horn_gradient(surface, transform)
    centroids = mesh.triangles_center
    x, y = centroids[:, 0], centroids[:, 1]
    ref_east, ref_north = (_sample(g, transform, x, y) for g in (east, north))
    ref_normal = np.column_stack([-ref_east, -ref_north, np.ones_like(ref_east)])
    ref_normal /= np.linalg.norm(ref_normal, axis=1, keepdims=True)
    angle = np.degrees(np.arccos(np.clip(np.sum(mesh.face_normals * ref_normal, axis=1), -1, 1)))

    height_above_ground = _sample(surface - ground, transform, x, y)
    normal = mesh.face_normals
    mesh_slope = np.degrees(np.arccos(np.clip(normal[:, 2], -1, 1)))
    terrain = mesh_slope < SKIRT_SLOPE_DEG
    open_ground = terrain & (height_above_ground < OPEN_GROUND_HEIGHT_M)
    raised = terrain & (height_above_ground > RAISED_HEIGHT_M)
    area = mesh.area_faces

    def angle_quantiles(mask: np.ndarray) -> tuple[float, float]:
        median = weighted_quantile(angle[mask], area[mask], 0.5)
        return median, weighted_quantile(angle[mask], area[mask], UPPER_QUANTILE)

    ref_slope = _slope_deg(ref_east, ref_north)
    flat_on_slope = open_ground & (ref_slope > FLAT_ON_SLOPE_DEG)
    flat_fraction = (
        area[flat_on_slope & (mesh_slope < FLAT_FACET_DEG)].sum() / area[flat_on_slope].sum()
    )

    mesh_aspect = _aspect_deg(-normal[:, 0] / normal[:, 2], -normal[:, 1] / normal[:, 2])
    sloped = open_ground & (mesh_slope >= FLAT_FACET_DEG)
    mesh_share = area[sloped & _grid_aligned(mesh_aspect)].sum() / area[sloped].sum()

    pixel_slope = _slope_deg(east, north)
    pixel_open = ((surface - ground) < OPEN_GROUND_HEIGHT_M) & (pixel_slope >= FLAT_FACET_DEG)
    pixel_open[[0, -1], :] = False  # Horn's kernel is incomplete on the border
    pixel_open[:, [0, -1]] = False
    reference_share = _grid_aligned(_aspect_deg(east, north))[pixel_open].mean()

    open_median, open_p90 = angle_quantiles(open_ground)
    raised_median, raised_p90 = angle_quantiles(raised)
    return SmoothnessScore(
        open_normal_median_deg=open_median,
        open_normal_p90_deg=open_p90,
        raised_normal_median_deg=raised_median,
        raised_normal_p90_deg=raised_p90,
        flat_on_slope_fraction=float(flat_fraction),
        grid_aspect_excess=float(mesh_share - reference_share),
    )
