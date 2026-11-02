"""The rendered views of the two search levels, built only over the set the priors allow.

A level is a product grid: positions on a square lattice over the ground, and at each the same
heights above ground, pitches and headings. Views are ordered position by position, then height,
pitch and heading, so the views of one position are contiguous and heading is the fastest axis.

Lattices start half a fine spacing in from the store's south-west corner (as the Bexhill grids
did), so level 1 positions are level 2 positions too when the spacings divide.

Fusion (level 1): a candidate view at heading h scores the sum over the frames of a window of
frame i's similarity to the view at the same position, height and pitch and heading
h + o_i, with o_i frame i's heading offset from frame 0 rounded to the heading lattice. A view
that was not rendered (outside the heading window) scores `MISSING_VIEW_SCORE`. The sum is the
sequence score of SeqSLAM (Milford and Wyeth, ICRA 2012) with the heading offsets in place of
time alignment; summing rotation-compensated render similarities is this project's own.
"""

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import NamedTuple

import numpy as np
import numpy.typing as npt

from satmesh_eval.perspective import GroundExtent
from satmesh_locate.events import Interval, PositionPrior, Priors
from satmesh_locate.places import Cells, Place
from satmesh_track.priors import FULL_CIRCLE_DEG, FirstFixConfig
from satmesh_track.search import GroundHeight

# a view missing one frame (at most 4 - 9 = -5) ranks below every complete view (at least -5) for
# windows of up to five frames: similarities are cosines in [-1, 1]
MISSING_VIEW_SCORE = -9.0
HEADING_KEY_DECIMALS = 6  # headings are lattice multiples; rounding absorbs float noise in sums
COARSE_LEVEL, FINE_LEVEL = 1, 2


class Position(NamedTuple):
    """A searched position in store ENU metres and the ground height there."""

    east_m: float
    north_m: float
    ground_m: float


class View(NamedTuple):
    """One rendered view: its position, height above ground (m), pitch and heading (degrees)."""

    position: Position
    height_m: float
    pitch_deg: float
    heading_deg: float


@dataclass(frozen=True)
class LevelGrid:
    """The views of one level: every position at every height, pitch and heading."""

    level: int
    spacing_m: float
    positions: tuple[Position, ...]
    heights_m: tuple[float, ...]
    pitches_deg: tuple[float, ...]
    headings_deg: tuple[float, ...]

    @property
    def views_per_position(self) -> int:
        """Views rendered at each position."""
        return len(self.heights_m) * len(self.pitches_deg) * len(self.headings_deg)

    @property
    def view_count(self) -> int:
        """Views of the whole level."""
        return len(self.positions) * self.views_per_position

    def views_at(self, position: Position) -> Iterator[View]:
        """The views of one position in grid order."""
        for height in self.heights_m:
            for pitch in self.pitches_deg:
                for heading in self.headings_deg:
                    yield View(position, height, pitch, heading)

    def cells(self) -> Cells:
        """Every view's pose as arrays in grid order, for `satmesh_locate.places.top_places`."""
        rows = np.array(
            [
                (
                    view.position.east_m,
                    view.position.north_m,
                    view.position.ground_m,
                    view.height_m,
                    view.heading_deg,
                    view.pitch_deg,
                )
                for position in self.positions
                for view in self.views_at(position)
            ],
            dtype=np.float64,
        ).reshape(-1, 6)
        return Cells(*(rows[:, column] for column in range(6)))


def angle_difference_deg(first_deg: float, second_deg: float) -> float:
    """The unsigned angle between two headings, 0 to 180 degrees."""
    return abs((first_deg - second_deg + 180.0) % FULL_CIRCLE_DEG - 180.0)


def heading_lattice(
    step_deg: float, window: Interval | None, margin_deg: float
) -> tuple[float, ...]:
    """Lattice headings every `step_deg` within `window` widened by `margin_deg`."""
    lattice = [step_deg * index for index in range(round(FULL_CIRCLE_DEG / step_deg))]
    return headings_in_window(lattice, window, margin_deg)


def headings_in_window(
    headings_deg: Sequence[float], window: Interval | None, margin_deg: float = 0.0
) -> tuple[float, ...]:
    """The headings within `window` widened by `margin_deg`; all of them without a window.

    A window narrower than the lattice keeps the heading nearest its centre.
    """
    if window is None:
        return tuple(headings_deg)
    inside = tuple(
        heading
        for heading in headings_deg
        if angle_difference_deg(heading, window.centre) <= window.half_width + margin_deg
    )
    return inside or (min(headings_deg, key=lambda h: angle_difference_deg(h, window.centre)),)


def values_in_window(values: Sequence[float], window: Interval | None) -> tuple[float, ...]:
    """The values inside `window`, or the one nearest its centre if none is; all without one."""
    if window is None:
        return tuple(values)
    inside = tuple(v for v in values if abs(v - window.centre) <= window.half_width)
    return inside or (min(values, key=lambda v: abs(v - window.centre)),)


def coarse_heights_m(
    heights_m: Sequence[float], height_prior: Interval | None
) -> tuple[float, ...]:
    """Level 1 heights: raised together when the prior's lower end is above the lowest of them.

    Retrieval preferred renders at 90 to 110 m even for photos at 51 to 74 m, so a height prior
    never lowers them.
    """
    if height_prior is None:
        return tuple(heights_m)
    raise_by = max(0.0, height_prior.centre - height_prior.half_width - min(heights_m))
    return tuple(height + raise_by for height in heights_m)


def lattice_points(
    bounds: GroundExtent, spacing_m: float, inset_m: float
) -> Iterator[tuple[float, float]]:
    """East-north points every `spacing_m` from `inset_m` inside the south-west corner."""
    for east in np.arange(bounds.west_m + inset_m, bounds.east_m, spacing_m):
        for north in np.arange(bounds.south_m + inset_m, bounds.north_m, spacing_m):
            yield float(east), float(north)


def in_scene(
    points: Iterator[tuple[float, float]], ground_height: GroundHeight
) -> tuple[Position, ...]:
    """The points the scene covers, with their ground height."""
    positions = []
    for east, north in points:
        try:
            ground = ground_height(east, north)
        except ValueError:
            continue
        positions.append(Position(east, north, ground))
    return tuple(positions)


def within_circle(point: tuple[float, float], prior: PositionPrior | None, margin_m: float) -> bool:
    """Whether the point lies within the prior's circle widened by `margin_m` (always, if none)."""
    if prior is None:
        return True
    return (
        math.hypot(point[0] - prior.east_m, point[1] - prior.north_m) <= prior.radius_m + margin_m
    )


def level_one(
    config: FirstFixConfig,
    bounds: GroundExtent,
    ground_height: GroundHeight,
    priors: Priors,
    heading_margin_deg: float,
) -> LevelGrid:
    """The coarse views: the lattice within the position prior plus one spacing, every pitch.

    Headings cover the heading prior widened by `heading_margin_deg`, the largest heading offset
    of a fused frame, so every frame of the window finds its view.
    """
    points = (
        point
        for point in lattice_points(bounds, config.coarse_spacing_m, config.fine_spacing_m / 2)
        if within_circle(point, priors.position, config.coarse_spacing_m)
    )
    return LevelGrid(
        COARSE_LEVEL,
        config.coarse_spacing_m,
        in_scene(points, ground_height),
        coarse_heights_m(config.coarse_heights_m, priors.height_m),
        config.coarse_pitches_deg,
        heading_lattice(config.heading_step_deg, priors.heading_deg, heading_margin_deg),
    )


def level_two(
    config: FirstFixConfig,
    bounds: GroundExtent,
    ground_height: GroundHeight,
    priors: Priors,
    places: Sequence[Place],
) -> LevelGrid:
    """The fine views: the fine lattice within `fine_radius_m` of a coarse place."""
    points = (
        point
        for point in lattice_points(bounds, config.fine_spacing_m, config.fine_spacing_m / 2)
        if any(
            math.hypot(point[0] - place.east, point[1] - place.north) <= config.fine_radius_m
            for place in places
        )
    )
    return LevelGrid(
        FINE_LEVEL,
        config.fine_spacing_m,
        in_scene(points, ground_height),
        values_in_window(config.fine_heights_m, priors.height_m),
        values_in_window(config.fine_pitches_deg, priors.pitch_deg),
        heading_lattice(config.heading_step_deg, priors.heading_deg, 0.0),
    )


def planned_fine_positions(config: FirstFixConfig) -> int:
    """Most level 2 positions: the lattice points within the fine radius of each coarse place."""
    steps = int(config.fine_radius_m // config.fine_spacing_m)
    offsets = config.fine_spacing_m * np.arange(-steps, steps + 1)
    east, north = np.meshgrid(offsets, offsets)
    return config.coarse_places * int(
        np.count_nonzero(np.hypot(east, north) <= config.fine_radius_m)
    )


def lattice_offsets_deg(offsets_deg: Sequence[float], step_deg: float) -> tuple[float, ...]:
    """Heading offsets rounded to the heading lattice."""
    return tuple(step_deg * round(offset / step_deg) for offset in offsets_deg)


def _heading_key(heading_deg: float) -> float:
    return round(heading_deg % FULL_CIRCLE_DEG, HEADING_KEY_DECIMALS)


def fused_scores(
    similarity: npt.NDArray[np.float32],
    headings_deg: Sequence[float],
    lattice_offsets: Sequence[float],
) -> npt.NDArray[np.float64]:
    """Each view's fused score over the frames of a window.

    `similarity` holds one row per frame and one column per view of whole positions in grid
    order; `lattice_offsets` are the frames' heading offsets from frame 0 on the heading lattice.
    """
    by_heading = similarity.reshape(len(similarity), -1, len(headings_deg))
    column = {_heading_key(heading): index for index, heading in enumerate(headings_deg)}
    total = np.zeros(by_heading.shape[1:], dtype=np.float64)
    for frame, offset in enumerate(lattice_offsets):
        for index, heading in enumerate(headings_deg):
            source = column.get(_heading_key(heading + offset))
            total[:, index] += (
                MISSING_VIEW_SCORE if source is None else by_heading[frame, :, source]
            )
    return total.reshape(-1)


def view_index(cells: Cells, place: Place) -> int:
    """The grid-order index of the view a place was ranked from.

    A place's pose values are copies of the grid's, so they compare equal exactly.
    """
    match = (
        (cells.east == place.east)
        & (cells.north == place.north)
        & (cells.height == place.height)
        & (cells.heading == place.heading)
        & (cells.pitch == place.pitch)
    )
    return int(np.flatnonzero(match)[0])


def frame_similarities(
    similarity: npt.NDArray[np.float32],
    headings_deg: Sequence[float],
    lattice_offsets: Sequence[float],
    view: int,
) -> list[float | None]:
    """Each frame's similarity to the view it contributes to the fused score of grid view `view`.

    `similarity` holds one row per frame and one column per view, as for `fused_scores`.
    """
    count = len(headings_deg)
    position_start, heading_index = view - view % count, view % count
    column = {_heading_key(heading): index for index, heading in enumerate(headings_deg)}
    sources = [
        column.get(_heading_key(headings_deg[heading_index] + offset)) for offset in lattice_offsets
    ]
    return [
        None if source is None else float(similarity[frame, position_start + source])
        for frame, source in enumerate(sources)
    ]


def candidate_mask(grid: LevelGrid, heading_prior: Interval | None) -> npt.NDArray[np.bool_]:
    """Views that may be the first photo's: those whose heading lies in the prior's window.

    Level 1 renders a wider window for the fused frames; frame 0's view stays within the prior.
    """
    allowed = np.isin(grid.headings_deg, headings_in_window(grid.headings_deg, heading_prior))
    return np.tile(allowed, len(grid.positions) * len(grid.heights_m) * len(grid.pitches_deg))
