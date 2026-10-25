import math
from pathlib import Path
from typing import TypedDict

import numpy as np
import pygltflib
import pytest
import rasterio
from matplotlib.tri import LinearTriInterpolator, Triangulation
from pydantic import TypeAdapter
from rasterio.transform import from_bounds, from_origin

from satmesh_core import BRITISH_NATIONAL_GRID, Aoi
from satmesh_data import Raster
from satmesh_mesh import MAX_TEXTURE_PX, Tin, drape_texture, to_glb, triangulate

WEB_MERCATOR = "EPSG:3857"
BOX = Aoi(crs=BRITISH_NATIONAL_GRID, west=399900, south=447400, east=399960, north=447440)
COLS, ROWS = int(BOX.east - BOX.west), int(BOX.north - BOX.south)
# pixel centres of the 1 m DTM grid, row 0 at the north edge
EASTING = BOX.west + 0.5 + np.arange(COLS)[None, :]
NORTHING = BOX.north - 0.5 - np.arange(ROWS)[:, None]
GLTF_FLOAT_TOLERANCE_M = (
    1e-4  # float32 positions within about 60 m of the origin: about 4e-6 m resolution
)


def plane(e: np.ndarray, n: np.ndarray) -> np.ndarray:
    return 100.0 + 0.5 * (e - BOX.west) - 0.25 * (n - BOX.south)


def hill(e: np.ndarray, n: np.ndarray) -> np.ndarray:
    """Gaussian peak of 20 m in the north-east quadrant."""
    peak_e, peak_n = BOX.west + 0.75 * COLS, BOX.south + 0.75 * ROWS
    return 50.0 + 20.0 * np.exp(-((e - peak_e) ** 2 + (n - peak_n) ** 2) / (2 * 6.0**2))


def write_dtm(path: Path, heights: np.ndarray) -> Path:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=COLS,
        height=ROWS,
        count=1,
        dtype="float32",
        crs=BRITISH_NATIONAL_GRID,
        transform=from_origin(BOX.west, BOX.north, 1.0, 1.0),
        nodata=-9999.0,
    ) as dst:
        dst.write(heights.astype(np.float32), 1)
    return path


def bng_texture(cols: int = 120, rows: int = 80) -> Raster:
    pixels = np.zeros((3, rows, cols), np.uint8)
    pixels[0] = np.linspace(0, 255, cols, dtype=np.uint8)[None, :]
    return Raster(
        pixels,
        from_bounds(BOX.west, BOX.south, BOX.east, BOX.north, cols, rows),
        BRITISH_NATIONAL_GRID,
    )


def mercator_source(pixel_m: float, margin_m: float) -> Raster:
    """Web Mercator raster over the box plus margin: west half red, east half blue."""
    west, south, east, north = BOX.grown(margin_m).bounds_in(WEB_MERCATOR)
    cols, rows = math.ceil((east - west) / pixel_m), math.ceil((north - south) / pixel_m)
    pixels = np.zeros((3, rows, cols), np.uint8)
    pixels[0, :, : cols // 2] = 255
    pixels[2, :, cols // 2 :] = 255
    return Raster(pixels, from_origin(west, north, pixel_m, pixel_m), WEB_MERCATOR)


def read_glb(path: Path) -> tuple[pygltflib.GLTF2, np.ndarray, np.ndarray, np.ndarray]:
    gltf = pygltflib.GLTF2().load(str(path))
    blob = gltf.binary_blob()
    primitive = gltf.meshes[0].primitives[0]

    def accessor(index: int, dtype: type, width: int) -> np.ndarray:
        a = gltf.accessors[index]
        view = gltf.bufferViews[a.bufferView]
        start = (view.byteOffset or 0) + (a.byteOffset or 0)
        return np.frombuffer(blob, dtype, a.count * width, start).reshape(a.count, width)

    positions = accessor(primitive.attributes.POSITION, np.float32, 3).astype(np.float64)
    uv = accessor(primitive.attributes.TEXCOORD_0, np.float32, 2).astype(np.float64)
    index_dtype = {pygltflib.UNSIGNED_INT: np.uint32, pygltflib.UNSIGNED_SHORT: np.uint16}
    indices = accessor(
        primitive.indices, index_dtype[gltf.accessors[primitive.indices].componentType], 1
    )
    return gltf, positions, uv, indices.reshape(-1, 3)


class SatmeshExtras(TypedDict):
    crs: str
    origin: tuple[float, float, float]
    axes: str
    point_scale: float


def satmesh_extras(gltf: pygltflib.GLTF2) -> SatmeshExtras:
    extras = gltf.scenes[0].extras
    assert isinstance(extras, dict)
    return TypeAdapter(SatmeshExtras).validate_python(extras["satmesh"])


def tin_error_m(tin: Tin, heights: np.ndarray) -> float:
    """Worst |TIN - DTM| over every pixel centre, interpolating on the TIN's own triangles."""
    v = tin.vertices
    surface = LinearTriInterpolator(Triangulation(v[:, 0], v[:, 1], tin.triangles), v[:, 2])
    mesh = surface(
        np.broadcast_to(EASTING, heights.shape), np.broadcast_to(NORTHING, heights.shape)
    )
    assert not np.ma.count_masked(mesh)
    return float(np.abs(mesh - heights).max())


def test_plane_vertices_sit_on_the_plane_at_their_coordinates(tmp_path: Path) -> None:
    tin = triangulate(write_dtm(tmp_path / "plane.tif", plane(EASTING, NORTHING)))
    e, n, h = tin.vertices.T
    # float32 DTM storage of heights near 100 m: about 1e-5 m
    assert h == pytest.approx(plane(e, n), abs=1e-4)
    assert tin.box == BOX


@pytest.mark.parametrize("max_error_m", [0.05, 0.1, 0.5])
def test_tin_stays_within_max_error_of_every_pixel(tmp_path: Path, max_error_m: float) -> None:
    heights = hill(EASTING, NORTHING).astype(np.float32).astype(np.float64)
    tin = triangulate(write_dtm(tmp_path / "hill.tif", heights), max_error_m)
    assert tin_error_m(tin, heights) <= max_error_m + 1e-9


def test_dtm_gaps_are_rejected(tmp_path: Path) -> None:
    heights = plane(EASTING, NORTHING)
    heights[3, 4] = -9999.0
    with pytest.raises(ValueError, match="1 nodata"):
        triangulate(write_dtm(tmp_path / "gap.tif", heights))


@pytest.fixture
def hill_glb(tmp_path: Path) -> tuple[Tin, Path]:
    tin = triangulate(write_dtm(tmp_path / "hill.tif", hill(EASTING, NORTHING)))
    path = tmp_path / "hill.glb"
    to_glb(tin, bng_texture(), path)
    return tin, path


def test_glb_is_north_up_and_y_up(hill_glb: tuple[Tin, Path]) -> None:
    _, path = hill_glb
    _, positions, _, _ = read_glb(path)
    peak = positions[positions[:, 1].argmax()]
    assert peak[0] > 0, "peak is in the east half, so x > 0"
    assert peak[2] < 0, "peak is in the north half, so z (south) < 0"


def test_uvs_follow_gltf_top_left_origin(hill_glb: tuple[Tin, Path]) -> None:
    _, path = hill_glb
    gltf, positions, uv, _ = read_glb(path)
    east0, north0, _ = satmesh_extras(gltf)["origin"]
    easting, northing = positions[:, 0] + east0, -positions[:, 2] + north0
    expected_u = (easting - BOX.west) / (BOX.east - BOX.west)
    expected_v = (BOX.north - northing) / (BOX.north - BOX.south)
    assert uv[:, 0] == pytest.approx(expected_u, abs=1e-5)
    assert uv[:, 1] == pytest.approx(expected_v, abs=1e-5)


def test_every_face_points_up(hill_glb: tuple[Tin, Path]) -> None:
    _, path = hill_glb
    _, positions, _, faces = read_glb(path)
    a, b, c = (positions[faces[:, i]] for i in range(3))
    assert (np.cross(b - a, c - a)[:, 1] > 0).all()


def test_material_is_matte_jpeg(hill_glb: tuple[Tin, Path]) -> None:
    _, path = hill_glb
    gltf = pygltflib.GLTF2().load(str(path))
    pbr = gltf.materials[0].pbrMetallicRoughness
    assert (pbr.metallicFactor, pbr.roughnessFactor, pbr.baseColorFactor) == (
        0.0,
        1.0,
        [1.0, 1.0, 1.0, 1.0],
    )
    assert gltf.images[0].mimeType == "image/jpeg"


def test_extras_georeference_puts_vertices_back_on_the_map(hill_glb: tuple[Tin, Path]) -> None:
    tin, path = hill_glb
    gltf, positions, _, _ = read_glb(path)
    extras = satmesh_extras(gltf)
    assert extras["crs"] == BRITISH_NATIONAL_GRID
    east0, north0, height0 = extras["origin"]
    on_map = np.column_stack(
        [positions[:, 0] + east0, -positions[:, 2] + north0, positions[:, 1] + height0]
    )
    assert on_map == pytest.approx(tin.vertices, abs=GLTF_FLOAT_TOLERANCE_M)
    # BNG point scale near its central meridian (2 W) is its 0.9996012717 central scale factor
    assert extras["point_scale"] == pytest.approx(0.9996012717, abs=1e-6)


def test_texture_box_must_match_the_tin(hill_glb: tuple[Tin, Path], tmp_path: Path) -> None:
    tin, _ = hill_glb
    texture = bng_texture()
    shifted = Raster(
        texture.pixels,
        from_bounds(BOX.west + 1, BOX.south, BOX.east + 1, BOX.north, 120, 80),
        texture.crs,
    )
    with pytest.raises(ValueError, match="does not match"):
        to_glb(tin, shifted, tmp_path / "bad.glb")


def test_drape_keeps_the_source_pixel_and_orientation() -> None:
    mercator_pixel_m = 0.3
    texture = drape_texture(mercator_source(mercator_pixel_m, margin_m=5), BOX)
    lat = 53.92
    # Web Mercator ground pixel is pixel * cos(lat); 1% covers BNG scale (0.04%) and the spherical
    # Mercator scale's ellipsoid error (under 0.7%)
    assert texture.transform.a == pytest.approx(
        mercator_pixel_m * math.cos(math.radians(lat)), rel=0.01
    )
    rows, cols = texture.pixels.shape[1:]
    assert texture.transform.c == BOX.west
    assert texture.transform.f == BOX.north
    assert texture.transform.c + cols * texture.transform.a == pytest.approx(BOX.east)
    assert texture.transform.f + rows * texture.transform.e == pytest.approx(BOX.south)
    assert tuple(texture.pixels[:, rows // 2, 2]) == (255, 0, 0), "west edge red"
    assert tuple(texture.pixels[:, rows // 2, -3]) == (0, 0, 255), "east edge blue"


def test_drape_coarsens_to_the_texture_cap() -> None:
    big = Aoi(crs=BRITISH_NATIONAL_GRID, west=399000, south=447000, east=401000, north=447010)
    west, south, east, north = big.grown(5).bounds_in(WEB_MERCATOR)
    pixel_m = 0.3
    cols, rows = math.ceil((east - west) / pixel_m), math.ceil((north - south) / pixel_m)
    source = Raster(
        np.zeros((3, rows, cols), np.uint8),
        from_origin(west, north, pixel_m, pixel_m),
        WEB_MERCATOR,
    )
    texture = drape_texture(source, big)
    assert texture.pixels.shape[2] == MAX_TEXTURE_PX
    assert texture.transform.a == pytest.approx((big.east - big.west) / MAX_TEXTURE_PX)


def test_drape_needs_the_source_to_cover_the_box() -> None:
    source = mercator_source(0.3, margin_m=5)
    beyond = Aoi(
        crs=BRITISH_NATIONAL_GRID,
        west=BOX.west - 50,
        south=BOX.south,
        east=BOX.east,
        north=BOX.north,
    )
    with pytest.raises(ValueError, match="does not cover"):
        drape_texture(source, beyond)
