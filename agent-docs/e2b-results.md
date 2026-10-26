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
