# S6 results: EA vertical aerial photography versus Esri z19

Run 2026-10-25. Part A is the index coverage, part B a pixel comparison on one EA tile. `[live]`
marks what was observed against endpoints.

## Conclusions

Correction (F6, `f6-results.md`): the 2.4 m offset below is not reproduced. Reprojecting Esri
through rasterio's GDAL, which has no OSTN15 grid, adds a 1.6 m Helmert error; with OSTN15 the Esri
imagery is 0.8 to 1.0 m north of EA at two sites. The imagery coverage and detail findings stand.

- EA daytime imagery covers about 24,900 km2 of England in some year, about a fifth of the
  country. Only about 7,000 km2 has a capture from 2020 on, and 1,100 km2 of that is at 10 to
  12.5 cm.
- Where it exists, EA is finer than Esri at every site checked. Esri `SRC_RES` is 0.34 to 0.5 m,
  while EA offers 10 cm from 2020 to 2024. That is 3 to 5 times finer than the source Esri resamples
  to z19 (about 0.17 m/px on the tile grid).
- At 4 of the 7 S1 England sites EA has nothing. The other 3 have only old 20 to 40 cm captures
  (2008 to 2013). For a randomly placed AOI, Esri stays the default and EA is the exception.
- Some blocks have many captures. A 216 km2 block in Holderness has 21 EA captures from 2008 to
  2024, which matters for E6 multi-capture super-resolution.
- The finer GSD is real detail. On a 300 m crop at Upper Aire, EA 2020 at 10 cm resolves branches,
  track edges and tussocks that Esri at 0.34 m smears. EA carries 2 to 3 times Esri's fine-scale
  power at periods of 0.35 to 4 m, and keeps resolving detail down to about 0.2 m, past Esri's z19
  Nyquist.
- The two sources are offset by about 2.4 m on that crop, which matters for any mosaic that mixes
  them (F3, E2) and for E6 registration.
- England gets an EA imagery entry in the source registry. It is worth the ECW cost only where an
  index tile at 25 cm or finer covers the AOI.

## Index

- The live index is the source of truth: WFS `Vertical_photography_index_catalogue` at
  `https://environment.data.gov.uk/spatialdata/survey-index-files/wfs`. It returns 79,607 features
  in EPSG:27700, and the full fetch takes 8 pages of 10,000 [live].
- The bulk GeoPackage (dataset `ff38d68e-dd00-4c1c-b414-0944205baea6`) has 73,198 rows, so it lags
  the live index.
- Fields:
  - `resolution`: GSD in metres.
  - `year`: a string.
  - `sd_flown` / `ed_flown`: capture dates.
  - `type`: RGB, RGBN, IRRGB, IRRGBN or NightTime.
  - `os_ref_5k`: the download tile id.
- `type` is null on 3,198 rows from 2023 to 2024. Their `meta_split` (for example `RGBN_2023_20cm`)
  still carries the type.
- `event_05k` can disagree with `year`, so use `year`.
- Footprints are 1 km at 10 cm and 2 km at 40 cm. There is no download link field.

## Coverage

Areas are the union of daytime footprints (RGB, RGBN, IRRGB, IRRGBN), in km2. Night-time captures
are excluded. England is about 130,000 km2.

| GSD class | All years | 2020 on |
| --- | --- | --- |
| 10 to 12.5 cm | 7,743 | 1,143 |
| 13 to 25 cm | 20,520 | 6,191 |
| 40 cm to 1 m | 2,017 | 0 |
| Any daytime | 24,935 | 6,971 |

The finest GSD each year is 10 cm in every year except 2022 and 2025, when it is 20 cm. Area flown
per year is 650 to 7,900 km2 and mostly 20 cm RGBN. Surveys are project-based: river corridors,
coasts and floodplains.

## England S1 sites

| Site | Esri `SRC_RES` m, date | EA at the point |
| --- | --- | --- |
| London | 0.31, 2025-08 | RGB 2008 0.4 m; night 2012 0.2 m |
| Manchester | 0.46, 2020-04 | none |
| Norfolk fens | 0.5, 2023-06 | none |
| Peak District | 0.34, 2025-04 | none |
| Lake District | 0.5, 2025-05 | IRRGB 2009 0.2 m |
| Cornwall coast | 0.34, 2025-09 | RGBN 2011 and 2013, 0.2 m |
| Northumberland | 0.31, 2021-04 | none |

## Sites where EA is finest

The six largest connected blocks of 10 to 12.5 cm daytime coverage from 2020 on, with Esri at an
interior point. All of them reach Esri z19.

| Point (lon, lat) | Block km2 | EA captures | Esri source, `SRC_RES` m, date |
| --- | --- | --- | --- |
| -0.7794, 53.2702 (Trent vale west of Lincoln) | 412 | IRRGB 2012 0.25; RGBN 2024 0.1 | Vivid, 0.5, 2022-08 |
| -0.1235, 53.8640 (Holderness) | 216 | 21 captures 2008 to 2024, 0.1 to 0.2 | Vivid, 0.5, 2025-07 |
| -1.2058, 53.7233 (Lower Aire) | 177 | IRRGB 2007 0.15; RGBN 2020 0.1 | Vivid Advanced, 0.5, 2022-07 |
| -2.0015, 53.9236 (Upper Aire) | 147 | RGBN 2020 0.1 | Vivid, 0.34, 2025-03 |
| -2.9227, 51.1062 (Somerset Levels) | 109 | IRRGB 2012 0.25; RGBN 2020 0.1 | Vivid, 0.34, 2025-06 |
| -2.8164, 51.5565 (Severn shore) | 62 | RGBN 2016, 2017, 2018, 2021, all 0.1 | Vivid, 0.5, 2025-08 |

## Download [live]

The download needs two unauthenticated calls:

1. POST a WGS84 GeoJSON polygon to
   `https://environment.data.gov.uk/tiles/collections/survey/search`. Filter the results to
   `product.id` starting `vertical_aerial_photography`.
2. GET `https://environment.data.gov.uk/tiles/collections/survey/{product}/{year}/{res}/{tile_id}`,
   which returns a zip of ECW files for one 5 km OS grid square.

- The response is chunked with no Content-Length, and HEAD returns 405. Downloads need a streaming
  byte cap.
- One 2008 0.4 m RGB tile is 484 MB zipped (12 ECWs). A 10 cm tile will be several times larger.
- A tile zip streams through `funzip`, which extracts the first ECW and closes the pipe, so one 1 km
  ECW costs only its own size (17 MB for a 2020 10 cm RGBN file).

## ECW decode

- No apt package and no pip wheel carries the GDAL ECW driver. Ubuntu, UbuntuGIS and Debian dropped
  it because the SDK is proprietary. The rasterio wheel and the official GDAL Docker images omit it.
- `docker/gdal-ecw/Dockerfile` (`make gdal-ecw-image`) builds a minimal GDAL 3.13.3 with the ECW
  driver against libecwj2 3.3. It reads the EA files. The image is 552 MB and builds in about
  3 minutes on 16 cores.
- SDK 3.3 reads ECW version 2 only. The 2008 and 2020 EA files are both `VERSION=2` [live].
- The 2020 files georeference as EPSG:27700. The 2008 files carry an unnamed OSGB36 Transverse
  Mercator CRS, which needs assigning EPSG:27700.
- RGBN files have 4 bands with `ColorInterp=Undefined`. Band 4 is NIR (mean 119 against 52 to 64 for
  bands 1 to 3), and bands 1 to 3 are RGB by visual check.
- ECW stays outside `pipeline/`: F2b converts tiles to GeoTIFF in the container, and the pipeline
  reads only GeoTIFF.

## Pixel comparison

- Site: a 300 m square in EA tile SD9545, BNG 398350 to 398650 E, 448350 to 448650 N, near Skipton.
  EA RGBN 2020 at 0.1 m against Esri Vivid 2025-03 (`SRC_RES` 0.34 m) at z19, which is 0.176 m
  ground pixel at this latitude.
- Method: the radially averaged power spectrum of Rec. 709 luma, with a Hann window, binned by
  ground frequency up to each image's Nyquist. Each spectrum is divided by its mean power at 0.05
  to 0.25 cycles/m (periods 4 to 20 m) to cancel date and contrast differences between captures.

| Band cycles/m | Period m | Esri / EA power |
| --- | --- | --- |
| 0.25 to 0.5 | 2 to 4 | 0.51 |
| 0.5 to 1.0 | 1 to 2 | 0.31 |
| 1.0 to 1.5 | 0.67 to 1 | 0.46 |
| 1.5 to 2.85 | 0.35 to 0.67 | 0.46 |
| 2.85 to 5.0 | 0.2 to 0.35 | EA only; Esri has no data past its Nyquist |

- EA's spectrum falls steeply only above about 4.5 cycles/m, so detail holds to about 0.22 m.
- A 40 m side-by-side view of the busiest block confirms it: EA shows single branches and fence-line
  edges, while Esri shows soft blobs.
- Offset: phase correlation (`skimage.registration.phase_cross_correlation`, upsampled 10 times)
  puts Esri about 0.8 m south and 2.3 m west of EA, with error 0.31. This is one crop with
  different leaf-on states and shadows, so treat it as indicative.
- Limits:
  - One site, one season pair.
  - Part of the power gap comes from scene changes between 2020 and 2025 rather than resolution.
