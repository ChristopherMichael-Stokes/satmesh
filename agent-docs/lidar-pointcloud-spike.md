---
status: historical
topic: sources
summary: Spike: EA National LIDAR Programme raw LAZ downloads with one unauthenticated GET per 5 km tile; LAS 1.2 with intensity and classes
answers: How do I download EA lidar point clouds; What tile size does the EA point cloud endpoint serve; Does the EA point cloud carry intensity and classification; What CRS and point density do EA LAZ files have
---

# EA National LIDAR Programme point cloud spike

It works: the raw LAZ downloads with one unauthenticated GET, no portal scraping needed (VERIFIED).

## Endpoint

- Same OGC-style service the repo already uses for aerial imagery (`ea_aerial.py`).
- Search (VERIFIED): `POST https://environment.data.gov.uk/tiles/collections/survey/search`,
  header `Content-Type: application/geo+json`, body a WGS84 GeoJSON Polygon. Returns
  `results[]` with `product.id`, `year.id`, `resolution.id`, `tile.id`, `uri`.
- Point-cloud products listed for the AOI (VERIFIED): `national_lidar_programme_point_cloud`
  (2020, res 1) and the older `lidar_point_cloud` (2016, res NaN).
- Download (VERIFIED): `GET <uri>`, e.g.
  `.../survey/national_lidar_programme_point_cloud/2020/1/SD9545`. Returns `application/zip`
  with `content-disposition: ...-SD94ne.zip`. No Content-Length, HEAD gives 405, Range is
  ignored, so cap size by piping through `head -c`.
- The tile id is a **5 km** OS square (SD9545 = E395-400, N445-450), not 1 km. The zip holds one
  LAZ `SD9545_P_10663_20200318_20200319.laz` (155 MB, 51 M points). Fetching a 1 km tile means
  downloading the 5 km file and cropping (assumed: there is no 1 km endpoint; not found in this spike).
- Target E399800 N447300 is OS ref SD9947 (VERIFIED by arithmetic), inside SD9545.
- Licence: Open Government Licence v3 (ASSUMED from uk-sources.md and EA portal; not re-read).
- Polite use: one search, one download, UA `satmesh-research-spike (<email>)`.

## Contents (VERIFIED with laspy 2 + lazrs, `python -I`)

| Item | Value |
| --- | --- |
| Format | LAS 1.2, point format 1 (XYZ, intensity, returns, class, GPS time; no RGB) |
| Writer | lasclip64 / LAStools, created 2020-04-22 |
| CRS | GeoTIFF keys only: EPSG:27700 horizontal, units metres (9001); no vertical datum key (ODN assumed) |
| Scale | 0.01 m |
| Z range (5 km file) | 88.2 to 368.2 m |
| Survey dates | file name 2020-03-18 to 2020-03-19; GPS time agrees (adjusted GPS time) |
| Whole file | 50,971,141 pts over 25 km2, about 2.04 pts/m2 |

SD9947 1 km crop (2,156,427 points, 2.16 pts/m2):

| Class | Count |
| --- | --- |
| 1 unclassified | 5,356 |
| 2 ground | 1,880,853 |
| 3 low vegetation | 93,246 |
| 4 medium vegetation | 83,056 |
| 5 high vegetation | 88,725 |
| 6 building | 5,092 |
| 7 noise | 99 |

- There is a building/vegetation split (contrary to the EA docs), with three vegetation heights.
- Return number 1..5: 2,065,545 / 74,658 / 14,714 / 1,455 / 55. First-return density 2.07 pts/m2.
  Number-of-returns 1..5: 1,990,918 / 119,882 / 39,769 / 5,585 / 273.
- Intensity 2 to 4025 (un-normalised, 16-bit field).
- Ground is 87% of points here (upland/moor), so the 1 km crop is mostly ground; buildings are
  only 0.2%, which suggests few structures in this square (not checked visually).

## Not done

- No check that other 5 km tiles use the same classification scheme or point format.
- Older `lidar_point_cloud` 2016 product not downloaded.
- Vertical datum and OGL text not verified.

Files: LAZ at `.../scratchpad/lidar-spike/x/SD9545_P_10663_20200318_20200319.laz`; inspect
script `.../scratchpad/lidar-inspect.py`.
