# Status and decision log

Running record of where the project stands and why. Updated at every checkpoint: state, decisions
with their reasons, open risks. Detail per feature lives in the plan and results docs named here.

## Goals (owner, 2026-10-25)

- Place a virtual camera in a 3D scene built from the tiles, render with arbitrary camera specs,
  and check that everything on the ground that is visible in reality is visible in the render
  (video-to-map matching pipelines). Needs true ground scale, accurate georeference, a known
  height datum, and geometry for what a camera sees (buildings, trees).
- Populate Gazebo with the tiles covering the right ground and run a robotics stack on them.
- View in CesiumJS.
- No compromise on end quality, but optimised. Resolution is decided per tile, never capped for
  the whole area. Tile and texture sizes are fixed (Cesium-style), not scaled to the area.
- Esri imagery is the fallback source; enhancement (super-resolution, DEM refinement) replaces
  tile contents later, so the store keeps the source pixels.

## State against the plan (2026-10-25)

| Stage | State |
| --- | --- |
| 0 Scaffold | Done |
| 1 Spikes | S1, S5, S6 done. Open: S3, S4; S2, S2b, S7 on demand |
| 2 Baseline pipeline | F1 to F5a done for Great Britain (DSM visual mesh, DTM ground grid). Open: F2a, F2b, F5b Gazebo collision, F5c large-area DTM |
| 3 Evaluation harness F6 | Approved; checkpoints 1 to 3 of 5 done (`f6-results.md`): height scores, pipeline check, EA aerial slice, Esri-to-EA offset, relief dependence, drape render |
| 4 Classical enhancement E1, E2 | Not started |
| 5 ML experiments E3 to E7 | Not started; owner priorities are E4 (continuous height) and E6 (multi-capture SR) |

Next: F6 checkpoint 4 (camera visibility); F5b before any Gazebo run, since collision
still uses the visual mesh.

## Decisions

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-10-25 | PyTorch constraint dropped from README, AGENTS.md and plans | Came from the scaffold copied from xfeat-rt, not from the owner; `ml/` workspace remains an option |
| 2026-10-25 | Typer for the CLI | Owner choice; typed signatures, `CliRunner` for tests |
| 2026-10-25 | platformdirs cache, `--cache-dir` and `SATMESH_CACHE_DIR` | Owner choice; `~/.cache/satmesh` |
| 2026-10-25 | EA DTM hard-wired for Great Britain, no `--dtm` | Registry is F2a; other regions raise |
| 2026-10-25 | Single-GLB output with an 8,192 px texture cap replaced by a tiled store | Owner rejected a whole-area cap: resolution is per tile |
| 2026-10-25 | Canonical store with thin exporters, not 3D Tiles as the store | Cesium, Gazebo and renderers each want a different frame; swapping a texture or DEM replaces one node |
| 2026-10-25 | Leaf = 4 x 4 Esri tiles (1,024 px, about 180 m at z19, 54 N) | Whole Esri tiles, no resampling; per-place native zoom is leaf depth |
| 2026-10-25 | Meshes in true-metre local ENU through OSTN15 and OSGM15, with both heights recorded | BNG XY is 0.04% short; Cesium and GNSS use ellipsoidal height; geoid separation is about 50.8 m |
| 2026-10-25 | Parents only where all four children exist; container over maximal complete nodes | No holes in parent textures, no extra fetches; ragged edge stays at leaf resolution |
| 2026-10-25 | Store DTM and EA first-return DSM per node (DSM for the visual mesh, DTM for ground and collision) | Orthophoto on a DTM paints buildings and trees flat; built in F5a |
| 2026-10-25 | F6 approved: `satmesh-eval` package with xdem, scikit-image and a ray caster; depth difference and object recall for camera visibility; raw point-cloud spike; opensr-test deferred to E3 | Owner decisions 1 to 4 on `f6-plan.md` |
| 2026-10-25 | F6 sites: Upper Aire and Lower Aire | Owner choice; moorland and trees, then houses and roads |
| 2026-10-25 | F6 second site moved from Lower Aire (BNG 452000 425000) to Ferrybridge (448000 424000) | The 2020 EA survey caught the Aire in flood at the first box: 31 of 900 windows reliable |
| 2026-10-25 | Offset windows kept only above the 99th percentile of peak response between unrelated windows | Raw phase-correlation shifts span +-16 m on real pairs and skimage's error is uninformative |
| 2026-10-25 | Esri-to-EA comparisons resample through pyproj with OSTN15, never `rasterio.warp` | The rasterio wheel has no UK grids; its Helmert fallback was 1.6 m north of OSTN15 at Upper Aire and produced a false 2 to 3 m offset |
| 2026-10-25 | Ray casting with trimesh and embreex, not Open3D | Open3D 0.20 has no wheel for CPython 3.13 on this glibc |
| 2026-10-25 | Real-photo localisation test (F7) out of F6 but required before v1 release | Owner decision 5; needs photographs with known poses |
| 2026-10-25 | Ground grid stored as a per-node GeoTIFF (EPSG:3857, one pixel per grid node), not a ground mesh | F5b needs the DTM without refetching; a raster is readable by GIS and by the F6 scorer, and the decimation choices stay open |
| 2026-10-25 | DSM used as served, not clamped to the DTM | It sits below the DTM at 5 % of pixels by up to 0.33 m; clamping would hide a survey-epoch disagreement F6 should measure |

## Open risks

- Gazebo collision uses the visual (DSM) mesh until F5b: robots would collide with canopies.
- DSM nodata (water, survey edges) raises and stops the build; untested on such a box.
- Esri imagery sits 0.8 to 1.0 m north of EA 2020 imagery (F6 checkpoint 2; S6's 2.4 m was a
  Helmert-reprojection artifact), and raised objects are displaced differently from open ground, so
  a rigid correction will not do; matching pipelines will see it.
- Whether Esri imagery is a true orthophoto is unknown; if not, buildings lean in the texture.
- No ground-truth scoring yet: DEM, texture and geoid chain are untested against raw lidar and
  EA aerial imagery.
- Gazebo untested: roll pose for glTF, `elevation` datum (gz-math treats it as ellipsoidal),
  levels, mesh collision cost, tile-count and VRAM limits.
- Large areas: parents past about 6 km need a DTM fetch not yet tried (WCS tested to 6000 x 6000
  px); a 20 km box is about 198,000 Esri tiles, about 55 h at 1 request/s.
- Texture seam lines were wrap-around sampling, fixed with a clamp sampler (2026-10-25). Geometric
  cracks between tiles are hidden by skirts, not removed; not seen in renders since the fix.
- `sources_at` is not cached, so a cached rerun still makes one identify request.
- Wales and Scotland have no EA DTM; zoom comes from sources at the area centre only.

## Where things are

| What | Where |
| --- | --- |
| Feature plans | `f1-f2-plan.md`, `f4-plan.md` (partly superseded), `f5-plan.md`, `f6-plan.md` |
| Research | `s1-results.md`, `s5-results.md`, `s6-results.md`, `uk-sources.md`, `f5-tiling-research.md`, `f6-research.md` |
| F5 build record | `f5-results.md`, `f5a-results.md` (DSM) |
| Task list | `TODO.md` at the repo root |
