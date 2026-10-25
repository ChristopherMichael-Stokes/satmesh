import io
from pathlib import Path

import mercantile
import numpy as np
import pygltflib
import pytest
from fakes import (
    LEAF_ZOOM,
    FakeServices,
    clients,
    square_of_four_leaves,
    tile_colour,
)
from PIL import Image
from rasterio.transform import from_bounds

from satmesh_core import Aoi
from satmesh_data import WEB_MERCATOR, Raster
from satmesh_tiles import (
    build_store,
    complete_tree,
    ground_path,
    node_paths,
    parent_texture,
    plan_tiles,
    read_record,
    snap_outward,
)

# two JPEG generations (Esri tile, then the leaf texture) and a 2 x 2 mean of flat colour
JPEG_COLOUR_TOLERANCE = 6


@pytest.fixture
def services() -> FakeServices:
    return FakeServices()


def test_complete_tree_keeps_only_parents_with_all_four_children() -> None:
    # 5 x 4 leaves from x 8..12, y 8..11: columns 8..11 form a 4 x 4 block, column 12 is ragged
    leaves = [mercantile.Tile(x, y, LEAF_ZOOM) for x in range(8, 13) for y in range(8, 12)]
    children, roots = complete_tree(leaves)
    level_one = [t for t in children if t.z == LEAF_ZOOM - 1]
    level_two = [t for t in children if t.z == LEAF_ZOOM - 2]
    assert len(level_one) == 4
    assert level_two == [mercantile.Tile(2, 2, LEAF_ZOOM - 2)]
    assert set(roots) == {mercantile.Tile(2, 2, LEAF_ZOOM - 2)} | {
        mercantile.Tile(12, y, LEAF_ZOOM) for y in range(8, 12)
    }


def test_complete_tree_of_a_single_leaf_is_that_leaf() -> None:
    leaf = mercantile.Tile(8, 8, LEAF_ZOOM)
    assert complete_tree([leaf]) == ({}, (leaf,))


def test_parent_texture_is_the_two_by_two_mean_of_its_children() -> None:
    parent = mercantile.Tile(4, 4, LEAF_ZOOM - 1)
    colours = [(0, 0, 0), (100, 50, 200), (255, 255, 255), (10, 20, 31)]
    rows = cols = 4
    children = []
    for colour in colours:
        pixels = np.zeros((3, rows, cols), np.uint8)
        pixels[:, :, :] = np.array(colour, np.uint8)[:, None, None]
        pixels[:, 0, 0] = np.array(colour, np.uint8) + 1 if max(colour) < 255 else 254
        children.append(Raster(pixels, from_bounds(0, 0, 1, 1, cols, rows), WEB_MERCATOR))
    texture = parent_texture(children, parent)
    assert texture.pixels.shape == (3, rows, cols)
    # one 2 x 2 block of the output covers a 4 x 4 block of the stitched child pixels:
    # the top-left output pixel averages child 0's top-left 2 x 2 block, with one pixel off by one
    expected_top_left = np.rint((np.array(colours[0]) * 3 + np.array(colours[0]) + 1) / 4)
    np.testing.assert_array_equal(texture.pixels[:, 0, 0], expected_top_left)
    # the bottom-right quarter is child 3's constant colour
    np.testing.assert_array_equal(texture.pixels[:, rows - 1, cols - 1], colours[3])
    bounds = mercantile.xy_bounds(parent)
    assert texture.transform.c == pytest.approx(bounds.left)
    assert texture.transform.f == pytest.approx(bounds.top)


def test_snap_outward_floors_west_south_and_ceils_east_north() -> None:
    aoi = Aoi(crs="EPSG:27700", west=399500.2, south=447000.7, east=400000.1, north=447500.0)
    snapped = snap_outward(aoi)
    assert (snapped.west, snapped.south, snapped.east, snapped.north) == (
        399500.0,
        447000.0,
        400001.0,
        447500.0,
    )


def test_plan_covers_the_aoi_with_native_zoom_leaves_and_one_parent(
    services: FakeServices, tmp_path: Path
) -> None:
    aoi, leaves = square_of_four_leaves()
    esri, _ = clients(services, tmp_path)
    plan = plan_tiles(aoi, esri)
    assert plan.leaf_zoom == LEAF_ZOOM
    assert set(plan.leaves) == leaves
    assert len(plan.roots) == 1
    assert plan.roots[0].z == LEAF_ZOOM - 1


def test_plan_outside_great_britain_raises(services: FakeServices, tmp_path: Path) -> None:
    paris = Aoi(crs="EPSG:4326", west=2.29, south=48.85, east=2.30, north=48.86)
    esri, _ = clients(services, tmp_path)
    with pytest.raises(ValueError, match="only Great Britain"):
        plan_tiles(paris, esri)


def test_build_writes_every_node_and_a_rerun_repeats_nothing(
    services: FakeServices, tmp_path: Path
) -> None:
    aoi, leaves = square_of_four_leaves()
    esri, http = clients(services, tmp_path / "cache")
    plan = plan_tiles(aoi, esri)
    store = tmp_path / "store"
    first = build_store(plan, store, esri=esri, http=http, cache_dir=tmp_path / "cache")
    assert (first.built, first.skipped) == (5, 0)
    for tile in [*leaves, plan.roots[0]]:
        glb, _ = node_paths(store, tile)
        assert glb.stat().st_size > 0
        assert read_record(store, tile).z == tile.z
        assert ground_path(store, tile).stat().st_size > 0
    assert services.requests["wcs"] == 2 * first.built  # one DSM and one DTM box per node
    requests_after_first = dict(services.requests)
    second = build_store(plan, store, esri=esri, http=http, cache_dir=tmp_path / "cache")
    assert (second.built, second.skipped) == (0, 5)
    assert services.requests == requests_after_first


def test_a_missing_leaf_is_rebuilt_from_cache_without_new_requests(
    services: FakeServices, tmp_path: Path
) -> None:
    aoi, leaves = square_of_four_leaves()
    esri, http = clients(services, tmp_path / "cache")
    plan = plan_tiles(aoi, esri)
    store = tmp_path / "store"
    build_store(plan, store, esri=esri, http=http, cache_dir=tmp_path / "cache")
    requests_after_first = dict(services.requests)
    lost = min(leaves)
    node_paths(store, lost)[1].unlink()
    summary = build_store(plan, store, esri=esri, http=http, cache_dir=tmp_path / "cache")
    assert summary.built == 1
    assert services.requests == requests_after_first
    assert read_record(store, lost).z == LEAF_ZOOM


def test_parents_use_coarser_grid_and_error(services: FakeServices, tmp_path: Path) -> None:
    aoi, leaves = square_of_four_leaves()
    esri, http = clients(services, tmp_path / "cache")
    plan = plan_tiles(aoi, esri)
    store = tmp_path / "store"
    build_store(plan, store, esri=esri, http=http, cache_dir=tmp_path / "cache", max_error_m=0.1)
    leaf, parent = read_record(store, min(leaves)), read_record(store, plan.roots[0])
    assert (leaf.grid_spacing_m, leaf.max_error_m) == (0.5, 0.1)
    assert (parent.grid_spacing_m, parent.max_error_m) == (1.0, 0.2)


def test_parent_texture_tiles_land_where_their_esri_tiles_are(
    services: FakeServices, tmp_path: Path
) -> None:
    aoi, _ = square_of_four_leaves()
    esri, http = clients(services, tmp_path / "cache")
    plan = plan_tiles(aoi, esri)
    store = tmp_path / "store"
    build_store(plan, store, esri=esri, http=http, cache_dir=tmp_path / "cache")
    parent = plan.roots[0]
    gltf = pygltflib.GLTF2().load(str(node_paths(store, parent)[0]))
    view = gltf.bufferViews[gltf.images[0].bufferView]
    blob = gltf.binary_blob()[view.byteOffset : view.byteOffset + view.byteLength]
    texture = np.asarray(Image.open(io.BytesIO(blob)).convert("RGB"))
    tiles_per_side = 8
    esri_zoom = parent.z + 3
    block = texture.shape[0] // tiles_per_side
    for row in range(tiles_per_side):
        for col in range(tiles_per_side):
            esri_y, esri_x = parent.y * tiles_per_side + row, parent.x * tiles_per_side + col
            expected = tile_colour(f"/tile/{esri_zoom}/{esri_y}/{esri_x}")
            centre = texture[row * block + block // 2, col * block + block // 2]
            np.testing.assert_allclose(centre, expected, atol=JPEG_COLOUR_TOLERANCE)
