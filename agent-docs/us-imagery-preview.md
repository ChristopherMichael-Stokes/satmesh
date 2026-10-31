---
status: current
topic: sources
summary: The seven US test squares (terrain mix, 1 m DEM and EPT lidar verified) and the Esri World Imagery against NAIP comparison on fixed crops: nominal rule results, measured offsets and sharpness, artefacts, the owner's reading and the open per-build imagery selector.
answers: Which seven US squares are the test set and what do they hold; which lidar and DEM project serves each; how do Esri and NAIP compare at each square; why is Esri chosen for the US; what did the owner say about the preview; what would a NAIP adapter cost; where are the preview crops
---

# US test squares and the Esri against NAIP preview

Run 2026-10-30. Review page: <https://claude.ai/artifact/QzeEQDYwh9X9jVVDBZwdf2> (private). Crops and
`manifest.json`: `uncommitted/imagery-preview/` (42 JPEGs; the `_cache/` Esri tile cache stays).
Related: `us-sources.md`, `regions-r1-results.md`, `decisions.md` (imagery row).

## Squares

| Square | Centre lat, lon | EPSG | Terrain | Relief | 3DEP 1 m project | EPT project | Lidar pts/m² | Esri (res, date) | NAIP (res, date) | Nominal rule |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Denver | 39.7480, -104.9950 | 6342 | flat, dense urban | 39 m | CO_DRCOG_2020_B20 | CO_DRCOG_2_2020 (2020-05) | 6.2 | 0.34 m, 2025-09 | 0.3 m, 2023-09 | NAIP |
| Chicago Loop | 41.8810, -87.6300 | 6345 | flat, high-rise | 23 m | IL_4_County_QL1_LiDAR_2016_B16 | USGS_LPC_IL_4County_Cook_2017_LAS_2019 | 32 | 0.31 m, 2025-04 | 0.3 m, 2023-07 | NAIP |
| Plano | 33.0500, -96.7600 | 6343 | flat, suburban | 24 m | TX_Pecos_Dallas_2018_D19 | TX_Pecos_Dallas_B3_2018 (2019-04) | 4.1 | 0.34 m, 2025-04 | 0.6 m, 2022-07 | Esri |
| Portland Forest Park | 45.5500, -122.7600 | 6339 | steep conifer forest and suburb | 286 m | OR_OLCMetro_2019_A19 | OR_OLCMetro_2019 (2019-08) | 29 | 0.34 m, 2025-09 | 0.3 m, 2022-07 | NAIP |
| Ames IA | 42.0300, -93.7300 | 6344 | flat farmland and town | 19 m | IA_NorthCentral_2020_D20 | IA_NorthCentral_2_2020 (2020-04) | 2.6 | 0.0243 m county flight, 2024-03 (leaf-off) | 0.3 m, 2023-09 | Esri |
| Mountain | 39.6200, -105.3000 | 6342 | steep conifer foothills, meadows | 417 m | CO_DRCOG_2020_B20 | CO_DRCOG_2_2020 (2020-06) | 8.2 | 0.31 to 0.34 m, 2023-06 to 2025-07 | 0.3 m, 2023-09 | NAIP |
| Desert | 39.3000, -114.8000 | 6340 | barren alluvial fan with washes | 181 m | NV_EastCentral_2021_D21 | NV_EastCentral_3_D21 (2022-07) | 8.8 | 0.34 m, 2025-06 | 0.6 m, 2022-09 | Esri |

- Rejected candidates: a Utah and a Nevada square (suburban or not open desert), and a New Mexico
  rangeland square (35.20, -107.10) whose only 1 m tile is entirely nodata although the index and
  TNM list it. That square stays as the nodata fall-through test. Spare steep arid square: 37.30,
  -113.40 (UT_FEMA_FS_FlamingGorge_2020_B20, 389 m relief). AZ candidates 33.30, -112.10 and
  32.40, -110.60 had valid DEM windows, imagery unchecked.
- Index coverage was 100 % on every square; the pixels were also 100 % valid on the final seven.
- NAIP scene footprints do not always cover the square (newest centre scene: Chicago 0.87, mountain
  0.93, Denver 0.66 and 0.47 for its two newest): a mosaic is needed.

## Preview: fixed crops

Rule fixed before looking: per square, crop A centred on the square, crop B 500 m east and 500 m
north, each 200 m at 0.15 m/px (bicubic both), plus a 2 km overview at 1 m/px. Offset is the
Esri displacement relative to NAIP by phase correlation at 0.3 m (checked on synthetic shifts,
error under 0.01 m); correlation after the shift below 0.3 means the offset is not trustworthy.
Sharpness is the Laplacian variance at 0.3 m, a rough measure only.

| Square, crop | Esri z | Sharpness Esri / NAIP | Offset E, N (m) | Corr after shift |
| --- | --- | --- | --- | --- |
| Denver A | 20 | 792 / 1013 | +3.3, +4.8 | 0.26 |
| Denver B | 20 | 1648 / 1250 | -2.6, +0.3 | 0.50 |
| Chicago A | 19 | 2943 / 1328 | +10.3, +29.8 | 0.02 |
| Chicago B | 19 | 3276 / 875 | +14.1, +14.1 | 0.00 |
| Plano A | 20 | 2006 / 29 | -0.3, +1.0 | 0.65 |
| Plano B | 20 | 2308 / 26 | -0.9, +1.1 | 0.61 |
| Portland A | 20 | 499 / 122 | +3.0, +9.0 | 0.22 |
| Portland B | 20 | 571 / 230 | -8.4, -7.2 | 0.04 |
| Ames A | 23 | 4950 / 434 | -7.0, +2.8 | 0.31 |
| Ames B | 23 | 4089 / 356 | -20.3, -13.2 | 0.14 |
| Mountain A | 20 | 961 / 892 | -6.2, +0.3 | 0.52 |
| Mountain B | 20 | 1062 / 902 | -3.9, -3.0 | 0.50 |
| Desert A | 19 | 654 / 15 | -0.4, -0.8 | 0.82 |
| Desert B | 19 | 239 / 11 | -0.9, +0.2 | 0.76 |

- Trustworthy offsets (correlation 0.5 or more): Plano 1 m, Desert under 1 m, Denver B 2.6 m,
  Mountain 4 to 6 m. Others are building lean or date differences, not registration.
- Esri is not true-ortho in dense cities: Denver and Chicago roofs lean tens of metres against NAIP.
- NAIP at 0.6 m (Plano, Desert) is enlarged to 0.15 m, so its sharpness figure says nothing.
- Mountain: the Esri source differs between crop A (2023-06-07) and crop B (2025-07-06), visible as
  a tone change.
- Not corrected: WGS 84 against NAD83(2011) grid labelling, up to 1 to 1.5 m in the west; small next
  to Esri's stated 8.47 m accuracy (5 m at Shibam).

## Owner's reading and decisions

- Esri equal or better everywhere except Denver crop A, where it looks poor (softer, Maxar
  enlarged, shadows in another direction).
- Seasonal differences are large: the owner wants a per-build choice of source and capture date or
  season, Esri as default. Texture processing and refinement on the orthophotos goes on the
  roadmap (`TODO.md` Next, two items).
- Esri is the US imagery default (rule: prefer Esri when it is more recent and the gap is small).
  The NAIP adapter and the selector are not approved yet.

## NAIP adapter: cost estimate (not measured)

A window reader returning the raster type the build already takes from the Esri mosaic, scene
merge, reprojection to the tile grid, a general imagery-source record (date, resolution, stated
accuracy; ±6 m for NAIP) in place of the Esri-only fields in the tile plan, node records and
exports, and `--imagery esri|naip` with a year or season request. One focused code task plus a live
Denver build; it touches the tile plan, so it must not run beside other tiler work. Benefits:
Denver A, several NAIP years per site, an open licence, and multi-capture input for the texture
work. Limits: CONUS only, up to 2023, 0.3 to 0.6 m, ±6 m.
Recommended first step: a short read-only check of how many dated Esri releases exist per square
(`TODO.md`: Esri releases, Wayback) and which NAIP years exist; if Esri releases already give
enough seasonal choice, NAIP stays a fallback.
