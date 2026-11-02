from pathlib import Path

import cv2
import numpy as np

from satmesh_monitor.mercator import Tile
from satmesh_monitor.tiles import MISSING_CHILD_BGR, TILE_SIZE_PX, read_tile_jpeg, tile_path

# BGR, far apart so JPEG error cannot confuse them
NORTH_WEST = (255, 0, 0)
NORTH_EAST = (0, 255, 0)
SOUTH_WEST = (0, 0, 255)
SOUTH_EAST = (255, 255, 255)
JPEG_FLAT_COLOUR_TOLERANCE = 6  # 8-bit levels; quantisation of flat blocks plus chroma subsampling


def write_flat_tile(directory: Path, tile: Tile, bgr: tuple[int, int, int]) -> None:
    path = tile_path(directory, tile)
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.full((TILE_SIZE_PX, TILE_SIZE_PX, 3), bgr, dtype=np.uint8)
    assert cv2.imwrite(str(path), image)


def decode(jpeg: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert image is not None
    return np.asarray(image)


def assert_colour(pixel: np.ndarray, bgr: tuple[int, int, int]) -> None:
    assert np.abs(pixel.astype(int) - np.array(bgr)).max() <= JPEG_FLAT_COLOUR_TOLERANCE


def test_a_native_tile_is_served_as_stored(tmp_path: Path) -> None:
    imagery = tmp_path / "imagery"
    write_flat_tile(imagery, Tile(18, 10, 20), NORTH_WEST)

    jpeg = read_tile_jpeg(imagery, tmp_path / "assembled", Tile(18, 10, 20))

    assert jpeg == tile_path(imagery, Tile(18, 10, 20)).read_bytes()


def test_a_missing_tile_is_none(tmp_path: Path) -> None:
    assert read_tile_jpeg(tmp_path / "imagery", tmp_path / "assembled", Tile(18, 1, 1)) is None
    assert read_tile_jpeg(tmp_path / "imagery", tmp_path / "assembled", Tile(17, 1, 1)) is None


def test_a_coarser_tile_places_its_four_children_in_quadrants(tmp_path: Path) -> None:
    imagery, assembled = tmp_path / "imagery", tmp_path / "assembled"
    # parent (17, 5, 7) has children (18, 10..11, 14..15); y grows southwards
    write_flat_tile(imagery, Tile(18, 10, 14), NORTH_WEST)
    write_flat_tile(imagery, Tile(18, 11, 14), NORTH_EAST)
    write_flat_tile(imagery, Tile(18, 10, 15), SOUTH_WEST)
    write_flat_tile(imagery, Tile(18, 11, 15), SOUTH_EAST)

    image = decode(read_tile_jpeg(imagery, assembled, Tile(17, 5, 7)) or b"")

    half = TILE_SIZE_PX // 2
    assert image.shape == (TILE_SIZE_PX, TILE_SIZE_PX, 3)
    quarter = half // 2
    assert_colour(image[quarter, quarter], NORTH_WEST)
    assert_colour(image[quarter, half + quarter], NORTH_EAST)
    assert_colour(image[half + quarter, quarter], SOUTH_WEST)
    assert_colour(image[half + quarter, half + quarter], SOUTH_EAST)
    assert tile_path(assembled, Tile(17, 5, 7)).is_file()


def test_missing_children_are_background_and_the_result_comes_from_the_cache_afterwards(
    tmp_path: Path,
) -> None:
    imagery, assembled = tmp_path / "imagery", tmp_path / "assembled"
    write_flat_tile(imagery, Tile(18, 10, 14), NORTH_WEST)

    first = read_tile_jpeg(imagery, assembled, Tile(17, 5, 7)) or b""
    south_east = decode(first)[-1, -1]
    assert_colour(south_east, MISSING_CHILD_BGR)

    tile_path(imagery, Tile(18, 10, 14)).unlink()
    assert read_tile_jpeg(imagery, assembled, Tile(17, 5, 7)) == first


def test_a_tile_two_levels_up_is_assembled_through_the_level_between(tmp_path: Path) -> None:
    imagery, assembled = tmp_path / "imagery", tmp_path / "assembled"
    # (16, 2, 3) -> (17, 4..5, 6..7) -> z18 x 8..11, y 12..15; fill only the north-west corner
    write_flat_tile(imagery, Tile(18, 8, 12), SOUTH_WEST)

    image = decode(read_tile_jpeg(imagery, assembled, Tile(16, 2, 3)) or b"")

    eighth = TILE_SIZE_PX // 4
    assert_colour(image[eighth // 2, eighth // 2], SOUTH_WEST)
    assert_colour(image[-1, -1], MISSING_CHILD_BGR)
