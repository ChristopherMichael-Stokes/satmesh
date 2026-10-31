---
status: current
topic: height-refinement
summary: E2 slice results: a U-Net trained on Upper Aire and Southend lidar scores RMSE 1.63 m at Ferrybridge x30 against 1.72 for e0m, then ranked behind avg_ma on a blind West Yorkshire square; overfits after about 2,000 steps.
answers: What did the E2 slice train on and how was it split; how does the supervised model score against e0m and avg_ma at Ferrybridge x30; how fast does E2 overfit; where are the E2 inputs, code and GLB; which traps did E2 find
---

# E2 slice results: height model trained on England lidar

Run 2026-10-30. Plan: `e2-slice-plan.md`. Scratch code, inputs and outputs: `uncommitted/e2/`
(`e2lib.py` model and loss, `train.py`, `infer.py`, `prep_boxes.py`, `predict.py`,
`krige_boxes.py`, `conditioning.py`, `glbs_e2.py`; log `e2.log`, `train.log`). GLB for Blender:
`uncommitted/e4b/e0/glb/ferry-e2-x30.glb`, beside the E0 set. The owner's reading decides; scores
are secondary (`e4b-results.md` caveat).

## Setup as run

- Train: 44 aligned 540 m boxes of Upper Aire and Southend, validation 8 boxes of the same areas
  (plateau check only), test the Ferrybridge box (BNG 448000, 424000), never seen in training or
  in any training input. Southend has 22 boxes with at least 95 % labelled lidar cells, Upper Aire
  30 of 77.
- Inputs at 1 m, 27 channels: corrected Esri RGB, mean of RS3DAda (4-flip) and Geopose height,
  CHMv2 at 0.5 m, five class probabilities (head trained on the other training area only), 16 PCA
  channels of DINOv3-Sat tokens (fitted on the two training areas), kriged coarse DSM relative to
  the crop mean. Source `s`: 30 m block means of the EA DSM. Base `X0 = K(s) + N - K(B(N))`.
- Imagery correction from each area store's `correction.json`. At the test box the area fit moves
  the guide a median 2.24 m north, the older 540 m box store (used by E0 and E1) 1.24 m.
- Net: U-Net, 3 poolings, 32 to 256 channels, zero-initialised head, 360 px crops on the coarse
  cell grid, batch 6, AdamW 1e-3 with cosine decay. Loss: Huber 0.5 m on height after the best
  shift within +-2 px, gradient L1, cell-mean Huber (weight 1). No coordinate channels, no
  augmentation. Exact projection after inference: `h = X + K(s - B(X))`.

## Measurements (Ferrybridge box, x30; RMSE m against the lidar DSM)

| Surface | RMSE | Building bias | Tree RMSE | Ground RMSE | Cell residual max |
| --- | --- | --- | --- | --- | --- |
| `avg_ma` (old guide, E0) | 2.294 | -1.50 | | | |
| `avg_ma` (new guide) | 2.377 | -1.63 | 2.61 | 2.31 | 0.03 |
| `e0m` (E0) | 1.723 | -1.89 | 2.68 | | |
| E2 before projection | 1.711 | -0.88 | 2.09 | 1.58 | 1.58 |
| E2 | 1.634 | -0.97 | 2.01 | 1.48 | 0.007 |

Cell-edge step ratio 1.03. Ground lift over 1 m 22.4 % and false lift 18.1 %.

- Training: validation RMSE 1.28 to 1.33 m from step 2,000, validation loss best near step 6,000
  and stopped at 9,500 by the plateau rule; training data loss 0.086 against 0.92 on validation.
  Overfitting is fast on 44 boxes.
- Scores say E2 beats `e0m` on tree and building bias; whether the roofs and walls look better is
  the owner's call.

## Traps

- RS3DAda with 4-flip TTA took 34 to 90 s per box alone, 14 min per box when sharing the 12 GB
  GPU with CHMv2.
- The conditioning script's PCA projection came out transposed; fixed.
- Model drivers import a module named `common`; any script that reuses them cannot have its own.

## Owner's reading and the blind comparison

- Ferrybridge x30 GLB: the owner called the buildings and foliage "insane" for a 30 m input, with a
  wonky road beside the river remaining, and approved a larger training corpus (`decisions.md`).
- Blind comparison, 2026-10-30: a random 2,160 m square in West Yorkshire (BNG SW corner 414820,
  426080; 18 % of pixels raised; Esri native depth z18; coarse source 30 m block means of the EA
  DSM, not GLO-30). Surfaces: kriging only, `avg_ma`, `e0m`, E2 under random labels A to D
  (`uncommitted/blind/key.json`: A `e0m`, B E2, C kriging, D `avg_ma`). Owner: C a write-off;
  D closest to the lidar in recall and shapes; A and B worse, with wonkier roofs. So `avg_ma`
  beat E2 on a new square.
- Scores on that square, secondary (`uncommitted/blind/data/scores.json`; RMSE m): kriging 1.99,
  `avg_ma` 1.85, `e0m` 1.66, E2 1.98; raised-pixel bias -2.9, -1.4, -2.1, -2.3.
- Likely causes, untested: 44 training boxes from two areas, early overfitting, a coarser z18 image
  than the training imagery.

## Rerun and where things are

- Pipeline for a new square (all under `uncommitted/blind/`): `select_site.py`, `store.sh` (build
  and correct), `prep_site.py`, `image_site.py`, `gpu_chain.sh` (RS3DAda, Geopose, CHMv2, DINO
  tokens), `blind_cond.py` (class heads and PCA), `krige_site.py ks|kn|kn0|proj`, `variants.py raw|final`,
  `glb_site.py`. A 2 km square costs about 17 min GPU and 15 min CPU; 30 squares would take 10 to
  12 h. The 52-box training set and its builders are in `uncommitted/e2/` (`prep_boxes.py`,
  `predict.py`, `krige_boxes.py`, `conditioning.py`, `train.py`, `infer.py`).
- Tiles of the blind GLBs left a 1 m gap between each other; overlap each tile by one row and column
  next time. Future comparisons ship as one `.blend` with a collection per surface (owner request).
