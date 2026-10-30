---
status: historical
topic: position-correction
summary: Results of lidar-referenced registration B0 to B2: intensity present at all boxes, but within 0.3 m of EA aerial at only 4 of 8 boxes against 5 planned
answers: Does EA lidar intensity work as a registration reference for Esri; How accurate was lidar-referenced Esri registration against EA aerial; Why did the correction fail at urban and wooded boxes; Why were MI and nDSM references rejected
---

# E2 results: lidar-referenced registration (B0 to B2)

Plan: `e2-plan.md`. Truth: Esri against EA aerial from `offset-survey.md`, re-measured at 1 km where
the lidar run used 1 km. Positive east and north mean Esri is displaced east and north.

## Conclusions

- B0 passes: all nine EA lidar tiles under the eight boxes carry intensity, at 1.8 to 3.7 points/m2.
- B2 misses its criterion: gradient-of-intensity registration is within 0.3 m of the EA-aerial
  offset on both axes at 4 of 8 boxes; the plan asked for 5 of 8.
- The four misses are the urban, wooded and floodplain boxes, where only 21 to 31 of 900 windows
  survive (Snettisham has 155 and misses by 0.08 m on the north axis).
- Raw intensity and the surface gradient were worse overall; nDSM gave too few textured windows.

## B2 table (gradient of first-return intensity as the reference)

| Box | Area | EA-aerial truth E, N m | Lidar-referenced E, N m | Windows | Error E, N m | Within 0.3 m |
| --- | --- | --- | --- | --- | --- | --- |
| 8 Ferrybridge | 1 km | -0.34, +0.99 | -0.41, +1.25 | 60 of 900 | 0.07, 0.26 | yes |
| 7 Upper Aire | 1 km | -0.02, +0.76 | -0.26, +0.98 | 61 of 900 | 0.24, 0.22 | yes |
| 6 Belford | 500 m | -0.59, +0.94 | -0.52, +0.91 | 82 of 196 | 0.07, 0.03 | yes |
| 5 Neston | 500 m | +0.46, +1.40 | +0.36, +1.21 | 48 of 196 | 0.10, 0.19 | yes |
| 3 Snettisham | 1 km | -0.32, +2.29 | -0.28, +2.67 | 155 of 900 | 0.04, 0.38 | no |
| 4 Loughborough | 1 km | +0.77, +0.74 | +1.00, +1.25 | 23 of 900 | 0.23, 0.51 | no |
| 2 Southend | 1 km | +0.23, +1.57 | -0.14, +1.01 | 21 of 900 | 0.37, 0.56 | no |
| 1 Dunster | 1 km | -0.34, +0.18 | -0.67, +1.27 | 31 of 900 | 0.33, 1.09 | no |

- Raw intensity at the 1 km boxes: Snettisham -0.28, +2.05 (60 windows, error 0.04, 0.24);
  Loughborough +0.52, +0.53 (41 windows, error 0.25, 0.21); Southend -0.21, +0.84 (25); Dunster
  -0.52, +0.33 (24). Choosing the better reference per box by its error would use the truth, so the
  table fixes the gradient reference in advance.
- Dunster's own truth is weak (51 of 900 windows, interval spanning zero), so its error is not
  informative.
- Every 95 % interval at the failing boxes is wide (Loughborough north +0.25 to +1.96).
- Where it works, the lidar-referenced shift removes most of the offset; where it misses, the
  residual is 0.4 to 0.6 m against offsets of 0.7 to 2.3 m, except Dunster.

## Method

`/survey/b12.py` (scratch, not in the repo): first returns (noise class dropped) within the box plus
20 m, linear interpolation to the 0.25 m BNG grid, cells more than 1.5 m from any point masked,
robust 1st to 99th percentile scaling to 0 to 255, Gaussian sigma 1 px then Sobel gradient
magnitude. Registered against Esri luma by `measure_offset` unchanged (phase correlation, 256 px
windows, null-response threshold), Esri at z18 (z19 at Dunster).

## Traps

- The portal lists Neston's 2019 national-programme tile with a download link that returns 404.
  The older `lidar_point_cloud` product for 2023 downloads (nine 2 km LAZ files, LAS 1.4 point
  format 6).
- The first byte of a LAZ download arrives about two minutes after the request; the zip is 112 to
  492 MB per 5 km tile (Dunster and Loughborough, 2022, 3.4 to 3.7 points/m2, are the largest).
- Intensity is not calibrated between surveys: median 26 to 477. Gradient phase correlation is
  scale-free, which is why it is used.
- Esri capture-date polygons split two boxes: Neston (2025-05-18 and 2025-06-26) and Upper Aire
  (2025-03-18 and 2023-05-27). The block name (`DYNAMIC_ESRI_...`) is not the unit that matters.
- The 500 m slice truth is noisy: Snettisham reads +2.78 m north on a 500 m slice (28 windows) and
  +2.29 m on 1 km (165 windows).

## B2 with mutual information

Windowed MI as the plan specifies when gradient correlation fails (Parmehr et al. 2013): 128 px
windows on a 0.5 m grid (64 m, as before), integer shifts within +-6 m, 16 rank bins, parabola
subpixel, windows kept above the 99th percentile of the peak z-score between unrelated windows.
Brute force in numpy, scratch only; it recovers a synthetic 2.00 m east, 1.00 m north shift under
inverted, nonlinear contrast. Errors are against the truth column of the table above.

| Box | Truth E, N m | MI intensity E, N m (windows) | Error E, N m | MI intensity + nDSM E, N m (windows) |
| --- | --- | --- | --- | --- |
| 8 Ferrybridge | -0.34, +0.99 | -0.67, +1.15 (5) | 0.33, 0.16 | same |
| 7 Upper Aire | -0.02, +0.76 | +1.39, -2.40 (17) | 1.41, 3.16 | -1.12, -2.89 (28) |
| 6 Belford | -0.59, +0.94 | -0.48, +1.00 (44) | 0.11, 0.06 | same |
| 5 Neston | +0.46, +1.40 | +0.40, +1.46 (13) | 0.06, 0.06 | +0.37, +1.43 (17) |
| 3 Snettisham | -0.32, +2.29 | -0.18, +3.50 (10) | 0.14, 1.21 | same |
| 4 Loughborough | +0.77, +0.74 | +0.46, +2.43 (9) | 0.31, 1.69 | +0.61, +2.90 (10) |
| 2 Southend | +0.23, +1.57 | -0.02, +2.42 (47) | 0.25, 0.85 | -0.03, +2.42 (47) |
| 1 Dunster | -0.34, +0.18 | -0.75, +2.44 (12) | 0.41, 2.26 | -0.52, +3.33 (12) |

- MI is worse than gradient correlation: within 0.3 m on both axes at 2 of 8 boxes (Belford,
  Neston) against 4 of 8, and it is wrong by 0.9 to 3.2 m on the north axis at five boxes.
- nDSM alone gives the wrong answer where it has windows (Upper Aire: -1.43, -3.07) and almost no
  windows elsewhere; adding it to intensity does not fix any box.
- The north bias at the urban and coastal boxes is one-sided (+0.85 to +2.3 m), not noise, so it
  is not a window-count problem. Cause not found; a lean of the satellite image at the edges of
  buildings and trees against lidar surface features is a candidate (untested).

## Shipped: `satmesh correct` (2026-10-26)

Owner chose gradient correlation applied where enough windows survive, with an error bound.

- Code: `satmesh-data` `ea_lidar_points.py` (5 km point-cloud tiles, 404 fallthrough),
  `satmesh-eval` `lidar_reference.py` and `registration.py`, `satmesh-tiles` `correction.py`
  (schema, in-place UV shift, `positional_error.json`), `satmesh-mesh` `shift_texture_coordinates`,
  CLI `satmesh correct`; exports write `positional_error.json`.
- Cells: the store's BNG footprint is cut into near-equal cells with sides of 0.5 to 1.5 km; fixed
  1 km cells left slivers at the area's edge whose nodes would have been wrongly uncorrected.
- Rule: a cell is corrected if reliable windows are at least 5 % of its windows and at least 20.
  Eight survey cells split at 3.4 % or less (failed) and 6.7 % or more (passed). Tuned on the same
  sites it was scored on.
- Bound: quadrature sum of the bootstrap half-widths and 0.4 m (the largest error of a corrected
  cell at the survey sites, Snettisham, 0.38 m). Uncorrected cells carry 2.8 m, the largest
  displacement seen.
- Applied by shifting texture coordinates in the node GLBs and recording the shift in the node
  record, so a repeat or a revised field moves nodes by the difference only.

End-to-end on the 500 m survey stores, top-down render against the EA aerial (before, after):

| Site | Before E, N m | After E, N m | Bound m |
| --- | --- | --- | --- |
| Belford | -0.41, +0.77 | +0.15, -0.04 | 0.42 |
| Snettisham | -0.08, +2.47 | +0.21, -0.09 | 0.77 |
| Southend | +0.48, +1.44 | unchanged (uncorrected) | 2.8 |

Limits: England only; shift is constant per cell, so adjacent cells can differ by a few tenths of
a metre at their edge; the texture clamps at a node's edge, so a shift of metres leaves a strip as
wide as the shift at one side of each tile; capture-date polygons are not used (Neston and Upper
Aire straddle two); lean on raised objects is not corrected; Wales has no point-cloud source.
