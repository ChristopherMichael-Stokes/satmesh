import math
from pathlib import Path

import mercantile
import numpy as np
import pygltflib
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_bounds, from_origin

from satmesh_data import WEB_MERCATOR, EsriSource, Raster
from satmesh_tiles import (
    ESRI_TILES_PER_LEAF_SIDE,
    MeshSettings,
    NodeRecord,
    build_node,
    esri_tiles,
)

UPPER_AIRE_LON, UPPER_AIRE_LAT = -2.0015, 53.9236
LEAF_ZOOM = 17
MAX_ERROR_M = 0.1
MESH_SETTINGS = MeshSettings.for_level(0, MAX_ERROR_M)
# float32 vertex positions within a few hundred metres of the origin resolve about 3e-5 m
GLB_POSITION_TOLERANCE_M = 1e-3
UV_TOLERANCE = 1e-5
TILE_PX = 256
# plane H = ORIGIN_H + SLOPE_E * (E - e0) + SLOPE_N * (N - n0), exact under bilinear sampling
ORIGIN_H, SLOPE_E, SLOPE_N = 120.0, 0.2, -0.1
DTM_MARGIN_M = 30

LEAF = mercantile.tile(UPPER_AIRE_LON, UPPER_AIRE_LAT, LEAF_ZOOM)
BOUNDS = mercantile.xy_bounds(LEAF)
TO_BNG = Transformer.from_crs(WEB_MERCATOR, "EPSG:27700", always_xy=True)
BNG_ODN_TO_GEODETIC = Transformer.from_crs("EPSG:7405", "EPSG:4979", always_xy=True)
GEODETIC_TO_BNG_ODN = BNG_ODN_TO_GEODETIC.transform
ESRI_SOURCE = EsriSource.model_validate(
    {
        "SOURCE_INFO": "Vivid",
        "RESOLUTION (M)": 0.34,
        "DATE (YYYYMMDD)": "20250301",
        "FROM_CACHE_LEVEL": 12,
        "TO_CACHE_LEVEL": 19,
    }
)


def plane_height(easting: np.ndarray, northing: np.ndarray, e0: float, n0: float) -> np.ndarray:
    return ORIGIN_H + SLOPE_E * (easting - e0) + SLOPE_N * (northing - n0)


def write_plane_dtm(path: Path) -> tuple[float, float]:
    corners = [
        TO_BNG.transform(x, y)
        for x in (BOUNDS.left, BOUNDS.right)
        for y in (BOUNDS.bottom, BOUNDS.top)
    ]
    west = math.floor(min(c[0] for c in corners)) - DTM_MARGIN_M
    south = math.floor(min(c[1] for c in corners)) - DTM_MARGIN_M
    east = math.ceil(max(c[0] for c in corners)) + DTM_MARGIN_M
    north = math.ceil(max(c[1] for c in corners)) + DTM_MARGIN_M
    cols, rows = east - west, north - south
    easting = west + 0.5 + np.arange(cols)[None, :]
    northing = north - 0.5 - np.arange(rows)[:, None]
    heights = plane_height(easting, northing, west, south)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=cols,
        height=rows,
        count=1,
        dtype="float32",
        crs="EPSG:27700",
        transform=from_origin(west, north, 1.0, 1.0),
    ) as dst:
        dst.write(heights.astype(np.float32), 1)
    return float(west), float(south)


def leaf_texture() -> Raster:
    side = ESRI_TILES_PER_LEAF_SIDE * TILE_PX
    pixels = np.zeros((3, side, side), np.uint8)
    return Raster(
        pixels,
        from_bounds(BOUNDS.left, BOUNDS.bottom, BOUNDS.right, BOUNDS.top, side, side),
        WEB_MERCATOR,
    )


def positions(glb: bytes) -> tuple[np.ndarray, np.ndarray]:
    gltf = pygltflib.GLTF2.load_from_bytes(glb)
    primitive = gltf.meshes[0].primitives[0]
    blob = gltf.binary_blob()
    out = []
    for index, width in ((primitive.attributes.POSITION, 3), (primitive.attributes.TEXCOORD_0, 2)):
        accessor = gltf.accessors[index]
        view = gltf.bufferViews[accessor.bufferView]
        out.append(
            np.frombuffer(blob, np.float32, accessor.count * width, view.byteOffset).reshape(
                -1, width
            )
        )
    return out[0], out[1]


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[bytes, NodeRecord, float, float]:
    dtm = tmp_path_factory.mktemp("dtm") / "plane.tif"
    west, south = write_plane_dtm(dtm)
    leaf = build_node(LEAF, leaf_texture(), dtm, ESRI_SOURCE, MESH_SETTINGS)
    return leaf.glb, leaf.record, west, south


def test_esri_tiles_are_the_sixteen_children_two_zooms_down() -> None:
    tiles = esri_tiles(LEAF)
    assert len(tiles) == 16
    assert {t.z for t in tiles} == {LEAF_ZOOM + 2}
    assert {mercantile.parent(t, zoom=LEAF_ZOOM) for t in tiles} == {LEAF}


def test_uv_follows_each_vertex_position_on_the_web_mercator_grid(
    built: tuple[bytes, NodeRecord, float, float],
) -> None:
    glb, record, _, _ = built
    local, uv = positions(glb)
    enu_to_ecef = np.array(record.enu_to_ecef)
    enu = np.column_stack([local[:, 0], -local[:, 2], local[:, 1]])
    ecef = (enu_to_ecef @ np.column_stack([enu, np.ones(len(enu))]).T).T[:, :3]
    lon, lat, _ = Transformer.from_crs("EPSG:4978", "EPSG:4979", always_xy=True).transform(*ecef.T)
    x, y = Transformer.from_crs("EPSG:4326", WEB_MERCATOR, always_xy=True).transform(lon, lat)
    # skirt vertices hang below their boundary vertex, which does not move them sideways
    np.testing.assert_allclose(
        uv[:, 0], (x - BOUNDS.left) / (BOUNDS.right - BOUNDS.left), atol=UV_TOLERANCE
    )
    # glTF's texture origin is top-left, so v counts down from the north edge
    np.testing.assert_allclose(
        uv[:, 1], (BOUNDS.top - y) / (BOUNDS.top - BOUNDS.bottom), atol=UV_TOLERANCE
    )


def test_heights_match_the_dtm_in_ordnance_datum_through_the_grids(
    built: tuple[bytes, NodeRecord, float, float],
) -> None:
    glb, record, west, south = built
    local, _ = positions(glb)
    enu_to_ecef = np.array(record.enu_to_ecef)
    terrain = local[: record.terrain_vertices]
    enu = np.column_stack([terrain[:, 0], -terrain[:, 2], terrain[:, 1]])
    ecef = (enu_to_ecef @ np.column_stack([enu, np.ones(len(enu))]).T).T[:, :3]
    lon, lat, height = Transformer.from_crs("EPSG:4978", "EPSG:4979", always_xy=True).transform(
        *ecef.T
    )
    easting, northing, odn = Transformer.from_crs(
        "EPSG:4979", "EPSG:7405", always_xy=True
    ).transform(lon, lat, height)
    expected = plane_height(easting, northing, west, south)
    assert np.abs(odn - expected).max() <= MAX_ERROR_M + GLB_POSITION_TOLERANCE_M


def test_record_counts_match_the_mesh(built: tuple[bytes, NodeRecord, float, float]) -> None:
    glb, record, _, _ = built
    local, _ = positions(glb)
    assert record.vertices == len(local)
    assert record.terrain_vertices < record.vertices
    assert record.error_m <= MAX_ERROR_M
    assert record.texture_px == (1024, 1024)
    assert record.geoid_separation_m == pytest.approx(50.8, abs=0.2)
    assert record.imagery.zoom == LEAF_ZOOM + 2


def test_dtm_that_misses_the_leaf_raises(tmp_path: Path) -> None:
    dtm = tmp_path / "small.tif"
    with rasterio.open(
        dtm,
        "w",
        driver="GTiff",
        width=10,
        height=10,
        count=1,
        dtype="float32",
        crs="EPSG:27700",
        transform=from_origin(400000, 447500, 1.0, 1.0),
    ) as dst:
        dst.write(np.zeros((10, 10), np.float32), 1)
    with pytest.raises(ValueError, match="does not cover"):
        build_node(LEAF, leaf_texture(), dtm, ESRI_SOURCE, MESH_SETTINGS)


def test_texture_that_is_not_the_leaf_raises(tmp_path: Path) -> None:
    dtm = tmp_path / "plane.tif"
    write_plane_dtm(dtm)
    other = mercantile.Tile(LEAF.x + 1, LEAF.y, LEAF.z)
    bounds = mercantile.xy_bounds(other)
    side = ESRI_TILES_PER_LEAF_SIDE * TILE_PX
    wrong = Raster(
        np.zeros((3, side, side), np.uint8),
        from_bounds(bounds.left, bounds.bottom, bounds.right, bounds.top, side, side),
        WEB_MERCATOR,
    )
    with pytest.raises(ValueError, match="not the tile"):
        build_node(LEAF, wrong, dtm, ESRI_SOURCE, MESH_SETTINGS)
