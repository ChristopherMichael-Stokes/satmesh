"""Ground sample distance of Web Mercator (EPSG:3857) tiles."""

import math

# 2 * pi * 6378137 m (WGS84 semi-major axis) / 256 px: metres per pixel at zoom 0 on the equator
EQUATOR_METRES_PER_PIXEL_AT_ZOOM_0 = 156543.03392804097


def ground_sample_distance_m(zoom: int, latitude_deg: float) -> float:
    """Return the true ground metres per pixel of a 256 px tile at `zoom` and `latitude_deg`.

    GSD = 156543.03392804097 * cos(latitude) / 2**zoom, the standard Web Mercator relation.
    """
    return (
        EQUATOR_METRES_PER_PIXEL_AT_ZOOM_0
        * math.cos(math.radians(latitude_deg))
        / math.ldexp(1.0, zoom)
    )


def zoom_for_resolution(source_resolution_m: float, latitude_deg: float, max_zoom: int) -> int:
    """Return the coarsest zoom with GSD at or below `source_resolution_m`, capped at `max_zoom`.

    z = ceil(log2(156543.03392804097 * cos(latitude) / source_resolution)).
    """
    if source_resolution_m <= 0:
        msg = f"source_resolution_m must be positive, got {source_resolution_m}"
        raise ValueError(msg)
    ideal = math.log2(
        EQUATOR_METRES_PER_PIXEL_AT_ZOOM_0
        * math.cos(math.radians(latitude_deg))
        / source_resolution_m
    )
    return min(math.ceil(ideal), max_zoom)
