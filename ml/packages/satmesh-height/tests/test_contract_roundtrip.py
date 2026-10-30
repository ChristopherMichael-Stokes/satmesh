"""ML side of the `ml/` file contract; run by `make test-contract` between the pipeline stages."""

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from satmesh_height.cli import app

CONTRACT_DIR_VARIABLE = "SATMESH_CONTRACT_DIR"


@pytest.mark.skipif(
    CONTRACT_DIR_VARIABLE not in os.environ, reason=f"{CONTRACT_DIR_VARIABLE} is unset"
)
def test_refine_the_pipeline_written_inputs() -> None:
    directory = Path(os.environ[CONTRACT_DIR_VARIABLE])
    arguments = [
        "refine",
        str(directory / "inputs"),
        str(directory / "outputs"),
        "--variant",
        "B",
        "--training-extent-m",
        "9",
        "--steps",
        "4",
        "--device",
        "cpu",
    ]
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 0, result.output
