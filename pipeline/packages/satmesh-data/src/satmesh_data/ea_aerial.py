"""Environment Agency vertical aerial photography: index search, tile download, ECW crop.

The portal's search endpoint takes a WGS84 GeoJSON polygon and lists the 5 km OS squares with a
capture; a square downloads as a zip of 1 km ECW files. ECW needs the proprietary SDK, so the crop
to GeoTIFF runs in the `satmesh-gdal-ecw` Docker image (`make gdal-ecw-image`).
"""

import os
import shutil
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

import httpx
from pydantic import BaseModel, ConfigDict

from satmesh_core import BRITISH_NATIONAL_GRID, Aoi
from satmesh_data.http import DEFAULT_INITIAL_BACKOFF_S, checked, with_retry

SEARCH_URL = "https://environment.data.gov.uk/tiles/collections/survey/search"
AERIAL_PRODUCT_PREFIX = "vertical_aerial_photography"
CACHE_SUBDIR = Path("ea-aerial")
GDAL_ECW_IMAGE = "satmesh-gdal-ecw"
# the search endpoint rejects application/json
GEOJSON_MEDIA_TYPE = "application/geo+json"
# a 5 km square of 10 cm RGBN is about 260 MB zipped; 2008 40 cm squares reach 484 MB
DEFAULT_MAX_DOWNLOAD_BYTES = 2_000_000_000
DOWNLOAD_CHUNK_BYTES = 1 << 20
RGB_BANDS = (1, 2, 3)  # RGBN files carry NIR as band 4


class AerialTile(BaseModel):
    """One 5 km OS square with a capture, as the search lists it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    product: str
    year: int
    resolution_m: float
    tile_id: str
    uri: str


def find_aerial_tiles(
    http: httpx.Client,
    wgs84_bounds: tuple[float, float, float, float],
    initial_backoff_s: float = DEFAULT_INITIAL_BACKOFF_S,
) -> tuple[AerialTile, ...]:
    """Return the aerial captures whose 5 km square meets the WGS84 box, newest year first.

    `wgs84_bounds` is (west, south, east, north) in degrees.
    """
    west, south, east, north = wgs84_bounds
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
    tiles = [
        AerialTile(
            product=result["product"]["id"],
            year=int(result["year"]["id"]),
            resolution_m=float(result["resolution"]["id"]),
            tile_id=result["tile"]["id"],
            uri=result["uri"],
        )
        for result in response.json()["results"]
        if result["product"]["id"].startswith(AERIAL_PRODUCT_PREFIX)
    ]
    return tuple(sorted(tiles, key=lambda t: (-t.year, t.resolution_m, t.tile_id)))


def fetch_aerial_ecws(
    http: httpx.Client,
    tile: AerialTile,
    cache_dir: Path,
    max_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
    initial_backoff_s: float = DEFAULT_INITIAL_BACKOFF_S,
) -> tuple[Path, ...]:
    """Return the ECW files of `tile`, downloading and unzipping them if not cached.

    The response is chunked with no length, so the download stops with `ValueError` past
    `max_bytes`. The zip is deleted after extraction.
    """
    directory = _tile_directory(cache_dir, tile)
    if directory.exists():
        return tuple(sorted(directory.glob("*.ecw")))
    partial = directory.with_suffix(".zip.part")
    partial.parent.mkdir(parents=True, exist_ok=True)
    with_retry(lambda: _download(http, tile.uri, partial, max_bytes), initial_backoff_s)
    unpacking = directory.with_suffix(".unpacking")
    unpacking.mkdir(exist_ok=True)
    with zipfile.ZipFile(partial) as archive:
        for entry in archive.infolist():
            name = PurePosixPath(entry.filename).name  # never trust paths inside a download
            if name.lower().endswith(".ecw"):
                (unpacking / name).write_bytes(archive.read(entry))
    partial.unlink()
    unpacking.rename(directory)
    return tuple(sorted(directory.glob("*.ecw")))


def crop_aerial(ecws: tuple[Path, ...], box: Aoi, out_path: Path, cache_dir: Path) -> Path:
    """Write the RGB bands of `ecws` over `box` (BNG) to a GeoTIFF at `out_path`, in Docker.

    `ecws` and `out_path` must lie under `cache_dir`, which is mounted into the container.
    """
    if box.crs != BRITISH_NATIONAL_GRID:
        msg = f"aerial crops are cut in {BRITISH_NATIONAL_GRID}, got {box.crs}"
        raise ValueError(msg)
    if out_path.exists():
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mosaic = out_path.with_suffix(".vrt")
    partial = out_path.with_suffix(".part")
    _gdal(
        cache_dir,
        ["gdalbuildvrt", "-a_srs", BRITISH_NATIONAL_GRID, _mounted(mosaic, cache_dir)]
        + [_mounted(ecw, cache_dir) for ecw in ecws],
    )
    band_args = [arg for band in RGB_BANDS for arg in ("-b", str(band))]
    _gdal(
        cache_dir,
        [
            "gdal_translate",
            *band_args,
            "-projwin", str(box.west), str(box.north), str(box.east), str(box.south),
            "-of", "GTiff", "-co", "COMPRESS=DEFLATE", "-co", "TILED=YES",
            _mounted(mosaic, cache_dir),
            _mounted(partial, cache_dir),
        ],
    )  # fmt: skip
    partial.replace(out_path)
    return out_path


def _tile_directory(cache_dir: Path, tile: AerialTile) -> Path:
    return (
        cache_dir
        / CACHE_SUBDIR
        / tile.product
        / str(tile.year)
        / str(tile.resolution_m)
        / tile.tile_id
    )


def _download(http: httpx.Client, uri: str, path: Path, max_bytes: int) -> None:
    received = 0
    with http.stream("GET", uri) as response, path.open("wb") as out:
        checked(response)
        for chunk in response.iter_bytes(DOWNLOAD_CHUNK_BYTES):
            received += len(chunk)
            if received > max_bytes:
                path.unlink()
                msg = f"{uri} exceeds the {max_bytes} byte download cap"
                raise ValueError(msg)
            out.write(chunk)


def _mounted(path: Path, cache_dir: Path) -> str:
    return (Path("/data") / path.relative_to(cache_dir)).as_posix()


def _gdal(cache_dir: Path, command: list[str]) -> None:
    docker = shutil.which("docker")
    if docker is None:
        msg = "docker is not on PATH; the ECW crop runs in the satmesh-gdal-ecw image"
        raise FileNotFoundError(msg)
    subprocess.run(  # noqa: S603 (arguments are our own paths and constants)
        [
            docker,
            "run",
            "--rm",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-v",
            f"{cache_dir}:/data",
            GDAL_ECW_IMAGE,
            *command,
        ],
        check=True,
    )
