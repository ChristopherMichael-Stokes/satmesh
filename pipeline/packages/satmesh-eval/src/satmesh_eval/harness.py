"""Run photos with known poses through the localisation harness against a store.

Each photo is localised against up to four references (full surface, bare earth, flat ortho,
photo warped top-down) from a prior pose, the true pose displaced by a fixed offset or given in the
pose file. Each fix keeps its status, inlier count, reprojection residual and error against the
true pose, and how well photo and reference agree when the reference is rendered at the true pose.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from satmesh_core import EnuFrame
from satmesh_eval.camera import (
    CameraPose,
    PoseOffset,
    camera_centre_and_rotation,
    offset_pose,
    pose_from_camera_to_enu,
)
from satmesh_eval.gpu import GpuRenderer
from satmesh_eval.ground import flattened, ground_height_m, load_ground_scene
from satmesh_eval.localise import (
    MINIMUM_INLIERS,
    Localisation,
    MatchingViews,
    PoseError,
    localise,
    pose_error,
)
from satmesh_eval.matching import Matcher
from satmesh_eval.metrics import KnownPoseMetrics, RecallSummary, known_pose_metrics, pose_recall
from satmesh_eval.panels import FixPanels, encode_panels, encode_photo
from satmesh_eval.perspective import AreaScene, load_area_scene
from satmesh_eval.photos import WorkingPhoto, load_working_photo
from satmesh_eval.poses import PhotoRecord
from satmesh_eval.references import PhotoQuery, Renderer, nadir_views, perspective_views

DEFAULT_PRIOR_OFFSET = PoseOffset(2.0, -2.0, 0.5, 3.0, 1.0, 0.0)  # 2.9 m and 3 degrees off
DEFAULT_MAX_RANGE_M = 500.0
TOP_DOWN_GROUND_SAMPLE_M = 0.3  # the finest ground sample of the imagery the stores carry
PLANE_HEIGHT_KEY_DECIMALS = 3  # flat renderers are shared between photos on the same ground


class Reference(StrEnum):
    """What the photo is matched against."""

    SURFACE = "surface"
    GROUND = "ground"
    FLAT = "flat"
    TOP_DOWN = "top-down"


class FixStatus(StrEnum):
    """Outcome of one localisation."""

    SOLVED = "solved"
    REJECTED = "rejected"  # a pose was found but with fewer inliers than the minimum
    UNSOLVED = "unsolved"  # no pose could be computed from the matches
    SKIPPED = "skipped"  # the reference could not be built for this photo


@dataclass(frozen=True)
class Fix:
    """One photo against one reference.

    `inlier_count` and `reprojection_rmse_px` describe the best pose found, accepted or rejected;
    `pose` and `error` exist only for a solved fix. `note` explains a skipped fix.
    """

    reference: Reference
    status: FixStatus
    note: str | None
    match_count: int
    inlier_count: int | None
    reprojection_rmse_px: float | None
    pose: CameraPose | None
    error: PoseError | None
    at_true_pose: KnownPoseMetrics | None
    panels: FixPanels | None


@dataclass(frozen=True)
class PhotoResult:
    """All fixes of one photo."""

    photo: str
    truth: CameraPose
    prior: CameraPose
    photo_jpeg: bytes
    fixes: tuple[Fix, ...]


@dataclass(frozen=True)
class RunResult:
    """A run over a set of photos."""

    matcher: str
    minimum_inliers: int
    max_range_m: float
    references: tuple[Reference, ...]
    photos: tuple[PhotoResult, ...]

    def recall(self, reference: Reference) -> RecallSummary:
        """Recall of one reference over all photos; a skipped photo counts as unsolved."""
        errors = [
            fix.error for photo in self.photos for fix in photo.fixes if fix.reference == reference
        ]
        return pose_recall(errors)


class ReferenceRenderers:
    """GPU renderers for the references, built from a full-surface and a bare-earth scene.

    A scene is needed only by the references that use it (`surface` for the full-surface
    reference, `ground` for the other three). Flat planes are built per ground height and kept,
    so photos over the same ground share one.
    """

    def __init__(self, surface: AreaScene | None, ground: AreaScene | None) -> None:
        """Upload the scenes that are given."""
        self._surface = surface
        self._ground = ground
        self._surface_renderer = GpuRenderer(surface) if surface else None
        self._ground_renderer = GpuRenderer(ground) if ground else None
        self._flat: dict[float, GpuRenderer] = {}

    @classmethod
    def from_store(cls, store: Path, references: Sequence[Reference]) -> "ReferenceRenderers":
        """Load from `store` the scenes the `references` need."""
        surface = load_area_scene(store) if Reference.SURFACE in references else None
        needs_ground = any(reference != Reference.SURFACE for reference in references)
        return cls(surface, load_ground_scene(store) if needs_ground else None)

    @property
    def frame(self) -> EnuFrame:
        """The area ENU frame the loaded scenes share."""
        scene = self._surface or self._ground
        if scene is None:
            msg = "no reference selected"
            raise ValueError(msg)
        return scene.frame

    def plane_height_m(self, east_m: float, north_m: float) -> float:
        """Bare-earth height at an area-ENU position; raises `ValueError` outside the store."""
        if self._ground is None:
            msg = "no bare-earth scene loaded"
            raise ValueError(msg)
        return ground_height_m(self._ground, east_m, north_m)

    def renderer(self, reference: Reference, plane_height_m: float | None) -> Renderer:
        """The render function of a reference; flat and top-down need the plane height."""
        if reference == Reference.SURFACE and self._surface_renderer:
            return self._surface_renderer.render
        if reference == Reference.GROUND and self._ground_renderer:
            return self._ground_renderer.render
        if plane_height_m is None or self._ground is None:
            msg = f"reference {reference} needs a plane height and the bare-earth scene"
            raise ValueError(msg)
        key = round(plane_height_m, PLANE_HEIGHT_KEY_DECIMALS)
        if key not in self._flat:
            self._flat[key] = GpuRenderer(flattened(self._ground, plane_height_m))
        return self._flat[key].render


@dataclass(frozen=True)
class RunSettings:
    """What is shared by every photo of a run."""

    renderers: ReferenceRenderers
    references: tuple[Reference, ...]
    matcher: Matcher
    matcher_name: str
    prior_offset: PoseOffset = DEFAULT_PRIOR_OFFSET
    minimum_inliers: int = MINIMUM_INLIERS
    max_range_m: float = DEFAULT_MAX_RANGE_M


@dataclass(frozen=True)
class _PhotoCase:
    working: WorkingPhoto
    truth: CameraPose
    prior: CameraPose
    plane: float | str  # bare-earth height under the prior camera, or why there is none


def run_photos(
    records: Sequence[PhotoRecord],
    photo_directory: Path,
    settings: RunSettings,
    on_photo: Callable[[int, int], None] | None = None,
) -> RunResult:
    """Localise every record's photo against every reference of `settings`."""
    results = []
    for index, record in enumerate(records):
        working = load_working_photo(
            photo_directory / record.photo, record.intrinsics.to_intrinsics()
        )
        truth = record.to_pose()
        prior = (
            record.prior.to_pose() if record.prior else offset_pose(truth, settings.prior_offset)
        )
        case = _PhotoCase(working, truth, prior, _plane_height(settings.renderers, prior))
        fixes = tuple(_fix(reference, settings, case) for reference in settings.references)
        results.append(PhotoResult(record.photo, truth, prior, encode_photo(working.image), fixes))
        if on_photo:
            on_photo(index + 1, len(records))
    return RunResult(
        settings.matcher_name,
        settings.minimum_inliers,
        settings.max_range_m,
        settings.references,
        tuple(results),
    )


def _plane_height(renderers: ReferenceRenderers, prior: CameraPose) -> float | str:
    centre, _ = camera_centre_and_rotation(prior, renderers.frame)
    try:
        return renderers.plane_height_m(float(centre[0]), float(centre[1]))
    except ValueError as error:
        return str(error)


def _fix(reference: Reference, settings: RunSettings, case: _PhotoCase) -> Fix:
    plane_height = None if isinstance(case.plane, str) else case.plane
    if plane_height is None and reference in (Reference.FLAT, Reference.TOP_DOWN):
        return _skipped(reference, str(case.plane))
    frame = settings.renderers.frame
    try:
        render = settings.renderers.renderer(reference, plane_height)
        views = _views(reference, case, case.prior, render, plane_height, settings)
        true_views = _views(reference, case, case.truth, render, plane_height, settings)
    except ValueError as error:
        return _skipped(reference, str(error))
    intrinsics = case.working.intrinsics
    result = localise(views, intrinsics, settings.matcher, settings.minimum_inliers)
    centre, rotation = camera_centre_and_rotation(case.truth, frame)
    true_matches = settings.matcher(true_views.photo_view, true_views.reference.render.rgb)
    best = result.estimate or result.rejected
    return Fix(
        reference=reference,
        status=_status(result),
        note=None,
        match_count=result.match_count,
        inlier_count=best.inlier_count if best else None,
        reprojection_rmse_px=best.reprojection_rmse_px if best else None,
        pose=(
            pose_from_camera_to_enu(
                frame, result.estimate.centre_enu, result.estimate.camera_to_enu
            )
            if result.estimate
            else None
        ),
        error=pose_error(result.estimate, centre, rotation) if result.estimate else None,
        at_true_pose=known_pose_metrics(true_matches, true_views.reference.render),
        panels=encode_panels(views, result, intrinsics, centre, rotation),
    )


def _status(result: Localisation) -> FixStatus:
    if result.estimate is not None:
        return FixStatus.SOLVED
    return FixStatus.REJECTED if result.rejected is not None else FixStatus.UNSOLVED


def _views(  # noqa: PLR0913, PLR0917 (reference, case, pose, renderer, plane and the run settings)
    reference: Reference,
    case: _PhotoCase,
    pose: CameraPose,
    render: Renderer,
    plane_height: float | None,
    settings: RunSettings,
) -> MatchingViews:
    query = PhotoQuery(case.working.image, case.working.intrinsics, pose, settings.renderers.frame)
    if reference == Reference.TOP_DOWN and plane_height is not None:
        return nadir_views(
            query, render, plane_height, TOP_DOWN_GROUND_SAMPLE_M, settings.max_range_m
        )
    return perspective_views(query, render, settings.max_range_m)


def _skipped(reference: Reference, note: str) -> Fix:
    return Fix(reference, FixStatus.SKIPPED, note, 0, None, None, None, None, None, None)
