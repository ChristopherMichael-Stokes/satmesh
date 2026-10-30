---
status: current
topic: process
summary: Where the project stands now, what is held or awaiting the owner, and where each workstream is documented.
answers: What is the project state today; what is running; what awaits the owner; what is paused and why; what comes next
---

# Status

State as of 2026-10-30. Decisions are in `decisions.md`, open risks in `risks.md`, the document
map in `INDEX.md`, the older narrative in `status-history.md`. Update this file at every
checkpoint; keep it to current state only.

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

## Workstreams

| Workstream | State | Next | Read |
| --- | --- | --- | --- |
| Baseline pipeline (`build`, exports) | Shipped for Great Britain: DSM visual mesh, DTM ground grid, 3D Tiles, Gazebo, GLB | Other regions (Yemen first), terrain past 6 km, Gazebo collision mesh and simulator test, real-photo test | `f5-results.md`, `region-research.md`, `risks.md` |
| Position correction (`correct`) | Shipped with ground shift and per-capture lean; stores for three 5.4 km areas corrected | Re-check on open-ground truth; Southend north overshoot; Wales and Scotland lidar | `e2b-results.md`, `metric-bias-audit.md` |
| Height refinement | M-A on the mean of Geopose and RS3DAda with a kriging base chosen; CHMv2 for trees; land-cover head built; E0 run and held; successor proposal written | E0 and E1 of the proposal, after the owner's go | `e4b-results.md`, `pixtransform-proposal.md` |
| ML workspace | `ml/` with `satmesh-height` (PixTransform port, kriging, cell adjustments, GeoTIFF contract) committed; PixTransform paused | Reopen only through the proposal | `e4b-results.md` |
| Knowledge store | Restructure in progress: index, headers, decisions, risks; scratch audited, extraction done | Owner checks no information is lost, then scratch is cleaned | `scratch-audit.md`, `INDEX.md` |

## Held or awaiting the owner

- The go for E0 and E1 (the tidy and restructure come first; E0 already ran and is held).
- Scratch cleanup: the deletable list is in `scratch-audit.md`; nothing is deleted.
- Whether GPL-3 tools (roofer, CGAL, lidR) are acceptable if satmesh is distributed
  (`semantic-height-research.md`).
- Policy call: keep or drop vehicles lifted from the photo that the older lidar lacks.

## Running

Nothing. Scratch inputs the next stage reads: `uncommitted/e4b/` (stores, `seg/`, `m1/pred`, `e0/`),
`uncommitted/scratch-archive/e4/` (trial inputs, `out/`, scorer, renderers) and
`uncommitted/models/` (RS3DAda and Geopose weights, CHMv2 tiles).

## Working principle

Judge meshes by eye. Scores against the DSM did not predict the owner's ranking in E8, and in E4
RMSE ranked PixTransform last while the owner judged it by far the closest at x30. The lidar and
the Esri image differ in lean, registration, capture date and edge smearing, so height scores
cannot be trusted as a verdict on any method that takes shape from the image. Show textured
renders from fixed camera views before proposing a geometry change.
