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
| Baseline pipeline (`build`, exports) | Shipped for Great Britain; region registry built (R0: Sana'a, Shibam) and R1 US 3DEP built: Denver, mountain and desert 2 km squares build and export, uncommitted | Exporters to carry provenance and attribution; R2 polish and merge; then terrain past 6 km, Gazebo collision mesh, real-photo test | `regions-plan.md`, `regions-results.md`, `regions-r1-results.md`, `us-sources.md`, `risks.md` |
| Position correction (`correct`) | Shipped with ground shift and per-capture lean; stores for three 5.4 km areas corrected | Re-check on open-ground truth; Southend north overshoot; Wales and Scotland lidar | `e2b-results.md`, `metric-bias-audit.md` |
| Height refinement | M-A on the mean of Geopose and RS3DAda with a kriging base chosen; CHMv2 for trees; land-cover head built; E0 (masks) judged by the owner: acceptable coarsely, buildings become blobs, a Ferrybridge road is scooped, PixTransform recovers objects best; E1 dropped | E2: a model trained on England lidar (owner approved), slice first; E1c controls offered | `e4b-results.md`, `pixtransform-proposal.md`, `decisions.md` |
| ML workspace | `ml/` with `satmesh-height` (PixTransform port, kriging, cell adjustments, GeoTIFF contract) committed; PixTransform paused | Reopen only through the proposal | `e4b-results.md` |
| Knowledge store | Restructured: `INDEX.md` generated from doc headers, decisions, risks and plan codes split out, `agent-docs` hook enforces headers; scratch audited and its facts extracted | Owner decides the scratch cleanup | `scratch-audit.md`, `INDEX.md` |

## Held or awaiting the owner

- Old scratch stores: their node records use the previous field names and the exporters cannot read
  them. A key rename (reversible, in place over 4,000 small JSON files) was blocked by the
  permission check after it had already renamed `uncommitted/eval-slice` and `uncommitted/blind/store`.
  Decide: rename in place with `uncommitted/regions/migrate_records.py`, or rebuild when needed.
  Stores built under an older position schema (`t0`, `s0`, `scratch-archive/c3c4`) are stale anyway.
- Look at `uncommitted/regions/us-squares.blend` (Denver, mountain, desert; one collection each,
  3 km apart; built with bpy, not yet seen in Blender). Yemen GLBs seen: okay, the mountain one
  very good, buildings and vegetation lack relief (the height work's target).
- Imagery: preview seen (`us-imagery-preview.md`); Esri stays the default. Open: per-build source
  and season selector with a NAIP adapter; first a read-only check of dated Esri releases and NAIP
  years per square. Texture refinement is in `TODO.md` Next.
- Built: Plano, Portland (stores in `uncommitted/regions/us-{plano,portland}/store`); Ames is
  running (20,736 leaves at z21 from a 2.4 cm county flight, hours) and Chicago waits behind it
  (`uncommitted/regions/build_rest.sh`, status file beside it). Decide: cap Ames at a coarser zoom,
  let it finish, or skip it. Not done: exporter attribution and provenance. `make check`, `make test`
  and `make test-contract` pass; `make smoke-regions` builds Denver and Sana'a 100 m boxes in 72 s.
- Stale DSM windows without the provenance tag sit in
  `~/.cache/satmesh/usgs-3dep/ept-dsm-windows/` (early Denver attempt); delete or keep.
- E2 larger training corpus (about 30 random 2 km squares, 10 to 12 h unattended, 5-square dry run
  first): the owner greenlit it before the blind comparison, then E2 ranked behind `avg_ma` on the
  blind square (`e2-results.md`). Held until the owner says what the comparison means for it.
- The E2 forks in `e2-slice-plan.md` (real GLO-30 source, `noprior` control, second fold, per-tile
  fit, vehicle policy) were not answered.
- Whether to run the E1c controls (MMSR and PixTransform with the cell adjustment) before or after E2.
- Scratch cleanup: the deletable list is in `scratch-audit.md`; nothing is deleted.
- Whether GPL-3 tools (roofer, CGAL, lidR) are acceptable if satmesh is distributed
  (`semantic-height-research.md`).
- Policy call: keep or drop vehicles lifted from the photo that the older lidar lacks.
- Leftovers of the private test area removal (`decisions.md`): derived arrays under
  `uncommitted/scratch-archive/s0b/` (delete or keep), Claude Code session transcripts in
  `~/.claude/projects/-home-chris-xfeat-dev-satmesh/*.jsonl` (five files hold the name), and version
  1 of the published "Steep Face Stretch" page (only deletable by deleting the artifact).
- Pushing: `main` is 19 commits ahead of `origin/main` (local only; history was rewritten for
  the removal above); the owner pushes.

## Running

Nothing. The regions work (R0) and the E2 slice are built and uncommitted; the new files are staged
(`git add`) and nothing is committed. Scratch the height work reads (E2 slice and blind comparison):
`uncommitted/e2/` (inputs, pred, cond, krige, ckpt, `e2lib.py`, `train.py`, `infer.py`),
`uncommitted/blind/` (site, store, data, GLB tiles, `key.json`) and `uncommitted/regions/` (Sana'a
and Shibam stores and GLBs, `migrate_records.py`). The model environments the E2 and blind scripts
ran in sit in an ephemeral session scratchpad (`m1-research-a` and `-b`, `torchenv`) and will go;
recreate them from `m1-model-recipes.md`. Other scratch inputs: `uncommitted/e4b/` (stores, `seg/`,
`m1/pred`, `e0/`), `uncommitted/scratch-archive/e4/` (trial inputs, `out/`, scorer, renderers) and
`uncommitted/models/` (RS3DAda and Geopose weights, CHMv2 tiles).

## Working principle

Judge meshes by eye. Scores against the DSM did not predict the owner's ranking in E8, and in E4
RMSE ranked PixTransform last while the owner judged it by far the closest at x30. The lidar and
the Esri image differ in lean, registration, capture date and edge smearing, so height scores
cannot be trusted as a verdict on any method that takes shape from the image. Show textured
renders from fixed camera views before proposing a geometry change.
