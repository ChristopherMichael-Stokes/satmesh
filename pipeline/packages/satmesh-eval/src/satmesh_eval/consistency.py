"""Consistency of an enhanced texture with the source it came from.

The enhanced image is reduced to the source grid by area averaging (`cv2.INTER_AREA`, an exact
block mean at integer scales) and compared with the source. A faithful enhancement adds detail
above the source's Nyquist frequency and leaves everything below it as it was, so the reduced
image must reproduce the source: small mean absolute difference, small spectral angle between the
RGB vectors, no residual shift. This is the consistency property of Aybar et al. (2024), "A
Comprehensive Benchmark for Optical Remote Sensing Image Super-Resolution", IEEE GRSL 21, 5003105,
computed without their learned metrics.
"""

from dataclasses import dataclass

import cv2
import numpy as np
from skimage.registration import phase_cross_correlation

from satmesh_eval.offset import LUMA_709, UPSAMPLE_FACTOR

COLOUR_BANDS = 3


@dataclass(frozen=True)
class Consistency:
    """Agreement of an enhanced image, reduced to the source grid, with the source.

    The shift is the displacement of the reduced image from the source in source pixels, east and
    north (rows run south), by phase correlation of luma.
    """

    mean_abs_difference: float
    mean_spectral_angle_deg: float
    shift_east_px: float
    shift_north_px: float


def consistency(enhanced: np.ndarray, source: np.ndarray) -> Consistency:
    """Compare `enhanced` with `source`, both `(row, col, band)` arrays on 0 to 255.

    The enhanced size must be an integer multiple of the source size.
    """
    if source.ndim != COLOUR_BANDS or source.shape[2] != COLOUR_BANDS:
        msg = f"expected (row, col, 3) images, got source {source.shape}"
        raise ValueError(msg)
    scale, remainder = divmod(enhanced.shape[0], source.shape[0])
    if (
        remainder
        or enhanced.shape[1] != scale * source.shape[1]
        or enhanced.shape[2:] != source.shape[2:]
        or scale < 1
    ):
        msg = f"enhanced {enhanced.shape} is not an integer multiple of source {source.shape}"
        raise ValueError(msg)
    reduced = cv2.resize(
        enhanced.astype(np.float32), source.shape[1::-1][:2], interpolation=cv2.INTER_AREA
    ).astype(np.float64)
    reference = source.astype(np.float64)
    shift, _, _ = phase_cross_correlation(
        _tapered(np.tensordot(reference, LUMA_709, axes=([2], [0]))),
        _tapered(np.tensordot(reduced, LUMA_709, axes=([2], [0]))),
        upsample_factor=UPSAMPLE_FACTOR,
        normalization="phase",
    )
    return Consistency(
        mean_abs_difference=float(np.abs(reduced - reference).mean()),
        mean_spectral_angle_deg=_mean_spectral_angle_deg(reduced, reference),
        shift_east_px=float(-shift[1]),
        shift_north_px=float(shift[0]),
    )


def _tapered(luma: np.ndarray) -> np.ndarray:
    return (luma - luma.mean()) * np.outer(np.hanning(luma.shape[0]), np.hanning(luma.shape[1]))


def _mean_spectral_angle_deg(first: np.ndarray, second: np.ndarray) -> float:
    norms = np.linalg.norm(first, axis=2) * np.linalg.norm(second, axis=2)
    defined = norms > 0
    cosine = np.sum(first * second, axis=2)[defined] / norms[defined]
    return float(np.degrees(np.arccos(np.clip(cosine, -1, 1))).mean())
