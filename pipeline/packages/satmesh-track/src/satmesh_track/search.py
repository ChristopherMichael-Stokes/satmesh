"""Local search for a camera pose: render a grid of poses around a centre and keep the best match.

Used to re-localise after a lost track (centre = the last fix, radius growing with the missed
steps) and to start a track when the first photo's rough position is given. Candidates are poses on
a horizontal grid, at several heights above the ground and in evenly spaced headings. The photo is
matched against the render at each; the best few by match count go on to the normal solve.

The grid spacing follows the basin of the solve: a render pose up to 50 m off always localised for
cameras at 25 m and above, and the worst offset on a square grid is spacing x 0.71, so 70 m spacing
keeps every pose inside the basin (`photo-only-p0-results.md`).
"""

from collections import deque
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from satmesh_core import EnuFrame
from satmesh_eval.camera import CameraPose, Intrinsics, pose_from_enu
from satmesh_eval.matching import Matcher, Matches, match_against, supports_concurrent_calls
from satmesh_eval.references import Renderer

GroundHeight = Callable[
    [float, float], float
]  # area-ENU east, north -> ground height; ValueError outside


@dataclass(frozen=True)
class SearchConfig:
    """Grid and ranking settings of the local search."""

    spacing_m: float = 70.0
    margin_m: float = 60.0
    radius_per_missed_step: float = 1.2  # times the typical step between fixes
    height_factors: tuple[float, ...] = (0.7, 1.0, 1.4)  # times the last height above ground
    min_height_above_ground_m: float = 25.0  # cameras below this are out of scope
    heading_count: int = 8
    top_k: int = 5
    ranking_workers: int = 3  # candidates matched at once; renders stay on the calling thread


def search_radius_m(config: SearchConfig, step_m: float, missed_steps: int) -> float:
    """How far the camera may have moved: a margin plus the missed steps at the typical step."""
    return config.margin_m + config.radius_per_missed_step * step_m * missed_steps


def candidate_poses(  # noqa: PLR0913, PLR0917 (config, frame, ground, centre, radius, heights, pitch)
    config: SearchConfig,
    area: EnuFrame,
    ground_height: GroundHeight,
    centre_east_north: npt.NDArray[np.float64],
    radius_m: float,
    heights_above_ground_m: Sequence[float],
    pitch_deg: float,
) -> list[CameraPose]:
    """Poses on a grid, centred on `centre_east_north`, inside the circle of `radius_m`."""
    steps_out = int(radius_m // config.spacing_m)
    offsets = config.spacing_m * np.arange(-steps_out, steps_out + 1)
    headings = np.arange(config.heading_count) * 360.0 / config.heading_count
    poses = []
    for east_offset in offsets:
        for north_offset in offsets:
            if np.hypot(east_offset, north_offset) > radius_m:
                continue
            east = centre_east_north[0] + east_offset
            north = centre_east_north[1] + north_offset
            try:
                ground = ground_height(float(east), float(north))
            except ValueError:  # outside the store
                continue
            for height in heights_above_ground_m:
                centre = np.array(
                    [east, north, ground + max(config.min_height_above_ground_m, height)]
                )
                poses.extend(
                    pose_from_enu(area, centre, float(h), pitch_deg, 0.0) for h in headings
                )
    return poses


def best_candidates(  # noqa: PLR0913, PLR0917 (photo, candidates, render, matcher, camera and range)
    config: SearchConfig,
    photo: npt.NDArray[np.uint8],
    candidates: Sequence[CameraPose],
    render: Renderer,
    matcher: Matcher,
    intrinsics: Intrinsics,
    max_range_m: float,
) -> list[CameraPose]:
    """The `top_k` candidates whose renders share the most matches with the photo."""
    match_photo = match_against(matcher, photo)
    renders = (render(intrinsics, pose, max_range_m).rgb for pose in candidates)
    workers = config.ranking_workers if supports_concurrent_calls(matcher) else 1
    counts = _match_counts(match_photo, renders, workers)
    order = np.argsort(counts)[::-1][: config.top_k]
    return [candidates[i] for i in order]


def _match_counts(
    match_photo: Callable[[npt.NDArray[np.uint8]], Matches],
    renders: Iterable[npt.NDArray[np.uint8]],
    workers: int,
) -> list[int]:
    """Match counts of `renders` in order.

    Up to `workers` matches run at once (ONNX Runtime and OpenCV release the GIL); at most
    2 x `workers` renders are held at a time. One worker runs inline.
    """
    if workers == 1:  # on the calling thread: a GPU matcher's context belongs to it
        return [len(match_photo(image)) for image in renders]
    in_flight: deque[Future[int]] = deque()
    counts: list[int] = []
    with ThreadPoolExecutor(workers) as pool:
        for image in renders:
            in_flight.append(pool.submit(lambda image=image: len(match_photo(image))))
            if len(in_flight) >= 2 * workers:
                counts.append(in_flight.popleft().result())
        counts.extend(future.result() for future in in_flight)
    return counts
