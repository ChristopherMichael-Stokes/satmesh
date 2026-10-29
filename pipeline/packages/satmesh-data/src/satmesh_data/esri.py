"""Esri World Imagery: source metadata, zoom choice and cached, throttled tile fetch."""

import hashlib
import threading
import time
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
import mercantile
from pydantic import BaseModel, ConfigDict, Field, field_validator

from satmesh_core import zoom_for_resolution
from satmesh_data.http import DEFAULT_INITIAL_BACKOFF_S, checked, with_retry

BASE_URL = "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer"
CITATIONS_LAYER = 4
# identify needs a map extent and display size to turn its pixel tolerance into ground distance;
# 0.01 degrees over 400 px with 1 px tolerance hits only polygons under the point (S1 probe)
IDENTIFY_HALF_EXTENT_DEG = 0.01
IDENTIFY_IMAGE_DISPLAY = "400,400,96"
# "Map data not yet available" tile served with HTTP 200 past the cached depth (S1)
PLACEHOLDER_SIZE_BYTES = 2521
PLACEHOLDER_MD5_PREFIX = "f27d9de7"
# 1 request/s ran S1, S5 and S6 (over 600 requests) with no throttling response;
# Esri publishes no limit
DEFAULT_MIN_INTERVAL_S = 1.0
CACHE_SUBDIR = Path("esri-world-imagery") / "live"
NULL_ATTRIBUTE = "Null"


class PlaceholderTileError(Exception):
    """Esri served its "Map data not yet available" tile: no imagery at this zoom and place."""


class ZoomBeyondSourceError(ValueError):
    """A tile was requested deeper than the imagery source's deepest cache level."""


class EsriSource(BaseModel):
    """One layer 4 (Citations) polygon: an imagery source and the cache levels it is drawn at."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    source_info: str = Field(alias="SOURCE_INFO")
    resolution_m: float = Field(alias="RESOLUTION (M)")
    capture_date: date | None = Field(alias="DATE (YYYYMMDD)")
    from_cache_level: int = Field(alias="FROM_CACHE_LEVEL")
    to_cache_level: int = Field(alias="TO_CACHE_LEVEL")

    @field_validator("capture_date", mode="before")
    @classmethod
    def _parse_yyyymmdd(cls, value: Any) -> date | None:  # noqa: ANN401 (raw JSON before validation)
        if value == NULL_ATTRIBUTE:
            return None
        return datetime.strptime(value, "%Y%m%d").date()  # noqa: DTZ007 (a calendar date, no time zone)


class _IdentifyResult(BaseModel):
    attributes: EsriSource


class _IdentifyResponse(BaseModel):
    results: list[_IdentifyResult]


def choose_zoom(sources: list[EsriSource], latitude_deg: float) -> tuple[int, EsriSource]:
    """Return the zoom to fetch and the source drawn there.

    The source is the one cached deepest, ties to the finest resolution. The zoom is the coarsest
    whose ground sample distance reaches that source's resolution, clamped to the source's cache
    levels: a source that starts at a deep level is only visible from there.
    """
    if not sources:
        msg = "no imagery sources"
        raise ValueError(msg)
    best = max(sources, key=lambda s: (s.to_cache_level, -s.resolution_m))
    zoom = zoom_for_resolution(best.resolution_m, latitude_deg, max_zoom=best.to_cache_level)
    return max(zoom, best.from_cache_level), best


def is_placeholder(data: bytes) -> bool:
    """Return whether `data` is Esri's "Map data not yet available" tile."""
    return len(data) == PLACEHOLDER_SIZE_BYTES and hashlib.md5(data).hexdigest().startswith(  # noqa: S324 (fingerprint, not security)
        PLACEHOLDER_MD5_PREFIX
    )


class EsriClient:
    """Esri World Imagery access that caches tiles by (z, y, x) and spaces requests apart.

    Safe to call from several threads: they share one request schedule.
    """

    def __init__(
        self,
        http: httpx.Client,
        cache_dir: Path,
        min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
        initial_backoff_s: float = DEFAULT_INITIAL_BACKOFF_S,
    ) -> None:
        """Use `http` for requests and keep tiles under `cache_dir`; the caller owns `http`."""
        self._http = http
        self._tile_dir = cache_dir / CACHE_SUBDIR
        self._min_interval_s = min_interval_s
        self._initial_backoff_s = initial_backoff_s
        self._next_request = -float("inf")
        self._schedule_lock = threading.Lock()

    def sources_at(self, lon: float, lat: float) -> list[EsriSource]:
        """Return every imagery source polygon under a WGS84 point."""
        d = IDENTIFY_HALF_EXTENT_DEG
        params = {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "sr": 4326,
            "layers": f"all:{CITATIONS_LAYER}",
            "tolerance": 1,
            "mapExtent": f"{lon - d},{lat - d},{lon + d},{lat + d}",
            "imageDisplay": IDENTIFY_IMAGE_DISPLAY,
            "returnGeometry": "false",
            "f": "json",
        }
        body = self._get(f"{BASE_URL}/identify", params).content
        return [r.attributes for r in _IdentifyResponse.model_validate_json(body).results]

    def tile(self, tile: mercantile.Tile, max_zoom: int) -> bytes:
        """Return the JPEG for `tile`, from the cache when present.

        Raises `ZoomBeyondSourceError` without a request when `tile.z > max_zoom`, and
        `PlaceholderTileError` (nothing cached) when Esri has no imagery there.
        """
        if tile.z > max_zoom:
            msg = f"zoom {tile.z} is past the source's deepest level {max_zoom}"
            raise ZoomBeyondSourceError(msg)
        path = self._tile_dir / str(tile.z) / str(tile.y) / f"{tile.x}.jpg"
        if path.exists():
            return path.read_bytes()
        data = self._get(f"{BASE_URL}/tile/{tile.z}/{tile.y}/{tile.x}", {}).content
        if is_placeholder(data):
            msg = f"placeholder tile at {tile}"
            raise PlaceholderTileError(msg)
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(".part")
        partial.write_bytes(data)
        partial.replace(path)
        return data

    def query_citations(self, params: Mapping[str, str | int | float]) -> bytes:
        """Return the raw JSON of one layer 4 (Citations) `query` request with `params`."""
        return self._get(f"{BASE_URL}/{CITATIONS_LAYER}/query", params).content

    def _get(self, url: str, params: Mapping[str, str | int | float]) -> httpx.Response:
        return with_retry(lambda: self._throttled_get(url, params), self._initial_backoff_s)

    def _throttled_get(self, url: str, params: Mapping[str, str | int | float]) -> httpx.Response:
        # each request reserves the next free slot under the lock and then waits for it outside
        # it, so any number of threads share one request rate
        with self._schedule_lock:
            slot = max(time.monotonic(), self._next_request)
            self._next_request = slot + self._min_interval_s
        wait_s = slot - time.monotonic()
        if wait_s > 0:
            time.sleep(wait_s)
        return checked(self._http.get(url, params=params))
