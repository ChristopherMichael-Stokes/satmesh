import math

import pytest
from pydantic import ValidationError
from pyproj import Transformer

from satmesh_core import BRITISH_NATIONAL_GRID, WGS84, Aoi, covering_tiles, metric_crs

# S5 box at Upper Aire, BNG metres
UPPER_AIRE = Aoi(crs=BRITISH_NATIONAL_GRID, west=399500, south=447000, east=400500, north=448000)


def point_aoi(lon: float, lat: float, half_deg: float = 0.001) -> Aoi:
    return Aoi(
        crs=WGS84,
        west=lon - half_deg,
        south=lat - half_deg,
        east=lon + half_deg,
        north=lat + half_deg,
    )


def utm_north_epsg(lon: float) -> str:
    """UTM zone n spans longitudes [-180 + 6(n - 1), -180 + 6n); northern zones are EPSG:326nn."""
    return f"EPSG:{32600 + math.floor((lon + 180) / 6) + 1}"


def tile_index(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    """Web Mercator tile index.

    x = floor((lon + 180) / 360 * 2^z), y = floor((1 - asinh(tan lat) / pi) / 2 * 2^z).
    """
    n = 1 << zoom
    x = math.floor((lon + 180) / 360 * n)
    y = math.floor((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def test_empty_box_is_rejected() -> None:
    with pytest.raises(ValidationError, match="empty box"):
        Aoi(crs=WGS84, west=1.0, south=50.0, east=1.0, north=51.0)


def test_unknown_crs_is_rejected() -> None:
    with pytest.raises(ValidationError, match="crs not found"):
        Aoi(crs="EPSG:999999", west=0.0, south=0.0, east=1.0, north=1.0)


def test_great_britain_meshes_in_bng() -> None:
    assert metric_crs(UPPER_AIRE) == BRITISH_NATIONAL_GRID


@pytest.mark.parametrize(
    ("name", "lon", "lat"),
    [
        ("Denver", -105.0, 39.74),
        ("Belfast", -5.93, 54.6),
        ("west of the 29/30 zone edge", -6.001, 40.0),
    ],
)
def test_outside_great_britain_meshes_in_utm(name: str, lon: float, lat: float) -> None:
    assert metric_crs(point_aoi(lon, lat)) == utm_north_epsg(lon), name


def test_tiles_without_margin_span_the_box_corners() -> None:
    aoi = point_aoi(-2.0, 53.92, half_deg=0.002)
    zoom = 19
    x0, y0 = tile_index(aoi.west, aoi.north, zoom)
    x1, y1 = tile_index(aoi.east, aoi.south, zoom)
    expected = {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}
    assert {(t.x, t.y) for t in covering_tiles(aoi, zoom, margin_m=0)} == expected


def test_margin_reaches_ground_metres_beyond_the_box() -> None:
    margin_m, zoom = 100.0, 19
    tiles = {(t.x, t.y) for t in covering_tiles(UPPER_AIRE, zoom, margin_m=margin_m)}
    to_wgs84 = Transformer.from_crs(BRITISH_NATIONAL_GRID, WGS84, always_xy=True)
    centre_e, centre_n = (
        (UPPER_AIRE.west + UPPER_AIRE.east) / 2,
        (UPPER_AIRE.south + UPPER_AIRE.north) / 2,
    )
    just_inside_margin = [
        (UPPER_AIRE.east + margin_m - 1, centre_n),
        (UPPER_AIRE.west - margin_m + 1, centre_n),
        (centre_e, UPPER_AIRE.north + margin_m - 1),
        (centre_e, UPPER_AIRE.south - margin_m + 1),
    ]
    for easting, northing in just_inside_margin:
        assert tile_index(*to_wgs84.transform(easting, northing), zoom) in tiles


def test_negative_margin_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        covering_tiles(UPPER_AIRE, 19, margin_m=-1.0)
