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
FP16_COSINE_FLOOR = 0.99  # worst cosine to the FP32 graph measured on 128 real renders: 0.9954
ENGINE_BATCH = 4
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


@pytest.fixture(scope="module")
def engine_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if MODEL_VARIABLE not in os.environ:
        pytest.skip(f"{MODEL_VARIABLE} not set")
    pytest.importorskip("xfeat_trt")
    from satmesh_locate.megaloc_export import export_fp16_engine  # noqa: PLC0415  # needs the tensorrt extra

    return export_fp16_engine(
        Path(os.environ[MODEL_VARIABLE]), tmp_path_factory.mktemp("engine"), ENGINE_BATCH
    )


@pytest.mark.skipif(not CUDA_INSTALLED, reason="needs the gpu extra")
def test_engine_descriptors_follow_the_fp32_graph_and_do_not_depend_on_the_batch(
    engine_path: Path,
) -> None:
    images = [noise_image(seed) for seed in range(ENGINE_BATCH + 1)]  # a full batch and a short one
    engine = MegaLocDescriber(engine_path, Device.CUDA, batch_size=ENGINE_BATCH)
    reference = MegaLocDescriber(Path(os.environ[MODEL_VARIABLE]), Device.CUDA)

    together = engine.describe(images)
    alone = engine.describe(images[-1:])
    cosine = np.sum(together * reference.describe(images), axis=1)

    assert np.allclose(np.linalg.norm(together, axis=1), 1.0, atol=UNIT_TOLERANCE)
    assert np.all(cosine > FP16_COSINE_FLOOR)
    assert np.allclose(together[-1], alone[0], atol=BATCH_TOLERANCE)


@pytest.mark.skipif(not CUDA_INSTALLED, reason="needs the gpu extra")
def test_an_engine_refuses_a_batch_size_it_was_not_built_for_and_the_cpu(engine_path: Path) -> None:
    with pytest.raises(ValueError, match="at a time"):
        MegaLocDescriber(engine_path, Device.CUDA, batch_size=ENGINE_BATCH + 1)
    with pytest.raises(CudaUnavailableError, match="CUDA GPU"):
        MegaLocDescriber(engine_path, Device.CPU)
