"""Environment Agency lidar point clouds (LAZ) by 5 km OS square, from the survey tile service.

The same service as the aerial imagery lists the 5 km squares that hold a point-cloud capture and
serves each as a zip of LAZ files. The National LIDAR Programme product is preferred; a listed
tile can still return 404, in which case the next capture is tried.
"""

import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import httpx

from satmesh_core import BRITISH_NATIONAL_GRID, Aoi
from satmesh_data.ea_aerial import GEOJSON_MEDIA_TYPE, SEARCH_URL
from satmesh_data.http import DEFAULT_INITIAL_BACKOFF_S, checked, with_retry

NATIONAL_PROGRAMME_PRODUCT = "national_lidar_programme_point_cloud"
POINT_CLOUD_PRODUCT_SUFFIX = "point_cloud"
CACHE_SUBDIR = Path("ea-lidar")
# the Dunster 5 km square is 492 MB zipped; the cap leaves room for denser captures
DEFAULT_MAX_DOWNLOAD_BYTES = 1_500_000_000
DOWNLOAD_CHUNK_BYTES = 1 << 20
TILE_SIDE_M = 5000
# OS National Grid: 100 km squares are lettered on a 5 x 5 grid, I omitted
GRID_LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"
SQUARE_100KM_M = 100_000
LETTERS_PER_SIDE = 5
# 100 km squares east of, and north of, the lettering's origin: the grid's 500 km lettering is
# anchored at the false origin of the OS National Grid
FALSE_ORIGIN_100KM = (10, 19)
NOT_FOUND = 404


@dataclass(frozen=True)
class PointCloudTile:
    """One 5 km OS square with a point-cloud capture, as the search lists it."""

    product: str
    year: int
    tile_id: str
    uri: str


def os_tile_id(easting_m: float, northing_m: float) -> str:
    """Return the 5 km OS National Grid square id (such as `SD9545`) containing a BNG point."""
    e100, n100 = int(easting_m // SQUARE_100KM_M), int(northing_m // SQUARE_100KM_M)
    major = (FALSE_ORIGIN_100KM[1] - n100) - (FALSE_ORIGIN_100KM[1] - n100) % LETTERS_PER_SIDE
    first = major + (e100 + FALSE_ORIGIN_100KM[0]) // LETTERS_PER_SIDE
    second = (FALSE_ORIGIN_100KM[1] - n100) * LETTERS_PER_SIDE % (LETTERS_PER_SIDE**2) + (
        e100 % LETTERS_PER_SIDE
    )
    east_km = int(easting_m % SQUARE_100KM_M // TILE_SIDE_M) * (TILE_SIDE_M // 1000)
    north_km = int(northing_m % SQUARE_100KM_M // TILE_SIDE_M) * (TILE_SIDE_M // 1000)
    return f"{GRID_LETTERS[first]}{GRID_LETTERS[second]}{east_km:02d}{north_km:02d}"


def tile_ids_covering(box: Aoi) -> tuple[str, ...]:
    """Return the 5 km square ids that meet a BNG `box`, sorted."""
    if box.crs != BRITISH_NATIONAL_GRID:
        msg = f"point-cloud squares are looked up in {BRITISH_NATIONAL_GRID}, got {box.crs}"
        raise ValueError(msg)
    ids = set()
    east = box.west
    while True:
        north = box.south
        while True:
            ids.add(os_tile_id(east, north))
            if north >= box.north:
                break
            north = min(north + TILE_SIDE_M, box.north)
        if east >= box.east:
            break
        east = min(east + TILE_SIDE_M, box.east)
    return tuple(sorted(ids))


def find_point_cloud_tiles(
    http: httpx.Client,
    box: Aoi,
    initial_backoff_s: float = DEFAULT_INITIAL_BACKOFF_S,
) -> dict[str, tuple[PointCloudTile, ...]]:
    """Return, per 5 km square meeting `box`, its captures: national programme first, newest first.

    The search takes a WGS84 polygon that is skewed against the grid, so it also lists neighbouring
    squares; only the squares that meet `box` are kept.
    """
    west, south, east, north = box.wgs84_bounds()
    polygon = {
        "type": "Polygon",
        "coordinates": [
            [[west, south], [east, south], [east, north], [west, north], [west, south]]
        ],
    }
    response = with_retry(
        lambda: checked(
            http.post(SEARCH_URL, json=polygon, headers={"Content-Type": GEOJSON_MEDIA_TYPE})
        ),
        initial_backoff_s,
    )
    wanted = set(tile_ids_covering(box))
    found = [
        PointCloudTile(
            product=result["product"]["id"],
            year=int(result["year"]["id"]),
            tile_id=result["tile"]["id"],
            uri=result["uri"],
        )
        for result in response.json()["results"]
        if result["product"]["id"].endswith(POINT_CLOUD_PRODUCT_SUFFIX)
        and result["tile"]["id"] in wanted
    ]
    return {
        tile_id: tuple(
            sorted(
                (t for t in found if t.tile_id == tile_id),
                key=lambda t: (t.product != NATIONAL_PROGRAMME_PRODUCT, -t.year),
            )
        )
        for tile_id in sorted(wanted)
    }


def fetch_point_cloud(
    http: httpx.Client,
    captures: tuple[PointCloudTile, ...],
    cache_dir: Path,
    max_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
    initial_backoff_s: float = DEFAULT_INITIAL_BACKOFF_S,
) -> tuple[Path, ...]:
    """Return the LAZ files of the first capture in `captures` that downloads, cached.

    A capture whose link answers 404 is skipped for the next; any other failure propagates. The
    response is chunked with no length, so a download past `max_bytes` raises `ValueError`.
    """
    if not captures:
        msg = "no point-cloud capture to fetch"
        raise ValueError(msg)
    for capture in captures:
        directory = _capture_directory(cache_dir, capture)
        if directory.exists():
            return tuple(sorted(directory.glob("*.laz")))
    for capture in captures:
        try:
            return _download_capture(http, capture, cache_dir, max_bytes, initial_backoff_s)
        except httpx.HTTPStatusError as error:
            if error.response.status_code != NOT_FOUND:
                raise
    msg = f"every capture of {captures[0].tile_id} answered 404"
    raise FileNotFoundError(msg)


def _download_capture(
    http: httpx.Client,
    capture: PointCloudTile,
    cache_dir: Path,
    max_bytes: int,
    initial_backoff_s: float,
) -> tuple[Path, ...]:
    directory = _capture_directory(cache_dir, capture)
    partial = directory.with_suffix(".zip.part")
    partial.parent.mkdir(parents=True, exist_ok=True)
    with_retry(lambda: _download(http, capture.uri, partial, max_bytes), initial_backoff_s)
    unpacking = directory.with_suffix(".unpacking")
    unpacking.mkdir(exist_ok=True)
    with zipfile.ZipFile(partial) as archive:
        for entry in archive.infolist():
            name = PurePosixPath(entry.filename).name  # never trust paths inside a download
            if name.lower().endswith(".laz"):
                with archive.open(entry) as source, (unpacking / name).open("wb") as target:
                    while chunk := source.read(DOWNLOAD_CHUNK_BYTES):
                        target.write(chunk)
    partial.unlink()
    unpacking.rename(directory)
    return tuple(sorted(directory.glob("*.laz")))


def _capture_directory(cache_dir: Path, capture: PointCloudTile) -> Path:
    return cache_dir / CACHE_SUBDIR / capture.product / str(capture.year) / capture.tile_id


def _download(http: httpx.Client, uri: str, path: Path, max_bytes: int) -> None:
    received = 0
    with http.stream("GET", uri) as response:
        checked(response)  # before the file exists, so a 404 leaves nothing behind
        with path.open("wb") as out:
            for chunk in response.iter_bytes(DOWNLOAD_CHUNK_BYTES):
                received += len(chunk)
                if received > max_bytes:
                    path.unlink()
                    msg = f"{uri} exceeds the {max_bytes} byte download cap"
                    raise ValueError(msg)
                out.write(chunk)
