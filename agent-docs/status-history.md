---
status: historical
topic: process
summary: Verbatim record of the status log before the restructure; the 2026-10-26 plan state, owner order and result rows.
answers: What was the owner order on 2026-10-26; what did E2b C1 to C6 conclude in the status log; what did the E4 and M1 result rows say
---

# Status history

Moved verbatim from the old `status.md` on 2026-10-30. Current state is in `status.md`; decisions
are in `decisions.md`; measurements live in the results docs.

## State against the plan (2026-10-26)

| Stage | State |
| --- | --- |
| 0 Scaffold | Done |
| 1 Spikes | S1, S5, S6 done. Open: S3, S4; S2, S2b, S7 on demand |
| 2 Baseline pipeline | F1 to F5a done for Great Britain (DSM visual mesh, DTM ground grid). Open: F2a, F2b, F5b Gazebo collision, F5c large-area DTM |
| 3 Evaluation harness F6 | Done (`f6-results.md`): height, smoothness, camera-visibility and held-out-point scores; Esri-to-EA offset and texture-detail spectrum; consistency function (library only); all behind `satmesh eval` |
| 4 Classical enhancement E1, E2 | E2 shipped as `satmesh correct` (`e2-results.md`); E2b (towns and woodland) planned in `e2b-plan.md`; E1 not started |
| 5 ML experiments E3 to E7 | Not started. E8 (lidar surface refinement) closed without a change. E4 survey done (`e4-research.md`), first trial PixTransform not started; E9 closed after S0 and S0b (`e9-results.md`), no fill built; owner priorities are E4 and E6 |

## Where to resume (as written 2026-10-30, before the restructure)

Owner order (2026-10-26):

1. E9 steep faces: closed by the owner after S0 and S0b (`e9-results.md`); no fill was built.
2. E2b towns and woodland, paused 2026-10-26 (usage). Lean correction in `correct` is approved by
   the owner ("C all day"; the lean-corrected strips beat as-published at most sites). Design from
   the strong-tier consult: per-vertex UV rewrite `uv_base + J (t + l h)` in node GLBs (JPEG
   untouched), one lean per Esri scene (date plus sensor) over the whole store, scene polygons from
   one layer-4 envelope query cached by release (`e2b-results.md`), schema `SceneLean`
   (applied or rejected), lean on by default, old corrected stores rejected with a rebuild message,
   stages C1 polygons, C2 library and tests, C3 measurement in `correct`, C4 application, C5 real
   flow with before/after strips and blink on an artifact page, C6 de-leaned ground registration.
   Open fork: owner prefers B (joint fit of ground shift and lean from roofs, as in the strips)
   over A (ground shift from ground registration, lean only from roofs) and asked to keep B
   "smartly". Research brief was running and was stopped unfinished: make the joint fit
   better conditioned (all registration windows regressed on mean height with ground windows
   anchoring t, tall objects, priors from neighbouring cells and k <= tan 30, roads and kerbs, de-leaned
   re-registration, centred regression with honest extrapolated bound). Resume: relaunch that
   research (scratch in `uncommitted/scratch-archive/lean2`), test offline on saved offsets with
   Southend truth (+0.23, +1.57), then decide the fit and build C1 onward.
   Lean2 result (2026-10-29, per-fit tables in `e2b-results.md` "Lean2: conditioning of the joint
   fit", source `uncommitted/scratch-archive/lean2/results.md`): ground error at
   Southend / Ferrybridge truth, F0 roofs only 0.91 / 5.19 m, F1 roofs+windows 1.08 / 0.16,
   F2 F0 + ground-registration prior 0.73 / 0.36, F4 alternation 0.30 / 0.69 (does not converge),
   F5 whole-image 0.57 / 0.98. F0 fails where roofs span only 3 to 7 m (extrapolation to h = 0).
   Owner chose F2 (2026-10-29), with k clamped to tan 30. Only two truth boxes; F2's 95 % k
   interval reaches 0.67 to 0.71 at two sites (cap 0.58).
   C1 and C2 built 2026-10-29, staged, not committed (`e2b-results.md`, "C1/C2 build"):
   `satmesh_data.esri_scenes` (scene footprints per release, labels per point or grid, shares)
   and `satmesh_eval.roofs` plus `satmesh_eval.scene_lean` (`SceneLean`, capped F2 fit). The
   production fit reproduces lean2 F2 exactly (Southend 0.73 m, Ferrybridge 0.36 m from truth).
   Ferrybridge's lean is rejected (95 % lean radius 0.62 m per m); whether a rejected-lean scene
   takes its F2 t with l = 0 or the per-cell shift (uncorrected there) is open for the owner.
   C3 and C4 built 2026-10-29, staged, not committed (`e2b-results.md`, "C3/C4 build"):
   `correct` pools roofs and reliable windows per Esri scene over the store, fits each scene and
   rewrites node UVs per vertex as base + J (t + l h) (exact BNG-to-texture map); schema 2, old
   corrected stores refused with a rebuild message; `--no-lean`; a rejected scene keeps the cell
   shift (lead's call). Bound B(h) = B_t + r_l h. Southend 0.79 km store: GE01 applied (13 roofs,
   11 windows, t +0.07 +2.13 m, k 0.34 toward 198, bound 1.16 m + 0.15 h), WV02 rejected (3 roofs);
   corrected UVs reproduce t and l exactly against independent DSM-DTM heights. Risks: tile-edge
   clamp smear (0.5 % of vertices) and seam stretch inside mixed nodes.
   C5 ran 2026-10-29 (`e2b-results.md`, "C5: lean-corrected render review"; page
   `uncommitted/scratch-archive/c5/index.html`, 19 strips): its lidar-ground check rests on 11 of
   529 windows with north from -9.27 to +6.4 m and is noise.
   C6 (one de-leaned re-registration pass, then one F2 refit) failed its declared gate on
   2026-10-29 and was not built (`e2b-results.md`, "C6 result"): ground error vs truth Southend
   0.73 to 0.95 m, Ferrybridge 0.36 to 0.42 m. The Southend over-correction seen in C5 stays open.
3. E4 trial: `e4-research.md` recommends PixTransform per tile, scored on the degraded EA DSM
   (x2, x5, x30) with an edge-leakage check; judge by eye as well.
   E4 trial run 2026-10-29 (`e4-results.md`, review page
   <https://claude.ai/artifact/6v1CiNcDK3SGErJ6jvixce>): PixTransform has the highest RMSE at x2
   and x5 on both sites and copies photo texture into relief (edge slope 0.30 to 0.74 against
   lidar 0.033 at Ferrybridge); area-to-point kriging is lowest everywhere (Ferrybridge x2 0.48 m
   against bilinear 0.57). Owner by eye (2026-10-29): PixTransform at x30 is visually closest to
   the lidar; at x2 and x5 bilinear and kriging trade blows. Next: `e4b-plan.md`, drafted, not
   run (Part 1: combinations A, B, C over 5.4 km areas; Part 2: metric-bias re-checks;
   Part 3: learned-height models); survey
   `e4-research-2.md` done (first trial RS3DAda nDSM plus mass-preserving composition; runner-up
   Geopose). GLBs of every surface in `uncommitted/scratch-archive/e4/glb/`. Every e4b script reads
   `scratch-archive/e4/` (`{ferry,aire}-inputs.npz`, `-texture.npz`, `out/`, `scores.json`,
   `score.py`, `render.py`, `make_page.py`, `glbs.py`, `vendor/`): do not clean it up. Kriging
   variograms, scorer strata and the degenerate Upper Aire fits are in `e4-results.md`.
4. Yemen as the different-region test (F2a source registry, UTM, geoid, coarse elevation). The
   source survey is `region-research.md`; its plan follows from that report.
5. F5b Gazebo collision, then F7 real-photo localisation (needs owner-supplied photographs with
   known poses; required before v1).

Done since the last record: `build` and `correct` speed-up with byte-identical output
(`speedup-results.md`), progress bars, `run.log` and `--nw`/`--se` corner input
(`progress-logging-input-plan.md`).

Judge meshes by eye: scores against the DSM did not predict the owner's ranking in E8, and in E4
RMSE ranked PixTransform last while the owner judged it by far the closest at x30. The lidar and
the Esri image differ in lean, registration, capture date and edge smearing, so height scores
cannot be trusted as a verdict on any method that takes shape from the image. Show textured
renders from fixed camera views before proposing a geometry change.

E4b state (2026-10-30): S0 built and staged, not committed (`ml/`, `satmesh_height`: PixTransform
port with chunked inference, indexed patches and GPU batches; variants A, B, C+B; kriging; GeoTIFF
contract; CLI `satmesh-height refine`; `make check`, `make test`, `make test-contract` pass). S1
done (above). S3 under way: EA coverage of the three areas has no nodata (Southend min -1.38 m);
slice path (1,080 m Ferrybridge block) built and corrected; the full 5.4 km builds run through
`uncommitted/e4b/areas.sh` (log `areas.out`), where the EA WCS answers a few requests with 403
mid-build and the script resumes the build (nodes done: 403 then 588 of 1,245 over two attempts).
Next: S2 (vendored-port check against the original on a 270 m tile, per-training time, C at the
540 m boxes), then S2b tuning once the tuning blocks' inputs exist.

## Result rows from the old decision table

| Date | Entry | Note |
| --- | --- | --- |
| 2026-10-30 | M1 phase 1 done (scratch `uncommitted/e4b/m1/`, tables in `m1/tables.txt`, review page <https://claude.ai/artifact/GBTiu16cvHBpbgkxC1GDL5>): RS3DAda (TTA and not), Geopose (folds 5 and 6, 4-flip TTA), CHMv2 (model, gated access granted, and global tiles), Depth Anything 3 Mono and Metric, V2 Small, zero-shot on the 540 m boxes at x5 and x30. By RMSE (secondary) only Geopose M-C and RS3DAda M-C beat kriging, at Ferrybridge x30 (1.68, 1.92 against 2.08); Upper Aire x30 ties (2.11 against 2.17); M-A equals kriging; M-B is much worse. Flat-ground edge slope stays above lidar for every height model (RS3DAda 0.27, Geopose 0.37 raw at Ferrybridge against 0.017). Depth models, fitted to height above ground (the first fit regressed on terrain elevation and gave negative scales), add nothing: M-A within 0.03 m of kriging, M-C worse. CHMv2 on the 0.25 m texture overpredicts canopy (open-ground RMSE 7 m); at 0.5 m better; global tiles best; all underpredict Ferrybridge trees by 3 to 4.5 m. M-C uses two tunables, gain floor 0.1 m and gain cap 3 (no source) | Zero-shot sweep; owner judges the renders |
| 2026-10-30 | Land-cover head built (`uncommitted/e4b/seg/`, results in `e4b-results.md`): leave-one-area-out building F1 0.73 to 0.82 against 0.16 to 0.32 for RGB, vegetation F1 0.14 to 0.31, no water class in the lidar. Next per the proposal (`pixtransform-proposal.md`, approved by the owner): E0 masked anomaly surface, then E1 per-image correction | Owner approved merging the PixTransform and height-model tracks and E0, E1 |
| 2026-10-30 | E0 ran early (before the owner's go; the tidy was to come first) and is held: results are in `e4b-results.md`, nothing rendered, no next stage started. Masks help at Ferrybridge x30 (RMSE 2.29 to 1.72) and little elsewhere; per-class gains unusable; Upper Aire has no mask signal | Owner paused the plan until the tidy completes |
| 2026-10-30 | DINOv3-Sat feature look and probe (scratch `uncommitted/e4b/dino/`): frozen facebook/dinov3-vitl16-pretrain-sat493m last-layer features, tokens of 4 m (0.25 m input) and 8 m (0.5 m). Within one box (west 75 % train, east 25 % test) ridge and logistic probes reach R2 0.56 to 0.75 and raised AUC 0.93 to 0.99, and on grey tokens at Ferrybridge AUC 0.93 to 0.94 against 0.39 to 0.60 for RGB. Across boxes R2 is about 0 and AUC 0.65 to 0.85 (Upper Aire has no buildings, Ferrybridge no woodland), so transfer is untested rather than disproved. Token floor: lidar token means upsampled to 1 m give RMSE 1.35 to 1.84 m, so detail needs an image-guided decoder | Two boxes only; the owner's grey-roof hypothesis holds within a scene |
| 2026-10-30 | Southend `satmesh correct` failed on empty cells; fixed in `satmesh_eval.registration` (cells with fewer than 3 lidar points stay uncorrected, with a warning; test added; checks pass; not committed). Earlier symptom: Southend `satmesh correct` fails: `lidar_reference.intensity_gradient_image` builds a triangulation from a cell with no lidar points (estuary water) and scipy raises `No points given`. Left unfixed (outside E4b scope); the Southend store is built, not corrected. Fix: skip a cell with no points and leave it uncorrected | Ferrybridge and Upper Aire 5.4 km stores built and corrected; EA WCS returns sporadic 403s mid-build, resumed by `uncommitted/e4b/areas.sh` |
| 2026-10-30 | E4b S1: A and B on the saved 540 m PixTransform outputs reproduce the source cell means to 6 mm at most (B at x30; 1e-13 m at x2 and x5). RMSE (secondary): A and B cut P0 at x2 (Ferrybridge 1.74 to 0.73 and 0.62) and x5 (1.71 to 1.25 and 1.14), stay above kriging (0.48, 0.87), and leave x30 unchanged (2.33, edge slope 0.739) because P0's x30 cell means were already near the source. Review page <https://claude.ai/artifact/WJ4AqDx4DAdd2GRCHGzxFm>; GLBs `pixa` and `pixb` in `uncommitted/scratch-archive/e4/glb/` | Cell offsets were most of P0's x2 and x5 error; the texture-into-relief defect remains at x30. The owner's eye decides |
