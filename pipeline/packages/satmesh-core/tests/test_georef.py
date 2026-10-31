import os
import subprocess
import sys

import numpy as np
import pytest
from pyproj import Transformer
from pyproj.transformer import TransformerGroup

from satmesh_core import (
    BNG_ODN,
    NAD83_2011_TO_WGS84_EPOCH,
    EnuFrame,
    GridMissingError,
    ellipsoidal_height_from,
    geodetic_to_ecef,
    require_best_transformer,
    wgs84_to,
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
    lon, lat, height = ellipsoidal_height_from(BNG_ODN).transform(*UPPER_AIRE_BNG, odn_height)
    assert height - odn_height == pytest.approx(UPPER_AIRE_GEOID_M, abs=GEOID_TOLERANCE_M)
    assert (lon, lat) == pytest.approx((UPPER_AIRE_LON, UPPER_AIRE_LAT), abs=5e-5)


def test_egm2008_height_at_sanaa_gains_the_geoid_separation() -> None:
    # EGM2008 geoid height at Sana'a, sampled from PROJ's us_nga_egm08_25 grid (region-research.md)
    sanaa_lon, sanaa_lat, geoid_height_m = 44.207, 15.355, -4.98
    lon, lat, height = ellipsoidal_height_from("EPSG:4326+3855").transform(
        sanaa_lon, sanaa_lat, 0.0
    )
    assert height == pytest.approx(geoid_height_m, abs=0.02)
    assert (lon, lat) == pytest.approx((sanaa_lon, sanaa_lat), abs=1e-9)


def test_geodetic_to_ecef_puts_the_equator_on_the_semi_major_axis() -> None:
    # WGS84 semi-major axis a = 6378137 m (NIMA TR8350.2)
    x, y, z = geodetic_to_ecef().transform(0.0, 0.0, 0.0)
    assert (x, y, z) == pytest.approx((6378137.0, 0.0, 0.0), abs=1e-6)


def test_at_ecef_takes_longitude_and_latitude_from_the_point() -> None:
    point = ecef(UPPER_AIRE_LON, UPPER_AIRE_LAT, 75.0)
    from_point = EnuFrame.at_ecef(point)
    explicit = EnuFrame.at(point, UPPER_AIRE_LON, UPPER_AIRE_LAT)
    np.testing.assert_allclose(from_point.east_north_up, explicit.east_north_up, atol=1e-12)


DENVER_LON, DENVER_LAT = -104.995, 39.748
DENVER_NAVD88_M = 1600.0
# GEOID18 height at Denver, from NGS's grid through PROJ (us-sources.md); the grid's stated
# accuracy is 0.015 m
DENVER_GEOID18_M = -17.10
NAD83_2011_UTM_13N = "EPSG:6342"


def test_geoid18_separation_at_denver() -> None:
    _, _, height = require_best_transformer("EPSG:6349", "EPSG:6319").transform(
        DENVER_LON, DENVER_LAT, DENVER_NAVD88_M
    )
    assert height - DENVER_NAVD88_M == pytest.approx(DENVER_GEOID18_M, abs=0.02)


def proj_route_to_wgs84_g2139(lon: float, lat: float, height: float) -> tuple[float, ...]:
    """PROJ's own best route from NAVD88 to WGS 84 (G2139), evaluated at the US epoch."""
    best = TransformerGroup("EPSG:6349", "EPSG:9754", always_xy=True).transformers[0]
    x, y, z, _ = best.transform(lon, lat, height, NAD83_2011_TO_WGS84_EPOCH)
    return float(x), float(y), float(z)


def test_navd88_chain_is_geoid18_then_the_dated_helmert() -> None:
    chain = ellipsoidal_height_from("EPSG:6349")
    assert "us_noaa_g2018u0.tif" in chain.definition
    assert "proj=helmert" in chain.definition
    assert f"proj=set v_4={NAD83_2011_TO_WGS84_EPOCH}" in chain.definition
    lon, lat, height = chain.transform(DENVER_LON, DENVER_LAT, DENVER_NAVD88_M)
    # 1e-9 degrees is 0.1 mm
    assert (lon, lat) == pytest.approx(
        proj_route_to_wgs84_g2139(DENVER_LON, DENVER_LAT, DENVER_NAVD88_M)[:2], abs=1e-9
    )
    assert height == pytest.approx(
        proj_route_to_wgs84_g2139(DENVER_LON, DENVER_LAT, DENVER_NAVD88_M)[2], abs=1e-4
    )


# without the GEOID03 grid PROJ's direct route falls back to GEOID18 and warns
@pytest.mark.filterwarnings("ignore:Best transformation is not available")
def test_navd88_chain_is_not_proj_direct_path_to_wgs84() -> None:
    # the direct EPSG:6349 to EPSG:4979 route treats NAD83(2011) as WGS 84; the Helmert it skips
    # moves Denver about 1.3 m horizontally and 0.86 m vertically (us-sources.md)
    direct = TransformerGroup("EPSG:6349", "EPSG:4979", always_xy=True).transformers[0]
    *_, direct_height = direct.transform(DENVER_LON, DENVER_LAT, DENVER_NAVD88_M)
    *_, height = ellipsoidal_height_from("EPSG:6349").transform(
        DENVER_LON, DENVER_LAT, DENVER_NAVD88_M
    )
    assert height - direct_height == pytest.approx(-0.86, abs=0.02)


def test_projected_navd88_heights_match_geographic_ones() -> None:
    easting, northing = Transformer.from_crs(
        "EPSG:6318", NAD83_2011_UTM_13N, always_xy=True
    ).transform(DENVER_LON, DENVER_LAT)
    projected = ellipsoidal_height_from(f"{NAD83_2011_UTM_13N}+5703").transform(
        easting, northing, DENVER_NAVD88_M
    )
    geographic = ellipsoidal_height_from("EPSG:6349").transform(
        DENVER_LON, DENVER_LAT, DENVER_NAVD88_M
    )
    assert projected == pytest.approx(geographic, abs=1e-6)


def test_wgs84_to_nad83_2011_inverts_the_horizontal_part_of_the_height_chain() -> None:
    to_utm = wgs84_to(NAD83_2011_UTM_13N)
    easting, northing = to_utm.transform(DENVER_LON, DENVER_LAT)
    lon, lat, _ = ellipsoidal_height_from(f"{NAD83_2011_UTM_13N}+5703").transform(
        easting, northing, DENVER_NAVD88_M
    )
    # the forward step runs the Helmert at zero height, the chain at 1583 m: the difference is
    # under 1e-8 degrees (1 mm)
    assert (lon, lat) == pytest.approx((DENVER_LON, DENVER_LAT), abs=1e-8)
    back = to_utm.transform(easting, northing, direction="INVERSE")
    assert back == pytest.approx((DENVER_LON, DENVER_LAT), abs=1e-10)


def test_navd88_on_an_unrealised_nad83_is_refused() -> None:
    with pytest.raises(ValueError, match="NAD83\\(2011\\)"):
        ellipsoidal_height_from("EPSG:26913+5703")


def test_missing_geoid18_grid_raises_before_any_use() -> None:
    # PROJ reads grids from its user directory; an empty one with the network off hides GEOID18
    env = os.environ | {"PROJ_USER_WRITABLE_DIRECTORY": "/nonexistent", "PROJ_NETWORK": "OFF"}
    code = "from satmesh_core import ellipsoidal_height_from; ellipsoidal_height_from('EPSG:6349')"
    result = subprocess.run(  # noqa: S603 (this interpreter, fixed code)
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode != 0
    assert "GridMissingError" in result.stderr
    assert "us_noaa_g2018u0.tif" in result.stderr
