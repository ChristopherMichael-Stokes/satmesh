import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import pytest
import shapely
from pydantic import ValidationError

from satmesh_core import BRITISH_NATIONAL_GRID, Aoi
from satmesh_data import EsriScene, SceneId, SceneMap
from satmesh_eval.offset import ShiftField
from satmesh_eval.registration import (
    METHOD_RESIDUAL_M,
    CellMeasurement,
    StoreMeasurement,
)
from satmesh_eval.roofs import RoofOffset
from satmesh_eval.scene_lean import correction_field, fit_scene_lean
from satmesh_tiles import MAX_LEAN, CellCorrection, SceneLean

SCENE = SceneId(capture_date=date(2025, 7, 12), sensor="GE01")
OTHER_SCENE = SceneId(capture_date=date(2025, 4, 11), sensor="WV02")
CELL_SIDE_M = 1000.0
STORE_WEST_M, STORE_SOUTH_M = 587_000.0, 185_000.0
# 64 m windows every 32 m (`offset.py`): window j is centred 32 + 32 j m east of the west edge
WINDOW_STEP_M, FIRST_CENTRE_M = 32.0, 32.0
# east cell split between the centres of its window columns 14 and 15
SCENE_SPLIT_OFFSET_M = 500.0
FEW_BOOTSTRAP_DRAWS = 200
WINDOW_GRID = (30, 30)
ROOF_NOISE_M = 0.3
WINDOW_NOISE_M = 0.5
# standard errors of the fitted values, taken this many times, bound the recovery error
STANDARD_ERRORS = 4.0
# lean2 (`fits.py`, an independent scratch implementation, 2026-10-29): the observations of its
# Southend and Ferrybridge truth boxes, and its F2 fit of them (full precision from its JSON)
LEAN2 = json.loads((Path(__file__).parent / "data" / "lean2-observations.json").read_text())
LEAN2_F2 = {
    "southend_t": (
        0.5371165165098216,
        2.228811608597317,
        -0.20406515505124312,
        -0.3470712574904383,
    ),
    "ferry_t": (
        -0.5666176979130685,
        0.45940200464947556,
        -0.015760034096548227,
        0.14524564681031815,
    ),
}
# EA aerial photography against Esri over the same 1 km boxes (`e2b-results.md`)
TRUTH = {"southend_t": (0.23, 1.57), "ferry_t": (-0.31, 0.71)}
# least_squares stops at a relative cost change of 1e-8; the parameters agree to well inside this
SOLVER_TOLERANCE = 1e-4


def roofs_for(
    t: tuple[float, float],
    lean: tuple[float, float],
    heights: np.ndarray,
    seed: int,
    noise_m: float = ROOF_NOISE_M,
) -> list[RoofOffset]:
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, noise_m, (len(heights), 2))
    return [
        RoofOffset(0.0, 0.0, h, t[0] + lean[0] * h + ne, t[1] + lean[1] * h + nn, 0.5)
        for h, (ne, nn) in zip(heights.tolist(), noise.tolist(), strict=True)
    ]


def ground_for(t: tuple[float, float], windows: int, seed: int) -> ShiftField:
    rng = np.random.default_rng(seed)
    east, north = np.full(WINDOW_GRID, np.nan), np.full(WINDOW_GRID, np.nan)
    cells = rng.choice(east.size, windows, replace=False)
    east.flat[cells] = t[0] + rng.normal(0, WINDOW_NOISE_M, windows)
    north.flat[cells] = t[1] + rng.normal(0, WINDOW_NOISE_M, windows)
    return ShiftField(east, north, np.full(WINDOW_GRID, np.nan))


def lean2_inputs(box: str) -> tuple[list[RoofOffset], ShiftField]:
    observed = LEAN2[box]
    roofs = [
        RoofOffset(0.0, 0.0, r["eave_height_m"], r["east_m"], r["north_m"], r["peak"])
        for r in observed["roofs"]
    ]
    east, north = np.full(observed["window_grid"], np.nan), np.full(observed["window_grid"], np.nan)
    for w in observed["windows"]:
        east[w["row"], w["col"]], north[w["row"], w["col"]] = w["east_m"], w["north_m"]
    return roofs, ShiftField(east, north, np.full(east.shape, np.nan))


def test_known_shift_and_lean_are_recovered_within_their_standard_errors() -> None:
    t, lean = (0.4, -1.2), (-0.2, -0.35)
    heights = np.linspace(3, 20, 40)
    result = fit_scene_lean(SCENE, roofs_for(t, lean, heights, 1), ground_for(t, 120, 2))

    assert result.status == "applied"
    assert result.fit is not None
    fit = result.fit
    # ordinary least squares on h: se(l) = s / sqrt(S_hh), se(t) = s sqrt(1/n + mean(h)^2 / S_hh)
    s_hh = float(((heights - heights.mean()) ** 2).sum())
    se_lean = ROOF_NOISE_M / math.sqrt(s_hh)
    se_t = ROOF_NOISE_M * math.sqrt(1 / len(heights) + heights.mean() ** 2 / s_hh)
    assert (fit.lean_east, fit.lean_north) == pytest.approx(lean, abs=STANDARD_ERRORS * se_lean)
    assert (fit.t_east_m, fit.t_north_m) == pytest.approx(t, abs=STANDARD_ERRORS * se_t)
    assert fit.k == pytest.approx(math.hypot(*lean), abs=STANDARD_ERRORS * se_lean)
    assert fit.azimuth_deg == pytest.approx(math.degrees(math.atan2(*lean)) % 360, abs=2.0)
    assert fit.t_east_interval_m[0] < t[0] < fit.t_east_interval_m[1]
    assert fit.t_north_interval_m[0] < t[1] < fit.t_north_interval_m[1]
    assert fit.k_interval[0] < math.hypot(*lean) < fit.k_interval[1]
    assert not fit.at_cap
    assert (result.roof_count, result.window_count) == (40, 120)
    half_east = max(
        fit.t_east_m - fit.t_east_interval_m[0], fit.t_east_interval_m[1] - fit.t_east_m
    )
    half_north = max(
        fit.t_north_m - fit.t_north_interval_m[0], fit.t_north_interval_m[1] - fit.t_north_m
    )
    assert fit.ground_error_bound_m == pytest.approx(
        math.hypot(half_east, half_north, METHOD_RESIDUAL_M)
    )


def test_a_lean_past_the_off_nadir_cap_is_fitted_on_the_cap() -> None:
    # due south, so by symmetry the capped optimum keeps the true direction
    t, lean = (0.0, 0.5), (0.0, -0.8)
    heights = np.linspace(3, 20, 40)
    result = fit_scene_lean(SCENE, roofs_for(t, lean, heights, 3), ground_for(t, 120, 4))

    assert result.fit is not None
    fit = result.fit
    se_lean = ROOF_NOISE_M / math.sqrt(float(((heights - heights.mean()) ** 2).sum()))
    assert fit.at_cap
    assert fit.k == pytest.approx(MAX_LEAN)
    assert math.hypot(fit.lean_east, fit.lean_north) == pytest.approx(MAX_LEAN)
    assert fit.azimuth_deg == pytest.approx(
        180.0, abs=math.degrees(STANDARD_ERRORS * se_lean / MAX_LEAN)
    )
    assert fit.k_interval[1] <= MAX_LEAN + SOLVER_TOLERANCE


@pytest.mark.parametrize(
    ("roof_count", "windows", "heights", "reason"),
    [
        (9, 120, (3.0, 20.0), "9 roofs"),
        (40, 5, (3.0, 20.0), "5 ground windows"),
        (40, 120, (6.0, 6.0), "same eave height"),
    ],
)
def test_scenes_without_enough_evidence_are_rejected_without_a_fit(
    roof_count: int, windows: int, heights: tuple[float, float], reason: str
) -> None:
    t, lean = (0.4, -1.2), (-0.2, -0.35)
    roofs = roofs_for(t, lean, np.linspace(*heights, roof_count), 5)

    result = fit_scene_lean(SCENE, roofs, ground_for(t, windows, 6))

    assert result.status == "rejected"
    assert result.reason is not None
    assert reason in result.reason
    assert result.fit is None


def test_a_lean_the_roofs_cannot_measure_is_rejected_with_its_fit() -> None:
    # Ferrybridge-like: 20 roofs over 3.4 to 6.7 m that scatter 2.5 m about the model
    t, lean = (0.4, -1.2), (-0.2, -0.35)
    roofs = roofs_for(t, lean, np.linspace(3.4, 6.7, 20), 8, noise_m=2.5)

    result = fit_scene_lean(SCENE, roofs, ground_for(t, 60, 8))

    assert result.status == "rejected"
    assert result.reason is not None
    assert "lean not measured" in result.reason
    assert result.fit is not None


@pytest.mark.parametrize("box", ["southend_t", "ferry_t"])
def test_lean2_truth_boxes_give_the_lean2_f2_fit(box: str) -> None:
    roofs, ground = lean2_inputs(box)

    result = fit_scene_lean(SCENE, roofs, ground)

    assert result.fit is not None
    fit = result.fit
    fitted = (fit.t_east_m, fit.t_north_m, fit.lean_east, fit.lean_north)
    assert fitted == pytest.approx(LEAN2_F2[box], abs=SOLVER_TOLERANCE)
    # lean2's verdict: F2 is within 0.8 m of the aerial truth at both boxes (0.73 and 0.36 m)
    assert math.dist(fitted[:2], TRUTH[box]) < 0.8


def test_lean2_ferrybridge_lean_is_rejected_and_southend_applied() -> None:
    statuses = {box: fit_scene_lean(SCENE, *lean2_inputs(box)).status for box in LEAN2}

    # Ferrybridge roofs span 3.4 to 6.7 m: k from 0.04 to the cap, azimuth undetermined
    assert statuses == {"southend_t": "applied", "ferry_t": "rejected"}


def test_an_applied_lean_must_carry_a_fit() -> None:
    with pytest.raises(ValidationError, match="applied lean has a fit"):
        SceneLean(
            scene=SCENE, status="applied", reason=None, fit=None, roof_count=0, window_count=0
        )


def cell_measurement(
    west_m: float, t: tuple[float, float], roofs: list[RoofOffset], seed: int
) -> CellMeasurement:
    box = Aoi(
        crs=BRITISH_NATIONAL_GRID,
        west=west_m,
        south=STORE_SOUTH_M,
        east=west_m + CELL_SIDE_M,
        north=STORE_SOUTH_M + CELL_SIDE_M,
    )
    rng = np.random.default_rng(seed)
    east = t[0] + rng.normal(0, WINDOW_NOISE_M, WINDOW_GRID)
    north = t[1] + rng.normal(0, WINDOW_NOISE_M, WINDOW_GRID)
    correction = CellCorrection(
        west_m=box.west,
        south_m=box.south,
        east_m=box.east,
        north_m=box.north,
        status="corrected",
        displacement_east_m=t[0],
        displacement_north_m=t[1],
        error_bound_m=0.5,
        windows_used=east.size,
        windows_total=east.size,
    )
    windows = ShiftField(east, north, np.ones(WINDOW_GRID))
    return CellMeasurement(box, correction, windows, tuple(roofs))


def placed(roofs: list[RoofOffset], west_m: float) -> list[RoofOffset]:
    """The roofs spread along a row of the cell whose west edge is `west_m`, 40 m apart."""
    return [
        RoofOffset(
            west_m + 20 + 40 * i, STORE_SOUTH_M + 500, r.eave_height_m, r.east_m, r.north_m, r.peak
        )
        for i, r in enumerate(roofs)
    ]


def two_cell_store() -> tuple[StoreMeasurement, SceneMap, float]:
    t, lean = (0.4, 1.6), (-0.2, -0.35)
    heights = np.linspace(3, 20, 14)
    roofs = roofs_for(t, lean, heights, seed=4)
    east_west_m = STORE_WEST_M + CELL_SIDE_M
    split_m = east_west_m + SCENE_SPLIT_OFFSET_M
    west_cell = cell_measurement(STORE_WEST_M, t, placed(roofs[:8], STORE_WEST_M), seed=5)
    # six roofs west of the split, in the first scene, and three east of it
    east_roofs = placed(roofs[8:], east_west_m) + [
        RoofOffset(split_m + 100 + 40 * i, STORE_SOUTH_M + 500, 6.0, 0.0, 0.0, 0.5)
        for i in range(3)
    ]
    east_cell = cell_measurement(east_west_m, t, east_roofs, seed=6)
    scenes = SceneMap(
        BRITISH_NATIONAL_GRID,
        19,
        "test release",
        (
            EsriScene(
                SCENE, 0.3, 1.0, (1,), shapely.MultiPolygon([shapely.box(0, 0, split_m, 1e6)])
            ),
            EsriScene(
                OTHER_SCENE,
                0.5,
                1.0,
                (2,),
                shapely.MultiPolygon([shapely.box(split_m, 0, 1e6, 1e6)]),
            ),
        ),
    )
    return StoreMeasurement(2.8, (west_cell, east_cell)), scenes, split_m


def test_store_measurements_are_pooled_per_scene_across_cells() -> None:
    measurement, scenes, split_m = two_cell_store()

    field = correction_field(measurement, scenes, lambda *_: None, draws=FEW_BOOTSTRAP_DRAWS)

    first, second = field.scenes
    rows, cols = WINDOW_GRID
    east_cell_west = STORE_WEST_M + CELL_SIDE_M
    centres = east_cell_west + FIRST_CENTRE_M + WINDOW_STEP_M * np.arange(cols)
    east_cell_columns_in_first = int((centres < split_m).sum())
    assert (first.scene, first.status, first.roof_count) == (SCENE, "applied", 14)
    assert first.window_count == rows * cols + rows * east_cell_columns_in_first
    assert first.fit is not None
    assert (first.fit.t_east_m, first.fit.t_north_m) == pytest.approx((0.4, 1.6), abs=0.3)
    assert (second.scene, second.status, second.roof_count) == (OTHER_SCENE, "rejected", 3)
    assert second.window_count == rows * (cols - east_cell_columns_in_first)
    assert second.reason == "3 roofs, fewer than 10"
    assert field.scene_release == "test release"
    assert field.cells == tuple(cell.correction for cell in measurement.cells)


def test_without_a_scene_map_no_lean_is_measured() -> None:
    measurement, _, _ = two_cell_store()
    field = correction_field(measurement, None, lambda *_: None)
    assert (field.scene_release, field.scenes) == (None, ())
