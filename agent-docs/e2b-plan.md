---
status: current
topic: position-correction
summary: Plan for position correction in towns and woodland where `correct` leaves four of eight boxes unchanged; hypotheses H1 to H4 and stages T0 to T4
answers: Why does correct fail in towns and woodland; What causes the one-sided northward leftover bias; What stages T0 to T4 test the hypotheses; Can unmeasured cells borrow the shift of their Esri scene
---

# E2b plan: position correction in towns and woodland

> **Status note (2026-10-30).** The owner approved E2b on 2026-10-26; the lean correction (C1 to
> C4) is built and shipped in `correct`, C6 failed its gate. See `e2b-results.md`.

Builds on `e2-plan.md` and `e2-results.md`. Awaiting owner approval.

## Problem

`correct` leaves the imagery as it was in four of the eight survey boxes (Dunster wooded,
Southend and Loughborough urban, Snettisham fen and coast): 21 to 31 of 900 windows survive, below
the 5 % rule, and those boxes carry the 2.8 m bound. Their EA-aerial offsets are 0.2 to 2.3 m north.
The mutual-information and nDSM variants did not help, and the leftover bias was one-sided
(+0.85 to +2.3 m north), which points at a systematic cause, not noise. Candidate causes:

| Cause | Why it fits | Test |
| --- | --- | --- |
| H1 Windows hold roofs and crowns, whose image position is leaned and whose lidar position is not | Towns and woods are mostly raised objects | T1 |
| H2 The satellite lean is one direction per scene (`e2-research.md`, `[gap]`: no published fit on a basemap) | One-sided bias | T2 |
| H3 Leaf state and date differ between lidar and imagery in woods | Dunster: 5.4 years apart | T0 |
| H4 The shift is constant within an Esri source polygon (one scene) | Survey boxes differ between polygons, 0.2 to 2.8 m | T0 |

If H4 holds, an unmeasurable cell can take its shift from measured cells in the same scene, and
H1 to H3 matter less.

## Stages

| Stage | Work | Go criterion |
| --- | --- | --- |
| T0 | Run `correct` over one 5 x 5 km store (Ferrybridge and Knottingley: town, industry, farmland; lidar tile SE4520 is cached) and read the per-cell shifts from `run.log`; fetch the Esri source polygon (identify, with geometry) per cell; fetch EA aerial for 4 more 1 km cells there, including a town cell, as truth. Cost: about 28,000 Esri tiles, 50 min at 10 per second | Report: share of cells corrected; spread of corrected shifts within each polygon (is it under 0.3 m?); truth at the town cell |
| T1 | Ground-only windows: mask lidar and image pixels where the nDSM exceeds 2 m, grown by the lean allowance (the largest roof height times 0.3), and re-measure the four failing survey boxes and the town cell | Reliable windows at least 5 % in 3 of the 4 failing boxes, and within 0.3 m of truth where measured |
| T2 | Lean model, only if T0 and T1 leave cells unmeasured. Fit direction and metres of lean per metre of height per scene (two parameters) from object windows, then register against a lidar reference whose points are moved by the predicted lean. Prior-art check first (satellite off-nadir displacement from a DSM, RPC orthorectification) by a research subagent | Held-out object-window residual falls against the shift-only fit; then within 0.3 m of truth at the failing boxes |
| T3 | Borrow: where H4 holds, give each unmeasured cell the interpolated shift of measured cells in its polygon (RBF or kriging of the measured shifts), with a bound that adds the spread among them | Within 0.3 m of truth at the town cell and at two held-out measured cells |
| T4 | Wire the winners into `correct` (cells keep the 5 % rule, the new paths set the status and bound), results doc, status, TODO, `make check` | Output on the eight survey sites no worse than `e2-results.md` |

Order: T0, then T1 and T3 in parallel on its data, T2 last. T2 is the only stage that is not an
established method; the plan stops there and returns to the owner if it is needed.

## What each outcome means

- H4 true: T3 alone raises coverage cheaply, with an honest wider bound where borrowed.
- H4 false (shift varies inside a polygon): borrowing is unsafe; T1 and T2 must carry it, and the
  uncorrected bound stays for what they cannot reach.
- Wooded cells may stay unmeasurable under every option (no ground visible); they then take the
  borrowed value or the 2.8 m bound.

## Decisions for the owner

1. T0 region: Ferrybridge and Knottingley (proposed, caches exist), or another site.
2. Accuracy threshold: 0.3 m, as before.
3. Whether T2 may proceed to implementation after the prior-art check, or comes back to you first
   (proposed: comes back first).
4. Borrowed cells: reported as `borrowed` in `positional_error.json` with their own bound
   (proposed), or folded into `corrected`.

## Costs and traps

- Esri polygons straddle some boxes (Neston, Upper Aire); T0 handles a cell split by a polygon
  edge by measuring each side separately or marking the cell mixed.
- EA aerial has its own lean, so object windows against it mix two leans; truth is scored on open
  ground.
- `correct` over 25 cells needs about 15 GB of memory at 8 workers.
