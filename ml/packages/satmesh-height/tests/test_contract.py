import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from conftest import CELLS, CRS, FACTOR, FINE_TRANSFORM, SIDE, write_inputs
from pydantic import ValidationError
from typer.testing import CliRunner

from satmesh_height.cli import app
from satmesh_height.contract import (
    FactorError,
    GridMismatchError,
    InputSidecar,
    NonFiniteInputError,
    OutputSidecar,
    read_inputs,
)

runner = CliRunner()
FAST_ARGS = ["--steps", "4", "--device", "cpu", "--training-extent-m", "9"]
FLOAT32_ABSOLUTE_TOLERANCE = 1e-5  # float32 spacing at 30 m is 2^-19


def test_reader_returns_arrays_on_the_declared_grids(input_dir: Path) -> None:
    inputs = read_inputs(input_dir)
    assert inputs.dsm.shape == (CELLS, CELLS)
    assert inputs.guide.shape == (3, SIDE, SIDE)
    assert inputs.guide.dtype == np.uint8
    assert inputs.dtm is None
    assert inputs.sidecar.factor == FACTOR


def test_reader_rejects_a_guide_shifted_off_the_grid(tmp_path: Path) -> None:
    write_inputs(tmp_path, guide_shift_m=1.0)
    with pytest.raises(GridMismatchError, match=r"guide\.tif: transform"):
        read_inputs(tmp_path)


def test_reader_rejects_a_grid_that_the_factor_does_not_divide(input_dir: Path) -> None:
    sidecar = json.loads((input_dir / "inputs.json").read_text())
    sidecar["factor"] = 4
    (input_dir / "inputs.json").write_text(json.dumps(sidecar))
    with pytest.raises(FactorError):
        read_inputs(input_dir)


def test_reader_rejects_nan_in_the_coarse_dsm(tmp_path: Path) -> None:
    write_inputs(tmp_path, dsm_nan=True)
    with pytest.raises(NonFiniteInputError):
        read_inputs(tmp_path)


def test_sidecars_reject_unknown_fields(input_dir: Path) -> None:
    sidecar = json.loads((input_dir / "inputs.json").read_text())
    with pytest.raises(ValidationError):
        InputSidecar.model_validate({**sidecar, "extra": 1})


@pytest.mark.parametrize("method", ["P0", "A", "B"])
def test_cli_writes_float32_metres_on_the_input_grid(
    input_dir: Path, tmp_path: Path, method: str
) -> None:
    output = tmp_path / "out"
    result = runner.invoke(
        app, ["refine", str(input_dir), str(output), "--variant", method, *FAST_ARGS]
    )
    assert result.exit_code == 0, result.output
    with rasterio.open(output / "height.tif") as raster:
        assert raster.dtypes == ("float32",)
        assert raster.crs == CRS
        assert raster.transform.almost_equals(FINE_TRANSFORM)
        assert (raster.width, raster.height) == (SIDE, SIDE)
        height = raster.read(1)
    sidecar = OutputSidecar.model_validate_json((output / "height.json").read_text())
    assert sidecar.method == method
    assert sidecar.seeds == (0,)
    assert sidecar.config.steps == 4
    assert sidecar.training_extent_m == 9
    assert sidecar.source_files == ("lidar-dsm.tif",)
    assert not (output / "spread.tif").exists()
    if method != "P0":
        coarse = height.reshape(CELLS, FACTOR, CELLS, FACTOR).mean(axis=(1, 3))
        np.testing.assert_allclose(
            coarse, read_inputs(input_dir).dsm, rtol=0, atol=FLOAT32_ABSOLUTE_TOLERANCE
        )


def test_cli_seed_average_also_writes_the_spread(input_dir: Path, tmp_path: Path) -> None:
    output = tmp_path / "out"
    seeds = ["--seeds", "1", "--seeds", "2"]
    result = runner.invoke(
        app, ["refine", str(input_dir), str(output), "--variant", "C+B", *seeds, *FAST_ARGS]
    )
    assert result.exit_code == 0, result.output
    with rasterio.open(output / "spread.tif") as raster:
        spread = raster.read(1)
    assert spread.dtype == np.float32
    assert spread.min() >= 0
    assert spread.max() > 0
    assert OutputSidecar.model_validate_json((output / "height.json").read_text()).has_spread


def test_cli_rejects_several_seeds_for_a_single_seed_method(
    input_dir: Path, tmp_path: Path
) -> None:
    seeds = ["--seeds", "1", "--seeds", "2"]
    result = runner.invoke(
        app, ["refine", str(input_dir), str(tmp_path / "o"), "--variant", "A", *seeds, *FAST_ARGS]
    )
    assert result.exit_code != 0
    assert not (tmp_path / "o" / "height.tif").exists()
