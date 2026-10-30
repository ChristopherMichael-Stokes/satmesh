# E4b plan: PixTransform to the end, then learned-height models

Draft for the owner, 2026-10-30. Nothing here has been run. Read `e4-results.md` and
`e4-research-2.md` first.

> **The scores below cannot be trusted as a verdict.** The lidar reference and the Esri image do
> not describe the same ground in the same place: roofs lean in the image by up to tan 30 per
> metre of height, registration is good to about a metre at best, the two were captured years
> apart, and a first-return DSM has its own edge smearing. A method that puts a correct building
> 1 to 2 m off, or with the image's shape rather than the lidar's, is punished as heavily as one
> that invents relief. Ranked by RMSE alone, E4 would have thrown out PixTransform, the only
> method that forms buildings at x30, which the owner judged by eye to be by far the closest to
> the lidar. The owner's judgement of the renders decides; the scores are a secondary check.
>
> In every stage below: renders and the owner's judgement decide; scores are reported beside the
> views, never as the verdict, and every results doc repeats this caveat. A pass gate on a score
> (Part 3) can only reject a method together with the owner's view, never on its own.

## Context

- The E4 trial refined the EA 1 m first-return DSM, block-averaged by x2, x5 and x30, back to 1 m
  at Ferrybridge (BNG 448000 424000) and Upper Aire (399750 447250), 540 m boxes in four 270 m
  tiles, with a position-corrected Esri RGB guide. Kriging scored best and PixTransform worst by
  RMSE, and PixTransform turned photo texture into relief on flat ground.
- Owner judgement by eye: at x30 PixTransform is by far the closest to the lidar, because the
  smooth methods cannot form buildings. At x2 and x5, bilinear and kriging trade blows and
  PixTransform looks worse than its own x30. The owner reads the RMSE gap partly as a metric and
  data problem (lidar against imagery layout, lean, registration), and holds that injecting
  learned height from pixels is essential to the product. x30 is the Yemen case (GLO-30).
- Owner, 2026-10-30: Esri imagery may be used for scientific work, model fine-tuning included;
  the DINOv3 licence's military clause does not apply to this project. Esri fetches run at up to
  30 requests/s without hitting a limit, and a 5 km area fetches in minutes, so areas are at
  least 5 km and fetches use `--esri-requests-per-second 30`.
- Everything from the trial is in `uncommitted/scratch-archive/e4/` (git-ignored): `prep.py`
  (inputs), `texture.py`, `pix_run.py` with `vendor/pix_transform` (commit 3db98d5),
  `baselines.py`, `krige.py`, `score.py`, `render.py`, `make_page.py`, `glbs.py`; outputs in
  `out/`, page in `page/`, GLBs in `glb/`. Each script's docstring carries its run command.
  Scratch torch env, made in the session scratchpad:
  `uv venv -p 3.13 torchenv && uv pip install torch numpy tqdm opencv-contrib-python-headless scipy`
  (torch 2.15 cu132 worked on the RTX 4070 Ti).

## Part 1: PixTransform to the end

### What it settles

1. Whether PixTransform's building shapes survive once its two defects are removed: whole coarse
   cells sitting metres off (cell residual up to 17 m; its consistency is only a training loss)
   and photo texture turned into bumps.
2. Whether a larger training area and seed averaging make it steadier at x30, where a 270 m tile
   gives it only 81 cells to learn from.
3. Whether the result holds over 5 km areas with mixed cover (town, moor, shore), at x30 first and
   x5 second.

### Variants

Notation: s = source (coarse cell means), P = PixTransform output on the 1 m grid, B(.) = mean
over each f x f cell, N(.) = nearest upsampling of a coarse grid to 1 m, K(.) = area-to-point
kriging of coarse cell values to 1 m (`krige.py`, coherent: B(K(c)) = c).

| Code | Output | Source of the method |
| --- | --- | --- |
| P0 | P, as published | de Lutio et al., ICCV 2019 |
| A | P + N(s - B(P)): each cell shifted so its mean is the source | Additive mass-preserving adjustment of pycnophylactic interpolation (Tobler 1979, JASA 74:519-530); DADA's source-consistency step (Metzger et al., CVPR 2023) does the same job, form to be read from the paper at build |
| B | P + K(s - B(P)): P as the trend, its cell residuals kriged | Area-to-point residual kriging with a covariate trend (Kyriakidis 2004; Liu, Kyriakidis and Goodchild 2008, IJGIS 22:431-447, to verify at build) |
| C | mean over R seeds of P trained on a larger area | Same method, more training cells; seed averaging as in deep ensembles (Lakshminarayanan et al., NeurIPS 2017) |
| C+B | B applied to the C mean | As above |

- A and B both reproduce s exactly. A leaves steps at cell edges wherever P's cell means are off.
  B spreads the same correction smoothly. Since K is linear with fixed weights,
  B = K(s) + (P - K(B(P))): kriging's smooth base plus P's detail about its own smooth part.
- A and B reuse saved PixTransform outputs, so no GPU time.
- C also gives a per-pixel spread across seeds: an uncertainty map, shown on the page.

### `ml/` workspace (stage S0)

Owner, 2026-10-30: PixTransform is in the product for certain, so the ML environment is created
now and permanent code from these experiments lives there. Trial tooling (scoring, renders, review
pages) stays in scratch.

- `ml/` is a uv workspace beside `pipeline/` (AGENTS.md layout): own `pyproject.toml`, `uv.lock`,
  `.venv`, `prek.toml` (uv-lock, uv-audit, ty), members under `ml/packages/*`, Python >= 3.13,
  ruff and ty at the repo's strictness. New dependency: PyTorch from PyPI (CUDA wheels; torch 2.15
  cu132 worked on the RTX 4070 Ti), plus numpy, scipy, rasterio for the file contract.
- One member, `satmesh-height` (module `satmesh_height`), holding:
  - the PixTransform network and training loop, ported from prs-eth/PixTransform (MIT, commit
    3db98d5, notice kept) to the repo's typing and style, with the three size and overhead fixes
    below and the tuning parameters as a frozen config model;
  - variants A, B, C and C+B as plain functions;
  - area-to-point kriging (Kyriakidis 2004), moved from `krige.py`;
  - a CLI entry point that refines an area from the file contract below.
- Contract with `pipeline/` (workspaces meet through files): `pipeline/` writes the inputs (coarse
  DSM, guide RGB, optional DTM) as GeoTIFFs on one grid with a JSON sidecar; `satmesh_height`
  writes the refined height GeoTIFF (float32, metres, same grid and CRS) with a sidecar naming the
  method, parameters, seeds and source files. A contract test writes with one side and reads with
  the other, run from a Makefile target that uses both environments.
- Tests: chunked inference equals full-image inference on a small grid; `unfold` patches equal the
  original loop's; A, B and C+B reproduce the source cell means (Hypothesis property tests);
  kriging coherence (cell means of K(c) equal c).
- Root `Makefile` `setup`, `check` and `test` cover `ml/`; AGENTS.md layout and commands tables
  are updated in the same change.
- How the pipeline consumes a refined height raster in `build` (in place of the EA DSM, or Yemen's
  GLO-30) is a separate plan once Part 3 has picked the detail method.

### Code changes

Permanent ones land in `satmesh_height` (S0); the trial scripts stay in scratch.

- `vendor/pix_transform`: three changes that keep the method (network, loss, optimiser, step
  count) and only remove size and overhead limits.
  - Inference in row chunks. The network is per-pixel (1 x 1 convolutions), so chunking is exact.
    Full-image inference keeps 2,048-channel activations: 29 M pixels over 5.4 km would need about
    240 GB.
  - Patch extraction with `torch.nn.functional.unfold` instead of the Python double loop
    (1.17 M cells at x5 over 5.4 km).
  - Batches drawn from a per-epoch random permutation on the GPU instead of a `DataLoader`
    rebuilt every epoch. At x30 the per-epoch overhead dominated: 12,945 epochs per 270 m tile,
    8 to 20 min each.
  - Check: on one 270 m tile at x5 and one at x30, the patches are identical and the output agrees
    with the original code within the spread of two repeat runs of the original.
- `pix_run.py`: training extent (270, 540, 1,080, 2,700, 5,400 m) and seed as arguments; output
  name carries both; run-claim files kept so several GPU processes share one list.
- `combine.py` (new): A, B and C+B from saved outputs; asserts each reproduces s within float32
  rounding.
- `prep.py`, `texture.py`: Esri at `--esri-requests-per-second 30`; texture stored per 1,080 m
  block (a 5.4 km texture at 0.25 m is 21,600 px a side, 1.4 GB).
- `krige.py`: run per 1,080 m block with its neighbours' cells as context; one variogram per area
  and factor.
- `score.py`: cover from EA lidar point classes (6 building, 3 to 5 vegetation, 2 ground)
  rasterised to 1 m, replacing the photo-greenness split. That split put 7,599 Ferrybridge pixels
  in buildings against 48,229 in trees, and 142 at Upper Aire. Points come from
  `satmesh_data.fetch_point_cloud` (5 km squares, 100 to 500 MB each). Add seed spread per cover
  class.
- `render.py`, `make_page.py`: a variant selector, A/B blink between any two variants, views by
  the rule below.
- `glbs.py`: one GLB per 1,080 m block with a 0.25 m texture (4,320 px), under about 100 MB each.
  Exported for the blocks holding views and the P0 comparison block, for truth and every variant
  at x30 and x5.

### Tuning (stage S2b)

The trial used the published defaults, set for 10 m canopy height from Sentinel-2. Our case
(0.25 to 1 m RGB, buildings, 2 to 30 m sources) may need other settings. The tunable settings are
the function's own parameters (`DEFAULT_PARAMS` in `vendor/pix_transform/pix_transform.py`) plus
the guide resolution:

| Setting | Default | Range searched | Why it matters here |
| --- | --- | --- | --- |
| Weight decay on the position branch | 1e-4 | 1e-6 to 1e-2 | How freely the height mapping may vary across the tile; low lets it fit local texture, high forces one colour-to-height rule |
| Weight decay on the colour branch | 1e-3 | 1e-5 to 1e-1 | How sharply colour changes become height changes: the texture-copying lever |
| Weight decay on the head | 1e-3 | 1e-5 to 1e-1 | Overall smoothness of the mapping |
| Learning rate | 1e-3 | 1e-4 to 3e-3 | Stability with few cells (81 per tile at x30) |
| Training steps | 32,768 | 8,192 to 131,072 | Under- or over-fitting the block means |
| Loss | L1 | L1, MSE | L1 tolerates cells the image cannot explain |
| Guide | RGB, 1 m | RGB or greyscale; 1 m or 0.5 m (doubles the factor) | Colour against shape cues; finer roof edges |

The position channels stay on: the code breaks without them (`pix_transform_net.py`).

Method: random search (Bergstra and Bengio, JMLR 13:281-305, 2012), sampling log-uniformly over
the ranges above. 24 configurations at x30 and 24 at x5, one seed each, plus the defaults. They
run on tuning blocks only: one 1,080 m block per area, held out from every view and score in S5,
so the pick is not judged on the ground it was tuned on.

Choosing (see the caveat at the top): scores only shortlist. Keep the configurations not
dominated on RMSE, flat-ground edge slope and coarse-cell residual, at most six per factor, plus
the defaults. Render them with the same view rule on the tuning blocks. The owner picks one per
factor by eye on a review page, and S4 uses the pick. If the owner sees no difference from the
defaults, S4 keeps the defaults.

### Areas

5,400 m boxes: 20 x 20 tiles of 270 m, divisible by 2, 5 and 30; south-west corners in BNG. Before
each build, check EA DSM, DTM and point-cloud coverage and nodata (DSM nodata stops `build`) and
move the box inland or into coverage if needed.

| Area | SW corner | Cover |
| --- | --- | --- |
| Ferrybridge, Knottingley, Pontefract edge | 445000 421500 | Town, industry, river, power-station site; contains the trial box |
| Upper Aire | 397000 444500 | Moor, walls, farm trees; contains the trial box |
| Southend, Westcliff, Leigh | 584500 185600 | Dense town, shore; contains the E2b lean store (588300 186400); the shore needs the nodata check |

### Run sizes

- P0 per 270 m tile (the published setting) in one 1,080 m block per area (16 tiles), as the
  reference for the larger extents.
- C over the whole area at extents 1,080 m (25 blocks, R = 1), 2,700 m (4 blocks, R = 4) and
  5,400 m (1, R = 4); A and B on each. PixTransform's step count is fixed (32,768 steps of 32
  cells), so a training run costs about the same at any extent once the overhead fixes are in.
- Bilinear and kriging over each whole area.
- Factors: x30 and x5. x2 stays at the 540 m boxes.
- Per-training time is measured on the slice first (S2) and the run list resized if one area and
  factor would exceed about 1 h of GPU; the resize is logged in `status.md`.

### Stages

Each stage ends with its outputs checked and a line in `status.md`. Long runs write one log line
per run with a count, a done or failed line, and run under a Monitor.

| Stage | Work |
| --- | --- |
| S0 | `ml/` workspace and `satmesh_height` (above): port, fixes, tests, contract, checks passing |
| S1 | A and B on the existing 540 m outputs, all factors, both sites; score, page, GLBs (CPU, about 20 min) |
| S2 | Vendored-code changes and their check; per-training time at x30 and x5; C at the 540 m boxes (extents 270 and 540 m, R = 4) and C+B |
| S2b | Tuning: 24 random configurations per factor at x30 and x5 on the held-out tuning blocks (needs S3's data for those blocks), shortlist, review page, owner's pick |
| S3 | The three 5.4 km areas: coverage check, `satmesh build` and `satmesh correct` at 30 requests/s, inputs, textures, lidar point classes. First the whole path on one 1,080 m block. Can run while S2 trains |
| S4 | Area runs (run sizes above) with the owner's tuned settings, plus the defaults for comparison, up to three PixTransform processes sharing the GPU |
| S5 | Scores, renders, review page, GLBs, `e4b-results.md`, `status.md` |

### View rule (fixed before results)

Per area: in each 2,700 m quadrant, the 40 m window with the highest mean nDSM at least 60 m from
the box edge, cameras facing north, east, south and west by quadrant; the worst 40 m window for B
and for C at x30; two windows drawn at random with seed 0. Drone and ground rigs as in the trial.

## Part 2: re-checks from the metric-bias audit

Starts after S5, before Part 3. Evidence and item numbers are in `metric-bias-audit.md`. CPU work on
cached data unless stated.

### What it settles

Whether the lean correction's chosen fit (F2), the rejected C6 re-registration, the E2 cell rule
and the Southend north overshoot hold once the truth is measured on open ground. The current
truth, a median over all Esri-to-EA-aerial windows, carries roof lean. And whether other earlier
rejections were the reference's fault.

### Stages

| Stage | Work |
| --- | --- |
| R1 | Open-ground truth: Esri against EA aerial on windows with nDSM at most 0.5 m, raised pixels masked with a lean margin (k up to tan 30 times local height), over boxes of at least 5 km around Southend and Ferrybridge so far more than 12 and 2 windows survive. Report each truth with its bootstrap interval |
| R2 | Re-score the saved lean2 fits F0 to F5 (`lean2/*_results.json`) and the C6 gate (`c6/gate.py`) against R1 |
| R3 | Re-derive the E2 cell rule (5 %, 20 windows) and its 0.4 m bound on R1 truths at the eight E2 boxes: per box, corrected against uncorrected error, with the truth's interval beside the 0.3 m criterion; re-score mutual-information registration at the urban boxes |
| R4 | Ferrybridge lean: inspect its 20 roof strips by eye for buildings changed between the 2021 lidar and the 2025 imagery, refit without any that changed |
| R5 | E4 edge leakage re-scored only at guide edges beyond 0.58 h_max + 1 m from any lidar nDSM above 2 m, shadows masked, on the saved E4 and E4b outputs |
| R6 | E8 re-render: roof planes, raw-point Delaunay and the current mesh with lean-corrected texture (`c3c4/l500`), textured and shaded, same views, for the owner |
| R7 | Review page with every re-scored item and the R6 renders; `metric-bias-results.md`; `status.md` |

Each re-score comes to the owner with renders or strips beside it. Any change to the shipped
correction (F2, the cell rule, the bound) is a separate decision with its own plan.

## Part 3: learned-height model development

Starts after Part 2. Candidates and evidence are in `e4-research-2.md`. Every model is tried in
its own scratch environment (some ship for Python 3.8 to 3.10, which uv installs); one that earns
a place moves into `ml/` beside PixTransform, behind the same file contract.

### What it settles

Which pretrained or fine-tuned model turns one Esri image into height above ground that, laid
onto the coarse DEM, looks closest to the lidar by eye at x30 and x5, without flat-ground bumps.

### Composition onto the coarse DEM

N = a model's height above ground on the 1 m grid. Recipes from `e4-research-2.md`, step 4:

| Code | Output |
| --- | --- |
| M-A | K(s) + (N - K(B(N))) (the B form above, N as the trend); reproduces s |
| M-B | K(B(DTM)) + N: bare-earth base plus model height; proxy for FABDEM plus N in Yemen |
| M-C | M-B with a per-coarse-cell gain on N fitted so each cell mean matches s; proxy for GLO-30 (Song 2025, Prior2DSM 2026) |

### Stages

| Stage | Work |
| --- | --- |
| M1 | Zero-shot sweep on the 540 m boxes, then the 5.4 km areas: RS3DAda (with and without test-time augmentation), the Geopose first-place model (height and lean field), CHMv2 tiles and its DINOv3-Sat DPT head (trees), Depth Anything 3 Mono-Large and Metric-Large and V2 Small with a per-tile scale and shift fit (Song 2025), Depth Any Canopy. Scored as nDSM against lidar nDSM and after M-A, M-B, M-C |
| M2 | Guided refinement with learned features: PixTransform with DINOv3-Sat and DINOv2 patch features as the guide in place of RGB. Not published for DSMs (`e4-research-2.md`), so it comes to the owner as new work before it is built |
| M3 | Fine-tuning on England: Esri z19 and EA lidar nDSM from 5.4 km areas other than the test areas, split by geography. RS3DAda with BitFit (Song 2025); Depth Anything V2/V3 Small or Base with its DPT head trained on nDSM; DINOv3-Sat frozen with a DPT head as in Siméoni et al. 2025 sec. 8.2. Frozen encoders to fit 12 GB |
| M4 | Coarse-DEM conditioning: PromptDA-Small (Apache) fine-tuned with the degraded DSM as its prompt, after Rafaeli et al. 2025 |
| M5 | Yemen dry run on one Sana'a or Aden tile with the best model: FABDEM plus N and GLO-30 with scaled N, checked by eye and against ICESat-2 ATL08 points where present |

Screening per model (`e4-research-2.md`): flat-ground edge slope against twice the lidar's and
x30 RMSE against kriging are reported; the owner's preference by eye decides.

## Decisions for the owner

| Fork | Options | Recommendation |
| --- | --- | --- |
| Areas | The three above; or others | All three |
| Tuning budget | 12; 24; 48 configurations per factor | 24 |
| Seeds R | 1; 4; 8 | 4 at 2,700 and 5,400 m; 1 at 1,080 m |
| Fine-tuning data (M3) | Number and spread of England training areas | Ten 5.4 km areas across England, town and country, none touching the test areas |

## Risks

- PixTransform's x and y input channels let its colour-to-height mapping drift across a large
  training area; extents 1,080, 2,700 and 5,400 m are compared for this reason.
- `correct` holds every cell's lidar points at once, about 2 GB per worker; a 5.4 km box spans
  about 36 1 km cells. Measured on the first area; a bounded reader is open work if it runs out of
  memory (49 GB on this machine).
- Kriging at x5 over 5.4 km is 1.17 M cells; run per 1,080 m block.
- Scores on block-averaged lidar remain a best case for GLO-30 (radar, not an average).
- Zero-shot overhead height models rely on shadows (Song 2025: Depth Anything V2 MAE 11.98 m on
  shadowless scenes); Esri scenes vary in sun angle.

## Not in scope

- The Southend north overshoot (TODO, Later).
- Any change to the pipeline packages beyond writing the `ml/` input files.
