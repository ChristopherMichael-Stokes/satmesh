import math

import cv2
import numpy as np
import pytest
from trimesh.creation import box

from satmesh_core import EnuFrame, geodetic_to_ecef
from satmesh_eval.camera import CameraPose, Intrinsics, camera_centre_and_rotation, pixel_rays
from satmesh_eval.perspective import AreaScene, GroundExtent, SceneLeaf, flat_plane_scene, render

LATITUDE_DEG, LONGITUDE_DEG, ORIGIN_HEIGHT_M = 53.72, -1.27, 40.0
CAMERA_HEIGHT_M = 20.0
PLANE_HALF_EXTENT_M = 100.0
FOCAL_PX = 50.0
CENTRE_COL, CENTRE_ROW = 32, 24  # pixel whose centre is the principal point of a 65 x 49 image
INTRINSICS = Intrinsics(65, 49, FOCAL_PX, FOCAL_PX, CENTRE_COL + 0.5, CENTRE_ROW + 0.5, ())
TEXTURE_SIDE_PX = 1000
BYTE_MAX = 255.0
ONE_LEVEL = 1.0  # texture rounding (0.5) plus output rounding (0.5)
MAX_RANGE_M = 1000.0


def frame() -> EnuFrame:
    ecef = np.array(geodetic_to_ecef().transform(LONGITUDE_DEG, LATITUDE_DEG, ORIGIN_HEIGHT_M))
    return EnuFrame.at(ecef, LONGITUDE_DEG, LATITUDE_DEG)


def gradient_texture() -> np.ndarray:
    """Red grows with east, green with north: 0 at the west and south edges, 255 at the others.

    Sampled at texel centres; row 0 is north.
    """
    fraction = (np.arange(TEXTURE_SIDE_PX) + 0.5) / TEXTURE_SIDE_PX
    texture = np.zeros((TEXTURE_SIDE_PX, TEXTURE_SIDE_PX, 3), np.uint8)
    texture[..., 0] = np.rint(BYTE_MAX * fraction)[None, :]
    texture[..., 1] = np.rint(BYTE_MAX * fraction[::-1])[:, None]
    return texture


def ground_scene() -> AreaScene:
    half = PLANE_HALF_EXTENT_M
    return flat_plane_scene(
        frame(), 0.0, gradient_texture(), GroundExtent(-half, half, -half, half)
    )


def gradient_level(metres: float) -> float:
    """Expected red or green level at `metres` east or north of the plane centre."""
    return BYTE_MAX * (metres + PLANE_HALF_EXTENT_M) / (2 * PLANE_HALF_EXTENT_M)


def pose(heading: float = 0.0, pitch: float = -90.0, roll: float = 0.0) -> CameraPose:
    return CameraPose(
        LATITUDE_DEG, LONGITUDE_DEG, ORIGIN_HEIGHT_M + CAMERA_HEIGHT_M, heading, pitch, roll
    )


def test_nadir_centre_depth_is_camera_height() -> None:
    result = render(ground_scene(), INTRINSICS, pose(), MAX_RANGE_M)

    assert result.depth_m[CENTRE_ROW, CENTRE_COL] == pytest.approx(CAMERA_HEIGHT_M, abs=1e-3)
    assert result.z_depth_m[CENTRE_ROW, CENTRE_COL] == pytest.approx(CAMERA_HEIGHT_M, abs=1e-3)
    assert result.hit_mask.all()


def test_nadir_offset_pixel_depth_is_analytic_range() -> None:
    result = render(ground_scene(), INTRINSICS, pose(), MAX_RANGE_M)

    # 10 px right and 5 px down of centre: lateral tangent from the focal length
    tangent_squared = (10.0**2 + 5.0**2) / FOCAL_PX**2
    row, col = CENTRE_ROW + 5, CENTRE_COL + 10
    assert result.depth_m[row, col] == pytest.approx(
        CAMERA_HEIGHT_M * math.sqrt(1 + tangent_squared), abs=1e-3
    )
    assert result.z_depth_m[row, col] == pytest.approx(CAMERA_HEIGHT_M, abs=1e-3)


def test_texture_colour_equals_gradient_at_analytic_ground_point() -> None:
    result = render(ground_scene(), INTRINSICS, pose(), MAX_RANGE_M)

    # heading north, nadir: image right is east, image up is north
    for d_col, d_row in [(0, 0), (10, 5), (-20, 15), (25, -18)]:
        east = CAMERA_HEIGHT_M * d_col / FOCAL_PX
        north = -CAMERA_HEIGHT_M * d_row / FOCAL_PX
        red, green, _ = result.rgb[CENTRE_ROW + d_row, CENTRE_COL + d_col].astype(float)
        assert red == pytest.approx(gradient_level(east), abs=ONE_LEVEL)
        assert green == pytest.approx(gradient_level(north), abs=ONE_LEVEL)


@pytest.mark.parametrize(
    ("heading", "d_col", "d_row"),
    [(0.0, 15, 0), (90.0, 0, -15), (180.0, -15, 0), (270.0, 0, 15)],
)
def test_heading_places_a_point_6_m_east_of_the_camera(
    heading: float, d_col: int, d_row: int
) -> None:
    result = render(ground_scene(), INTRINSICS, pose(heading), MAX_RANGE_M)

    # nadir: image up is the heading direction, image right is 90 degrees clockwise from it.
    # 6 m on the ground is 6 * f / H = 15 px: east is right when facing north, up when facing
    # east, left when facing south and down when facing west.
    red, green, _ = result.rgb[CENTRE_ROW + d_row, CENTRE_COL + d_col].astype(float)
    assert red == pytest.approx(gradient_level(6.0), abs=ONE_LEVEL)
    assert green == pytest.approx(gradient_level(0.0), abs=ONE_LEVEL)


def test_roll_keeps_centre_hit_and_rotates_the_image() -> None:
    roll = 30.0
    result = render(ground_scene(), INTRINSICS, pose(roll=roll), MAX_RANGE_M)

    centre = result.rgb[CENTRE_ROW, CENTRE_COL].astype(float)
    assert result.depth_m[CENTRE_ROW, CENTRE_COL] == pytest.approx(CAMERA_HEIGHT_M, abs=1e-3)
    assert centre[:2] == pytest.approx([gradient_level(0.0)] * 2, abs=ONE_LEVEL)
    # clockwise roll tips the image's right edge down: 20 px right of centre looks at the ground
    # cos(roll) east and sin(roll) south of the camera, scaled by H / f
    reach = CAMERA_HEIGHT_M * 20 / FOCAL_PX
    red, green, _ = result.rgb[CENTRE_ROW, CENTRE_COL + 20].astype(float)
    assert red == pytest.approx(gradient_level(reach * math.cos(math.radians(roll))), abs=ONE_LEVEL)
    assert green == pytest.approx(
        gradient_level(-reach * math.sin(math.radians(roll))), abs=ONE_LEVEL
    )


def test_radial_distortion_ray_hits_ground_and_projects_back_to_its_pixel() -> None:
    distorted = Intrinsics(160, 120, 140.0, 140.0, 80.0, 60.0, (-0.3, 0.1))
    scene = ground_scene()
    camera = pose(heading=35.0, pitch=-50.0)

    result = render(scene, distorted, camera, MAX_RANGE_M)

    centre, rotation = camera_centre_and_rotation(camera, scene.frame)
    rays = pixel_rays(distorted, rotation)
    rows, cols = np.meshgrid(np.arange(0, 120, 7), np.arange(0, 160, 9), indexing="ij")
    hits = centre + result.depth_m[rows, cols][..., None] * rays[rows, cols]
    in_camera = (hits.reshape(-1, 3) - centre) @ rotation
    projected, _ = cv2.projectPoints(
        in_camera,
        np.zeros(3),
        np.zeros(3),
        distorted.matrix(),
        np.array([-0.3, 0.1, 0.0, 0.0, 0.0]),
    )
    assert result.hit_mask[rows, cols].all()
    assert hits[..., 2] == pytest.approx(0.0, abs=1e-3)
    expected = np.column_stack([cols.ravel() + 0.5, rows.ravel() + 0.5])
    assert projected.reshape(-1, 2) == pytest.approx(expected, abs=0.01)


def test_nearer_box_hides_the_ground_and_depth_is_the_nearer_surface() -> None:
    ground = ground_scene()
    side, top = 10.0, 5.0
    block = box(extents=(side, side, 2 * top))  # centred on the origin: spans z from -5 to 5
    solid_red = np.zeros((2, 2, 3), np.uint8)
    solid_red[..., 0] = 200
    leaf = SceneLeaf(block, np.zeros((len(block.vertices), 2)), solid_red)
    scene = AreaScene((*ground.leaves, leaf), ground.frame)

    result = render(scene, INTRINSICS, pose(), MAX_RANGE_M)

    assert result.depth_m[CENTRE_ROW, CENTRE_COL] == pytest.approx(CAMERA_HEIGHT_M - top, abs=1e-3)
    assert result.rgb[CENTRE_ROW, CENTRE_COL].tolist() == [200, 0, 0]
    # 30 px right: the ray reaches the box top height at 15 * 30 / 50 = 9 m, beyond its 5 m edge
    far_col = CENTRE_COL + 30
    expected = CAMERA_HEIGHT_M * math.sqrt(1 + (30.0 / FOCAL_PX) ** 2)
    assert result.rgb[CENTRE_ROW, far_col].tolist() != [200, 0, 0]
    assert result.depth_m[CENTRE_ROW, far_col] == pytest.approx(expected, abs=1e-3)


def test_hits_beyond_max_range_are_misses() -> None:
    result = render(ground_scene(), INTRINSICS, pose(), CAMERA_HEIGHT_M - 1.0)

    assert not result.hit_mask.any()
    assert np.isnan(result.depth_m).all()
    assert (result.rgb == 0).all()
