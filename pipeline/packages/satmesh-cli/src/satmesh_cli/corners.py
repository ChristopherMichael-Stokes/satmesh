"""The area options: north-west and south-east corners as "lat, lon" text copied from a map."""

import math
from typing import NamedTuple

import typer

from satmesh_core import BRITISH_NATIONAL_GRID, WGS84, Aoi, wgs84_to_bng

MAX_LATITUDE_DEG = 90.0
MAX_LONGITUDE_DEG = 180.0
LAT_LON_PARTS = 2


class LatLon(NamedTuple):
    """A point in WGS84 degrees."""

    lat: float
    lon: float


def parse_lat_lon(text: str) -> LatLon:
    """Parse `"53.9236, -2.0015"` (comma, or whitespace alone) into a `LatLon`."""
    parts = text.replace(",", " ").split()
    if len(parts) != LAT_LON_PARTS:
        msg = f'expected "lat, lon", got {text!r}'
        raise typer.BadParameter(msg)
    try:
        lat, lon = (float(part) for part in parts)
    except ValueError:
        msg = f'expected "lat, lon" as numbers, got {text!r}'
        raise typer.BadParameter(msg) from None
    if not (math.isfinite(lat) and math.isfinite(lon)):
        msg = f"lat and lon must be finite, got {text!r}"
        raise typer.BadParameter(msg)
    if abs(lat) > MAX_LATITUDE_DEG or abs(lon) > MAX_LONGITUDE_DEG:
        msg = f"lat must be within 90 and lon within 180 degrees, got {text!r}"
        raise typer.BadParameter(msg)
    return LatLon(lat, lon)


def corners_to_wgs84(north_west: LatLon, south_east: LatLon) -> Aoi:
    """Return the WGS84 box between the corners; an empty or inverted box raises `ValueError`."""
    return Aoi(
        crs=WGS84,
        west=north_west.lon,
        south=south_east.lat,
        east=south_east.lon,
        north=north_west.lat,
    )


def corners_to_bng_inside(north_west: LatLon, south_east: LatLon) -> Aoi:
    """Return the largest whole-metre BNG box inside the corners' box, through OSTN15.

    Store scores need a box inside the store and on whole metres for the EA WCS; the corners'
    box is slightly rotated in BNG, so each edge is taken from the corner that reaches in furthest.
    """
    corners_to_wgs84(north_west, south_east)  # validates the order
    to_bng = wgs84_to_bng()
    nw_e, nw_n = to_bng.transform(north_west.lon, north_west.lat)
    se_e, se_n = to_bng.transform(south_east.lon, south_east.lat)
    ne_e, ne_n = to_bng.transform(south_east.lon, north_west.lat)
    sw_e, sw_n = to_bng.transform(north_west.lon, south_east.lat)
    return Aoi(
        crs=BRITISH_NATIONAL_GRID,
        west=math.ceil(max(nw_e, sw_e)),
        south=math.ceil(max(sw_n, se_n)),
        east=math.floor(min(ne_e, se_e)),
        north=math.floor(min(nw_n, ne_n)),
    )
