from pathlib import Path

import mercantile
import numpy as np
import pygltflib
import pytest
from fakes import FakeServices, clients, square_of_four_leaves

from satmesh_tiles import build_store, export_area_glb, node_paths, plan_tiles, read_record

ECEF_TOLERANCE_M = 2e-3  # float32 vertices and node matrices at a few hundred metres


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("area")
    esri, http = clients(FakeServices(), root / "cache")
    plan = plan_tiles(square_of_four_leaves()[0], esri)
    build_store(plan, root / "store", esri=esri, http=http, cache_dir=root / "cache")
    return root / "store"


def vertices(gltf: pygltflib.GLTF2, mesh_index: int) -> np.ndarray:
    position = gltf.meshes[mesh_index].primitives[0].attributes.POSITION
    assert position is not None
    accessor = gltf.accessors[position]
    view = gltf.bufferViews[accessor.bufferView]
    flat = np.frombuffer(gltf.binary_blob(), np.float32, accessor.count * 3, view.byteOffset)
    return flat.reshape(-1, 3).astype(np.float64)


def apply(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    return (matrix @ np.column_stack([points, np.ones(len(points))]).T).T[:, :3]


def test_every_leaf_vertex_lands_at_its_own_ecef_position(store: Path, tmp_path: Path) -> None:
    out = tmp_path / "area.glb"
    export_area_glb(store, out)
    gltf = pygltflib.GLTF2().load(str(out))
    extras = gltf.scenes[0].extras["satmesh"]
    area_to_ecef = np.array(extras["enu_to_ecef"])
    leaves = stored_leaf_tiles(store)
    assert len(gltf.meshes) == len(leaves) == 4
    for node in gltf.nodes:
        tile = mercantile.Tile(
            *(int(v) for v in node.name.split("/")[1:]), int(node.name.split("/")[0])
        )
        record = read_record(store, tile)
        node_matrix = np.array(node.matrix).reshape(4, 4).T
        area_gltf = apply(node_matrix, vertices(gltf, node.mesh))
        area_enu = np.column_stack([area_gltf[:, 0], -area_gltf[:, 2], area_gltf[:, 1]])
        actual = apply(area_to_ecef, area_enu)
        own = pygltflib.GLTF2().load(str(node_paths(store, tile)[0]))
        own_local = vertices(own, 0)
        own_enu = np.column_stack([own_local[:, 0], -own_local[:, 2], own_local[:, 1]])
        expected = apply(np.array(record.enu_to_ecef), own_enu)
        np.testing.assert_allclose(actual, expected, atol=ECEF_TOLERANCE_M)


def stored_leaf_tiles(store: Path) -> list[mercantile.Tile]:
    return [
        mercantile.Tile(int(p.parent.name), int(p.stem), int(p.parent.parent.name))
        for p in (store / "nodes").glob("*/*/*.json")
        if int(p.parent.parent.name) == 17
    ]


def test_empty_store_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no nodes"):
        export_area_glb(tmp_path, tmp_path / "area.glb")
