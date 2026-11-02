"""Web Mercator slippy-map tile indices (EPSG:3857, y counted down from the north edge)."""

import math
from typing import NamedTuple

CHILDREN_PER_TILE_SIDE = 2


class Tile(NamedTuple):
    """A tile of the `zoom` level's 2^zoom by 2^zoom grid."""

    zoom: int
    x: int
    y: int

    def children(self) -> tuple["Tile", "Tile", "Tile", "Tile"]:
        """The four tiles one level down, as (north-west, north-east, south-west, south-east)."""
        zoom, x, y = self.zoom + 1, CHILDREN_PER_TILE_SIDE * self.x, CHILDREN_PER_TILE_SIDE * self.y
        return (
            Tile(zoom, x, y),
            Tile(zoom, x + 1, y),
            Tile(zoom, x, y + 1),
            Tile(zoom, x + 1, y + 1),
        )


def tile_containing(longitude_deg: float, latitude_deg: float, zoom: int) -> Tile:
    """The tile holding a WGS84 point.

    x = floor(n (lon + 180) / 360), y = floor(n (1 - asinh(tan(lat)) / pi) / 2) with n = 2^zoom
    (https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames#Python).
    """
    tiles_per_side = 2**zoom
    x = math.floor(tiles_per_side * (longitude_deg + 180.0) / 360.0)
    mercator_y = math.asinh(math.tan(math.radians(latitude_deg)))
    y = math.floor(tiles_per_side * (1.0 - mercator_y / math.pi) / 2.0)
    return Tile(zoom, x, y)
