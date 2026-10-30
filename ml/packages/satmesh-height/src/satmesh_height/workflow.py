"""One refinement run: a method applied to the inputs of the file contract."""

from dataclasses import dataclass

import numpy as np
import torch

from satmesh_height.arrays import Float32Array
from satmesh_height.composition import variant_a, variant_b
from satmesh_height.config import PixTransformConfig
from satmesh_height.contract import Method, RefineInputs
from satmesh_height.kriging import fit_point_covariance
from satmesh_height.pixtransform import ensemble, refine_area

SINGLE_SEED_METHODS = ("P0", "A", "B")


class SeedCountError(ValueError):
    """The method takes a different number of seeds."""


class TrainingExtentError(ValueError):
    """The training extent is not a whole number of pixels."""


@dataclass(frozen=True)
class Refinement:
    """Refined heights in metres; `spread` is the standard deviation over seeds, when averaged."""

    height: Float32Array
    spread: Float32Array | None


def training_extent_pixels(training_extent_m: float, pixel_size_m: float) -> int:
    """Training extent in pixels of the fine grid."""
    pixels = training_extent_m / pixel_size_m
    if not float(pixels).is_integer():
        message = f"training extent {training_extent_m} m is not whole {pixel_size_m} m pixels"
        raise TrainingExtentError(message)
    return int(pixels)


def run_method(  # noqa: PLR0913
    inputs: RefineInputs,
    method: Method,
    seeds: tuple[int, ...],
    training_extent_m: float,
    *,
    config: PixTransformConfig,
    device: torch.device,
) -> Refinement:
    """Refine `inputs.dsm` with its guide by `method` (see `satmesh_height.composition`)."""
    if method in SINGLE_SEED_METHODS and len(seeds) != 1:
        message = f"method {method} takes one seed, got {len(seeds)}"
        raise SeedCountError(message)
    factor = inputs.sidecar.factor
    source = inputs.dsm.astype(np.float64)
    guide = inputs.guide.astype(np.float64)
    extent = training_extent_pixels(training_extent_m, inputs.sidecar.grid.pixel_size)
    outputs = [
        refine_area(source, guide, factor, extent, config, seed=seed, device=device)
        for seed in seeds
    ]
    mean, spread = ensemble(outputs)
    if method == "P0":
        return Refinement(outputs[0], None)
    if method == "A":
        return Refinement(variant_a(mean, source, factor).astype(np.float32), None)
    if method == "C":
        return Refinement(mean.astype(np.float32), spread.astype(np.float32))
    covariance = fit_point_covariance(source, factor)
    adjusted = variant_b(mean, source, factor, covariance).astype(np.float32)
    return Refinement(adjusted, spread.astype(np.float32) if method == "C+B" else None)
