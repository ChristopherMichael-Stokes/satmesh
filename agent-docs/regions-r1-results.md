---
status: current
topic: baseline-pipeline
summary: R1 results: the US 3DEP path (1 m DEM through TNM with a nodata remedy chain, DSM from EPT first returns, GEOID18 plus dated Helmert) builds Denver, a mountain and a desert 2 km square; DEM matches the ImageServer to 0.01 m, DSM matches the 2 m Planetary Computer DSM on bare ground to 0.09 m; traps found.
answers: What did R1 build and how was it checked; how far is the US DEM from the ImageServer and the DSM from the Planetary Computer DSM; which datum does USGS EPT use; how long do US builds take; what fraction of DSM cells is empty; which US traps exist; what was not checked
---

# Regions R1 results: US 3DEP build

Run 2026-10-30. Plan: `regions-plan.md` (R1 row); sources: `us-sources.md`. Code in
`satmesh-core` (georef chain), `satmesh-data` (`usgs_dem.py`, `ept_dsm.py`, registry entry
`usgs-3dep`), node record field `elevation_provenance` in `satmesh-tiles`. Scratch builds:
`uncommitted/regions/us-denver/` (`store-final`, `export/`), `us-mountain/`, `us-desert/`, each
with its own `cache/` and `build*.log`.

## What changed

- `registry.toml` entry `usgs-3dep` (12 overlapping CONUS boxes, before GLO-30). DTM from the
  1 m project COGs the TNM API lists, tiles of the DSM's lidar year first; then small holes
  interpolated; then the ImageServer; then the 1/3 arc-second COGs; a remaining hole raises with
  the window name, sources tried and nodata fraction. DSM: highest first return per pixel of the
  DTM grid from the newest EPT project covering the window; noise (7, 18) and withheld dropped.
- Rasters are written on a 1 m grid in the NAD83(2011) UTM zone of each window (`EPSG:6339` to
  `6348`), heights `EPSG:634x+5703`. Node records carry `elevation_provenance`.
- Hole interpolation thresholds (owner's tunable, `usgs_dem.py`): `SMALL_HOLE_MAX_FRACTION` 0.001
  of the window, `SMALL_HOLE_MAX_ACROSS_M` 5 m (smallest enclosing circle), GDAL `fillnodata` with
  a 6 px search.

## Measurements

| Square | Centre | Nodes (leaves) | Build, cold cache | Peak RSS | DTM relief | First returns per m² (leaf median, range) | DSM cells filled from DTM (mean, worst leaf) | Capture dates (GpsTime) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Denver downtown | 39.7480, -104.9950 | 426 (324 at z18) | 8 min 02 s | 2.7 GB | 39.8 m | 3.28 (1.96 to 6.40) | 2.4 %, 29 % | 2020-05-27 |
| Mountain | 39.6200, -105.3000 | 440 (342 at z18) | about 10 min (two runs, see traps) | 1.3 GB | 429.7 m | 5.82 (2.63 to 8.83) | 2.9 %, 9.4 % | 2020-06-05 to 06-12 |
| Desert | 39.3000, -114.8000 | 124 (100 at z17) | 3 min 42 s | 1.6 GB | 222.0 m | 8.44 (5.00 to 11.57) | 0.02 %, 0.55 % | 2022-07-06 |
| Plano | 33.0500, -96.7600 | 383 (306 at z18) | about 10 min (Esri at 30 requests/s) | not logged | not logged | not logged | 1.1 % | 2019-04 (EPT name) |
| Portland Forest Park | 45.5500, -122.7600 | 499 (400 at z18) | about 34 min | not logged | not logged | not logged | 0.4 % | 2019 (EPT name) |

- Relief is over the built area (leaf extent plus a 5 m margin), so it exceeds the 2 km square's.
- Every DEM window of the three squares came from one 1 m project at 100 %: Denver and mountain
  `CO_DRCOG_2020_B20` (the mountain square also lists `CO_ArapahoRooseveltPikeNF_D23`; the year
  preference kept the 2020 flight), desert `NV_EastCentral_2021_D21`. No hole was interpolated.
- Geoid: GEOID18 N at Denver -17.10 m (PROJ grid sample). The node records hold ellipsoidal minus
  NAVD88 of -17.92 m: N plus the Helmert's -0.86 m at epoch 2025.0 (PROJ's direct 6349 to 4979
  route lacks that 0.86 m).
- DEM against the ImageServer `exportImage` on the same 217 x 277 m grid at Denver: max |diff|
  0.010 m, mean 0.000 m, best integer shift zero; identical when requested in EPSG:6342 or 26913.
  The 1/3 arc-second COG on that grid: bias -0.01 m, RMSE 0.26 m.
- DSM against the Planetary Computer `3dep-lidar-dsm` 2 m (only item there:
  `USGS_LPC_CO_SoPlatteRiver_Lot5_2013_LAS_2015`, flown 2013-10 to 2014-05) over the Denver build,
  our 1 m DSM taken as 2 m block maxima: 904,180 cells, bias +1.83 m, median -0.01 m, RMSE 15.5 m,
  p5 -7.4 m, p95 +17.0 m; best integer shift zero. Where both are bare ground (each within 0.3 m
  of the DTM): bias -0.05 m, RMSE 0.09 m. The large RMSE is downtown building change between
  2013/14 and 2020 and roof edges at 2 m; the ground agreement shows datum and grid agree.
- EPT datum, measured: class-2 points of `CO_DRCOG_2_2020` against the 1 m DEM on slopes over 0.3:
  RMSE 0.43 m at zero shift when EPT Web Mercator is read as NAD83(2011) latitude and longitude
  with no datum shift; read as WGS 84 (Helmert applied) the fit needs a (-1.25, +0.75) m shift.
- New Mexico fall-through (35.20, -107.10): TNM lists only `NM_NRCS_MiddleRioGrande_2017_D18`,
  whose tile is nodata over three sampled leaf windows; each window fell through to the
  ImageServer at 1.0 m (identify: served primary raster LowPS 1), 100 % share. EPT project there:
  `NM_MRCOG_B1_2018`.
- Exports at Denver: `export glb` 10 s (249 MB, 324 meshes, 4.94 M vertices), `3dtiles` 2 s,
  `gazebo` 2 s; GLB for the mountain (11.2 M vertices) and desert (0.77 M) squares.

## Traps

- Ames: Esri serves a 0.0243 m county flight there (z23, capped by the build at z21): the 2 km
  square plans 20,736 leaves at z21 and up to 331,776 Esri tiles (about 185 min of fetching at 1
  per second; the build ran at 30), and built about 1,900 nodes in the first 33 min. Not finished;
  waits on the owner (imagery zoom cap for this square).
- A DSM window cached by an early attempt without the `DSM_PROVENANCE` tag makes
  `read_dsm_provenance` raise `KeyError` on a later build that shares the cache (seen with the
  default cache at Denver).
  `make smoke-regions` uses its own cache directory; the old files stay.
- The TNM API answers some requests with status 200 and `{"error": ...}` or
  `{"errorMessage": "Search ... return fewer results"}`; the same request then succeeds. Treated
  as retryable.
- A listed 1 m tile can be entirely nodata (New Mexico); index coverage does not imply pixels.
- 1 m tiles are labelled NAD83 UTM (`EPSG:269xx`), not NAD83(2011); origins carry float fuzz
  (`4400005.999985854`). Read as NAD83(2011) unchanged; the DEM agreed with EPT ground at zero
  offset.
- EPT project names do not always carry a four-digit year (`NV_EastCentral_3_D21`), so the year
  preference for the DTM does nothing there; capture there was 2022-07-06 though the name says
  21. Names with a year can still differ from the DEM project name (`CO_DRCOG_2_2020` against
  `CO_DRCOG_2020_B20`).
- Parallel leaf fetches share EPT nodes; two writers to one `.part` file crashed the first
  mountain run. Each download now writes its own partial file.
- EPT nodes are LAS 1.2 point format 1 with a `ClassFlags` extra byte carrying the LAS 1.4
  withheld flag; class 18 fits the 5-bit field.
- Denver downtown has leaf windows with up to 29 % of 1 m cells without a first return (glass,
  water, shadowed courtyards at 2 to 3 returns per m²); those cells show the DTM.

## Not checked

- Any of the US meshes by eye in Blender.
- Ames and Chicago squares (in progress, see Traps); Plano and Portland by
  eye; Alaska and Hawaii (no registry entry).
- The ImageServer resolution is read at the window centre only.
- Exporters do not yet carry the provenance or the USGS attribution into the 3D Tiles, GLB or
  Gazebo outputs.
