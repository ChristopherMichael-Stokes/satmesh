"""Pipeline side of the `ml/` file contract; run by `make test-contract`.

The writer and the reader follow the contract as documented in `satmesh_height.contract` and do
not import it. `make test-contract` runs the write stage here, then `ml/` refines the directory,
then the read stage here. Both stages skip when SATMESH_CONTRACT_DIR is unset.
"""

import json
import os
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine

CONTRACT_DIR_VARIABLE = "SATMESH_CONTRACT_DIR"
CRS = "EPSG:27700"
FACTOR = 3
CELLS = 6
SIDE = CELLS * FACTOR
FINE_TRANSFORM = Affine(1.0, 0.0, 448000.0, 0.0, -1.0, 424018.0)
SOURCE_FILES = ["ea-dsm-sample.tif"]
# float32 spacing at 30 m is 2^-19; kriging's coherence adds well under 1e-5
HEIGHT_TOLERANCE_M = 1e-5

requires_contract_dir = pytest.mark.skipif(
    CONTRACT_DIR_VARIABLE not in os.environ, reason=f"{CONTRACT_DIR_VARIABLE} is unset"
)


def contract_dir() -> Path:
    return Path(os.environ[CONTRACT_DIR_VARIABLE])


def fine_heights() -> np.ndarray:
    rows, cols = np.mgrid[0:SIDE, 0:SIDE].astype(np.float64)
    return 20.0 + 0.2 * rows + 5.0 * np.exp(-(((rows - 9) ** 2 + (cols - 9) ** 2) / 20.0))


def coarse_heights() -> np.ndarray:
    return fine_heights().reshape(CELLS, FACTOR, CELLS, FACTOR).mean(axis=(1, 3))


def write_raster(path: Path, bands: np.ndarray, transform: Affine) -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=bands.shape[2],
        height=bands.shape[1],
        count=bands.shape[0],
        dtype=bands.dtype,
        crs=CRS,
        transform=transform,
    ) as raster:
        raster.write(bands)


@requires_contract_dir
def test_write_ml_inputs() -> None:
    inputs = contract_dir() / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    cols = np.mgrid[0:SIDE, 0:SIDE][1]
    guide = np.stack([(fine_heights() - 15) * 20 + 40 * band + cols for band in range(3)])
    write_raster(
        inputs / "dsm.tif",
        coarse_heights().astype(np.float32)[None],
        FINE_TRANSFORM @ Affine.scale(FACTOR),
    )
    write_raster(inputs / "guide.tif", guide.astype(np.uint8), FINE_TRANSFORM)
    sidecar = {
        "factor": FACTOR,
        "grid": {"width": SIDE, "height": SIDE, "transform": list(FINE_TRANSFORM)[:6]},
        "crs": CRS,
        "has_dtm": False,
        "source_files": SOURCE_FILES,
    }
    (inputs / "inputs.json").write_text(json.dumps(sidecar))


@requires_contract_dir
def test_read_ml_outputs() -> None:
    outputs = contract_dir() / "outputs"
    with rasterio.open(outputs / "height.tif") as raster:
        assert raster.dtypes == ("float32",)
        assert raster.count == 1
        assert raster.crs == CRS
        assert (raster.width, raster.height) == (SIDE, SIDE)
        assert raster.transform.almost_equals(FINE_TRANSFORM)
        height = raster.read(1)
    # metres: each factor x factor cell averages to the coarse DSM it was refined from
    cell_means = height.reshape(CELLS, FACTOR, CELLS, FACTOR).mean(axis=(1, 3))
    np.testing.assert_allclose(cell_means, coarse_heights(), rtol=0, atol=HEIGHT_TOLERANCE_M)
    sidecar = json.loads((outputs / "height.json").read_text())
    assert sidecar["method"] == "B"
    assert sidecar["factor"] == FACTOR
    assert sidecar["crs"] == CRS
    assert sidecar["grid"] == {"width": SIDE, "height": SIDE, "transform": list(FINE_TRANSFORM)[:6]}
    assert sidecar["source_files"] == SOURCE_FILES
    assert sidecar["seeds"] == [0]
    assert sidecar["training_extent_m"] == 9
    assert sidecar["config"]["steps"] == 4
    assert sidecar["config"]["loss"] == "l1"
