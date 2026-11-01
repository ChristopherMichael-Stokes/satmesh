"""Rendered view cells and the ranking of places by descriptor similarity.

A directory of cells holds `meta.npy`, one row per rendered view with the columns `east`, `north`,
`ground`, `height`, `heading`, `pitch` (store ENU metres, height above ground in metres, degrees),
and the renders in `renders_NNN.npy` chunks, 322 x 322 RGB `uint8`, in the same row order.
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

META_FILE = "meta.npy"
RENDER_GLOB = "renders_*.npy"
META_COLUMNS = 6


@dataclass(frozen=True)
class Cells:
    """Camera poses of the rendered views, one array element per view."""

    east: npt.NDArray[np.float64]
    north: npt.NDArray[np.float64]
    ground: npt.NDArray[np.float64]
    height: npt.NDArray[np.float64]
    heading: npt.NDArray[np.float64]
    pitch: npt.NDArray[np.float64]


@dataclass(frozen=True)
class Place:
    """The best view of one place: its pose in ENU metres and degrees and its similarity."""

    east: float
    north: float
    ground: float
    height: float
    heading: float
    pitch: float
    similarity: float


def load_cells(directory: Path) -> Cells:
    """Read `meta.npy` of a render directory.

    Raises:
        ValueError: the file does not have the six columns.
    """
    meta = np.load(directory / META_FILE)
    if meta.ndim != 2 or meta.shape[1] != META_COLUMNS:  # noqa: PLR2004
        message = f"{directory / META_FILE} must have {META_COLUMNS} columns, got {meta.shape}"
        raise ValueError(message)
    return Cells(*(meta[:, column] for column in range(META_COLUMNS)))


def iter_render_chunks(directory: Path) -> Iterator[Sequence[npt.NDArray[np.uint8]]]:
    """The render chunks of a directory in file-name order, each a sequence of images."""
    for path in sorted(directory.glob(RENDER_GLOB)):
        yield np.unstack(np.load(path))


def top_places(
    similarity: npt.NDArray[np.float32], cells: Cells, count: int, separation_m: float
) -> list[Place]:
    """Greedy non-maximum suppression: best views more than `separation_m` apart.

    Views are taken in order of falling similarity; a view within `separation_m` of a place
    already chosen is skipped. Fewer than `count` places come back when the cells run out.
    """
    chosen: list[int] = []
    for index in np.argsort(-similarity):
        distances = np.hypot(
            cells.east[chosen] - cells.east[index], cells.north[chosen] - cells.north[index]
        )
        if np.all(distances > separation_m):
            chosen.append(int(index))
        if len(chosen) == count:
            break
    return [
        Place(
            east=float(cells.east[i]),
            north=float(cells.north[i]),
            ground=float(cells.ground[i]),
            height=float(cells.height[i]),
            heading=float(cells.heading[i]),
            pitch=float(cells.pitch[i]),
            similarity=float(similarity[i]),
        )
        for i in chosen
    ]
