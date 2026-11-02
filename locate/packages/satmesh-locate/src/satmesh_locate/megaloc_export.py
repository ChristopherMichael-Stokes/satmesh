"""Offline conversion of the MegaLoc ONNX graph to an FP16 TensorRT engine of fixed batch size.

Run once per MegaLoc export, TensorRT version and GPU; the pipeline then reads the engine file.
TensorRT 11 networks are strongly typed, so the FP16 comes from the tensor types of the ONNX graph:
ONNX Runtime's converter writes them, keeping the graph's inputs and outputs in FP32.
"""

from pathlib import Path
from typing import Annotated

import onnx
import typer
from cuda.core import Device  # ty: ignore[unresolved-import]  # cuda.core exports it lazily; ty cannot see it
from onnxruntime.transformers.float16 import convert_float_to_float16
from xfeat_trt.engine import load_or_build_engine

from satmesh_locate.megaloc import DEFAULT_BATCH_SIZE
from satmesh_locate.megaloc_engine import CUDA_DEVICE_ORDINAL

SCATTER_OPERATORS = frozenset({"ScatterND", "ScatterElements"})
DEFAULT_REDUCTION = b"none"


def export_fp16_engine(megaloc_onnx: Path, out_dir: Path, batch_size: int) -> Path:
    """Write the FP16 graph and its engine for `batch_size` images into `out_dir`.

    An engine already built for the same graph, TensorRT version and GPU is reused.

    Returns:
        The path of the engine file.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    model = convert_float_to_float16(onnx.load(megaloc_onnx), keep_io_types=True)
    _drop_default_scatter_reduction(model)
    _fix_batch(model, batch_size)
    graph_path = out_dir / f"{megaloc_onnx.stem}_fp16_b{batch_size}.onnx"
    onnx.save(model, graph_path)
    device = Device(CUDA_DEVICE_ORDINAL)
    return load_or_build_engine(graph_path, device, cache_dir=out_dir).path


def _drop_default_scatter_reduction(model: onnx.ModelProto) -> None:
    """Remove `reduction="none"`, the attribute default, which the TensorRT ONNX parser rejects."""
    for node in model.graph.node:
        if node.op_type not in SCATTER_OPERATORS:
            continue
        kept = [
            attribute
            for attribute in node.attribute
            if not (attribute.name == "reduction" and attribute.s == DEFAULT_REDUCTION)
        ]
        del node.attribute[:]
        node.attribute.extend(kept)


def _fix_batch(model: onnx.ModelProto, batch_size: int) -> None:
    """Make the batch dimension static; the engine builder takes no optimisation profile."""
    for tensor in (*model.graph.input, *model.graph.output):
        tensor.type.tensor_type.shape.dim[0].dim_value = batch_size
    del model.graph.value_info[:]  # intermediate shapes still name the dynamic batch


app = typer.Typer(add_completion=False)


@app.command()
def main(
    model: Annotated[
        Path, typer.Argument(envvar="MEGALOC_MODEL", help="MegaLoc ONNX graph (FP32).")
    ],
    out_dir: Annotated[Path, typer.Argument(help="Directory for the FP16 graph and the engine.")],
    batch_size: Annotated[
        int, typer.Option(help="Images per engine execution; fixed at build time.")
    ] = DEFAULT_BATCH_SIZE,
) -> None:
    """Build the FP16 TensorRT engine once; point MEGALOC_MODEL at the printed file afterwards."""
    typer.echo(export_fp16_engine(model, out_dir, batch_size))
