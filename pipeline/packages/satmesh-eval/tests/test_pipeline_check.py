import math
from pathlib import Path

import mercantile
import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_bounds, from_origin

from satmesh_data import EA_DSM, EA_DTM, WEB_MERCATOR, EsriSource, Raster, cached_lidar_path
from satmesh_eval.pipeline_check import check_node, check_store
from satmesh_tiles import (
    ESRI_TILES_PER_LEAF_SIDE,
    MeshSettings,
    SurfacePaths,
    build_node,
    ground_path,
    node_paths,
)

LEAF = mercantile.tile(-2.0015, 53.9236, 17)
BOUNDS = mercantile.xy_bounds(LEAF)
MARGIN_M = 30
CANOPY_M = 3.0
# plane H = BASE + SLOPE_E * (E - e0) + SLOPE_N * (N - n0) in ODN, exact under bilinear sampling
BASE, SLOPE_E, SLOPE_N = 120.0, 0.2, -0.1
# float32 heights and positions within a few hundred metres of the origin
TOLERANCE_M = 2e-3
SOURCE = EsriSource.model_validate(
    {
        "SOURCE_INFO": "Vivid",
        "RESOLUTION (M)": 0.34,
        "DATE (YYYYMMDD)": "20250301",
        "FROM_CACHE_LEVEL": 12,
        "TO_CACHE_LEVEL": 19,
    }
)


def write_plane(path: Path, rise_m: float) -> None:
    to_bng = Transformer.from_crs(WEB_MERCATOR, "EPSG:27700", always_xy=True)
    corners = [
        to_bng.transform(x, y)
        for x in (BOUNDS.left, BOUNDS.right)
        for y in (BOUNDS.bottom, BOUNDS.top)
    ]
    west = math.floor(min(c[0] for c in corners)) - MARGIN_M
    south = math.floor(min(c[1] for c in corners)) - MARGIN_M
    east = math.ceil(max(c[0] for c in corners)) + MARGIN_M
    north = math.ceil(max(c[1] for c in corners)) + MARGIN_M
    easting = west + 0.5 + np.arange(east - west)[None, :]
    northing = north - 0.5 - np.arange(north - south)[:, None]
    heights = BASE + SLOPE_E * (easting - west) + SLOPE_N * (northing - south) + rise_m
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=east - west,
        height=north - south,
        count=1,
        dtype="float32",
        crs="EPSG:27700",
        transform=from_origin(west, north, 1.0, 1.0),
    ) as dst:
        dst.write(heights.astype(np.float32), 1)


@pytest.fixture
def stored(tmp_path: Path) -> tuple[Path, Path]:
    """A one-leaf store and the lidar cache its record names."""
    cache, store = tmp_path / "cache", tmp_path / "store"
    surfaces = SurfacePaths(
        dsm=cached_lidar_path(cache, EA_DSM, "box.tif"),
        dtm=cached_lidar_path(cache, EA_DTM, "box.tif"),
    )
    write_plane(surfaces.dsm, CANOPY_M)
    write_plane(surfaces.dtm, 0.0)
    side = ESRI_TILES_PER_LEAF_SIDE * 256
    texture = Raster(
        np.zeros((3, side, side), np.uint8),
        from_bounds(BOUNDS.left, BOUNDS.bottom, BOUNDS.right, BOUNDS.top, side, side),
        WEB_MERCATOR,
    )
    node = build_node(LEAF, texture, surfaces, SOURCE, MeshSettings.for_level(0, 0.1))
    glb, record = node_paths(store, LEAF)
    glb.parent.mkdir(parents=True)
    glb.write_bytes(node.glb)
    ground_path(store, LEAF).write_bytes(node.ground_tif)
    record.write_text(node.record.model_dump_json())
    return store, cache


def test_a_correct_store_reproduces_the_rasters_through_an_independent_path(
    stored: tuple[Path, Path],
) -> None:
    store, cache = stored
    (result,) = check_store(store, cache)
    assert result.tile == LEAF
    assert abs(result.vertices_against_dsm.median_m) < TOLERANCE_M
    assert result.vertices_against_dsm.quantile_95_m < TOLERANCE_M
    assert result.ground_grid_against_dtm.quantile_95_m < TOLERANCE_M


def test_a_dsm_shifted_after_the_build_shows_as_that_offset(stored: tuple[Path, Path]) -> None:
    store, cache = stored
    shifted = cached_lidar_path(cache, EA_DSM, "box.tif")
    write_plane(shifted, CANOPY_M + 1.5)
    result = check_node(store, cache, LEAF)
    assert result.vertices_against_dsm.median_m == pytest.approx(-1.5, abs=TOLERANCE_M)
    assert abs(result.ground_grid_against_dtm.median_m) < TOLERANCE_M
