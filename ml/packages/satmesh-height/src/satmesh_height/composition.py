"""Variants that make a PixTransform output P consistent with the source s (coarse cell means).

B(.) is the mean over each factor x factor cell, N(.) nearest-neighbour upsampling of a coarse
grid and K(.) area-to-point kriging, coherent so that B(K(c)) = c.

- A:   P + N(s - B(P)). Additive mass-preserving adjustment of pycnophylactic interpolation
  (Tobler 1979, JASA 74:519-530).
- B:   P + K(s - B(P)). P is the trend and its cell residuals are kriged (area-to-point residual
  kriging with a covariate trend, Kyriakidis 2004; Liu, Kyriakidis and Goodchild 2008, IJGIS
  22:431-447).
- C+B: B applied to the mean of P over several seeds.

A and B satisfy B(result) = s. For B this is exact only where K is exactly coherent (see
`satmesh_height.kriging`).
"""

import numpy as np

from satmesh_height.arrays import FloatArray
from satmesh_height.kriging import DEFAULT_NEIGHBOURHOOD_RADIUS, PointCovariance, krige


def block_mean(fine: FloatArray, factor: int) -> FloatArray:
    """Mean over each factor x factor block of `fine`."""
    rows, cols = fine.shape
    return fine.reshape(rows // factor, factor, cols // factor, factor).mean(axis=(1, 3))


def nearest_up(coarse: FloatArray, factor: int) -> FloatArray:
    """Repeat each coarse value over its factor x factor block."""
    return np.repeat(np.repeat(coarse, factor, axis=0), factor, axis=1)


def variant_a(pix: FloatArray, source: FloatArray, factor: int) -> FloatArray:
    """P + N(s - B(P)): each cell shifted so its mean is the source."""
    return pix + nearest_up(source - block_mean(pix, factor), factor)


def variant_b(
    pix: FloatArray,
    source: FloatArray,
    factor: int,
    covariance: PointCovariance,
    radius: int = DEFAULT_NEIGHBOURHOOD_RADIUS,
) -> FloatArray:
    """P + K(s - B(P)): the cell residuals kriged instead of repeated."""
    return pix + krige(source - block_mean(pix, factor), factor, covariance, radius)
