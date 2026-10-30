# Status and decision log

Running record of where the project stands and why. Updated at every checkpoint: state, decisions
with their reasons, open risks. Detail per feature lives in the plan and results docs named here.

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

## State against the plan (2026-10-26)

| Stage | State |
| --- | --- |
| 0 Scaffold | Done |
| 1 Spikes | S1, S5, S6 done. Open: S3, S4; S2, S2b, S7 on demand |
| 2 Baseline pipeline | F1 to F5a done for Great Britain (DSM visual mesh, DTM ground grid). Open: F2a, F2b, F5b Gazebo collision, F5c large-area DTM |
| 3 Evaluation harness F6 | Done (`f6-results.md`): height, smoothness, camera-visibility and held-out-point scores; Esri-to-EA offset and texture-detail spectrum; consistency function (library only); all behind `satmesh eval` |
| 4 Classical enhancement E1, E2 | E2 shipped as `satmesh correct` (`e2-results.md`); E2b (towns and woodland) planned in `e2b-plan.md`; E1 not started |
| 5 ML experiments E3 to E7 | Not started. E8 (lidar surface refinement) closed without a change. E4 survey done (`e4-research.md`), first trial PixTransform not started; E9 closed after S0 and S0b (`e9-results.md`), no fill built; owner priorities are E4 and E6 |

## TODO.md to plan codes

`TODO.md` is human-facing and uses no codes. Its items map to the plan codes used in this folder:

| TODO.md item | Code |
| --- | --- |
| Height-detail recovery research, then trials | E4 (survey first, owner instruction) |
| Stretched texture on steep faces | E9 |
| Ship the imagery position correction (done 2026-10-26) | E2 |
| Position correction in towns and woodland | E2b |
| Test a different region (Yemen) | F2a, F2b |
| Combine several captures | E6 |
| Source registry | F2a, F2b |
| Terrain past about 6 km | F5c |
| Smoother elevation data | E1 |
| Sharpen past native zoom | E3 |
| Fine-tuned super-resolution | E5 |
| Single-image height as detail | E7 |
| Wales lidar points, Scottish lidar route | E2 follow-up, S7 |
| Older Esri releases | S2, S2b |
| Elevation coverage at UK sites | S3 |
| More England test sites | S4 |
| ML environment split | `ml/` workspace |
| Real-photo localisation test | F7 |
| Gazebo | F5b |

## Where to resume

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
   Lean2 result (2026-10-29, `uncommitted/scratch-archive/lean2/results.md`): ground error at
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
   Next: C5 before/after strips with blink from `uncommitted/scratch-archive/c3c4/` stores.
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
   Geopose). GLBs of every surface in `uncommitted/scratch-archive/e4/glb/`.
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

## Decisions

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-10-30 | M1 phase 1 done (scratch `uncommitted/e4b/m1/`, tables in `m1/tables.txt`, review page <https://claude.ai/artifact/GBTiu16cvHBpbgkxC1GDL5>): RS3DAda (TTA and not), Geopose (folds 5 and 6, 4-flip TTA), CHMv2 (model, gated access granted, and global tiles), Depth Anything 3 Mono and Metric, V2 Small, zero-shot on the 540 m boxes at x5 and x30. By RMSE (secondary) only Geopose M-C and RS3DAda M-C beat kriging, at Ferrybridge x30 (1.68, 1.92 against 2.08); Upper Aire x30 ties (2.11 against 2.17); M-A equals kriging; M-B is much worse. Flat-ground edge slope stays above lidar for every height model (RS3DAda 0.27, Geopose 0.37 raw at Ferrybridge against 0.017). Depth models, fitted to height above ground (the first fit regressed on terrain elevation and gave negative scales), add nothing: M-A within 0.03 m of kriging, M-C worse. CHMv2 on the 0.25 m texture overpredicts canopy (open-ground RMSE 7 m); at 0.5 m better; global tiles best; all underpredict Ferrybridge trees by 3 to 4.5 m. M-C uses two tunables, gain floor 0.1 m and gain cap 3 (no source) | Zero-shot sweep; owner judges the renders |
| 2026-10-30 | Coarse-to-fine choice: heights = coarse DEM + anomaly of the mean of Geopose and RS3DAda height-above-ground predictions, with a kriging base (M-A, `avg_ma`) as the general case; bilinear base dropped. Kriging base leaves no slope creases (second-difference ratio at cell-centre lines 1.0 to 1.2) where the bilinear base does at x5 (Ferrybridge 1.5 to 1.6, Upper Aire 2 to 6); at x30 both are about 1.0 to 1.1, but kriging at x30 is slow (about 7 min per 540 m box, so per-block runs are needed over 5.4 km) and coherent only to about 1 cm. CHMv2 is accepted as the tree layer despite a 3 to 4.5 m underestimate (any lift beats flat). Review page <https://claude.ai/artifact/9hW3why4guocCyLyVjkbQy> | Owner choice after own visual review; CHMv2 plus building models merge and per-class sourcing wait on segmentation |
| 2026-10-30 | Segmentation work approved: (1) class labels from EA point-cloud classes (ground, vegetation, building, water) for the three 5.4 km areas and a small head on frozen DINOv3-Sat features, tested leave-one-area-out; (2) per-class height sources and post-processing (flat roofs, steeper walls, tree-crown caps, ground held to the DEM) after a prior-art survey. The PixTransform proposal must include supplementary data (class masks, DINOv3 features, other lidar-derived layers) as extra guide input | Owner: the segmentation can constrain height extraction and clean artefacts; extra data steers PixTransform |
| 2026-10-30 | M1 verdict by eye: owner judges both M-A surfaces (RS3DAda TTA, Geopose) the most faithful to the lidar, with a preference for Geopose M-A; kriging looks bad to the owner, bilinear better. Own review of the renders agrees: M-A has no cell-edge steps (30 m edge step 1.0 times the step elsewhere); M-C has 3.9 to 4.2 times (rejected); the trial kriging panels carry 270 m tile-edge tears (12 to 22 times at x30) because the trial ran kriging per 270 m tile, so the kriging baseline was unfair, and bilinear is the baseline from here. M-A gives footprint, position and rough height of grey buildings beside grey pavement and keeps road verges flat, but rounds walls, roof ridges and tree crowns, underestimates raised heights (raw means 1.4 to 8 m low) and lifts a red vehicle into an oversized dome (cars absent from the older lidar are real objects: keep or drop is a policy call). Candidate next steps: average Geopose and RS3DAda N, fine-tune on England lidar (M3), bilinear base in place of kriging | Owner decision plus own visual review; two boxes and views at the tallest windows |
| 2026-10-30 | DINOv3-Sat feature look and probe (scratch `uncommitted/e4b/dino/`): frozen facebook/dinov3-vitl16-pretrain-sat493m last-layer features, tokens of 4 m (0.25 m input) and 8 m (0.5 m). Within one box (west 75 % train, east 25 % test) ridge and logistic probes reach R2 0.56 to 0.75 and raised AUC 0.93 to 0.99, and on grey tokens at Ferrybridge AUC 0.93 to 0.94 against 0.39 to 0.60 for RGB. Across boxes R2 is about 0 and AUC 0.65 to 0.85 (Upper Aire has no buildings, Ferrybridge no woodland), so transfer is untested rather than disproved. Token floor: lidar token means upsampled to 1 m give RMSE 1.35 to 1.84 m, so detail needs an image-guided decoder | Two boxes only; the owner's grey-roof hypothesis holds within a scene |
| 2026-10-30 | Southend `satmesh correct` failed on empty cells; fixed in `satmesh_eval.registration` (cells with fewer than 3 lidar points stay uncorrected, with a warning; test added; checks pass; not committed). Earlier symptom: Southend `satmesh correct` fails: `lidar_reference.intensity_gradient_image` builds a triangulation from a cell with no lidar points (estuary water) and scipy raises `No points given`. Left unfixed (outside E4b scope); the Southend store is built, not corrected. Fix: skip a cell with no points and leave it uncorrected | Ferrybridge and Upper Aire 5.4 km stores built and corrected; EA WCS returns sporadic 403s mid-build, resumed by `uncommitted/e4b/areas.sh` |
| 2026-10-30 | PixTransform paused after S1; Part 3 M1 (inference-only model sweep) runs next. S2 ensembles, S2b tuning and S4 area runs wait. On return, deep survey of guided-upsampling work since 2019 (methods, training recipes, usage) before any more PixTransform runs. The next PixTransform stage must also explore other architectures, and a strong-model review proposes architecture and training-procedure improvements; both come to the owner as a written proposal to read before any long experiment starts | Owner, seeing S1 renders: A and B indistinguishable (neither has an advantage); roof dimples removed, grassy verges raised, grey buildings on pavement left flat are flaws of the colour-to-height mapping that Part 1 does not address. Owner: the 2019 model is old and the field must have improved in technique and training |
| 2026-10-30 | E4b S1: A and B on the saved 540 m PixTransform outputs reproduce the source cell means to 6 mm at most (B at x30; 1e-13 m at x2 and x5). RMSE (secondary): A and B cut P0 at x2 (Ferrybridge 1.74 to 0.73 and 0.62) and x5 (1.71 to 1.25 and 1.14), stay above kriging (0.48, 0.87), and leave x30 unchanged (2.33, edge slope 0.739) because P0's x30 cell means were already near the source. Review page <https://claude.ai/artifact/WJ4AqDx4DAdd2GRCHGzxFm>; GLBs `pixa` and `pixb` in `uncommitted/scratch-archive/e4/glb/` | Cell offsets were most of P0's x2 and x5 error; the texture-into-relief defect remains at x30. The owner's eye decides |
| 2026-10-30 | Owner confirmed the E4b decision table: all three 5.4 km areas, 24 tuning configurations per factor, R = 4 seeds at 2,700 and 5,400 m and 1 at 1,080 m | Plan recommendations |
| 2026-10-30 | Kriging in `satmesh_height` is exactly coherent only up to x10 (one discretisation point per pixel); at x30 the cell-mean residual is up to 1 cm (6 mm in S1). Kept; exact discretisation at x30 costs 900 x 900 point pairs per offset | Far below the metre-scale errors judged; open for the owner |
| 2026-10-30 | `ml/` uv workspace created at the start of E4b with member `satmesh-height` (PixTransform port, variants, kriging) and PyTorch; meets `pipeline/` through GeoTIFF files with a contract test | Owner: PixTransform is in the product for certain; permanent code from the height experiments lives in `ml/` |
| 2026-10-30 | Height scores against lidar are a secondary check, never the verdict, for methods that take shape from the image; every results doc says so | E4: RMSE ranked PixTransform last; the owner judged it by far the closest at x30. Lean, registration, capture date and edge smearing differ between lidar and Esri image |
| 2026-10-30 | Esri imagery may be used for scientific work including model fine-tuning; the DINOv3 licence's military clause does not apply | Owner checked both |
| 2026-10-30 | E4b areas at least 5 km (5.4 km boxes); Esri fetched at `--esri-requests-per-second 30` | Owner: a 5 km area fetches in minutes at up to 30 requests/s with no rate limit hit; 1 to 2 km is too small |
| 2026-10-29 | E4: photo-shift sensitivity (1 and 3 m) measured at x2 and x5 only, not x30 | PixTransform at x30 runs 12,945 tiny epochs per tile (81 coarse cells), about 8 to 20 min per tile, so the two shifted x30 runs per site cost about 2.5 h. Owner choice |
| 2026-10-29 | E4 kriging baseline is trial-only code after Kyriakidis 2004 (block-averaged variogram as in Goovaerts 2008), checked for coarse-cell mean reproduction, never committed | No Python library implements area-to-point kriging for heights: pyinterpolate has only the Poisson (population-count) variant; gstools, pykrige and scikit-gstat do point kriging; R `atakrig` needs R. Owner choice |
| 2026-10-29 | E4 trial approved: PixTransform against bilinear, guided filter and area-to-point kriging on the EA DSM degraded x2, x5, x30 at Ferrybridge and Upper Aire; Esri guide lean- and position-corrected by `correct`, shifted 0, 1, 3 m for sensitivity; PyTorch in a throwaway env outside the repo | Owner choice; kriging added for the x30 (Yemen) case; no ml/ workspace until a method earns a place |
| 2026-10-29 | A scene's lean is rejected when the 95 % bootstrap radius of l exceeds tan 30 / 2, not on the width of the k interval | The k interval is clipped by the cap and misses a small lean with an undetermined azimuth; the radius bounds the lean error at any height (radius times h) |
| 2026-10-29 | Cap k <= tan 30 by fitting on the circle k = tan 30 when the free fit exceeds it | The soft-L1 cost is convex in (t, l), so this is the exact constrained optimum; no clipping |
| 2026-10-25 | PyTorch constraint dropped from README, AGENTS.md and plans | Came from the scaffold copied from xfeat-rt, not from the owner; `ml/` workspace remains an option |
| 2026-10-25 | Typer for the CLI | Owner choice; typed signatures, `CliRunner` for tests |
| 2026-10-25 | platformdirs cache, `--cache-dir` and `SATMESH_CACHE_DIR` | Owner choice; `~/.cache/satmesh` |
| 2026-10-25 | EA DTM hard-wired for Great Britain, no `--dtm` | Registry is F2a; other regions raise |
| 2026-10-25 | Single-GLB output with an 8,192 px texture cap replaced by a tiled store | Owner rejected a whole-area cap: resolution is per tile |
| 2026-10-25 | Canonical store with thin exporters, not 3D Tiles as the store | Cesium, Gazebo and renderers each want a different frame; swapping a texture or DEM replaces one node |
| 2026-10-25 | Leaf = 4 x 4 Esri tiles (1,024 px, about 180 m at z19, 54 N) | Whole Esri tiles, no resampling; per-place native zoom is leaf depth |
| 2026-10-25 | Meshes in true-metre local ENU through OSTN15 and OSGM15, with both heights recorded | BNG XY is 0.04% short; Cesium and GNSS use ellipsoidal height; geoid separation is about 50.8 m |
| 2026-10-25 | Parents only where all four children exist; container over maximal complete nodes | No holes in parent textures, no extra fetches; ragged edge stays at leaf resolution |
| 2026-10-25 | Store DTM and EA first-return DSM per node (DSM for the visual mesh, DTM for ground and collision) | Orthophoto on a DTM paints buildings and trees flat; built in F5a |
| 2026-10-25 | F6 approved: `satmesh-eval` package with xdem, scikit-image and a ray caster; depth difference and object recall for camera visibility; raw point-cloud spike; opensr-test deferred to E3 | Owner decisions 1 to 4 on `f6-plan.md` |
| 2026-10-25 | F6 sites: Upper Aire and Lower Aire | Owner choice; moorland and trees, then houses and roads |
| 2026-10-25 | F6 second site moved from Lower Aire (BNG 452000 425000) to Ferrybridge (448000 424000) | The 2020 EA survey caught the Aire in flood at the first box: 31 of 900 windows reliable |
| 2026-10-25 | Offset windows kept only above the 99th percentile of peak response between unrelated windows | Raw phase-correlation shifts span +-16 m on real pairs and skimage's error is uninformative |
| 2026-10-25 | DSM and DTM sampled bilinearly every 0.5 m (was 1 m) | Nearest-pixel sampling matched the lidar exactly (raised-object NMAD 0.00 m) but rendered as terraced fields and blocky trees; owner judged bilinear 0.5 m clearly best by eye in Blender. Cost: raised-object NMAD 0.54 m at Upper Aire and 61 to 75 % of camera-visible raised points shown, against 85 to 92 % with nearest; about 1.5 times the 1 m store size |
| 2026-10-25 | Esri-to-EA comparisons resample through pyproj with OSTN15, never `rasterio.warp` | The rasterio wheel has no UK grids; its Helmert fallback was 1.6 m north of OSTN15 at Upper Aire and produced a false 2 to 3 m offset |
| 2026-10-25 | Ray casting with trimesh and embreex, not Open3D | Open3D 0.20 has no wheel for CPython 3.13 on this glibc |
| 2026-10-25 | Real-photo localisation test (F7) out of F6 but required before v1 release | Owner decision 5; needs photographs with known poses |
| 2026-10-25 | Ground grid stored as a per-node GeoTIFF (EPSG:3857, one pixel per grid node), not a ground mesh | F5b needs the DTM without refetching; a raster is readable by GIS and by the F6 scorer, and the decimation choices stay open |
| 2026-10-25 | DSM used as served, not clamped to the DTM | It sits below the DTM at 5 % of pixels by up to 0.33 m; clamping would hide a survey-epoch disagreement F6 should measure |
| 2026-10-25 | Keep the bilinear 0.5 m DSM sampling; E8 closed without a geometry change | Node-aligned bilinear, raw-point Delaunay and fitted roof planes scored better against the DSM but the owner judged the current mesh best by eye in textured and shaded renders; scores against the DSM did not predict that |
| 2026-10-26 | Esri request rate set by `--esri-requests-per-second` (default 1); fetches within a mosaic run in 8 threads sharing one schedule; stay threaded, not async | Owner raised the rate; the cap is the request rate, so concurrency only hides latency and async would rewrite the sync client, retry and callers for no gain |
| 2026-10-26 | E2: lidar-referenced Esri shift by gradient correlation, applied only where enough windows survive; error bound estimate shipped with products; MI and nDSM rejected | B2 matched EA aerial within 0.3 m at 4 of 8 boxes with gradients, 2 of 8 with MI; urban, wooded and coastal boxes fail (`e2-results.md`) |
| 2026-10-26 | `build` and `correct` sped up with byte-identical output (`speedup-results.md`): imagery prefetch, one read per LAZ, threaded evaluation, cells in up to 8 worker processes, BLAS pools set to 1 thread by `satmesh_cli` | Owner: no loss of quality, output parity, lower latency and higher throughput. Averaging lidar points into grid cells and splitting the triangulation both change the output, so both were dropped |
| 2026-10-26 | Progress, run log and corner input (`progress-logging-input-plan.md`, approved): `ProgressReport` hook in `satmesh-core` called by `build_store`, `measure_correction` and `apply_correction`; `rich` bars and `loguru` sinks in `satmesh-cli`; `<store>/run.log` appended by every store command; `--nw` and `--se` replace `--bbox` and `--crs`; BLAS pools limited by `threadpoolctl` in the window matching instead of an environment default | Owner approved the plan and the dependencies (loguru, rich, threadpoolctl); eval commands take the corners snapped inward to whole BNG metres |
| 2026-10-26 | Owner closed E9 after S0 and S0b | Steep faces are 4 to 10 % of a ground camera's view and a fill adds no measured information; position and lean matter more. Real-photo test photographs: the owner has them and they are good enough, so no further request |
| 2026-10-26 | Owner approved the E9 and E2b proposals and the opening measurements S0, S0b, T0 | `_FILL` vertex attribute plus a flat-colour export; snapping an explicit step; threshold set from S0; T0 at Ferrybridge; 0.3 m; T2 returns to the owner after its prior-art check; borrowed cells get their own status and bound |
| 2026-10-25 | Mesh smoothness scored by facet normals at centroids against Horn normals of the DSM, plus flat-facets-on-slope and grid-aligned aspect excess | Height scores at pixel centres cannot see terracing; nearest 0.5 m ranks worst on all three as the eye did; thresholds are tunables and the blind-comparison validation has not been run |

## Open risks

- Lean-biased truth (`metric-bias-audit.md`, 2026-10-30): the Esri-to-EA-aerial truth used for every
  position and lean fit is a median over all windows, roofs included, so lean pulls it south;
  against a 12-window open-ground truth at Southend the C6 refit would pass and the north
  overshoot shrinks. Unverified until an open-ground truth with more windows is measured.
- `correct` memory: about 2 GB per worker, 8 workers at most, all cells' lidar points held at
  once; a many-km area needs a bounded reader.
- Crown and roof-edge fidelity against the lidar is traded for a smooth look (see the 0.5 m sampling
  decision); E8 tried three ways of recovering it and the owner rejected all three by eye.
- Gazebo collision uses the visual (DSM) mesh until F5b: robots would collide with canopies.
- DSM nodata (water, survey edges) raises and stops the build; untested on such a box.
- Esri imagery sits 0.2 to 2.8 m north of EA imagery across eight England boxes (F6 checkpoint 2,
  `offset-survey.md`; S6's 2.4 m was a Helmert-reprojection artifact), and raised objects are
  displaced differently from open ground, so a rigid correction will not do; matching pipelines
  will see it.
- Esri imagery is not a true orthophoto at Worcester (roofs displaced about 0.3 to 0.6 m per m of
  height toward south-west; S0b, `e9-results.md`); undetermined at the survey sites, so buildings
  can lean in the texture and the position correction does not remove it.
- No ground-truth scoring yet: DEM, texture and geoid chain are untested against raw lidar and
  EA aerial imagery.
- Gazebo untested: roll pose for glTF, `elevation` datum (gz-math treats it as ellipsoidal),
  levels, mesh collision cost, tile-count and VRAM limits.
- Large areas: parents past about 6 km need a DTM fetch not yet tried (WCS tested to 6000 x 6000
  px); a 20 km box is about 198,000 Esri tiles, about 55 h at 1 request/s.
- Texture seam lines were wrap-around sampling, fixed with a clamp sampler (2026-10-25). Geometric
  cracks between tiles are hidden by skirts, not removed; not seen in renders since the fix.
- `sources_at` is not cached, so a cached rerun still makes one identify request.
- Wales and Scotland have no EA DTM; zoom comes from sources at the area centre only.

## Where things are

| What | Where |
| --- | --- |
| Feature plans | `f1-f2-plan.md`, `f4-plan.md` (partly superseded), `f5-plan.md`, `f6-plan.md`, `e2-plan.md` (built), `e2b-plan.md`, `e9-plan.md`, `progress-logging-input-plan.md` (built) |
| Research | `s1-results.md`, `s5-results.md`, `s6-results.md`, `uk-sources.md`, `f5-tiling-research.md`, `f6-research.md` |
| F5 build record | `f5-results.md`, `f5a-results.md` (DSM) |
| E8 survey, results | `e8-research.md`, `e8-results.md`, `lidar-pointcloud-spike.md` |
| E2 survey, results | `e2-research.md`, `offset-survey.md`, `e2-results.md` |
| Metric bias audit | `metric-bias-audit.md` |
| E4, E9, region surveys | `e4-research.md`, `e4-results.md`, `e4-research-2.md`, `e4b-plan.md`, `e9-research.md`, `region-research.md` |
| Speed-up record | `speedup-results.md` |
| Task list | `TODO.md` at the repo root |
