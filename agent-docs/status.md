---
status: current
topic: process
summary: Where the project stands now, what is held or awaiting the owner, and where each workstream is documented.
answers: What is the project state today; what is running; what awaits the owner; what is paused and why; what comes next
---

# Status

State as of 2026-10-31. Decisions are in `decisions.md`, open risks in `risks.md`, the document
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
| Texture refinement | Parked: ESRGAN plus half of the original's fine band gave little visible gain on UK meshes in Blender; nothing in the store or `build` | Reopen only with sharper source imagery (NAIP, county flights, dated releases) | `texture-plan.md`, `texture-results.md` |
| Acceptance harness | H0 (Embree), H0b (wgpu `GpuRenderer`, 8 to 12 ms per 1280 x 960 frame) and H1 (references, SIFT and XFeat + LighterGlue, PnP solve) built, uncommitted; on the slice XFeat + LighterGlue recovers 6 of 8 poses within 0.25 m / 2 degrees against the full surface and none against bare earth or flat | H2: metrics, JSON report, review page, `satmesh eval localise`; H3 on the owner's photos; far-field parent tiles when a pose needs them | `harness-plan.md`, `harness-results.md` |
| Knowledge store | Restructured: `INDEX.md` generated from doc headers, decisions, risks and plan codes split out, `agent-docs` hook enforces headers; scratch audited and its facts extracted | Owner decides the scratch cleanup | `scratch-audit.md`, `INDEX.md` |

## Held or awaiting the owner

- Owner saw `uncommitted/regions/us-squares.blend`: "looks great, best DSM yet bar none". Also
  `us-ames-plano-portland.blend` (Ames partial at z21, Plano, Portland; not yet seen). Viewport
  clip end is 20 km in both. Older note, same file: (Denver, mountain, desert; one collection each,
  3 km apart; built with bpy, not yet seen in Blender). Yemen GLBs seen: okay, the mountain one
  very good, buildings and vegetation lack relief (the height work's target).
- Imagery: preview seen (`us-imagery-preview.md`); Esri stays the default. Open: per-build source
  and season selector with a NAIP adapter; first a read-only check of dated Esri releases and NAIP
  years per square. Texture refinement is in `TODO.md` Next.
- Built: Denver, mountain, desert, Plano, Portland (`uncommitted/regions/us-*/store`). Ames and
  Chicago are not built: the owner stopped building (`decisions.md`); partial Ames stores are scratch
  (`us-ames/store` at z21, `us-ames-z19/store` at the 30 cm cap). The 30 cm imagery cap is in
  `choose_zoom`. `make check`, `make test` and `make test-contract` pass; `make smoke-regions`
  builds Denver and Sana'a 100 m boxes in 72 s.
- Stale DSM windows without the provenance tag sit in
  `~/.cache/satmesh/usgs-3dep/ept-dsm-windows/` (early Denver attempt); delete or keep.
- E2 is parked (`decisions.md`, 2026-10-31): the larger training run does not start; code, checkpoint
  and inputs stay in `uncommitted/e2/`. Texture refinement is parked; the harness is the active workstream.
- The E2 forks in `e2-slice-plan.md` (real GLO-30 source, `noprior` control, second fold, per-tile
  fit, vehicle policy) were not answered.
- Whether to run the E1c controls (MMSR and PixTransform with the cell adjustment) before or after E2.
- Policy call: keep or drop vehicles lifted from the photo that the older lidar lacks.
- Leftovers of the private test area removal: only the Claude Code session transcripts in
  `~/.claude/projects/-home-chris-xfeat-dev-satmesh/*.jsonl` remain; the owner said not to touch
  them. The published "Steep Face Stretch" page is deleted.
- Pushing: the owner asked for a push of `4f5a311` and `0ce3b2a` (plus the earlier local commit);
  the permission check denied `git push`, so `main` is 3 commits ahead of `origin/main`. Push when
  allowed.

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
