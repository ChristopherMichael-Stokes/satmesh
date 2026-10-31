"""Global image descriptors from MegaLoc on ONNX Runtime.

MegaLoc (Berton and Masone, "MegaLoc: One Retrieval to Place Them All", 2025, MIT) maps an image
to an L2-normalised 8448-dimension descriptor; the cosine of two descriptors ranks places. The
exported graph takes 322 x 322 RGB images normalised with ImageNet statistics and a dynamic batch.
It matches the torch model to a cosine of 0.99999 (`photo-only-p1-results.md`). The weights are a
build output read from a path, like the XFeat exports.
"""

from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np
import numpy.typing as npt
from onnxruntime import (
    InferenceSession,
    SessionOptions,  # ty: ignore[possibly-missing-import]  # onnxruntime imports it in a try block
)

MEGALOC_INPUT_PX = 322
DESCRIPTOR_SIZE = 8448
BYTE_MAX = 255.0
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
DEFAULT_BATCH_SIZE = 16
CPU_PROVIDER = "CPUExecutionProvider"


class MegaLocDescriber:
    """MegaLoc descriptors of RGB images."""

    def __init__(self, model_path: Path, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
        """Load the ONNX graph at `model_path`; images are described `batch_size` at a time."""
        options = SessionOptions()
        self._session = InferenceSession(model_path, options, providers=[CPU_PROVIDER])
        self._batch_size = batch_size

    def describe(self, images: Sequence[npt.NDArray[np.uint8]]) -> npt.NDArray[np.float32]:
        """Unit-length descriptors, one row per image, in the order given."""
        rows = [
            self._run([_prepared(image) for image in images[start : start + self._batch_size]])
            for start in range(0, len(images), self._batch_size)
        ]
        return np.concatenate(rows) if rows else np.zeros((0, DESCRIPTOR_SIZE), dtype=np.float32)

    def _run(self, batch: list[npt.NDArray[np.float32]]) -> npt.NDArray[np.float32]:
        output = self._session.run(None, {"images": np.stack(batch)})[0]
        return np.asarray(output, dtype=np.float32)


def _prepared(image: npt.NDArray[np.uint8]) -> npt.NDArray[np.float32]:
    """Resize to the graph's square input and normalise to channels-first ImageNet statistics."""
    resized = cv2.resize(image, (MEGALOC_INPUT_PX, MEGALOC_INPUT_PX), interpolation=cv2.INTER_AREA)
    normalised = (resized.astype(np.float32) / BYTE_MAX - IMAGENET_MEAN) / IMAGENET_STD
    return np.ascontiguousarray(normalised.transpose(2, 0, 1))
