import numpy as np
import pytest
from pyproj import Transformer

from satmesh_core import (
    EnuFrame,
    GridMissingError,
    bng_odn_to_wgs84,
    geodetic_to_ecef,
    require_best_transformer,
)

UPPER_AIRE_LON, UPPER_AIRE_LAT = -2.0015, 53.9236
UPPER_AIRE_BNG = (400000.0, 447500.0)
# geoid height N = h - H at Upper Aire, measured with the OSGM15 grid (f5-tiling-research.md)
UPPER_AIRE_GEOID_M = 50.79
GEOID_TOLERANCE_M = 0.05  # research quotes the measurement to 0.01 m
ECEF_TOLERANCE_M = 1e-6  # float64 at 6.4e6 m magnitudes resolves about 1e-9 m


def ecef(lon: float, lat: float, height: float) -> np.ndarray:
    return np.array(
        Transformer.from_crs("EPSG:4979", "EPSG:4978", always_xy=True).transform(lon, lat, height)
    )


def frame_at(lon: float, lat: float, height: float) -> EnuFrame:
    return EnuFrame.at(ecef(lon, lat, height), lon, lat)


def test_up_is_the_ellipsoid_normal() -> None:
    frame = frame_at(UPPER_AIRE_LON, UPPER_AIRE_LAT, 100.0)
    above = ecef(UPPER_AIRE_LON, UPPER_AIRE_LAT, 350.0)
    np.testing.assert_allclose(frame.to_enu(above[None])[0], [0, 0, 250], atol=ECEF_TOLERANCE_M)


@pytest.mark.parametrize(
    ("lon", "lat"), [(UPPER_AIRE_LON, UPPER_AIRE_LAT), (-179.9, -45.0), (12.3, 0.5), (140.0, 70.0)]
)
def test_enu_matches_proj_topocentric(lon: float, lat: float) -> None:
    height = 120.0
    frame = frame_at(lon, lat, height)
    topocentric = Transformer.from_pipeline(
        f"+proj=pipeline +step +proj=cart +ellps=WGS84 "
        f"+step +proj=topocentric +ellps=WGS84 +lon_0={lon} +lat_0={lat} +h_0={height}"
    )
    points = np.array(
        [
            [lon + 0.001, lat, height + 3.0],
            [lon, lat - 0.002, height - 20.0],
            [lon - 0.003, lat + 0.001, height + 55.0],
        ]
    )
    expected = np.array([topocentric.transform(*point) for point in points])
    np.testing.assert_allclose(
        frame.to_enu(np.array([ecef(*point) for point in points])), expected, atol=1e-5
    )


def test_enu_to_ecef_matrix_inverts_to_enu() -> None:
    frame = frame_at(UPPER_AIRE_LON, UPPER_AIRE_LAT, 100.0)
    enu = np.array([[12.0, -340.5, 7.25], [0.0, 0.0, 0.0]])
    homogeneous = np.column_stack([enu, np.ones(len(enu))])
    back = (frame.enu_to_ecef_matrix() @ homogeneous.T).T[:, :3]
    np.testing.assert_allclose(frame.to_enu(back), enu, atol=ECEF_TOLERANCE_M)


def test_missing_grids_raise_instead_of_falling_back() -> None:
    # NAD27 to NAD83 needs US NADCON grids, which are not installed alongside the UK ones
    with pytest.raises(GridMissingError, match="grids"):
        require_best_transformer("EPSG:4267", "EPSG:4269")


def test_bng_odn_applies_the_osgm15_geoid_separation() -> None:
    odn_height = 100.0
    lon, lat, height = bng_odn_to_wgs84().transform(*UPPER_AIRE_BNG, odn_height)
    assert height - odn_height == pytest.approx(UPPER_AIRE_GEOID_M, abs=GEOID_TOLERANCE_M)
    assert (lon, lat) == pytest.approx((UPPER_AIRE_LON, UPPER_AIRE_LAT), abs=5e-5)


def test_geodetic_to_ecef_puts_the_equator_on_the_semi_major_axis() -> None:
    # WGS84 semi-major axis a = 6378137 m (NIMA TR8350.2)
    x, y, z = geodetic_to_ecef().transform(0.0, 0.0, 0.0)
    assert (x, y, z) == pytest.approx((6378137.0, 0.0, 0.0), abs=1e-6)


def test_at_ecef_takes_longitude_and_latitude_from_the_point() -> None:
    point = ecef(UPPER_AIRE_LON, UPPER_AIRE_LAT, 75.0)
    from_point = EnuFrame.at_ecef(point)
    explicit = EnuFrame.at(point, UPPER_AIRE_LON, UPPER_AIRE_LAT)
    np.testing.assert_allclose(from_point.east_north_up, explicit.east_north_up, atol=1e-12)
