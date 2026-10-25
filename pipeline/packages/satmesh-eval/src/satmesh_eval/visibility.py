"""Camera visibility: does a render of the store show what a camera would see in reality?

There is no standard metric for this (`f6-research.md`, Q4); it is assembled from ray casting
(trimesh with Embree) against two meshes of the same ground in BNG metres:

- the reference, the EA first-return DSM triangulated at its full 1 m resolution, standing for
  what is physically there;
- the test mesh, normally the store's finest nodes.

Two checks, both pinhole cameras at random poses:

- `depth_agreement`: for every pixel where the reference ray hits, the test hit range must agree
  within a tolerance; pixels the test hits where the reference misses are reported separately.
- `raised_point_visibility`: points sampled on the surface of raised objects (connected patches at
  least `MIN_OBJECT_AREA_M2` large whose surface stands above the threshold over the ground). A
  point is visible to a mesh when it falls in the image and the first hit of the ray to it lies
  within the tolerance of its range, so an occluded point, or one floating above a mesh that lacks
  the object, is not visible. Recall is the share of reference-visible points that the test mesh
  also shows; points are the unit because a flat-topped object has no single apex to test.

Ranges are metres along the ray. The tolerance tau(r) = TOLERANCE_BASE_M + TOLERANCE_PER_M * r
for range r allows the TIN's error and the lateral slack of a pixel-sized ray footprint.
"""

from dataclasses import dataclass

import numpy as np
from rasterio.transform import Affine
from scipy.ndimage import label
from trimesh import Trimesh
from trimesh.ray.ray_pyembree import RayMeshIntersector

# tolerances and sizes below are tunables (f6-plan)
TOLERANCE_BASE_M = 0.5
TOLERANCE_PER_M = 0.01
MIN_OBJECT_AREA_M2 = 4.0
MAX_SAMPLED_POINTS = 3000
# a camera stands where the surface is within this of the ground: not inside a building or a tree
CAMERA_CLEARANCE_M = 0.5
MAX_CAMERA_DRAWS_PER_CAMERA = 200
OBJECT_HEIGHT_CLASS_EDGES_M = (5.0, 15.0)
OBJECT_HEIGHT_CLASS_NAMES = ("2 to 5 m", "5 to 15 m", "over 15 m")
RAY_HIT_EPSILON_M = 1e-6


@dataclass(frozen=True)
class Camera:
    """A pinhole camera in BNG: position (easting, northing, ODN height) and view direction.

    `heading_deg` runs clockwise from north; `pitch_deg` is positive upward; the horizontal field
    of view is `fov_deg`, with square pixels.
    """

    easting: float
    northing: float
    height: float
    heading_deg: float
    pitch_deg: float
    fov_deg: float
    width_px: int
    height_px: int

    @property
    def position(self) -> np.ndarray:
        """The camera centre as (easting, northing, height)."""
        return np.array([self.easting, self.northing, self.height])

    def basis(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return the unit forward, right and up vectors in (east, north, up)."""
        heading, pitch = np.radians(self.heading_deg), np.radians(self.pitch_deg)
        forward = np.array(
            [np.sin(heading) * np.cos(pitch), np.cos(heading) * np.cos(pitch), np.sin(pitch)]
        )
        right = np.array([np.cos(heading), -np.sin(heading), 0.0])
        return forward, right, np.cross(right, forward)

    def pixel_rays(self) -> np.ndarray:
        """Unit ray directions for every pixel centre, shape (height_px, width_px, 3)."""
        focal_px = (self.width_px / 2) / np.tan(np.radians(self.fov_deg) / 2)
        forward, right, up = self.basis()
        x = (np.arange(self.width_px) + 0.5 - self.width_px / 2) / focal_px
        y = (self.height_px / 2 - (np.arange(self.height_px) + 0.5)) / focal_px
        rays = (
            forward[None, None, :]
            + x[None, :, None] * right[None, None, :]
            + y[:, None, None] * up[None, None, :]
        )
        return rays / np.linalg.norm(rays, axis=2, keepdims=True)

    def project(self, points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return pixel column and row of `points`, and a mask of those that fall in the image."""
        forward, right, up = self.basis()
        relative = points - self.position
        depth = relative @ forward
        focal_px = (self.width_px / 2) / np.tan(np.radians(self.fov_deg) / 2)
        in_front = depth > 0
        safe = np.where(in_front, depth, 1.0)
        col = self.width_px / 2 + focal_px * (relative @ right) / safe
        row = self.height_px / 2 - focal_px * (relative @ up) / safe
        inside = in_front & (col >= 0) & (col < self.width_px) & (row >= 0) & (row < self.height_px)
        return col, row, inside


@dataclass(frozen=True)
class DepthAgreement:
    """Pixel-level agreement of a test mesh with the reference, for one or many cameras."""

    reference_hit_pixels: int
    agreeing_pixels: int
    test_only_pixels: int

    @property
    def recall(self) -> float:
        """Share of reference-hit pixels where the test mesh agrees within tolerance."""
        return self.agreeing_pixels / self.reference_hit_pixels

    def __add__(self, other: "DepthAgreement") -> "DepthAgreement":
        """Pool the pixel counts of two cameras."""
        return DepthAgreement(
            self.reference_hit_pixels + other.reference_hit_pixels,
            self.agreeing_pixels + other.agreeing_pixels,
            self.test_only_pixels + other.test_only_pixels,
        )


@dataclass(frozen=True)
class PointVisibility:
    """Counts over camera-point pairs, in total and by height-above-ground class: (seen, shown)."""

    reference_visible: int
    shown: int
    test_only_visible: int
    by_class: dict[str, tuple[int, int]]

    @property
    def recall(self) -> float:
        """Share of reference-visible pairs the test mesh also shows."""
        return self.shown / self.reference_visible


@dataclass(frozen=True)
class RaisedPoints:
    """Sampled surface points of raised objects: BNG positions and heights above the ground."""

    points: np.ndarray
    height_above_ground_m: np.ndarray


def tolerance(range_m: np.ndarray) -> np.ndarray:
    """Range tolerance tau(r) in metres."""
    return TOLERANCE_BASE_M + TOLERANCE_PER_M * range_m


def raster_mesh(heights: np.ndarray, transform: Affine) -> Trimesh:
    """Triangulate a north-up height raster at its pixel centres: two triangles per cell."""
    rows, cols = heights.shape
    easting = transform.c + transform.a * (np.arange(cols) + 0.5)
    northing = transform.f + transform.e * (np.arange(rows) + 0.5)
    e, n = np.meshgrid(easting, northing)
    vertices = np.column_stack([e.ravel(), n.ravel(), heights.ravel()])
    index = np.arange(rows * cols).reshape(rows, cols)
    a, b = index[:-1, :-1].ravel(), index[:-1, 1:].ravel()
    c, d = index[1:, :-1].ravel(), index[1:, 1:].ravel()
    faces = np.concatenate([np.column_stack([a, c, b]), np.column_stack([b, c, d])])
    return Trimesh(vertices, faces, process=False)


def first_hit_range(mesh: Trimesh, origins: np.ndarray, directions: np.ndarray) -> np.ndarray:
    """Range to the first surface along each ray, NaN where a ray misses."""
    ranges = np.full(len(origins), np.nan)
    points, ray_index, _ = RayMeshIntersector(mesh).intersects_location(
        origins, directions, multiple_hits=False
    )
    ranges[ray_index] = np.linalg.norm(points - origins[ray_index], axis=1)
    return ranges


def range_image(mesh: Trimesh, camera: Camera, max_range_m: float) -> np.ndarray:
    """Range image of `mesh` from `camera`; NaN for sky and for hits past `max_range_m`."""
    rays = camera.pixel_rays().reshape(-1, 3)
    origins = np.tile(camera.position, (len(rays), 1))
    ranges = first_hit_range(mesh, origins, rays)
    ranges[ranges > max_range_m] = np.nan
    return ranges.reshape(camera.height_px, camera.width_px)


def depth_agreement(reference: np.ndarray, test: np.ndarray) -> DepthAgreement:
    """Compare two range images of one camera pixel by pixel."""
    reference_hit = np.isfinite(reference)
    test_hit = np.isfinite(test)
    agree = reference_hit & test_hit
    agree[agree] = np.abs(test[agree] - reference[agree]) <= tolerance(reference[agree])
    return DepthAgreement(
        int(reference_hit.sum()), int(agree.sum()), int((test_hit & ~reference_hit).sum())
    )


def sample_raised_points(
    surface: np.ndarray,
    ground: np.ndarray,
    transform: Affine,
    threshold_m: float,
    seed: int = 0,
) -> RaisedPoints:
    """Sample surface points of patches more than `threshold_m` above ground and large enough."""
    above = surface - ground
    labels, count = label(above > threshold_m)
    if count == 0:
        return RaisedPoints(np.empty((0, 3)), np.empty(0))
    areas = np.bincount(labels.ravel(), minlength=count + 1) * abs(transform.a * transform.e)
    rows, cols = np.nonzero((labels > 0) & (areas[labels] >= MIN_OBJECT_AREA_M2))
    if len(rows) > MAX_SAMPLED_POINTS:
        keep = np.random.default_rng(seed).choice(len(rows), MAX_SAMPLED_POINTS, replace=False)
        rows, cols = rows[keep], cols[keep]
    easting = transform.c + transform.a * (cols + 0.5)
    northing = transform.f + transform.e * (rows + 0.5)
    return RaisedPoints(
        np.column_stack([easting, northing, surface[rows, cols]]), above[rows, cols]
    )


def raised_point_visibility(
    reference: Trimesh,
    test: Trimesh,
    cameras: list[Camera],
    raised: RaisedPoints,
    max_range_m: float,
) -> PointVisibility:
    """Count camera-point pairs the reference shows and the test mesh also shows."""
    classes = np.digitize(raised.height_above_ground_m, OBJECT_HEIGHT_CLASS_EDGES_M)
    visible = shown = test_only = 0
    per_class = np.zeros((len(OBJECT_HEIGHT_CLASS_NAMES), 2), dtype=int)
    for camera in cameras:
        _, _, in_image = camera.project(raised.points)
        to_point = raised.points - camera.position
        target_range = np.linalg.norm(to_point, axis=1)
        considered = in_image & (target_range <= max_range_m)
        if not considered.any():
            continue
        directions = to_point[considered] / target_range[considered, None]
        origins = np.tile(camera.position, (int(considered.sum()), 1))
        wanted = target_range[considered]
        sees_reference = _shows(reference, origins, directions, wanted)
        sees_test = _shows(test, origins, directions, wanted)
        visible += int(sees_reference.sum())
        shown += int((sees_reference & sees_test).sum())
        test_only += int((~sees_reference & sees_test).sum())
        for cls in range(len(OBJECT_HEIGHT_CLASS_NAMES)):
            in_class = classes[considered] == cls
            per_class[cls, 0] += int((sees_reference & in_class).sum())
            per_class[cls, 1] += int((sees_reference & sees_test & in_class).sum())
    return PointVisibility(
        visible,
        shown,
        test_only,
        {
            name: (int(per_class[i, 0]), int(per_class[i, 1]))
            for i, name in enumerate(OBJECT_HEIGHT_CLASS_NAMES)
        },
    )


def random_cameras(  # noqa: PLR0913 (sampling box, rig and seed, each a setting)
    surface: np.ndarray,
    ground: np.ndarray,
    transform: Affine,
    count: int,
    *,
    above_ground_m: float,
    pitch_deg: float,
    margin_m: float,
    fov_deg: float = 90.0,
    size_px: tuple[int, int] = (320, 240),
    seed: int = 0,
) -> list[Camera]:
    """Cameras at random open-ground positions `margin_m` inside the raster.

    A position is open when the surface there is within `CAMERA_CLEARANCE_M` of the ground, so no
    camera starts inside a building or tree. Each camera hangs `above_ground_m` over the ground.
    """
    rng = np.random.default_rng(seed)
    rows, cols = ground.shape
    margin_px = int(np.ceil(margin_m / abs(transform.a)))
    if 2 * margin_px >= min(rows, cols):
        msg = f"a {margin_m} m margin leaves no room in a {rows} x {cols} px raster"
        raise ValueError(msg)
    cameras = []
    draws = 0
    while len(cameras) < count:
        draws += 1
        if draws > count * MAX_CAMERA_DRAWS_PER_CAMERA:
            msg = f"only {len(cameras)} open-ground camera positions found for {count} cameras"
            raise ValueError(msg)
        row = int(rng.integers(margin_px, rows - margin_px))
        col = int(rng.integers(margin_px, cols - margin_px))
        if surface[row, col] - ground[row, col] > CAMERA_CLEARANCE_M:
            continue
        cameras.append(
            Camera(
                easting=transform.c + transform.a * (col + 0.5),
                northing=transform.f + transform.e * (row + 0.5),
                height=float(ground[row, col]) + above_ground_m,
                heading_deg=float(rng.uniform(0, 360)),
                pitch_deg=pitch_deg,
                fov_deg=fov_deg,
                width_px=size_px[0],
                height_px=size_px[1],
            )
        )
    return cameras


def _shows(
    mesh: Trimesh, origins: np.ndarray, directions: np.ndarray, wanted_range: np.ndarray
) -> np.ndarray:
    hit = first_hit_range(mesh, origins, directions)
    return np.isfinite(hit) & (np.abs(hit - wanted_range) <= tolerance(wanted_range))
