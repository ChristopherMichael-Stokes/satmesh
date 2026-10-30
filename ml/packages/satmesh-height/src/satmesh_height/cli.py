"""`satmesh-height refine`: refine a coarse DSM from a contract input directory."""

from pathlib import Path
from typing import Annotated

import torch
import typer

from satmesh_height.config import PixTransformConfig
from satmesh_height.contract import Method, OutputSidecar, read_inputs, write_outputs
from satmesh_height.workflow import run_method

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Refine coarse DSMs.")


def resolve_device(name: str) -> torch.device:
    """`auto` is cuda when available, else cpu; any other name is passed to torch."""
    if name == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(name)


@app.callback()
def main() -> None:
    """Refine coarse DSMs with a guide image."""


@app.command()
def refine(  # noqa: PLR0913, PLR0917
    input_dir: Annotated[
        Path, typer.Argument(exists=True, file_okay=False, help="Input directory.")
    ],
    output_dir: Annotated[Path, typer.Argument(file_okay=False, help="Output directory.")],
    method: Annotated[Method, typer.Option("--variant", help="P0, A, B, C or C+B.")],
    training_extent_m: Annotated[
        float, typer.Option(min=0, help="Side of each independently trained window, metres.")
    ],
    seeds: Annotated[list[int] | None, typer.Option(help="Seed; repeat for several.")] = None,
    steps: Annotated[
        int | None, typer.Option(help="Optimiser steps; default is published.")
    ] = None,
    device: Annotated[str, typer.Option(help="auto, cpu or cuda.")] = "auto",
) -> None:
    """Refine INPUT_DIR's coarse DSM to the guide's grid and write it to OUTPUT_DIR."""
    inputs = read_inputs(input_dir)
    config = PixTransformConfig() if steps is None else PixTransformConfig(steps=steps)
    seed_tuple = (0,) if seeds is None else tuple(seeds)
    torch_device = resolve_device(device)
    typer.echo(f"{method} on {torch_device}, seeds {seed_tuple}, {config.steps} steps")
    result = run_method(
        inputs, method, seed_tuple, training_extent_m, config=config, device=torch_device
    )
    sidecar = OutputSidecar(
        method=method,
        config=config,
        seeds=seed_tuple,
        training_extent_m=training_extent_m,
        factor=inputs.sidecar.factor,
        grid=inputs.sidecar.grid,
        crs=inputs.sidecar.crs,
        has_spread=result.spread is not None,
        source_files=inputs.sidecar.source_files,
    )
    write_outputs(output_dir, result.height, result.spread, sidecar)
    typer.echo(f"wrote {output_dir}")
