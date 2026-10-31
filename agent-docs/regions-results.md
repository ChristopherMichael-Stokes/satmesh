---
status: current
topic: baseline-pipeline
summary: R0 results: the build runs outside Great Britain through a source registry; Sana'a and Shibam build from a cold cache with GLO-30 surface and FABDEM ground, EGM2008 heights check to 2 cm, and the traps found.
answers: What did R0 build and how was it checked; which Yemen squares were built and how long did they take; how do GLO-30 and FABDEM compare at Sana'a; what traps affect GLO-30 and FABDEM access; what was not checked
---

# Regions R0 results: Middle East build

Run 2026-10-30. Plan: `regions-plan.md`; sources: `region-research.md`, `us-sources.md`. Code in
`satmesh-core` (georef), `satmesh-data` (registry, COG and ground adapters), `satmesh-tiles` and
`satmesh-cli`. Scratch builds: `uncommitted/regions/`.

## What changed

- `registry.toml` picks the elevation source per area: EA lidar (England), GLO-30 surface with
  FABDEM bare earth (lon 34 to 60, lat 12 to 38), GLO-30 alone elsewhere.
- Heights keep the source's vertical datum; each node record names it (`vertical_crs`), the source
  and whether the ground is the surface. EGM2008 goes through PROJ's `us_nga_egm08_25` grid, which
  `make setup` installs.
- Stores outside England carry Esri's `ACCURACY (M)` as the position bound; `correct` refuses them.
- Node records changed: `origin_odn_height_m` became `origin_orthometric_height_m`, three fields
  were added. Older stores need a rebuild or a key rename (see `status.md`).

## Measurements

- Sana'a old city, 2 km square, GLO-30 only: 74 nodes (64 leaves at z17, Esri z19 0.31 m, stated
  accuracy 8.47 m) built in 37 s from a cold cache; with FABDEM ground 74 nodes in 19 s (cache warm
  for imagery). Shibam, 29 nodes (25 leaves at z16: Esri's cache stops at z18 there, stated
  accuracy 5 m), UTM 39N, same build. Georeference cross-checks: EGM2008 geoid height at Sana'a
  -4.98 m (grid sample, matches `region-research.md`); the store's separation -4.956 m is the mean
  over a leaf; `satmesh export glb`, `3dtiles` and `gazebo` ran on the store.
- Sana'a window, 71 x 72 pixels: DSM 2,241.9 to 2,272.1 m, FABDEM ground 2,244.6 to 2,263.8 m,
  mean ground minus surface -1.70 m (range -14.2 to +5.4 m; the positive part is FABDEM's own
  error, left as is). No pixel needed filling from the surface.
- A node of GLO-30 holds 400 to 740 vertices at 0.1 m TIN error: the 30 m source is smooth, so
  buildings and trees are absent until the height-lift work adds them.
- Fetch cost: first GLO-30 plus FABDEM window 3.2 s including the FABDEM block index (5.7 MB),
  cached 0.0 s.

## Traps

- GLO-30 and FABDEM tiles are point-registered (`AREA_OR_POINT=Point`). GDAL already shifts the
  geotransform by half a pixel (tile N15E044 origin 43.99986, 16.00014), so the sampling formula
  holds as is; the code reads through `src.transform` and sets `GTIFF_POINT_GEO_IGNORE=FALSE`
  explicitly. A test with a one-pixel peak fails when the option is flipped.
- FABDEM zip names are not computable: `S20W050-S-10W040`, `S10W170-N00W160`, `N00E170-N10W180`.
  The tile index `FABDEM_v1-2_tiles.geojson` supplies them. The index writes `N015E044`, the zip
  members are `N15E044_FABDEM_V1-2.tif`.
- One tile near 51 N, 1 W (`N51W001`) did not open under that name; irrelevant for the Middle East,
  unchecked elsewhere.
- Reads from the FABDEM zips have no retry (GDAL, not httpx); the block index download does.
- A 1-degree tile needed only for the 2-pixel margin may be missing (coast): the margin is dropped
  on that side. A needed tile that is missing raises.
- Selection is by the area's centre; an area only partly inside the first matching entry raises.

## Not checked

- Any render of the Yemen meshes by eye (the owner reads them in Blender): they are expected to be
  smooth at 30 m with imagery on top.
- FABDEM against any reference in Yemen (no open lidar); published arid-terrain RMSE is about 1.8
  to 2.4 m, 2.7 m in built-up terrain (`region-research.md` follow-up survey in this session:
  Ho et al. 2025, PeerJ 13:e19673).
- `make test-contract`, which needs the network for its slice build.
