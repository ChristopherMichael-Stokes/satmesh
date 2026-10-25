"""Text reports of the evaluation checks over one box, for the `satmesh eval` command."""

from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

import httpx
import numpy as np
import rasterio
import trimesh
from rasterio.transform import Affine

from satmesh_core import BRITISH_NATIONAL_GRID, Aoi
from satmesh_data import EA_DSM, EA_DTM, EsriClient, fetch_ea_lidar
from satmesh_eval.heights import HeightScore, score_by_stratum, score_heights
from satmesh_eval.imagery import esri_raster_over, read_rgb_geotiff
from satmesh_eval.mesh_score import surface_height_error
from satmesh_eval.offset import luminance_on_grid, measure_offset, source_ground_pixel_m
from satmesh_eval.render import load_store
from satmesh_eval.smoothness import smoothness_score
from satmesh_eval.spectrum import (
    DETAIL_BAND_EDGES_CYCLES_PER_M,
    WINDOW_M,
    detail_ratio,
    native_windows,
    stable_windows,
)
from satmesh_eval.strata import (
    OBJECT_HEIGHT_THRESHOLD_M,
    SLOPE_CLASS_NAMES,
    raised_object_mask,
    slope_classes,
)
from satmesh_eval.visibility import (
    DepthAgreement,
    depth_agreement,
    raised_point_visibility,
    random_cameras,
    range_image,
    raster_mesh,
    sample_raised_points,
)

# outer pixels of the box where a leaf may stop short of the lidar raster's edge
EDGE_MARGIN_PX = 5
# one rig is a camera height above ground and a pitch; 1.7 m level is a person or ground robot
CAMERA_RIGS = (("ground 1.7 m, level", 1.7, 0.0), ("drone 60 m, pitch -25", 60.0, -25.0))


@dataclass(frozen=True)
class Site:
    """First-return surface and bare-earth rasters of one box, in BNG and ODN."""

    surface: np.ndarray
    ground: np.ndarray
    transform: Affine


def bng_box(bbox: tuple[float, float, float, float]) -> Aoi:
    """Return the Aoi for west, south, east, north in British National Grid metres."""
    west, south, east, north = bbox
    return Aoi(crs=BRITISH_NATIONAL_GRID, west=west, south=south, east=east, north=north)


def load_site(box: Aoi, cache_dir: Path, http: httpx.Client) -> Site:
    """Fetch (or reuse cached) EA first-return DSM and DTM over `box`."""
    with rasterio.open(fetch_ea_lidar(http, box, cache_dir, EA_DSM)) as dsm:
        surface, transform = dsm.read(1).astype(np.float64), dsm.transform
    with rasterio.open(fetch_ea_lidar(http, box, cache_dir, EA_DTM)) as dtm:
        ground = dtm.read(1).astype(np.float64)
    return Site(surface, ground, transform)


def store_mesh(store: Path) -> trimesh.Trimesh:
    """Return every finest-level leaf of the store as one mesh in BNG and ODN."""
    meshes = [leaf.mesh for leaf in load_store(store)]
    first_vertex = np.cumsum([0, *(len(m.vertices) for m in meshes[:-1])])
    faces = [m.faces + start for m, start in zip(meshes, first_vertex, strict=True)]
    return trimesh.Trimesh(
        vertices=np.concatenate([m.vertices for m in meshes]),
        faces=np.concatenate(faces),
        process=False,
    )


def heights_report(store: Path, site: Site) -> str:
    """Height error of the store against the first-return DSM at the DSM's pixel centres."""
    error = surface_height_error(
        store_mesh(store), site.surface, site.transform, margin_px=EDGE_MARGIN_PX
    )
    raised = raised_object_mask(site.surface, site.ground)
    rows = {
        "all": score_heights(error),
        "open ground": score_heights(np.where(raised, np.nan, error)),
        "raised objects": score_heights(np.where(raised, error, np.nan)),
        **score_by_stratum(
            error, slope_classes(site.surface, site.transform, 27700), SLOPE_CLASS_NAMES
        ),
    }
    lines = ["store minus first-return DSM at DSM pixel centres, m"]
    lines += [_height_row(label, score) for label, score in rows.items()]
    return "\n".join(lines)


def smoothness_report(store: Path, site: Site) -> str:
    """Facet smoothness of the store against the first-return DSM."""
    score = smoothness_score(store_mesh(store), site.surface, site.ground, site.transform)
    open_ground = f"median {score.open_normal_median_deg:.2f}  p90 {score.open_normal_p90_deg:.2f}"
    raised = f"median {score.raised_normal_median_deg:.1f}  p90 {score.raised_normal_p90_deg:.1f}"
    return "\n".join(
        [
            "facet smoothness against the first-return DSM",
            f"  open ground normal error  {open_ground} deg",
            f"  raised objects normal error  {raised} deg",
            f"  flat facets on slopes over 5 deg  {score.flat_on_slope_fraction:.1%}",
            f"  grid-aligned aspect excess  {score.grid_aspect_excess:+.3f}",
        ]
    )


def visibility_report(store: Path, site: Site, *, cameras: int, range_m: float, seed: int) -> str:
    """Pixel agreement and raised-point visibility of the store against the DSM triangulated."""
    reference = raster_mesh(site.surface, site.transform)
    ground_only = raster_mesh(site.ground, site.transform)
    meshes = {"store": store_mesh(store), "DTM only": ground_only}
    raised = sample_raised_points(
        site.surface, site.ground, site.transform, OBJECT_HEIGHT_THRESHOLD_M, seed
    )
    lines = [
        f"camera visibility against the DSM mesh, {cameras} cameras per rig, range {range_m} m"
    ]
    for rig, above_ground_m, pitch_deg in CAMERA_RIGS:
        rig_cameras = random_cameras(
            site.surface,
            site.ground,
            site.transform,
            cameras,
            above_ground_m=above_ground_m,
            pitch_deg=pitch_deg,
            margin_m=range_m,
            seed=seed,
        )
        for name, mesh in meshes.items():
            pixels = sum(
                (
                    depth_agreement(
                        range_image(reference, c, range_m), range_image(mesh, c, range_m)
                    )
                    for c in rig_cameras
                ),
                start=DepthAgreement(0, 0, 0),
            )
            points = raised_point_visibility(reference, mesh, rig_cameras, raised, range_m)
            lines.append(
                f"  {rig:22s} {name:9s} "
                f"pixel agreement {_share(pixels.agreeing_pixels, pixels.reference_hit_pixels)}  "
                f"raised points shown {_share(points.shown, points.reference_visible)} "
                f"of {points.reference_visible}"
            )
    return "\n".join(lines)


def offset_report(aerial_geotiff: Path, box: Aoi, zoom: int, esri: EsriClient) -> str:
    """Offset of Esri imagery at `zoom` against an EA aerial GeoTIFF over `box`."""
    reference = luminance_on_grid(read_rgb_geotiff(aerial_geotiff), box)
    other = luminance_on_grid(esri_raster_over(esri, box, zoom), box)
    estimate, _ = measure_offset(reference, other)
    east = f"{estimate.east_m:+.2f}  95% interval {_interval(estimate.east_interval_m)}"
    north = f"{estimate.north_m:+.2f}  95% interval {_interval(estimate.north_interval_m)}"
    return "\n".join(
        [
            "Esri displacement from the EA aerial (positive is east and north), m",
            f"  east {east}  NMAD {estimate.east_nmad_m:.2f}",
            f"  north {north}  NMAD {estimate.north_nmad_m:.2f}",
            f"  reliable windows {estimate.windows_used} of {estimate.windows_total}",
        ]
    )


def texture_report(aerial_geotiff: Path, box: Aoi, zoom: int, esri: EsriClient, site: Site) -> str:
    """Esri detail power over the EA aerial's by band, on windows clear of raised objects."""
    reference = read_rgb_geotiff(aerial_geotiff)
    other = esri_raster_over(esri, box, zoom)
    raised = raised_object_mask(site.surface, site.ground)
    windows = [
        stable_windows(native_windows(raster, box), raised, site.transform, WINDOW_M)
        for raster in (other, reference)
    ]
    ratio = detail_ratio(
        windows[0],
        source_ground_pixel_m(other, box),
        windows[1],
        source_ground_pixel_m(reference, box),
    )
    counts = f"Esri {ratio.windows_other}, EA {ratio.windows_reference}"
    lines = [
        "Esri over EA aerial power, each normalised by its own 4 to 20 m band",
        f"  windows of {WINDOW_M:.0f} m clear of raised objects: {counts}",
    ]
    for (low, high), value in zip(
        pairwise(DETAIL_BAND_EDGES_CYCLES_PER_M), ratio.ratio, strict=True
    ):
        lines.append(f"  {low:.2f} to {high:.2f} cycles/m  {value:.2f}")
    return "\n".join(lines)


def _share(part: int, whole: int) -> str:
    return f"{part / whole:.1%}" if whole else "n/a"


def _interval(interval: tuple[float, float]) -> str:
    return f"({interval[0]:+.2f}, {interval[1]:+.2f})"


def _height_row(label: str, score: HeightScore) -> str:
    return (
        f"  {label:20s} n={score.count:8d} median {score.median_m:+.3f}  NMAD {score.nmad_m:.3f}"
        f"  p68 {score.quantile_683_m:.3f}  p95 {score.quantile_95_m:.3f}"
    )
