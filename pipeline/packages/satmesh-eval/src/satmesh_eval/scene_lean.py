"""Ground shift and lean of one Esri scene, from roof offsets anchored by ground registration.

A satellite scene orthorectified onto a bare-earth DEM leaves a point at height h above the ground
displaced by

    d(h) = t + l h,

with t = (t_E, t_N) the ground shift in metres and l = (l_E, l_N) the lean in metres per metre of
height (the 3D affine projection of Fraser and Yamakawa, applied per scene as in Parmehr, Fraser,
Zhang and Leach 2013, ISPRS Annals II-5/W2). Positive values put the Esri image east and north
of the ground; the corrected image is out(p) = Esri(p + t + l h(p)). k = |l| is the tangent of the
off-nadir angle, which the Maxar basemap specification caps at 30 degrees, so k <= tan 30.

`correction_field` pools a store's measurements per scene: every accepted roof, labelled by the
scene at its bounding-box centre, and every reliable registration window, labelled at its centre,
across all cells, then fits each scene once.

The fit minimises a soft-L1 loss (`scipy.optimize.least_squares`, `f_scale` `ROBUST_SCALE_M`) of
the roof residuals o_i - t - l h_i over accepted roofs (`roofs.py`, h the eave height), plus one
pseudo-observation per axis (t - t0) / s * `ROBUST_SCALE_M`, where t0 is the median ground
registration shift of the scene's reliable windows and s the block-bootstrap standard deviation of
that median combined in quadrature with `METHOD_RESIDUAL_M`. Roofs alone extrapolate t to h = 0
from a 3 to 7 m height span and miss by up to 5 m (lean2 F0 at Ferrybridge); the prior is what
pins t. The cost is convex in (t, l) (soft-L1 is convex in each residual, the residuals affine),
so the constrained minimum is the unconstrained one when it has k <= tan 30 and otherwise lies on
the circle k = tan 30, which is then fitted with the azimuth free.

95 % intervals come from a bootstrap that resamples roofs and, independently, blocks of
`BOOTSTRAP_BLOCK_WINDOWS` x `BOOTSTRAP_BLOCK_WINDOWS` ground windows (which moves t0); every draw is
refitted with the cap.

A scene is rejected, and keeps the per-cell ground shift, when:

- fewer than `MIN_ROOFS` roofs were accepted (Brighton gave 5 and 2: no fit);
- fewer than `MIN_GROUND_WINDOWS` reliable ground windows fall in the scene, so there is no prior
  on t and the roofs-only fit is unusable;
- every roof has the same eave height, or the fit does not converge;
- the lean is not measured: 95 % of the bootstrap leans lie within `lean_radius_95` of the fitted
  one, and that radius exceeds `MAX_LEAN_RADIUS_95`. The radius bounds the lean's share of the
  correction error, `lean_radius_95` * h at height h, in any direction.
"""

import logging
import math
from collections.abc import Callable, Sequence

import numpy as np
from scipy.optimize import least_squares
from scipy.stats import norm

from satmesh_core import BRITISH_NATIONAL_GRID, ProgressReport
from satmesh_data import UNLABELLED, SceneId, SceneMap
from satmesh_eval.heights import (
    DEFAULT_BOOTSTRAP_DRAWS,
    DEFAULT_CONFIDENCE,
    block_bootstrap_interval,
)
from satmesh_eval.offset import (
    BOOTSTRAP_BLOCK_WINDOWS,
    GRID_M,
    WINDOW_PX,
    WINDOW_STEP_PX,
    ShiftField,
)
from satmesh_eval.registration import METHOD_RESIDUAL_M, CellMeasurement, StoreMeasurement
from satmesh_eval.roofs import RoofOffset
from satmesh_tiles import MAX_LEAN, CorrectionField, LeanFit, SceneLean

logger = logging.getLogger(__name__)

FIT_PHASE = "fitting scene leans"

# residual size where soft-L1 turns from quadratic to linear: roof offsets scatter about 0.6 to
# 1 m around a good fit (lean2 roof residuals), false matches several metres
ROBUST_SCALE_M = 1.0
# lean2 fits ran with 13 to 23 roofs; below 10 the bootstrap has too few distinct roofs (tunable)
MIN_ROOFS = 10
# the smallest working prior in lean2 had 13 windows (Southend); a block bootstrap of fewer has
# one or two blocks (tunable)
MIN_GROUND_WINDOWS = 10
# half the physical range of k; lean2 radii: Southend 0.17 and 0.24 (two boxes of one scene),
# Ferrybridge 0.62 with its azimuth interval spanning 355 degrees (tunable)
MAX_LEAN_RADIUS_95 = MAX_LEAN / 2
LEAN_RADIUS_PERCENTILE = 95.0
DEGREES_PER_TURN = 360.0


def fit_scene_lean(
    scene: SceneId,
    roofs: Sequence[RoofOffset],
    ground: ShiftField,
    *,
    draws: int = DEFAULT_BOOTSTRAP_DRAWS,
    seed: int = 0,
) -> SceneLean:
    """Fit t and l of `scene` from its `roofs` and its reliable ground windows `ground`.

    `ground` is a registration shift field on its window grid with NaN wherever a window is
    unreliable or outside the scene.
    """
    in_scene = np.isfinite(ground.east_m) & np.isfinite(ground.north_m)
    counts = {"roof_count": len(roofs), "window_count": int(in_scene.sum())}
    heights = np.array([r.eave_height_m for r in roofs])
    if (gap := _evidence_gap(heights, counts["window_count"])) is not None:
        return _rejected(scene, gap, counts)
    offsets = np.array([[r.east_m, r.north_m] for r in roofs])
    prior_sd = _prior_sd(ground)
    prior = (float(np.nanmedian(ground.east_m)), float(np.nanmedian(ground.north_m)), *prior_sd)
    params, converged = _capped_fit(heights, offsets, prior, np.zeros(4))
    if not converged:
        return _rejected(scene, "the robust fit did not converge", counts)
    draws_fitted = _bootstrap(heights, offsets, ground, prior_sd, params, draws=draws, seed=seed)
    if len(draws_fitted) == 0:
        return _rejected(scene, "no bootstrap draw could be fitted", counts)
    fit = _summary(params, draws_fitted, heights, offsets)
    if fit.lean_radius_95 > MAX_LEAN_RADIUS_95:
        reason = (
            f"lean not measured: 95 % radius {fit.lean_radius_95:.2f} m per m, "
            f"above {MAX_LEAN_RADIUS_95:.2f}"
        )
        return SceneLean(scene=scene, status="rejected", reason=reason, fit=fit, **counts)
    return SceneLean(scene=scene, status="applied", reason=None, fit=fit, **counts)


def correction_field(
    measurement: StoreMeasurement,
    scene_map: SceneMap | None,
    report: ProgressReport,
    *,
    draws: int = DEFAULT_BOOTSTRAP_DRAWS,
) -> CorrectionField:
    """Return the store's correction: its cells, and one fitted lean per scene of `scene_map`.

    `scene_map` is in BNG; None leaves the lean unmeasured (no scenes). `report` is called with
    phase "fitting scene leans" before the first scene and after each.
    """
    cells = tuple(cell.correction for cell in measurement.cells)
    if scene_map is None:
        return CorrectionField(
            uncorrected_error_bound_m=measurement.uncorrected_error_bound_m,
            cells=cells,
            scene_release=None,
            scenes=(),
        )
    if scene_map.crs != BRITISH_NATIONAL_GRID:
        msg = f"scenes are pooled in {BRITISH_NATIONAL_GRID}, got {scene_map.crs}"
        raise ValueError(msg)
    roofs = [roof for cell in measurement.cells for roof in cell.roofs]
    roof_labels = scene_map.labels_at(
        np.array([r.easting_m for r in roofs]), np.array([r.northing_m for r in roofs])
    )
    windows, window_labels = _pooled_windows(measurement.cells, scene_map)
    report(FIT_PHASE, 0, len(scene_map.scenes))
    leans = []
    for index, scene in enumerate(scene_map.scenes):
        outside = window_labels != index
        lean = fit_scene_lean(
            scene.scene_id,
            [r for r, label in zip(roofs, roof_labels.tolist(), strict=True) if label == index],
            ShiftField(
                np.where(outside, np.nan, windows.east_m),
                np.where(outside, np.nan, windows.north_m),
                np.where(outside, np.nan, windows.response),
            ),
            draws=draws,
        )
        _log_lean(lean)
        leans.append(lean)
        report(FIT_PHASE, index + 1, len(scene_map.scenes))
    return CorrectionField(
        uncorrected_error_bound_m=measurement.uncorrected_error_bound_m,
        cells=cells,
        scene_release=scene_map.release,
        scenes=tuple(leans),
    )


def _pooled_windows(
    cells: Sequence[CellMeasurement], scene_map: SceneMap
) -> tuple[ShiftField, np.ndarray]:
    """Return every cell's windows on one grid, cells in their places, and each window's scene.

    Cell window grids differ by a window at most; shorter ones are padded with NaN, so a bootstrap
    block stays among neighbouring windows.
    """
    measured = [(cell.box, cell.windows) for cell in cells if cell.windows is not None]
    wests = sorted({box.west for box, _ in measured})
    norths = sorted({box.north for box, _ in measured}, reverse=True)
    rows = max((windows.east_m.shape[0] for _, windows in measured), default=0)
    cols = max((windows.east_m.shape[1] for _, windows in measured), default=0)
    shape = (rows * len(norths), cols * len(wests))
    east, north, response = (np.full(shape, np.nan) for _ in range(3))
    labels = np.full(shape, UNLABELLED, dtype=np.int32)
    for box, windows in measured:
        r0, c0 = norths.index(box.north) * rows, wests.index(box.west) * cols
        h, w = windows.east_m.shape
        place = (slice(r0, r0 + h), slice(c0, c0 + w))
        east[place], north[place], response[place] = (
            windows.east_m,
            windows.north_m,
            windows.response,
        )
        centre_offset_m = (np.arange(max(h, w)) * WINDOW_STEP_PX + WINDOW_PX / 2) * GRID_M
        centre_e, centre_n = np.meshgrid(
            box.west + centre_offset_m[:w], box.north - centre_offset_m[:h]
        )
        labels[place] = scene_map.labels_at(centre_e, centre_n)
    return ShiftField(east, north, response), labels


def _log_lean(lean: SceneLean) -> None:
    if lean.fit is None:
        logger.info(
            "scene %s: %s, %d roofs, %d windows: %s",
            lean.scene,
            lean.status,
            lean.roof_count,
            lean.window_count,
            lean.reason,
        )
        return
    fit = lean.fit
    logger.info(
        "scene %s: %s, %d roofs, %d windows, t %+.2f E %+.2f N m, lean %.2f m per m toward %.0f "
        "deg (radius %.2f), bound %.2f m + %.2f h%s",
        lean.scene,
        lean.status,
        lean.roof_count,
        lean.window_count,
        fit.t_east_m,
        fit.t_north_m,
        fit.k,
        fit.azimuth_deg,
        fit.lean_radius_95,
        fit.ground_error_bound_m,
        fit.lean_radius_95,
        "" if lean.reason is None else f": {lean.reason}",
    )


def _evidence_gap(heights: np.ndarray, window_count: int) -> str | None:
    if len(heights) < MIN_ROOFS:
        return f"{len(heights)} roofs, fewer than {MIN_ROOFS}"
    if window_count < MIN_GROUND_WINDOWS:
        return f"{window_count} ground windows, fewer than {MIN_GROUND_WINDOWS}"
    if np.ptp(heights) == 0:
        return "every roof has the same eave height"
    return None


def _rejected(scene: SceneId, reason: str, counts: dict[str, int]) -> SceneLean:
    return SceneLean(scene=scene, status="rejected", reason=reason, fit=None, **counts)


def _prior_sd(ground: ShiftField) -> tuple[float, float]:
    half_widths_to_sd = 2 * float(norm.ppf(0.5 + DEFAULT_CONFIDENCE / 2))
    east_low, east_high = block_bootstrap_interval(
        ground.east_m, BOOTSTRAP_BLOCK_WINDOWS, np.median
    )
    north_low, north_high = block_bootstrap_interval(
        ground.north_m, BOOTSTRAP_BLOCK_WINDOWS, np.median
    )
    return (
        math.hypot((east_high - east_low) / half_widths_to_sd, METHOD_RESIDUAL_M),
        math.hypot((north_high - north_low) / half_widths_to_sd, METHOD_RESIDUAL_M),
    )


def _capped_fit(
    heights: np.ndarray,
    offsets: np.ndarray,
    prior: tuple[float, float, float, float],
    start: np.ndarray,
) -> tuple[np.ndarray, bool]:
    """Return (t_E, t_N, l_E, l_N) minimising the robust cost subject to |l| <= `MAX_LEAN`."""
    t0_east, t0_north, sd_east, sd_north = prior

    def residuals(t_east: float, t_north: float, lean: np.ndarray) -> np.ndarray:
        model = np.array([t_east, t_north]) + np.outer(heights, lean)
        anchor = [
            (t_east - t0_east) / sd_east * ROBUST_SCALE_M,
            (t_north - t0_north) / sd_north * ROBUST_SCALE_M,
        ]
        return np.concatenate([(offsets - model).T.ravel(), anchor])

    free, free_converged = _robust(lambda p: residuals(p[0], p[1], p[2:]), start)
    if math.hypot(*free[2:]) <= MAX_LEAN:
        return free, free_converged

    def on_cap(azimuth: float) -> np.ndarray:
        return MAX_LEAN * np.array([math.sin(azimuth), math.cos(azimuth)])

    start_on_cap = np.array([free[0], free[1], math.atan2(free[2], free[3])])
    capped, converged = _robust(lambda p: residuals(p[0], p[1], on_cap(p[2])), start_on_cap)
    return np.array([*capped[:2], *on_cap(capped[2])]), converged


def _robust(
    residuals: Callable[[np.ndarray], np.ndarray], start: np.ndarray
) -> tuple[np.ndarray, bool]:
    result = least_squares(residuals, start, loss="soft_l1", f_scale=ROBUST_SCALE_M)
    return np.asarray(result.x, dtype=float), bool(result.status > 0)


def _bootstrap(  # noqa: PLR0913 (data, prior, start and resampling settings)
    heights: np.ndarray,
    offsets: np.ndarray,
    ground: ShiftField,
    prior_sd: tuple[float, float],
    start: np.ndarray,
    *,
    draws: int,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    rows, cols = np.nonzero(np.isfinite(ground.east_m) & np.isfinite(ground.north_m))
    by_block: dict[tuple[int, int], list[int]] = {}
    for window, (r, c) in enumerate(zip(rows, cols, strict=True)):
        key = (int(r) // BOOTSTRAP_BLOCK_WINDOWS, int(c) // BOOTSTRAP_BLOCK_WINDOWS)
        by_block.setdefault(key, []).append(window)
    blocks = [np.array(members) for members in by_block.values()]
    east, north = ground.east_m[rows, cols], ground.north_m[rows, cols]
    fitted = []
    for _ in range(draws):
        roofs = rng.integers(0, len(heights), len(heights))
        windows = np.concatenate([blocks[b] for b in rng.integers(0, len(blocks), len(blocks))])
        if np.ptp(heights[roofs]) == 0:
            continue
        prior = (float(np.median(east[windows])), float(np.median(north[windows])), *prior_sd)
        params, converged = _capped_fit(heights[roofs], offsets[roofs], prior, start)
        if converged:
            fitted.append(params)
    return np.array(fitted)


def _summary(
    params: np.ndarray, draws: np.ndarray, heights: np.ndarray, offsets: np.ndarray
) -> LeanFit:
    tail = 100 * (1 - DEFAULT_CONFIDENCE) / 2
    k_draws = np.hypot(draws[:, 2], draws[:, 3])
    centre_deg = _azimuth_deg(np.median(draws[:, 2]), np.median(draws[:, 3]))
    azimuth_draws = np.degrees(np.arctan2(draws[:, 2], draws[:, 3]))
    # deviations from the median direction, wrapped to [-180, 180), so the interval can cross north
    deviation = (azimuth_draws - centre_deg + DEGREES_PER_TURN / 2) % DEGREES_PER_TURN - (
        DEGREES_PER_TURN / 2
    )
    residual = offsets - (params[:2] + np.outer(heights, params[2:]))
    lean_spread = np.hypot(draws[:, 2] - params[2], draws[:, 3] - params[3])
    k = math.hypot(params[2], params[3])
    t_east_interval, t_north_interval = _interval(draws[:, 0], tail), _interval(draws[:, 1], tail)
    return LeanFit(
        t_east_m=float(params[0]),
        t_north_m=float(params[1]),
        lean_east=float(params[2]),
        lean_north=float(params[3]),
        k=k,
        azimuth_deg=_azimuth_deg(params[2], params[3]),
        t_east_interval_m=t_east_interval,
        t_north_interval_m=t_north_interval,
        k_interval=_interval(k_draws, tail),
        azimuth_interval_deg=_interval(centre_deg + deviation, tail),
        lean_radius_95=float(np.percentile(lean_spread, LEAN_RADIUS_PERCENTILE)),
        ground_error_bound_m=math.hypot(
            _half_width(float(params[0]), t_east_interval),
            _half_width(float(params[1]), t_north_interval),
            METHOD_RESIDUAL_M,
        ),
        at_cap=math.isclose(k, MAX_LEAN),
        roof_residual_m=float(np.median(np.hypot(residual[:, 0], residual[:, 1]))),
        bootstrap_draws=len(draws),
    )


def _half_width(value: float, interval: tuple[float, float]) -> float:
    return max(value - interval[0], interval[1] - value)


def _azimuth_deg(east: float, north: float) -> float:
    return float(np.degrees(np.arctan2(east, north)) % DEGREES_PER_TURN)


def _interval(values: np.ndarray, tail_percent: float) -> tuple[float, float]:
    low, high = np.percentile(values, [tail_percent, 100 - tail_percent])
    return float(low), float(high)
