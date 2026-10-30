---
status: current
topic: evaluation
summary: Audit of past rejections: Esri-to-EA truth is biased by roof and canopy lean, which may explain the C6 gate failure and the F0 to F5 ranking; ranks re-checks
answers: Were past rejections caused by a lean-biased truth; Why did RMSE against EA lidar rank PixTransform last; Does open-ground truth flip the Southend fit ranking; Which re-checks should run first; Which scores are judged safe
---

# Audit: past rejections that may come from a flawed reference

Audit by a strong-tier research subagent, 2026-10-30, of the project's own docs. Prompted by E4,
where RMSE against EA lidar ranked PixTransform last while the owner judged it by far the closest
at x30. Labels: [doc] stated in the cited doc and checked; [computed] arithmetic on printed
numbers; [inference] reasoning, not measured. Nothing was re-run.

## Main finding

Every position and lean fit was scored against a truth that lean biases. That bias may be what
caused the largest open "failures": the C6 gate, the Southend over-correction, and the lean2
ranking of F0 to F5.

- The truth is the median shift of Esri against the EA aerial over all phase-correlation
  windows, ground and raised alike (`e2b-results.md` "all windows, not open ground only";
  `lean2/results.md`). Windows holding roofs and trees carry Esri's lean, which at Southend points
  south-south-west (azimuth 193 to 212 deg, k about 0.4). The EA aerial also leans
  (`e2b-plan.md`). The truth is therefore pulled south of the ground shift every fit estimates.
- `e2b-plan.md` said truth is scored on open ground. That was not done.
- The project's own sensitivity check: at Southend, windows with under 5 % raised pixels give
  (+0.92, +2.67) against the published (+0.23, +1.57), 1.1 m further north, the way lean
  predicts. It rests on 12 windows (`lean2/results.md`) [doc].
- Against that open-ground truth the ranking flips [computed; the 12-window truth is thin]:

| Fit (Southend T) | t E, N | Error vs published truth | Error vs open-ground truth |
| --- | --- | --- | --- |
| F0 roofs only | +0.60, +2.40 | 0.91 | 0.42 |
| F1 | +0.49, +2.62 | 1.08 | 0.43 |
| F2 (chosen) | +0.54, +2.23 | 0.73 | 0.58 |
| F4 ("best", 0.30) | +0.46, +1.77 | 0.30 | 1.01 |
| F5 | +0.38, +2.12 | 0.57 | 0.77 |
| C6 de-leaned t0 | +0.50, +2.50 | 0.97 | 0.45 |
| C6 refit | +0.55, +2.46 | 0.95 | 0.43 (gate would pass at Southend) |

- Ferrybridge cannot settle it: its open-ground subset has 2 windows (-0.31, +1.19).
- Fits that share the truth's raised-object windows (F1, F2, F4) are rewarded; fits that push t
  to pure ground (F0, C6 de-leaning) are punished [inference].

## Rejected, closed or down-ranked items

| # | Item (doc) | Score and reference | Flaw and direction | Owner's eye? | Risk the rejection is wrong | Cheapest re-check |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | C6 de-leaned re-registration, failed its gate (`e2b-results.md` "C6 result") | \|t - truth\| at 2 boxes, all-window EA-aerial truth | Truth mixes ground with leaned roofs, pulled south at Southend; punishes a fit that removes lean | No | High: against open-ground truth the refit improves Southend 0.58 to 0.43 m | Re-measure truth on open-ground windows (bigger box for more windows); re-run `c6/gate.py` |
| 2 | Southend north overshoot (`status.md`; TODO, Later) | F2 t against the same truth | As 1: the overshoot is the size of the lean contamination | C5 page shown; its lidar-ground check is noise (11 windows, N from -9.27 to +6.4 m) | High that it is partly or wholly an artefact | Same truth; blink corrected Southend against EA aerial on kerbs and road markings only |
| 3 | lean2 F0 to F5 ranking; F2 chosen | \|t - truth\| at two boxes | Same bias; fit differences (0.05 to 0.3 m) sit inside the truth's 0.2 to 1.1 m uncertainty | Owner chose F2 from scores | Medium: F2 is reasonable, F0 and F1 not shown worse at Southend. F0 at Ferrybridge (5.19 m) is a real failure; F4 fails on non-convergence | Re-score saved fits (`lean2/*_results.json`) on open-ground truth; more truth boxes |
| 4 | E2 B2 "misses criterion" and the cell rule (5 %, 20 windows, 0.4 m bound) (`e2-results.md`) | Within 0.3 m of EA-aerial truth at 5 of 8 boxes; rule tuned on the same sites | 0.3 m is below the truth's own instability (Snettisham 2.78 vs 2.29 by box size, Loughborough +0.38 vs +0.74, Dunster interval spans zero); failing boxes are urban or coastal, where lean bias is largest | No | Medium-high: the rule leaves Southend, Loughborough and Dunster uncorrected (2.8 m bound) though correction cut error from 0.7-2.3 m to 0.4-0.6 m even against the flawed truth | Recompute per box on open-ground truth with its interval; compare corrected against uncorrected error |
| 5 | MI and nDSM registration rejected (`e2-results.md`) | Error vs aerial truth | MI's north bias at urban and coastal boxes points the same way as the truth's lean bias (Southend MI +2.42 N against open-ground +2.67) | No | Low-medium: MI also fails on moorland (Upper Aire 3.16 m) where truth is sound; nDSM superseded by the roof lean fit | Re-score MI at Southend and Loughborough on open-ground truth |
| 6 | Ferrybridge lean rejected (radius 0.62 > 0.29) (`e2b-results.md`) | Bootstrap radius of roof offsets, Esri vs EA DSM | Lidar 2020-12 to 2021-03 against Esri 2025-07-16 at an industrial site; changed buildings would inflate roof scatter (unverified) | No | Medium | Inspect the 20 roof strips for changed buildings; refit without them |
| 7 | E4 edge leakage "copies photo texture" (`e4-results.md`) | Mean \|grad h\| at Canny guide edges where lidar slope < 0.1 | Building edges displaced by lean, registration or date land on flat lidar ground and count as leakage; shadows are genuine leakage | Yes: x30 best, x2 and x5 worse | Medium at x30 (0.739 partly bias); low at x2 and x5 | Re-score only at edges beyond about 0.58 h_max + 1 m from any lidar nDSM > 2 m, shadows masked (saved outputs, CPU) |
| 8 | E4 PixTransform RMSE last | RMSE vs EA DSM | All four flaws | Yes, x30 overturned | Already re-judged | None beyond `e4b-plan.md` |
| 9 | E4 guided filter "worse than bilinear everywhere", absent from `e4b-plan.md` | RMSE | Takes shape from the image, so punished the same way; x30 RMSE 2.27 sits between bilinear 2.12 and PixTransform 2.33 | Panels and GLBs exist; no judgement recorded | Low-medium | Owner looks at the guided x30 panels and GLBs |
| 10 | E8 roof planes and raw-point Delaunay rejected by eye (`e8-results.md`) | Eye on textured and shaded renders; held-out test circular | Textured renders used Esri not corrected for lean (E8 predates C3/C4), so sharp walls expose texture misplacement that bilinear smoothing hides [inference]; the fair 90 % test favoured Delaunay by about 3x building NMAD; roof-plane failures were prototype flaws | Yes | Medium for roof planes, low-medium for Delaunay (shaded renders show spiky trees too) | Re-render roof planes and the current mesh with lean-corrected texture (`c3c4/l500`), plus shaded views |
| 11 | E2b T0, H4 "not supported" | Spread of cell shifts within a scene vs 0.3 m | Different raised fractions add lean spread to a constant ground shift | No | Low (superseded by per-scene pooling) | None |
| 12 | `e4-research-2.md` ranks Depth Anything / Marigold low | Published errors vs lidar nDSM | Literature shares the flaws | No | Low: still in the M1 sweep | Planned |
| 13 | `e4-research-2.md` gate "x30 RMSE no worse than kriging" | RMSE | Rewards smoothness | Owner decides (`e4b-plan.md`) | Low | Keep the plan's wording |
| 14 | Cubic 0.25 m and PCHIP resampling, never taken forward (`e8-results.md`) | DSM at pixel centres (circular for interpolants) | Score cannot credit detail | Not rendered | Low | GLB of cubic 0.25 m if E8 reopens |

## Bias the other way (rewards smoothness, DSM-identical output or circularity)

- E8 node-aligned bilinear and nearest 0.5 m: raised NMAD 0.000 is circular (scored at the DSM's
  own pixel centres). The eye rejected both for real terracing and voxel trees; sound.
- E4 kriging: best by RMSE because the reference rewards smoothness; fine as a base layer, not
  evidence of detail.
- lean2 F1, F2, F4: rewarded for sharing raised-object windows with the truth.
- Closure and self-consistency checks (lean2 closure, C5 "B vs A at t", C4 UV check, F6 pipeline
  check) verify the implementation, not accuracy; the docs mostly say so.

## Re-checks ranked

1. Open-ground truth (Esri against EA aerial on windows with nDSM at most 0.5 m, raised pixels
   masked with a lean margin, or a 2 to 5 km box for more than 12 windows); re-score lean2 F0 to
   F5 and the C6 gate. This also settles the Southend overshoot. Cached inputs and saved
   observations exist (`lean2/*_obs.pkl`, `c6/gate.py`); CPU only.
2. Re-derive the E2 cell rule and 0.4 m bound on that truth; per box, corrected against
   uncorrected error, with the truth's interval beside the 0.3 m criterion.
3. Re-score E4 edge leakage away from leaned and changed objects, shadows masked; the owner looks
   at the guided-filter x30 panels.
4. Inspect the Ferrybridge roof strips for buildings changed between 2021 and 2025; refit.
5. Re-render the E8 roof planes and the current mesh with lean-corrected texture, plus shaded
   views.
6. Re-score MI at the urban boxes on the item-1 truth.

## Judged safe

- S6 2.4 m offset retracted: cause identified (Helmert without OSTN15).
- Lower Aire dropped for the 2020 flood: the scene really differs.
- Nearest 0.5 m DSM sampling: eye and smoothness score agree.
- T1 ground-only windows: failed on the mask-edge artefact and too few windows.
- lean2 F4 (non-convergence) and F0 at Ferrybridge (k 1.13, sd of tN 3.8 m): internal failures.
- PixTransform's 17 m cell residual: measured against its own source.
- PixTransform last at x2 and x5: the eye agrees and a guide shift barely moves it.
- 99th-percentile null threshold: set from unrelated window pairs, not a reference; it keeps
  edge-rich windows, which carry lean (a selection effect). Validated at two sites.
- MAX_LEAN (tan 30) and the lean radius limit (tan 30 / 2): from the Maxar specification.
- MIN_ROOFS = 10: a count, not reference-tuned.
- E9 closure: an owner decision on view share, not a reference score.

## Too thin to judge

- The open-ground truth: 12 windows at Southend, 2 at Ferrybridge; its east component (+0.92)
  could be noise. Every flag above is a re-check, not a verdict, until re-check 1 is done.
- How much the EA aerial leans: unmeasured.
- Where the C5 overshoot was seen by eye: `c5/progress.log` holds only scores.
- Building change at Ferrybridge: not checked.
- The owner's view of the guided filter: not recorded.
