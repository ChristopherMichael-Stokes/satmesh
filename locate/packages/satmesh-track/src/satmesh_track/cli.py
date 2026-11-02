"""`satmesh-track`: recover each photo's pose and the camera's lens from ordered photos."""

from collections import Counter
from pathlib import Path
from typing import Annotated

import numpy as np
import typer

from satmesh_cli.common import (
    BackendOption,
    MatcherChoice,
    StoreOption,
    XFeatBackend,
    build_matcher,
    log_photo_progress,
    reported_errors,
)
from satmesh_cli.corners import LatLon, parse_lat_lon
from satmesh_cli.reporting import run_log
from satmesh_core import EnuFrame, geodetic_to_ecef
from satmesh_locate.events import EVENTS_FILE, EventWriter, Interval, PositionPrior
from satmesh_locate.megaloc import MegaLocDescriber
from satmesh_track.first_fix import first_fix
from satmesh_track.lens import LensConfig
from satmesh_track.outputs import read_reference, write_outputs
from satmesh_track.photos import list_photos, load_photo
from satmesh_track.priors import FirstFixConfig, load_config, parse_interval, with_priors
from satmesh_track.store_scene import load_store_scene
from satmesh_track.tracker import TrackConfig, TrackingContext, TrackingError, track

WINDOW_HELP = (
    "Give about twice the expected error: a heading hint 30 degrees off, with the truth at the "
    "window's edge, lost most of the recall."
)
RELAXED_HELP = "Dropped if no place verifies within it."

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def track_photos(  # noqa: PLR0913 (photos, store and twelve settings)
    photos: Annotated[Path, typer.Argument(help="Directory of photos, in the order taken.")],
    store: StoreOption,
    *,
    out: Annotated[
        Path, typer.Option(help="Directory for the output files and events.jsonl.")
    ] = Path("track-report"),
    priors: Annotated[
        Path | None,
        typer.Option(
            help="TOML file of first-fix settings and priors; the options below override it."
        ),
    ] = None,
    start: Annotated[
        LatLon | None,
        typer.Option(
            parser=parse_lat_lon,
            metavar="LAT, LON",
            help="Rough position of the first photo: the centre of the position prior.",
        ),
    ] = None,
    radius_m: Annotated[
        float,
        typer.Option(
            min=0.0, help=f"Radius of the position prior, metres. {WINDOW_HELP} {RELAXED_HELP}"
        ),
    ] = 150.0,
    heading: Annotated[
        Interval | None,
        typer.Option(
            parser=parse_interval,
            metavar="CENTRE+-HALF",
            help=f"Heading prior, degrees clockwise from north. {WINDOW_HELP} {RELAXED_HELP}",
        ),
    ] = None,
    pitch: Annotated[
        Interval | None,
        typer.Option(
            parser=parse_interval,
            metavar="CENTRE+-HALF",
            help=f"Pitch prior, degrees, negative looking down. {WINDOW_HELP} {RELAXED_HELP}",
        ),
    ] = None,
    height: Annotated[
        Interval | None,
        typer.Option(
            parser=parse_interval,
            metavar="CENTRE+-HALF",
            help="Height prior, metres above the ground: limits the fine search heights and raises "
            "the coarse ones (90 and 110 m) when its lower end is above 90 m.",
        ),
    ] = None,
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
        typer.Option(envvar="MEGALOC_MODEL", help="MegaLoc ONNX graph of the first fix."),
    ] = None,
) -> None:
    """Recover each photo's pose and the camera's lens from the photos alone; writes five files."""
    settings = {
        "photos": photos,
        "out": out,
        "priors": priors,
        "start": start,
        "radius_m": radius_m,
        "heading": heading,
        "pitch": pitch,
        "height": height,
        "mesh_error_m": mesh_error_m,
        "reference": reference,
        "matcher": matcher.value,
        "backend": backend.value,
    }
    if megaloc_model is None:
        msg = "the first fix needs --megaloc-model (or MEGALOC_MODEL)"
        raise typer.BadParameter(msg)
    with reported_errors(TrackingError), run_log(store, "track", settings):
        loaded = [load_photo(path) for path in list_photos(photos)]
        images = [item.image for item in loaded]
        store_scene = load_store_scene(store)
        config = TrackConfig(lens=LensConfig(mesh_error_m=mesh_error_m))
        selected = build_matcher(matcher, backend, xfeat_models)
        context = TrackingContext(store_scene.scene, selected, config, log_photo_progress)
        fix_config = with_priors(
            FirstFixConfig() if priors is None else load_config(priors),
            position=None
            if start is None
            else _position_prior(start, radius_m, store_scene.scene.area),
            heading_deg=heading,
            pitch_deg=pitch,
            height_m=height,
        )
        out.mkdir(parents=True, exist_ok=True)
        events = out / EVENTS_FILE
        events.unlink(missing_ok=True)  # a run's file holds that run only
        with EventWriter(events) as writer:
            fix = first_fix(
                images,
                store_scene,
                MegaLocDescriber(megaloc_model),
                context,
                config=fix_config,
                emit=writer.write,
            )
        result = track(images, fix.pose, context)
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


def _position_prior(start: LatLon, radius_m: float, area: EnuFrame) -> PositionPrior:
    """A circle around `start` in the store's ENU frame."""
    ecef = np.array(geodetic_to_ecef().transform(start.lon, start.lat, 0.0))
    east, north, _ = area.to_enu(ecef[None, :])[0]
    return PositionPrior(east_m=float(east), north_m=float(north), radius_m=radius_m)
