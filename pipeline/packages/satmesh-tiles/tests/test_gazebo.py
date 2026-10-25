import xml.etree.ElementTree as ET
from pathlib import Path

import mercantile
import numpy as np
import pygltflib
import pytest
from fakes import FakeServices, clients, square_of_four_leaves
from pyproj import Transformer

from satmesh_tiles import build_store, export_gazebo, plan_tiles, read_record

# float32 vertices and 9 significant digits in the SDF poses, at a few hundred metres
ECEF_TOLERANCE_M = 5e-3
MODELS = 4
GEODETIC_TO_ECEF = Transformer.from_crs("EPSG:4979", "EPSG:4978", always_xy=True)


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("gazebo")
    esri, http = clients(FakeServices(), root / "cache")
    plan = plan_tiles(square_of_four_leaves()[0], esri)
    build_store(plan, root / "store", esri=esri, http=http, cache_dir=root / "cache")
    return root / "store"


def rotation_from_rpy(rpy: np.ndarray) -> np.ndarray:
    """SDF poses compose as R = Rz(yaw) Ry(pitch) Rx(roll)."""
    roll, pitch, yaw = rpy
    cr, sr, cp, sp = np.cos(roll), np.sin(roll), np.cos(pitch), np.sin(pitch)
    cy, sy = np.cos(yaw), np.sin(yaw)
    rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return rz @ ry @ rx


def pose(element: ET.Element) -> tuple[np.ndarray, np.ndarray]:
    text = element.findtext("pose")
    assert text is not None
    values = np.array([float(v) for v in text.split()])
    return values[:3], values[3:]


def glb_positions(path: Path) -> np.ndarray:
    gltf = pygltflib.GLTF2().load(str(path))
    position = gltf.meshes[0].primitives[0].attributes.POSITION
    assert position is not None
    accessor = gltf.accessors[position]
    view = gltf.bufferViews[accessor.bufferView]
    flat = np.frombuffer(gltf.binary_blob(), np.float32, accessor.count * 3, view.byteOffset)
    return flat.reshape(-1, 3).astype(np.float64)


def world_element(world_path: Path) -> ET.Element:
    root = ET.parse(world_path).getroot()  # noqa: S314 (the exporter's own output)
    world = root.find("world")
    assert world is not None
    return world


def test_each_model_places_its_mesh_at_the_nodes_ecef_position(store: Path, tmp_path: Path) -> None:
    out = tmp_path / "gz"
    world = world_element(export_gazebo(store, out))
    spherical = world.find("spherical_coordinates")
    assert spherical is not None
    assert spherical.findtext("surface_model") == "EARTH_WGS84"
    assert spherical.findtext("world_frame_orientation") == "ENU"
    lon, lat, height = (
        float(spherical.findtext(key) or "nan")
        for key in ("longitude_deg", "latitude_deg", "elevation")
    )
    # PROJ's topocentric operation, run backwards, takes world ENU to geodetic
    topocentric = Transformer.from_pipeline(
        "+proj=pipeline +step +proj=cart +ellps=WGS84 "
        f"+step +proj=topocentric +ellps=WGS84 +lon_0={lon} +lat_0={lat} +h_0={height}"
    )
    models = world.findall("model")
    assert len(models) == MODELS
    for model in models:
        assert model.findtext("static") == "true"
        position, rpy = pose(model)
        visual = model.find("link/visual")
        assert visual is not None
        _, visual_rpy = pose(visual)
        uri = visual.findtext("geometry/mesh/uri")
        assert uri is not None
        zoom, x, y = (int(v) for v in model.attrib["name"].split("_")[1:])
        local = glb_positions(out / uri)
        rotation = rotation_from_rpy(rpy) @ rotation_from_rpy(visual_rpy)
        world_enu = local @ rotation.T + position
        geodetic = np.array([topocentric.transform(*p, direction="INVERSE") for p in world_enu])
        actual = np.column_stack(GEODETIC_TO_ECEF.transform(*geodetic.T))
        record = read_record(store, mercantile.Tile(x, y, zoom))
        tile_enu = np.column_stack([local[:, 0], -local[:, 2], local[:, 1]])
        homogeneous = np.column_stack([tile_enu, np.ones(len(tile_enu))])
        expected = (np.array(record.enu_to_ecef) @ homogeneous.T).T[:, :3]
        np.testing.assert_allclose(actual, expected, atol=ECEF_TOLERANCE_M)


def test_visual_and_collision_use_the_same_copied_mesh(store: Path, tmp_path: Path) -> None:
    out = tmp_path / "gz"
    world = world_element(export_gazebo(store, out))
    for model in world.findall("model"):
        uris = {
            model.findtext(f"link/{kind}/geometry/mesh/uri") for kind in ("visual", "collision")
        }
        assert len(uris) == 1
        (uri,) = uris
        assert uri is not None
        assert (out / uri).read_bytes()[:4] == b"glTF"


def test_a_performer_adds_one_level_per_tile_around_the_tile(store: Path, tmp_path: Path) -> None:
    world = world_element(export_gazebo(store, tmp_path / "gz", performer="robot"))
    plugin = world.find("plugin[@name='gz::sim']")
    assert plugin is not None
    assert plugin.findtext("performer/ref") == "robot"
    levels = plugin.findall("level")
    assert {level.findtext("ref") for level in levels} == {
        m.attrib["name"] for m in world.findall("model")
    }
    for level in levels:
        size = [float(v) for v in (level.findtext("geometry/box/size") or "").split()]
        assert min(size[:2]) > 100  # a 4 x 4 Esri tile leaf at z17 is about 180 m wide


def test_no_levels_without_a_performer(store: Path, tmp_path: Path) -> None:
    world = world_element(export_gazebo(store, tmp_path / "gz"))
    assert world.find("plugin[@name='gz::sim']") is None
