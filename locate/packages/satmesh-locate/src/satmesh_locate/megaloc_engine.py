"""MegaLoc descriptors from a serialized TensorRT engine of fixed batch size.

The engine is built offline by `satmesh_locate.megaloc_export`; this module only loads and runs it,
through the `EngineRunner` of `xfeat-trt`. Needs the `tensorrt` extra of `satmesh-locate`.
"""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import numpy.typing as npt
import tensorrt as trt
from cuda.core import Device  # ty: ignore[unresolved-import]  # cuda.core exports it lazily; ty cannot see it
from xfeat_trt.runner import EngineRunner

CUDA_DEVICE_ORDINAL = 0
INPUT_NAME = "images"
OUTPUT_NAME = "descriptor"


class TensorRtEngine:
    """A deserialized MegaLoc engine that runs `batch_size` images per execution."""

    def __init__(self, plan_path: Path) -> None:
        """Deserialize the engine at `plan_path` and allocate its buffers on the first GPU.

        Raises:
            ValueError: TensorRT cannot read the plan, for example one built by another TensorRT
                version or for another GPU.
        """
        device = Device(CUDA_DEVICE_ORDINAL)
        device.set_current()
        self._runtime = trt.Runtime(trt.Logger(trt.Logger.WARNING))  # ty: ignore[unresolved-attribute]  # tensorrt stubs lack Runtime and Logger
        self._engine = self._runtime.deserialize_cuda_engine(plan_path.read_bytes())
        if self._engine is None:
            message = (
                f"TensorRT cannot deserialize {plan_path}; rebuild it with `satmesh-locate-export`"
            )
            raise ValueError(message)
        self.batch_size = int(self._engine.get_tensor_shape(INPUT_NAME)[0])
        self._runner = EngineRunner(self._engine, device)

    def run(self, batch: Sequence[npt.NDArray[np.float32]]) -> npt.NDArray[np.float32]:
        """Unit-length descriptors of up to `batch_size` prepared images, one row per image.

        A short batch is padded with its last image; the padding rows are dropped.
        """
        padding = [batch[-1]] * (self.batch_size - len(batch))
        output = self._runner.run({INPUT_NAME: np.stack([*batch, *padding])})[OUTPUT_NAME]
        descriptors = output[: len(batch)].astype(np.float32)  # engine output is FP16
        return descriptors / np.linalg.norm(descriptors, axis=1, keepdims=True)
