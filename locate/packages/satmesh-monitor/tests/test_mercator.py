import math

from hypothesis import given
from hypothesis import strategies as st

from satmesh_monitor.mercator import Tile, tile_containing


def test_the_origin_is_the_south_east_corner_of_the_first_quadrant_at_zoom_one() -> None:
    # zoom 1 is a 2 x 2 grid; (0, 0) sits on the shared corner, and a point just north-east
    # of it is in the north-east tile
    assert tile_containing(0.001, 0.001, 1) == Tile(1, 1, 0)
    assert tile_containing(-0.001, -0.001, 1) == Tile(1, 0, 1)


def test_bexhill_at_zoom_eighteen() -> None:
    # n = 2^18; x = floor(n (0.4506 + 180) / 360); y from the Mercator ordinate
    # asinh(tan(50.8585 deg)) = 1.0166..., y = floor(n (1 - 1.0166.../pi) / 2)
    n = 2**18
    expected_x = math.floor(n * 180.4506 / 360.0)
    mercator_y = math.log(math.tan(math.radians(50.8585)) + 1 / math.cos(math.radians(50.8585)))
    expected_y = math.floor(n * (1 - mercator_y / math.pi) / 2)
    assert tile_containing(0.4506, 50.8585, 18) == Tile(18, expected_x, expected_y)
    assert (expected_x, expected_y) == (131400, 87923)


@given(
    longitude=st.floats(-179.9, 179.9),
    latitude=st.floats(-80.0, 80.0),
    zoom=st.integers(0, 20),
)
def test_the_point_lies_in_one_of_the_children_of_its_tile(
    longitude: float, latitude: float, zoom: int
) -> None:
    parent = tile_containing(longitude, latitude, zoom)

    assert tile_containing(longitude, latitude, zoom + 1) in parent.children()
