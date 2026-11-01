"""Options, matcher selection and error reporting shared by the `satmesh` commands and its tools."""

from collections.abc import Generator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import httpx
import typer
from loguru import logger
from platformdirs import user_cache_dir

from satmesh_core import GridMissingError
from satmesh_data import EsriQueryError, LidarCheckError, PlaceholderTileError
from satmesh_eval.matching import Matcher, onnx_matcher, sift_match, tensorrt_matcher

DEFAULT_CACHE_DIR = Path(user_cache_dir("satmesh"))

StoreOption = Annotated[Path, typer.Option(help="Tile store directory.")]
CacheDirOption = Annotated[
    Path,
    typer.Option(envvar="SATMESH_CACHE_DIR", help="Fetched tiles and DTMs, reused across runs."),
]


class MatcherChoice(StrEnum):
    """Feature matcher of `eval localise` and `track`."""

    XFEAT = "xfeat"
    SIFT = "sift"


class XFeatBackend(StrEnum):
    """Where XFeat and LighterGlue run."""

    TENSORRT = "tensorrt"
    ONNX = "onnx"


BackendOption = Annotated[
    XFeatBackend,
    typer.Option(
        help="Where --matcher xfeat runs: tensorrt (NVIDIA GPU, FP16 exports) or onnx (CPU)."
    ),
]


@contextmanager
def reported_errors(*also: type[Exception]) -> Generator[None]:
    """Turn the failures a user can act on into one stderr line and exit code 1.

    `also` adds exception types of the calling tool to the ones every command reports.
    """
    try:
        yield
    except (
        ValueError,
        GridMissingError,
        PlaceholderTileError,
        LidarCheckError,
        EsriQueryError,
        httpx.HTTPError,
        RuntimeError,
        *also,
    ) as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(1) from e


def build_matcher(
    choice: MatcherChoice, backend: XFeatBackend, xfeat_models: Path | None
) -> Matcher:
    """The feature matcher for a command's `--matcher`, `--backend` and `--xfeat-models`."""
    if choice == MatcherChoice.SIFT:
        return sift_match
    if xfeat_models is None:
        msg = "--matcher xfeat needs --xfeat-models or XFEAT_MODEL_DIR"
        raise typer.BadParameter(msg)
    if backend == XFeatBackend.ONNX:
        return onnx_matcher(xfeat_models)
    try:
        return tensorrt_matcher(xfeat_models)
    except ModuleNotFoundError as error:
        msg = f"--backend tensorrt needs the tensorrt extra ({error}); sync with --all-extras"
        raise typer.BadParameter(msg) from error


def log_photo_progress(done: int, total: int) -> None:
    """Progress callback of the photo runs."""
    logger.info("localised photo {}/{}", done, total)
