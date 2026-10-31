---
status: current
topic: baseline-pipeline
summary: Plan to make the baseline pipeline region-agnostic: a source registry, a georeference for any horizontal and vertical datum, GLO-30 for the Middle East first (Yemen end to end), then US 3DEP; stages R0 to R2 and forks for the owner.
answers: How will the pipeline build outside Great Britain; what does the source registry hold; how are heights converted for GLO-30 and 3DEP; what happens to position correction abroad; what are the stages R0 to R2 and what does each deliver
---

# Regions plan: Middle East first, then the USA

Drafted 2026-10-30 after the owner moved this ahead of the height experiments; R0 is built and
measured in `regions-results.md`. Sources:
`region-research.md` (Yemen and the Middle East), `us-sources.md`, `implementation-plan.md`
(registry design). R1 is built and measured in `regions-r1-results.md`; R2 is open. The ML
work resumes once a build runs end to end outside Great Britain.

## What is hard-wired to Great Britain today

| Where | Coupling | Change |
| --- | --- | --- |
| `satmesh_tiles/tiler.py` | raises unless `metric_crs` is BNG; fetches `EA_DSM` and `EA_DTM`; AOI snapped to whole BNG metres | ask the registry for the sources; work in `metric_crs(aoi)` (already UTM outside Great Britain) |
| `satmesh_core/georef.py` | `bng_odn_to_wgs84`, `wgs84_to_bng` (OSTN15, OSGM15) | one transformer built from the horizontal CRS and the source's vertical CRS |
| `satmesh_tiles/node.py` | converts node ENU through BNG | same transformer |
| `satmesh_cli/main.py`, `corners.py` | corners snapped in BNG; `fetch_scene_map` in BNG | snap in the metric CRS |
| `satmesh_data/ea_*.py` | EA WCS and EA point clouds | stay as the Great Britain entries; position correction stays England only |

`metric_crs` already returns the UTM zone outside BNG, and Esri tiles, Web Mercator tile math and
the 3D Tiles and Gazebo exporters do not depend on the country.

## Design

- **Registry**: a validated TOML file in `satmesh-data` read into frozen pydantic models. Entry:
  name, kind (DSM or DTM), resolution, region polygon (lon/lat box list), access adapter name and
  its parameters, horizontal CRS, vertical CRS, licence and attribution. Lookup walks an ordered
  list and takes the first entry that covers the AOI. Three real adapters exist by R1, so a
  registry is warranted (no speculative seam): `ea_wcs` (existing), `cog_window` (GLO-30; 3DEP
  1/3 arc-second) and `tnm_cog_1m` (3DEP 1 m: TNM API, then COG range reads).
- **Georeference**: heights live in the source's vertical datum, recorded per node as today (both
  heights). Conversion to ellipsoidal is a PROJ pipeline named by the source: ODN `EPSG:7405`
  (existing), GLO-30 `EPSG:4326+3855` to 4979 (EGM2008), US `EPSG:6349` to `6319` (GEOID18) then
  the time-dependent Helmert to WGS 84 (`us-sources.md`: explicit two-step chain). A missing grid
  fails before any fetch (existing `require_best_transformer`).
- **GLO-30 pixels are point-registered** (`AREA_OR_POINT=Point`): the half-pixel shift is applied
  in the adapter, and a test moves a known synthetic peak to prove it.
- **Surfaces**: a node stores a DSM (visual mesh) and a DTM (ground grid, collision). GLO-30 is a
  DSM only. Fork 1.
- **Position correction**: `correct` needs lidar and stays England only for now. Elsewhere a store
  carries a `correction.json` with every cell uncorrected and `uncorrected_error_bound_m` set from
  the Esri layer `SRC_ACC` at the AOI (4.2 to 10.2 m in Yemen). Exports keep reporting a bound.
  US lidar (EPT, with GpsTime) can feed `correct` later; that is outside R0 and R1.
- **Esri imagery** is global; the leaf depth probe, throttling and cache are reused. The Yemen
  survey saw z18 as the cache ceiling at several places, so the native-depth probe is tested there.

## Stages

| Stage | Delivers | Check |
| --- | --- | --- |
| R0 | Registry, georeference, tiler without BNG, GLO-30 adapter, uncorrected correction file, `build` and all three exporters for a 2 km square at Sana'a old city (44.207 E, 15.355 N, UTM 38N); then Shibam | store builds from cold cache; geoid values match the survey table (Sana'a N = -4.98 m); mesh vertex ECEF round-trips through PROJ to the input corners; GLB opens in Blender; tests with recorded fixtures (no network in unit tests); `make check` |
| R1 | 3DEP adapter: 1 m DEM COGs via TNM, ImageServer fallback, 1/3 arc-second fallback; DSM rasterised from EPT first returns; GEOID18 chain; Denver and a suburban square | DEM against ImageServer within 0.01 m; DSM against the 2 m Planetary Computer DSM; geoid separation at Denver -17.10 m; builds; GLB in Blender |
| R2 | Polish for merging: README and docs, CLI help, `make` target for a regional smoke build, risks updated, hand-over of what stays England only | `make check`, then a real build per region observed working |

Scoring abroad: the US squares have lidar truth (so `satmesh eval heights` can score a GLO-30 build
against 3DEP, a real test of the coarse-source case); Yemen has none and stays a plausibility
check (DEM agreement), as in `region-research.md`.

## Forks for the owner

1. **Ground surface where only a DSM exists** (GLO-30). Recommended: GLO-30 serves as both DSM and
   ground, flagged in the store as "ground = surface"; collision then hits roofs and trees.
   Alternative: FABDEM bare earth (CC BY-NC-SA, ML-corrected, research use only) as an optional
   registry entry later.
2. **US DSM**: rasterise EPT first returns ourselves (recommended; carries the acquisition year
   and matches the England product) against the 2 m Planetary Computer DSM (2012 to 2022 only).
3. **US imagery**: Esri stays primary (finer, global, your earlier research-use decision), with
   NAIP as a registry entry for an open licence. NAIP is capped at 2023 and ±6 m.
4. **Geoid grids**: `make setup` downloads `us_nga_egm08_25.tif` (80.6 MB) and
   `us_noaa_g2018u0.tif` (16.7 MB) into PROJ's user directory, as it does for the UK grids.
5. **Order**: R0 before R1, as you asked; R1 starts after R0 builds and opens in Blender.

No new Python dependency is expected: rasterio, pyproj, httpx, laspy and pydantic are already in
the workspace.
