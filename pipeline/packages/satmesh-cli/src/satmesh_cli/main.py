"""Typer app: `satmesh build` fills a tile store, `satmesh export` writes it for a consumer."""

import math
from collections import Counter
from collections.abc import Generator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import httpx
import mercantile
import numpy as np
import typer
from loguru import logger
from platformdirs import user_cache_dir

from satmesh_cli.corners import LatLon, corners_to_bng_inside, corners_to_wgs84, parse_lat_lon
from satmesh_cli.grids import Region, grid_files, install_grids
from satmesh_cli.reporting import file_log, run_log
from satmesh_core import (
    BNG_ODN,
    BRITISH_NATIONAL_GRID,
    Aoi,
    GridMissingError,
    geodetic_to_ecef,
)
from satmesh_data import (
    EsriClient,
    EsriQueryError,
    LidarCheckError,
    PlaceholderTileError,
    fetch_scene_map,
    new_client,
)
from satmesh_eval.camera import CameraPose
from satmesh_eval.harness import (
    DEFAULT_MAX_RANGE_M,
    Reference,
    ReferenceRenderers,
    RunSettings,
    run_photos,
)
from satmesh_eval.localise import MINIMUM_INLIERS
from satmesh_eval.localise_report import report_json
from satmesh_eval.matching import Matcher, onnx_matcher, sift_match, tensorrt_matcher
from satmesh_eval.poses import read_pose_file
from satmesh_eval.registration import measure_correction
from satmesh_eval.report import (
    heights_report,
    load_site,
    offset_report,
    smoothness_report,
    texture_report,
    visibility_report,
)
from satmesh_eval.review_page import review_page
from satmesh_eval.scene_lean import correction_field
from satmesh_mesh import DEFAULT_MAX_ERROR_M
from satmesh_tiles import (
    ESRI_TILES_PER_LEAF_SIDE,
    POSITIONAL_ERROR_FILE,
    CorrectionField,
    CorrectionSummary,
    apply_correction,
    build_store,
    export_3dtiles,
    export_area_glb,
    export_gazebo,
    plan_tiles,
    read_record,
    require_current_correction,
    stored_tiles,
    write_positional_error,
)
from satmesh_track.first_fix import (
    GridConfig,
    descriptor_cache_path,
    find_start,
    grid_descriptors,
    grid_poses,
    start_near,
)
from satmesh_track.lens import LensConfig
from satmesh_track.outputs import write_outputs
from satmesh_track.photos import list_photos, load_photo
from satmesh_track.retrieval import MegaLocDescriber
from satmesh_track.store_scene import StoreScene, load_store_scene
from satmesh_track.tracker import (
    PhotoImage,
    TrackConfig,
    TrackingContext,
    TrackingError,
    nominal_focal,
    track,
)

DEFAULT_CACHE_DIR = Path(user_cache_dir("satmesh"))
DEFAULT_ESRI_REQUESTS_PER_SECOND = 20.0
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
def reported_errors() -> Generator[None]:
    """Turn the failures a user can act on into one stderr line and exit code 1."""
    try:
        yield
    except (
        ValueError,
        GridMissingError,
        PlaceholderTileError,
        LidarCheckError,
        EsriQueryError,
        TrackingError,
        httpx.HTTPError,
        RuntimeError,
    ) as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(1) from e


@app.command()
def grids(
    region: Annotated[
        list[Region] | None,
        typer.Option(help="Region to fetch grids for, repeatable; omitted means all."),
    ] = None,
    dry_run: Annotated[bool, typer.Option(help="List the grid files without downloading.")] = False,  # noqa: FBT002 (typer flag)
) -> None:
    """Download the PROJ datum grids the regions' height sources need."""
    files = grid_files(region or [])
    if dry_run:
        typer.echo("\n".join(files))
        return
    install_grids(files)
    typer.echo(f"{len(files)} grids installed")


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
    """Fetch imagery (at most 30 cm fine) and terrain for an area into the store; resumable."""
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
        logger.info(
            "elevation {} ({}); imagery {}, stated accuracy {} m",
            plan.source.name,
            "DSM also serves as ground" if plan.source.ground_is_surface else "DSM and DTM",
            plan.imagery.source_info,
            plan.imagery.accuracy_m,
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


@app.command("track")
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
        "matcher": matcher.value,
        "backend": backend.value,
    }
    with reported_errors(), run_log(store, "track", settings):
        loaded = [load_photo(path) for path in list_photos(photos)]
        images = [item.image for item in loaded]
        store_scene = load_store_scene(store)
        config = TrackConfig(lens=LensConfig(mesh_error_m=mesh_error_m))
        selected = _matcher(matcher, backend, xfeat_models)
        context = TrackingContext(store_scene.scene, selected, config, _log_photo_progress)
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
        write_outputs(out, result, loaded, store_scene.scene.area)
        counts = Counter(p.status.value for p in result.photos)
        lens = result.lens.lens
        typer.echo(
            f"{dict(counts)}; focal {lens.focal_px:.1f} px "
            f"(1 sigma {result.lens.focal_sigma_px:.1f} at the working size), "
            f"k1 {lens.k1:.4f}, k2 {lens.k2:.4f}"
        )
        typer.echo(out)


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
    *,
    lean: Annotated[
        bool,
        typer.Option(
            "--lean/--no-lean",
            help="Also measure and remove each Esri scene's lean of roofs and tree crowns.",
        ),
    ] = True,
) -> None:
    """Move the store's imagery to its true position using EA lidar; repeatable.

    Esri imagery sits 0.2 to 2.8 m from true position in England, by a different amount in
    different places, and roofs and tree crowns lean further, by an amount that grows with their
    height. The ground shift is measured per 1 km cell from lidar intensity. With the lean (the
    default), each Esri capture's ground shift and lean are also fitted from roofs matched against
    the lidar surface across the whole store, and applied wherever the fit is good enough; other
    places keep the cell's ground shift. Cells that cannot be measured keep the imagery as it is
    and carry the survey's largest displacement as their bound. Downloads EA point clouds (about
    100 to 500 MB per 5 km square) and, with the lean, EA DSM and DTM per cell.
    """
    settings = {
        "cache_dir": cache_dir,
        "esri_requests_per_second": esri_requests_per_second,
        "lean": lean,
    }
    with reported_errors(), run_log(store, "correct", settings) as report, new_client() as http:
        require_current_correction(store)
        tiles = stored_tiles(store)
        if not tiles:
            msg = f"no nodes in store {store}"
            raise ValueError(msg)
        finest = max(tile.z for tile in tiles)
        first = read_record(store, next(t for t in sorted(tiles) if t.z == finest))
        if first.vertical_crs != BNG_ODN:
            msg = (
                f"position correction needs EA lidar, which covers England only; this store's "
                f"heights are {first.vertical_crs}"
            )
            raise ValueError(msg)
        zoom = first.imagery.zoom
        area = _store_area([t for t in tiles if t.z == finest])
        logger.info(
            "measuring over {} nodes at Esri z{}; point clouds are downloaded on first use",
            len(tiles),
            zoom,
        )
        esri = EsriClient(http, cache_dir, min_interval_s=1 / esri_requests_per_second)
        scene_map = (
            fetch_scene_map(esri, area, zoom, cache_dir).in_crs(BRITISH_NATIONAL_GRID)
            if lean
            else None
        )
        if scene_map is not None:
            logger.info("Esri {}: {} scenes at z{}", scene_map.release, len(scene_map.scenes), zoom)
        measurement = measure_correction(area, zoom, esri, http, cache_dir, report, with_roofs=lean)
        field = correction_field(measurement, scene_map, report)
        summary = apply_correction(store, field, scene_map, report)
        typer.echo(_correction_result(field, summary))


def _correction_result(field: CorrectionField, summary: CorrectionSummary) -> str:
    measured = sum(c.status == "corrected" for c in field.cells)
    lines = [f"{measured} of {len(field.cells)} cells corrected"]
    lines += [
        f"scene {s.scene}: lean {s.status}, {s.roof_count} roofs, {s.window_count} windows"
        + ("" if s.reason is None else f" ({s.reason}; keeps the cell shift)")
        for s in field.scenes
    ]
    lines.append(
        f"nodes: {summary.lean} lean, {summary.corrected} ground shift only, "
        f"{summary.uncorrected} left as they were (bound {field.uncorrected_error_bound_m} m); "
        f"{summary.lean_vertices} of {summary.vertices} vertices lean-corrected, "
        f"{summary.past_texture_edge} sample more than a pixel past their texture's edge"
    )
    result = "\n".join(lines)
    file_log.info(result)
    return result


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


@eval_app.command("localise")
def eval_localise(  # noqa: PLR0913 (photos, poses, store and the five run settings)
    photos: Annotated[Path, typer.Argument(help="Directory of the photos named in the pose file.")],
    poses: Annotated[Path, typer.Option(help="JSON-lines pose file, one line per photo.")],
    store: StoreOption,
    *,
    out: Annotated[Path, typer.Option(help="Directory for report.json and review.html.")] = Path(
        "localise-report"
    ),
    reference: Annotated[
        list[Reference] | None,
        typer.Option(help="References to match against; repeat for several. Default: all four."),
    ] = None,
    matcher: Annotated[MatcherChoice, typer.Option(help="Feature matcher.")] = MatcherChoice.XFEAT,
    backend: BackendOption = XFeatBackend.TENSORRT,
    xfeat_models: Annotated[
        Path | None,
        typer.Option(
            envvar="XFEAT_MODEL_DIR",
            help="Directory of xfeat-rt ONNX exports; for --matcher xfeat.",
        ),
    ] = None,
    minimum_inliers: Annotated[
        int, typer.Option(min=4, help="Fewer inliers than this reject a pose.")
    ] = MINIMUM_INLIERS,
    range_m: Annotated[float, typer.Option(help="Render range limit.")] = DEFAULT_MAX_RANGE_M,
) -> None:
    """Localise photos with known poses against the store; write a JSON report and a review page."""
    references = tuple(reference or Reference)
    settings = {
        "photos": photos,
        "poses": poses,
        "out": out,
        "references": [r.value for r in references],
        "matcher": matcher.value,
        "backend": backend.value,
        "minimum_inliers": minimum_inliers,
        "range_m": range_m,
    }
    with reported_errors(), run_log(store, "eval localise", settings):
        records = read_pose_file(poses)
        run_settings = RunSettings(
            ReferenceRenderers.from_store(store, references),
            references,
            _matcher(matcher, backend, xfeat_models),
            matcher.value,
            minimum_inliers=minimum_inliers,
            max_range_m=range_m,
        )
        result = run_photos(records, photos, run_settings, _log_photo_progress)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(report_json(result))
        (out / "review.html").write_text(review_page(result))
        for each in references:
            recall = result.recall(each)
            typer.echo(
                f"{each.value}: {recall.solved_count}/{recall.photo_count} solved, "
                f"recalled {recall.recalled}"
            )
        typer.echo(out)


def _matcher(choice: MatcherChoice, backend: XFeatBackend, xfeat_models: Path | None) -> Matcher:
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


def _log_photo_progress(done: int, total: int) -> None:
    logger.info("localised photo {}/{}", done, total)


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
