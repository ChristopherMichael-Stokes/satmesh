import numpy as np
import pygltflib
import pytest
from matplotlib.tri import LinearTriInterpolator, Triangulation
from rasterio.transform import from_origin

from satmesh_data import Raster
from satmesh_mesh import add_skirts, glb_bytes, triangulate_heights, upward

SIZE = 61
MAX_ERROR_M = 0.1
SKIRT_DEPTH_M = 0.4
PLANE_TILT = (0.5, -0.25)
HILL_PEAK_M = 20.0
HILL_SIGMA_PX = 6.0


def plane() -> np.ndarray:
    cols, rows = np.meshgrid(np.arange(SIZE), np.arange(SIZE))
    return 100.0 + PLANE_TILT[0] * cols + PLANE_TILT[1] * rows


def hill() -> np.ndarray:
    cols, rows = np.meshgrid(np.arange(SIZE), np.arange(SIZE))
    return 50.0 + HILL_PEAK_M * np.exp(
        -((cols - 45) ** 2 + (rows - 15) ** 2) / (2 * HILL_SIGMA_PX**2)
    )


def local_mesh(heights: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """glTF-frame vertices (x east = column, y up, z south = row), UV and upward triangles."""
    tin = triangulate_heights(heights, MAX_ERROR_M)
    vertices = np.column_stack([tin.columns, tin.heights, tin.rows]).astype(np.float64)
    uv = np.column_stack([tin.columns / (SIZE - 1), 1 - tin.rows / (SIZE - 1)])
    return vertices, uv, upward(vertices, tin.triangles)


def test_plane_needs_only_two_triangles() -> None:
    tin = triangulate_heights(plane(), MAX_ERROR_M)
    assert len(tin.triangles) == 2
    assert tin.error_m <= MAX_ERROR_M


def test_every_grid_node_is_within_max_error_of_the_tin() -> None:
    heights = hill()
    tin = triangulate_heights(heights, MAX_ERROR_M)
    interpolator = LinearTriInterpolator(
        Triangulation(tin.columns, tin.rows, tin.triangles), tin.heights
    )
    cols, rows = np.meshgrid(np.arange(SIZE), np.arange(SIZE))
    gap = np.abs(interpolator(cols, rows) - heights)
    assert gap.max() <= MAX_ERROR_M + 1e-9


def test_row_zero_is_the_top_row() -> None:
    heights = np.zeros((SIZE, SIZE))
    heights[0, SIZE - 1] = 30.0
    tin = triangulate_heights(heights, MAX_ERROR_M)
    peak = tin.heights.argmax()
    assert (tin.columns[peak], tin.rows[peak]) == (SIZE - 1, 0)


def test_non_finite_heights_raise() -> None:
    heights = plane()
    heights[3, 3] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        triangulate_heights(heights)


def test_terrain_faces_point_up() -> None:
    vertices, _, triangles = local_mesh(hill())
    a, b, c = (vertices[triangles[:, i]] for i in range(3))
    assert (np.cross(b - a, c - a)[:, 1] > 0).all()


def test_skirt_walls_hang_down_from_the_boundary_and_face_outward() -> None:
    vertices, uv, triangles = local_mesh(hill())
    n_terrain = len(triangles)
    out_vertices, out_uv, out_triangles = add_skirts(vertices, uv, triangles, SKIRT_DEPTH_M)
    walls = out_triangles[n_terrain:]
    a, b, c = (out_vertices[walls[:, i]] for i in range(3))
    normals = np.cross(b - a, c - a)
    centre = np.array([(SIZE - 1) / 2, 0.0, (SIZE - 1) / 2])
    outward = (a + b + c) / 3 - centre
    assert np.allclose(normals[:, 1], 0.0)
    assert (np.einsum("ij,ij->i", normals, outward) > 0).all()
    added = out_vertices[len(vertices) :]
    assert len(out_uv) == len(out_vertices)
    # each added vertex is its boundary vertex lowered by exactly the depth
    top = np.array([vertices[(vertices[:, [0, 2]] == p[[0, 2]]).all(axis=1)][0] for p in added])
    np.testing.assert_allclose(top[:, 1] - added[:, 1], SKIRT_DEPTH_M)


def test_skirts_close_a_square_tile_with_four_sides() -> None:
    vertices, uv, triangles = local_mesh(plane())
    _, _, out = add_skirts(vertices, uv, triangles, SKIRT_DEPTH_M)
    assert len(out) - len(triangles) == 4 * 2


def test_glb_reads_back_with_texture_and_uv_contract() -> None:
    vertices, uv, triangles = local_mesh(hill())
    cols, rows = 8, 4
    pixels = np.zeros((3, rows, cols), np.uint8)
    texture = Raster(pixels, from_origin(0, rows, 1, 1), "EPSG:3857")
    gltf = pygltflib.GLTF2.load_from_bytes(glb_bytes(vertices, uv, triangles, texture))
    primitive = gltf.meshes[0].primitives[0]
    blob = gltf.binary_blob()
    accessor = gltf.accessors[primitive.attributes.TEXCOORD_0]
    view = gltf.bufferViews[accessor.bufferView]
    raw = np.frombuffer(blob, np.float32, accessor.count * 2, view.byteOffset).reshape(-1, 2)
    # glTF's texture origin is top-left, so v = 1 - (v up from the bottom)
    np.testing.assert_allclose(raw[:, 0], uv[:, 0], atol=1e-6)
    np.testing.assert_allclose(raw[:, 1], 1 - uv[:, 1], atol=1e-6)
    material = gltf.materials[0].pbrMetallicRoughness
    assert material.metallicFactor == 0.0
    assert gltf.images[0].mimeType == "image/jpeg"
