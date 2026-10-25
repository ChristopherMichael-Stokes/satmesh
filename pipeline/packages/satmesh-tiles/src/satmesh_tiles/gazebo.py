"""Gazebo world: one static model per finest-level node, georeferenced by spherical coordinates."""

import itertools
import shutil
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path

import mercantile
import numpy as np
from scipy.spatial.transform import Rotation

from satmesh_core import EnuFrame, ecef_to_geodetic
from satmesh_tiles.area import area_frame, leaf_records
from satmesh_tiles.node import NodeRecord
from satmesh_tiles.tiler import node_paths

WORLD_FILE = "world.sdf"
MESH_DIR = Path("meshes")
SDF_VERSION = "1.9"
# glTF is Y up and gz-common loads its vertices as authored (AssimpLoader.cc keeps the glTF root
# transform), while Gazebo is Z up: a roll of +90 degrees about X sends glTF (x east, y up,
# z south) to (x east, y north, z up).
GLTF_TO_Z_UP_RPY = (float(np.pi / 2), 0.0, 0.0)
# a tile's level box reaches this far past its extent so a tile loads before a robot reaches it
LEVEL_BUFFER_M = 100.0
BOX_CORNER_SIGNS = np.array(list(itertools.product((-1.0, 1.0), repeat=3)))
SYSTEM_PLUGINS = (
    ("gz-sim-physics-system", "gz::sim::systems::Physics"),
    ("gz-sim-user-commands-system", "gz::sim::systems::UserCommands"),
    ("gz-sim-scene-broadcaster-system", "gz::sim::systems::SceneBroadcaster"),
    ("gz-sim-sensors-system", "gz::sim::systems::Sensors"),
)


def export_gazebo(store_dir: Path, out_dir: Path, performer: str | None = None) -> Path:
    """Write `world.sdf` and `meshes/` to `out_dir` and return the world path.

    Every finest-level node becomes a static model posed in one ENU world frame tangent at the
    area's centre, so the world's origin latitude, longitude and elevation (ellipsoidal height, as
    gz-math reads it) locate it on the globe and NavSat reads true coordinates. A model's pose
    carries the small tilt between its own ENU frame and the world's. With `performer`, the name of
    the robot model whose position loads tiles, each tile also gets a level so only nearby tiles
    are loaded (`gz sim --levels`).
    """
    records = leaf_records(store_dir)
    area = area_frame(records)
    (out_dir / MESH_DIR).mkdir(parents=True, exist_ok=True)
    sdf = ET.Element("sdf", version=SDF_VERSION)
    world = ET.SubElement(sdf, "world", name="satmesh")
    for filename, name in SYSTEM_PLUGINS:
        plugin = ET.SubElement(world, "plugin", filename=filename, name=name)
        if filename == "gz-sim-sensors-system":
            ET.SubElement(plugin, "render_engine").text = "ogre2"
    _add_spherical_coordinates(world, area)
    _add_sun(world)
    levels = []
    for tile, record in records.items():
        mesh_uri = (MESH_DIR / _name(tile)).with_suffix(".glb")
        shutil.copy2(node_paths(store_dir, tile)[0], out_dir / mesh_uri)
        matrix = _tile_to_world(record, area)
        _add_model(world, _name(tile), mesh_uri.as_posix(), matrix)
        levels.append((tile, record, matrix))
    if performer is not None:
        _add_levels(world, performer, levels)
    ET.indent(sdf)
    path = out_dir / WORLD_FILE
    path.write_text(ET.tostring(sdf, encoding="unicode", xml_declaration=True))
    return path


def _name(tile: mercantile.Tile) -> str:
    return f"tile_{tile.z}_{tile.x}_{tile.y}"


def _tile_to_world(record: NodeRecord, area: EnuFrame) -> np.ndarray:
    """Return the 4 x 4 matrix taking a node's ENU frame to the area ENU frame."""
    return np.linalg.inv(area.enu_to_ecef_matrix()) @ np.array(record.enu_to_ecef)


def _pose_text(position: np.ndarray, rpy: Sequence[float]) -> str:
    return " ".join(f"{v:.9g}" for v in (*position, *rpy))


def _add_spherical_coordinates(world: ET.Element, area: EnuFrame) -> None:
    lon, lat, height = ecef_to_geodetic().transform(*area.origin_ecef)
    spherical = ET.SubElement(world, "spherical_coordinates")
    ET.SubElement(spherical, "surface_model").text = "EARTH_WGS84"
    ET.SubElement(spherical, "world_frame_orientation").text = "ENU"
    ET.SubElement(spherical, "latitude_deg").text = f"{lat:.12g}"
    ET.SubElement(spherical, "longitude_deg").text = f"{lon:.12g}"
    ET.SubElement(spherical, "elevation").text = f"{height:.9g}"
    ET.SubElement(spherical, "heading_deg").text = "0"


def _add_sun(world: ET.Element) -> None:
    light = ET.SubElement(world, "light", type="directional", name="sun")
    ET.SubElement(light, "cast_shadows").text = "true"
    ET.SubElement(light, "pose").text = "0 0 1000 0 0 0"
    ET.SubElement(light, "diffuse").text = "1 1 1 1"
    ET.SubElement(light, "specular").text = "0.2 0.2 0.2 1"
    ET.SubElement(light, "direction").text = "-0.3 0.2 -0.9"


def _add_model(world: ET.Element, name: str, mesh_uri: str, matrix: np.ndarray) -> None:
    model = ET.SubElement(world, "model", name=name)
    ET.SubElement(model, "static").text = "true"
    rpy = Rotation.from_matrix(matrix[:3, :3]).as_euler("xyz")
    ET.SubElement(model, "pose").text = _pose_text(matrix[:3, 3], rpy)
    link = ET.SubElement(model, "link", name="link")
    for kind in ("visual", "collision"):
        part = ET.SubElement(link, kind, name=kind)
        ET.SubElement(part, "pose").text = _pose_text(np.zeros(3), GLTF_TO_Z_UP_RPY)
        mesh = ET.SubElement(ET.SubElement(part, "geometry"), "mesh")
        ET.SubElement(mesh, "uri").text = mesh_uri


def _add_levels(
    world: ET.Element, performer: str, levels: list[tuple[mercantile.Tile, NodeRecord, np.ndarray]]
) -> None:
    plugin = ET.SubElement(world, "plugin", name="gz::sim", filename="dummy")
    performer_element = ET.SubElement(plugin, "performer", name=f"performer_{performer}")
    ET.SubElement(performer_element, "ref").text = performer
    box = ET.SubElement(ET.SubElement(performer_element, "geometry"), "box")
    ET.SubElement(box, "size").text = "2 2 2"
    for tile, record, matrix in levels:
        corners = _box_corners(record, matrix)
        low, high = corners.min(axis=0), corners.max(axis=0)
        level = ET.SubElement(plugin, "level", name=f"level_{_name(tile)}")
        ET.SubElement(level, "pose").text = _pose_text((low + high) / 2, (0.0, 0.0, 0.0))
        size = ET.SubElement(ET.SubElement(level, "geometry"), "box")
        ET.SubElement(size, "size").text = " ".join(f"{v:.9g}" for v in high - low)
        ET.SubElement(level, "buffer").text = f"{LEVEL_BUFFER_M:g}"
        ET.SubElement(level, "ref").text = _name(tile)


def _box_corners(record: NodeRecord, matrix: np.ndarray) -> np.ndarray:
    """The node's bounding box corners in world ENU."""
    low, high = np.array(record.enu_min), np.array(record.enu_max)
    local = (low + high) / 2 + BOX_CORNER_SIGNS * (high - low) / 2
    return (matrix @ np.column_stack([local, np.ones(len(local))]).T).T[:, :3]
