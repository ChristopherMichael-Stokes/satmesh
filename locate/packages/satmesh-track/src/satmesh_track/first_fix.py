"""The first photo's pose with no prior: rank a grid of renders by global descriptor, then verify.

A grid of poses covers the scene: positions every `spacing_m`, several heights above the ground,
headings every 90 degrees and two pitches. Each is rendered and described once (the descriptors
are cached on disk, because describing thousands of renders takes tens of minutes on CPU). The
first photo is described, the grid ranked by cosine similarity and the best `verify_top_k` are
localised with the normal solve; the pose with the most inliers wins (photo-only P1: 16 of 18
queries within 1 m on a 100 m grid, 17 of 18 on 50 m, one wrong fix in the latter).

The height ladder 25, 50, 100 m follows from the scale gap: a render up to 2 times higher than the
photo still matches, 4 times does not.
"""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from itertools import batched
from pathlib import Path

import numpy as np
import numpy.typing as npt

from satmesh_core import EnuFrame
from satmesh_eval.camera import CameraPose, pose_from_camera_to_enu, pose_from_enu
from satmesh_eval.perspective import GroundExtent
from satmesh_locate.megaloc import MegaLocDescriber
from satmesh_track.search import GroundHeight, best_candidates, candidate_poses
from satmesh_track.tracker import (
    FIRST_SEARCH_HEIGHTS_M,
    UNKNOWN_PITCH_DEG,
    PhotoImage,
    Scene,
    TrackingContext,
    TrackingError,
    best_attempt,
    nominal_focal,
    pinhole,
    solved,
)

FloatArray = npt.NDArray[np.float64]
DESCRIPTOR_CACHE_SUFFIX = ".npz"
CACHE_KEY_LENGTH = 16
RENDERS_PER_CHUNK = 32  # renders held in memory while they are described


@dataclass(frozen=True)
class GridConfig:
    """Spacing and extent of the first-fix grid; the spacing follows from the P0 basin (70 m)."""

    spacing_m: float = 70.0
    heights_above_ground_m: tuple[float, ...] = (25.0, 50.0, 100.0)
    pitches_deg: tuple[float, ...] = (-25.0, -45.0)
    heading_count: int = 4
    verify_top_k: int = 20


@dataclass(frozen=True)
class GridPose:
    """A grid camera: area-ENU position over the ground, and its attitude."""

    east_m: float
    north_m: float
    ground_m: float
    height_above_ground_m: float
    heading_deg: float
    pitch_deg: float

    def camera_pose(self, area: EnuFrame) -> CameraPose:
        """The pose in the area frame."""
        centre = np.array([self.east_m, self.north_m, self.ground_m + self.height_above_ground_m])
        return pose_from_enu(area, centre, self.heading_deg, self.pitch_deg, 0.0)


def grid_poses(
    config: GridConfig, bounds: GroundExtent, ground_height: GroundHeight
) -> list[GridPose]:
    """Every grid pose over `bounds`; positions outside the scene are left out."""
    east_values = np.arange(bounds.west_m, bounds.east_m + 1e-6, config.spacing_m)
    north_values = np.arange(bounds.south_m, bounds.north_m + 1e-6, config.spacing_m)
    headings = np.arange(config.heading_count) * 360.0 / config.heading_count
    poses = []
    for east in east_values:
        for north in north_values:
            try:
                ground = ground_height(float(east), float(north))
            except ValueError:
                continue
            for height in config.heights_above_ground_m:
                for pitch in config.pitches_deg:
                    poses.extend(
                        GridPose(float(east), float(north), ground, height, float(h), pitch)
                        for h in headings
                    )
    return poses


def descriptor_cache_path(
    directory: Path, scene_key: str, config: GridConfig, image_size: tuple[int, int], model: Path
) -> Path:
    """File name from everything the descriptors depend on, so a changed input never hits."""
    identity = json.dumps(
        [scene_key, asdict(config), image_size, model.name, model.stat().st_size], sort_keys=True
    )
    digest = hashlib.sha256(identity.encode()).hexdigest()[:CACHE_KEY_LENGTH]
    return directory / f"first-fix-{digest}{DESCRIPTOR_CACHE_SUFFIX}"


def grid_descriptors(  # noqa: PLR0913, PLR0917 (grid, scene, describer, image size, focal, cache path)
    grid: Sequence[GridPose],
    scene: Scene,
    describer: MegaLocDescriber,
    image_size: tuple[int, int],
    focal_px: float,
    cache_path: Path,
    max_range_m: float,
) -> npt.NDArray[np.float32]:
    """Descriptors of the renders at every grid pose, from the cache or built and cached."""
    if cache_path.exists():
        cached = np.load(cache_path)["descriptors"]
        if len(cached) == len(grid):
            return np.asarray(cached, dtype=np.float32)
    width, height = image_size
    intrinsics = pinhole(width, height, focal_px)
    images = (
        scene.render(intrinsics, pose.camera_pose(scene.area), max_range_m).rgb for pose in grid
    )
    descriptors = np.concatenate(
        [
            describer.describe(list(chunk))
            for chunk in batched(images, RENDERS_PER_CHUNK, strict=False)
        ]
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(cache_path, descriptors=descriptors.astype(np.float16))
    return descriptors


def find_start(  # noqa: PLR0913, PLR0917 (photo, grid, descriptors, describer, context)
    photo: PhotoImage,
    grid: Sequence[GridPose],
    descriptors: npt.NDArray[np.float32],
    describer: MegaLocDescriber,
    context: TrackingContext,
    verify_top_k: int,
) -> CameraPose:
    """The refined pose of the best verified candidate; raises `TrackingError` if none localises."""
    similarity = descriptors @ describer.describe([photo.rgb])[0]
    ranked = np.argsort(similarity)[::-1][:verify_top_k]
    priors = [grid[i].camera_pose(context.scene.area) for i in ranked]
    return _refined(photo, priors, context, f"the {verify_top_k} best-ranked renders")


def start_near(
    photo: PhotoImage,
    centre_east_north: FloatArray,
    radius_m: float,
    context: TrackingContext,
) -> CameraPose:
    """The first photo's pose when its position is known roughly: a local search at the ladder."""
    search = context.config.search
    candidates = candidate_poses(
        search,
        context.scene.area,
        context.scene.ground_height,
        centre_east_north,
        radius_m,
        FIRST_SEARCH_HEIGHTS_M,
        [UNKNOWN_PITCH_DEG],
        list(np.arange(search.heading_count) * 360.0 / search.heading_count),
        search.spacing_m,
    )
    height, width = photo.rgb.shape[:2]
    best = best_candidates(
        search,
        photo.rgb,
        candidates,
        context.scene.render,
        context.matcher,
        pinhole(width, height, nominal_focal(width)),
        context.config.max_range_m,
    )
    return _refined(photo, best, context, f"the {len(candidates)} renders within {radius_m:.0f} m")


def _refined(
    photo: PhotoImage, priors: Sequence[CameraPose], context: TrackingContext, searched: str
) -> CameraPose:
    attempt = best_attempt(photo, priors, nominal_focal(photo.rgb.shape[1]), context)
    if not solved(attempt, context.config) or attempt.estimate is None:
        msg = f"none of {searched} localised {photo.name}"
        raise TrackingError(msg)
    estimate = attempt.estimate
    return pose_from_camera_to_enu(context.scene.area, estimate.centre_enu, estimate.camera_to_enu)
