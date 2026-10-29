# E2b results: position correction in towns and woodland

Plan: `e2b-plan.md`.

## T0: is the shift constant within an Esri scene? (2026-10-26)

Store: `uncommitted/t0/ferrybridge-5km`, EA lidar tile SE4520 (BNG E 445000 to 450000, N 420000
to 425000), Esri z18, 310 nodes, built in 10 min. `correct` over it: 36 cells (6 x 6, about 917 m
east by 974 m north), 213 s, 13 corrected, 23 uncorrected (36 %, against 4 of 8 survey boxes
before). The run.log "E x N y" is a cell's south-west corner. The printed shift has the sign of
the truth (positive = Esri east and north of the ground).

Esri capture polygons (identify with geometry, 169 points): 9 Vivid Advanced polygons at z18 in
4 date and sensor groups (2022-07-16 WV02 0.5 m, six polygons; 2025-04-29 WV02 0.5 m; 2025-06-30
LG02 0.34 m; 2025-07-16 LG01 0.34 m). 26 of 36 cells are mixed (second group at least 10 %), so
only one corrected cell lies in a single polygon.

| Dominant group | Corrected cells | E range, std (m) | N range, std (m) | Bounds (m) |
| --- | --- | --- | --- | --- |
| 2022 WV02 | 5 | 1.67, 0.60 | 1.10, 0.44 | 0.76 to 1.54 |
| 2025-06 LG02 | 2 | 0.21, 0.15 | 0.26, 0.19 | 0.81, 1.49 |
| 2025-07 LG01 | 5 | 0.56, 0.23 | 0.71, 0.31 | 0.93 to 1.47 |
| 2025-04 WV02 | 1 | n/a | n/a | 2.73 |
| All 13 | 13 | 1.67, 0.40 | 1.43, 0.35 | 0.76 to 2.73 |

- H4 is not supported and not testable here: no group with three or more cells meets 0.3 m, but
  the spread is mostly inside the cell bounds, so it may be noise. East is negative (-0.03 to
  -1.04, one +0.63) and north positive in 12 of 13 cells.
- Uncorrected cells carry 2.8 m, so 23 of 36 cells have no better statement than that.

EA aerial truth (2020-02, 10 cm, `satmesh eval offset` over 1 km boxes, all windows, not open
ground only; truth E, N m with 95 % interval):

| Box (SW corner) | Truth | Cells overlapped | Printed shift of the corrected share |
| --- | --- | --- | --- |
| Town 448500, 423500 (terraced housing, industry) | -0.31, +0.71 | 75 % uncorrected | -0.54, +0.79 (19 %) |
| 445050, 423950 | +0.05, +0.50 | 78 % uncorrected | -0.21, +0.74 (22 %) |
| 446100, 423950 | -0.09, +0.14 (wide) | 78 % corrected | -0.26, +0.76 |
| 447200, 423950 | -0.25, +1.07 | 64 % corrected | -0.44, +0.59 |

- Corrected cells miss the truth by 0.1 to 0.6 m on north where the box is mostly corrected.
- The town box has a real offset (+0.71 N) that the uncorrected cell leaves at 2.8 m.
- Coverage limit: the 2020 aerial tile exists only for N 423000 to 425000; the southern 3 km has
  a 2007 infrared tile only, not used. No truth in the southern, mostly uncorrected part and in
  the 2025-04 polygon.

Traps: `c_crop.py` ran first with boxes outside coverage and left empty crops
`t0-B/C/D-*.tif` in `~/.cache/satmesh/ea-aerial/` (delete refused; remove by hand).

Consequence for the plan: borrowing across a polygon (T3) cannot be validated on this data, and
cells straddle polygons, so a polygon-keyed borrow would need polygon-split cells. T1 (ground-only
windows) and the S0b lean finding (see `e9-results.md`) are the better next steps; a
lean model (T2) now has evidence behind it at the S0b cross-check site.

## T1: ground-only windows (2026-10-26)

Verdict: no-go. Scratch experiment, repo untouched. The nDSM (first-return maximum minus lowest
ground-class point, 1 m grid) above 2 m, grown by 0.3 m per metre of height up to 8 m, was set to
the median gradient in both the lidar and the Esri gradient images before the unchanged window
matching. Declared before any result: windows with at least 50 % unmasked pixels (A). A second
setting, at least 95 % (B), was added after the artefact below appeared.

- A reaches the 5 % window rule at Dunster, Loughborough and Snettisham, but returns exactly
  0.00, 0.00 m shift (interval about 0.01 m) in 8 boxes: both images carry the same mask-edge
  steps, which correlate at zero shift. Those windows say nothing about the ground.
- B removes the artefact and leaves 0 to 10 reliable windows at the roof-heavy boxes (Dunster,
  Southend, Loughborough, town); only 347, 0 and 127 of 900 windows at the first three are even
  eligible.
- Snettisham (0.3 % of pixels masked) goes from 0.38 to 0.25 m north error: marginal, not
  evidence the mask works. Belford and Neston are unchanged. Ferrybridge and Upper Aire could not
  be compared: their 1 km corners were inferred and Upper Aire's baseline does not reproduce.
- Roof-heavy boxes have too little open ground for a window to be mostly ground, so masking
  cannot raise coverage there.

Untried: a ground-class-only lidar reference with windows that are fully ground, without mask
edges. It faces the same shortage of ground windows.

## T2 prior-art check: lean model (2026-10-26)

Survey by a research subagent. VERIFIED means the source was opened and read; UNOPENED means a
snippet only.

- An established method fits: model the basemap's residual geometry as a constrained 3D affine
  projection, displacement = t + l * h, with t the ground shift, l the lean vector (azimuth
  atan2(l_E, l_N), magnitude tan of the off-nadir angle) and h the height above the DEM the
  basemap was orthorectified with. Project the lidar into image geometry under the model, match
  templates (normalised cross-correlation or mutual information), refit, iterate. Parmehr, Fraser,
  Zhang and Leach 2013 (ISPRS Annals II-5/W2, VERIFIED) do this for WorldView-2 against lidar;
  results are qualitative, mutual information fails where elevation varies little. Fraser and
  Yamakawa's affine model (Yamakawa and Fraser 2004, VERIFIED) gives the form. Mastin, Kepner and
  Fisher (CVPR 2009, VERIFIED, partly read) render the lidar under candidate cameras and maximise
  mutual information. Suliman and Zhang (2014, 2017, abstracts VERIFIED) project the DSM but need a
  sensor model or a stereo pair.
- No basemap-specific result found; the DEM Esri's Maxar basemap is orthorectified with is not
  published. The Maxar basemap specification (VERIFIED) allows off-nadir angles to 30 degrees and
  accuracy 8.5 m CE90 for the standard products. Esri identify (live, VERIFIED) returns a scene
  polygon, capture date and sensor per pixel, so each scene can be fitted separately.
- Libraries, no new algorithm: `scipy.optimize.least_squares` with a robust loss (`soft_l1`) for
  the four-parameter fit, bootstrap over buildings, OpenCV `matchTemplate` or SimpleITK mutual
  information for matching, `scipy.optimize.minimize(method="Powell")` for refinement, and the
  existing lidar mesh rendered orthographically along the lean direction for forward projection.
  xdem coregistration does not apply (DEM to DEM).
- Conflict to settle first: a 30 degree cap allows at most tan 30 = 0.58 m per m. The pooled
  S0b cross-check slope is about 0.55 m per m, and the synthetic check says the measurement is about
  half the truth, which would be about 1.1 m per m and above the cap. Either the halving does not
  carry to real data or false matches inflate the slope. Settle it by refitting the existing
  per-building offsets per Esri scene polygon with a robust loss, and by a closure test (shift
  each template by the fitted lean, re-match, regress again).
- Failure modes: seamlines and mixed scenes in one area, facades visible in the image but absent
  from a DSM render, shadows, capture-date differences between image and lidar, leaf state, flat
  areas without a peak, a coarse orthorectification DEM leaving slope-dependent shifts.
- Recommended: Parmehr-style iteration with the four-parameter model, per Esri scene polygon,
  initialised from the per-building offsets already measured.

The cheap verification needs no repository code. Implementation comes back to the owner first.

## Lean fit at four sites (2026-10-26)

Scratch experiment (scripts in the session scratchpad, images in `uncommitted/e2b-lean/<site>/`,
git-ignored). Per Esri scene polygon, a robust least-squares fit of the per-building offsets on
eave height (10th percentile of roof height, declared before fitting), t + l * h, with a bootstrap
over buildings. Corrected imagery: out(p) = Esri(p + t + l * h_dsm(p)). Sites, 1 km boxes at Esri
z19: Worcester (west, BNG 385500 254600), Southend (east, 588300 186400), Newcastle (north,
426700 564500), Brighton (south, 531500 106300).

| Scene | Buildings | Azimuth (95 %) | Lean k, m per m (95 %) | Closure: matcher offset before to after, m |
| --- | --- | --- | --- | --- |
| Worcester 2025-08-06 WV03 | 21 | 158 (91 to 251) | 0.37 (0.15 to 1.14) | 1.80 to 1.54 |
| Worcester 2025-04-10 LG02 | 11 | 242 (137 to 314) | 0.56 (0.20 to 1.61) | 0.81 to 0.55 |
| Southend 2025-07-12 GE01 | 23 | 193 (183 to 218) | 0.54 (0.27 to 0.83) | 1.68 to 1.22 |
| Newcastle 2025-09-09 WV03 | 17 | 153 (83 to 246) | 0.12 (0.07 to 0.58) | 2.79 to 0.67 |

- Brighton: no fit; 5 buildings passed the matcher (terraced roofs touch and fail the building
  tests); a second box gave 2.
- Matcher acceptance is 4 to 17 % of candidate buildings, mostly flat-roofed blocks; pitched
  terraces are under-represented.
- Only Southend's direction is tight. The ground shift t is badly constrained because roofs span
  only 3 to 9 m, so the "shift only" image is often worse than as published and is not what
  `satmesh correct` produces.
- Closure improves at three of four scenes (matcher self-consistency, not independent truth);
  Southend's residual slope on height rose. No lower interval bound exceeds the 0.58 m per m
  off-nadir cap, so the synthetic halving from S0b is not confirmed as a factor of two.
- Corrected images put roofs on their lidar outline in the strips inspected (Southend, Worcester)
  with stepped edges from the 1 m height grid; facades hidden from the lidar are not recovered.
- The owner judges the images (artifact page of 24 building strips and three overviews).

## Esri scene polygons by one query (2026-10-26)

- `World_Imagery/MapServer/4/query` with an envelope (`geometryType=esriGeometryEnvelope`,
  `inSR=4326`, `outFields=*`, `returnGeometry=true`, `outSR=4326`, `geometryPrecision=6`,
  `maxAllowableOffset` 1e-4 to 5e-4 degrees to keep the response small, `where` URL-encoded as
  `MinMapLevel<=Z AND MaxMapLevel>=Z`) returns every scene footprint of a 5 km area in one request
  (15 polygons, below the 100-record page; `resultOffset` paging works for dense areas). VERIFIED live.
- It is more complete than T0's 13 x 13 identify grid: 5 small slivers the grid missed.
- Fields: `OBJECTID`, `SRC_DATE` (YYYYMMDD), `SRC_RES`, `SRC_ACC`, `SRC_DESC` (sensor),
  `MinMapLevel`, `MaxMapLevel`, `DrawOrder`, `BlockName`, `ReleaseName`.
- Overlap: the footprints of one zoom level are disjoint (T0 area: 14 Vivid polygons, pairwise
  overlap at float noise; Auckland, about 0.01 m2), so no draw-order rule is needed. The winner at
  zoom z is the polygon with `MinMapLevel <= z <= MaxMapLevel` containing the point. Identify
  ignores zoom and also returns TerraColor. UNVERIFIED: that a higher `DrawOrder` draws on top.
- MultiPolygons with holes occur; test points with even-odd fill. Cache footprints with the
  release name, which changes (here `DYNAMIC_ESRI_Leeds_25Q3`).

## C1/C2 build (2026-10-29)

Code, staged and not committed: `satmesh_data/esri_scenes.py` (C1), `satmesh_eval/roofs.py` and
`satmesh_eval/scene_lean.py` (C2), `EsriClient.query_citations`, `shapely` declared in
`satmesh-data` (already locked through geopandas). Tests: 9 for scenes, 2 for roofs, 10 for the
fit; 219 pass in all.

C1, scene footprints:

- One geometry-free query (`outFields=OBJECTID,ReleaseName`) names the release, then the
  footprints come from `~/.cache/satmesh/esri-world-imagery/scenes/<release>/<WGS84 bounds>-z<zoom>.json`
  or one geometry query (`maxAllowableOffset` 1e-5 degrees, `orderByFields=OBJECTID`, paged by
  `resultOffset` while `exceededTransferLimit`). The cache holds the features as served.
- Live, Southend 1 km box at z19: 1.4 s, release `Raster Basemaps 2026.R01`, one scene 20250712
  GE01 from polygons 3297692 and 3298659, share 1.0; cached call 0.9 s (probe plus throttle).
  The 5 km box around it: two scenes, GE01 0.974 and 20250411 WV02 0.026 (8 polygons). The 1 km
  response is 374 KB: polygons come back whole, not clipped to the envelope.
- Ferrybridge SE4520 at z18 (release `Raster Basemaps 2025.R12`): 12 polygons in 4 scenes (T0
  saw 9); shares sum to 1 within 1e-6.
- Scene id is (capture date, sensor); scenes' polygons are unioned after even-odd ring assembly
  (`make_valid` per ring, then symmetric difference). Labels come per point (`labels_at`), per
  raster pixel centre (`label_grid`, rasterio) or as area shares; footprints go to BNG through
  `require_best_transformer` (OSTN15).
- Traps: `ReleaseName` is `Raster Basemaps 2026.R01`, not the `DYNAMIC_ESRI_*` string recorded
  earlier, which is `BlockName`. Releases differ by region on the same day (2025.R12 at
  Ferrybridge, 2026.R01 at Southend). A bad `where` returns HTTP 200 with an `error` body; it
  raises `EsriQueryError`. Fixtures are the live responses clipped to box plus 100 m.

C2, roofs and fit:

- The roof matcher port gives the same roofs as lean2's saved observations, bit for bit, at
  Southend T (13), Ferrybridge T (20) and Southend L (23), 3 s per 1 km box.
- `fit_scene_lean` reproduces lean2 F2 to the printed digits on the saved observations (1000
  bootstrap draws, seed 0):

| Box | Status | t E, N (m) | Error vs truth | k (95 %) | Azimuth (95 %) | Lean radius 95 % |
| --- | --- | --- | --- | --- | --- | --- |
| Southend T | applied | +0.54, +2.23 | 0.73 m | 0.40 (0.30 to 0.55) | 210 (190 to 218) | 0.17 |
| Ferrybridge T | rejected | -0.57, +0.46 | 0.36 m | 0.15 (0.04 to 0.58) | 354 (177 to 533) | 0.62 |
| Southend L | applied | +0.24, +2.44 | no truth | 0.36 (0.19 to 0.58) | 200 (187 to 252) | 0.24 |

- The cap: the soft-L1 cost is convex in (t, l), so when the free fit has k above tan 30 the
  constrained optimum lies on k = tan 30 and is fitted there with t and the azimuth free; every
  bootstrap draw is capped the same way. None of the three point estimates reaches the cap; the
  capped bootstrap moves the upper k bound from 0.71 and 0.67 (lean2, uncapped) to 0.58.
- Rejection rules, in order: fewer than 10 roofs (Brighton had 5 and 2); fewer than 10 reliable
  ground windows in the scene (no prior on t; roofs alone missed by 5.19 m at Ferrybridge);
  all eave heights equal, a fit that does not converge or no bootstrap draw fitted; the 95 %
  radius of the bootstrap leans about the fit above tan 30 / 2 = 0.29 m per m. The minimums and
  the radius limit are tunables.
- Decision, the radius rule over a k-interval width rule: the k interval is cut at the cap and
  misses small leans with an undetermined azimuth (a synthetic case gave k 0.03 to 0.43 with a
  204 degree azimuth interval). The radius times h bounds the lean's share of the error at
  height h in any direction.
- Ferrybridge is rejected although its F2 t is the closest to truth of all fits (0.36 m): its
  roofs span 3.4 to 6.7 m and scatter 2.45 m about the model, so the lean is not measured.
  Falling back to the per-cell shift leaves that box uncorrected (T0: 75 % uncorrected cells).

For C3 and C4:

- `fit_scene_lean` takes the scene's roofs and the cell registration field with NaN outside the
  scene and at unreliable windows; C3 must label windows (centre) and roofs (bounding-box centre)
  with `SceneMap.labels_at` in BNG and pool them over the whole store per scene.
- Sign: positive t and l put Esri east and north of the ground; out(p) = Esri(p + t + l h(p)),
  h the height above the DTM. Azimuth is clockwise from grid north, the direction roofs move.
- A rejected `SceneLean` keeps its fit when the rule was the lean radius; whether such a scene
  takes t with l = 0 is an owner fork, unsettled.

## C3/C4 build (2026-10-29)

Code, staged and not committed. `satmesh correct` fits one lean per Esri scene and rewrites node
UVs per vertex; `--no-lean` keeps the ground-only path. Tests: 228 pass (10 in
`test_correction.py` rewritten, 2 pooling tests in `test_scene_lean.py`, 2 in `test_mesh.py`).

Design as built:

- Schema 2: `CorrectionField` gains `schema_version` (2), `scene_release` (None with `--no-lean`)
  and `scenes` (one `SceneLean` each). `LeanFit`, `SceneLean` and `MAX_LEAN` moved to
  `satmesh_tiles.correction` (the store schema; eval already depends on tiles). `PositionRecord`
  gains `scene`, `lean_east`, `lean_north`, `error_bound_per_height`; status "lean" is new.
- Old stores: `require_current_correction` (tiler) rejects a `correction.json` without version 2
  in `correct`, `apply_correction`, all three exporters and `write_positional_error` with "rebuild
  it with `satmesh build` into a fresh store and re-run `satmesh correct`". Exercised on
  `uncommitted/t0/ferrybridge-5km` (export glb and correct both refused; each appended a failure
  line to that store's run.log).
- C3 pooling (`scene_lean.correction_field`): each cell's reliable windows (any cell status) and
  roofs (matched over the cell box against the cell's own Esri luma and EA DSM/DTM) are labelled
  with `SceneMap.labels_at` at window centre and roof bounding-box centre; windows of all cells
  are placed on one grid (cells side by side, shorter grids padded with NaN) so the block bootstrap
  stays among neighbours. `cell_boxes` now rounds inner edges to whole metres so a cell lies on
  the 1 m lidar grid. A cell whose DSM or DTM fails the gap check gives no roofs (logged).
- Decision (owner-side lead): a rejected scene keeps the per-cell ground shift, no lean, no new t.
- C4 (`apply_correction`): a vertex's build-grid node comes from its glTF position (ENU to ECEF to
  geodetic, rounded to the grid, 0.01-step tolerance), its h from that position's ODN height (OSGM15)
  minus the node's ground GeoTIFF at the node; skirts take the h of the vertex above. New UV =
  base grid UV + uv(p + d) - uv(p), p the vertex's BNG position and uv() the exact BNG to Web
  Mercator to texture map: J d with no linearisation. UVs are absolute, so a repeat or a revised
  field equals a single application (repeat at Southend: max UV change 0.0).
- Error bound: B(h) = B_t + r_l h, B_t = sqrt(w_E^2 + w_N^2 + r_m^2) (w the larger half of the
  95 % bootstrap interval of t per axis, r_m = 0.4 m method residual, as for a cell), r_l the
  95 % lean radius. A sum, not quadrature, as t and l are fitted jointly; each term 95 %, so the
  sum holds at least 90 % by the union bound. Ground-only and uncorrected vertices carry
  r_l = tan 30 (the Maxar off-nadir cap). Node records hold the largest over their vertices.
- Exporters: 3dtiles references the store GLBs, gazebo copies them byte for byte, glb re-exports
  through trimesh; the test checks each against the store's UVs (glb: as unique rows, trimesh may
  merge vertices).

Real flow, Southend (requested BNG 588300 to 588800 E, 186400 to 186900 N, the lean2 "L" corner),
store `uncommitted/scratch-archive/c3c4/l500`: 5 nodes, leaves z16, Esri z18 (not z19 as in
lean2), footprint BNG 588272 to 589063 E, 186159 to 186948 N (0.79 x 0.79 km), build 74 s, correct
63 s. One cell, uncorrected (11 of 529 windows). Scene map release `Raster Basemaps 2026.R01`, two
scenes at z18.

| Scene | Status | Roofs | Windows | t E, N (m) | k (azimuth) | Radius | Bound |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 20250712 GE01 | applied | 13 | 11 | +0.07, +2.13 | 0.34 (198) | 0.15 | 1.16 m + 0.15 h |
| 20250411 WV02 | rejected (3 roofs) | 3 | 0 | none | none | none | cell: 2.8 m + 0.58 h |

- lean2 Southend L (z19, 1 km): t +0.24, +2.44, k 0.36 toward 200; same scene, consistent.
- Check (scratch `c4_check.py`): per vertex, the BNG point sampled by the corrected UV minus the
  one sampled by the uncorrected store's UV, regressed on h from the EA DSM minus DTM sampled
  bilinearly at the vertex: t and l equal the record to 3 and 4 digits in all four leaves,
  residual 95th percentile 0.000 m. Ground vertices (h < 0.5 m) move +0.06 E, +2.08 N m; roof
  vertices (h > 8 m, mean 9.5 to 10.3 m) move -0.93 to -1.01 E, -0.88 to -1.14 N m, so roofs move
  about 3.2 m toward 198 degrees relative to the ground.
- Nodes: 4 lean, 1 uncorrected (centre in WV02); 873035 of 968996 vertices lean-corrected; leaf
  32898/21781 is mixed (83150 of 153494 vertices in GE01).
- The 100 m slice (BNG 587000 to 587100 E, 185000 to 185100 N, one z16 leaf): GE01 rejected, 2
  roofs and 1 window. The 0.79 km footprint above is the smallest tried with 10 or more roofs.

Traps:

- Texture edges: t_N = 2.1 m is about 6 px at z18, so 5098 vertices (0.5 %) sample more than a
  pixel past their texture's edge; the clamp sampler repeats the edge pixels there, a stretched
  strip up to the shift wide along tile edges (ground along the north edge, as t points north;
  tall roofs along the south edge). Also true of the ground-only shift; a fix needs texture
  margins at build time.
- Seamlines inside a node: triangles across a scene boundary interpolate between a lean-corrected
  and an uncorrected vertex, so imagery stretches along the seam (here GE01 against WV02, 2 m).
- Float noise: base UVs of 1.0 read back as 1.0000001; the edge count uses a one-pixel slack.
- `export glb --out` into a directory that does not exist fails (seen in the real flow; earlier
  behaviour, untouched).
- An independent h check needs bilinear sampling of the 1 m grids, as the build does: nearest-pixel
  h gave a 0.29 slope against 0.32 and 0.45 m residuals at roof edges.

For C5: `uncommitted/scratch-archive/c3c4/` holds three copies of one build, `l500` (lean, default),
`l500-nolean` (`correct --no-lean`; here equal to uncorrected, as its one cell is uncorrected) and
`l500-uncorrected`, with `exports/<store>.glb`, `exports/<store>-gazebo/` and 3dtiles in each
store. Before/after strips can be rendered from `l500-uncorrected` against `l500` on the same
crop; a store with a corrected cell is needed to show ground-only against lean.

## C6 result (2026-10-29)

Verdict: fails the gate, no production code. Scratch: `uncommitted/scratch-archive/c6/gate.py`,
declaration and run in `progress.log` there, per-box `*_gate.json`.

Method, declared before running: from the production F2 fit (`fit_scene_lean`, 1000 draws, seed
0) of the box's dominant scene, de-lean the Esri luma with l only, out(p) = Esri(p + l h(p)), h =
DSM - DTM clipped at 0 and sampled bilinearly onto the 0.25 m grid (`scipy.ndimage.map_coordinates`,
order 1); rerun `measure_offset` against the lidar intensity gradient (null threshold recomputed on
the de-leaned pair); keep the in-scene reliable windows; refit F2 once with them as the ground
prior. One pass. Gate: error vs truth improves at both truth boxes, or at one with at most 0.05 m
loss at the other, and at least `MIN_GROUND_WINDOWS` (10) in-scene windows after de-leaning.

| Box | Truth E, N | F2 t, error | De-leaned windows (raw) | De-leaned t0, error | Refit t, error | Refit status |
| --- | --- | --- | --- | --- | --- | --- |
| Southend T | +0.23, +1.57 | +0.54, +2.23, 0.73 m | 38 (13) | +0.50, +2.50, 0.97 m | +0.55, +2.46, 0.95 m | applied, k 0.43 |
| Ferrybridge T | -0.31, +0.71 | -0.57, +0.46, 0.36 m | 30 (63) | -0.21, +0.64, 0.12 m | -0.37, +1.13, 0.42 m | rejected (radius 0.59) |

- Both boxes get worse (+0.22 m and +0.06 m); the window half of the gate passes.
- At Southend de-leaning moves the window median 0.4 m further north of truth, the direction of
  the C5 overshoot (matcher north +0.43 to -0.51 m), so the ground prior's bias there is not
  explained by lean inside the windows.
- At Ferrybridge the de-leaned window median alone is 0.12 m from truth, but the roofs pull the
  refit to +1.13 N; the de-leaned windows halve (63 to 30), widening the prior.
- Info, not gated: keeping the raw-image threshold gives 19 and 43 windows and refit errors 0.97
  and 0.70 m.
- The window count rises at Southend (13 to 38) and halves at Ferrybridge after de-leaning, as
  lean2 F4 saw 18 to 25 windows change per iteration: the reliable set is sensitive to the warp,
  so a de-leaned prior averages over different windows than the raw one.

Traps: `SceneId.capture_date` is a `date`; lean2's scene strings carry `YYYYMMDD`, which pydantic
does not parse as a date.
