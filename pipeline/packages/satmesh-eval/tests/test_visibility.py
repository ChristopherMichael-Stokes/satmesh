import numpy as np
import pytest
from rasterio.transform import from_origin

from satmesh_eval.visibility import (
    Camera,
    depth_agreement,
    raised_point_visibility,
    random_cameras,
    range_image,
    raster_mesh,
    sample_raised_points,
    tolerance,
)

PIXEL_M = 1.0
SIDE = 120
TRANSFORM = from_origin(1000.0, 2000.0 + SIDE, PIXEL_M, PIXEL_M)  # west 1000, south 2000
THRESHOLD_M = 2.0
RANGE_LIMIT_M = 200.0


def scene(blocks: list[tuple[slice, slice, float]]) -> tuple[np.ndarray, np.ndarray]:
    """A flat ground at 100 m ODN, and the same ground with raised blocks (rows, cols, height)."""
    ground = np.full((SIDE, SIDE), 100.0)
    surface = ground.copy()
    for rows, cols, height in blocks:
        surface[rows, cols] += height
    return surface, ground


def camera_at(
    easting: float, northing: float, height: float, heading: float, pitch: float
) -> Camera:
    return Camera(easting, northing, height, heading, pitch, 90.0, 64, 48)


def test_look_down_range_is_height_over_sine_of_depression() -> None:
    surface, _ = scene([])
    mesh = raster_mesh(surface, TRANSFORM)
    camera = camera_at(1060.0, 2060.0, 120.0, 0.0, -45.0)
    image = range_image(mesh, camera, RANGE_LIMIT_M)
    # the pixel centre rows and columns straddle the optical axis; take the mean of the middle four
    centre = image[23:25, 31:33].mean()
    # 20 m above the ground along a 45 degree depression: 20 / sin(45 deg)
    assert centre == pytest.approx(20 / np.sin(np.radians(45)), rel=2e-3)


def test_heading_is_clockwise_from_north() -> None:
    surface, _ = scene([(slice(0, SIDE), slice(90, 100), 30.0)])  # a wall of columns east of centre
    mesh = raster_mesh(surface, TRANSFORM)
    east = range_image(mesh, camera_at(1060.0, 2060.0, 105.0, 90.0, 0.0), RANGE_LIMIT_M)
    north = range_image(mesh, camera_at(1060.0, 2060.0, 105.0, 0.0, 0.0), RANGE_LIMIT_M)
    # facing east the wall face at easting 1090 is 30 m ahead; facing north it is not hit ahead
    assert east[24, 32] == pytest.approx(30.0, abs=1.0)
    assert np.isnan(north[24, 32])


def test_projection_matches_the_ray_through_the_same_pixel() -> None:
    camera = camera_at(1060.0, 2060.0, 105.0, 37.0, -10.0)
    rays = camera.pixel_rays()
    row, col = 10, 50
    point = camera.position + 80.0 * rays[row, col]
    projected_col, projected_row, inside = camera.project(point[None, :])
    assert inside[0]
    assert projected_col[0] == pytest.approx(col + 0.5)
    assert projected_row[0] == pytest.approx(row + 0.5)


def test_identical_meshes_agree_everywhere_and_a_missing_building_does_not() -> None:
    surface, ground = scene([(slice(50, 70), slice(60, 80), 12.0)])
    reference = raster_mesh(surface, TRANSFORM)
    camera = camera_at(1030.0, 2060.0, 101.7, 90.0, 0.0)  # on the ground, facing the building
    ref_image = range_image(reference, camera, RANGE_LIMIT_M)
    same = depth_agreement(ref_image, range_image(reference, camera, RANGE_LIMIT_M))
    assert same.recall == 1.0
    ground_only = depth_agreement(
        ref_image, range_image(raster_mesh(ground, TRANSFORM), camera, RANGE_LIMIT_M)
    )
    # the building fills part of the view, and the bare ground behind it lies far beyond the wall
    assert 0.0 < ground_only.recall < 0.95
    assert ground_only.test_only_pixels == 0


def test_tolerance_grows_with_range() -> None:
    assert tolerance(np.array([0.0, 100.0])).tolist() == pytest.approx([0.5, 1.5])


def test_raised_points_come_only_from_patches_above_threshold_and_minimum_area() -> None:
    surface, ground = scene(
        [(slice(10, 20), slice(10, 20), 6.0), (slice(40, 41), slice(40, 41), 6.0)]  # 100 m2, 1 m2
    )
    surface[15, 15] += 4.0
    raised = sample_raised_points(surface, ground, TRANSFORM, THRESHOLD_M)
    assert len(raised.points) == 100  # the 1 m2 patch is under the minimum area
    assert raised.height_above_ground_m.max() == pytest.approx(10.0)
    assert raised.points[:, 0].min() == 1010.5
    assert raised.points[:, 1].max() == 2000 + SIDE - 10.5


def test_a_ground_only_mesh_shows_no_raised_point_and_an_occluded_one_is_not_visible() -> None:
    surface, ground = scene(
        [
            (slice(50, 70), slice(60, 70), 12.0),  # front building, 12 m tall
            (slice(54, 66), slice(95, 105), 12.0),  # behind it, in its shadow from the camera
        ]
    )
    reference = raster_mesh(surface, TRANSFORM)
    raised = sample_raised_points(surface, ground, TRANSFORM, THRESHOLD_M)
    camera = camera_at(1030.0, 2060.0, 101.7, 90.0, 0.0)
    full = raised_point_visibility(reference, reference, [camera], raised, RANGE_LIMIT_M)
    # the camera sees the front wall (its edge ramp is 1 m wide) but not the roof interior at a
    # 17 degree elevation, and nothing of the building behind: some, not all, points are visible
    assert 0 < full.reference_visible < len(raised.points)
    assert full.recall == 1.0
    assert full.by_class["5 to 15 m"][0] == full.reference_visible
    bare = raised_point_visibility(
        reference, raster_mesh(ground, TRANSFORM), [camera], raised, RANGE_LIMIT_M
    )
    assert bare.reference_visible == full.reference_visible
    assert bare.recall == 0.0


def test_random_cameras_stay_inside_the_margin_and_fly_at_height() -> None:
    surface, ground = scene([(slice(30, 60), slice(30, 90), 8.0)])  # a building in the middle
    cameras = random_cameras(
        surface, ground, TRANSFORM, 20, above_ground_m=60.0, pitch_deg=-25.0, margin_m=30.0, seed=3
    )
    assert len(cameras) == 20
    assert all(1030 <= c.easting <= 1090 and 2030 <= c.northing <= 2090 for c in cameras)
    assert all(c.height == pytest.approx(160.0) for c in cameras)
    # none stands in the building: rows 30 to 59 are northing 2090 down to 2061, columns 30 to 89
    assert not any(2061 <= c.northing <= 2090 and 1030 <= c.easting <= 1090 for c in cameras)
    with pytest.raises(ValueError, match="no room"):
        random_cameras(
            surface, ground, TRANSFORM, 1, above_ground_m=1.7, pitch_deg=0, margin_m=70.0
        )
    covered = np.full_like(ground, 10.0) + ground
    with pytest.raises(ValueError, match="open-ground"):
        random_cameras(covered, ground, TRANSFORM, 1, above_ground_m=1.7, pitch_deg=0, margin_m=5.0)
