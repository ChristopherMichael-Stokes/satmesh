"""`satmesh-track`: recover each photo's pose and the camera's lens from ordered photos."""

from collections import Counter
from pathlib import Path
from typing import Annotated

import numpy as np
import typer
from loguru import logger

from satmesh_cli.common import (
    DEFAULT_CACHE_DIR,
    BackendOption,
    CacheDirOption,
    MatcherChoice,
    StoreOption,
    XFeatBackend,
    build_matcher,
    log_photo_progress,
    reported_errors,
)
from satmesh_cli.corners import LatLon, parse_lat_lon
from satmesh_cli.reporting import run_log
from satmesh_core import geodetic_to_ecef
from satmesh_eval.camera import CameraPose
from satmesh_locate.megaloc import MegaLocDescriber
from satmesh_track.first_fix import (
    GridConfig,
    descriptor_cache_path,
    find_start,
    grid_descriptors,
    grid_poses,
    start_near,
)
from satmesh_track.lens import LensConfig
from satmesh_track.outputs import read_reference, write_outputs
from satmesh_track.photos import list_photos, load_photo
from satmesh_track.store_scene import StoreScene, load_store_scene
from satmesh_track.tracker import (
    PhotoImage,
    TrackConfig,
    TrackingContext,
    TrackingError,
    nominal_focal,
    track,
)

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def track_photos(  # noqa: PLR0913 (photos, store and seven settings)
    photos: Annotated[Path, typer.Argument(help="Directory of photos, in the order taken.")],
    store: StoreOption,
    *,
    out: Annotated[Path, typer.Option(help="Directory for the four output files.")] = Path(
        "track-report"
    ),
    start: Annotated[
        LatLon | None,
        typer.Option(
            parser=parse_lat_lon,
            metavar="LAT, LON",
            help="Rough position of the first photo; searches only around it instead of the store.",
        ),
    ] = None,
    radius_m: Annotated[float, typer.Option(help="Search radius around --start.")] = 150.0,
    mesh_error_m: Annotated[
        float, typer.Option(min=0.0, help="Assumed error of the mesh's heights, metres.")
    ] = LensConfig().mesh_error_m,
    reference: Annotated[
        Path | None,
        typer.Option(
            help="CSV of logged positions (photo, latitude_deg, longitude_deg, optional height_m) "
            "to plot and tabulate against the recovered track on the review page."
        ),
    ] = None,
    matcher: Annotated[MatcherChoice, typer.Option(help="Feature matcher.")] = MatcherChoice.XFEAT,
    backend: BackendOption = XFeatBackend.TENSORRT,
    xfeat_models: Annotated[
        Path | None, typer.Option(envvar="XFEAT_MODEL_DIR", help="xfeat-rt ONNX exports.")
    ] = None,
    megaloc_model: Annotated[
        Path | None,
        typer.Option(envvar="MEGALOC_MODEL", help="MegaLoc ONNX graph; needed without --start."),
    ] = None,
    cache_dir: CacheDirOption = DEFAULT_CACHE_DIR,
) -> None:
    """Recover each photo's pose and the camera's lens from the photos alone; writes four files."""
    settings = {
        "photos": photos,
        "out": out,
        "start": start,
        "radius_m": radius_m,
        "mesh_error_m": mesh_error_m,
        "reference": reference,
        "matcher": matcher.value,
        "backend": backend.value,
    }
    with reported_errors(TrackingError), run_log(store, "track", settings):
        loaded = [load_photo(path) for path in list_photos(photos)]
        images = [item.image for item in loaded]
        store_scene = load_store_scene(store)
        config = TrackConfig(lens=LensConfig(mesh_error_m=mesh_error_m))
        selected = build_matcher(matcher, backend, xfeat_models)
        context = TrackingContext(store_scene.scene, selected, config, log_photo_progress)
        if start is not None:
            ecef = np.array(geodetic_to_ecef().transform(start[1], start[0], 0.0))
            centre = store_scene.scene.area.to_enu(ecef[None, :])[0][:2]
            first_pose = start_near(images[0], centre, radius_m, context)
        elif megaloc_model is not None:
            first_pose = _store_wide_start(
                images[0], store_scene, context, megaloc_model, cache_dir
            )
        else:
            msg = "searching the store needs --megaloc-model (or MEGALOC_MODEL), or give --start"
            raise typer.BadParameter(msg)
        result = track(images, first_pose, context)
        logged = read_reference(reference) if reference is not None else []
        write_outputs(out, result, loaded, store_scene.scene.area, logged)
        counts = Counter(p.status.value for p in result.photos)
        lens = result.lens.lens
        typer.echo(
            f"{dict(counts)}; focal {lens.focal_px:.1f} px "
            f"(1 sigma {result.lens.focal_sigma_px:.1f} at the working size), "
            f"k1 {lens.k1:.4f}, k2 {lens.k2:.4f}"
        )
        typer.echo(out)


def _store_wide_start(
    photo: PhotoImage,
    store_scene: StoreScene,
    context: TrackingContext,
    model: Path,
    cache_dir: Path,
) -> CameraPose:
    """First fix with no prior: the MegaLoc-ranked grid over the whole store, descriptors cached."""
    describer = MegaLocDescriber(model)
    grid_config = GridConfig()
    grid = grid_poses(grid_config, store_scene.bounds, store_scene.scene.ground_height)
    height, width = photo.rgb.shape[:2]
    cache = descriptor_cache_path(
        cache_dir / "first-fix", store_scene.key, grid_config, (width, height), model
    )
    logger.info("describing {} grid renders (cached after the first run)", len(grid))
    descriptors = grid_descriptors(
        grid,
        store_scene.scene,
        describer,
        (width, height),
        nominal_focal(width),
        cache,
        context.config.max_range_m,
    )
    return find_start(photo, grid, descriptors, describer, context, grid_config.verify_top_k)
