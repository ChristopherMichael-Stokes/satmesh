"""Follow ordered photos through a mesh: predict, render, match, solve, and fit the lens.

The first photo starts from a given pose (from a search, or a position the user knows). Its focal
length is scanned (nominal times 0.7 to 1.5, lowest reprojection error, photo-only P0b), then each
photo is rendered at the pose predicted by constant velocity, matched, lifted through the render's
depth and solved with perspective-n-point at the current focal length (no distortion yet). A photo
with fewer than `min_inliers` inliers starts a local search around the last fix. When all photos
are followed the lens graph (`lens.py`) fits focal length, k1 and k2 and the poses together and
rejects wrong frames. Distortion is unknown while tracking: a strong barrel lens leaves the
tracker poses a metre or two off, which the graph removes.
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise

import cv2
import numpy as np
import numpy.typing as npt
from scipy.spatial.transform import Rotation

from satmesh_core import EnuFrame
from satmesh_eval.camera import (
    CameraPose,
    Intrinsics,
    camera_centre_and_rotation,
    pose_from_camera_to_enu,
)
from satmesh_eval.localise import (
    MINIMUM_INLIERS,
    Correspondences,
    PoseEstimate,
    lift_matches,
    solve_pose,
)
from satmesh_eval.matching import Matcher
from satmesh_eval.references import PhotoQuery, Renderer, perspective_views
from satmesh_track.lens import (
    CameraPoseEnu,
    FrameObservations,
    Lens,
    LensConfig,
    LensEstimate,
    fit_lens,
)
from satmesh_track.search import (
    GroundHeight,
    SearchConfig,
    best_candidates,
    candidate_poses,
    max_recovered_displacement_m,
    search_radius_m,
)

NOMINAL_HFOV_DEG = (
    70.0  # a typical camera; the focal scan covers 0.7 to 1.5 times this focal length
)
FOCAL_SCAN_RELATIVE = np.arange(0.70, 1.5001, 0.01)
FIRST_PHOTO_FOCAL_TRIES = (
    0.8,
    0.9,
    1.0,
    1.1,
    1.2,
)  # times the nominal focal; a pose solved at a wrong focal is biased
MAX_RANGE_M = 1000.0  # render hits farther than this count as misses (black sky and far field)
FIRST_SEARCH_HEIGHTS_M = (25.0, 50.0, 100.0)  # height ladder: a render up to 2 times higher matches
MIN_FIXES_FOR_VELOCITY = 2
HELD_FIXES_AS_PRIORS = 3  # earlier fixes tried as priors: a weak last fix misleads the next photo
PRIOR_PULL_MAX_M = 30.0  # match basin measured on the Bexhill clip
REFINE_BELOW_INLIERS = 150  # a fix with fewer inliers is re-rendered and solved again
REFINE_ITERATIONS = (
    2  # Render2Loc iterates render, match, PnP three times in all (arXiv 2302.06287)
)
UNKNOWN_PITCH_DEG = -35.0  # oblique: between the steepest and shallowest pitches tested


class TrackingError(Exception):
    """The first photo could not be localised, or too many searches in a row failed."""


class PhotoStatus(StrEnum):
    """What happened to a photo."""

    TRACKED = "tracked"
    RELOCALISED = "relocalised"  # found by the local search after a lost track
    REJECTED = "rejected"  # located, then dropped by the lens graph as a wrong frame
    LOST = "lost"  # no pose


@dataclass(frozen=True)
class PhotoImage:
    """A photo's name and its RGB pixels.

    `sequence_index` is the photo's place in the full sequence when photos are missing from the
    list (from time stamps); without it the photos are taken to be one step apart.
    """

    name: str
    rgb: npt.NDArray[np.uint8]
    sequence_index: int | None = None


@dataclass(frozen=True)
class Scene:
    """What the tracker renders and queries: the render function, the area frame and the ground."""

    render: Renderer
    area: EnuFrame
    ground_height: GroundHeight


@dataclass(frozen=True)
class TrackConfig:
    """Thresholds of the tracker; the lens graph has its own `LensConfig`."""

    min_inliers: int = MINIMUM_INLIERS
    max_range_m: float = MAX_RANGE_M
    max_failed_searches: int = 10
    search: SearchConfig = SearchConfig()  # noqa: RUF009  # frozen
    lens: LensConfig = LensConfig()  # noqa: RUF009  # frozen


@dataclass(frozen=True)
class TrackedPhoto:
    """One photo's result; `pose` is None only for a lost photo."""

    name: str
    status: PhotoStatus
    pose: CameraPoseEnu | None
    inliers: int
    reprojection_rmse_px: float | None


@dataclass(frozen=True)
class SearchEvent:
    """A local search after a lost track."""

    photo: str
    radius_m: float
    renders: int
    recovered: bool


@dataclass(frozen=True)
class TrackResult:
    """The lens, every photo's outcome and the searches that were run."""

    lens: LensEstimate
    photos: tuple[TrackedPhoto, ...]
    searches: tuple[SearchEvent, ...]


@dataclass(frozen=True)
class TrackingContext:
    """What every localisation needs: the scene, the matcher and the thresholds.

    `on_photo`, if given, is called with (photos done, photos in all) after each photo.
    """

    scene: Scene
    matcher: Matcher
    config: TrackConfig = TrackConfig()  # frozen
    on_photo: Callable[[int, int], None] | None = None


@dataclass(frozen=True)
class _Fix:
    index: int  # position in the photo list
    step: int  # place in the full sequence
    estimate: PoseEstimate
    correspondences: Correspondences
    relocalised: bool


def track(photos: Sequence[PhotoImage], start: CameraPose, context: TrackingContext) -> TrackResult:
    """Follow `photos` from `start`, the first photo's approximate pose, and fit the lens.

    Raises `TrackingError` if the first photo is not localised or searches keep failing, and
    `ValueError` for no photos or photos of different sizes.
    """
    height, width = _common_size(photos)
    steps = _steps(photos)
    config = context.config
    first_attempt = _first_attempt(photos[0], start, width, context)
    if first_attempt.estimate is None or first_attempt.estimate.inlier_count < config.min_inliers:
        msg = f"the first photo {photos[0].name} was not localised from the start pose"
        raise TrackingError(msg)
    focal = _scanned_focal(first_attempt, width, height)
    fixes, searches = _follow(photos, steps, first_attempt, focal, context)
    observations = [
        FrameObservations(
            fix.step,
            CameraPoseEnu(fix.estimate.centre_enu, fix.estimate.camera_to_enu),
            fix.correspondences.photo_points[fix.estimate.inlier_mask],
            fix.correspondences.world_points[fix.estimate.inlier_mask],
        )
        for fix in fixes
    ]
    fit = fit_lens(observations, Lens(focal, 0.0, 0.0, width, height), config.lens)
    return TrackResult(
        fit.estimate,
        _outcomes(photos, fixes, fit.poses, set(fit.rejected)),
        tuple(searches),
    )


def _common_size(photos: Sequence[PhotoImage]) -> tuple[int, int]:
    if not photos:
        msg = "no photos to track"
        raise ValueError(msg)
    sizes = {photo.rgb.shape[:2] for photo in photos}
    if len(sizes) > 1:
        msg = f"photos differ in size: {sorted(sizes)}"
        raise ValueError(msg)
    height, width = (int(side) for side in photos[0].rgb.shape[:2])
    return height, width


def _steps(photos: Sequence[PhotoImage]) -> list[int]:
    steps = [
        photo.sequence_index if photo.sequence_index is not None else index
        for index, photo in enumerate(photos)
    ]
    if any(later <= earlier for earlier, later in pairwise(steps)):
        msg = "sequence indices must increase from photo to photo"
        raise ValueError(msg)
    return steps


def nominal_focal(width_px: int) -> float:
    """The focal length of a `NOMINAL_HFOV_DEG` camera, in pixels of a `width_px` image."""
    return (width_px / 2) / math.tan(math.radians(NOMINAL_HFOV_DEG) / 2)


@dataclass(frozen=True)
class Attempt:
    """A photo localised at a prior: the correspondences and the pose estimate (None if none)."""

    correspondences: Correspondences
    estimate: PoseEstimate | None


def pinhole(width: int, height: int, focal: float) -> Intrinsics:
    """Square pixels, principal point at the centre, no distortion."""
    return Intrinsics(width, height, focal, focal, width / 2, height / 2, ())


def localise_at(
    photo: PhotoImage, prior: CameraPose, focal: float, context: TrackingContext
) -> Attempt:
    """Render at `prior` with `focal`, match, lift and solve."""
    height, width = photo.rgb.shape[:2]
    intrinsics = pinhole(width, height, focal)
    views = perspective_views(
        PhotoQuery(photo.rgb, intrinsics, prior, context.scene.area),
        context.scene.render,
        context.config.max_range_m,
    )
    reference = views.reference.render.rgb
    correspondences = lift_matches(context.matcher(views.photo_view, reference), views)
    return Attempt(correspondences, solve_pose(correspondences, intrinsics))


def _first_attempt(
    photo: PhotoImage, start: CameraPose, width: int, context: TrackingContext
) -> Attempt:
    """Localise the first photo at the start pose with several focal lengths; the most inliers win.

    The lens is unknown, and a pose solved at a wrong focal is biased: rendered again at the
    nominal focal it matches few features, though it is close to the truth.
    """
    attempts = [
        localise_at(photo, start, relative * nominal_focal(width), context)
        for relative in FIRST_PHOTO_FOCAL_TRIES
    ]
    return max(attempts, key=lambda a: 0 if a.estimate is None else a.estimate.inlier_count)


def _scanned_focal(attempt: Attempt, width: int, height: int) -> float:
    """The focal length with the lowest reprojection error over the scan, on the inliers."""
    assert attempt.estimate is not None  # noqa: S101  # checked by the caller
    world = attempt.correspondences.world_points[attempt.estimate.inlier_mask]
    pixels = attempt.correspondences.photo_points[attempt.estimate.inlier_mask]
    nominal = nominal_focal(width)
    errors = [
        _reprojection_rms(world, pixels, pinhole(width, height, scale * nominal).matrix())
        for scale in FOCAL_SCAN_RELATIVE
    ]
    return float(FOCAL_SCAN_RELATIVE[int(np.argmin(errors))] * nominal)


def _reprojection_rms(
    world: npt.NDArray[np.float64],
    pixels: npt.NDArray[np.float64],
    camera_matrix: npt.NDArray[np.float64],
) -> float:
    _, rotation, translation = cv2.solvePnP(
        world, pixels, camera_matrix, None, flags=cv2.SOLVEPNP_SQPNP
    )
    projected, _ = cv2.projectPoints(world, rotation, translation, camera_matrix, None)
    return float(np.sqrt(np.mean(np.sum((projected.reshape(-1, 2) - pixels) ** 2, axis=1))))


def _follow(
    photos: Sequence[PhotoImage],
    steps: list[int],
    first: Attempt,
    focal: float,
    context: TrackingContext,
) -> tuple[list[_Fix], list[SearchEvent]]:
    fixes: list[_Fix] = []
    searches: list[SearchEvent] = []
    config = context.config
    failed_in_a_row = 0
    for index, photo in enumerate(photos):
        if not fixes:
            attempt = first  # localised by `track` over several focal lengths
        else:
            stages = _prior_stages(fixes, steps[index], context.scene.area)
            attempt = _first_acceptable(photo, stages, focal, context)
        relocalised = False
        if not solved(attempt, config) and fixes:
            attempt, event = _search(photo, steps[index], fixes, focal, context)
            searches.append(event)
            relocalised = event.recovered
            failed_in_a_row = 0 if event.recovered else failed_in_a_row + 1
            if failed_in_a_row >= config.max_failed_searches:
                msg = f"{failed_in_a_row} local searches in a row failed at {photo.name}"
                raise TrackingError(msg)
        elif solved(attempt, config):
            failed_in_a_row = 0
        if solved(attempt, config) and attempt.estimate is not None:
            fixes.append(
                _Fix(index, steps[index], attempt.estimate, attempt.correspondences, relocalised)
            )
        if context.on_photo is not None:
            context.on_photo(index + 1, len(photos))
    return fixes, searches


def best_attempt(
    photo: PhotoImage, priors: Sequence[CameraPose], focal: float, context: TrackingContext
) -> Attempt:
    """Localise at each prior; the attempt with the most inliers (the first if none is solved)."""
    attempts = [localise_at(photo, prior, focal, context) for prior in priors]
    localised = [a for a in attempts if solved(a, context.config)]
    if not localised:
        return attempts[0]
    return max(localised, key=lambda a: a.estimate.inlier_count if a.estimate else 0)


def solved(attempt: Attempt, config: TrackConfig) -> bool:
    """Whether the attempt found a pose with at least `min_inliers` inliers."""
    return attempt.estimate is not None and attempt.estimate.inlier_count >= config.min_inliers


def _predicted(
    fixes: list[_Fix], step: int, area: EnuFrame, *, turning: bool = False
) -> CameraPose:
    """Constant velocity from the last two fixes, scaled by the photos since the last one.

    With `turning` the camera also keeps its angular velocity: the rotation between the last two
    fixes, scaled the same way, is applied again (a yaw or gimbal move of several degrees a photo
    leaves the heading basin of the match in two photos).
    """
    last = fixes[-1]
    if len(fixes) < MIN_FIXES_FOR_VELOCITY:
        return pose_from_camera_to_enu(area, last.estimate.centre_enu, last.estimate.camera_to_enu)
    before = fixes[-2]
    span = last.step - before.step
    velocity = (last.estimate.centre_enu - before.estimate.centre_enu) / span
    centre = last.estimate.centre_enu + velocity * (step - last.step)
    rotation = last.estimate.camera_to_enu
    if turning:
        turn = Rotation.from_matrix(last.estimate.camera_to_enu @ before.estimate.camera_to_enu.T)
        advance = Rotation.from_rotvec(turn.as_rotvec() * (step - last.step) / span)
        rotation = advance.as_matrix() @ last.estimate.camera_to_enu
    return pose_from_camera_to_enu(area, centre, rotation)


def _prior_stages(fixes: list[_Fix], step: int, area: EnuFrame) -> list[list[CameraPose]]:
    """Priors to try in turn, each stage only if the one before found no pose.

    First the constant-velocity prediction and the last fix held (velocity noise misleads weak
    views). Then the prediction that also keeps the angular velocity, and the earlier fixes held:
    a yaw or gimbal move of several degrees a photo leaves the heading basin in two photos, and an
    earlier, stronger fix often still renders close enough to match. Trying them last keeps a wrong
    prior from beating a right one.
    """
    held = [
        pose_from_camera_to_enu(area, fix.estimate.centre_enu, fix.estimate.camera_to_enu)
        for fix in reversed(fixes[-HELD_FIXES_AS_PRIORS:])
    ]
    if len(fixes) < MIN_FIXES_FOR_VELOCITY:
        return [held[:1], held[1:]] if len(held) > 1 else [held]
    return [
        [_predicted(fixes, step, area), held[0]],
        [_predicted(fixes, step, area, turning=True), *held[1:]],
    ]


def _first_acceptable(
    photo: PhotoImage, stages: list[list[CameraPose]], focal: float, context: TrackingContext
) -> Attempt:
    """The first stage's fix that solves and lies near its prior; else an unsolved attempt."""
    first: Attempt | None = None
    for priors in stages:
        attempt = _iterated(photo, best_attempt(photo, priors, focal, context), focal, context)
        first = first or attempt
        if solved(attempt, context.config) and _stayed_near(attempt, priors, context):
            return attempt
    assert first is not None  # noqa: S101  # stages is never empty
    return Attempt(first.correspondences, None)  # a fix far from every prior is not trusted


def _stayed_near(attempt: Attempt, priors: list[CameraPose], context: TrackingContext) -> bool:
    """Whether the fix lies within the basin of one of the priors.

    A wrong match on a repeating scene lands far from where the render was made.
    """
    assert attempt.estimate is not None  # noqa: S101  # checked by the caller
    centres = [camera_centre_and_rotation(p, context.scene.area)[0] for p in priors]
    return any(
        float(np.linalg.norm(attempt.estimate.centre_enu - c)) <= PRIOR_PULL_MAX_M for c in centres
    )


def _iterated(
    photo: PhotoImage, attempt: Attempt, focal: float, context: TrackingContext
) -> Attempt:
    """Re-render at a weak fix's own pose and solve again while that finds more inliers."""
    for _ in range(REFINE_ITERATIONS):
        estimate = attempt.estimate
        if not solved(attempt, context.config) or estimate is None:
            break
        if estimate.inlier_count >= REFINE_BELOW_INLIERS:
            break
        area = context.scene.area
        prior = pose_from_camera_to_enu(area, estimate.centre_enu, estimate.camera_to_enu)
        again = localise_at(photo, prior, focal, context)
        if not solved(again, context.config) or again.estimate is None:
            break
        if again.estimate.inlier_count <= estimate.inlier_count:
            break
        attempt = again
    return attempt


def _typical_step_m(fixes: list[_Fix]) -> float:
    if len(fixes) < MIN_FIXES_FOR_VELOCITY:
        return 0.0
    steps = [
        float(np.linalg.norm(b.estimate.centre_enu - a.estimate.centre_enu)) / (b.step - a.step)
        for a, b in pairwise(fixes)
    ]
    return float(np.median(steps))


def _search(
    photo: PhotoImage, step: int, fixes: list[_Fix], focal: float, context: TrackingContext
) -> tuple[Attempt, SearchEvent]:
    """Local search around the last fix: the best attempt among the best-matching renders."""
    scene, config = context.scene, context.config
    last = fixes[-1]
    last_pose = pose_from_camera_to_enu(
        scene.area, last.estimate.centre_enu, last.estimate.camera_to_enu
    )
    height_above_ground = float(
        last.estimate.centre_enu[2]
        - scene.ground_height(
            float(last.estimate.centre_enu[0]), float(last.estimate.centre_enu[1])
        )
    )
    radius = search_radius_m(config.search, _typical_step_m(fixes), step - last.step)
    search = config.search
    heights = [f * height_above_ground for f in search.height_factors]
    centre = last.estimate.centre_enu[:2]
    nearby = candidate_poses(  # a small yaw or gimbal move, the common cause of a lost photo
        search,
        scene.area,
        scene.ground_height,
        centre,
        radius,
        heights,
        [last_pose.pitch_deg + o for o in search.local_pitch_offsets_deg],
        [last_pose.heading_deg + o for o in search.local_heading_offsets_deg],
        search.local_spacing_m,
    )
    turned = candidate_poses(  # a turn of any size, at the last pitch
        search,
        scene.area,
        scene.ground_height,
        centre,
        radius,
        heights,
        [last_pose.pitch_deg],
        list(np.arange(search.heading_count) * 360.0 / search.heading_count),
        search.spacing_m,
    )
    candidates = nearby + turned
    height, width = photo.rgb.shape[:2]
    best = best_candidates(
        config.search,
        photo.rgb,
        candidates,
        scene.render,
        context.matcher,
        pinhole(width, height, focal),
        config.max_range_m,
    )
    chosen = best_attempt(photo, best, focal, context)
    if solved(chosen, config) and not _plausible_recovery(chosen, fixes, step, config):
        chosen = Attempt(chosen.correspondences, None)  # a wrong match on a repeating scene
    return chosen, SearchEvent(photo.name, radius, len(candidates), solved(chosen, config))


def _plausible_recovery(
    attempt: Attempt, fixes: list[_Fix], step: int, config: TrackConfig
) -> bool:
    """Whether a recovered fix lies within reach of the last fix (judged from two fixes on)."""
    assert attempt.estimate is not None  # noqa: S101  # checked by the caller
    if len(fixes) < MIN_FIXES_FOR_VELOCITY:
        return True
    last = fixes[-1]
    reach = max_recovered_displacement_m(config.search, _typical_step_m(fixes), step - last.step)
    return float(np.linalg.norm(attempt.estimate.centre_enu - last.estimate.centre_enu)) <= reach


def _outcomes(
    photos: Sequence[PhotoImage],
    fixes: list[_Fix],
    graph_poses: dict[int, CameraPoseEnu],
    rejected: set[int],
) -> tuple[TrackedPhoto, ...]:
    by_index = {fix.index: fix for fix in fixes}
    outcomes = []
    for index, photo in enumerate(photos):
        fix = by_index.get(index)
        if fix is None:
            outcomes.append(TrackedPhoto(photo.name, PhotoStatus.LOST, None, 0, None))
            continue
        if fix.step in rejected:
            status = PhotoStatus.REJECTED
            pose = CameraPoseEnu(fix.estimate.centre_enu, fix.estimate.camera_to_enu)
        else:
            status = PhotoStatus.RELOCALISED if fix.relocalised else PhotoStatus.TRACKED
            pose = graph_poses[fix.step]
        outcomes.append(
            TrackedPhoto(
                photo.name,
                status,
                pose,
                fix.estimate.inlier_count,
                fix.estimate.reprojection_rmse_px,
            )
        )
    return tuple(outcomes)
