import math

import numpy as np
import pytest

from satmesh_eval.perspective import GroundExtent
from satmesh_locate.events import Interval, PositionPrior, Priors
from satmesh_locate.places import Cells, Place
from satmesh_track.grid import (
    MISSING_VIEW_SCORE,
    LevelGrid,
    Position,
    candidate_mask,
    coarse_heights_m,
    frame_similarities,
    fused_scores,
    heading_lattice,
    lattice_offsets_deg,
    level_one,
    level_two,
    values_in_window,
    view_index,
)
from satmesh_track.priors import NO_PRIORS, FirstFixConfig

BOUNDS = GroundExtent(0.0, 1000.0, 0.0, 600.0)
CONFIG = FirstFixConfig()
EDGE_EAST_M = 800.0


def ground(east: float, north: float) -> float:
    """Ground 5 m up, with no scene east of `EDGE_EAST_M`."""
    if east > EDGE_EAST_M:
        msg = "outside the scene"
        raise ValueError(msg)
    return 5.0 + 0.0 * north


def test_without_a_window_every_lattice_heading_is_searched() -> None:
    assert heading_lattice(30.0, None, 0.0) == tuple(30.0 * i for i in range(12))


def test_a_heading_window_keeps_the_headings_within_it_across_north() -> None:
    assert set(heading_lattice(30.0, Interval(centre=30.0, half_width=45.0), 0.0)) == {0, 30, 60}
    assert set(heading_lattice(30.0, Interval(centre=350.0, half_width=45.0), 0.0)) == {
        330,
        0,
        30,
    }


def test_the_heading_window_widens_by_the_margin() -> None:
    window = Interval(centre=350.0, half_width=45.0)

    assert set(heading_lattice(30.0, window, 20.0)) == {300, 330, 0, 30}


def test_a_window_narrower_than_the_lattice_keeps_the_nearest_heading() -> None:
    assert heading_lattice(30.0, Interval(centre=20.0, half_width=5.0), 0.0) == (30.0,)


def test_values_outside_a_window_give_way_to_the_nearest() -> None:
    heights = (40.0, 55.0, 72.0, 90.0, 110.0)

    assert values_in_window(heights, Interval(centre=60.0, half_width=10.0)) == (55.0,)
    assert values_in_window(heights, Interval(centre=80.0, half_width=20.0)) == (72.0, 90.0)
    assert values_in_window(heights, Interval(centre=200.0, half_width=10.0)) == (110.0,)
    assert values_in_window(heights, None) == heights


def test_a_height_prior_only_raises_the_coarse_heights() -> None:
    assert coarse_heights_m((90.0, 110.0), None) == (90.0, 110.0)
    assert coarse_heights_m((90.0, 110.0), Interval(centre=70.0, half_width=30.0)) == (90.0, 110.0)
    assert coarse_heights_m((90.0, 110.0), Interval(centre=150.0, half_width=20.0)) == (
        130.0,
        150.0,
    )


def test_level_one_covers_the_scene_on_the_coarse_lattice() -> None:
    grid = level_one(CONFIG, BOUNDS, ground, NO_PRIORS, 0.0)

    # 35 m in from the corner every 280 m: east 35, 315, 595 (875 is off the scene), north alike
    expected = {(e, n) for e in (35.0, 315.0, 595.0) for n in (35.0, 315.0, 595.0)}
    assert {(p.east_m, p.north_m) for p in grid.positions} == expected
    assert all(p.ground_m == 5.0 for p in grid.positions)
    assert grid.view_count == 9 * 2 * 2 * 12


def test_level_one_keeps_the_positions_within_one_spacing_of_the_position_prior() -> None:
    priors = NO_PRIORS.model_copy(
        update={"position": PositionPrior(east_m=315.0, north_m=315.0, radius_m=10.0)}
    )

    grid = level_one(CONFIG, BOUNDS, ground, priors, 0.0)

    expected = {(315.0, 315.0), (35.0, 315.0), (595.0, 315.0), (315.0, 35.0), (315.0, 595.0)}
    assert {(p.east_m, p.north_m) for p in grid.positions} == expected


def test_level_one_renders_the_heading_window_widened_for_the_fused_frames() -> None:
    priors = NO_PRIORS.model_copy(update={"heading_deg": Interval(centre=90.0, half_width=45.0)})

    grid = level_one(CONFIG, BOUNDS, ground, priors, 30.0)

    assert set(grid.headings_deg) == {30, 60, 90, 120, 150}
    assert grid.pitches_deg == CONFIG.coarse_pitches_deg  # pitch is not a window at level 1


def test_level_two_takes_the_fine_lattice_around_each_place_within_the_priors() -> None:
    place = Place(315.0, 315.0, 5.0, 90.0, 0.0, -35.0, 0.9)
    priors = Priors(
        position=None,
        heading_deg=Interval(centre=0.0, half_width=30.0),
        pitch_deg=Interval(centre=-50.0, half_width=5.0),
        height_m=Interval(centre=60.0, half_width=15.0),
    )

    grid = level_two(CONFIG, BOUNDS, ground, priors, [place])

    lattice = [(35.0 + 70.0 * i, 35.0 + 70.0 * j) for i in range(15) for j in range(9)]
    expected = {
        (e, n) for e, n in lattice if math.hypot(e - 315.0, n - 315.0) <= 250.0 and e <= EDGE_EAST_M
    }
    assert {(p.east_m, p.north_m) for p in grid.positions} == expected
    assert grid.heights_m == (55.0, 72.0)
    assert grid.pitches_deg == (-50.0,)
    assert set(grid.headings_deg) == {330, 0, 30}


def test_level_two_renders_the_headings_near_the_places_that_reach_each_position() -> None:
    config = CONFIG.model_copy(update={"fine_heading_steps": 1})
    north_place = Place(315.0, 315.0, 5.0, 90.0, 90.0, -35.0, 0.9)
    far_place = Place(35.0, 35.0, 5.0, 90.0, 270.0, -35.0, 0.8)

    grid = level_two(config, BOUNDS, ground, NO_PRIORS, [north_place, far_place])

    assert grid.rendered_headings is not None
    for position in grid.positions:
        near_north = math.hypot(position.east_m - 315.0, position.north_m - 315.0) <= 250.0
        near_far = math.hypot(position.east_m - 35.0, position.north_m - 35.0) <= 250.0
        expected = set()
        if near_north:
            expected |= {60.0, 90.0, 120.0}
        if near_far:
            expected |= {240.0, 270.0, 300.0}
        assert set(grid.rendered_headings[position]) == expected
    per_heading = len(grid.heights_m) * len(grid.pitches_deg)
    assert grid.render_count == per_heading * sum(len(h) for h in grid.rendered_headings.values())
    assert grid.render_count < grid.view_count


def test_render_flags_mark_the_views_at_the_rendered_headings_in_grid_order() -> None:
    config = CONFIG.model_copy(update={"fine_heading_steps": 0})
    place = Place(315.0, 315.0, 5.0, 90.0, 90.0, -35.0, 0.9)
    grid = level_two(config, BOUNDS, ground, NO_PRIORS, [place])
    position = grid.positions[0]

    flags = grid.render_flags(position)
    views = list(grid.views_at(position))

    assert len(flags) == len(views) == grid.views_per_position
    assert [v.heading_deg for v, flagged in zip(views, flags, strict=True) if flagged] == [90.0] * (
        len(grid.heights_m) * len(grid.pitches_deg)
    )


def test_without_a_step_limit_level_two_renders_every_view() -> None:
    place = Place(315.0, 315.0, 5.0, 90.0, 90.0, -35.0, 0.9)

    grid = level_two(CONFIG, BOUNDS, ground, NO_PRIORS, [place])

    assert grid.rendered_headings is None
    assert grid.render_count == grid.view_count
    assert all(
        grid.render_flags(position) == [True] * grid.views_per_position
        for position in grid.positions
    )


def test_offsets_round_to_the_heading_lattice() -> None:
    assert lattice_offsets_deg([0.0, 14.0, 16.0, -46.0], 30.0) == (0.0, 0.0, 30.0, -60.0)


def test_fused_scores_add_each_frame_at_its_offset_heading_wrapping_north() -> None:
    headings = (0.0, 90.0, 180.0, 270.0)
    similarity = np.array([[0.1, 0.2, 0.3, 0.4], [0.5, 0.6, 0.7, 0.8]], dtype=np.float32)

    scores = fused_scores(similarity, headings, (0.0, 90.0))

    # view at heading h: frame 0 at h plus frame 1 at h + 90
    assert scores == pytest.approx([0.1 + 0.6, 0.2 + 0.7, 0.3 + 0.8, 0.4 + 0.5])


def test_a_frame_whose_view_was_not_rendered_scores_the_missing_score() -> None:
    headings = (0.0, 90.0)
    similarity = np.array([[0.1, 0.2], [0.5, 0.6]], dtype=np.float32)

    scores = fused_scores(similarity, headings, (0.0, 90.0))

    assert scores == pytest.approx([0.1 + 0.6, 0.2 + MISSING_VIEW_SCORE])


def test_fused_scores_keep_positions_apart() -> None:
    headings = (0.0, 180.0)
    # two positions, two headings each; frame 1 turned 180 degrees
    similarity = np.array([[0.1, 0.2, 0.3, 0.4], [0.5, 0.6, 0.7, 0.8]], dtype=np.float32)

    scores = fused_scores(similarity, headings, (0.0, 180.0))

    assert scores == pytest.approx([0.1 + 0.6, 0.2 + 0.5, 0.3 + 0.8, 0.4 + 0.7])


def test_only_views_inside_the_heading_prior_are_candidates() -> None:
    grid = LevelGrid(
        1,
        280.0,
        (Position(0.0, 0.0, 0.0), Position(280.0, 0.0, 0.0)),
        (90.0, 110.0),
        (-35.0,),
        (0.0, 30.0, 60.0, 90.0),
    )

    mask = candidate_mask(grid, Interval(centre=15.0, half_width=20.0))

    assert mask.tolist() == [True, True, False, False] * 4
    assert candidate_mask(grid, None).all()


def test_frame_similarities_are_the_terms_of_the_fused_score_of_that_view() -> None:
    headings = (0.0, 180.0)
    similarity = np.array([[0.1, 0.2, 0.3, 0.4], [0.5, 0.6, 0.7, 0.8]], dtype=np.float32)
    offsets = (0.0, 180.0)
    fused = fused_scores(similarity, headings, offsets)

    terms = [frame_similarities(similarity, headings, offsets, view) for view in range(4)]

    assert terms[0] == pytest.approx([0.1, 0.6])  # frame 1 at heading 0 + 180, same position
    assert terms[3] == pytest.approx([0.4, 0.7])  # second position, heading 180 + 180 wraps to 0
    assert [math.fsum(x for x in t if x is not None) for t in terms] == pytest.approx(fused)


def test_a_frame_whose_view_was_not_rendered_has_no_similarity_term() -> None:
    similarity = np.array([[0.1, 0.2], [0.5, 0.6]], dtype=np.float32)

    assert frame_similarities(similarity, (0.0, 90.0), (0.0, 90.0), 1) == [
        pytest.approx(0.2),
        None,
    ]


def test_a_place_finds_the_grid_index_of_its_view() -> None:
    cells = Cells(
        east=np.array([0.0, 0.0, 70.0]),
        north=np.array([0.0, 0.0, 0.0]),
        ground=np.array([5.0, 5.0, 5.0]),
        height=np.array([90.0, 110.0, 90.0]),
        heading=np.array([0.0, 0.0, 0.0]),
        pitch=np.array([-35.0, -35.0, -35.0]),
    )

    place = Place(70.0, 0.0, 5.0, 90.0, 0.0, -35.0, 0.3)

    assert view_index(cells, place) == 2
