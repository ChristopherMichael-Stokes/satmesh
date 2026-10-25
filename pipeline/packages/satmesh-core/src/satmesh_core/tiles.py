"""Web Mercator tiles covering an area of interest."""

import mercantile

from satmesh_core.aoi import Aoi


def covering_tiles(aoi: Aoi, zoom: int, margin_m: float) -> list[mercantile.Tile]:
    """Return the tiles at `zoom` covering `aoi` grown by `margin_m` ground metres on each side."""
    return list(mercantile.tiles(*aoi.grown(margin_m).wgs84_bounds(), [zoom]))
