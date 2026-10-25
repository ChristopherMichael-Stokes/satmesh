"""Imagery reprojected onto the mesh's box and CRS."""

import math

import numpy as np
from pyproj import Transformer
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject

from satmesh_core import Aoi
from satmesh_data import Raster

# Owner decision (f4-plan.md): keeps full z19 detail up to about 1.4 km and fits desktop WebGL;
# larger boxes get a coarser pixel instead of failing
MAX_TEXTURE_PX = 8192


def drape_texture(raster: Raster, box: Aoi) -> Raster:
    """Return `raster` bilinearly reprojected onto a north-up grid covering exactly `box`.

    The pixel size is the source's ground pixel at the box centre, coarsened only as far as needed
    to keep both sides within `MAX_TEXTURE_PX`. Raises `ValueError` if `raster` does not cover
    `box`.
    """
    _require_cover(raster, box)
    width_m, height_m = box.east - box.west, box.north - box.south
    pixel_m = max(source_pixel_m(raster, box), max(width_m, height_m) / MAX_TEXTURE_PX)
    cols, rows = math.ceil(width_m / pixel_m), math.ceil(height_m / pixel_m)
    transform = from_bounds(box.west, box.south, box.east, box.north, cols, rows)
    pixels = np.zeros((raster.pixels.shape[0], rows, cols), np.uint8)
    reproject(
        raster.pixels,
        pixels,
        src_transform=raster.transform,
        src_crs=raster.crs,
        dst_transform=transform,
        dst_crs=box.crs,
        resampling=Resampling.bilinear,
    )
    return Raster(pixels, transform, box.crs)


def source_pixel_m(raster: Raster, box: Aoi) -> float:
    """Return the width of one `raster` pixel at the box centre, measured in `box.crs` units."""
    to_raster = Transformer.from_crs(box.crs, raster.crs, always_xy=True)
    centre_x, centre_y = to_raster.transform((box.west + box.east) / 2, (box.south + box.north) / 2)
    xs, ys = to_raster.transform(
        [centre_x, centre_x + raster.transform.a], [centre_y, centre_y], direction="INVERSE"
    )
    return math.hypot(xs[1] - xs[0], ys[1] - ys[0])


def _require_cover(raster: Raster, box: Aoi) -> None:
    west, south, east, north = box.bounds_in(raster.crs)
    rows, cols = raster.pixels.shape[1:]
    t = raster.transform
    r_west, r_north = t.c, t.f
    r_east, r_south = r_west + cols * t.a, r_north + rows * t.e
    if not (r_west <= west and east <= r_east and r_south <= south and north <= r_north):
        msg = (
            f"raster ({r_west}, {r_south}, {r_east}, {r_north}) "
            f"does not cover box ({west}, {south}, {east}, {north})"
        )
        raise ValueError(msg)
