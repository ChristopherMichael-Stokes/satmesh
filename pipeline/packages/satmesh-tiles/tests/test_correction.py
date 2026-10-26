import json
import math
from pathlib import Path

import mercantile
import numpy as np
import pygltflib
import pytest
from fakes import FakeServices, clients, ignore_progress, square_of_four_leaves

from satmesh_tiles import (
    CellCorrection,
    CellStatus,
    CorrectionField,
    apply_correction,
    build_store,
    node_paths,
    plan_tiles,
    read_record,
    stored_tiles,
    write_positional_error,
)

# one cell spanning the whole of the national grid, so every node of the fixture store falls in it
GRID_SPAN_M = 1_000_000
UNCORRECTED_BOUND_M = 2.8
EAST_M, NORTH_M, BOUND_M = 2.0, -1.0, 0.45
LATITUDE_DEG = 53.9236
# BNG axes are rotated 0.2 to 0.6 degrees from Web Mercator's, which moves a 2 m shift by about
# 0.02 m sideways: under 1.5e-4 of a 180 m tile
FRACTION_TOLERANCE = 1.5e-4


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


def field(*cells: CellCorrection) -> CorrectionField:
    return CorrectionField(uncorrected_error_bound_m=UNCORRECTED_BOUND_M, cells=cells)


@pytest.fixture
def store(tmp_path: Path) -> Path:
    esri, http = clients(FakeServices(), tmp_path / "cache")
    aoi, _ = square_of_four_leaves()
    build_store(
        plan_tiles(aoi, esri),
        tmp_path / "store",
        esri=esri,
        http=http,
        cache_dir=tmp_path / "cache",
        report=ignore_progress,
    )
    return tmp_path / "store"


def texture_coordinates(store: Path, tile: mercantile.Tile) -> np.ndarray:
    gltf = pygltflib.GLTF2().load(str(node_paths(store, tile)[0]))
    accessor = gltf.accessors[gltf.meshes[0].primitives[0].attributes.TEXCOORD_0]
    view = gltf.bufferViews[accessor.bufferView]
    raw = np.frombuffer(gltf.binary_blob(), np.float32, accessor.count * 2, view.byteOffset)
    return raw.reshape(-1, 2).copy()


def tile_ground_width_m(tile: mercantile.Tile) -> float:
    bounds = mercantile.xy_bounds(tile)
    return float((bounds.right - bounds.left) * math.cos(math.radians(LATITUDE_DEG)))


def test_corrected_cell_moves_texture_coordinates_by_the_shift_over_the_tile_size(
    store: Path,
) -> None:
    tiles = sorted(stored_tiles(store))
    before = {tile: texture_coordinates(store, tile) for tile in tiles}
    summary = apply_correction(
        store, field(cell("corrected", EAST_M, NORTH_M, BOUND_M)), report=ignore_progress
    )
    assert (summary.corrected, summary.uncorrected, summary.rewritten) == (
        len(tiles),
        0,
        len(tiles),
    )
    for tile in tiles:
        moved = texture_coordinates(store, tile) - before[tile]
        width = tile_ground_width_m(tile)
        # sampled where the feature really is: east of the vertex for an eastward displacement;
        # north is up the texture, which lowers the file's top-left v
        np.testing.assert_allclose(moved[:, 0], EAST_M / width, atol=FRACTION_TOLERANCE)
        np.testing.assert_allclose(moved[:, 1], -NORTH_M / width, atol=FRACTION_TOLERANCE)
        position = read_record(store, tile).position
        assert position is not None
        assert (position.status, position.error_bound_m) == ("corrected", BOUND_M)


def test_repeating_or_revising_the_correction_lands_where_a_single_application_would(
    store: Path,
) -> None:
    tile = min(stored_tiles(store))
    apply_correction(store, field(cell("corrected", 5.0, 5.0, 1.0)), report=ignore_progress)
    again = apply_correction(store, field(cell("corrected", 5.0, 5.0, 1.0)), report=ignore_progress)
    assert again.rewritten == 0
    apply_correction(
        store, field(cell("corrected", EAST_M, NORTH_M, BOUND_M)), report=ignore_progress
    )
    revised = texture_coordinates(store, tile)

    fresh = store.parent / "fresh"
    esri, http = clients(FakeServices(), store.parent / "cache2")
    aoi, _ = square_of_four_leaves()
    build_store(
        plan_tiles(aoi, esri),
        fresh,
        esri=esri,
        http=http,
        cache_dir=store.parent / "cache2",
        report=ignore_progress,
    )
    apply_correction(
        fresh, field(cell("corrected", EAST_M, NORTH_M, BOUND_M)), report=ignore_progress
    )
    np.testing.assert_allclose(revised, texture_coordinates(fresh, tile), atol=1e-6)


def test_uncorrected_cell_leaves_textures_and_carries_the_bound(store: Path) -> None:
    tile = min(stored_tiles(store))
    before = texture_coordinates(store, tile)
    summary = apply_correction(
        store, field(cell("uncorrected", 0.0, 0.0, UNCORRECTED_BOUND_M)), report=ignore_progress
    )
    assert summary.corrected == 0
    np.testing.assert_array_equal(texture_coordinates(store, tile), before)
    position = read_record(store, tile).position
    assert position is not None
    assert (position.status, position.error_bound_m) == ("uncorrected", UNCORRECTED_BOUND_M)


def test_nodes_outside_every_cell_are_uncorrected_with_the_survey_bound(store: Path) -> None:
    apply_correction(store, field(), report=ignore_progress)
    tile = min(stored_tiles(store))
    position = read_record(store, tile).position
    assert position is not None
    assert (position.status, position.error_bound_m) == ("uncorrected", UNCORRECTED_BOUND_M)


def test_positional_error_report_lists_finest_nodes_and_the_largest_bound(
    store: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out" / "positional_error.json"
    write_positional_error(store, out)
    unmeasured = out.read_text()
    assert '"max_error_bound_m": null' in unmeasured
    apply_correction(
        store, field(cell("corrected", EAST_M, NORTH_M, BOUND_M)), report=ignore_progress
    )
    write_positional_error(store, out)
    report = json.loads(out.read_text())
    finest = max(tile.z for tile in stored_tiles(store))
    assert {n["z"] for n in report["nodes"]} == {finest}
    assert report["max_error_bound_m"] == BOUND_M
    assert report["unmeasured_nodes"] == 0
