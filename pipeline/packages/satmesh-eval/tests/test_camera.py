import math

import cv2
import numpy as np
import pytest
from pyproj import Geod

from satmesh_core import EnuFrame, ecef_to_geodetic, geodetic_to_ecef
from satmesh_eval.camera import CameraPose, Intrinsics, camera_centre_and_rotation, pixel_rays

LATITUDE_DEG, LONGITUDE_DEG, ORIGIN_HEIGHT_M = 53.72, -1.27, 40.0
WGS84_EQUATORIAL_RADIUS_M = 6_378_137.0
EAST_OFFSET_M = 100.0
# the tangent plane leaves the ellipsoid by d^2 / 2R at distance d
CURVATURE_DROP_M = EAST_OFFSET_M**2 / (2 * WGS84_EQUATORIAL_RADIUS_M)
MILLIMETRE = 1e-3


def area_frame_at_origin() -> EnuFrame:
    ecef = np.array(geodetic_to_ecef().transform(LONGITUDE_DEG, LATITUDE_DEG, ORIGIN_HEIGHT_M))
    return EnuFrame.at(ecef, LONGITUDE_DEG, LATITUDE_DEG)


def pose(heading: float = 0.0, pitch: float = 0.0, roll: float = 0.0) -> CameraPose:
    return CameraPose(LATITUDE_DEG, LONGITUDE_DEG, ORIGIN_HEIGHT_M, heading, pitch, roll)


def test_camera_at_frame_origin_looks_north_along_y() -> None:
    centre, rotation = camera_centre_and_rotation(pose(), area_frame_at_origin())

    assert centre == pytest.approx([0.0, 0.0, 0.0], abs=MILLIMETRE)
    assert rotation[:, 2] == pytest.approx([0.0, 1.0, 0.0], abs=1e-9)  # forward
    assert rotation[:, 0] == pytest.approx([1.0, 0.0, 0.0], abs=1e-9)  # right = east
    assert rotation[:, 1] == pytest.approx([0.0, 0.0, -1.0], abs=1e-9)  # down


def test_camera_100_m_east_lands_100_m_east_in_the_area_frame() -> None:
    longitude, latitude, _ = Geod(ellps="WGS84").fwd(
        LONGITUDE_DEG, LATITUDE_DEG, 90.0, EAST_OFFSET_M
    )
    east_pose = CameraPose(latitude, longitude, ORIGIN_HEIGHT_M, 0.0, 0.0, 0.0)

    centre, _ = camera_centre_and_rotation(east_pose, area_frame_at_origin())

    # geodesic distance is along the ellipsoid; the tangent plane drops away by d^2 / 2R
    assert centre[0] == pytest.approx(EAST_OFFSET_M, abs=MILLIMETRE * 10)
    assert centre[1] == pytest.approx(0.0, abs=MILLIMETRE * 10)
    assert centre[2] == pytest.approx(-CURVATURE_DROP_M, abs=0.05 * CURVATURE_DROP_M)


def test_rotation_is_orthonormal_and_right_handed_for_any_attitude() -> None:
    _, rotation = camera_centre_and_rotation(pose(123.0, -37.0, 21.0), area_frame_at_origin())

    assert rotation.T @ rotation == pytest.approx(np.eye(3), abs=1e-12)
    assert np.linalg.det(rotation) == pytest.approx(1.0)


def test_heading_east_pitch_up_forward_vector() -> None:
    _, rotation = camera_centre_and_rotation(pose(90.0, 30.0), area_frame_at_origin())

    expected = [math.cos(math.radians(30.0)), 0.0, math.sin(math.radians(30.0))]
    assert rotation[:, 2] == pytest.approx(expected, abs=1e-9)


def test_positive_roll_tips_the_right_of_the_image_down() -> None:
    _, rotation = camera_centre_and_rotation(pose(roll=30.0), area_frame_at_origin())

    assert rotation[:, 0] == pytest.approx(
        [math.cos(math.radians(30.0)), 0.0, -math.sin(math.radians(30.0))], abs=1e-9
    )


def test_pixel_ray_through_offset_pixel_matches_pinhole_geometry() -> None:
    intrinsics = Intrinsics(65, 49, 50.0, 50.0, 32.5, 24.5, ())
    rays = pixel_rays(intrinsics, np.eye(3))

    # pixel (col 42, row 29) centre is 10 px right of and 5 px below the principal point
    expected = np.array([10.0 / 50.0, 5.0 / 50.0, 1.0])
    assert rays.shape == (49, 65, 3)
    assert rays[29, 42] == pytest.approx(expected / np.linalg.norm(expected), abs=1e-12)


def test_distorted_ray_projects_back_to_its_pixel() -> None:
    intrinsics = Intrinsics(640, 480, 500.0, 480.0, 321.0, 238.0, (-0.25, 0.08, -0.01))
    rays = pixel_rays(intrinsics, np.eye(3))
    columns, rows = np.meshgrid(np.arange(0, 640, 37), np.arange(0, 480, 29))
    sampled = rays[rows, columns].reshape(-1, 3)

    projected, _ = cv2.projectPoints(
        sampled * 7.0,
        np.zeros(3),
        np.zeros(3),
        intrinsics.matrix(),
        np.array([-0.25, 0.08, 0.0, 0.0, -0.01]),
    )

    expected = np.column_stack([columns.ravel() + 0.5, rows.ravel() + 0.5])
    assert projected.reshape(-1, 2) == pytest.approx(expected, abs=0.01)


def test_area_frame_origin_geodetic_roundtrip() -> None:
    frame = area_frame_at_origin()

    longitude, latitude, height = ecef_to_geodetic().transform(*frame.origin_ecef)

    assert (longitude, latitude, height) == pytest.approx(
        (LONGITUDE_DEG, LATITUDE_DEG, ORIGIN_HEIGHT_M), abs=1e-7
    )
