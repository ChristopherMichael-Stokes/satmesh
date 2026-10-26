import pytest
import typer
from pyproj import Transformer

from satmesh_cli.corners import (
    LatLon,
    corners_to_bng_inside,
    corners_to_wgs84,
    parse_lat_lon,
)
from satmesh_core import BRITISH_NATIONAL_GRID, WGS84

UPPER_AIRE_NW = LatLon(53.925897, -2.005297)
UPPER_AIRE_SE = LatLon(53.921403, -1.997683)


@pytest.mark.parametrize(
    "text", ["53.9236, -2.0015", "53.9236,-2.0015", "  53.9236   -2.0015 ", "53.9236 , -2.0015"]
)
def test_a_map_copy_parses_with_or_without_the_comma(text: str) -> None:
    assert parse_lat_lon(text) == LatLon(53.9236, -2.0015)


@pytest.mark.parametrize(
    "text", ["", "53.9", "1, 2, 3", "north, west", "91, 0", "0, 181", "nan, 0"]
)
def test_anything_but_two_in_range_numbers_is_rejected(text: str) -> None:
    with pytest.raises(typer.BadParameter, match="lat"):
        parse_lat_lon(text)


def test_corners_make_the_wgs84_box() -> None:
    box = corners_to_wgs84(LatLon(48.86, 2.29), LatLon(48.85, 2.30))
    assert (box.crs, box.west, box.south, box.east, box.north) == (WGS84, 2.29, 48.85, 2.30, 48.86)


def test_corners_in_the_wrong_order_are_an_empty_box() -> None:
    with pytest.raises(ValueError, match="empty box"):
        corners_to_wgs84(LatLon(48.85, 2.29), LatLon(48.86, 2.30))


def test_the_bng_box_is_whole_metres_and_inside_the_corners() -> None:
    box = corners_to_bng_inside(UPPER_AIRE_NW, UPPER_AIRE_SE)
    assert box.crs == BRITISH_NATIONAL_GRID
    assert all(float(v).is_integer() for v in (box.west, box.south, box.east, box.north))
    to_wgs84 = Transformer.from_crs(BRITISH_NATIONAL_GRID, WGS84, always_xy=True)
    for easting, northing in (
        (box.west, box.south),
        (box.west, box.north),
        (box.east, box.south),
        (box.east, box.north),
    ):
        lon, lat = to_wgs84.transform(easting, northing)
        assert UPPER_AIRE_SE.lat <= lat <= UPPER_AIRE_NW.lat
        assert UPPER_AIRE_NW.lon <= lon <= UPPER_AIRE_SE.lon
    # the map box is the survey's 500 m square, about 400000 east at its east edge
    assert box.east - box.west == pytest.approx(500, abs=3)
    assert box.north - box.south == pytest.approx(500, abs=3)
