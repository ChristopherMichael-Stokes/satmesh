"""Imagery tiles from the local Esri cache, and coarser tiles assembled from them.

The cache holds `ZOOM/Y/X.jpg`. Tiles below `NATIVE_MIN_ZOOM` are not fetched from Esri; they are
built from the four tiles one level down, resized to `TILE_SIZE_PX`, and kept in a second directory
of the same layout.
"""

from pathlib import Path

import cv2
import numpy as np
import numpy.typing as npt

from satmesh_monitor.mercator import Tile

TILE_SIZE_PX = 256
NATIVE_MIN_ZOOM = 18
MIN_ASSEMBLED_ZOOM = 10
# BGR of the map's background colour (#1b1d21 in static/map.js), so absent quarters blend in
MISSING_CHILD_BGR = (33, 29, 27)
JPEG_QUALITY = 90

type Image = npt.NDArray[np.uint8]


def tile_path(directory: Path, tile: Tile) -> Path:
    """Where `tile` lives under `directory`."""
    return directory / str(tile.zoom) / str(tile.y) / f"{tile.x}.jpg"


def read_tile_jpeg(imagery_dir: Path, assembled_dir: Path, tile: Tile) -> bytes | None:
    """JPEG bytes of `tile`, or None when the cache holds nothing for it.

    A tile below `NATIVE_MIN_ZOOM` with some but not all children cached has the missing
    quarters in the map background colour.
    """
    if tile.zoom >= NATIVE_MIN_ZOOM:
        return _read_if_present(tile_path(imagery_dir, tile))
    if tile.zoom < MIN_ASSEMBLED_ZOOM:
        return None
    assembled_path = tile_path(assembled_dir, tile)
    if (cached := _read_if_present(assembled_path)) is not None:
        return cached
    children = [read_tile_jpeg(imagery_dir, assembled_dir, child) for child in tile.children()]
    if all(child is None for child in children):
        return None
    jpeg = _encode(_assemble(children))
    assembled_path.parent.mkdir(parents=True, exist_ok=True)
    assembled_path.write_bytes(jpeg)
    return jpeg


def _read_if_present(path: Path) -> bytes | None:
    return path.read_bytes() if path.is_file() else None


def _assemble(children: list[bytes | None]) -> Image:
    """Children as (north-west, north-east, south-west, south-east) into one tile."""
    side = 2 * TILE_SIZE_PX
    canvas: Image = np.full((side, side, 3), MISSING_CHILD_BGR, dtype=np.uint8)
    for index, jpeg in enumerate(children):
        if jpeg is None:
            continue
        row, column = divmod(index, 2)
        canvas[
            row * TILE_SIZE_PX : (row + 1) * TILE_SIZE_PX,
            column * TILE_SIZE_PX : (column + 1) * TILE_SIZE_PX,
        ] = _decode(jpeg)
    return np.asarray(
        cv2.resize(canvas, (TILE_SIZE_PX, TILE_SIZE_PX), interpolation=cv2.INTER_AREA),
        dtype=np.uint8,
    )


def _decode(jpeg: bytes) -> Image:
    image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        message = "cached tile is not a decodable image"
        raise ValueError(message)
    return np.asarray(image, dtype=np.uint8)


def _encode(image: Image) -> bytes:
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        message = "OpenCV could not encode the assembled tile"
        raise RuntimeError(message)
    return encoded.tobytes()
