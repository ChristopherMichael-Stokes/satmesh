import json
import os
from pathlib import Path

import cv2
import numpy as np
import pytest
from onnxruntime import (
    get_available_providers,  # ty: ignore[possibly-missing-import]  # onnxruntime imports it in a try block
)
from typer.testing import CliRunner

from satmesh_locate.cli import app
from satmesh_locate.megaloc import (
    DESCRIPTOR_SIZE,
    CudaUnavailableError,
    Device,
    MegaLocDescriber,
    resolve_device,
)

MODEL_VARIABLE = "MEGALOC_MODEL"
CUDA_INSTALLED = "CUDAExecutionProvider" in get_available_providers()
needs_model = pytest.mark.skipif(
    MODEL_VARIABLE not in os.environ, reason=f"{MODEL_VARIABLE} not set"
)
UNIT_TOLERANCE = 1e-4  # float32 arithmetic through a transformer
BATCH_TOLERANCE = 1e-3  # batch composition changes float32 summation order
INPUT_PX = 322


def noise_image(seed: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 256, (INPUT_PX, INPUT_PX, 3), dtype=np.uint8)


@pytest.mark.skipif(CUDA_INSTALLED, reason="needs an environment without the gpu extra")
def test_cuda_is_refused_without_the_cuda_provider_and_auto_falls_back_to_the_cpu() -> None:
    with pytest.raises(CudaUnavailableError, match="gpu"):
        resolve_device(Device.CUDA)
    assert resolve_device(Device.AUTO) is Device.CPU


@pytest.mark.skipif(not CUDA_INSTALLED, reason="needs the gpu extra")
def test_auto_picks_cuda_when_the_provider_is_installed() -> None:
    assert resolve_device(Device.AUTO) is Device.CUDA


@needs_model
def test_descriptors_are_unit_length_and_do_not_depend_on_the_batch() -> None:
    describer = MegaLocDescriber(Path(os.environ[MODEL_VARIABLE]), batch_size=2)
    images = [noise_image(seed) for seed in range(3)]

    together = describer.describe(images)
    alone = describer.describe(images[1:2])

    assert together.shape == (3, DESCRIPTOR_SIZE)
    assert np.allclose(np.linalg.norm(together, axis=1), 1.0, atol=UNIT_TOLERANCE)
    assert np.allclose(together[1], alone[0], atol=BATCH_TOLERANCE)
    assert describer.describe([]).shape == (0, DESCRIPTOR_SIZE)


@needs_model
def test_rank_puts_the_view_identical_to_the_photo_first(tmp_path: Path) -> None:
    images = np.stack([noise_image(seed) for seed in range(4)])
    np.save(tmp_path / "renders_000.npy", images)
    np.save(
        tmp_path / "meta.npy", np.array([[i * 500.0, 0.0, 5.0, 70.0, 0.0, -35.0] for i in range(4)])
    )
    photo = tmp_path / "photo.png"
    cv2.imwrite(str(photo), cv2.cvtColor(images[2], cv2.COLOR_RGB2BGR))
    out = tmp_path / "places.json"

    result = CliRunner().invoke(app, [str(tmp_path), str(photo), str(out), "--places", "2"])

    assert result.exit_code == 0, result.output
    places = json.loads(out.read_text())
    assert places[0]["east"] == 1000.0
    assert places[0]["similarity"] == pytest.approx(1.0, abs=UNIT_TOLERANCE)
    assert places[1]["similarity"] < places[0]["similarity"]
