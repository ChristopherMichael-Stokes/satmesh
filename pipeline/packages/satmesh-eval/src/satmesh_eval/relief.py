"""Does the imagery offset depend on relief? Windows on raised objects against open ground.

A conventional orthophoto is rectified to a ground model, so a raised feature (tree, roof, bridge
deck) leans away from the nadir point by `h * r / H` (height, radial distance, flying height); a
true orthophoto uses a surface model and does not. If the offset on windows full of raised objects
differs from the offset on open ground, the imagery is not true-ortho at those objects.
"""

from dataclasses import dataclass

import numpy as np
from scipy.stats import spearmanr

from satmesh_eval.offset import OffsetEstimate, ShiftField, summarise
from satmesh_eval.strata import OBJECT_HEIGHT_THRESHOLD_M, raised_object_mask

# a window counts as open ground below this share of raised pixels, and as object-dominated above
# the second (tunable)
OPEN_MAX_FRACTION = 0.02
OBJECT_MIN_FRACTION = 0.3
MIN_WINDOWS_FOR_TREND = 3


@dataclass(frozen=True)
class ReliefSplit:
    """Offsets on open-ground windows and on object-dominated windows, with the height trend."""

    open_ground: OffsetEstimate | None
    objects: OffsetEstimate | None
    north_against_height_rho: float
    east_against_height_rho: float


def raised_fraction_by_window(  # noqa: PLR0913 (window grid in ground metres, each a setting)
    surface: np.ndarray,
    ground: np.ndarray,
    *,
    pixel_m: float,
    window_m: float,
    step_m: float,
    threshold_m: float = OBJECT_HEIGHT_THRESHOLD_M,
) -> tuple[np.ndarray, np.ndarray]:
    """Return per-window share of raised pixels and mean height above ground.

    `surface` and `ground` are north-up rasters of one box at `pixel_m`; the windows are the
    regular grid `window_shifts` uses once its pixel counts are converted to metres.
    """
    raised = raised_object_mask(surface, ground, threshold_m)
    height = surface - ground
    size, step = round(window_m / pixel_m), round(step_m / pixel_m)
    starts_r = range(0, surface.shape[0] - size + 1, step)
    starts_c = range(0, surface.shape[1] - size + 1, step)
    fraction = np.array(
        [[raised[r : r + size, c : c + size].mean() for c in starts_c] for r in starts_r]
    )
    mean_height = np.array(
        [[height[r : r + size, c : c + size].mean() for c in starts_c] for r in starts_r]
    )
    return fraction, mean_height


def split_by_relief(
    field: ShiftField, fraction: np.ndarray, mean_height: np.ndarray
) -> ReliefSplit:
    """Summarise the reliable windows of `field` by relief class; a class with none is None."""
    if fraction.shape != field.east_m.shape:
        msg = f"window grids differ: {fraction.shape} against {field.east_m.shape}"
        raise ValueError(msg)
    reliable = np.isfinite(field.east_m)
    if reliable.sum() < MIN_WINDOWS_FOR_TREND:
        msg = f"{reliable.sum()} reliable windows are too few for a height trend"
        raise ValueError(msg)
    return ReliefSplit(
        open_ground=_summary(field, reliable & (fraction <= OPEN_MAX_FRACTION)),
        objects=_summary(field, reliable & (fraction >= OBJECT_MIN_FRACTION)),
        north_against_height_rho=_rank_correlation(mean_height[reliable], field.north_m[reliable]),
        east_against_height_rho=_rank_correlation(mean_height[reliable], field.east_m[reliable]),
    )


def _rank_correlation(first: np.ndarray, second: np.ndarray) -> float:
    """Spearman's rho, NaN when either input is constant (rho is undefined there)."""
    if np.ptp(first) == 0 or np.ptp(second) == 0:
        return float("nan")
    return float(spearmanr(first, second).statistic)


def _summary(field: ShiftField, keep: np.ndarray) -> OffsetEstimate | None:
    if not keep.any():
        return None
    return summarise(
        ShiftField(
            np.where(keep, field.east_m, np.nan),
            np.where(keep, field.north_m, np.nan),
            np.where(keep, field.response, np.nan),
        )
    )
