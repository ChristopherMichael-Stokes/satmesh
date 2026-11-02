"""Global image descriptors from MegaLoc on ONNX Runtime or TensorRT, on the CPU or a CUDA GPU.

MegaLoc (Berton and Masone, "MegaLoc: One Retrieval to Place Them All", 2025, MIT) maps an image
to an L2-normalised 8448-dimension descriptor; the cosine of two descriptors ranks places. The
exported graph takes 322 x 322 RGB images normalised with ImageNet statistics and a dynamic batch.
The weights are a build output read from a path.

Which `onnxruntime` wheel is installed decides what is available: the `cpu` extra of this package
installs `onnxruntime`, the `gpu` extra `onnxruntime-gpu`; the two cannot share an environment.
"""

from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from enum import StrEnum
from pathlib import Path

import cv2
import numpy as np
import numpy.typing as npt
from onnxruntime import (
    InferenceSession,
    get_available_providers,  # ty: ignore[possibly-missing-import]  # onnxruntime imports it in a try block
)

MEGALOC_INPUT_PX = 322
DESCRIPTOR_SIZE = 8448
BYTE_MAX = 255.0
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
DEFAULT_BATCH_SIZE = 32
PREPARE_WORKERS = (
    4  # preprocessing is 2.5 ms an image; one worker is slower than the TensorRT engine
)
ENGINE_SUFFIX = ".engine"
CPU_PROVIDER = "CPUExecutionProvider"
CUDA_PROVIDER = "CUDAExecutionProvider"


class Device(StrEnum):
    """Where the descriptors are computed."""

    AUTO = "auto"
    CPU = "cpu"
    CUDA = "cuda"


class CudaUnavailableError(RuntimeError):
    """CUDA was requested but the installed `onnxruntime` cannot run on it."""


def resolve_device(device: Device) -> Device:
    """`AUTO` becomes CUDA when the installed `onnxruntime` offers it, else the CPU.

    Raises:
        CudaUnavailableError: `device` is `CUDA` and the CUDA provider is not installed.
    """
    cuda_installed = CUDA_PROVIDER in get_available_providers()
    if device is Device.CUDA and not cuda_installed:
        message = (
            "CUDA requested but this environment has no CUDAExecutionProvider; "
            "install the `gpu` extra of satmesh-locate"
        )
        raise CudaUnavailableError(message)
    if device is Device.AUTO:
        return Device.CUDA if cuda_installed else Device.CPU
    return device


class MegaLocDescriber:
    """MegaLoc descriptors of RGB images."""

    _run: Callable[[Sequence[npt.NDArray[np.float32]]], npt.NDArray[np.float32]]

    def __init__(
        self,
        model_path: Path,
        device: Device = Device.AUTO,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        """Load the ONNX graph or TensorRT engine at `model_path`; `batch_size` images run at once.

        A file ending in `.engine` is a TensorRT engine built by `satmesh-locate-export`; it runs
        on the GPU at the batch size it was built for, and `device` must not be the CPU.

        Raises:
            CudaUnavailableError: CUDA is requested and not installed, or the session did not
                place the graph on it, or an engine is given with `Device.CPU`.
            ValueError: an engine is given with a `batch_size` other than its own.
        """
        self.device = resolve_device(device)
        if model_path.suffix == ENGINE_SUFFIX:
            self._init_engine(model_path, batch_size)
            return
        providers = [CUDA_PROVIDER, CPU_PROVIDER] if self.device is Device.CUDA else [CPU_PROVIDER]
        session = InferenceSession(model_path, providers=providers)
        if self.device is Device.CUDA and session.get_providers()[0] != CUDA_PROVIDER:
            message = "CUDAExecutionProvider is installed but the session fell back to the CPU"
            raise CudaUnavailableError(message)
        self._run = lambda batch: np.asarray(
            session.run(None, {"images": np.stack(batch)})[0], dtype=np.float32
        )
        self._batch_size = batch_size

    def _init_engine(self, plan_path: Path, batch_size: int) -> None:
        if self.device is not Device.CUDA:
            message = f"{plan_path} is a TensorRT engine and needs a CUDA GPU"
            raise CudaUnavailableError(message)
        from satmesh_locate.megaloc_engine import TensorRtEngine  # noqa: PLC0415  # optional `tensorrt` extra

        engine = TensorRtEngine(plan_path)
        if batch_size not in (DEFAULT_BATCH_SIZE, engine.batch_size):
            message = f"{plan_path} runs {engine.batch_size} images at a time, not {batch_size}"
            raise ValueError(message)
        self._run = engine.run
        self._batch_size = engine.batch_size

    def describe(self, images: Sequence[npt.NDArray[np.uint8]]) -> npt.NDArray[np.float32]:
        """Unit-length descriptors, one row per image, in the order given."""
        batches = [
            images[start : start + self._batch_size]
            for start in range(0, len(images), self._batch_size)
        ]
        if not batches:
            return np.zeros((0, DESCRIPTOR_SIZE), dtype=np.float32)
        # workers prepare batch n + 1 (OpenCV and numpy release the GIL) while the model runs n
        with ThreadPoolExecutor(max_workers=PREPARE_WORKERS) as preparer:
            upcoming = _submit_prepared(preparer, batches[0])
            rows = []
            for following in [*batches[1:], None]:
                batch = [future.result() for future in upcoming]
                if following is not None:
                    upcoming = _submit_prepared(preparer, following)
                rows.append(self._run(batch))
        return np.concatenate(rows)


def _submit_prepared(
    preparer: ThreadPoolExecutor, images: Sequence[npt.NDArray[np.uint8]]
) -> list[Future[npt.NDArray[np.float32]]]:
    return [preparer.submit(_prepared, image) for image in images]


def _prepared(image: npt.NDArray[np.uint8]) -> npt.NDArray[np.float32]:
    """Resize to the graph's square input and normalise to channels-first ImageNet statistics."""
    resized = cv2.resize(image, (MEGALOC_INPUT_PX, MEGALOC_INPUT_PX), interpolation=cv2.INTER_AREA)
    normalised = (resized.astype(np.float32) / BYTE_MAX - IMAGENET_MEAN) / IMAGENET_STD
    return np.ascontiguousarray(normalised.transpose(2, 0, 1))
