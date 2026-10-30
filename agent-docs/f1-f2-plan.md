---
status: historical
topic: baseline-pipeline
summary: Executed plan for satmesh-core (AOI, metric CRS, tile cover) and satmesh-data (Esri tiles, EA DTM WCS)
answers: What do Aoi, metric_crs and covering_tiles do?; How are Esri tiles cached?; What did F1 and F2 leave out?; How is the EA DTM fetched?
---

# Plan: F1 core geometry and F2 Esri plus EA DTM fetch

Approved and implemented 2026-10-25. Builds the first two packages of the baseline pipeline on
the chain S5 proved (`s5-results.md`). UK sites are the primary test sites, with EA 1 m lidar as
ground truth; S3 and S4 (US sites) and S2, S2b and S7 wait until an experiment needs them.

## Scope

In:

- F1 `satmesh-core`: AOI type, metric CRS choice, tiles covering an AOI. Core stays
  source-agnostic.
- F2 `satmesh-data`: Esri layer 4 metadata and zoom choice, cached and throttled Esri tile fetch
  with placeholder detection, EA 1 m DTM fetch by WCS.

Out, each with its own later task:

- Source registry and selection policy (F2a). F2 exposes the two adapters as plain functions; the
  registry and the code that walks it come later.
- Other DEM and imagery sources (F2b): EA aerial ECW, Welsh COG, GLO-30, OS Terrain 50.
- Mosaic and crop (F3), meshing (F4), CLI (F5).

## F1 `satmesh-core`

| Unit | Shape |
| --- | --- |
| `Aoi` | Frozen pydantic model: a box `(west, south, east, north)` in a named CRS, validated non-empty. Built from a WGS84 box or a BNG box |
| `metric_crs(aoi)` | EPSG:27700 when the AOI lies inside BNG's area of use, else the UTM zone from `pyproj.database.query_utm_crs_info` |
| `covering_tiles(aoi, zoom)` | `mercantile.tiles` over the AOI's WGS84 bounds plus a margin in metres |

- The existing `gsd.py` stays as it is.
- BNG XY is 0.04% short of ground distance (S5). F1 does not correct it; F4 decides.

## F2 `satmesh-data`

| Unit | Shape |
| --- | --- |
| `EsriClient` | Owns an `httpx.Client`, a minimum interval between requests, and a cache directory. Methods: `sources_at(lon, lat) -> list[EsriSource]` (layer 4 `identify`), `tile(z, y, x) -> bytes` |
| `EsriSource` | Frozen pydantic model parsed from one layer 4 polygon: source name, `SRC_RES` m, date, min and max cache level |
| `choose_zoom(sources, latitude)` | Polygon with the highest max cache level, ties to the finest `SRC_RES`; zoom from core's `zoom_for_resolution`, clamped to the polygon's min and max cache levels (Denver's 0.34 m source is drawn only at level 20) |
| Tile cache | One file per tile at `<cache>/esri-world-imagery/live/{z}/{y}/{x}.jpg`; a hit makes no request. `live` leaves room for Wayback release ids; live tiles go stale when Esri updates imagery, and clearing the cache is the remedy |
| Placeholder | 2521 bytes with md5 prefix `f27d9de7` raises `PlaceholderTileError`; never cached |
| Zoom guard | `tile` raises before any request when `z` exceeds the max cache level known for the AOI |
| `fetch_ea_dtm(box_bng, cache)` | WCS 2.0.1 GetCoverage to a GeoTIFF cached by coverage id and box; checks CRS EPSG:27700, 1 m pixels, exact bounds and no nodata, raising otherwise |

- Retry with exponential backoff on network errors, 429 and 5xx via tenacity; other statuses raise.
- User-Agent `satmesh/<version> (research; <repo url>)`.
- The caller passes the cache directory; F5 picks the default.
- The minimum interval between Esri requests is a hand-written sleep: one monotonic timestamp and
  one sleep, so no library is warranted.

## Dependencies

| Package | New dependencies | Why |
| --- | --- | --- |
| `satmesh-core` | pydantic, pyproj, mercantile | Validated AOI; CRS and UTM lookup; tile math |
| `satmesh-data` | `satmesh-core`, httpx, tenacity, rasterio | HTTP with a test transport; retry and backoff on 429 and 5xx, which httpx's transport retries do not cover; GeoTIFF checks |

None pulls in PyTorch; `uv.lock` is checked after adding them.

## Tests

- `covering_tiles` and `metric_crs`: expected tiles and zones worked out from the Web Mercator and
  UTM definitions at fixed points (Upper Aire, a UTM-zone boundary, a point outside BNG).
- `choose_zoom`: the Denver case from S1 (0.34 m source only at level 20, 0.5 m at levels 12 to 19)
  picks z20.
- `EsriClient` against `httpx.MockTransport` serving canned responses: a cache hit makes no request,
  a placeholder raises and is not cached, 503 then 200 retries, the zoom guard raises with no
  request.
- `fetch_ea_dtm`: a GeoTIFF written in the test with rasterio and served by `MockTransport`, with
  wrong-CRS, wrong-bounds and nodata variants.
- No live tests in `make test`. A scratch harness fetches the S5 Upper Aire box live and compares
  the outputs with S5's files.

## Docs

- `TODO.md`: S3 and S4 reworded to UK sites with EA lidar ground truth, and F1 and F2 ticked when
  done.
- `implementation-plan.md`: stage 1 exit and stage 3 changed to UK ground truth; S2, S2b and S7
  marked as on demand.
- `AGENTS.md` layout row for `pipeline/` lists `satmesh-data`.

## Checkpoints

1. F1 with tests; `make check` and `make test` pass.
2. F2 with tests; the live harness on the Upper Aire box matches S5.
