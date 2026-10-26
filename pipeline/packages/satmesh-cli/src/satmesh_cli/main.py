"""Typer app: `satmesh build` fills a tile store, `satmesh export` writes it for a consumer."""

import math
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import httpx
import mercantile
import typer
from loguru import logger
from platformdirs import user_cache_dir

from satmesh_cli.corners import LatLon, corners_to_bng_inside, corners_to_wgs84, parse_lat_lon
from satmesh_cli.reporting import file_log, run_log
from satmesh_core import BRITISH_NATIONAL_GRID, Aoi, GridMissingError
from satmesh_data import EsriClient, LidarCheckError, PlaceholderTileError, new_client
from satmesh_eval.registration import measure_correction
from satmesh_eval.report import (
    heights_report,
    load_site,
    offset_report,
    smoothness_report,
    texture_report,
    visibility_report,
)
from satmesh_mesh import DEFAULT_MAX_ERROR_M
from satmesh_tiles import (
    ESRI_TILES_PER_LEAF_SIDE,
    POSITIONAL_ERROR_FILE,
    apply_correction,
    build_store,
    export_3dtiles,
    export_area_glb,
    export_gazebo,
    plan_tiles,
    read_record,
    stored_tiles,
    write_positional_error,
)

DEFAULT_CACHE_DIR = Path(user_cache_dir("satmesh"))
DEFAULT_ESRI_REQUESTS_PER_SECOND = 1.0
SECONDS_PER_MINUTE = 60

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Tiled terrain meshes.")
export_app = typer.Typer(no_args_is_help=True, help="Write a store for a consumer.")
app.add_typer(export_app, name="export")
eval_app = typer.Typer(no_args_is_help=True, help="Score a store against EA lidar and aerial data.")
app.add_typer(eval_app, name="eval")

StoreOption = Annotated[Path, typer.Option(help="Tile store directory.")]
CacheDirOption = Annotated[
    Path,
    typer.Option(envvar="SATMESH_CACHE_DIR", help="Fetched tiles and DTMs, reused across runs."),
]
EsriRateOption = Annotated[
    float,
    typer.Option(
        min=0.1,
        help="Esri tile requests per second, shared by all fetches. Esri publishes no limit.",
    ),
]
NorthWestOption = Annotated[
    LatLon,
    typer.Option(
        parser=parse_lat_lon, metavar="LAT, LON", help="North-west corner, as copied from a map."
    ),
]
SouthEastOption = Annotated[
    LatLon,
    typer.Option(
        parser=parse_lat_lon, metavar="LAT, LON", help="South-east corner, as copied from a map."
    ),
]


@contextmanager
def reported_errors() -> Generator[None]:
    """Turn the failures a user can act on into one stderr line and exit code 1."""
    try:
        yield
    except (
        ValueError,
        GridMissingError,
        PlaceholderTileError,
        LidarCheckError,
        httpx.HTTPError,
    ) as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(1) from e


@app.command()
def build(  # noqa: PLR0913, PLR0917 (the two corners, store and three tuning options)
    nw: NorthWestOption,
    se: SouthEastOption,
    store: StoreOption,
    cache_dir: Annotated[
        Path,
        typer.Option(
            envvar="SATMESH_CACHE_DIR", help="Fetched tiles and DTMs, reused across runs."
        ),
    ] = DEFAULT_CACHE_DIR,
    max_error_m: Annotated[
        float, typer.Option(help="Largest height error of a finest-level mesh, in metres.")
    ] = DEFAULT_MAX_ERROR_M,
    esri_requests_per_second: EsriRateOption = DEFAULT_ESRI_REQUESTS_PER_SECOND,
) -> None:
    """Fetch imagery and terrain for an area and write its tiles to the store; resumable."""
    settings = {
        "nw": nw,
        "se": se,
        "cache_dir": cache_dir,
        "max_error_m": max_error_m,
        "esri_requests_per_second": esri_requests_per_second,
    }
    with reported_errors(), run_log(store, "build", settings) as report, new_client() as http:
        esri = EsriClient(http, cache_dir, min_interval_s=1 / esri_requests_per_second)
        plan = plan_tiles(corners_to_wgs84(nw, se), esri)
        tiles = len(plan.leaves) * ESRI_TILES_PER_LEAF_SIDE**2
        eta_min = math.ceil(tiles / esri_requests_per_second / SECONDS_PER_MINUTE)
        logger.info(
            "{} leaves at z{}, {} parents; up to {} Esri tiles, about {} min if none are cached",
            len(plan.leaves),
            plan.leaf_zoom,
            len(plan.children),
            tiles,
            eta_min,
        )
        summary = build_store(
            plan,
            store,
            esri=esri,
            http=http,
            cache_dir=cache_dir,
            report=report,
            max_error_m=max_error_m,
        )
        file_log.info("built {} nodes, skipped {}", summary.built, summary.skipped)
    typer.echo(f"built {summary.built} nodes, skipped {summary.skipped} already in {store}")


@app.command()
def correct(
    store: StoreOption,
    cache_dir: Annotated[
        Path,
        typer.Option(
            envvar="SATMESH_CACHE_DIR", help="Fetched tiles and point clouds, reused across runs."
        ),
    ] = DEFAULT_CACHE_DIR,
    esri_requests_per_second: EsriRateOption = DEFAULT_ESRI_REQUESTS_PER_SECOND,
) -> None:
    """Move the store's imagery to its true position using EA lidar intensity; repeatable.

    Esri imagery sits 0.2 to 2.8 m from true position in England, by a different amount in
    different places. The shift is measured per 1 km cell where lidar and imagery agree well
    enough, applied to every node, and the remaining error bound is recorded for each node.
    Cells that cannot be measured keep the imagery as it is and carry the survey's largest
    displacement as their bound. Downloads EA point clouds (about 100 to 500 MB per 5 km square).
    """
    settings = {"cache_dir": cache_dir, "esri_requests_per_second": esri_requests_per_second}
    with reported_errors(), run_log(store, "correct", settings) as report, new_client() as http:
        tiles = stored_tiles(store)
        if not tiles:
            msg = f"no nodes in store {store}"
            raise ValueError(msg)
        finest = max(tile.z for tile in tiles)
        zoom = read_record(store, next(t for t in sorted(tiles) if t.z == finest)).imagery.zoom
        area = _store_area([t for t in tiles if t.z == finest])
        logger.info(
            "measuring over {} nodes at Esri z{}; point clouds are downloaded on first use",
            len(tiles),
            zoom,
        )
        esri = EsriClient(http, cache_dir, min_interval_s=1 / esri_requests_per_second)
        field = measure_correction(area, zoom, esri, http, cache_dir, report)
        summary = apply_correction(store, field, report)
        measured = [c for c in field.cells if c.status == "corrected"]
        result = (
            f"{len(measured)} of {len(field.cells)} cells corrected; "
            f"{summary.corrected} nodes corrected, {summary.uncorrected} left as they were "
            f"(bound {field.uncorrected_error_bound_m} m), {summary.rewritten} rewritten"
        )
        file_log.info(result)
    typer.echo(result)


@export_app.command("3dtiles")
def export_tileset(store: StoreOption) -> None:
    """Write tileset.json into the store: serve the store directory to open it in CesiumJS."""
    with reported_errors(), run_log(store, "export 3dtiles", {}):
        tileset = export_3dtiles(store)
        write_positional_error(store, store / POSITIONAL_ERROR_FILE)
        typer.echo(tileset)


@export_app.command("gazebo")
def export_world(
    store: StoreOption,
    out: Annotated[Path, typer.Option(help="Output directory for world.sdf and meshes/.")],
    performer: Annotated[
        str | None,
        typer.Option(help="Robot model name; adds one level per tile so tiles load by distance."),
    ] = None,
) -> None:
    """Write a Gazebo world with one static model per finest-level tile."""
    with reported_errors(), run_log(store, "export gazebo", {"out": out, "performer": performer}):
        world = export_gazebo(store, out, performer)
        write_positional_error(store, out / POSITIONAL_ERROR_FILE)
        typer.echo(world)


@export_app.command("glb")
def export_glb(
    store: StoreOption,
    out: Annotated[Path, typer.Option(help="Output GLB path.")],
) -> None:
    """Write every finest-level tile as one GLB in a single local frame, for renderers."""
    with reported_errors(), run_log(store, "export glb", {"out": out}):
        export_area_glb(store, out)
        write_positional_error(store, out.with_suffix(f".{POSITIONAL_ERROR_FILE}"))
        typer.echo(out)


@eval_app.command("heights")
def eval_heights(
    store: StoreOption,
    nw: NorthWestOption,
    se: SouthEastOption,
    cache_dir: CacheDirOption = DEFAULT_CACHE_DIR,
) -> None:
    """Height error of the store against the EA first-return DSM, by stratum."""
    box = corners_to_bng_inside(nw, se)
    settings = {"nw": nw, "se": se, "bng_box": box, "cache_dir": cache_dir}
    with reported_errors(), run_log(store, "eval heights", settings), new_client() as http:
        typer.echo(heights_report(store, load_site(box, cache_dir, http)))


@eval_app.command("smoothness")
def eval_smoothness(
    store: StoreOption,
    nw: NorthWestOption,
    se: SouthEastOption,
    cache_dir: CacheDirOption = DEFAULT_CACHE_DIR,
) -> None:
    """Facet normal error, terrace and grid-alignment scores of the store."""
    box = corners_to_bng_inside(nw, se)
    settings = {"nw": nw, "se": se, "bng_box": box, "cache_dir": cache_dir}
    with reported_errors(), run_log(store, "eval smoothness", settings), new_client() as http:
        typer.echo(smoothness_report(store, load_site(box, cache_dir, http)))


@eval_app.command("visibility")
def eval_visibility(  # noqa: PLR0913 (store, area, cache and the three camera settings)
    store: StoreOption,
    nw: NorthWestOption,
    se: SouthEastOption,
    cache_dir: CacheDirOption = DEFAULT_CACHE_DIR,
    *,
    cameras: Annotated[int, typer.Option(help="Random cameras per rig.")] = 30,
    range_m: Annotated[
        float, typer.Option(help="Range limit; cameras keep this far from the box edge.")
    ] = 150.0,
    seed: Annotated[int, typer.Option(help="Seed of the camera draw.")] = 1,
) -> None:
    """Pixel agreement and raised-object visibility from random cameras, against the DSM."""
    box = corners_to_bng_inside(nw, se)
    settings = {
        "nw": nw,
        "se": se,
        "bng_box": box,
        "cache_dir": cache_dir,
        "cameras": cameras,
        "range_m": range_m,
        "seed": seed,
    }
    with reported_errors(), run_log(store, "eval visibility", settings), new_client() as http:
        site = load_site(box, cache_dir, http)
        typer.echo(visibility_report(store, site, cameras=cameras, range_m=range_m, seed=seed))


@eval_app.command("offset")
def eval_offset(
    aerial: Annotated[Path, typer.Option(help="EA aerial RGB GeoTIFF in BNG covering the box.")],
    nw: NorthWestOption,
    se: SouthEastOption,
    zoom: Annotated[int, typer.Option(help="Esri zoom level to compare.")],
    cache_dir: CacheDirOption = DEFAULT_CACHE_DIR,
) -> None:
    """Displacement of Esri imagery from an EA aerial over the box."""
    box = corners_to_bng_inside(nw, se)
    with reported_errors(), new_client() as http:
        typer.echo(offset_report(aerial, box, zoom, EsriClient(http, cache_dir)))


@eval_app.command("texture")
def eval_texture(
    aerial: Annotated[Path, typer.Option(help="EA aerial RGB GeoTIFF in BNG covering the box.")],
    nw: NorthWestOption,
    se: SouthEastOption,
    zoom: Annotated[int, typer.Option(help="Esri zoom level to compare.")],
    cache_dir: CacheDirOption = DEFAULT_CACHE_DIR,
) -> None:
    """Esri detail power against an EA aerial by frequency band, away from raised objects."""
    box = corners_to_bng_inside(nw, se)
    with reported_errors(), new_client() as http:
        site = load_site(box, cache_dir, http)
        typer.echo(texture_report(aerial, box, zoom, EsriClient(http, cache_dir), site))


def _store_area(finest: list[mercantile.Tile]) -> Aoi:
    """Return the whole-metre BNG box around the finest-level footprint of a store.

    Web Mercator and BNG axes differ by up to a few degrees, so the box also takes in strips just
    outside the store; Esri tiles there are fetched and cached once.
    """
    bounds = [mercantile.xy_bounds(tile) for tile in finest]
    footprint = Aoi(
        crs="EPSG:3857",
        west=min(b.left for b in bounds),
        south=min(b.bottom for b in bounds),
        east=max(b.right for b in bounds),
        north=max(b.top for b in bounds),
    )
    west, south, east, north = footprint.bounds_in(BRITISH_NATIONAL_GRID)
    return Aoi(
        crs=BRITISH_NATIONAL_GRID,
        west=math.floor(west),
        south=math.floor(south),
        east=math.ceil(east),
        north=math.ceil(north),
    )
