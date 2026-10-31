---
status: historical
topic: height-refinement
summary: E4 trial of PixTransform, bilinear, guided filter and kriging on Ferrybridge and Upper Aire at x2, x5, x30; kriging scores best, PixTransform copies texture but looks closest at x30 by eye.
answers: How did PixTransform compare with bilinear and kriging on lidar-truth tests?; Why can the E4 RMSE scores not be trusted as a verdict?; How much slope does PixTransform add on flat ground?; How was the E4 trial set up (sites, factors, guide)?; Does the guided filter beat bilinear?
---

# E4 results: fine height detail from coarse elevation data

Trial of `e4-research.md`'s first candidate, 2026-10-29. Review page for the owner:
<https://claude.ai/artifact/6v1CiNcDK3SGErJ6jvixce>. Scripts and outputs in
`uncommitted/scratch-archive/e4/` (git-ignored); each script's docstring carries its run command.

> **The scores below cannot be trusted as a verdict.** The lidar reference and the Esri image do
> not describe the same ground in the same place: roofs lean in the image by up to tan 30 per
> metre of height, registration is good to about a metre at best, the two were captured years
> apart, and a first-return DSM has its own edge smearing. A method that puts a correct building
> 1 to 2 m off, or with the image's shape rather than the lidar's, is punished as heavily as one
> that invents relief. Ranked by RMSE alone, E4 would have thrown out PixTransform, the only
> method that forms buildings at x30, which the owner judged by eye to be by far the closest to
> the lidar. The owner's judgement of the renders decides; the scores are a secondary check.

## Conclusions

- By eye (owner, 2026-10-29), PixTransform at x30 is by far the closest to the lidar: the smooth
  methods cannot form buildings at all. At x2 and x5, bilinear and kriging trade blows and
  PixTransform looks worse than its own x30. By RMSE it ranks last at x2 and x5 and level with
  bilinear at x30; that ranking reflects the reference's limits as much as the method.
- It copies photo texture into relief. On flat lidar ground under a photo edge, its mean slope is
  0.19 to 0.74 m per m at Ferrybridge against 0.033 in the lidar and 0.05 to 0.12 for bilinear.
  This is the failure `e4-research.md` named. Shifting the photo 1 or 3 m barely changes it, so
  part of it is texture; the rest of the score is open to the reference's limits above.
- Area-to-point kriging has the lowest RMSE everywhere (smooth surfaces are rewarded by this
  reference), reproduces every coarse cell exactly, and
  adds no photo texture. It adds no detail either: it is the best smooth base, not a detail
  method.
- The guided filter is worse than bilinear everywhere, as the survey's NYU numbers predicted.
- By the research's own reasoning, candidates 4 and 5 (monocular depth, a trained guided network)
  inherit the texture-copying risk. The owner judged the technique worth pursuing (`e4b-plan.md`).

## Setup

- Sites: Ferrybridge (BNG 448000 424000) and Upper Aire (399750 447250), 540 m boxes split into
  four 270 m tiles (270 divides by 2, 5 and 30). Stores built and corrected with `satmesh build`
  and `satmesh correct`; Ferrybridge took the 2025-07-16 LG01 lean (t -0.53 E +1.24 N m, 0.20 m
  per m toward 162 deg), Upper Aire the cell shift (-0.48 E +0.79 N m, no roofs).
- Truth: EA 1 m first-return DSM. Source: its block means at x2, x5, x30. Guide: Esri z19 on the
  1 m BNG grid through OSTN15, displaced by the store's correction (t + l h per pixel where a
  scene's lean is applied, else the cell shift).
- Methods: bilinear (cv2 `INTER_LINEAR`); guided filter (He 2013, OpenCV contrib, radius =
  factor, eps 0.1^2 on a [0, 1] guide); area-to-point ordinary kriging (Kyriakidis 2004; point
  exponential covariance fitted by regularisation to the coarse semivariogram, Journel and
  Huijbregts 1978 / Goovaerts 2008; 17 x 17 block neighbourhood; trial-only code, owner choice);
  PixTransform (de Lutio 2019, repo commit 3db98d5, published defaults, RGB guide).
- Scores per `e4-research.md` protocol: RMSE, MedAE, NMAD overall, by DTM slope class and by cover
  (nDSM > 2 m split by excess green); edge leakage = mean |grad h| at Canny guide edges where the
  lidar slope is under 0.1; coarse-cell residual. Guide shifted 1 and 3 m north at x2 and x5 (x30
  shifts cut by the owner for runtime).

## Measurements

RMSE in m, unshifted guide, all pixels of the 540 m box:

| Site, factor | Bilinear | Guided | Kriging | PixTransform |
| --- | --- | --- | --- | --- |
| Ferrybridge x2 | 0.57 | 0.89 | **0.48** | 1.74 |
| Ferrybridge x5 | 1.03 | 1.43 | **0.87** | 1.71 |
| Ferrybridge x30 | 2.12 | 2.27 | **2.08** | 2.33 |
| Upper Aire x2 | 1.46 | 1.66 | **1.43** | 2.08 |
| Upper Aire x5 | 1.71 | 1.88 | **1.66** | 2.05 |
| Upper Aire x30 | 2.26 | 2.58 | **2.17** | 2.28 |

Edge slope at flat guide edges, m per m (lidar 0.033 Ferrybridge, 0.041 Upper Aire):

| Site, factor | Bilinear | Guided | Kriging | PixTransform |
| --- | --- | --- | --- | --- |
| Ferrybridge x2 | 0.084 | 0.124 | 0.097 | 0.301 |
| Ferrybridge x5 | 0.121 | 0.129 | 0.172 | 0.354 |
| Ferrybridge x30 | 0.050 | 0.066 | 0.075 | 0.739 |
| Upper Aire x30 | 0.042 | 0.048 | 0.046 | 0.185 |

- Guide shift 0 / 1 / 3 m north, PixTransform RMSE: Ferrybridge x2 1.74 / 1.70 / 1.75, x5 1.71 /
  1.74 / 1.70; Upper Aire x2 2.08 / 2.11 / 2.14, x5 2.05 / 2.10 / 2.11.
- Coarse-cell residual (max |cell mean - source|): kriging 0.00 at x2 and x5, 0.02 m at x30;
  PixTransform up to 17 m (its consistency is a soft training loss only).
- PixTransform runtime on the RTX 4070 Ti: about 90 s per 270 m tile at x2 and x5, 8 min at x30
  (20 min with two processes on the GPU).
- PixTransform schedule (`pix-progress*.log`): 18 runs (2 sites x guide shifts 0, 1, 3 m north x
  x5, x2, x30) in `run_all.sh` and `run_all_2.sh`, two processes in parallel; the x30 runs were
  executed for the unshifted guide only. Logged four-tile runs: x2 and x5 6.6 min each (about
  100 s per tile), x30 60 min at Ferrybridge and 43 min at Upper Aire with two processes sharing
  the GPU. Both scripts hard-code the interpreter path of a /tmp session scratchpad
  (`.../3047c0e6-.../scratchpad/torchenv/bin/python`); `e4b/m1/run.sh` does the same. The `torchenv`
  recreate command is in `e4b-plan.md`; `m1-model-recipes.md` holds the M1 environments.

Fitted point covariance of the kriging, C(h) = sill exp(-3 h / range), by regularisation to the
coarse semivariogram (`out/kriging-variograms.json`, `krige-progress.log`):

| Site, factor | Sill (m2) | Practical range (m) |
| --- | --- | --- |
| Ferrybridge x2 | 6.28 | 27.3 |
| Ferrybridge x5 | 7.08 | 53.6 |
| Ferrybridge x30 | 8.10 | 423 |
| Upper Aire x2 | 1.7e5 | 1.6e6 |
| Upper Aire x5 | 6.6e7 | 3.8e8 |
| Upper Aire x30 | 4.6e7 | 1.1e8 |

Scorer strata, NMAD in m, unshifted guide, the four methods of the RMSE table (`scores.json`; the
file also holds MedAE and the other trial methods and is read by `e4b/m1/tables.py`). Slope class
by DTM slope, cover as in Setup. Pixels per stratum, Ferrybridge: slope under 5 deg 234,953,
5 to 15 deg 34,151, 15 to 30 deg 12,680, over 30 deg 5,512; open 235,772, trees 48,229, buildings
7,599. Upper Aire: 127,476, 123,085, 32,683, 4,052; open 266,185, trees 25,273, buildings 142.
Each site has 291,600 pixels.

| Site, factor | Method | MedAE | NMAD | Slope under 5 | 5 to 15 | 15 to 30 | Over 30 | Open | Trees | Buildings |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Ferrybridge x2 | Bilinear | 0.054 | 0.079 | 0.05 | 0.22 | 0.18 | 0.23 | 0.04 | 0.50 | 0.20 |
| Ferrybridge x2 | Guided | 0.189 | 0.268 | 0.21 | 0.49 | 0.42 | 0.46 | 0.14 | 0.93 | 0.63 |
| Ferrybridge x2 | Kriging | 0.059 | 0.087 | 0.07 | 0.18 | 0.13 | 0.20 | 0.06 | 0.45 | 0.18 |
| Ferrybridge x2 | PixTransform | 0.305 | 0.445 | 0.38 | 0.75 | 0.79 | 0.78 | 0.30 | 2.36 | 1.58 |
| Ferrybridge x5 | Bilinear | 0.233 | 0.332 | 0.27 | 0.58 | 0.48 | 0.52 | 0.18 | 1.10 | 0.90 |
| Ferrybridge x5 | Guided | 0.499 | 0.678 | 0.59 | 0.95 | 0.86 | 0.83 | 0.43 | 1.70 | 1.20 |
| Ferrybridge x5 | Kriging | 0.208 | 0.309 | 0.27 | 0.49 | 0.37 | 0.46 | 0.22 | 1.06 | 0.65 |
| Ferrybridge x5 | PixTransform | 0.315 | 0.465 | 0.38 | 0.87 | 0.86 | 0.88 | 0.31 | 2.16 | 1.60 |
| Ferrybridge x30 | Bilinear | 1.173 | 1.365 | 1.28 | 1.54 | 1.54 | 1.41 | 1.04 | 2.42 | 1.82 |
| Ferrybridge x30 | Guided | 1.439 | 1.437 | 1.28 | 1.63 | 1.81 | 1.65 | 1.02 | 2.54 | 2.03 |
| Ferrybridge x30 | Kriging | 1.010 | 1.348 | 1.31 | 1.50 | 1.37 | 1.25 | 1.04 | 2.38 | 1.82 |
| Ferrybridge x30 | PixTransform | 1.093 | 1.602 | 1.55 | 1.69 | 1.94 | 2.04 | 1.30 | 2.36 | 3.01 |
| Upper Aire x2 | Bilinear | 0.016 | 0.024 | 0.02 | 0.03 | 0.10 | 1.69 | 0.02 | 2.26 | 5.81 |
| Upper Aire x2 | Guided | 0.032 | 0.047 | 0.03 | 0.05 | 0.25 | 2.45 | 0.04 | 2.87 | 5.71 |
| Upper Aire x2 | Kriging | 0.013 | 0.019 | 0.01 | 0.02 | 0.08 | 1.34 | 0.02 | 2.15 | 4.84 |
| Upper Aire x2 | PixTransform | 0.150 | 0.222 | 0.14 | 0.25 | 0.66 | 3.52 | 0.20 | 4.40 | 5.62 |
| Upper Aire x5 | Bilinear | 0.035 | 0.052 | 0.04 | 0.06 | 0.27 | 2.60 | 0.05 | 3.06 | 5.58 |
| Upper Aire x5 | Guided | 0.072 | 0.108 | 0.07 | 0.12 | 0.59 | 3.27 | 0.09 | 3.60 | 5.95 |
| Upper Aire x5 | Kriging | 0.029 | 0.044 | 0.03 | 0.05 | 0.21 | 2.22 | 0.04 | 2.89 | 6.12 |
| Upper Aire x5 | PixTransform | 0.152 | 0.225 | 0.12 | 0.29 | 0.83 | 3.57 | 0.19 | 4.18 | 5.88 |
| Upper Aire x30 | Bilinear | 0.288 | 0.418 | 0.24 | 0.56 | 1.59 | 3.90 | 0.36 | 4.45 | 5.67 |
| Upper Aire x30 | Guided | 0.625 | 0.904 | 0.39 | 1.42 | 2.74 | 4.27 | 0.78 | 5.16 | 5.71 |
| Upper Aire x30 | Kriging | 0.201 | 0.298 | 0.19 | 0.35 | 1.27 | 3.75 | 0.26 | 4.15 | 5.79 |
| Upper Aire x30 | PixTransform | 0.280 | 0.414 | 0.27 | 0.47 | 1.40 | 3.84 | 0.36 | 4.67 | 5.74 |

- MedAE and NMAD sit far below the RMSE everywhere (Upper Aire x2 bilinear MedAE 0.016 m against
  RMSE 1.46 m): the RMSE is carried by trees, buildings and slopes over 15 degrees. On open ground
  at x2 and x5 PixTransform's NMAD is 1.7 to 10 times the smooth methods' (Ferrybridge x2 0.30 m
  against 0.04 for bilinear, Upper Aire x2 0.20 against 0.02), consistent with the texture copying
  on flat ground.

## Scratch kept and scratch regenerated

- `uncommitted/scratch-archive/e4/` is kept: `e4b/m1/common.py`, `e4b/e0/common.py`,
  `e4b/dino/common.py`, `e4b/m1render.sh`, `e4b/s1.sh`, `e4b/m2render.sh`, `e4b/combine.py` and
  `e4b/s2_check.py` read its inputs, `out/`, `scores.json` and scripts (checked by grep, 2026-10-31).
- `glb/` (78 GLBs, 990 MB) and `page/` (216 MB) are deleted; the scripts regenerate them from
  `out/`, `*-inputs.npz` and `*-texture.npz`, run from `pipeline/` (`e4b/s1.sh` runs them in order).
- `glb/` held `SITE-SURFACE.glb` for the two sites, 39 surfaces each: `truth`, then `bilinear`,
  `guided`, `kriging`, `pix`, `pixa`, `pixb` at x2, x5 and x30 (`pix-x2.glb`), and at x5 and x30
  `bil`, `avg_ma`, `avg_mu`, `geo_ma`, `geo_mc`, `geo_mu`, `rs3dtta_ma`, `rs3dtta_mc`,
  `rs3dtta_mu`, `chmtiles_mb` (`glbs.py` writes them; textured at 0.25 m).
- `page/` held `index.html`, `views.json` and `data.json`, 1,640 PNG renders in `img/` (for example
  `aire-err-avg_ma-x30.png`, `ferry-worst-ground-tex-truth.png`) and 128 JPEG strips in `strips/`
  (for example `aire-tile0-ground-tex-x5.jpg`, `aire-err-x2.jpg`). `render.py` writes `img/` and
  `views.json`; `make_page.py` reads them and writes `strips/` and `data.json`.

## Traps

- PixTransform at x30 runs 12,945 epochs of 3 tiny batches per tile; per-epoch Python overhead
  dominates, and two processes on one GPU halve each one's speed there.
- PixTransform has no nodata mask and does not enforce consistency; its `utils.utils` imports the
  removed `scipy.misc`, so only `pix_transform/` is vendored.
- Upper Aire's fitted kriging covariances are degenerate: sills of 1.7e5 to 6.6e7 m2 and practical
  ranges of 1.6e6 to 3.8e8 m, against 6 to 8 m2 and 27 to 423 m at Ferrybridge. The DSM there has
  a trend, not a stationary variogram, so the kriging there behaves as an almost linear trend
  interpolator; its Upper Aire scores are the best-smooth-base result, not evidence for the
  exponential model.
- The greenness cover split is unreliable: Ferrybridge has 7,599 "building" pixels against 48,229
  "tree" pixels, and Upper Aire 142 building pixels. Per-cover numbers are indicative only.
- Ground cameras 30 m back can stand against a wall (Ferrybridge tile 0); views were fixed by rule
  before results and not moved.
- `pkill -f <script>` from the tool shell matches the shell's own command line and kills it.

## Not checked

- Real coarse sources (GLO-30, OS Terrain 50): scores on degraded lidar are an upper bound.
- A residual (mass-preserving) correction on PixTransform, other PixTransform settings, and a
  greyscale or shadow-masked guide.
- The pipeline's 0.5 m bilinear mesh; renders use plain 1 m grids for every method.
