import json
import re
from datetime import date
from pathlib import Path
from typing import override

import httpx
import mercantile
import numpy as np
import pygltflib
import pytest
import shapely
from fakes import FakeServices, clients, ignore_progress, square_of_four_leaves
from pyproj import Transformer
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds

from satmesh_core import BRITISH_NATIONAL_GRID, WGS84, wgs84_to_bng
from satmesh_data import EA_DSM, WEB_MERCATOR, EsriScene, SceneId, SceneMap
from satmesh_tiles import (
    CORRECTION_FILE,
    MAX_LEAN,
    CellCorrection,
    CellStatus,
    CorrectionField,
    LeanFit,
    SceneLean,
    StaleCorrectionError,
    apply_correction,
    build_store,
    export_3dtiles,
    export_area_glb,
    export_gazebo,
    node_paths,
    plan_tiles,
    read_record,
    stored_tiles,
    write_positional_error,
)

# one cell spanning the whole of the national grid, so every node of the fixture store falls in it
GRID_SPAN_M = 1_000_000
UNCORRECTED_BOUND_M = 2.8
CELL_EAST_M, CELL_NORTH_M, CELL_BOUND_M = 2.0, -1.0, 0.45
T_EAST_M, T_NORTH_M = -0.6, 1.4
LEAN_EAST, LEAN_NORTH = 0.3, -0.2
LEAN_GROUND_BOUND_M, LEAN_RADIUS = 0.7, 0.12
# height above ground of the fake surface: CANOPY_M at REFERENCE_EASTING_M, rising east, so the
# fixture's vertices stand 0 to 9 m tall
CANOPY_M = 2.0
CANOPY_RISE_PER_M = 0.02
REFERENCE_EASTING_M = 399_600.0
# float32 texture coordinates hold about 1e-7; the BNG position of a vertex read back from float32
# glTF is within 1e-4 m, under 1e-6 of a 180 m tile
UV_TOLERANCE = 2e-6
APPLIED = SceneId(capture_date=date(2025, 7, 12), sensor="GE01")
REJECTED = SceneId(capture_date=date(2025, 4, 11), sensor="WV02")
OLD_CORRECTION = {
    "uncorrected_error_bound_m": 2.8,
    "cells": [
        {
            "west_m": 0,
            "south_m": 0,
            "east_m": 1_000_000,
            "north_m": 1_000_000,
            "status": "corrected",
            "displacement_east_m": 2.0,
            "displacement_north_m": -1.0,
            "error_bound_m": 0.45,
            "windows_used": 61,
            "windows_total": 900,
        }
    ],
}


class SurfaceServices(FakeServices):
    """The fake EA WCS with heights in absolute BNG: a sloping DTM and a canopy rising east."""

    @staticmethod
    @override
    def lidar(request: httpx.Request) -> bytes:
        subsets = request.url.params.get_list("subset")
        east, north = (tuple(int(v) for v in re.findall(r"-?\d+", subset)) for subset in subsets)
        cols, rows = east[1] - east[0], north[1] - north[0]
        centres = east[0] + np.arange(cols) + 0.5
        heights = np.tile(100.0 + 0.1 * (centres - REFERENCE_EASTING_M), (rows, 1))
        if request.url.params["coverageId"] == EA_DSM.coverage_id:
            heights += canopy_m(centres)
        with MemoryFile() as memory:
            with memory.open(
                driver="GTiff",
                width=cols,
                height=rows,
                count=1,
                dtype="float64",
                crs="EPSG:27700",
                transform=from_bounds(east[0], north[0], east[1], north[1], cols, rows),
            ) as dst:
                dst.write(heights, 1)
            return bytes(memory.read())


def canopy_m(easting_m: np.ndarray) -> np.ndarray:
    return CANOPY_M + CANOPY_RISE_PER_M * (easting_m - REFERENCE_EASTING_M)


def build(root: Path) -> Path:
    esri, http = clients(SurfaceServices(), root / "cache")
    aoi, _ = square_of_four_leaves()
    build_store(
        plan_tiles(aoi, esri),
        root / "store",
        esri=esri,
        http=http,
        cache_dir=root / "cache",
        report=ignore_progress,
    )
    return root / "store"


@pytest.fixture
def store(tmp_path: Path) -> Path:
    return build(tmp_path)


def cell(status: CellStatus, east_m: float, north_m: float, bound_m: float) -> CellCorrection:
    return CellCorrection(
        west_m=0,
        south_m=0,
        east_m=GRID_SPAN_M,
        north_m=GRID_SPAN_M,
        status=status,
        displacement_east_m=east_m,
        displacement_north_m=north_m,
        error_bound_m=bound_m,
        windows_used=61,
        windows_total=900,
    )


def fit(t: tuple[float, float], lean: tuple[float, float]) -> LeanFit:
    return LeanFit(
        t_east_m=t[0],
        t_north_m=t[1],
        lean_east=lean[0],
        lean_north=lean[1],
        k=float(np.hypot(*lean)),
        azimuth_deg=float(np.degrees(np.arctan2(*lean)) % 360),
        t_east_interval_m=(t[0] - 0.3, t[0] + 0.3),
        t_north_interval_m=(t[1] - 0.3, t[1] + 0.3),
        k_interval=(0.2, 0.5),
        azimuth_interval_deg=(110.0, 130.0),
        lean_radius_95=LEAN_RADIUS,
        ground_error_bound_m=LEAN_GROUND_BOUND_M,
        at_cap=False,
        roof_residual_m=0.6,
        bootstrap_draws=1000,
    )


def lean_field(*scenes: SceneLean) -> CorrectionField:
    return CorrectionField(
        uncorrected_error_bound_m=UNCORRECTED_BOUND_M,
        cells=(cell("corrected", CELL_EAST_M, CELL_NORTH_M, CELL_BOUND_M),),
        scene_release="test release",
        scenes=scenes,
    )


def applied() -> SceneLean:
    return SceneLean(
        scene=APPLIED,
        status="applied",
        reason=None,
        fit=fit((T_EAST_M, T_NORTH_M), (LEAN_EAST, LEAN_NORTH)),
        roof_count=23,
        window_count=40,
    )


def rejected() -> SceneLean:
    return SceneLean(
        scene=REJECTED,
        status="rejected",
        reason="lean not measured",
        fit=fit((5.0, 5.0), (0.5, 0.0)),
        roof_count=12,
        window_count=30,
    )


def ground_only_field(*cells: CellCorrection) -> CorrectionField:
    return CorrectionField(
        uncorrected_error_bound_m=UNCORRECTED_BOUND_M, cells=cells, scene_release=None, scenes=()
    )


def split_easting(store: Path) -> float:
    """The BNG easting through the middle of the store, where the two test scenes meet."""
    eastings = np.concatenate([vertex_bng(store, tile)[0] for tile in stored_tiles(store)])
    return float((eastings.min() + eastings.max()) / 2)


def two_scenes(split_m: float) -> SceneMap:
    west = shapely.MultiPolygon([shapely.box(0, 0, split_m, GRID_SPAN_M)])
    east = shapely.MultiPolygon([shapely.box(split_m, 0, GRID_SPAN_M, GRID_SPAN_M)])
    return SceneMap(
        BRITISH_NATIONAL_GRID,
        19,
        "test release",
        (EsriScene(APPLIED, 0.3, 1.0, (1,), west), EsriScene(REJECTED, 0.5, 1.0, (2,), east)),
    )


def texture_coordinates(path: Path) -> np.ndarray:
    """The texture coordinates of a GLB's single primitive, v up from the texture's bottom edge."""
    gltf = pygltflib.GLTF2().load(str(path))
    return primitive_uv(gltf, gltf.meshes[0].primitives[0])


def primitive_uv(gltf: pygltflib.GLTF2, primitive: pygltflib.Primitive) -> np.ndarray:
    index = primitive.attributes.TEXCOORD_0
    assert index is not None
    accessor = gltf.accessors[index]
    view = gltf.bufferViews[accessor.bufferView]
    start = (view.byteOffset or 0) + (accessor.byteOffset or 0)
    raw = np.frombuffer(gltf.binary_blob(), np.float32, accessor.count * 2, start)
    uv = raw.reshape(-1, 2).astype(np.float64)
    return np.column_stack([uv[:, 0], 1 - uv[:, 1]])


def bng_of_uv(tile: mercantile.Tile, uv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    bounds = mercantile.xy_bounds(tile)
    x = bounds.left + uv[:, 0] * (bounds.right - bounds.left)
    y = bounds.bottom + uv[:, 1] * (bounds.top - bounds.bottom)
    lon, lat = Transformer.from_crs(WEB_MERCATOR, WGS84, always_xy=True).transform(x, y)
    easting, northing = wgs84_to_bng().transform(lon, lat)
    return np.asarray(easting), np.asarray(northing)


def uv_of_bng(tile: mercantile.Tile, easting: np.ndarray, northing: np.ndarray) -> np.ndarray:
    lon, lat = wgs84_to_bng().transform(easting, northing, direction="INVERSE")
    x, y = Transformer.from_crs(WGS84, WEB_MERCATOR, always_xy=True).transform(lon, lat)
    bounds = mercantile.xy_bounds(tile)
    return np.column_stack(
        [
            (np.asarray(x) - bounds.left) / (bounds.right - bounds.left),
            (np.asarray(y) - bounds.bottom) / (bounds.top - bounds.bottom),
        ]
    )


def vertex_bng(store: Path, tile: mercantile.Tile) -> tuple[np.ndarray, np.ndarray]:
    """Where each vertex stands, from its texture coordinate before any correction."""
    return bng_of_uv(tile, texture_coordinates(node_paths(store, tile)[0]))


def expected_uv(
    tile: mercantile.Tile,
    standing: tuple[np.ndarray, np.ndarray],
    east_m: np.ndarray,
    north_m: np.ndarray,
) -> np.ndarray:
    """Out(p) = Esri(p + d): the vertex samples the texture d metres from where it stands."""
    easting, northing = standing
    return uv_of_bng(tile, easting + east_m, northing + north_m)


def test_lean_scene_vertices_move_by_shift_plus_lean_times_height_and_others_by_the_cell(
    store: Path,
) -> None:
    tiles = sorted(stored_tiles(store))
    standing = {tile: vertex_bng(store, tile) for tile in tiles}
    split_m = split_easting(store)

    summary = apply_correction(
        store, lean_field(applied(), rejected()), two_scenes(split_m), ignore_progress
    )

    lean_vertices = 0
    for tile in tiles:
        easting, _ = standing[tile]
        in_lean = easting < split_m
        height = canopy_m(easting)
        east = np.where(in_lean, T_EAST_M + LEAN_EAST * height, CELL_EAST_M)
        north = np.where(in_lean, T_NORTH_M + LEAN_NORTH * height, CELL_NORTH_M)
        np.testing.assert_allclose(
            texture_coordinates(node_paths(store, tile)[0]),
            expected_uv(tile, standing[tile], east, north),
            atol=UV_TOLERANCE,
            rtol=0,
        )
        lean_vertices += int(in_lean.sum())
    assert summary.lean_vertices == lean_vertices
    assert 0 < lean_vertices < summary.vertices
    assert summary.lean + summary.corrected == len(tiles)
    assert summary.lean > 0
    assert summary.corrected > 0


def test_node_records_carry_the_centre_correction_and_the_worst_bound(store: Path) -> None:
    split_m = split_easting(store)
    standing = {tile: vertex_bng(store, tile)[0] for tile in stored_tiles(store)}
    apply_correction(store, lean_field(applied(), rejected()), two_scenes(split_m), ignore_progress)
    for tile, easting in standing.items():
        position = read_record(store, tile).position
        assert position is not None
        if (easting < split_m).all():
            assert (position.status, position.scene) == ("lean", APPLIED)
            assert (position.east_m, position.lean_east) == (T_EAST_M, LEAN_EAST)
            assert (position.error_bound_m, position.error_bound_per_height) == (
                LEAN_GROUND_BOUND_M,
                LEAN_RADIUS,
            )
        elif (easting >= split_m).all():
            assert (position.status, position.scene) == ("corrected", REJECTED)
            assert (position.east_m, position.lean_east) == (CELL_EAST_M, 0.0)
            assert (position.error_bound_m, position.error_bound_per_height) == (
                CELL_BOUND_M,
                MAX_LEAN,
            )
        else:
            assert position.error_bound_m == max(LEAN_GROUND_BOUND_M, CELL_BOUND_M)
            assert position.error_bound_per_height == MAX_LEAN


def test_without_scenes_every_vertex_takes_its_cell_shift(store: Path) -> None:
    tiles = sorted(stored_tiles(store))
    standing = {tile: vertex_bng(store, tile) for tile in tiles}

    summary = apply_correction(
        store,
        ground_only_field(cell("corrected", CELL_EAST_M, CELL_NORTH_M, CELL_BOUND_M)),
        None,
        ignore_progress,
    )

    assert (summary.lean, summary.corrected, summary.lean_vertices) == (0, len(tiles), 0)
    for tile in tiles:
        count = len(standing[tile][0])
        np.testing.assert_allclose(
            texture_coordinates(node_paths(store, tile)[0]),
            expected_uv(
                tile, standing[tile], np.full(count, CELL_EAST_M), np.full(count, CELL_NORTH_M)
            ),
            atol=UV_TOLERANCE,
            rtol=0,
        )


def test_repeating_or_revising_the_correction_lands_where_a_single_application_would(
    store: Path, tmp_path: Path
) -> None:
    split_m = split_easting(store)
    scenes = two_scenes(split_m)
    apply_correction(
        store, ground_only_field(cell("corrected", 5.0, 5.0, 1.0)), None, ignore_progress
    )
    apply_correction(store, lean_field(applied(), rejected()), scenes, ignore_progress)
    apply_correction(store, lean_field(applied(), rejected()), scenes, ignore_progress)

    fresh = build(tmp_path / "fresh")
    apply_correction(fresh, lean_field(applied(), rejected()), scenes, ignore_progress)
    for tile in stored_tiles(store):
        np.testing.assert_allclose(
            texture_coordinates(node_paths(store, tile)[0]),
            texture_coordinates(node_paths(fresh, tile)[0]),
            atol=1e-7,
            rtol=0,
        )


def test_uncorrected_cells_leave_textures_and_carry_the_bound(store: Path) -> None:
    tile = min(stored_tiles(store))
    before = texture_coordinates(node_paths(store, tile)[0])
    summary = apply_correction(
        store,
        ground_only_field(cell("uncorrected", 0.0, 0.0, UNCORRECTED_BOUND_M)),
        None,
        ignore_progress,
    )
    assert summary.corrected == 0
    np.testing.assert_allclose(
        texture_coordinates(node_paths(store, tile)[0]), before, atol=1e-7, rtol=0
    )
    position = read_record(store, tile).position
    assert position is not None
    assert (position.status, position.error_bound_m) == ("uncorrected", UNCORRECTED_BOUND_M)


def test_nodes_outside_every_cell_are_uncorrected_with_the_survey_bound(store: Path) -> None:
    apply_correction(store, ground_only_field(), None, ignore_progress)
    position = read_record(store, min(stored_tiles(store))).position
    assert position is not None
    assert (position.status, position.error_bound_m) == ("uncorrected", UNCORRECTED_BOUND_M)


def test_applied_leans_need_a_scene_map(store: Path) -> None:
    with pytest.raises(ValueError, match="scene map"):
        apply_correction(store, lean_field(applied()), None, ignore_progress)


def test_every_exporter_carries_the_corrected_texture_coordinates(
    store: Path, tmp_path: Path
) -> None:
    apply_correction(
        store, lean_field(applied(), rejected()), two_scenes(split_easting(store)), ignore_progress
    )
    leaves = {t for t in stored_tiles(store) if t.z == max(t.z for t in stored_tiles(store))}

    tileset = json.loads(export_3dtiles(store).read_text())
    uris = re.findall(r'"uri": "([^"]+)"', json.dumps(tileset))
    assert {store / uri for uri in uris} == {node_paths(store, t)[0] for t in stored_tiles(store)}

    world = export_gazebo(store, tmp_path / "gazebo")
    for tile in leaves:
        copied = world.parent / "meshes" / f"tile_{tile.z}_{tile.x}_{tile.y}.glb"
        assert copied.read_bytes() == node_paths(store, tile)[0].read_bytes()

    area = tmp_path / "area.glb"
    export_area_glb(store, area)
    gltf = pygltflib.GLTF2().load(str(area))
    for node in gltf.nodes:
        z, x, y = (int(v) for v in node.name.split("/"))
        assert node.mesh is not None
        (primitive,) = gltf.meshes[node.mesh].primitives
        np.testing.assert_allclose(
            np.unique(primitive_uv(gltf, primitive), axis=0),
            np.unique(texture_coordinates(node_paths(store, mercantile.Tile(x, y, z))[0]), axis=0),
            atol=1e-7,
            rtol=0,
        )


def test_a_store_corrected_under_the_old_schema_is_rejected_everywhere(
    store: Path, tmp_path: Path
) -> None:
    (store / CORRECTION_FILE).write_text(json.dumps(OLD_CORRECTION))
    message = r"rebuild it .* re-run `satmesh correct`"
    with pytest.raises(StaleCorrectionError, match=message):
        export_3dtiles(store)
    with pytest.raises(StaleCorrectionError, match=message):
        export_gazebo(store, tmp_path / "gazebo")
    with pytest.raises(StaleCorrectionError, match=message):
        export_area_glb(store, tmp_path / "area.glb")
    with pytest.raises(StaleCorrectionError, match=message):
        write_positional_error(store, tmp_path / "positional_error.json")
    with pytest.raises(StaleCorrectionError, match=message):
        apply_correction(store, ground_only_field(), None, ignore_progress)


def test_positional_error_report_lists_finest_nodes_and_the_largest_bounds(
    store: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out" / "positional_error.json"
    write_positional_error(store, out)
    assert json.loads(out.read_text())["max_error_bound_m"] is None
    apply_correction(
        store, lean_field(applied(), rejected()), two_scenes(split_easting(store)), ignore_progress
    )
    write_positional_error(store, out)
    report = json.loads(out.read_text())
    finest = max(tile.z for tile in stored_tiles(store))
    assert {n["z"] for n in report["nodes"]} == {finest}
    assert report["max_error_bound_m"] == max(LEAN_GROUND_BOUND_M, CELL_BOUND_M)
    assert report["max_error_bound_per_height"] == MAX_LEAN
    assert report["unmeasured_nodes"] == 0
    assert {n["scene"] for n in report["nodes"]} <= {str(APPLIED), str(REJECTED)}
