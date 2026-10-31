---
status: current
topic: sources
summary: Verified survey of open US elevation, point-cloud and imagery sources for the contiguous US: 3DEP 1 m DEM COGs (91 % of CONUS), EPT point clouds for a first-return DSM, NAIP, datums and licences.
answers: Which US sources give a 1 m bare-earth DEM; how do I get a first-return DSM in the US; how do I fetch NAIP without an account; which geoid and CRS chain converts NAVD88 to ellipsoidal heights; what are the licences; which 2 km squares suit tests
---

# US sources

Survey by a research subagent, 2026-10-30. V means the endpoint was queried or the page opened,
U means a search snippet only (no numbers taken from U). Scripts are in the survey session's
scratchpad and are not kept; the commands below repeat the key checks.

## Elevation and point clouds

| Source | Access | Resolution and surface | Datum | Status |
| --- | --- | --- | --- | --- |
| 3DEP 1 m DEM, per project | TNM Access API finds COGs on `prd-tnm` S3, then range reads | 1 m bare earth, 10 km tiles (~250 MB); 200 m window in 1.8 s | NAD83 UTM (EPSG:269xx); NAVD88 in metadata | V |
| 3DEP ImageServer `exportImage` | `https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage` | best available to 1 m; max 8000 px; matched the 1 m COG to 0.01 m | catalog `VerticalDatum` per source | V |
| 3DEP 1/3″ and 1″ seamless | COGs `.../Elevation/13/TIFF/current/n40w105/USGS_13_n40w105.tif` | ~10 m, ~30 m bare earth | NAD83 + NAVD88 | V |
| EPT point clouds | `https://s3-us-west-2.amazonaws.com/usgs-lidar-public/{PROJECT}/ept.json`; project index `hobuinc/usgs-lidar` `resources.geojson` | LAZ nodes, ASPRS classes, GpsTime per point (acquisition date); Denver window 5.4 pts/m² | EPSG:3857 horizontal, Z orthometric | V |
| USGS LPC tiles | `rockyweb.usgs.gov` (TNM `downloadURL`) | LAS 1.4 | compound CRS, NAVD88 Geoid18 | V; HTTP 429 on a 2026 project |
| Planetary Computer `3dep-lidar-dsm`, COPC | STAC plus SAS token | 2 m DSM; COPC | no vertical adjustment | V; 2012 to 2022 only |

- USGS has no national 1 m first-return DSM product. The DSM must be built from EPT points
  (first returns, noise classes dropped), as the EA DSM is.
- 1 m coverage: 91.1 % of CONUS area (water inside state polygons inflates the denominator). Low
  states: MI 61 %, OR 68 %, RI 73 %, MT 74 %, NC 76 %, AZ 76 %, WA 77 %, FL 79 %. A Raleigh-area
  square had no 1 m DEM and no EPT project.
- EPT lags new projects (Portland 2024 is missing). Coverage test: index layer
  `https://index.nationalmap.gov/arcgis/rest/services/3DEPElevationIndex/MapServer/1`.
- ImageServer `/query` ignores geometry unless `spatialRel=esriSpatialRelIntersects` is set.

## Imagery

| Source | Access | Resolution | Licence | Status |
| --- | --- | --- | --- | --- |
| NAIP on Planetary Computer | STAC search, anonymous SAS token, COG range read | 0.3 to 1.0 m RGBN, years 2010 to 2023 | "Use_Constraints: None", credit requested | V |
| NAIP on AWS | `naip-*` buckets | same | public domain with attribution | V: requester pays, anonymous denied |
| Esri World Imagery | same tile service as Great Britain; layer metadata `/{layer}/query` | US cities 0.31 to 0.5 m satellite at z19; some county and state orthos 15 cm | Esri Master License Agreement, no offline tile export; owner decided research use is acceptable (`decisions.md`) | V |
| State orthos | MassGIS 15 cm 2019, NYS 2022 to 2025 | 15 cm | licences not checked | V service descriptions |

- NAIP stated position accuracy: ±6 m to ground (2019 metadata), confidence level not stated.
- No anonymous NAIP source for 2024 or later was found.
- Esri `SRC_ACC` of 8.47 m appears for Vantor sources; units and confidence undocumented.

## Datums

- Orthometric to ellipsoidal: EPSG:6349 (NAD83(2011) + NAVD88) to EPSG:6319 with grid
  `us_noaa_g2018u0.tif` (16.7 MB on cdn.proj.org), accuracy 0.015 m; Denver N = -17.10 m.
- Use the explicit two-step chain. PROJ's direct EPSG:6349 to EPSG:4979 picks a GEOID03 and HARN
  pipeline (0.05 m different), and EPSG:6319 to 4979 is a no-op with 2 m accuracy. NAD83(2011) to
  WGS 84 (G2139) is a time-dependent Helmert (EPSG:9755); at Denver, epoch 2025.0, it moves the
  height by -0.86 m.
- Projected CRS: NAD83(2011) / UTM, EPSG:6339 to 6348 for zones 10N to 19N. Alaska 6330 to 6338,
  the GEOID12B Alaska grid; Hawaii NAD83(PA11) UTM EPSG:6634 and 6635, the GEOID12B Hawaii
  grid (both on cdn.proj.org). The ImageServer labels Honolulu sources NAVD88, which is not
  defined in Hawaii: read the project metadata.
- PROJ network access is off by default: set `PROJ_NETWORK=ON` or install the grid.

## Licences

USGS 3DEP: no use limits, credit appreciated, modifications must be described, no endorsement. NAIP:
none, credit requested. No ML-use restriction found for either. Esri: see the owner's decision;
Planetary Computer terms were not read.

## Candidate 2 km squares (100 % 1 m DEM index coverage)

| Site | Centre (lat, lon) | Cover | 3DEP project (acquired) | NAIP (PC) |
| --- | --- | --- | --- | --- |
| Denver downtown | 39.7480, -104.9950 | dense urban | CO_DRCOG_2020_B20 (2020-05 to 2021-03) | 2023, 0.3 m |
| Chicago Loop | 41.8810, -87.6300 | high-rise | IL_4_County_QL1_LiDAR_2016_B16 (2017-04 to 05) | 2023, 0.3 m |
| Plano TX | 33.0500, -96.7600 | suburban | TX_Pecos_Dallas_2018_D19 (2019-01 to 07) | 2022, 0.6 m |
| Portland Forest Park | 45.5500, -122.7600 | forest and suburb | OR_OLCMetro_2019_A19 (2020); EPT has 2019 only | 2022, 0.3 m |
| Ames IA | 42.0300, -93.7300 | farmland and town | IA_NorthCentral_2020_D20 (2020-04 to 12) | 2023, 0.3 m |

Lidar to imagery gaps run 0 to 6 years; building and tree change contaminates labels at the long
ones. Spare: Seattle Capitol Hill 47.6200, -122.3200 (WA_KingCounty_2021_B21).

## Open

Land-only coverage share; a current NAIP source for 2024 or later; NAIP accuracy confidence level;
rate limits (rockyweb 429, others none seen); state ortho licences; Esri ML-training clause.

## Commands

```text
curl -s -G https://tnmaccess.nationalmap.gov/api/v1/products \
  --data-urlencode "datasets=Digital Elevation Model (DEM) 1 meter" \
  --data-urlencode "bbox=-105.00,39.74,-104.99,39.75" --data-urlencode max=5
curl -s -o ex.tif -G \
  https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage \
  --data-urlencode "bbox=500000,4399000,500400,4399400" --data-urlencode bboxSR=26913 \
  --data-urlencode imageSR=26913 --data-urlencode size=400,400 --data-urlencode format=tiff \
  --data-urlencode pixelType=F32 --data-urlencode f=image
curl -s https://s3-us-west-2.amazonaws.com/usgs-lidar-public/CO_DRCOG_2_2020/ept.json
curl -s https://planetarycomputer.microsoft.com/api/sas/v1/token/naip
PROJ_NETWORK=ON python -c "from pyproj import Transformer; print(Transformer.from_crs('EPSG:6349','EPSG:6319',always_xy=True).transform(-104.995,39.745,1600.0))"
```
