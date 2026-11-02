import math
import os
from collections import Counter
from pathlib import Path
from typing import override

import numpy as np
import pytest
import scene

from satmesh_eval.camera import camera_centre_and_rotation
from satmesh_eval.matching import Matches, onnx_matcher
from satmesh_eval.perspective import GroundExtent, render
from satmesh_locate.events import (
    Candidates,
    CellBatch,
    Event,
    EventWriter,
    FusionWindow,
    Interval,
    PositionPrior,
    PriorRelaxed,
    Priors,
    RunEnd,
    RunStart,
    StageEnd,
    StageStart,
    VerificationResult,
    VerificationStart,
    read_events,
)
from satmesh_locate.megaloc import DESCRIPTOR_SIZE, MegaLocDescriber
from satmesh_track.first_fix import first_fix, widened_search
from satmesh_track.priors import NO_PRIORS, FirstFixConfig
from satmesh_track.store_scene import StoreScene
from satmesh_track.tracker import (
    PRIOR_PULL_MAX_M,
    PhotoImage,
    Scene,
    TrackingContext,
    TrackingError,
)

MEGALOC_VARIABLE, XFEAT_VARIABLE = "MEGALOC_MODEL", "XFEAT_MODEL_DIR"
TOWN_BOUNDS = GroundExtent(-150.0, 150.0, -150.0, 150.0)
# the start must lie in the basin `track` pulls in from; solved at the nominal focal it is biased
START_TOLERANCE_M = PRIOR_PULL_MAX_M
STORE_BOUNDS = GroundExtent(-500.0, 500.0, -300.0, 300.0)
ALL_PRIORS = Priors(
    position=PositionPrior(east_m=100.0, north_m=0.0, radius_m=200.0),
    heading_deg=Interval(centre=30.0, half_width=45.0),
    pitch_deg=Interval(centre=-35.0, half_width=10.0),
    height_m=Interval(centre=60.0, half_width=20.0),
)
# small renders and one refinement pose keep the synthetic run to seconds on the CPU
TINY_RUN = FirstFixConfig(
    fusion_frames=2,
    fusion_frame_step=1,
    heading_step_deg=90.0,
    render_width_px=64,
    render_height_px=48,
    coarse_heights_m=(90.0,),
    coarse_places=2,
    fine_radius_m=100.0,
    fine_heights_m=(40.0, 90.0),
    final_places=2,
    refine_radius_m=0.0,
    refine_height_factors=(1.0,),
    refine_pitch_offsets_deg=(0.0,),
    refine_heading_offsets_deg=(0.0,),
)


class CountingDescriber(MegaLocDescriber):
    """Describes an image by its mean colour channels, repeated; counts the images it sees."""

    def __init__(self) -> None:
        self.seen = 0

    @override
    def describe(self, images):
        self.seen += len(images)
        rows = np.array(
            [
                np.resize(np.asarray(i, dtype=np.float32).mean(axis=(0, 1)), DESCRIPTOR_SIZE)
                for i in images
            ]
        ).reshape(-1, DESCRIPTOR_SIZE)
        return rows / np.maximum(np.linalg.norm(rows, axis=1, keepdims=True), 1e-12)  # sky only


def no_matches(_image_a, _image_b) -> Matches:
    return Matches(np.zeros((0, 2)), np.zeros((0, 2)))


def town_store() -> StoreScene:
    def renderer(intrinsics, pose, max_range_m):
        return render(scene.town(), intrinsics, pose, max_range_m)

    return StoreScene(Scene(renderer, scene.area_frame(), scene.ground_height), TOWN_BOUNDS, "town")


def test_the_ladder_relaxes_heading_then_pitch_then_area_until_a_search_succeeds() -> None:
    searched: list[Priors] = []
    relaxed = []

    def search(priors: Priors) -> str | None:
        searched.append(priors)
        return "found" if priors.position is None else None

    found, final = widened_search(ALL_PRIORS, STORE_BOUNDS, search, relaxed.append)

    assert found == "found"
    assert [r.prior for r in relaxed] == ["heading", "pitch", "area"]
    assert [(p.heading_deg, p.pitch_deg, p.position) for p in searched] == [
        (ALL_PRIORS.heading_deg, ALL_PRIORS.pitch_deg, ALL_PRIORS.position),
        (None, ALL_PRIORS.pitch_deg, ALL_PRIORS.position),
        (None, None, ALL_PRIORS.position),
        (None, None, None),
    ]
    assert final == searched[-1]
    assert final.height_m == ALL_PRIORS.height_m  # height is never relaxed
    assert [(r.half_width_before, r.half_width_after) for r in relaxed] == [
        (45.0, 180.0),
        (10.0, 90.0),
        (200.0, math.hypot(-500.0 - 100.0, 300.0)),  # the farthest corner from the circle's centre
    ]


def test_the_ladder_stops_at_the_first_search_that_succeeds() -> None:
    relaxed = []

    found, final = widened_search(
        ALL_PRIORS, STORE_BOUNDS, lambda p: 1 if p.heading_deg is None else None, relaxed.append
    )

    assert found == 1
    assert [r.prior for r in relaxed] == ["heading"]
    assert final.pitch_deg == ALL_PRIORS.pitch_deg


def test_the_ladder_skips_priors_that_are_not_set_and_names_what_it_tried() -> None:
    relaxed = []
    only_pitch = NO_PRIORS.model_copy(update={"pitch_deg": Interval(centre=-35.0, half_width=5.0)})

    with pytest.raises(TrackingError, match="relaxed in turn: pitch"):
        widened_search(only_pitch, STORE_BOUNDS, lambda _: None, relaxed.append)

    assert [r.prior for r in relaxed] == ["pitch"]


def test_a_run_that_finds_nothing_writes_a_coherent_event_stream(tmp_path: Path) -> None:
    photos = [
        PhotoImage(f"f{index}.png", scene.photograph(scene.pose_at(-20.0, -60.0, 10.0 * index)))
        for index in range(2)
    ]
    priors = NO_PRIORS.model_copy(
        update={
            "heading_deg": Interval(centre=30.0, half_width=45.0),
            "pitch_deg": Interval(centre=-35.0, half_width=10.0),
        }
    )
    config = TINY_RUN.model_copy(update={"priors": priors})
    store = town_store()
    path = tmp_path / "events.jsonl"

    with EventWriter(path) as writer, pytest.raises(TrackingError):
        first_fix(
            photos,
            store,
            CountingDescriber(),
            TrackingContext(store.scene, no_matches),
            config=config,
            emit=writer.write,
        )

    events = list(read_events(path))
    assert isinstance(events[0], RunStart)
    assert events[0].priors == priors
    assert events[0].photos == ["f0.png", "f1.png"]
    assert isinstance(events[-1], RunEnd)
    assert not events[-1].ok
    times = [event.time_s for event in events]
    assert times == sorted(times)
    open_stages = []
    for event in events:
        if isinstance(event, StageStart):
            assert not open_stages  # stages do not nest
            open_stages.append(event.stage)
        elif isinstance(event, StageEnd):
            assert open_stages.pop() == event.stage
    assert not open_stages
    assert [e.prior for e in events if isinstance(e, PriorRelaxed)] == ["heading", "pitch"]
    # three searches (as given, heading relaxed, pitch relaxed), each verifying its final places
    final_places = [e.places for e in events if isinstance(e, Candidates) and e.level == 2]
    assert len(final_places) == 3
    verified = [e for e in events if isinstance(e, VerificationResult)]
    assert [e.rank for e in verified] == [p.rank for places in final_places for p in places]
    assert [e.rank for e in events if isinstance(e, VerificationStart)] == [
        e.rank for e in verified
    ]
    assert not any(e.accepted for e in verified)
    # each position of the first level 1 pass is rendered, then described, once
    first_pass = events[
        : next(
            i
            for i, e in enumerate(events)
            if isinstance(e, StageEnd) and e.stage == "level 1: rank"
        )
    ]
    states = Counter(
        (cell.state, cell.east_m, cell.north_m)
        for event in first_pass
        if isinstance(event, CellBatch)
        for cell in event.cells
    )
    planned = events[0].levels[0].positions
    assert sum(1 for state, _, _ in states if state == "rendered") == planned
    assert sum(1 for state, _, _ in states if state == "described") == planned
    assert set(states.values()) == {1}
    windows = [e for e in events if isinstance(e, FusionWindow)]
    assert len(windows) == 1  # the same offsets serve every pass
    assert windows[0].frames[0].photo == "f0.png"
    assert windows[0].frames[0].yaw_offset_deg == 0.0
    coarse = next(e for e in events if isinstance(e, Candidates) and e.level == 1)
    for place in coarse.places:
        assert place.frame_similarities is not None
        assert len(place.frame_similarities) == len(windows[0].frames)
        assert sum(t for t in place.frame_similarities if t is not None) == pytest.approx(
            place.similarity, abs=1e-5
        )


SCREEN_MIN_MATCHES = 28
FULL_REFINEMENT_VIEWS = 3  # one position and heading, three heights
SCREENING_VIEWS = 1  # the place's own height


def verification_results(matcher, config: FirstFixConfig) -> list[VerificationResult]:
    photos = [
        PhotoImage(f"f{index}.png", scene.photograph(scene.pose_at(-20.0, -60.0, 10.0 * index)))
        for index in range(2)
    ]
    store = town_store()
    events: list[Event] = []
    with pytest.raises(TrackingError):
        first_fix(
            photos,
            store,
            CountingDescriber(),
            TrackingContext(store.scene, matcher),
            config=config,
            emit=events.append,
        )
    return [e for e in events if isinstance(e, VerificationResult)]


def test_a_place_whose_screening_poses_match_too_few_features_is_dropped_after_screening() -> None:
    config = TINY_RUN.model_copy(
        update={
            "refine_height_factors": (0.7, 1.0, 1.3),
            "refine_screen_min_matches": SCREEN_MIN_MATCHES,
        }
    )

    results = verification_results(no_matches, config)

    assert results
    assert {e.refine_views for e in results} == {SCREENING_VIEWS}
    assert not any(e.accepted for e in results)


def test_a_place_that_passes_screening_is_refined_in_full() -> None:
    def many_matches(_image_a, _image_b) -> Matches:
        return Matches(np.zeros((SCREEN_MIN_MATCHES, 2)), np.zeros((SCREEN_MIN_MATCHES, 2)))

    config = TINY_RUN.model_copy(
        update={
            "refine_height_factors": (0.7, 1.0, 1.3),
            "refine_screen_min_matches": SCREEN_MIN_MATCHES,
        }
    )

    results = verification_results(many_matches, config)

    assert results
    assert {e.refine_views for e in results} == {FULL_REFINEMENT_VIEWS}


@pytest.mark.skipif(
    MEGALOC_VARIABLE not in os.environ or XFEAT_VARIABLE not in os.environ,
    reason=f"{MEGALOC_VARIABLE} and {XFEAT_VARIABLE} not set",
)
def test_the_first_photo_is_localised_within_the_priors() -> None:
    describer = MegaLocDescriber(Path(os.environ[MEGALOC_VARIABLE]))
    matcher = onnx_matcher(Path(os.environ[XFEAT_VARIABLE]))
    truth = scene.pose_at(-20.0, -60.0, 0.0)
    photo = PhotoImage("first.png", scene.photograph(truth))
    store = town_store()
    priors = Priors(
        position=None,
        heading_deg=Interval(centre=0.0, half_width=15.0),
        pitch_deg=Interval(centre=-35.0, half_width=5.0),
        height_m=Interval(centre=40.0, half_width=5.0),
    )
    config = TINY_RUN.model_copy(
        update={
            "priors": priors,
            "heading_step_deg": 30.0,
            "render_width_px": 160,
            "render_height_px": 90,
            "fine_radius_m": 250.0,
            "final_places": 6,
            # five positions a 70 m step apart: from places 100 m apart they reach every point
            "refine_radius_m": 70.0,
            "refine_spacing_m": 70.0,
        }
    )

    fix = first_fix([photo], store, describer, TrackingContext(store.scene, matcher), config=config)

    centre, _ = camera_centre_and_rotation(fix.pose, scene.area_frame())
    truth_centre, _ = camera_centre_and_rotation(truth, scene.area_frame())
    assert np.linalg.norm(centre - truth_centre) < START_TOLERANCE_M
