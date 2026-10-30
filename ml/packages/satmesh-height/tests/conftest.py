import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine

CRS = "EPSG:27700"
FACTOR = 3
CELLS = 6
SIDE = CELLS * FACTOR
FINE_TRANSFORM = Affine(1.0, 0.0, 448000.0, 0.0, -1.0, 424018.0)


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


def write_inputs(directory: Path, *, dsm_nan: bool = False, guide_shift_m: float = 0.0) -> None:
    """Inputs as documented in the contract, written without the package's own writer."""
    directory.mkdir(parents=True, exist_ok=True)
    rows, cols = np.mgrid[0:SIDE, 0:SIDE].astype(np.float64)
    height = 20.0 + 0.2 * rows + 5.0 * np.exp(-(((rows - 9) ** 2 + (cols - 9) ** 2) / 20.0))
    coarse = height.reshape(CELLS, FACTOR, CELLS, FACTOR).mean(axis=(1, 3)).astype(np.float32)
    if dsm_nan:
        coarse[0, 0] = np.nan
    guide = np.stack([(height - 15) * 20 + 40 * k + cols for k in range(3)]).astype(np.uint8)
    write_raster(directory / "dsm.tif", coarse[None], FINE_TRANSFORM @ Affine.scale(FACTOR))
    write_raster(
        directory / "guide.tif", guide, FINE_TRANSFORM @ Affine.translation(guide_shift_m, 0)
    )
    sidecar = {
        "factor": FACTOR,
        "grid": {
            "width": SIDE,
            "height": SIDE,
            "transform": list(FINE_TRANSFORM)[:6],
        },
        "crs": CRS,
        "has_dtm": False,
        "source_files": ["lidar-dsm.tif"],
    }
    (directory / "inputs.json").write_text(json.dumps(sidecar))


@pytest.fixture
def input_dir(tmp_path: Path) -> Path:
    write_inputs(tmp_path / "in")
    return tmp_path / "in"
