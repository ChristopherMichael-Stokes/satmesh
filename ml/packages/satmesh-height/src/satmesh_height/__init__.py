"""Refines a coarse DSM to a guide image's grid: PixTransform, kriging and their compositions."""

from satmesh_height.composition import block_mean, nearest_up, variant_a, variant_b
from satmesh_height.config import PixTransformConfig
from satmesh_height.contract import (
    ContractError,
    FactorError,
    GridMismatchError,
    InputSidecar,
    NonFiniteInputError,
    OutputSidecar,
    RefineInputs,
    read_inputs,
    write_outputs,
)
from satmesh_height.kriging import PointCovariance, fit_point_covariance, krige, krige_region
from satmesh_height.pixtransform import ensemble, refine, refine_area
from satmesh_height.workflow import Refinement, run_method

__all__ = [
    "ContractError",
    "FactorError",
    "GridMismatchError",
    "InputSidecar",
    "NonFiniteInputError",
    "OutputSidecar",
    "PixTransformConfig",
    "PointCovariance",
    "RefineInputs",
    "Refinement",
    "block_mean",
    "ensemble",
    "fit_point_covariance",
    "krige",
    "krige_region",
    "nearest_up",
    "read_inputs",
    "refine",
    "refine_area",
    "run_method",
    "variant_a",
    "variant_b",
    "write_outputs",
]
