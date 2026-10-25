"""Adaptive triangulation of a height grid with pydelatin."""

from dataclasses import dataclass

import numpy as np
from pydelatin import Delatin

# Under the EA LIDAR Composite's quoted 15 cm RMSE, so the TIN adds less error than the source
# carries
DEFAULT_MAX_ERROR_M = 0.1


@dataclass(frozen=True)
class GridTin:
    """Triangulated height grid: vertices sit on grid nodes.

    `columns` and `rows` index the grid, with row 0 the top (north) row. `error_m` is the largest
    vertical gap between the TIN and the grid heights.
    """

    columns: np.ndarray
    rows: np.ndarray
    heights: np.ndarray
    triangles: np.ndarray
    error_m: float


def triangulate_heights(heights: np.ndarray, max_error_m: float = DEFAULT_MAX_ERROR_M) -> GridTin:
    """Triangulate a gap-free `(rows, cols)` grid so no node is over `max_error_m` off the TIN."""
    if not np.isfinite(heights).all():
        msg = "height grid has non-finite values"
        raise ValueError(msg)
    tin = Delatin(heights.astype(np.float64), max_error=max_error_m)
    columns = tin.vertices[:, 0].astype(np.int64)
    # pydelatin counts y up from the bottom row of the array
    rows = heights.shape[0] - 1 - tin.vertices[:, 1].astype(np.int64)
    return GridTin(
        columns, rows, tin.vertices[:, 2], tin.triangles.astype(np.uint32), float(tin.error)
    )
