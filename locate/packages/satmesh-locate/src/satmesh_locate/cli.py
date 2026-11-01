"""`satmesh-locate`: rank the places of a directory of rendered views against a photo."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import cv2
import numpy as np
import numpy.typing as npt
import typer

from satmesh_locate.megaloc import Device, MegaLocDescriber
from satmesh_locate.places import iter_render_chunks, load_cells, top_places

DEFAULT_PLACES = 6
DEFAULT_SEPARATION_M = 100.0

app = typer.Typer(add_completion=False, no_args_is_help=True)


def read_rgb(path: Path) -> npt.NDArray[np.uint8]:
    """The image at `path` as an RGB `uint8` array.

    Raises:
        FileNotFoundError: OpenCV cannot read the file as an image.
    """
    bgr = cv2.imread(str(path))
    if bgr is None:
        message = f"cannot read image {path}"
        raise FileNotFoundError(message)
    return np.asarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), dtype=np.uint8)


@app.command()
def rank(  # noqa: PLR0913, PLR0917 (three paths, the model and three options)
    renders: Annotated[Path, typer.Argument(help="Directory with meta.npy and renders_*.npy.")],
    photo: Annotated[Path, typer.Argument(help="Photo to place.")],
    out: Annotated[Path, typer.Argument(help="JSON file for the ranked places.")],
    model: Annotated[Path, typer.Option(envvar="MEGALOC_MODEL", help="MegaLoc ONNX graph.")],
    places: Annotated[int, typer.Option(help="Places to keep.")] = DEFAULT_PLACES,
    separation_m: Annotated[
        float, typer.Option(help="Places are more than this far apart, in metres.")
    ] = DEFAULT_SEPARATION_M,
    device: Annotated[Device, typer.Option(help="cpu, cuda, or auto.")] = Device.AUTO,
) -> None:
    """Describe the renders and the photo, then write the best places, most similar first."""
    describer = MegaLocDescriber(model, device)
    database = np.concatenate([describer.describe(c) for c in iter_render_chunks(renders)])
    query = describer.describe([read_rgb(photo)])[0]
    ranked = top_places(database @ query, load_cells(renders), places, separation_m)
    out.write_text(json.dumps([asdict(place) for place in ranked], indent=1))
    typer.echo(f"{len(database)} views described on {describer.device}; {len(ranked)} places")
