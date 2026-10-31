"""A node built from a GLO-30-style surface pair: WGS 84 grid, EGM2008 heights, no lidar."""

import math
from pathlib import Path

import mercantile
import numpy as np
import pygltflib
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_bounds, from_origin

from satmesh_data import WEB_MERCATOR, EsriSource, Raster, Surface, SurfacePair
from satmesh_tiles import ESRI_TILES_PER_LEAF_SIDE, MeshSettings, build_node

SANAA_LON, SANAA_LAT = 44.207, 15.355
LEAF = mercantile.tile(SANAA_LON, SANAA_LAT, 17)
BOUNDS = mercantile.xy_bounds(LEAF)
ARC_SECOND_DEG = 1 / 3600
# plane h = H0 + SLOPE_LON * (lon - lon0) + SLOPE_LAT * (lat - lat0), exact under bilinear sampling
H0, SLOPE_LON, SLOPE_LAT = 2250.0, 3000.0, -2000.0
CANOPY_M = 4.0
MAX_ERROR_M = 0.1
GLB_POSITION_TOLERANCE_M = 1e-3
# EGM2008 geoid height at Sana'a sampled from PROJ's us_nga_egm08_25 grid (region-research.md)
SANAA_GEOID_M = -4.98
SANAA_ACCURACY_M = 8.47
HEIGHT_CRS = "EPSG:4326+3855"


def write_plane(path: Path, rise_m: float) -> tuple[float, float]:
    west_deg, south_deg, east_deg, north_deg = (
        math.floor(v / ARC_SECOND_DEG) * ARC_SECOND_DEG
        for v in (SANAA_LON - 0.005, SANAA_LAT - 0.005, SANAA_LON + 0.005, SANAA_LAT + 0.005)
    )
    cols = round((east_deg - west_deg) / ARC_SECOND_DEG)
    rows = round((north_deg - south_deg) / ARC_SECOND_DEG)
    lon = west_deg + ARC_SECOND_DEG * (0.5 + np.arange(cols))[None, :]
    lat = north_deg - ARC_SECOND_DEG * (0.5 + np.arange(rows))[:, None]
    heights = H0 + SLOPE_LON * (lon - west_deg) + SLOPE_LAT * (lat - south_deg) + rise_m
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=cols,
        height=rows,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(west_deg, north_deg, ARC_SECOND_DEG, ARC_SECOND_DEG),
    ) as dst:
        dst.write(heights.astype(np.float32), 1)
    return west_deg, south_deg


def texture() -> Raster:
    side = ESRI_TILES_PER_LEAF_SIDE * 256
    return Raster(
        np.zeros((3, side, side), np.uint8),
        from_bounds(BOUNDS.left, BOUNDS.bottom, BOUNDS.right, BOUNDS.top, side, side),
        WEB_MERCATOR,
    )


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory):
    directory = tmp_path_factory.mktemp("glo30")
    dsm, dtm = directory / "dsm.tif", directory / "dtm.tif"
    origin = write_plane(dsm, CANOPY_M)
    write_plane(dtm, 0.0)
    pair = SurfacePair(
        dsm=Surface(dsm, "EPSG:4326", HEIGHT_CRS),
        dtm=Surface(dtm, "EPSG:4326", HEIGHT_CRS),
        source="copernicus-glo30-test",
        attribution="test",
        ground_is_surface=False,
        provenance=None,
    )
    source = EsriSource.model_validate(
        {
            "SOURCE_INFO": "Vivid Mosaic Metro",
            "RESOLUTION (M)": 0.31,
            "DATE (YYYYMMDD)": "20251229",
            "ACCURACY (M)": str(SANAA_ACCURACY_M),
            "FROM_CACHE_LEVEL": 12,
            "TO_CACHE_LEVEL": 19,
        }
    )
    node = build_node(LEAF, texture(), pair, source, MeshSettings.for_level(0, MAX_ERROR_M))
    return node, origin


def vertex_ecef(glb: bytes, enu_to_ecef: np.ndarray, count: int) -> np.ndarray:
    gltf = pygltflib.GLTF2.load_from_bytes(glb)
    accessor = gltf.accessors[gltf.meshes[0].primitives[0].attributes.POSITION]
    view = gltf.bufferViews[accessor.bufferView]
    local = np.frombuffer(gltf.binary_blob(), np.float32, accessor.count * 3, view.byteOffset)
    local = local.reshape(-1, 3)[:count]
    enu = np.column_stack([local[:, 0], -local[:, 2], local[:, 1]])
    return (enu_to_ecef @ np.column_stack([enu, np.ones(len(enu))]).T).T[:, :3]


def test_record_names_the_source_the_datum_and_the_imagery_accuracy(built) -> None:
    record = built[0].record
    assert record.vertical_crs == HEIGHT_CRS
    assert record.elevation_source == "copernicus-glo30-test"
    assert record.position is not None
    assert record.position.status == "uncorrected"
    assert record.position.error_bound_m == SANAA_ACCURACY_M


def test_geoid_separation_is_egm2008_at_sanaa(built) -> None:
    record = built[0].record
    assert record.geoid_separation_m == pytest.approx(SANAA_GEOID_M, abs=0.1)
    assert record.origin_ellipsoidal_height_m - record.origin_orthometric_height_m == pytest.approx(
        record.geoid_separation_m, abs=0.01
    )


def test_mesh_heights_match_the_dsm_in_egm2008_through_an_independent_path(built) -> None:
    node, (west_deg, south_deg) = built
    ecef = vertex_ecef(node.glb, np.array(node.record.enu_to_ecef), node.record.terrain_vertices)
    lon, lat, ellipsoidal = Transformer.from_crs(
        "EPSG:4978", "EPSG:4979", always_xy=True
    ).transform(*ecef.T)
    _, _, orthometric = Transformer.from_crs("EPSG:4979", HEIGHT_CRS, always_xy=True).transform(
        lon, lat, ellipsoidal
    )
    expected = H0 + SLOPE_LON * (lon - west_deg) + SLOPE_LAT * (lat - south_deg) + CANOPY_M
    assert np.abs(orthometric - expected).max() <= MAX_ERROR_M + GLB_POSITION_TOLERANCE_M
