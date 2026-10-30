---
status: historical
topic: height-refinement
summary: DINOv3-Sat feature probes on two 540 m boxes and the land-cover head over three 5.4 km areas; within-box probes work, leave-one-area-out transfer is limited.
answers: How well do frozen DINOv3-Sat features predict height and raised pixels?; How accurate is the land-cover head leave-one-area-out?; How were land-cover labels derived from EA point-cloud classes?; Do DINOv3 features separate grey roofs from pavement?; What are the limits of the land-cover head?
---

# DINOv3-Sat features: probes and the land-cover head

2026-10-30. Summary in `e4b-results.md`; this file holds the tables and the choices behind them.
Scratch code and outputs: `uncommitted/e4b/dino/` (probes on the two 540 m boxes) and
`uncommitted/e4b/seg/` (land-cover head over the three 5.4 km areas). Review page for the probe
figures: <https://claude.ai/artifact/Mm9qo191AAYuQM9chP8RHs>. Model recipe: `m1-model-recipes.md`.

## Probe on the two 540 m boxes (frozen last-layer features, ridge and logistic)

Setup: input 2,160 px at 0.25 m (token 4 m, "s4") and the 0.5 m area average cropped to 1,072 px
(token 8 m, "s8"); whole image in one pass, 2.25 GB peak, 1 to 2 s. Labels: lidar nDSM block mean
per token; raised = token mean above 2 m (prevalence Ferrybridge 19 to 20 %, Upper Aire 11 to
12 %). Ridge alpha and logistic C chosen on the east 25 % columns of the training box.

Cross-box (train on one, test on the other), s8, last layer; grey = tokens with saturation under
the test box's median and luma above 0.15:

| Direction | R2 | AUC | grey AUC | RGB baseline AUC (grey AUC) |
| --- | --- | --- | --- | --- |
| Ferrybridge to Upper Aire | 0.04 | 0.85 | 0.83 | 0.96 (0.94) |
| Upper Aire to Ferrybridge | 0.01 | 0.76 | 0.80 | 0.59 (0.62) |

Within one box (west 75 % train, east 25 % test), last layer: Ferrybridge s4 R2 0.56, AUC 0.93, grey
AUC 0.94, RGB R2 0.01 and AUC 0.54; s8 R2 0.66, AUC 0.93; Upper Aire s4 R2 0.68, AUC 0.98; s8 R2
0.75, AUC 0.99. The last layer beat hidden state 12 everywhere. Within-box numbers are optimistic
(the test band abuts the training region). Cross-box failure is probably content: Upper Aire has
no buildings and Ferrybridge no woodland. Best cross-box configuration by mean R2 was s8 last
(0.026). Upsampling the best prediction to 1 m beats predicting zero by 0.15 to 0.33 m
(RMSE 2.99 and 2.29 m against 3.14 and 2.62 m); token means of the lidar alone floor at 1.84 and
1.35 m; flat-edge slope of the predicted surface 0.064 and 0.138 against the lidar's 0.042 and
0.033.

## Land-cover head over the three areas

### Lidar classes and labels

ASPRS classes present (all returns inside each 5.4 km box): ground 2 (31.6 to 47.9 million
points), low, medium and high vegetation 3 to 5 (about 11 million at Ferrybridge and Southend, 8.8
million at Upper Aire), building 6 (3.5, 1.3 and 5.7 million), unclassified 1, noise 7, class 8
only at Southend (151,782). No water class (9) exists in any area, so water is untestable. Mapping:
3 to 5 vegetation (low vegetation, grass included, is vegetation), 2 ground, 6 building, all
other codes 'other'. Per 1 m cell the majority class of all returns; cells without points are no
data (Southend 4.3 million cells, estuary and a lidar gap).

Valid 8 m tokens (at least 50 % labelled cells) and their majority class:

| Area | Valid | Ground | Vegetation | Building | Other |
| --- | --- | --- | --- | --- | --- |
| Ferrybridge | 445,852 | 386,432 | 29,372 | 29,955 | 93 |
| Upper Aire | 452,383 | 424,504 | 17,052 | 10,805 | 22 |
| Southend | 414,421 | 319,551 | 37,512 | 56,947 | 411 |

### Features and heads

Esri zoom 19, uncorrected, resampled to 0.5 m through OSTN15 with the `prep.py` smoothing; 1,008 px
windows (63 x 63 tokens), stride 31 tokens (496 px, since 504 px is 31.5 tokens) with a clamped
final window, separable tent weights (floor 0.05), last hidden state minus CLS and the 4 register
tokens, fp16. 361 windows per area, about 40 s. Heads: logistic regression and a two-layer MLP
(hidden 256, AdamW 1e-3, weight decay 1e-4, batch 4,096, at most 40 epochs, patience 4, unweighted
cross-entropy, features standardised on training tokens); early stopping on the right 20 % of
columns of each training area with a 1 % gap. Baselines: token mean RGB and std (6 values),
logistic and `HistGradientBoostingClassifier` (200 iterations, 300,000 sampled tokens). The
logistic heads hit the 40-epoch cap and may be under-trained.

### Results, leave-one-area-out, DINOv3 MLP

| Test area | Accuracy | Ground F1 | Vegetation F1 | Building F1 (IoU) | RGB gradient boosting building F1 |
| --- | --- | --- | --- | --- | --- |
| Ferrybridge | 0.876 | 0.930 | 0.308 | 0.725 (0.568) | 0.320 |
| Upper Aire | 0.953 | 0.976 | 0.140 | 0.789 (0.652) | 0.229 |
| Southend | 0.870 | 0.923 | 0.217 | 0.818 (0.692) | 0.158 |

- Vegetation recall is 0.08 to 0.31; most vegetation tokens are predicted ground. The cause is the
  majority label: ground returns under a canopy outvote vegetation returns. 'Other' is never
  predicted. Overall accuracy hides this because ground is 70 to 89 % of tokens.
- Confusions (true to predicted, ground, vegetation, building): Ferrybridge ground 360,356,
  20,179, 5,897; vegetation 19,320, 9,100, 952; building 8,620, 388, 20,947. Southend building
  11,937, 140, 44,870.
- Grey tokens (saturation under 0.10; 28, 35 and 48 % building): building F1 DINOv3 MLP 0.705,
  0.831, 0.865; logistic 0.746, 0.802, 0.858; RGB logistic 0.395, 0.390, 0.503; RGB gradient
  boosting 0.444, 0.454, 0.456. The grey threshold was not tuned.
- Class-fraction regression (MLP on soft fractions) R2: building 0.665, 0.813, 0.790; vegetation
  0.329, 0.423, 0.498; ground 0.530, 0.630, 0.720.
- Maps (`seg/maps/`): the 1 km detail panels show large roofs as clean blocks, dense terraces as
  scattered specks, and wooded strips as vegetation where the majority label says ground.

### Limits

Three areas, one train and test split per fold; 8 m tokens lose terrace-scale gaps and gardens;
the imagery is uncorrected and offset north from the lidar by an unmeasured amount; labels were
checked by eye on two ONGs only.

## Where things are

- Features `seg/feats/{ferry,aire,southend}-feats.npz` (675 x 675 tokens), labels and imagery
  `seg/work/{area}-labels.npz`, `-image.npz`, results `seg/maps/results.json`, scripts
  `seg/{common,lidar_labels,imagery,features,heads}.py` and `run_full.sh`, log `seg/seg.log`.
- Probe scripts `dino/{extract,look,probe,maps_upsample,within,common}.py`, features
  `dino/feats/`, figures `dino/look/` and `dino/probe/`.
- The 5.4 km stores: see `e4b-results.md`.
