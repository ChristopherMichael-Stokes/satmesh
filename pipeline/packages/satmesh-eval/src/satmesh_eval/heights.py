"""Robust height-error statistics (Höhle and Höhle 2009) with a block bootstrap.

With error dh_i = h_i(estimate) - h_i(reference):

- median:  Q(0.5) of dh
- NMAD:    1.4826 * median(|dh_j - median(dh)|)
- p68.3, p95: sample quantiles Q(p) = x_(ceil(p n)) of |dh|
- RMSE:    sqrt(mean(dh^2)), reported for comparison only

Höhle J., Höhle M. (2009), ISPRS J. Photogramm. Remote Sens. 64(4), 398-406,
doi:10.1016/j.isprsjprs.2009.02.003.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from geoutils.stats import nmad

QUANTILE_ONE_SIGMA = 0.683  # share of a normal distribution within one standard deviation
QUANTILE_95 = 0.95
DEFAULT_CONFIDENCE = 0.95
DEFAULT_BOOTSTRAP_DRAWS = 1000


@dataclass(frozen=True)
class HeightScore:
    """Error statistics of one set of height differences, in metres."""

    count: int
    median_m: float
    nmad_m: float
    quantile_683_m: float
    quantile_95_m: float
    rmse_m: float


def score_heights(errors: np.ndarray) -> HeightScore:
    """Score `errors` (any shape, NaN ignored); raises when no finite error remains."""
    finite = errors[np.isfinite(errors)]
    if finite.size == 0:
        msg = "no finite height errors to score"
        raise ValueError(msg)
    absolute = np.abs(finite)
    return HeightScore(
        count=finite.size,
        median_m=float(np.median(finite)),
        nmad_m=float(nmad(finite)),
        quantile_683_m=_sample_quantile(absolute, QUANTILE_ONE_SIGMA),
        quantile_95_m=_sample_quantile(absolute, QUANTILE_95),
        rmse_m=float(np.sqrt(np.mean(finite**2))),
    )


def score_by_stratum(
    errors: np.ndarray, strata: np.ndarray, names: dict[int, str]
) -> dict[str, HeightScore]:
    """Score `errors` per label in `strata` (same shape); strata with no data are dropped."""
    scores: dict[str, HeightScore] = {}
    for label, name in names.items():
        selected = errors[strata == label]
        if np.isfinite(selected).any():
            scores[name] = score_heights(selected)
    return scores


def block_bootstrap_interval(  # noqa: PLR0913 (statistic, block size and resampling settings)
    errors: np.ndarray,
    block_px: int,
    statistic: Callable[[np.ndarray], float],
    *,
    draws: int = DEFAULT_BOOTSTRAP_DRAWS,
    confidence: float = DEFAULT_CONFIDENCE,
    seed: int = 0,
) -> tuple[float, float]:
    """Confidence interval of `statistic(errors)` resampling whole `block_px` squares.

    Neighbouring raster pixels are correlated, so resampling pixels would give an interval far too
    narrow; resampling blocks keeps the correlation inside a block (cluster bootstrap, as proposed
    by Höhle and Höhle for dependent data). `errors` is a 2-D raster with NaN for no data.
    """
    rows, cols = errors.shape
    blocks = [
        errors[r : r + block_px, c : c + block_px].ravel()
        for r in range(0, rows, block_px)
        for c in range(0, cols, block_px)
    ]
    blocks = [block[np.isfinite(block)] for block in blocks]
    blocks = [block for block in blocks if block.size]
    if not blocks:
        msg = "no finite height errors to resample"
        raise ValueError(msg)
    rng = np.random.default_rng(seed)
    values = [
        statistic(np.concatenate([blocks[i] for i in rng.integers(len(blocks), size=len(blocks))]))
        for _ in range(draws)
    ]
    tail = (1 - confidence) / 2
    low, high = np.quantile(values, [tail, 1 - tail])
    return float(low), float(high)


def _sample_quantile(values: np.ndarray, probability: float) -> float:
    return float(np.quantile(values, probability, method="inverted_cdf"))
