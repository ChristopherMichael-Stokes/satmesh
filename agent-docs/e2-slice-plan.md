---
status: current
topic: height-refinement
summary: Plan for the E2 slice: a U-Net trained on EA lidar at Upper Aire and Southend, fitted to 30 m block means, tested on the held-out Ferrybridge 540 m box at x30 against `avg_ma`, `e0m` and PixTransform; inputs, split, loss, GPU hours and forks for the owner.
answers: What does the E2 slice train and test on; how is the E2 train and test split drawn; what loss does E2 use; how many GPU hours does the E2 slice cost; which E2 choices wait for the owner
---

# E2 slice plan: a height model trained on England lidar

Drafted 2026-10-30 for the owner's approval. Proposal context: `pixtransform-proposal.md` (design
2, E2 row). Nothing in this plan has run. GPU-hour figures are estimates, measured on the first
smoke run before any longer run starts.

## What the slice settles

Whether supervision on EA lidar gives a held-out area that looks better than `e0m` (and than
PixTransform on object recovery) at x30. Judged by eye in Blender on GLBs; scores sit beside them
and never decide (`e4b-results.md` caveat).

## Split

| Role | Area | Use |
| --- | --- | --- |
| Train | Southend (building-rich), Upper Aire (moor, no buildings) | 540 m boxes sampled from the 5.4 km areas |
| Early-stop check | 4 boxes held back from each training area, 270 m gap to any training box | loss plateau only, never reported as a result |
| Test | Ferrybridge 540 m box (SW corner BNG 448000, 424000), the box E0 and E1 were judged on | one pass, never used for any choice |

Ferrybridge is held out as a whole area, so the model sees no Ferrybridge pixel in training, and
the E0 and E1 surfaces compare on the same box. Upper Aire as test box would mean 12 building
tokens; Southend and Ferrybridge are the building areas, so Southend trains. The second fold
(hold out Upper Aire or Southend) runs only after the owner has read this one.

## Inputs

All at 1 m on the 5.4 km grid of each area, row 0 north.

| Channel | Source | State |
| --- | --- | --- |
| RGB | Esri z19 at 0.5 m area-averaged to 1 m (`seg/work/{area}-image.npz`, uncorrected) | exists |
| Prior | Mean of RS3DAda and Geopose height above ground (as `avg`) | missing over the 5.4 km areas; only the two 540 m boxes exist |
| DINOv3-Sat | 16 PCA channels of the 8 m tokens, PCA fitted on the two training areas, bilinear to 1 m | features exist (`seg/feats/`); PCA missing |
| Coarse base | Kriging `K(s)` of the 30 m source, one channel | missing |
| Coords | x, y in metres from the box centre | trivial |

Target: EA first-return DSM, 1 m, from the cached WCS composites (`~/.cache/satmesh/ea-lidar-composite`,
3,173 DSM files). Coarse source `s`: 30 m block means of that DSM (the synthetic source; real
GLO-30 is a second step, see forks).

Prior inputs for 60 boxes (30 per training area, stratified on lidar building and vegetation
fraction from `seg/work/*-labels.npz`) plus the Ferrybridge box: RS3DAda without flip-TTA about 23
s per box, Geopose 8 s with its TTA, total about 40 min GPU. Whole-area priors (about 200 boxes)
cost about 2.3 h and wait for a promising fold.

Deviations from design 2 in the slice, each to be added back only if the slice earns it:

- No class-probability channels: the head's labels would have to be out-of-fold for the training
  areas, and its DINO features are already an input.
- No CHMv2 channel: not measured as a supervised input; trees come from lidar supervision.
- Uncorrected imagery: lean-corrected Esri exists only as per-vertex UVs in the stores, not as a
  raster; the best-shift loss and shift augmentation (below) absorb the registration offset, and
  the test box uses the same uncorrected input as training.

## Model

U-Net, four levels, 32 to 256 channels, about 2 M parameters, 23 input channels (RGB 3, prior 1,
PCA 16, `K(s)` 1, coords 2), receptive field above 100 px so one network sees several 30 m cells.
Output is a height correction `delta` added to `K(s) + prior` in metres, last layer zero-
initialised (ControlNet pattern, as in E1) so step 0 is the `avg_ma` surface. A projection step
(iterative back-projection, `h <- h + upsample(s - B(h))`) makes every 30 m cell match `s` after
the net, as E1 did. Crops 384 px, batch 6, random flips and 90-degree rotations, shift of the
guide by up to 2 m against the target.

## Loss

Huber (delta 0.5 m, no source: tunable, named as such) on height after the best integer shift
within +-2 m between prediction and target, per crop (adapted from the PROBA-V cPSNR idea,
unproven for height), plus a gradient loss of weight 1 on `|grad h|` (NAIMA; established for
supervised depth). No smoothness, anchor or cell terms: supervision carries the object-height
signal that E1 lacked, and the projection enforces the cells.

## Procedure and cost

| Step | What | GPU time (estimate) |
| --- | --- | --- |
| 0 | Smoke: 2 boxes, 200 steps, all stages through scoring and GLB writing | 5 min |
| 1 | Priors, PCA, kriging `K(s)` per box (kriging is CPU, about 7 min per 540 m box at x30; 61 boxes in 6 processes about 70 min) | 40 min GPU, 70 min CPU |
| 2 | Train: 20,000 steps, Adam 1e-3 with cosine decay, early-stop check every 500 steps, log line per 500 steps to `uncommitted/e2/train.log` | 1 to 2 h |
| 3 | Infer the Ferrybridge box at x30, project, write npz in the E0 format | 1 min |
| 4 | GLBs for Blender with `lidar`, `avg_ma`, `e0m`, `e1`, `e2` at x30, via a copy of `e0/glbs_e0.py`; scores (RMSE, building and tree bias, edge slope, cell residual) beside | 10 min |

Total about 2 to 3 h GPU plus 70 min CPU, 2 to 3 h of wall time; the kriging runs overlap with
the Geopose and RS3DAda passes. The training run exceeds a short session, so it starts only on
the owner's go after the smoke passes. Scratch: `uncommitted/e2/`; no scratch is deleted. A
module in `ml/` is created only if the slice earns it.

## Forks for the owner

1. Real GLO-30 as a second source (proposal: train on real GLO-30 over England as well, because
   synthetic degradation transfers badly). Needs a fetch from the Copernicus bucket and a
   datum decision (GLO-30 is a DSM on EGM2008; the stores use OSGM15). Recommendation: after the
   slice reads well on block means.
2. Controls in the same run: an `e2_noprior` model (prior channel zeroed) and an
   `e2_nodino` model, 1 to 2 h GPU each. Recommendation: `noprior` only, since the owner's hope
   rests on the embedding prior.
3. Per-tile design 1 fit on top of the supervised output. Recommendation: not in the slice; E1
   showed that objective carries no object-height signal.
4. Vehicle policy for the training target: cars absent from older lidar. Recommendation: train
   on the DSM as is.
