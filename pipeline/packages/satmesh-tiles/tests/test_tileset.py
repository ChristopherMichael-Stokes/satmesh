import json
import shutil
from pathlib import Path
from typing import Any

import mercantile
import numpy as np
import pygltflib
import pytest
from fakes import FakeServices, clients, ignore_progress, square_of_four_leaves

from satmesh_tiles import build_store, export_3dtiles, node_paths, plan_tiles, read_record

# float32 vertex positions within a few hundred metres of a tile origin resolve about 3e-5 m
BOX_TOLERANCE_M = 1e-3
PARENT_ZOOM = 16
CORNERS = 8


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("tileset")
    esri, http = clients(FakeServices(), root / "cache")
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


def column_major_matrix(values: list[float]) -> np.ndarray:
    return np.array(values).reshape(4, 4).T


def apply(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    return (matrix @ np.column_stack([points, np.ones(len(points))]).T).T[:, :3]


def box_corners(tile: dict[str, Any]) -> np.ndarray:
    """The 8 corners of a tile's box in the tile's own frame."""
    centre, *axes = (np.array(tile["boundingVolume"]["box"][i : i + 3]) for i in range(0, 12, 3))
    return np.array(
        [
            centre + sx * axes[0] + sy * axes[1] + sz * axes[2]
            for sx in (-1, 1)
            for sy in (-1, 1)
            for sz in (-1, 1)
        ]
    )


def glb_vertices_enu(glb: Path) -> np.ndarray:
    gltf = pygltflib.GLTF2().load(str(glb))
    accessor = gltf.accessors[gltf.meshes[0].primitives[0].attributes.POSITION]
    view = gltf.bufferViews[accessor.bufferView]
    local = np.frombuffer(gltf.binary_blob(), np.float32, accessor.count * 3, view.byteOffset)
    local = local.reshape(-1, 3)
    return np.column_stack([local[:, 0], -local[:, 2], local[:, 1]])


def stored_tiles(store: Path) -> list[mercantile.Tile]:
    return [
        mercantile.Tile(int(p.parent.name), int(p.stem), int(p.parent.parent.name))
        for p in (store / "nodes").glob("*/*/*.json")
    ]


def tileset(store: Path) -> dict[str, Any]:
    return json.loads(export_3dtiles(store).read_text())["root"]


def test_tree_has_a_container_one_parent_and_four_leaves(store: Path) -> None:
    container = tileset(store)
    assert "content" not in container
    (parent,) = container["children"]
    assert len(parent["children"]) == 4
    assert all("children" not in leaf for leaf in parent["children"])
    assert {t["refine"] for t in [container, parent, *parent["children"]]} == {"REPLACE"}


def test_geometric_error_shrinks_down_the_tree(store: Path) -> None:
    container = tileset(store)
    (parent,) = container["children"]
    leaf_errors = [leaf["geometricError"] for leaf in parent["children"]]
    assert container["geometricError"] > parent["geometricError"] > max(leaf_errors) > 0


def test_every_content_uri_is_a_glb_in_the_store(store: Path) -> None:
    (parent,) = tileset(store)["children"]
    for tile in [parent, *parent["children"]]:
        assert (store / tile["content"]["uri"]).read_bytes()[:4] == b"glTF"


def test_composed_transforms_equal_each_nodes_enu_to_ecef(store: Path) -> None:
    container = tileset(store)
    (parent,) = container["children"]
    container_matrix = column_major_matrix(container["transform"])
    parent_matrix = container_matrix @ column_major_matrix(parent["transform"])
    composed: dict[str, np.ndarray] = {}
    for leaf in parent["children"]:
        composed[leaf["content"]["uri"]] = parent_matrix @ column_major_matrix(leaf["transform"])
    leaf_tiles = [t for t in stored_tiles(store) if t.z == PARENT_ZOOM + 1]
    for tile in leaf_tiles:
        expected = np.array(read_record(store, tile).enu_to_ecef)
        matrix = composed[f"nodes/{tile.z}/{tile.x}/{tile.y}.glb"]
        np.testing.assert_allclose(matrix, expected, rtol=0, atol=1e-6)
    parent_tile = next(t for t in stored_tiles(store) if t.z == PARENT_ZOOM)
    np.testing.assert_allclose(
        parent_matrix, np.array(read_record(store, parent_tile).enu_to_ecef), rtol=0, atol=1e-6
    )


def test_each_box_contains_its_vertices_and_the_parent_box_contains_its_children(
    store: Path,
) -> None:
    (parent,) = tileset(store)["children"]
    parent_corners = box_corners(parent)
    low, high = parent_corners.min(axis=0), parent_corners.max(axis=0)
    for leaf in parent["children"]:
        leaf_matrix = column_major_matrix(leaf["transform"])
        corners_in_parent = apply(leaf_matrix, box_corners(leaf))
        assert (corners_in_parent.min(axis=0) >= low - BOX_TOLERANCE_M).all()
        assert (corners_in_parent.max(axis=0) <= high + BOX_TOLERANCE_M).all()
        vertices = glb_vertices_enu(store / leaf["content"]["uri"])
        leaf_low, leaf_high = box_corners(leaf).min(axis=0), box_corners(leaf).max(axis=0)
        assert (vertices >= leaf_low - BOX_TOLERANCE_M).all()
        assert (vertices <= leaf_high + BOX_TOLERANCE_M).all()
    parent_vertices = glb_vertices_enu(store / parent["content"]["uri"])
    assert (parent_vertices >= low - BOX_TOLERANCE_M).all()
    assert (parent_vertices <= high + BOX_TOLERANCE_M).all()


def test_a_node_whose_parent_is_absent_becomes_a_root(store: Path, tmp_path: Path) -> None:
    ragged = tmp_path / "ragged"
    shutil.copytree(store, ragged)
    parent = next(t for t in stored_tiles(ragged) if t.z == PARENT_ZOOM)
    for path in node_paths(ragged, parent):
        path.unlink()
    container = tileset(ragged)
    assert len(container["children"]) == 4
    assert all("children" not in child for child in container["children"])


def test_empty_store_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no nodes"):
        export_3dtiles(tmp_path)
