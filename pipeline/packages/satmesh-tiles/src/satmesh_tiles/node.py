"""One node of the tile store: a textured, georeferenced terrain mesh on the Esri tile grid."""

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import mercantile
import numpy as np
import rasterio
from pydantic import BaseModel, ConfigDict
from pyproj import Transformer
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from scipy.ndimage import map_coordinates

from satmesh_core import (
    WGS84,
    EnuFrame,
    bng_odn_to_wgs84,
    geodetic_to_ecef,
    wgs84_to_bng,
)
from satmesh_data import WEB_MERCATOR, EsriSource, Raster
from satmesh_mesh import (
    add_skirts,
    glb_bytes,
    triangulate_heights,
    upward,
)

ESRI_TILES_PER_LEAF_SIDE = 4
LEAF_ZOOM_DEPTH = 2  # log2(ESRI_TILES_PER_LEAF_SIDE): a leaf's Esri tiles are 2 zooms deeper
# Half the EA LIDAR Composite pixel size: with nearest-pixel sampling of the DSM each of its pixels
# is hit by four grid nodes, so the 1 m crowns and roof edges survive. At 1 m spacing the nodes fall
# between pixel centres and nearest sampling drops or doubles pixels instead.
LEAF_GRID_SPACING_M = 0.5
# The gap between two neighbouring tiles' edges is at most the sum of their TIN errors, which is
# under twice the coarser tile's error; twice that again leaves margin.
SKIRT_DEPTH_PER_ERROR = 4.0
# raster index of a pixel centre is half a pixel inside its corner coordinate
PIXEL_CENTRE_OFFSET = 0.5
EDGE_TOLERANCE_M = 1e-6
# scipy.ndimage spline orders: the DSM keeps its own pixel values, the smooth DTM is interpolated
NEAREST, BILINEAR = 0, 1


@dataclass(frozen=True)
class MeshSettings:
    """How finely a node is meshed: height grid spacing and TIN error, both in ground metres."""

    grid_spacing_m: float
    max_error_m: float

    @classmethod
    def for_level(cls, levels_above_leaf: int, leaf_max_error_m: float) -> "MeshSettings":
        """Settings for a node `levels_above_leaf` up the tree: both double per level."""
        scale = 2**levels_above_leaf
        return cls(LEAF_GRID_SPACING_M * scale, leaf_max_error_m * scale)


class ImageryRecord(BaseModel):
    """Where a node's texture came from; `zoom` is the Esri zoom whose pixel size it matches."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    resolution_m: float
    capture_date: date | None
    zoom: int


class NodeRecord(BaseModel):
    """Georeference and provenance of one node; the node's GLB holds the geometry.

    The GLB is in the glTF frame (x east, y up, z south) in ground metres, origin at `enu_origin`.
    `enu_to_ecef` is the row-major 4 x 4 matrix taking ENU (x east, y north, z up) to ECEF, and
    `enu_min` and `enu_max` bound every vertex, skirts included, in that ENU frame.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    z: int
    x: int
    y: int
    origin_lon: float
    origin_lat: float
    origin_ellipsoidal_height_m: float
    origin_odn_height_m: float
    geoid_separation_m: float
    enu_to_ecef: tuple[tuple[float, float, float, float], ...]
    enu_min: tuple[float, float, float]
    enu_max: tuple[float, float, float]
    grid_spacing_m: float
    grid_nodes: int
    terrain_vertices: int
    vertices: int
    triangles: int
    max_error_m: float
    error_m: float
    skirt_depth_m: float
    texture_px: tuple[int, int]
    imagery: ImageryRecord
    dsm: str
    dtm: str


@dataclass(frozen=True)
class Node:
    """A built node: its GLB bytes, its ground height grid as GeoTIFF bytes, and its record."""

    glb: bytes
    ground_tif: bytes
    record: NodeRecord


def esri_tiles(leaf: mercantile.Tile) -> list[mercantile.Tile]:
    """Return the 4 x 4 Esri tiles under `leaf`, row by row from the north-west."""
    zoom = leaf.z + LEAF_ZOOM_DEPTH
    return [
        mercantile.Tile(
            leaf.x * ESRI_TILES_PER_LEAF_SIDE + dx, leaf.y * ESRI_TILES_PER_LEAF_SIDE + dy, zoom
        )
        for dy in range(ESRI_TILES_PER_LEAF_SIDE)
        for dx in range(ESRI_TILES_PER_LEAF_SIDE)
    ]


@dataclass(frozen=True)
class SurfacePaths:
    """The BNG GeoTIFFs of one node: first-return DSM (visual) and DTM (ground)."""

    dsm: Path
    dtm: Path


def build_node(
    node: mercantile.Tile,
    texture: Raster,
    surfaces: SurfacePaths,
    imagery: EsriSource,
    settings: MeshSettings,
) -> Node:
    """Mesh `node` from the BNG first-return DSM and drape `texture`, which covers the node.

    The height grids are sampled every `settings.grid_spacing_m` ground metres on the node's own
    Web Mercator grid, so every grid node has an exact texture coordinate and a neighbouring node
    samples identical heights along a shared edge. The DSM takes the value of the nearest pixel and
    the DTM is interpolated bilinearly. Heights are ODN; the mesh is placed in ENU
    through OSTN15 and OSGM15. The DTM is not meshed: its sampled grid is returned as a GeoTIFF
    for ground queries and collision.
    """
    bounds = mercantile.xy_bounds(node)
    _require_texture_matches(texture, bounds)
    grid = _sample_grid(bounds, surfaces, settings.grid_spacing_m)
    tin = triangulate_heights(grid.odn_heights, settings.max_error_m)
    frame = EnuFrame.at(grid.origin_ecef, grid.origin_lon, grid.origin_lat)
    enu = frame.to_enu(grid.ecef[tin.rows, tin.columns])
    vertices = np.column_stack([enu[:, 0], enu[:, 2], -enu[:, 1]])
    last = grid.odn_heights.shape[0] - 1
    uv = np.column_stack([tin.columns / last, 1 - tin.rows / last])
    triangles = upward(vertices, tin.triangles)
    skirt_depth_m = SKIRT_DEPTH_PER_ERROR * settings.max_error_m
    all_vertices, all_uv, all_triangles = add_skirts(vertices, uv, triangles, skirt_depth_m)
    all_enu = np.column_stack([all_vertices[:, 0], -all_vertices[:, 2], all_vertices[:, 1]])
    record = NodeRecord(
        z=node.z,
        x=node.x,
        y=node.y,
        origin_lon=grid.origin_lon,
        origin_lat=grid.origin_lat,
        origin_ellipsoidal_height_m=grid.origin_height_m,
        origin_odn_height_m=grid.origin_height_m - grid.geoid_separation_m,
        geoid_separation_m=grid.geoid_separation_m,
        enu_to_ecef=tuple(tuple(float(v) for v in row) for row in frame.enu_to_ecef_matrix()),
        enu_min=_triple(all_enu.min(axis=0)),
        enu_max=_triple(all_enu.max(axis=0)),
        grid_spacing_m=settings.grid_spacing_m,
        grid_nodes=grid.odn_heights.size,
        terrain_vertices=len(vertices),
        vertices=len(all_vertices),
        triangles=len(all_triangles),
        max_error_m=settings.max_error_m,
        error_m=tin.error_m,
        skirt_depth_m=skirt_depth_m,
        texture_px=(texture.pixels.shape[2], texture.pixels.shape[1]),
        imagery=ImageryRecord(
            source=imagery.source_info,
            resolution_m=imagery.resolution_m,
            capture_date=imagery.capture_date,
            zoom=node.z + LEAF_ZOOM_DEPTH,
        ),
        dsm=surfaces.dsm.name,
        dtm=surfaces.dtm.name,
    )
    return Node(
        glb_bytes(all_vertices, all_uv, all_triangles, texture),
        _ground_geotiff(grid.ground_odn_heights, bounds),
        record,
    )


@dataclass(frozen=True)
class _SampledGrid:
    """Heights and positions at the nodes of a tile's Web Mercator grid, row 0 the north row.

    `odn_heights` and `ecef` are the DSM; `ground_odn_heights` is the DTM at the same nodes.
    """

    odn_heights: np.ndarray
    ground_odn_heights: np.ndarray
    ecef: np.ndarray
    origin_ecef: np.ndarray
    origin_lon: float
    origin_lat: float
    origin_height_m: float
    geoid_separation_m: float


def _sample_grid(
    bounds: mercantile.Bbox, surfaces: SurfacePaths, grid_spacing_m: float
) -> _SampledGrid:
    centre_lat = mercantile.lnglat(
        (bounds.left + bounds.right) / 2, (bounds.top + bounds.bottom) / 2
    ).lat
    ground_width_m = (bounds.right - bounds.left) * math.cos(math.radians(centre_lat))
    nodes = math.ceil(ground_width_m / grid_spacing_m) + 1
    x, y = np.meshgrid(
        np.linspace(bounds.left, bounds.right, nodes), np.linspace(bounds.top, bounds.bottom, nodes)
    )
    lon, lat = Transformer.from_crs(WEB_MERCATOR, WGS84, always_xy=True).transform(x, y)
    easting, northing = wgs84_to_bng().transform(lon, lat)
    odn_heights = _sample_heights(surfaces.dsm, easting, northing, NEAREST)
    ground_odn_heights = _sample_heights(surfaces.dtm, easting, northing, BILINEAR)
    lon, lat, height = bng_odn_to_wgs84().transform(easting, northing, odn_heights)
    ecef = np.stack(geodetic_to_ecef().transform(lon, lat, height), axis=-1)
    origin_lon, origin_lat = (
        float(v)
        for v in mercantile.lnglat(
            (bounds.left + bounds.right) / 2, (bounds.top + bounds.bottom) / 2
        )
    )
    origin_height = float(height.min())
    origin_ecef = np.array(geodetic_to_ecef().transform(origin_lon, origin_lat, origin_height))
    return _SampledGrid(
        odn_heights=odn_heights,
        ground_odn_heights=ground_odn_heights,
        ecef=ecef,
        origin_ecef=origin_ecef,
        origin_lon=origin_lon,
        origin_lat=origin_lat,
        origin_height_m=origin_height,
        geoid_separation_m=float((height - odn_heights).mean()),
    )


def _triple(values: np.ndarray) -> tuple[float, float, float]:
    x, y, z = (float(v) for v in values)
    return x, y, z


def _sample_heights(
    path: Path, easting: np.ndarray, northing: np.ndarray, order: int
) -> np.ndarray:
    with rasterio.open(path) as src:
        transform = src.transform
        heights = src.read(1, masked=True)
        bounds = src.bounds
    if np.ma.count_masked(heights):
        msg = f"{path.name} has nodata pixels"
        raise ValueError(msg)
    if (
        easting.min() < bounds.left
        or easting.max() > bounds.right
        or northing.min() < bounds.bottom
        or northing.max() > bounds.top
    ):
        msg = (
            f"{path.name} {tuple(bounds)} does not cover the tile grid "
            f"({easting.min()}, {northing.min()}, {easting.max()}, {northing.max()})"
        )
        raise ValueError(msg)
    columns = (easting - transform.c) / transform.a - PIXEL_CENTRE_OFFSET
    rows = (northing - transform.f) / transform.e - PIXEL_CENTRE_OFFSET
    return map_coordinates(heights.filled(), [rows, columns], order=order, mode="nearest")


def _ground_geotiff(heights: np.ndarray, bounds: mercantile.Bbox) -> bytes:
    """Return `heights` (grid nodes on the tile's edges, row 0 north) as a Web Mercator GeoTIFF."""
    rows, cols = heights.shape
    step_x = (bounds.right - bounds.left) / (cols - 1)
    step_y = (bounds.top - bounds.bottom) / (rows - 1)
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            width=cols,
            height=rows,
            count=1,
            dtype="float32",
            crs=WEB_MERCATOR,
            transform=from_origin(
                bounds.left - step_x / 2, bounds.top + step_y / 2, step_x, step_y
            ),
            compress="deflate",
        ) as dst:
            dst.write(heights.astype(np.float32), 1)
        return bytes(memory.read())


def _require_texture_matches(texture: Raster, bounds: mercantile.Bbox) -> None:
    rows, cols = texture.pixels.shape[1:]
    t = texture.transform
    texture_box = (t.c, t.f + rows * t.e, t.c + cols * t.a, t.f)
    if texture.crs != WEB_MERCATOR or not np.allclose(
        texture_box, tuple(bounds), rtol=0, atol=EDGE_TOLERANCE_M
    ):
        msg = f"texture {texture.crs} {texture_box} is not the tile's {tuple(bounds)}"
        raise ValueError(msg)
