---
status: historical
topic: position-correction
summary: Measured results of E2b: T0 to T4 tests, lean fit, lean2 comparison, C1 to C6 build; lean per Esri scene built, C6 de-leaned registration failed its gate
answers: Is the Esri shift constant within a scene; How was the roof lean fit conditioned and which fit was chosen; How does per-vertex UV lean correction work; Why did C6 de-leaned registration fail; What did the C5 lean-corrected render review show
---

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

Per-cell result of the 213 s run (`uncommitted/t0/ferrybridge-5km/run.log`, `correction.json`;
polygon cover shares per cell in `uncommitted/scratch-archive/t0/cells_cover.json`). Each entry is
the shift E, N in m and the windows used of 783; "-" is an uncorrected cell (bound 2.80 m). Row
label is the cell's south edge, column label its west edge (BNG m):

| N \ E | 444713 | 445630 | 446546 | 447463 | 448380 | 449296 |
| --- | --- | --- | --- | --- | --- | --- |
| 424437 | - (19) | -0.21 +0.74 (41) | -0.28 +0.63 (76) | -0.55 +0.47 (57) | - (39) | - (13) |
| 423463 | - (30) | - (39) | -0.28 +0.93 (50) | - (35) | - (33) | -0.54 +0.79 (44) |
| 422488 | +0.01 +0.48 (48) | -0.24 +0.96 (55) | -0.19 +0.29 (40) | -0.41 +0.91 (45) | - (30) | -0.75 +1.00 (41) |
| 421514 | +0.63 +0.76 (50) | -1.04 +1.72 (52) | - (34) | - (16) | - (19) | - (28) |
| 420540 | - (24) | - (26) | - (14) | - (11) | - (30) | - (22) |
| 419566 | -0.03 +0.78 (60) | - (30) | - (22) | - (23) | - (24) | - (19) |

Bounds of the 13 corrected cells: 0.76, 1.54, 1.49, 1.20, 1.07, 1.03, 0.81, 0.93, 1.03, 2.73,
1.39, 1.04, 1.47 m (log order). Run time: lidar download 107.5 s, point reading 34.5 s, matching
213.0 s, tile update 16.9 s, 372.9 s in all; 110 of 310 nodes corrected, 200 left as they were.

Truth intervals and windows of the four aerial boxes (`uncommitted/scratch-archive/t0/offset-*.txt`;
the three 1 km boxes are the 445050, 446100 and 447200 rows of the table above, 423950 south
edge; interval 95 %, NMAD E / N in m):

| Box | Aerial | Truth E (interval) | Truth N (interval) | NMAD E / N | Reliable windows |
| --- | --- | --- | --- | --- | --- |
| T-town 448500, 423500 | 2020-02 | -0.31 (-0.38, -0.23) | +0.71 (+0.37, +0.97) | 0.56 / 1.10 | 113 of 870 |
| B2 446100, 423950 (WV02 2022 cells) | 2020-02 | -0.09 (-0.43, +0.72) | +0.14 (-0.31, +1.01) | 1.33 / 2.04 | 98 of 870 |
| D2 445050, 423950 (LG02 cells) | 2020-02 | +0.05 (-0.07, +0.29) | +0.50 (+0.44, +0.65) | 0.85 / 0.76 | 166 of 870 |
| E2 447200, 423950 (LG01 cells) | 2020-02 | -0.25 (-0.34, -0.14) | +1.07 (+0.81, +1.49) | 0.47 / 1.42 | 140 of 870 |

The B2 interval spans zero on both axes; D2 and E2 north intervals exclude zero.

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

Per-box counts (`uncommitted/scratch-archive/t1/progress.log`, `results_main.json`,
`results_b95.json`): reliable windows of 900 (196 at Belford and Neston), with the windows eligible
under the mask rule in brackets. Raised share is the share of pixels with nDSM above 2 m; masked
share is that after growing.

| Box | Raised / masked share | Baseline | A, at least 50 % unmasked | B, at least 95 % unmasked |
| --- | --- | --- | --- | --- |
| Dunster | 0.222 / 0.280 | 31 | 50 (666) | 4 (347) |
| Southend | 0.371 / 0.482 | 21 | 7 (340) | 0 (69) |
| Loughborough | 0.304 / 0.381 | 23 | 93 (551) | 10 (127) |
| Snettisham | 0.003 / 0.003 | 155 | 163 (900) | 161 (886) |
| Town 448500, 423500 | 0.228 / 0.300 | 50 | 178 (813) | 0 (117) |
| 445050, 423950 | 0.190 / 0.236 | 60 | 380 (882) | 0 (244) |
| 446100, 423950 | 0.075 / 0.114 | 33 | 94 (881) | 3 (427) |
| 447200, 423950 | 0.186 / 0.238 | 42 | 127 (823) | 2 (176) |
| Ferrybridge | 0.144 / 0.190 | 57 | 105 (848) | 5 (306) |
| Upper Aire | 0.066 / 0.085 | 13 | 52 (865) | 25 (587) |
| Belford | 0.000 / 0.000 | 82 | 82 (196) | 82 (196) |
| Neston | 0.016 / 0.018 | 48 | 52 (196) | 45 (176) |

- Setting A raises the window count at 10 of 12 boxes, lowers it at Southend (21 to 7) and leaves
  Belford unchanged; the extra windows include the zero-shift artefact above. The share of
  setting-A windows at exactly zero shift: Dunster 0.24, Loughborough 0.17, town box 0.22, 445050
  0.28, 446100 0.16, 447200 0.21, Ferrybridge 0.23, Upper Aire 0.29, Snettisham 0.01, Neston
  0.02, Southend 0 and Belford 0.
- Setting B at Southend has 69 eligible windows and none reliable. The eligible counts at the
  first three boxes are therefore 347, 69 and 127; the 0 above is Southend's reliable count.
- Ferrybridge and Upper Aire were measured (105 and 52 windows under A, 5 and 25 under B), but
  their 1 km corners were inferred and Upper Aire's baseline of 13 does not reproduce, so the
  comparison with the other boxes stands as not made.

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

Details from `uncommitted/scratch-archive/lean/progress.log`, with `h_p10` the declared eave
height and `h_med` the median roof height as a check. Box search: Worcester 385500, 254600 (223
buildings of 5 m or more among 267), Southend 588300, 186400 (136 of 187), Newcastle first 425500,
564500 (63 of 78) then 426700, 564500 (129 of 158), Brighton 531500, 106300 (112 of 130), Brighton2
532000, 104600 (50 of 5 m or more).

| Box | Components over 3 m and 40 m2 | Passed building tests | Accepted by the matcher |
| --- | --- | --- | --- |
| Worcester | 833 | 264 | 32 |
| Southend | 1110 | 184 | 23 |
| Newcastle | 567 | 149 | 25 |
| Brighton | 644 | 127 | 5 |
| Brighton2 | 734 | 64 | 2 |

| Scene (n roofs) | t E, N, `h_p10` | l E, N | k (95 %), az | `h_med`: t E, N, k (95 %) | Closure, matcher offset: raw, shift only, lean |
| --- | --- | --- | --- | --- | --- |
| Worcester WV03 (21) | -1.16, +1.04 | +0.138, -0.341 | 0.368 (0.146 to 1.137), 158 | -1.77, +1.23, 0.419 (0.160 to 0.999) | 1.80, 2.32, 1.54 |
| Worcester LG02 (11) | +2.13, +1.86 | -0.492, -0.261 | 0.557 (0.202 to 1.607), 242 | +2.60, +2.98, 0.590 (0.259 to 1.370) | 0.81, 3.18, 0.55 |
| Southend GE01 (23) | +0.25, +3.54 | -0.124, -0.524 | 0.538 (0.265 to 0.830), 193 | +0.30, +3.08, 0.387 (0.183 to 0.696) | 1.68, 2.46, 1.22 |
| Newcastle WV03 (17) | +1.76, -1.32 | +0.053, -0.105 | 0.118 (0.070 to 0.582), 153 | +1.93, -1.27, 0.098 (0.082 to 0.490) | 2.79, 0.87, 0.67 |

- Shift-only closure (ground shift t alone, no lean) is worse than the published image at
  three of four scenes, by 0.5 to 2.4 m at the two Worcester scenes and 0.8 m at Southend;
  Newcastle improves from 2.79 to 0.87 with t alone and to 0.67 with the lean.
- Logged fitted share of the box: Worcester 1.000, Southend 0.997, Newcastle 0.717.
- S0b cross-check (`s0b_xcheck.py` on the S0b per-building offsets, 300 bootstrap draws,
  one lean shared by all boxes and a ground shift per box): 83 buildings in 7 boxes, k 0.654
  (0.509 to 0.796) with `h_p10`, 0.555 (0.433 to 0.681) with plain height, azimuth 209.5 degrees;
  the "about 0.55" quoted above is the plain-height value.
- Unresolved: `e9-results.md` attributes the S0b building set to Worcester (86 buildings in 8
  boxes). `s0b_xcheck.py` fits the `x35*` boxes of `results_extra.json` that hold at least 2
  `dsm`-accepted buildings: 7 of the 8 `x35*` boxes (354160 has none), 83 buildings; its docstring
  says "8 boxes", the log prints 7. The 86 of `e9-results.md` are those 83 plus 3 at Ferrybridge,
  8 boxes counting Ferrybridge. The `x35*` grid corners (BNG E 351892 to 354925, N 237291 to
  238828) lie about 33 km west of the Worcester box above (E 385500, N 254600). No S0b log or
  script names a place for the `x35*` boxes; the Worcester label in `e9-results.md` and in
  `status.md` stays unconfirmed.
- Files kept for the open-ground re-check: `lean2/{southend_t,ferry_t}.npz` and `*_obs.pkl`,
  `lean2/fits.py`, `c6/gate.py`, `s0b/lean.py` (imported by `lean2/fits.py`), all under
  `uncommitted/scratch-archive/`.

## Esri scene polygons by one query (2026-10-26)

- `World_Imagery/MapServer/4/query` with an envelope (`geometryType=esriGeometryEnvelope`,
  `inSR=4326`, `outFields=*`, `returnGeometry=true`, `outSR=4326`, `geometryPrecision=6`,
  `maxAllowableOffset` 1e-4 to 5e-4 degrees to keep the response small, `where` URL-encoded as
  `MinMapLevel<=Z AND MaxMapLevel>=Z`) returns every scene footprint of a 5 km area in one request
  (15 polygons, below the 100-record page; `resultOffset` paging works for dense areas). VERIFIED
  live.
- It is more complete than T0's 13 x 13 identify grid: 5 small slivers the grid missed.
- Fields: `OBJECTID`, `SRC_DATE` (YYYYMMDD), `SRC_RES`, `SRC_ACC`, `SRC_DESC` (sensor),
  `MinMapLevel`, `MaxMapLevel`, `DrawOrder`, `BlockName`, `ReleaseName`.
- Overlap: the footprints of one zoom level are disjoint (T0 area: 14 Vivid polygons, pairwise
  overlap at float noise; Auckland, about 0.01 m2), so no draw-order rule is needed. The winner at
  zoom z is the polygon with `MinMapLevel <= z <= MaxMapLevel` containing the point. Identify
  ignores zoom and also returns TerraColor. UNVERIFIED: that a higher `DrawOrder` draws on top.
- MultiPolygons with holes occur; test points with even-odd fill. Cache footprints with the
  release name, which changes (here `DYNAMIC_ESRI_Leeds_25Q3`).

## Lean2: conditioning of the joint fit (2026-10-29)

Scratch: `uncommitted/scratch-archive/lean2/` (`results.md`, `results_tables.md`, `progress.log`,
`*_results.json`, `*_obs.pkl`, `fits.py`, `prep2.py`; `southend_t.npz`, `ferry_t.npz` and their
`*_obs.pkl` are inputs of the open-ground re-check in
`metric-bias-audit.md`). Declared 2026-10-26, run 2026-10-29. Every
fit is soft-L1, `f_scale` 1 m, per dominant Esri scene; k = |l| in m per m, the Maxar cap is
tan 30 = 0.577. Bootstrap: 300 draws over roofs and 4 x 4 window blocks, F0 to F2 only.

| Fit | Definition |
| --- | --- |
| F0 | roofs only, joint (t, l), the lean-fit baseline |
| F1 | roofs plus all reliable registration windows, equal weight per observation |
| F2 | F0 plus the ground-registration median as a pseudo-observation of t: (t - t0) / sd, sd the block-bootstrap interval / 3.92 in quadrature with 0.4 m |
| F3 | F0 centred on the mean roof height (the same fit, t reported at h-bar instead of h = 0) |
| F4 | alternation of 5 iterations from l = 0, t starting at the raw-image window median; window threshold fixed from the raw image |
| F5 | whole-image Powell fit of (t, l) on the gradient NCC; l in units of 0.1 m per m |

Boxes: southend_t (BNG 587000, 185000; EA aerial 2024-06; truth +0.23, +1.57), ferry_t (448500,
423500; aerial 2020; truth -0.31, +0.71) and southend_l (588300, 186400; the lean box of the
four-site fit, no truth). Scenes are grouped by date plus sensor: southend_t is 20250712 GE01
(polygons 3297692 and 3298659 fitted as one), ferry_t 20250716 LG01 (polygon 4146033).

| Box | Components over 3 m | Passed building tests | Roofs in scene (h, mean) | Reliable windows (threshold) | Ground prior t0 (sd) |
| --- | --- | --- | --- | --- | --- |
| southend_t | 714 | 52 | 13 (3.2 to 16.1 m, 5.0) | 13 of 900 (0.0955) | +0.45, +2.12 (0.61, 0.48) |
| ferry_t | 667 | 162 | 20 (3.4 to 6.7 m, 4.3) | 63 of 900 (0.0880) | -0.46, +0.26 (0.41, 0.51) |
| southend_l | 1110 | 184 | 23 (3.0 to 8.4 m, 5.1) | 17 of 900 (0.0826) | +0.23, +0.75 (0.82, 0.88) |

Per fit (t E, N in m; |err| is the distance of t from truth; k 95 % and t sd from the bootstrap;
roof residual is the median |offset - t - l h| of the accepted roofs; closure is the median
|offset| of roofs re-matched on the corrected image, n the roofs accepted then):

| Box | Fit | t E, N | \|err\| | az | k (95 %) | t sd E, N | Roof residual | Closure (n) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| southend_t | F0 | +0.60, +2.40 | 0.91 | 210 | 0.424 (0.37 to 1.09) | 0.28, 1.13 | 0.64 | 0.89 (16) |
| | F1 | +0.49, +2.62 | 1.08 | 207 | 0.438 (0.39 to 0.75) | 0.44, 0.43 | 0.72 | 0.83 (15) |
| | F2 | +0.54, +2.23 | 0.73 | 210 | 0.403 (0.30 to 0.55) | 0.24, 0.32 | 0.59 | 0.80 (14) |
| | F4 | +0.46, +1.77 | 0.30 | 212 | 0.448 | | 0.77 | 1.04 (13) |
| | F5 | +0.38, +2.12 | 0.57 | 208 | 0.326 | | 0.88 | 0.70 (16) |
| ferry_t | F0 | -1.37, +5.79 | 5.19 | 172 | 1.128 (0.21 to 2.32) | 0.95, 3.83 | 1.99 | 0.52 (51) |
| | F1 | -0.46, +0.65 | 0.16 | 192 | 0.148 (0.05 to 0.53) | 0.29, 0.55 | 2.93 | 2.84 (29) |
| | F2 | -0.57, +0.46 | 0.36 | 354 | 0.146 (0.04 to 0.71) | 0.11, 0.91 | 2.45 | 3.15 (23) |
| | F4 | -0.01, +0.09 | 0.69 | 327 | 0.286 | | 2.41 | 3.55 (21) |
| | F5 | -0.60, +1.65 | 0.98 | 180 | 0.477 | | 3.06 | 2.18 (37) |
| southend_l | F0 | +0.25, +3.54 | no truth | 193 | 0.538 (0.25 to 0.85) | 0.30, 1.01 | 0.98 | 0.94 (24) |
| | F1 | +0.76, +1.52 | no truth | 227 | 0.288 (0.20 to 0.51) | 0.47, 0.57 | 0.74 | 1.92 (23) |
| | F2 | +0.24, +2.44 | no truth | 200 | 0.364 (0.20 to 0.67) | 0.33, 0.85 | 0.86 | 1.24 (30) |
| | F4 | +0.01, +1.20 | no truth | 232 | 0.256 | | 1.02 | 1.75 (24) |
| | F5 | +0.17, +1.90 | no truth | 204 | 0.324 | | 0.58 | 1.36 (27) |

- Ground error |err| (southend_t / ferry_t / mean): F0 0.91 / 5.19 / 3.05; F1 1.08 / 0.16 / 0.62;
  F2 0.73 / 0.36 / 0.55; F4 0.30 / 0.69 / 0.50; F5 0.57 / 0.98 / 0.78. F2 is the only fit under
  0.8 m at both truth boxes; the owner chose it. The southend_l F0 t reproduces the four-site fit
  (+0.25, +3.54); F1, F2, F4 and F5 there give tN 1.52, 2.44, 1.20, 1.90, nearer the southend_t
  truth tN of +1.57 for the same scene, which is consistent with a biased F0 tN and is not truth.
- F0 fails at ferry_t: k 1.128 is above the cap, the roof residual is 1.99 m and the tN bootstrap
  sd 3.83 m, with roofs spanning only 3.4 to 6.7 m. The same fit at southend_t has tN sd 1.13 m.
- F3: the bootstrap sd of t at the mean roof height is 0.12 / 0.40 (southend_t), 0.22 / 0.89
  (ferry_t) and 0.13 / 0.30 (southend_l) against 0.28 / 1.13, 0.95 / 3.83 and 0.30 / 1.01 at
  h = 0. The t at mean roof height: southend_t (-0.46, +0.58), ferry_t (-0.66, +1.02), southend_l
  (-0.38, +0.85). The extrapolation to the ground is the poorly conditioned quantity.
- F4 does not converge. southend_t, dt per iteration 0.24, 0.27, 0.18, 0.23, 0.80 m with 20, 18,
  22, 22, 21 windows; ferry_t 0.19, 1.29, 1.25, 0.20, 0.05 m with 45, 43, 53, 39, 48; southend_l
  1.03, 0.20, 0.18, 0.31, 0.71 m with 25, 22, 29, 18, 23. The window set changes with the warp, so
  the answer depends on the stopping iteration.
- F5 gradient NCC before to after: southend_t 0.1514 to 0.1583 (262 Powell evaluations), ferry_t
  0.1454 to 0.2131 (231), southend_l 0.1444 to 0.1836 (220).
- Bootstrap k intervals that reach above the cap 0.577: F0 southend_t (to 1.09), F0 ferry_t (to
  2.32), F0 southend_l (to 0.85), F1 southend_t (0.39 to 0.75), F2 ferry_t (to 0.71), F2
  southend_l (to 0.67). No point estimate except F0 at ferry_t exceeds the cap.
- Windows are scarce under the declared null threshold: 13, 63 and 17 of 900. F1 is mostly roofs
  at southend and windows-dominated at ferry_t (63 windows against 20 roofs), which is why F1 is
  excellent at ferry_t (0.16 m) and weak at southend_t (1.08 m).
- Uncorrected closure (median |offset| of re-matched roofs on the raw image): southend_t 1.15,
  ferry_t 2.84, southend_l 1.07 m. Closure values are not comparable across fits because n changes
  with the correction.
- Truth sensitivity (Esri against the EA aerial, windows): southend_t all 233 windows (+0.28,
  +1.42), within 0.15 m of the published truth; raised fraction under 5 % (nDSM above 2.5 m over
  each 256 px window) n = 12, (+0.92, +2.67). ferry_t all 67 windows (-0.26, +0.53); raised
  fraction under 5 % n = 2, (-0.31, +1.19). The truth is reliable to about 0.2 m for the
  all-window estimate; the lean-free subset at southend_t is 1.1 m north of it on 12 windows.
- `southend_l.npz` (no truth) is regenerated by `prep2.py` in about 12 minutes with cached Esri
  tiles; `southend_t.npz` and `ferry_t.npz` are the saved inputs of the open-ground re-check.
- The ground prior t0 is itself 0.55 m (southend_t) and 0.45 m (ferry_t) from truth in N, which
  bounds F2's accuracy.

## C1/C2 build (2026-10-29)

Code, staged and not committed: `satmesh_data/esri_scenes.py` (C1), `satmesh_eval/roofs.py` and
`satmesh_eval/scene_lean.py` (C2), `EsriClient.query_citations`, `shapely` declared in
`satmesh-data` (already locked through geopandas). Tests: 9 for scenes, 2 for roofs, 10 for the
fit; 219 pass in all.

C1, scene footprints:

- One geometry-free query (`outFields=OBJECTID,ReleaseName`) names the release, then the footprints
  come from `~/.cache/satmesh/esri-world-imagery/scenes/<release>/<WGS84 bounds>-z<zoom>.json` or
  one geometry query (`maxAllowableOffset` 1e-5 degrees, `orderByFields=OBJECTID`, paged by
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
  geodetic, rounded to the grid, 0.01-step tolerance), its h from that position's ODN height
  (OSGM15) minus the node's ground GeoTIFF at the node; skirts take the h of the vertex above. New
  UV = base grid UV + uv(p + d) - uv(p), p the vertex's BNG position and uv() the exact BNG to Web
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

## C5: lean-corrected render review (2026-10-29)

Scratch: `uncommitted/scratch-archive/c5/` (scripts, `progress.log`, `work/consistency.json`,
`work/ground_store.json`, page `index.html`, 2.7 MB; the artifact URL was not recorded). Inputs:
the `c3c4` Southend 0.79 km stores. The page was built in about 10 minutes (19:54 to 20:04) and
holds 19 roof strips and 3 ground crops. Render: 1,415,348 triangles, coverage 0.9289, 3164 x 3156
px at 0.25 m. Renders A (ground shift only) and B (lean-corrected) are compared with Esri-direct.

Subject rule, fixed before any result: the 8 tallest accepted GE01 roofs by eave height (tall); the
4 GE01 roofs with the largest matcher offset on render B, a roof the matcher rejects on B ranking
worst (worst); buildings the matcher rejects on the Esri-direct luma at positions 1, 11, 21, ... in
footprint id order, up to 6 (unfiltered); the 3 accepted roofs in the WV02 area (not corrected).
Store ids: tall 35, 25, 59, 38, 42, 13, 53, 36; worst 35, 25, 40, 45; unfiltered 0, 10, 21, 33, 50,
66; WV02 62, 63, 64. The store has 80 buildings; the production matcher on the Esri-direct luma
accepts 16 (13 GE01, 3 WV02), as in production.

- Ground-window rule, 3 amendments recorded in the log: the absolute thresholds (nDSM variance at
  most 0.0225 m2, 90 % of pixels under 0.5 m) gave no candidate, since the lowest window variance
  in the store is 0.023 m2 and only 2 windows have 90 % of pixels under 0.5 m, so the candidates
  became the covered windows in the lowest decile of nDSM variance; 40 m windows had variance 2.4
  to 3.3 m2 and were a third to half roofs or trees, so display windows became 20 m; single 64 m
  windows then gave phase-correlation shifts of up to 18 m on dense roofs, so the ground check
  became the production store-wide measurement and the three crops are for the eye only.
- Render check: the best-fit shift of render B's ground pixels against the shifted-by-t render A is
  (+0.05, +2.10) against the stored t (+0.07, +2.13), 0.03 m apart (limit 0.25); luma RMS 36.5
  unshifted to 5.6 shifted (2,899,346 ground pixels).
- Store-wide ground registration, windows reliable on Esri-direct (11 of 529); median E, N in m:
  Esri-direct (-0.01, +2.10) from 11 windows; A, ground shift only (-0.09, +2.92) from 10; B,
  lean-corrected (+0.10, +1.25) from 7. Taking every window reliable on each image separately gave
  direct (-0.01, +2.10) n 11, A (-0.52, +2.47) n 8, B (+0.50, -0.71) n 11 (GE01 only: A (-0.00,
  +3.45) n 7, B (+0.63, -0.76) n 10).
- The 11 per-window north shifts on Esri-direct are +4.00, +1.49, +2.10, +1.99, +3.02, +2.56,
  +2.54, +1.22, +1.26, -9.27, +6.40 m; east shifts run from -3.97 to +5.24 m. The median is
  stable but nine windows span 1.2 to 4.0 m and two are far outliers, so the check is noise, as
  `metric-bias-audit.md` says. B's median N is 0.85 m below direct's and A's 0.82 m above. The
  "Southend over-correction" rests on these 11 of 529 windows with north from -9.27 to +6.4 m, not
  on a documented eye judgement.
- Kept for the open-ground re-check: `lean2/{southend_t,ferry_t}.npz` and `*_obs.pkl`,
  `c6/gate.py`, `s0b/lean.py`; the C5 `work/` pickles and arrays are not inputs of it.
- Consistency blocks (n = 31): B(p) = A(p + d) gives median N +1.93 m, sd 0.74 m (E +0.05, sd
  0.03); A(p) = direct(p + d) gives median (-0.06, +0.06) m, sd about 0.02 m.

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
| Ferrybridge T | -0.31, +0.71 | -0.57, +0.46, 0.36 m | 30 (63) | -0.21, +0.64, 0.12 m | -0.37, +1.13, 0.42 m | rejected (radius 0.59 above 0.29) |

- Both boxes get worse (+0.22 m and +0.06 m); the window half of the gate passes.
- At Southend de-leaning moves the window median 0.4 m further north of truth, the direction of
  the C5 overshoot (matcher north +0.43 to -0.51 m), so the ground prior's bias there is not
  explained by lean inside the windows.
- At Ferrybridge the de-leaned window median alone is 0.12 m from truth, but the roofs pull the
  refit to +1.13 N; the de-leaned windows halve (63 to 30), widening the prior.
- Info, not gated: keeping the raw-image threshold gives 19 and 43 windows and refit errors 0.97
  and 0.70 m (window medians t0 (+0.84, +2.46) at Southend and (-0.33, +1.02) at Ferrybridge,
  refit t (+0.72, +2.41) and (-0.46, +1.39)).
- Null-response thresholds: de-leaned 0.0761 against raw 0.0955 at Southend (13 to 38 windows),
  0.0979 against 0.0880 at Ferrybridge (63 to 30). Refit l at Southend (-0.206, -0.374) against
  F2 (-0.204, -0.347); at Ferrybridge (-0.060, -0.023) against (-0.016, +0.145). Logged times
  after baseline, de-leaned registration, refit and info variant: 1, 5, 7, 10 s at Southend; 2,
  6, 8, 12 s at Ferrybridge.
- The window count rises at Southend (13 to 38) and halves at Ferrybridge after de-leaning, as
  lean2 F4 saw 18 to 25 windows change per iteration: the reliable set is sensitive to the warp,
  so a de-leaned prior averages over different windows than the raw one.

Traps: `SceneId.capture_date` is a `date`; lean2's scene strings carry `YYYYMMDD`, which pydantic
does not parse as a date.
