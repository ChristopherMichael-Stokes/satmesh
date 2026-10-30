"""Area-to-point ordinary kriging of block means.

Kyriakidis 2004, Geographical Analysis 36:259-289.

Data are the means z(v_k) of square blocks v_k of f x f pixels (f = factor). The prediction at the
centre u of a pixel is

    z^(u) = sum_k w_k z(v_k),   sum_j w_j Cbar(v_i, v_j) + mu = Cbar(v_i, u),   sum_k w_k = 1

where Cbar(v_i, v_j) is the mean of the point covariance C over pairs of discretisation points of
v_i and v_j, Cbar(v_i, u) the mean over the points of v_i, and mu the Lagrange multiplier. With
zero nugget and the target block among the data, the mean of the predictions over a datum block
equals its value (coherence, Kyriakidis 2004, sec. 3). Coherence is exact when the discretisation
points are the pixel centres, that is for factor <= MAX_DISCRETISATION; above it the blocks are
discretised more coarsely than the pixels and coherence holds approximately.

Point covariance: exponential, C(h) = s exp(-3 h / a), with sill s and practical range a. They are
fitted so the regularised semivariogram gamma_V(h) = Cbar(V, V) - Cbar(V, V_h) (Journel and
Huijbregts 1978, ch. II; the parametric deconvolution of Goovaerts 2008, Math. Geosci. 40:101-128)
matches the empirical semivariogram of the block means along rows and columns at lags of 1 to
MAX_LAG_BLOCKS blocks, weighted by pair counts.

Neighbourhood: the data blocks within `radius` blocks of the target block, clipped at the edge of
the coarse grid. On a regular grid the covariances depend only on block offsets, so they are
tabulated once and each distinct clipped window is solved once.

Lengths are in pixels. The grid's pixel size sets their unit (metres on a 1 m grid).
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import cache

import numpy as np
from scipy.optimize import least_squares

from satmesh_height.arrays import FloatArray

# a block is discretised by at most this many points a side; exact (one per pixel) up to x10
MAX_DISCRETISATION = 10
MAX_LAG_BLOCKS = 20
# exponential model: C(h) = sill exp(-3 h / range) falls to 5 % of the sill at the practical range
PRACTICAL_RANGE_FACTOR = 3.0
# 8 blocks each way: 17 x 17 data blocks, 289 equations
DEFAULT_NEIGHBOURHOOD_RADIUS = 8


class VariogramFitError(Exception):
    """The point covariance could not be fitted to the block means."""


@dataclass(frozen=True)
class PointCovariance:
    """Exponential point covariance C(h) = sill * exp(-3 h / practical_range_pixels)."""

    sill: float
    practical_range_pixels: float

    def __call__(self, distance_pixels: FloatArray) -> FloatArray:
        """Covariance at each distance (pixels)."""
        return self.sill * np.exp(
            -PRACTICAL_RANGE_FACTOR * distance_pixels / self.practical_range_pixels
        )


def _discretisation(factor: int) -> FloatArray:
    """(row, col) offsets in pixels of the points inside a block whose NW corner is at 0."""
    per_side = min(factor, MAX_DISCRETISATION)
    along = (np.arange(per_side) + 0.5) * factor / per_side
    rows, cols = np.meshgrid(along, along, indexing="ij")
    return np.column_stack([rows.ravel(), cols.ravel()])


def _mean_covariance(
    first: FloatArray, second: FloatArray, covariance: PointCovariance
) -> FloatArray:
    """Mean over the points of `first` of C to each point of `second`."""
    distance = np.linalg.norm(first[:, None] - second[None], axis=-1)
    return covariance(distance).mean(axis=0)


def _block_block(offsets: FloatArray, factor: int, covariance: PointCovariance) -> FloatArray:
    """Cbar(v_0, v_d) for each block offset d = (rows, cols) in `offsets`."""
    points = _discretisation(factor)
    return np.array(
        [
            _mean_covariance(points, points + factor * offset, covariance).mean()
            for offset in offsets
        ]
    )


def _empirical_semivariogram(coarse: FloatArray) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Lags (blocks), semivariances and pair counts along rows and columns."""
    lags = np.arange(1, min(MAX_LAG_BLOCKS, min(coarse.shape) // 2) + 1)
    differences = [
        np.concatenate(
            [(coarse[lag:] - coarse[:-lag]).ravel(), (coarse[:, lag:] - coarse[:, :-lag]).ravel()]
        )
        for lag in lags
    ]
    gammas = np.array([0.5 * np.mean(d**2) for d in differences])
    counts = np.array([d.size for d in differences], dtype=np.float64)
    return lags.astype(np.float64), gammas, counts


def fit_point_covariance(coarse: FloatArray, factor: int) -> PointCovariance:
    """Fit sill and range to the block means `coarse` of blocks of `factor` pixels.

    One fit serves every area at this factor that shares the terrain statistics.
    """
    lags, gammas, counts = _empirical_semivariogram(coarse)
    offsets = np.vstack([[0, 0], np.column_stack([lags, np.zeros_like(lags)])])
    weights = np.sqrt(counts / counts.sum())

    def residuals(log_parameters: FloatArray) -> FloatArray:
        sill, practical_range = np.exp(log_parameters)
        cbar = _block_block(offsets, factor, PointCovariance(sill, practical_range))
        return weights * ((cbar[0] - cbar[1:]) - gammas)

    start = np.log([coarse.var(), factor * lags[-1] / 2])
    fit = least_squares(residuals, start)
    if not fit.success:
        message = f"variogram fit failed: {fit.message}"
        raise VariogramFitError(message)
    sill, practical_range = np.exp(fit.x)
    return PointCovariance(float(sill), float(practical_range))


def _weights_for_window(
    factor: int, covariance: PointCovariance, radius: int
) -> Callable[[tuple[tuple[int, int], ...]], FloatArray]:
    """Cached solver: weights (data blocks x target pixels) for data at the given block offsets."""
    span = 2 * radius
    table_offsets = np.array(
        [(r, c) for r in range(-span, span + 1) for c in range(-span, span + 1)]
    )
    table = dict(
        zip(
            map(tuple, table_offsets.tolist()),
            _block_block(table_offsets, factor, covariance),
            strict=True,
        )
    )
    pixel_centres = np.array([(r + 0.5, c + 0.5) for r in range(factor) for c in range(factor)])
    points = _discretisation(factor)

    @cache
    def weights(window: tuple[tuple[int, int], ...]) -> FloatArray:
        count = len(window)
        lhs = np.ones((count + 1, count + 1))
        lhs[count, count] = 0.0
        for i, (row_i, col_i) in enumerate(window):
            for j, (row_j, col_j) in enumerate(window):
                lhs[i, j] = table[(row_j - row_i, col_j - col_i)]
        rhs = np.ones((count + 1, len(pixel_centres)))
        for i, offset in enumerate(window):
            rhs[i] = _mean_covariance(points + factor * np.array(offset), pixel_centres, covariance)
        return np.linalg.solve(lhs, rhs)[:count]

    return weights


def krige_region(
    coarse: FloatArray,
    factor: int,
    covariance: PointCovariance,
    blocks: tuple[slice, slice],
    radius: int = DEFAULT_NEIGHBOURHOOD_RADIUS,
) -> FloatArray:
    """Krige the pixels of `blocks` (row slice, column slice), with all of `coarse` as context.

    Blocks outside the region serve as data for blocks inside it, so adjacent regions join
    without seams. Returns (rows, cols) pixels of the region.
    """
    n_rows, n_cols = coarse.shape
    weights = _weights_for_window(factor, covariance, radius)
    rows = range(*blocks[0].indices(n_rows))
    cols = range(*blocks[1].indices(n_cols))
    out = np.empty((len(rows) * factor, len(cols) * factor))
    for i, row in enumerate(rows):
        for j, col in enumerate(cols):
            first_row, last_row = max(0, row - radius), min(n_rows, row + radius + 1)
            first_col, last_col = max(0, col - radius), min(n_cols, col + radius + 1)
            window = tuple(
                (r - row, c - col)
                for r in range(first_row, last_row)
                for c in range(first_col, last_col)
            )
            values = coarse[first_row:last_row, first_col:last_col].ravel()
            out[i * factor : (i + 1) * factor, j * factor : (j + 1) * factor] = (
                values @ weights(window)
            ).reshape(factor, factor)
    return out


def krige(
    coarse: FloatArray,
    factor: int,
    covariance: PointCovariance,
    radius: int = DEFAULT_NEIGHBOURHOOD_RADIUS,
) -> FloatArray:
    """Krige the whole coarse grid to (rows * factor, cols * factor) pixels."""
    return krige_region(coarse, factor, covariance, (slice(None), slice(None)), radius)
