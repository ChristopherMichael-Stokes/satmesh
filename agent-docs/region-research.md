---
status: current
topic: sources
summary: Middle East and Yemen source survey: no open high-resolution lidar or DTM; Yemen has Vantor imagery and GLO-30; scoring needs DEM agreement or ICESat-2
answers: What elevation data is open for Yemen; Is there lidar or a national DTM in the Middle East; How can height quality be scored without a reference; How do I fetch Copernicus GLO-30 for Yemen; What imagery zoom does Esri have in Yemen
---

# Region research: Middle East and Yemen sources

Survey by a research subagent, 2026-10-26, research use. VERIFIED means the page was opened or the
endpoint queried; UNOPENED means a search snippet only, and no numbers are taken from those.

## Conclusions

- No open high-resolution reference (lidar, national DTM or photogrammetric DSM) was found for
  Yemen, the Gulf states, Jordan, Turkey, Egypt, Lebanon or Iraq. Absence of search hits is not
  proof of absence. The only open patch is a Dead Sea lidar cloud in Israel.
- Yemen imagery is high zoom: every Yemeni point queried has Vantor (ex-Maxar) 0.31 to 0.46 m
  polygons dated 2019 to 2025. Elevation is limited to 30 m surface models.
- Scoring in Yemen has to come from agreement between DEMs (GLO-30, ALSO, NASADEM, FABDEM),
  degraded-GLO-30 tests, or ICESat-2 ATL08 and GEDI footprints. ATL08 is sub-metre on flat bare
  terrain per a Finland study and a 2026 review; no desert validation was found.
- Copernicus GLO-30 covers Yemen on a no-account S3 bucket (tile
  `Copernicus_DSM_COG_10_N15_00_E044_00_DEM` returned HTTP 200; 73 tiles in N12 to N18, E042 to
  E054). VERIFIED by curl.
- Ellipsoidal height works: PROJ's EGM2008 and EGM96 grids are on cdn.proj.org and were sampled.

## Elevation sources

| Source | Res. | Surface | Vertical accuracy (as stated) | Licence | Programmatic access | Datum | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Copernicus GLO-30 | 1" (30 m) | DSM | absolute under 4 m LE90; relative under 2 m (slope up to 20 %), under 4 m steeper; horizontal under 6 m CE90 | Copernicus licence; DLR/Airbus notice | `s3://copernicus-dem-30m` (eu-central-1, `--no-sign-request`), COG, `tileList.txt` | EGM2008 (EPSG:3855) | VERIFIED: COP-DEM page, AWS registry, bucket readme |
| Copernicus GLO-90 | 3" (90 m) | DSM | same family | same | `s3://copernicus-dem-90m`, tile exists for Yemen | EGM2008 | VERIFIED |
| SRTM 1" | 30 m | DSM (C-band) | not retrieved | public domain per OpenDEM | OpenTopography (key) or NASA | EGM96 (not from an opened source) | UNOPENED |
| NASADEM | 1" | DSM, reprocessed SRTM | no numbers on page | NASA open, citation requested | Earthdata login or OpenTopography | geoid unnamed | VERIFIED page |
| ALSO AW3D30 | 30 m | DSM | none on page | free incl. commercial, JAXA terms | JAXA account; OpenTopography (key) | "height above sea level" | VERIFIED page; 5 m commercial product unchecked |
| FABDEM V1-2 | 1" (30 m) | bare earth (GLO-30 with ML building and forest removal) | none official; independent 5.56 m overall (secondary); ranked first against 65 lidar sites (Meadows 2024) | CC BY-NC-SA 4.0 | Bristol repository (COG), GEE `projects/sat-io/open-datasets/FABDEM` | not stated | VERIFIED GEE page; Bristol page timed out |
| TanDEM-X 90 m | 3" | DSM | mission LE90 under 10 m | scientific use only | DLR account | WGS84 ellipsoidal | VERIFIED |
| TanDEM-X EDEM, ASTER GDEM | | | | | | | not retrieved |
| OpenTopography global DEMs | per product | per product | | per product | free API key; 30 m datasets 450,000 km2 per request, 50 calls a day non-academic, 200 academic | per product | VERIFIED |
| Dead Sea shoreline, Ze'elim fan (Israel) | about 8 points/m2 | LAS cloud, small | n/a | CC BY 4.0 | open download, 84 MiB | CRS and datum not stated | VERIFIED (TU Wien record); extent not given |
| National or city lidar and DTM (Israel, Turkey, UAE, Saudi, Jordan, Qatar, Egypt, Yemen) | | | | | none found open | | |
| Yemen heritage 3D surveys (Marib dam, Sirwah, Sana'a old city by UNESCO/ICONEM 2018) | | | | | reports exist, no open data seen | | UNOPENED |

GLO-30 country restrictions (Armenia, Azerbaijan, Moldova) were lifted in release 2023_1.

## Ellipsoidal heights

- The PROJ CDN serves `us_nga_egm08_25.tif` (80.6 MB, world) and `us_nga_egm96_15.tif` (2.7 MB,
  world). VERIFIED by HTTP 200.
- Network grid fetch exists from PROJ 7.0 (`https://cdn.proj.org`, `PROJ_NETWORK_ENDPOINT`,
  needs libcurl and network enabled). pyproj-specific settings not checked (pipeline has pyproj
  3.8.0).
- Geoid height N in metres, EGM2008 against EGM96, sampled from the CDN grids:

  | Place | N2008 | N96 | Difference |
  | --- | --- | --- | --- |
  | Sana'a | -4.98 | -4.85 | -0.13 |
  | Aden | -14.80 | -15.13 | +0.33 |
  | Shibam | -18.35 | -19.07 | +0.72 |
  | Marib | -10.88 | -9.83 | -1.05 |
  | Mukalla | -20.26 | -19.97 | -0.28 |
  | Dubai | -34.14 | -33.87 | -0.26 |
  | Riyadh | -7.53 | -7.98 | +0.44 |
  | Muscat | -28.09 | -27.53 | -0.56 |
  | Amman | 20.86 | 20.92 | -0.06 |
  | Istanbul | 37.34 | 37.43 | -0.09 |
  | Cairo | 15.33 | 15.43 | -0.10 |

  The two models differ by about 1 m or less. No national geoid models were looked for.

## Esri World Imagery (queried live, layer 4)

`SRC_ACC` is Esri's stated accuracy in metres, confidence level undocumented. The service has
levels 0 to 23; below z12 it is 15 m Earthstar TerraColor.

| Place | Resolution m | Date | Cached max z | SRC_ACC m |
| --- | --- | --- | --- | --- |
| Sana'a old city | 0.31 | 2025-12-29 | 19 | 8.47 |
| Sana'a north | 0.34 | 2025-12-13 | 19 | 8.47 |
| Shibam (Hadramawt) | 0.31 | 2025-01-07 | 18 | 5 |
| Seiyun, Tarim | 0.34, 0.31 | 2025-03 and 2025-07 | 18 | 5 |
| Aden | 0.46 | 2019-12-29 | 19 | 4.23 |
| Marib city and dam | 0.34 | 2025-02-08 | 18 | 5 |
| Mukalla | 0.31 | 2019-08-25 | 19 | 10.16 |
| Taiz, Hodeidah | 0.31 | 2024-02, 2024-01 | 19 | 5 |
| Zabid, Thula, Kawkaban, Socotra | 0.31 to 0.34 | 2025 | 18 | 5 |
| Dubai, Abu Dhabi, Doha, Riyadh, Jeddah | 0.31 to 0.50 | 2025-11 to 2026-01 | 19 | 8.47 |
| Muscat, Kuwait, Manama, Baghdad | 0.5 | 2025 to 2026 | 19 | 8.47 |
| Amman, Tel Aviv, Beirut | 0.5 | 2021, 2023, 2024 | 19 | 8.47 |
| Istanbul, Ankara, Cairo | 0.34 to 0.46 | 2025 to 2026 | 19 | 8.47 |
| Rub al Khali (empty desert) | 0.34 | 2025-04-30 | 17 | 5 |

- At 15 N, z18 is about 0.55 m/px and z19 about 0.28 m/px, so 0.31 m imagery is fully resolved
  only at z19. Where the cache stops at z18 (Shibam, Marib, Seiyun), tiles are 0.55 m/px sampled
  from 0.31 to 0.34 m sources. Behaviour past the cache was not tested.
- Source labels read "Vantor".

## Position accuracy

- Esri blog 2019: third-generation Vivid 4 m CE90, previously 10 m. Maxar 2020: Vivid Standard 5 m
  CE90. Both UNOPENED snippets.
- Live `SRC_ACC` values (4.23 to 10.16 m) are the only per-polygon figures found.
- No published ground-control comparison for Yemen or the Middle East was found. ICESat-2 or GEDI
  footprints on a distinctive feature are a possible check.

## Datum

- UTM central meridians: zone 37 39 E, 38 45 E, 39 51 E, 40 57 E.
- Yemen: Sana'a, Aden, Marib, Taiz, Hodeidah, Zabid, Thula, Kawkaban in 38N (EPSG:32638); Shibam,
  Seiyun, Tarim, Mukalla in 39N (EPSG:32639); Socotra on the 39/40 boundary; the far east reaches 40N
  (EPSG:32640).
- WGS84 UTM suffices since the sources are WGS84-based. National grids (ITM, Qatar National Grid)
  not looked up.

## Candidate 2 x 2 km sites, Yemen first

1. Sana'a old city (44.207 E, 15.355 N, UTM 38N). 0.31 m, 2025-12-29, cached to z19. Dense
   multi-storey mud-brick buildings: GLO-30 shows building bumps and FABDEM should remove them, a
   direct refinement test. SRC_ACC 8.47 m.
2. Shibam Hadramawt (48.627 E, 15.927 N, UTM 39N). 0.31 m, 2025-01-07, cached to z18 only. Tall
   mud towers in a wadi with clean desert and cliff around. SRC_ACC 5 m.
3. Marib (45.32 E, 15.46 N, UTM 38N). 0.34 m, 2025-02-08, cached to z18. Ancient dam, wadi and
   desert plateau. SRC_ACC 5 m.

None has an open reference; stand-ins are DEM agreement and degraded-GLO-30. Outside Yemen, the Dead
Sea shoreline lidar near Ze'elim is the only open reference found; Gulf cities have the freshest
imagery (cached to z19) but no reference.

## Open questions

- Extent, CRS and vertical datum of the Ze'elim lidar; the Esri polygon there.
- The Bristol FABDEM page and any no-account bulk download.
- ASTER GDEM, SRTM, JAXA 5 m details and national grids.
- Whether Esri tiles past the cache ceiling are upsampled.
- Maxar Open Data events (CC BY-NC 4.0, snippet only) list Turkey, Libya, Morocco and Sudan; none
  for Yemen or the Gulf.
