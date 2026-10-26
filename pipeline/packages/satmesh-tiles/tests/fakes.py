"""Stand-ins for Esri and the EA WCS, and a small Upper Aire area, shared by the tiler tests."""

import io
import re
from pathlib import Path

import httpx
import mercantile
import numpy as np
from PIL import Image
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds

from satmesh_core import Aoi
from satmesh_data import EA_DSM, WEB_MERCATOR, EsriClient

UPPER_AIRE_LON, UPPER_AIRE_LAT = -2.0015, 53.9236
LEAF_ZOOM = 17
INSET_M = 10.0
CANOPY_M = 2.0
IDENTIFY = {
    "results": [
        {
            "layerId": 4,
            "attributes": {
                "SOURCE_INFO": "Vivid",
                "RESOLUTION (M)": "0.34",
                "DATE (YYYYMMDD)": "20250318",
                "FROM_CACHE_LEVEL": "12",
                "TO_CACHE_LEVEL": "19",
            },
        }
    ]
}


def ignore_progress(phase: str, done: int, total: int) -> None:
    """A progress hook that shows nothing."""


def jpeg(colour: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (256, 256), colour).save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def tile_colour(tile_path: str) -> tuple[int, int, int]:
    """A colour that differs between neighbouring tiles, from a `.../tile/z/y/x` path."""
    z, y, x = (int(v) for v in tile_path.rsplit("/", 3)[1:])
    return (x * 37 + z) % 200 + 30, (y * 91) % 200 + 30, (x + y) * 53 % 200 + 30


class FakeServices:
    """Esri identify, Esri tiles and the EA WCS, counting what a build asks of each."""

    def __init__(self) -> None:
        self.requests: dict[str, int] = {"identify": 0, "tile": 0, "wcs": 0}

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/identify"):
            self.requests["identify"] += 1
            return httpx.Response(200, json=IDENTIFY)
        if "/tile/" in path:
            self.requests["tile"] += 1
            return httpx.Response(200, content=jpeg(tile_colour(path)))
        self.requests["wcs"] += 1
        return httpx.Response(200, content=self.lidar(request))

    @staticmethod
    def lidar(request: httpx.Request) -> bytes:
        """A sloping plane; the first-return DSM sits `CANOPY_M` above the DTM."""
        subsets = request.url.params.get_list("subset")
        east, north = (tuple(int(v) for v in re.findall(r"-?\d+", subset)) for subset in subsets)
        cols, rows = east[1] - east[0], north[1] - north[0]
        heights = (
            100.0
            + 0.1 * np.arange(cols, dtype=np.float32)[None, :]
            + np.zeros((rows, 1), np.float32)
        )
        if request.url.params["coverageId"] == EA_DSM.coverage_id:
            heights += CANOPY_M
        with MemoryFile() as memory:
            with memory.open(
                driver="GTiff",
                width=cols,
                height=rows,
                count=1,
                dtype="float32",
                crs="EPSG:27700",
                transform=from_bounds(east[0], north[0], east[1], north[1], cols, rows),
            ) as dst:
                dst.write(heights, 1)
            return bytes(memory.read())


def square_of_four_leaves() -> tuple[Aoi, set[mercantile.Tile]]:
    base = mercantile.tile(UPPER_AIRE_LON, UPPER_AIRE_LAT, LEAF_ZOOM)
    x0, y0 = base.x - base.x % 2, base.y - base.y % 2
    leaves = {mercantile.Tile(x0 + dx, y0 + dy, LEAF_ZOOM) for dx in (0, 1) for dy in (0, 1)}
    left = mercantile.xy_bounds(mercantile.Tile(x0, y0 + 1, LEAF_ZOOM))
    right = mercantile.xy_bounds(mercantile.Tile(x0 + 1, y0, LEAF_ZOOM))
    aoi = Aoi(
        crs=WEB_MERCATOR,
        west=left.left + INSET_M,
        south=left.bottom + INSET_M,
        east=right.right - INSET_M,
        north=right.top - INSET_M,
    )
    return aoi, leaves


def clients(services: FakeServices, cache: Path) -> tuple[EsriClient, httpx.Client]:
    http = httpx.Client(transport=httpx.MockTransport(services.handle))
    return EsriClient(http, cache, min_interval_s=0.0, initial_backoff_s=0.0), http
