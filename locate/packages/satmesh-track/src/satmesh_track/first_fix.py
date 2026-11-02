"""The first photo's pose from priors: a two-level place search, then verification by tracking.

1. Yaw offsets: the heading change of the fused frames from the first, from XFeat matches
   (`yaw.py`); a window whose offsets cannot be estimated falls back to the first photo alone.
2. Level 1: coarse views over the set the priors allow (`grid.py`), rendered from the store and
   described with MegaLoc in chunks as they are rendered, scored by the fused similarity of the
   window's frames; the best `coarse_places` places `coarse_separation_m` apart survive.
3. Level 2: fine views around those places, scored by the first photo alone; the best
   `final_places` places `final_separation_m` apart survive.
4. Verification: each place is refined by a local match search and localised; a solved place
   tracks the first `verify_photos` photos and is accepted with `min_tracked_photos` tracked. The
   most photos tracked, then the highest median inliers, wins.

When nothing is accepted the priors are relaxed one at a time, heading, then pitch, then position,
and the search runs again. Every step reports to an event callable (`satmesh_locate.events`) whose
times are seconds on one monotonic clock started with the run.
"""

import math
import time
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import batched
from statistics import median
from typing import Literal, NamedTuple

import numpy as np
import numpy.typing as npt

from satmesh_core import ecef_to_geodetic
from satmesh_eval.camera import (
    CameraPose,
    camera_centre_and_rotation,
    pose_from_camera_to_enu,
    pose_from_enu,
)
from satmesh_eval.perspective import GroundExtent
from satmesh_locate.events import (
    Bounds,
    Candidate,
    Candidates,
    Cell,
    CellBatch,
    Event,
    Fix,
    FusionFrame,
    FusionWindow,
    GridLevel,
    PriorRelaxed,
    Priors,
    RunEnd,
    RunStart,
    StageEnd,
    StageStart,
    VerificationResult,
    VerificationStart,
)
from satmesh_locate.megaloc import MegaLocDescriber
from satmesh_locate.places import Cells, Place, top_places
from satmesh_track.grid import (
    LevelGrid,
    Position,
    candidate_mask,
    frame_similarities,
    fused_scores,
    lattice_offsets_deg,
    level_one,
    level_two,
    planned_fine_positions,
    view_index,
)
from satmesh_track.priors import FULL_CIRCLE_DEG, FirstFixConfig
from satmesh_track.search import best_candidates, candidate_poses
from satmesh_track.store_scene import StoreScene
from satmesh_track.tracker import (
    PhotoImage,
    PhotoStatus,
    TrackingContext,
    TrackingError,
    best_attempt,
    nominal_focal,
    pinhole,
    solved,
    track,
)
from satmesh_track.yaw import focal_for_field_of_view, window_offsets_deg

DESCRIBE_CHUNK_VIEWS = 256  # renders held while described: about 180 MB at 640 x 360
CELL_BATCH_INTERVAL_S = 0.1  # the monitor redraws at about 10 Hz
FULL_PITCH_HALF_WIDTH_DEG = 90.0
STAGE_YAW = "yaw offsets"
STAGE_PHOTOS = "describe photos"
STAGE_VERIFY = "verification"

type RelaxedPrior = Literal["heading", "pitch", "area"]


@dataclass(frozen=True)
class StageTime:
    """Seconds a stage took; a level's render and describe stage also splits its time."""

    name: str
    seconds: float
    render_seconds: float = 0.0
    describe_seconds: float = 0.0


@dataclass(frozen=True)
class Hypothesis:
    """A final place and its verification; `pose` is the first photo's pose if it localised."""

    rank: int
    place: Place
    renders: int
    first_photo_inliers: int
    photos_tracked: int
    photos_verified: int
    median_inliers: float
    pose: CameraPose | None


@dataclass(frozen=True)
class FirstFix:
    """The winning pose, its rank, every hypothesis of the last search, timings, priors used."""

    pose: CameraPose
    rank: int
    hypotheses: tuple[Hypothesis, ...]
    timings: tuple[StageTime, ...]
    priors: Priors


class Relaxation(NamedTuple):
    """One rung of the widening ladder: the prior relaxed and the priors after it."""

    prior: RelaxedPrior
    half_width_before: float
    half_width_after: float
    priors: Priors


def ignore_event(_event: Event) -> None:
    """The event callable of a run nobody watches."""


class _ScoredViews(NamedTuple):
    scores: npt.NDArray[np.float64]  # fused score of every view, in grid order
    similarity: npt.NDArray[np.float32]  # one row per fused frame, one column per view


@dataclass
class _Split:
    render_seconds: float = 0.0
    describe_seconds: float = 0.0


class _Run:
    """The run's clock, its event callable and the times of its stages."""

    def __init__(self, emit: Callable[[Event], None]) -> None:
        self._emit = emit
        self._started = time.monotonic()
        self.timings: list[StageTime] = []

    def seconds(self) -> float:
        """Seconds since the run started."""
        return time.monotonic() - self._started

    def emit(self, event: Event) -> None:
        """Pass one event on."""
        self._emit(event)

    @contextmanager
    def stage(self, name: str, units: int) -> Generator[_Split]:
        """Emit the stage's start and end and record its time."""
        split = _Split()
        started = self.seconds()
        self.emit(StageStart(time_s=started, stage=name, units=units))
        yield split
        ended = self.seconds()
        self.emit(StageEnd(time_s=ended, stage=name))
        self.timings.append(
            StageTime(name, ended - started, split.render_seconds, split.describe_seconds)
        )


class _CellBatcher:
    """Cells of one level, emitted together at most every `CELL_BATCH_INTERVAL_S`."""

    def __init__(self, run: _Run, level: int) -> None:
        self._run = run
        self._level = level
        self._pending: list[Cell] = []
        self._last_emit_s = run.seconds()

    def add(self, cells: Sequence[Cell]) -> None:
        """Queue cells, emitting the queue if the interval has passed."""
        self._pending.extend(cells)
        if self._run.seconds() - self._last_emit_s >= CELL_BATCH_INTERVAL_S:
            self.flush()

    def flush(self) -> None:
        """Emit the queued cells, if any; at a stage's end, whatever the interval."""
        if not self._pending:
            return
        self._last_emit_s = self._run.seconds()
        self._run.emit(CellBatch(time_s=self._last_emit_s, level=self._level, cells=self._pending))
        self._pending = []


@dataclass(frozen=True)
class _Setup:
    """What every search attempt shares: inputs, the photos' descriptors and the frame offsets."""

    images: Sequence[PhotoImage]
    store_scene: StoreScene
    describer: MegaLocDescriber
    context: TrackingContext
    config: FirstFixConfig
    queries: npt.NDArray[np.float32]  # one MegaLoc descriptor per fused frame, frame 0 first
    lattice_offsets: tuple[float, ...]  # the frames' heading offsets on the heading lattice


class _Scoring(NamedTuple):
    """The frames a level is scored with: their descriptors and lattice heading offsets."""

    queries: npt.NDArray[np.float32]
    lattice_offsets: tuple[float, ...]


@dataclass(frozen=True)
class _Found:
    winner: Hypothesis
    pose: CameraPose  # the winner's
    hypotheses: tuple[Hypothesis, ...]


def first_fix(  # noqa: PLR0913 (photos, scene, describer, context, settings, events)
    images: Sequence[PhotoImage],
    store_scene: StoreScene,
    describer: MegaLocDescriber,
    context: TrackingContext,
    *,
    config: FirstFixConfig,
    emit: Callable[[Event], None] = ignore_event,
) -> FirstFix:
    """The first photo's pose within the priors of `config`, widened until a place verifies.

    Raises:
        TrackingError: no place verified, even with every prior relaxed.
    """
    run = _Run(emit)
    run.emit(_run_start(run, images, store_scene, config))
    try:
        frames = _fusion_frames(images, config)
        offsets = _frame_offsets(frames, context, config, run)
        frames = frames[: len(offsets)]
        run.emit(_fusion_event(run, frames, offsets, config))
        setup = _Setup(
            images,
            store_scene,
            describer,
            context,
            config,
            _photo_descriptors(frames, describer, run),
            lattice_offsets_deg(offsets, config.heading_step_deg),
        )
        found, priors = widened_search(
            config.priors,
            store_scene.bounds,
            lambda priors: _search(priors, setup, run),
            lambda relaxation: run.emit(_relaxed_event(run, relaxation)),
        )
    except TrackingError:
        run.emit(RunEnd(time_s=run.seconds(), ok=False))
        raise
    run.emit(_fix_event(run, found, store_scene))
    run.emit(RunEnd(time_s=run.seconds(), ok=True))
    return FirstFix(found.pose, found.winner.rank, found.hypotheses, tuple(run.timings), priors)


def widened_search[T](
    priors: Priors,
    bounds: GroundExtent,
    search: Callable[[Priors], T | None],
    on_relaxed: Callable[[Relaxation], None],
) -> tuple[T, Priors]:
    """Search with `priors`, then with each rung of the ladder until a search finds something.

    Raises:
        TrackingError: no search found anything; the message names every prior relaxed.
    """
    found = search(priors)
    if found is not None:
        return found, priors
    tried: list[str] = []
    for relaxation in relaxations(priors, bounds):
        on_relaxed(relaxation)
        tried.append(relaxation.prior)
        found = search(relaxation.priors)
        if found is not None:
            return found, relaxation.priors
    relaxed = f"; relaxed in turn: {', '.join(tried)}" if tried else ""
    message = f"no place verified with the priors {priors.model_dump_json()}{relaxed}"
    raise TrackingError(message)


def relaxations(priors: Priors, bounds: GroundExtent) -> list[Relaxation]:
    """The ladder: each prior that is set dropped in turn, heading, then pitch, then position.

    Each rung keeps the relaxations before it. An area's half-width is the circle's radius, and
    once relaxed the distance from its centre to the farthest corner of the store.
    """
    rungs: list[Relaxation] = []
    current = priors
    if (heading := current.heading_deg) is not None:
        current = current.model_copy(update={"heading_deg": None})
        rungs.append(Relaxation("heading", heading.half_width, FULL_CIRCLE_DEG / 2, current))
    if (pitch := current.pitch_deg) is not None:
        current = current.model_copy(update={"pitch_deg": None})
        rungs.append(Relaxation("pitch", pitch.half_width, FULL_PITCH_HALF_WIDTH_DEG, current))
    if current.position is not None:
        circle = current.position
        current = current.model_copy(update={"position": None})
        farthest = max(
            math.hypot(east - circle.east_m, north - circle.north_m)
            for east in (bounds.west_m, bounds.east_m)
            for north in (bounds.south_m, bounds.north_m)
        )
        rungs.append(Relaxation("area", circle.radius_m, farthest, current))
    return rungs


def _fusion_frames(images: Sequence[PhotoImage], config: FirstFixConfig) -> list[PhotoImage]:
    """The photos fused at level 1: the first and every `fusion_frame_step`-th after it."""
    return list(images[:: config.fusion_frame_step][: config.fusion_frames])


def _frame_offsets(
    frames: Sequence[PhotoImage], context: TrackingContext, config: FirstFixConfig, run: _Run
) -> tuple[float, ...]:
    """Heading offsets of the frames from the first; just the first if they cannot be estimated."""
    with run.stage(STAGE_YAW, len(frames) - 1):
        height, width = frames[0].rgb.shape[:2]
        focal = focal_for_field_of_view(width, config.nominal_horizontal_fov_deg)
        offsets = window_offsets_deg(
            [frame.rgb for frame in frames],
            context.matcher,
            pinhole(width, height, focal).matrix(),
            pitch_deg=config.assumed_pitch_deg,
            method=config.yaw_method,
            agreement_deg=config.yaw_agreement_deg,
        )
    return (0.0,) if offsets is None else offsets


def _photo_descriptors(
    frames: Sequence[PhotoImage], describer: MegaLocDescriber, run: _Run
) -> npt.NDArray[np.float32]:
    with run.stage(STAGE_PHOTOS, len(frames)):
        return describer.describe([frame.rgb for frame in frames])


def _search(priors: Priors, setup: _Setup, run: _Run) -> _Found | None:
    """One pass of level 1, level 2 and verification; None if no place is accepted."""
    config, scene = setup.config, setup.store_scene
    heading_margin = max(abs(offset) for offset in setup.lattice_offsets)
    coarse_grid = level_one(config, scene.bounds, scene.scene.ground_height, priors, heading_margin)
    coarse = _ranked_level(
        coarse_grid,
        _Scoring(setup.queries, setup.lattice_offsets),
        (config.coarse_places, config.coarse_separation_m),
        priors=priors,
        setup=setup,
        run=run,
    )
    fine_grid = level_two(config, scene.bounds, scene.scene.ground_height, priors, coarse)
    final = _ranked_level(
        fine_grid,
        _Scoring(setup.queries[:1], (0.0,)),
        (config.final_places, config.final_separation_m),
        priors=priors,
        setup=setup,
        run=run,
    )
    with run.stage(STAGE_VERIFY, len(final)):
        hypotheses = tuple(
            _verified(rank, place, setup, run) for rank, place in enumerate(final, start=1)
        )
    accepted = [h for h in hypotheses if _accepted(h, setup.config)]
    if not accepted:
        return None
    winner = max(accepted, key=lambda h: (h.photos_tracked, h.median_inliers))
    assert winner.pose is not None  # noqa: S101  # an accepted hypothesis is localised
    return _Found(winner, winner.pose, hypotheses)


def _ranked_level(  # noqa: PLR0913 (grid, scoring, places kept, priors, setup, run)
    grid: LevelGrid,
    scoring: _Scoring,
    places: tuple[int, float],
    *,
    priors: Priors,
    setup: _Setup,
    run: _Run,
) -> list[Place]:
    """Render, describe and score a level's views, then keep its best separated places."""
    candidates = candidate_mask(grid, priors.heading_deg)
    with run.stage(f"level {grid.level}: render and describe", grid.view_count) as split:
        scored = _scored_views(grid, candidates, scoring, setup=setup, run=run, split=split)
    with run.stage(f"level {grid.level}: rank", grid.view_count):
        count, separation_m = places
        cells = grid.cells()
        best = top_places(
            scored.scores[candidates].astype(np.float32),
            _selected(cells, candidates),
            count,
            separation_m,
        )
        run.emit(
            Candidates(
                time_s=run.seconds(),
                level=grid.level,
                places=[
                    _candidate(
                        rank,
                        place,
                        frame_similarities(
                            scored.similarity,
                            grid.headings_deg,
                            scoring.lattice_offsets,
                            view_index(cells, place),
                        ),
                    )
                    for rank, place in enumerate(best, start=1)
                ],
            )
        )
    return best


def _scored_views(  # noqa: PLR0913 (grid, candidates, scoring, setup, run, split)
    grid: LevelGrid,
    candidates: npt.NDArray[np.bool_],
    scoring: _Scoring,
    *,
    setup: _Setup,
    run: _Run,
    split: _Split,
) -> _ScoredViews:
    """Each view's score and per-frame similarity, rendering and describing a chunk at a time."""
    cells = _CellBatcher(run, grid.level)
    per_position = grid.views_per_position
    candidate_views = candidates[:per_position]  # the same headings at every position
    scores = []
    similarities = []
    positions_per_chunk = max(1, DESCRIBE_CHUNK_VIEWS // per_position)
    for chunk in batched(grid.positions, positions_per_chunk, strict=False):
        started = time.perf_counter()
        renders = []
        for position in chunk:
            renders.extend(_rendered_views(grid, position, setup))
            cells.add(
                [
                    Cell(
                        east_m=position.east_m,
                        north_m=position.north_m,
                        state="rendered",
                        similarity=None,
                    )
                ]
            )
        split.render_seconds += time.perf_counter() - started
        started = time.perf_counter()
        similarity = scoring.queries @ setup.describer.describe(renders).T
        split.describe_seconds += time.perf_counter() - started
        chunk_scores = fused_scores(similarity, grid.headings_deg, scoring.lattice_offsets)
        best = np.where(candidate_views, chunk_scores.reshape(len(chunk), per_position), -np.inf)
        cells.add(
            [
                Cell(
                    east_m=position.east_m,
                    north_m=position.north_m,
                    state="described",
                    similarity=float(score),
                )
                for position, score in zip(chunk, best.max(axis=1), strict=True)
            ]
        )
        scores.append(chunk_scores)
        similarities.append(similarity)
    cells.flush()
    if not scores:
        return _ScoredViews(
            np.zeros(0, dtype=np.float64), np.zeros((len(scoring.queries), 0), dtype=np.float32)
        )
    return _ScoredViews(np.concatenate(scores), np.concatenate(similarities, axis=1))


def _rendered_views(
    grid: LevelGrid, position: Position, setup: _Setup
) -> list[npt.NDArray[np.uint8]]:
    """The renders of one position's views, at the render size and the tracker's nominal focal."""
    config, scene = setup.config, setup.store_scene.scene
    width, height = config.render_width_px, config.render_height_px
    intrinsics = pinhole(width, height, nominal_focal(width))
    max_range_m = setup.context.config.max_range_m
    return [
        scene.render(
            intrinsics,
            pose_from_enu(
                scene.area,
                np.array([position.east_m, position.north_m, position.ground_m + view.height_m]),
                view.heading_deg,
                view.pitch_deg,
                0.0,
            ),
            max_range_m,
        ).rgb
        for view in grid.views_at(position)
    ]


def _selected(cells: Cells, mask: npt.NDArray[np.bool_]) -> Cells:
    return Cells(
        cells.east[mask],
        cells.north[mask],
        cells.ground[mask],
        cells.height[mask],
        cells.heading[mask],
        cells.pitch[mask],
    )


def _verified(rank: int, place: Place, setup: _Setup, run: _Run) -> Hypothesis:
    """Refine a place by a local match search, localise the first photo there and track."""
    run.emit(VerificationStart(time_s=run.seconds(), rank=rank))
    config, context = setup.config, setup.context
    photo = setup.images[0]
    poses = _refinement_poses(place, setup)
    height, width = photo.rgb.shape[:2]
    focal = nominal_focal(width)
    best = best_candidates(
        context.config.search,
        photo.rgb,
        poses,
        context.scene.render,
        context.matcher,
        pinhole(width, height, focal),
        context.config.max_range_m,
    )
    attempt = best_attempt(photo, best, focal, context)
    verify = setup.images[: config.verify_photos]
    inliers = 0 if attempt.estimate is None else attempt.estimate.inlier_count
    pose, tracked, median_inliers = None, 0, 0.0
    if solved(attempt, context.config) and attempt.estimate is not None:
        pose = pose_from_camera_to_enu(
            context.scene.area, attempt.estimate.centre_enu, attempt.estimate.camera_to_enu
        )
        tracked, median_inliers = _tracked(verify, pose, context)
    hypothesis = Hypothesis(
        rank, place, len(poses), inliers, tracked, len(verify), median_inliers, pose
    )
    run.emit(
        VerificationResult(
            time_s=run.seconds(),
            rank=rank,
            inliers=hypothesis.first_photo_inliers,
            frames_tracked=hypothesis.photos_tracked,
            frames_total=hypothesis.photos_verified,
            accepted=_accepted(hypothesis, config),
        )
    )
    return hypothesis


def _refinement_poses(place: Place, setup: _Setup) -> list[CameraPose]:
    """Poses around a place: nearby positions, heights, pitches and headings about its view."""
    config, context = setup.config, setup.context
    return candidate_poses(
        context.config.search,
        context.scene.area,
        context.scene.ground_height,
        np.array([place.east, place.north]),
        config.refine_radius_m,
        [factor * place.height for factor in config.refine_height_factors],
        [place.pitch + offset for offset in config.refine_pitch_offsets_deg],
        [place.heading + offset for offset in config.refine_heading_offsets_deg],
        config.refine_spacing_m,
    )


def _tracked(
    photos: Sequence[PhotoImage], start: CameraPose, context: TrackingContext
) -> tuple[int, float]:
    """Photos tracked or found again from `start`, and their median inliers; 0 if tracking fails."""
    try:
        result = track(photos, start, context)
    except TrackingError:
        return 0, 0.0
    located = [
        photo.inliers
        for photo in result.photos
        if photo.status in {PhotoStatus.TRACKED, PhotoStatus.RELOCALISED}
    ]
    return len(located), float(median(located)) if located else 0.0


def _accepted(hypothesis: Hypothesis, config: FirstFixConfig) -> bool:
    """Localised, and tracked through enough photos (all of them when fewer were given)."""
    needed = min(config.min_tracked_photos, hypothesis.photos_verified)
    return hypothesis.pose is not None and hypothesis.photos_tracked >= needed


def _run_start(
    run: _Run, images: Sequence[PhotoImage], store_scene: StoreScene, config: FirstFixConfig
) -> RunStart:
    """The first event: the store's frame and bounds, the priors, the photos and the grid plan.

    Level 1 is planned without the fused frames' heading margin, which is not known yet, and
    level 2 as the most positions the coarse places can bring.
    """
    bounds, scene = store_scene.bounds, store_scene.scene
    longitude, latitude, _ = ecef_to_geodetic().transform(*scene.area.origin_ecef)
    coarse = level_one(config, bounds, scene.ground_height, config.priors, 0.0)
    fine = level_two(config, bounds, scene.ground_height, config.priors, [])
    fine_positions = planned_fine_positions(config)
    return RunStart(
        time_s=run.seconds(),
        origin_latitude_deg=latitude,
        origin_longitude_deg=longitude,
        bounds=Bounds(
            east_min_m=bounds.west_m,
            east_max_m=bounds.east_m,
            north_min_m=bounds.south_m,
            north_max_m=bounds.north_m,
        ),
        priors=config.priors,
        photos=[image.name for image in images],
        levels=[
            GridLevel(
                level=coarse.level,
                spacing_m=coarse.spacing_m,
                positions=len(coarse.positions),
                views=coarse.view_count,
            ),
            GridLevel(
                level=fine.level,
                spacing_m=fine.spacing_m,
                positions=fine_positions,
                views=fine_positions * fine.views_per_position,
            ),
        ],
    )


def _candidate(rank: int, place: Place, frame_similarities: list[float | None]) -> Candidate:
    return Candidate(
        rank=rank,
        east_m=place.east,
        north_m=place.north,
        height_m=place.height,
        heading_deg=place.heading,
        pitch_deg=place.pitch,
        similarity=place.similarity,
        frame_similarities=frame_similarities,
    )


def _fusion_event(
    run: _Run, frames: Sequence[PhotoImage], offsets: Sequence[float], config: FirstFixConfig
) -> FusionWindow:
    return FusionWindow(
        time_s=run.seconds(),
        frames=[
            FusionFrame(photo=frame.name, yaw_offset_deg=offset, lattice_offset_deg=lattice)
            for frame, offset, lattice in zip(
                frames,
                offsets,
                lattice_offsets_deg(offsets, config.heading_step_deg),
                strict=True,
            )
        ],
    )


def _relaxed_event(run: _Run, relaxation: Relaxation) -> PriorRelaxed:
    return PriorRelaxed(
        time_s=run.seconds(),
        prior=relaxation.prior,
        half_width_before=relaxation.half_width_before,
        half_width_after=relaxation.half_width_after,
    )


def _fix_event(run: _Run, found: _Found, store_scene: StoreScene) -> Fix:
    """The winner's pose; height is above the ground, as in the candidates."""
    scene = store_scene.scene
    centre, _ = camera_centre_and_rotation(found.pose, scene.area)
    ground = scene.ground_height(float(centre[0]), float(centre[1]))
    return Fix(
        time_s=run.seconds(),
        east_m=float(centre[0]),
        north_m=float(centre[1]),
        height_m=float(centre[2]) - ground,
        heading_deg=found.pose.heading_deg,
        pitch_deg=found.pose.pitch_deg,
        inliers=found.winner.first_photo_inliers,
    )
