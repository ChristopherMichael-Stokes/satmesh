"""Global image descriptors from MegaLoc on ONNX Runtime, on the CPU or a CUDA GPU.

MegaLoc (Berton and Masone, "MegaLoc: One Retrieval to Place Them All", 2025, MIT) maps an image
to an L2-normalised 8448-dimension descriptor; the cosine of two descriptors ranks places. The
exported graph takes 322 x 322 RGB images normalised with ImageNet statistics and a dynamic batch.
The weights are a build output read from a path.

Which `onnxruntime` wheel is installed decides what is available: the `cpu` extra of this package
installs `onnxruntime`, the `gpu` extra `onnxruntime-gpu`; the two cannot share an environment.
"""

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
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

    def __init__(
        self,
        model_path: Path,
        device: Device = Device.AUTO,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        """Load the ONNX graph at `model_path` on `device`; images run `batch_size` at a time.

        Raises:
            CudaUnavailableError: CUDA is requested and not installed, or the session did not
                place the graph on it.
        """
        self.device = resolve_device(device)
        providers = [CUDA_PROVIDER, CPU_PROVIDER] if self.device is Device.CUDA else [CPU_PROVIDER]
        self._session = InferenceSession(model_path, providers=providers)
        if self.device is Device.CUDA and self._session.get_providers()[0] != CUDA_PROVIDER:
            message = "CUDAExecutionProvider is installed but the session fell back to the CPU"
            raise CudaUnavailableError(message)
        self._batch_size = batch_size

    def describe(self, images: Sequence[npt.NDArray[np.uint8]]) -> npt.NDArray[np.float32]:
        """Unit-length descriptors, one row per image, in the order given."""
        batches = [
            images[start : start + self._batch_size]
            for start in range(0, len(images), self._batch_size)
        ]
        if not batches:
            return np.zeros((0, DESCRIPTOR_SIZE), dtype=np.float32)
        # a worker prepares batch n + 1 (OpenCV and numpy release the GIL) while the session runs n
        with ThreadPoolExecutor(max_workers=1) as preparer:
            upcoming = preparer.submit(_prepared_batch, batches[0])
            rows = []
            for following in [*batches[1:], None]:
                batch = upcoming.result()
                if following is not None:
                    upcoming = preparer.submit(_prepared_batch, following)
                rows.append(self._run(batch))
        return np.concatenate(rows)

    def _run(self, batch: list[npt.NDArray[np.float32]]) -> npt.NDArray[np.float32]:
        output = self._session.run(None, {"images": np.stack(batch)})[0]
        return np.asarray(output, dtype=np.float32)


def _prepared_batch(images: Sequence[npt.NDArray[np.uint8]]) -> list[npt.NDArray[np.float32]]:
    return [_prepared(image) for image in images]


def _prepared(image: npt.NDArray[np.uint8]) -> npt.NDArray[np.float32]:
    """Resize to the graph's square input and normalise to channels-first ImageNet statistics."""
    resized = cv2.resize(image, (MEGALOC_INPUT_PX, MEGALOC_INPUT_PX), interpolation=cv2.INTER_AREA)
    normalised = (resized.astype(np.float32) / BYTE_MAX - IMAGENET_MEAN) / IMAGENET_STD
    return np.ascontiguousarray(normalised.transpose(2, 0, 1))
