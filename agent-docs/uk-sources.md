---
status: historical
topic: sources
summary: UK source survey: no open aerial imagery beats Esri z19; finer imagery only locally (EA, NI coast); open 1 m DTM and DSM are the real gain
answers: What open imagery exists for the UK; Is there anything finer than Esri z19 in England or Wales; Which UK DEMs and DSMs are open and how are they accessed; Can APGB or Bluesky imagery be redistributed
---

# UK source survey

Research report, 2026-10-25. `[live]` marks claims observed against live endpoints. Everything else
is metadata or search results and needs a check before it is relied on.

## Conclusions

- No UK nation offers open aerial imagery with a programmatic tile or WMS API that beats Esri z19.
  APGB (Bluesky, Getmapping) 12.5 and 25 cm imagery is public-sector licensed and not
  redistributable.
- Finer open imagery exists only locally: Environment Agency (EA) orthophoto in England (download,
  ECW, project-based) and a 10 cm coastal orthophoto in Northern Ireland (ArcGIS tile cache).
- DEMs are the real UK gain: England and Wales have open 1 m DTM and DSM with programmatic access.

## Imagery

| Source | Coverage | GSD | Access | Licence |
| --- | --- | --- | --- | --- |
| EA vertical aerial photography | England, project-based, 79,607 tiles; 1,900 tiles under 13 cm from 2020 on | 10 to 40 cm, RGB / NIR / RGBN | No OGC service. Index via WFS and OGC API Features [live]; tiles by portal download of ECW in EPSG:27700 | OGL |
| NI 2021 coastal survey orthophoto | NI coastline plus about 200 m inland | 10 cm, natural colour and CIR | ArcGIS tile cache, EPSG:3857, finest level 23 [live], no key | OGL v3 |
| APGB (Bluesky / Getmapping) | UK-wide | 12.5 / 25 cm | WMS for members only | Public-sector licence |
| Sentinel-2 | UK-wide | 10 m | STAC and COG on AWS [live], no key | Copernicus open |

No open orthophoto was found for Scotland or Wales. OS Data Hub offers no open aerial imagery.

## DEMs

| Source | Coverage | Resolution | Access | Notes |
| --- | --- | --- | --- | --- |
| EA LIDAR Composite | England, about 99% | 1 m and 2 m, DTM and DSM (first and last return) | WCS 2.0.1 GetCoverage by bbox to GeoTIFF [live], no key; WMS / WMTS | EPSG:27700, plus or minus 15 cm RMSE absolute, surveys 2000 to 2022 |
| Welsh Government LiDAR 2020 to 2023 | Wales, may not be complete | 1 m DTM and DSM | Country-wide COG on Azure blob, range reads work [live] | DTM 32-bit 48.6 GB, DSM 32-bit 52.1 GB |
| Scottish Remote Sensing Portal | Phases 1 to 6, NLP 2025 to 2027, coastal 2026, Hebrides 2019 | 25 cm to 1 m varies by phase | 10 km tile download via portal; WMS colourised only; WCS disabled [live] | Download API unresolved |
| NI River Basin LiDAR | about 14% of NI | 1 m | Download (search snippets only) | Unverified |
| OS Terrain 50 | GB | 50 m | OS Downloads API [live], no key | OGL |
| Copernicus GLO-30 | Global | 30 m DSM | COG on AWS [live], no key | EGM2008 heights |

## Preference per nation

| Nation | Imagery | DEM | Fallback |
| --- | --- | --- | --- |
| England | EA aerial where an index tile covers the AOI, else Esri | EA composite 1 m | OS Terrain 50, then GLO-30 |
| Scotland | Esri | Scottish lidar tiles where a phase covers the AOI | OS Terrain 50, then GLO-30 |
| Wales | Esri | Welsh Government 1 m COG | EA composite near the border, OS Terrain 50, GLO-30 |
| Northern Ireland | NI coastal orthophoto in the coastal strip, else Esri | NI River Basin or coastal lidar where present | OSNI 50 m, GLO-30 |

## Unverified

The EA aerial download, tile size and ECW decode are resolved in `s6-results.md`.

- Scottish tile download API and per-phase resolutions.
- Wales COG CRS, nodata, 16-bit encoding and accuracy.
- NI River Basin coverage and download, whole-country 10 m DTM licence, coastal DTM resolution.
- Rate limits of every service, the EA tile API included.
