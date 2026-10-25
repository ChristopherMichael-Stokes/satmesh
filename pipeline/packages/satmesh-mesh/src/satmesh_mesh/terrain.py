"""Adaptive triangulation of a DTM with pydelatin."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from pydelatin import Delatin

from satmesh_core import Aoi

# Under the EA LIDAR Composite's quoted 15 cm RMSE, so the TIN adds less error than the source
# carries
DEFAULT_MAX_ERROR_M = 0.1


@dataclass(frozen=True)
class Tin:
    """Triangulated terrain: `vertices` (n, 3) as (easting, northing, height) metres in `box.crs`.

    Vertices sit on DTM pixel centres inside `box`, the DTM's full extent. `error_m` is the largest
    vertical gap between the TIN and the DTM pixels.
    """

    vertices: np.ndarray
    triangles: np.ndarray
    box: Aoi
    error_m: float


def triangulate(dtm_path: Path, max_error_m: float = DEFAULT_MAX_ERROR_M) -> Tin:
    """Triangulate a north-up, gap-free DTM so no pixel is over `max_error_m` off the surface."""
    with rasterio.open(dtm_path) as src:
        t = src.transform
        if t.b != 0 or t.d != 0 or t.e >= 0:
            msg = f"DTM is not north-up: {t}"
            raise ValueError(msg)
        heights = src.read(1, masked=True)
        box = Aoi(
            crs=src.crs.to_string(),
            west=src.bounds.left,
            south=src.bounds.bottom,
            east=src.bounds.right,
            north=src.bounds.top,
        )
    if np.ma.count_masked(heights):
        msg = f"DTM has {np.ma.count_masked(heights)} nodata pixels"
        raise ValueError(msg)
    tin = Delatin(heights.filled().astype(np.float64), max_error=max_error_m)
    col, rows_up = tin.vertices[:, 0], tin.vertices[:, 1]
    # pydelatin counts y up from the bottom row of the array
    row = heights.shape[0] - 1 - rows_up
    easting = t.c + t.a * (col + 0.5)
    northing = t.f + t.e * (row + 0.5)
    vertices = np.column_stack([easting, northing, tin.vertices[:, 2]])
    return Tin(vertices, tin.triangles.astype(np.uint32), box, float(tin.error))
