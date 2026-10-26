"""Esri imagery position from lidar intensity: displacement per square cell, with an error bound.

Per rectangular cell of British National Grid, the gradient of EA lidar intensity is the
reference and the gradient of the Esri luma is registered to it by windowed phase correlation
(`offset.py`). The displacement is applied only where enough windows give a reliable shift. The
thresholds and bounds below come from eight England sites where the same procedure was scored
against the EA aerial photography (`agent-docs/e2-results.md`).
"""

import logging
import math
import multiprocessing
import os
import time
from concurrent.futures import (
    FIRST_COMPLETED,
    Future,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    as_completed,
    wait,
)
from itertools import pairwise
from pathlib import Path

import httpx
import numpy as np

from satmesh_core import BRITISH_NATIONAL_GRID, Aoi, ProgressReport
from satmesh_data import (
    EsriClient,
    Raster,
    fetch_point_cloud,
    find_point_cloud_tiles,
)
from satmesh_eval.imagery import esri_raster_over
from satmesh_eval.lidar_reference import (
    gradient_magnitude_u8,
    intensity_gradient_image,
    read_first_return_intensity,
)
from satmesh_eval.offset import (
    GRID_M,
    WINDOW_PX,
    OffsetEstimate,
    luminance_on_grid,
    measure_offset,
)
from satmesh_tiles import CellCorrection, CorrectionField

logger = logging.getLogger(__name__)

LIDAR_PHASE = "downloading lidar"
READ_PHASE = "reading points"
MATCH_PHASE = "matching cells"

# a cell is a share of the area close to this side, between 0.5 and 1.5 times it; the eight survey
# sites were scored over 0.5 to 1 km squares
TARGET_CELL_SIDE_M = 1000
# Reliable windows as a share of all windows in the cell. At eight sites the cells that agreed with
# the EA aerial offset to 0.3 m on both axes had 6.7 % or more (Ferrybridge, Upper Aire) and the
# cells that did not had 3.4 % or fewer, with nothing between; 5 % sits in that gap (tunable).
MIN_RELIABLE_FRACTION = 0.05
# fewer windows than this cannot give a bootstrap interval worth trusting
MIN_RELIABLE_WINDOWS = 20
# The largest error of a corrected cell against the EA aerial at eight sites was 0.38 m
# (Snettisham, east 0.04 and north 0.38); the interval below covers only window sampling.
METHOD_RESIDUAL_M = 0.4
# The largest displacement of the Esri imagery from the EA aerial over eight England sites:
# 2.78 m north at Snettisham on a 500 m slice. Cells left uncorrected carry it as their bound.
UNCORRECTED_ERROR_BOUND_M = 2.8
# lidar points beyond the cell that the interpolation needs at its edges
REFERENCE_MARGIN_M = 20.0
# a cell narrower than three windows has too few for a stable median
MIN_CELL_SIDE_PX = 3 * WINDOW_PX
# A worker holds about 2 GB for a 0.8 km2 cell (lidar triangulation, 0.25 m grids): 12 such cells
# on 8 workers peaked at 17.6 GB in all. The cap keeps a many-core machine within memory (tunable).
MAX_CELL_WORKERS = 8


def cell_correction(
    box: Aoi, reference_gradient: np.ndarray, esri_gradient: np.ndarray
) -> CellCorrection:
    """Register the Esri gradient image to the lidar one over a cell and decide whether to trust it.

    The bound is the 95 % radial sum, in quadrature, of the bootstrap half-widths of the east and
    north medians and `METHOD_RESIDUAL_M`. An unreliable cell is uncorrected and bounded by
    `UNCORRECTED_ERROR_BOUND_M`.
    """
    try:
        estimate, _ = measure_offset(reference_gradient, esri_gradient)
    except ValueError:
        return _uncorrected(box, 0, 0)
    if (
        estimate.windows_used < MIN_RELIABLE_WINDOWS
        or estimate.windows_used / estimate.windows_total < MIN_RELIABLE_FRACTION
    ):
        return _uncorrected(box, estimate.windows_used, estimate.windows_total)
    return CellCorrection(
        west_m=box.west,
        south_m=box.south,
        east_m=box.east,
        north_m=box.north,
        status="corrected",
        displacement_east_m=estimate.east_m,
        displacement_north_m=estimate.north_m,
        error_bound_m=_error_bound(estimate),
        windows_used=estimate.windows_used,
        windows_total=estimate.windows_total,
    )


def measure_correction(  # noqa: PLR0913, PLR0917 (area, zoom, three clients and directories, hook)
    area: Aoi,
    zoom: int,
    esri: EsriClient,
    http: httpx.Client,
    cache_dir: Path,
    report: ProgressReport,
) -> CorrectionField:
    """Measure the Esri displacement over a BNG `area` in 1 km cells, fetching what it needs.

    Cells are clipped to `area`. Lidar point clouds are fetched once per 5 km square (cached) and
    the Esri tiles at `zoom` are those the store already holds. `report` is called for the phases
    "downloading lidar" (per square), "reading points" and "matching cells" (per cell).
    """
    if area.crs != BRITISH_NATIONAL_GRID:
        msg = f"the correction is measured in {BRITISH_NATIONAL_GRID}, got {area.crs}"
        raise ValueError(msg)
    squares = find_point_cloud_tiles(http, area)
    report(LIDAR_PHASE, 0, len(squares))
    laz = {}
    for done, (tile_id, captures) in enumerate(squares.items(), start=1):
        started = time.perf_counter()
        laz[tile_id] = fetch_point_cloud(http, captures, cache_dir)
        logger.info("lidar square %s ready in %.1f s", tile_id, time.perf_counter() - started)
        report(LIDAR_PHASE, done, len(squares))
    laz_paths = [path for paths in laz.values() for path in paths]
    boxes = cell_boxes(area)
    measurable = [box for box in boxes if _measurable(box)]
    report(READ_PHASE, 0, 1)
    started = time.perf_counter()
    points = read_first_return_intensity(laz_paths, measurable, REFERENCE_MARGIN_M)
    logger.info(
        "read %d lidar files for %d cells in %.1f s",
        len(laz_paths),
        len(measurable),
        time.perf_counter() - started,
    )
    report(READ_PHASE, 1, 1)
    measured = iter(_measure_cells(measurable, points, zoom, esri, report))
    cells = [next(measured) if _measurable(box) else _uncorrected(box, 0, 0) for box in boxes]
    return CorrectionField(
        uncorrected_error_bound_m=UNCORRECTED_ERROR_BOUND_M,
        cells=tuple(cells),
    )


def _measurable(box: Aoi) -> bool:
    return min(box.east - box.west, box.north - box.south) / GRID_M >= MIN_CELL_SIDE_PX


def _measure_cells(
    boxes: list[Aoi],
    points: list[tuple[np.ndarray, np.ndarray]],
    zoom: int,
    esri: EsriClient,
    report: ProgressReport,
) -> list[CellCorrection]:
    """Measure each cell in a worker process and return the results in the order of `boxes`.

    Esri tiles are fetched here because the client's request schedule lives in this process; at
    most one cell per worker is in flight, which bounds the memory held by queued cells.
    """
    if not boxes:
        return []
    report(MATCH_PHASE, 0, len(boxes))
    workers = min(MAX_CELL_WORKERS, os.process_cpu_count() or 1, len(boxes))
    futures: list[Future[CellCorrection]] = []
    running: set[Future[CellCorrection]] = set()
    finished = 0

    def note(done_futures: set[Future[CellCorrection]]) -> None:
        nonlocal finished
        for future in done_futures:
            _log_cell(boxes[futures.index(future)], future.result())
            finished += 1
            report(MATCH_PHASE, finished, len(boxes))

    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(workers, mp_context=context) as pool:
        for box, (xy, intensity) in zip(boxes, points, strict=True):
            if len(running) >= workers:
                done_futures, running = wait(running, return_when=FIRST_COMPLETED)
                note(done_futures)
            future = pool.submit(
                _measure_cell, box, xy, intensity, esri_raster_over(esri, box, zoom)
            )
            futures.append(future)
            running.add(future)
        for future in as_completed(running):
            note({future})
    return [future.result() for future in futures]


def _log_cell(box: Aoi, cell: CellCorrection) -> None:
    logger.info(
        "cell E %.0f N %.0f: %s, %d of %d windows, shift %+.2f E %+.2f N m, bound %.2f m",
        box.west,
        box.south,
        cell.status,
        cell.windows_used,
        cell.windows_total,
        cell.displacement_east_m,
        cell.displacement_north_m,
        cell.error_bound_m,
    )


def _measure_cell(
    box: Aoi, xy: np.ndarray, intensity: np.ndarray, esri_raster: Raster
) -> CellCorrection:
    # the lidar triangulation and the Esri resampling are independent and both release the GIL
    with ThreadPoolExecutor(2) as pool:
        reference = pool.submit(intensity_gradient_image, xy, intensity, box)
        esri_gradient = pool.submit(
            lambda: gradient_magnitude_u8(luminance_on_grid(esri_raster, box))
        )
        return cell_correction(box, reference.result(), esri_gradient.result())


def cell_boxes(area: Aoi) -> list[Aoi]:
    """Split `area` into near-equal rectangular cells with sides close to `TARGET_CELL_SIDE_M`.

    Each side is cut into the whole number of parts nearest to its length over the target, so a
    cell is never a sliver and the cells tile the area exactly.
    """
    edges_e = np.linspace(area.west, area.east, _parts(area.east - area.west) + 1)
    edges_n = np.linspace(area.south, area.north, _parts(area.north - area.south) + 1)
    return [
        Aoi(
            crs=BRITISH_NATIONAL_GRID,
            west=float(west),
            south=float(south),
            east=float(east),
            north=float(north),
        )
        for west, east in pairwise(edges_e)
        for south, north in pairwise(edges_n)
    ]


def _parts(length_m: float) -> int:
    return max(1, round(length_m / TARGET_CELL_SIDE_M))


def _error_bound(estimate: OffsetEstimate) -> float:
    half_east = max(
        estimate.east_m - estimate.east_interval_m[0], estimate.east_interval_m[1] - estimate.east_m
    )
    half_north = max(
        estimate.north_m - estimate.north_interval_m[0],
        estimate.north_interval_m[1] - estimate.north_m,
    )
    return math.hypot(half_east, half_north, METHOD_RESIDUAL_M)


def _uncorrected(box: Aoi, used: int, total: int) -> CellCorrection:
    return CellCorrection(
        west_m=box.west,
        south_m=box.south,
        east_m=box.east,
        north_m=box.north,
        status="uncorrected",
        displacement_east_m=0.0,
        displacement_north_m=0.0,
        error_bound_m=UNCORRECTED_ERROR_BOUND_M,
        windows_used=used,
        windows_total=total,
    )
