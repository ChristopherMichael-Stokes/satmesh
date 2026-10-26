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
