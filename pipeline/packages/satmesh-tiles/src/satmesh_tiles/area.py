"""One GLB holding every finest-level node of a store, in a single local frame."""

from pathlib import Path

import mercantile
import numpy as np
import trimesh

from satmesh_core import EnuFrame
from satmesh_tiles.node import NodeRecord
from satmesh_tiles.tiler import node_paths, read_record
from satmesh_tiles.tileset import stored_tiles

EXTRAS_KEY = "satmesh"
# ENU (x east, y north, z up) to glTF (x east, y up, z south), as a 4 x 4 matrix
ENU_TO_GLTF = np.array(
    [[1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, -1.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
)


def export_area_glb(store_dir: Path, out_path: Path) -> EnuFrame:
    """Write the leaves of `store_dir` as one GLB in the glTF frame of a single area ENU frame.

    The frame is tangent at the mean of the nodes' ECEF origins. Each leaf is moved by its own
    ENU-to-ECEF matrix and then into the area frame, so tiles stay on the ellipsoid instead of a
    flat plane that would sit 8 m off the ground 10 km out. The area frame is returned and also
    stored in the scene's extras for placing the mesh on the map.
    """
    records = leaf_records(store_dir)
    matrices = {tile: np.array(record.enu_to_ecef) for tile, record in records.items()}
    area = area_frame(records)
    to_area_enu = np.linalg.inv(area.enu_to_ecef_matrix())
    scene = trimesh.Scene(metadata={EXTRAS_KEY: _extras(area)})
    for tile in records:
        tile_to_area = ENU_TO_GLTF @ to_area_enu @ matrices[tile] @ np.linalg.inv(ENU_TO_GLTF)
        loaded = trimesh.load_scene(node_paths(store_dir, tile)[0])
        for name, geometry in loaded.geometry.items():
            scene.add_geometry(
                geometry,
                node_name=f"{tile.z}/{tile.x}/{tile.y}",
                geom_name=f"{name}-{tile.z}-{tile.x}-{tile.y}",
                transform=tile_to_area,
            )
    out_path.write_bytes(scene.export(file_type="glb"))
    return area


def leaf_records(store_dir: Path) -> dict[mercantile.Tile, NodeRecord]:
    """Return the record of every finest-level node: those with no children in the store."""
    tiles = stored_tiles(store_dir)
    leaves = sorted(
        tile for tile in tiles if not any(kid in tiles for kid in mercantile.children(tile))
    )
    if not leaves:
        msg = f"no nodes in store {store_dir}"
        raise ValueError(msg)
    return {tile: read_record(store_dir, tile) for tile in leaves}


def area_frame(records: dict[mercantile.Tile, NodeRecord]) -> EnuFrame:
    """Return the ENU frame tangent at the mean of the nodes' ECEF origins."""
    origins = [np.array(record.enu_to_ecef)[:3, 3] for record in records.values()]
    return EnuFrame.at_ecef(np.mean(origins, axis=0))


def _extras(area: EnuFrame) -> dict[str, object]:
    return {
        "axes": "x east, y up, z south; metres, tangent plane at origin_ecef",
        "origin_ecef": [float(v) for v in area.origin_ecef],
        "enu_to_ecef": [[float(v) for v in row] for row in area.enu_to_ecef_matrix()],
    }
