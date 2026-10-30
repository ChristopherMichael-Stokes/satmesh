"""File contract with `pipeline/`: GeoTIFF rasters and JSON sidecars in a directory.

Inputs, written by `pipeline/` into one directory:

- `dsm.tif`: coarse DSM, float32 metres, one band, on the coarse grid.
- `guide.tif`: guide image, uint8, three bands (RGB), on the fine grid.
- `dtm.tif`: optional DTM, float32 metres, one band, on the fine grid.
- `inputs.json`: an `InputSidecar`.

The fine grid is the sidecar's `grid`; every raster uses its CRS. The coarse grid has the same
origin, `factor` times the pixel size and the fine grid's extent: the fine width and height are
multiples of `factor`.

Outputs, written by `satmesh_height` into one directory:

- `height.tif`: refined DSM, float32 metres, one band, on the fine grid and CRS.
- `spread.tif`: per-pixel standard deviation over seeds in metres, same grid; written only when
  the method averages seeds.
- `height.json`: an `OutputSidecar`.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import rasterio
from pydantic import BaseModel, ConfigDict, Field
from rasterio.transform import Affine

from satmesh_height.arrays import Float32Array
from satmesh_height.config import PixTransformConfig

DSM_FILE = "dsm.tif"
GUIDE_FILE = "guide.tif"
DTM_FILE = "dtm.tif"
INPUT_SIDECAR_FILE = "inputs.json"
HEIGHT_FILE = "height.tif"
SPREAD_FILE = "spread.tif"
OUTPUT_SIDECAR_FILE = "height.json"
GUIDE_BANDS = 3
AFFINE_COEFFICIENTS = 6

# plain alias: typer cannot resolve a `type` statement
Method = Literal["P0", "A", "B", "C", "C+B"]


class ContractError(Exception):
    """An input directory breaks the file contract."""


class GridMismatchError(ContractError):
    """A raster is not on the grid the sidecar declares."""


class FactorError(ContractError):
    """The grid size is not a multiple of the refinement factor."""


class NonFiniteInputError(ContractError):
    """The coarse DSM holds NaN or infinite cells."""


class Grid(BaseModel):
    """Fine raster grid: size in pixels and the affine transform (a, b, c, d, e, f) of rasterio."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    width: int = Field(gt=0)
    height: int = Field(gt=0)
    transform: tuple[float, float, float, float, float, float]

    @property
    def pixel_size(self) -> float:
        """Pixel width in CRS units (metres for a metric CRS)."""
        return abs(self.transform[0])

    def affine(self) -> Affine:
        """The transform as a rasterio `Affine`."""
        return Affine(*self.transform)


class InputSidecar(BaseModel):
    """Describes an input directory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    factor: int = Field(gt=1)
    grid: Grid
    crs: str
    has_dtm: bool
    source_files: tuple[str, ...]


class OutputSidecar(BaseModel):
    """Describes an output directory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    method: Method
    config: PixTransformConfig
    seeds: tuple[int, ...] = Field(min_length=1)
    training_extent_m: float = Field(gt=0)
    factor: int = Field(gt=1)
    grid: Grid
    crs: str
    has_spread: bool
    source_files: tuple[str, ...]


@dataclass(frozen=True)
class RefineInputs:
    """Validated contents of an input directory."""

    sidecar: InputSidecar
    dsm: Float32Array  # (M, M) metres
    guide: np.ndarray  # (3, N, N) uint8
    dtm: Float32Array | None  # (N, N) metres; absent when the pipeline had none


def _read_raster(
    path: Path, expected_crs: str, expected_grid: Grid, expected_transform: Affine
) -> np.ndarray:
    with rasterio.open(path) as raster:
        if raster.crs != expected_crs:
            message = f"{path.name}: CRS {raster.crs} differs from sidecar {expected_crs}"
            raise GridMismatchError(message)
        if (raster.width, raster.height) != (expected_grid.width, expected_grid.height):
            message = (
                f"{path.name}: size {raster.width} x {raster.height} differs from "
                f"{expected_grid.width} x {expected_grid.height}"
            )
            raise GridMismatchError(message)
        if not raster.transform.almost_equals(expected_transform):
            message = f"{path.name}: transform {raster.transform} differs from {expected_transform}"
            raise GridMismatchError(message)
        return raster.read()


def read_inputs(input_dir: Path) -> RefineInputs:
    """Read and validate an input directory.

    Raises:
        FactorError: the grid size is not a multiple of the factor.
        GridMismatchError: a raster's CRS, size or transform differs from the sidecar's grid.
        NonFiniteInputError: the coarse DSM has NaN or infinite cells.
    """
    sidecar = InputSidecar.model_validate_json((input_dir / INPUT_SIDECAR_FILE).read_text())
    grid, factor = sidecar.grid, sidecar.factor
    if grid.width % factor or grid.height % factor:
        message = f"grid {grid.width} x {grid.height} is not a multiple of factor {factor}"
        raise FactorError(message)
    fine = grid.affine()
    coarse_grid = Grid(
        width=grid.width // factor, height=grid.height // factor, transform=grid.transform
    )
    coarse = fine @ Affine.scale(factor)
    dsm = _read_raster(input_dir / DSM_FILE, sidecar.crs, coarse_grid, coarse)[0].astype(np.float32)
    if not np.isfinite(dsm).all():
        message = f"{DSM_FILE} has non-finite cells"
        raise NonFiniteInputError(message)
    guide = _read_raster(input_dir / GUIDE_FILE, sidecar.crs, grid, fine)
    if guide.shape[0] != GUIDE_BANDS or guide.dtype != np.uint8:
        message = (
            f"{GUIDE_FILE} must be {GUIDE_BANDS} uint8 bands, got {guide.shape[0]} of {guide.dtype}"
        )
        raise ContractError(message)
    dtm = (
        _read_raster(input_dir / DTM_FILE, sidecar.crs, grid, fine)[0].astype(np.float32)
        if sidecar.has_dtm
        else None
    )
    return RefineInputs(sidecar=sidecar, dsm=dsm, guide=guide, dtm=dtm)


def _write_height_raster(path: Path, values: Float32Array, grid: Grid, crs: str) -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=grid.width,
        height=grid.height,
        count=1,
        dtype="float32",
        crs=crs,
        transform=grid.affine(),
        compress="deflate",
    ) as raster:
        raster.write(values, 1)


def write_outputs(
    output_dir: Path,
    height: Float32Array,
    spread: Float32Array | None,
    sidecar: OutputSidecar,
) -> None:
    """Write `height.tif`, `spread.tif` when `spread` is given, and the sidecar."""
    if (spread is not None) != sidecar.has_spread:
        message = "spread must be given exactly when the sidecar has_spread"
        raise ValueError(message)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_height_raster(output_dir / HEIGHT_FILE, height, sidecar.grid, sidecar.crs)
    if spread is not None:
        _write_height_raster(output_dir / SPREAD_FILE, spread, sidecar.grid, sidecar.crs)
    (output_dir / OUTPUT_SIDECAR_FILE).write_text(sidecar.model_dump_json(indent=2))
