---
status: current
topic: height-refinement
summary: E4b results: PixTransform paused; mean of Geopose and RS3DAda anomaly on a kriging base chosen; CHMv2 for trees; DINOv3 features did not transfer; E0 mask results held for the owner.
answers: Which height model did the owner judge most faithful to the lidar?; Why was PixTransform paused after S1?; How well does CHMv2 estimate tree height?; What are the 5.4 km stores and how were they built?; What did the E0 masked anomaly surface achieve?; What traps were found in the height experiments?
---

# E4b results: PixTransform to the end, then pretrained height models

2026-10-30. Plan in `e4b-plan.md`; the successor proposal is `pixtransform-proposal.md`. Scratch
tooling and outputs are in `uncommitted/e4b/` and `uncommitted/scratch-archive/e4/` (git-ignored).
Review pages: PixTransform with cell adjustments <https://claude.ai/artifact/WJ4AqDx4DAdd2GRCHGzxFm>,
pretrained models <https://claude.ai/artifact/GBTiu16cvHBpbgkxC1GDL5>, Geopose, RS3DAda and their
mean with two bases <https://claude.ai/artifact/9hW3why4guocCyLyVjkbQy>, DINOv3-Sat outputs
<https://claude.ai/artifact/Mm9qo191AAYuQM9chP8RHs>.

> **The scores below cannot be trusted as a verdict.** Lean, registration, capture date and edge
> smearing differ between the lidar and the Esri image (`e4b-plan.md`). The owner's reading of the
> renders decides; scores are a secondary check.

## Conclusions

- PixTransform is paused. Its cell adjustments (A, B) removed the whole-cell offsets (P0 RMSE at
  Ferrybridge x2 1.74 to 0.73 and 0.62, x5 1.71 to 1.25 and 1.14, x30 unchanged at 2.33) but not the
  texture copying, erased roof dimples or flat grey roofs beside grey pavement. The owner could not
  tell A from B.
- The pretrained height-above-ground models are the better route. Geopose and RS3DAda added to the
  kriged coarse DEM as an anomaly (M-A) were judged by the owner the most faithful to the lidar,
  Geopose slightly ahead; the mean of the two is the chosen general case with a kriging base.
- CHMv2 lifts trees by 3 to 4.5 m too little at Ferrybridge and is accepted as the tree layer.
- Frozen DINOv3-Sat features separate scene types well and carry height within a scene, but did not
  transfer between the two test boxes.

## Measurements

- Port check (`satmesh_height.refine` against the original, Ferrybridge tile 0, x5): run-to-run
  RMS difference 0.344 m (original) and 0.343 m (port); original against port 0.35 to 0.41 m; RMSE
  against the lidar 1.31 to 1.32 for both. About 85 s per training either way; the original at x30
  took 439 to 611 s per tile.
- Variants A and B reproduce the coarse cell means: worst cell residual 6 mm (B at x30), about
  1e-13 m at x2 and x5.
- Zero-shot models, 540 m boxes, RMSE (m): Ferrybridge x30 kriging 2.08, Geopose M-C 1.68, RS3DAda
  M-C 1.92; Upper Aire x30 kriging 2.17, RS3DAda M-C 2.11. M-A equals kriging by RMSE; M-B is far
  worse. Mean of the two, M-A: Ferrybridge x5 0.87, x30 2.29; Upper Aire x30 2.11.
- Flat-ground edge slope stays above the lidar for every height model (RS3DAda 0.27, Geopose 0.37
  against 0.017 at Ferrybridge); the metric includes lean and registration offsets.
- Raw height-above-ground bias on raised pixels: 1.4 to 8 m too low (Geopose worst at Upper Aire).
- Depth Anything 3 and V2, fitted to height above ground, give surfaces within 0.03 m RMSE of kriging
  and add no detail.
- Cell-edge steps (mean height step at 30 m cell edges against elsewhere, x30): M-A 1.0, M-C 3.9 to
  4.2. Slope creases at cell-centre lines (second difference ratio, x5): kriging base 1.0 to 1.2,
  bilinear base Ferrybridge 1.5 to 1.6, Upper Aire 2 to 6; at x30 both about 1.0 to 1.1.
- DINOv3-Sat probes (ridge and logistic on frozen features, 4 m and 8 m tokens): within one box R2
  0.56 to 0.75, raised AUC 0.93 to 0.99, grey-token AUC at Ferrybridge 0.93 to 0.94 against 0.39 to
  0.60 for RGB; across boxes R2 about 0, AUC 0.65 to 0.85. Upsampling the best cross-box prediction
  to 1 m beats predicting zero by 0.15 to 0.33 m; token means of the lidar alone floor at RMSE 1.35
  to 1.84 m.
- Land-cover head (`uncommitted/e4b/seg/`): classes from EA point-cloud classes (ground, vegetation
  by codes 3 to 5, building by code 6; the lidar holds no water class, so water is untestable), 8 m
  tokens of frozen DINOv3-Sat features, a two-layer MLP, leave-one-area-out over the three 5.4 km
  areas. Building F1 0.725 (Ferrybridge), 0.789 (Upper Aire), 0.818 (Southend) against 0.32, 0.23,
  0.16 for gradient boosting on token RGB; vegetation F1 0.31, 0.14, 0.22 (recall 0.08 to 0.31); on
  grey tokens building F1 0.71 to 0.87 against 0.39 to 0.50 for RGB. Overall accuracy 0.87 to 0.95
  hides this because ground is 70 to 89 % of tokens.

## Recipes as run

Notation: s coarse cell means, B block mean, K area-to-point kriging (`satmesh_height`), N height
above ground at 1 m (negatives clipped to 0), d = B(dtm). Scripts `uncommitted/e4b/m1/compose*.py`.

- M-A: `K(s) + (N - K(B(N)))`; reproduces s. M-B: `K(d) + N`. M-C: M-B with a gain per coarse cell
  `g_c = (s_c - B(K(d))_c) / B(N)_c` where `B(N)_c >= 0.1 m`, else 1, clipped to `[0, 3]` (both
  constants tunable, no source); the per-cell gain causes the cell-edge steps.
- Bilinear baseline `bil` = `U(s)`, U = cv2 `INTER_LINEAR` of cell centres to 1 m pixel centres,
  edges held, over the whole box (the trial's bilinear ran per 270 m tile). `{m}_mu` =
  `U(s) + (N - U(B(N)))`; cell means match only approximately (median residual 0.02 to 0.26 m,
  largest 1.8 to 3.5 m). `avg` = mean of the Geopose and RS3DAda (TTA) N.
- Depth models: fit `s_c - B(dtm)_c = a * B(D)_c + b` per box and factor, `N = max(a * D + b, 0)`.
- Kriging fit: `fit_point_covariance` per call on its own input, so K(s) and K(B(N)) each get
  their own exponential covariance.

## Metrics defined this session

- Cell-edge step ratio: mean `|h[i+1] - h[i]|` across pixel pairs straddling lines at multiples
  of the factor, over the same elsewhere (1.0 = no seam). Same at 270 m for the trial tile edges.
- Crease ratio: mean `|second difference|` along rows and columns on the cell-centre lines
  (offset factor/2) over elsewhere; piecewise-linear bases score high by construction.
- Flat-ground edge slope: Canny (sigma 1) edges of the 1 m guide luma where the lidar slope is
  under 0.1, mean `|grad h|` of the surface there (lidar 0.033 Ferrybridge, 0.041 Upper Aire).
  It counts lean, registration and date offsets as leakage.

## The 5.4 km stores (`uncommitted/e4b/{ferry,aire,southend}-store`)

SW corners in BNG: Ferrybridge (445000, 421500), Upper Aire (397000, 444500), Southend (584500,
185600); 5,400 m boxes; EA DSM and DTM cover all three with no nodata (Southend minimum -1.38 m).
Ferrybridge and Upper Aire: 961 leaves at z17 and 284 parents (1,245 nodes, up to 15,376 Esri
tiles); Southend: 289 leaves at z16 and 84 parents (373 nodes, 17 min). Built at 30 Esri
requests/s. `correct` results:

| Area | Cells corrected | Scenes (all lean applied unless noted) |
| --- | --- | --- |
| Ferrybridge | 13 of 36 | WV02 2025-04-29 76 roofs t -0.33 E +1.07 N lean 0.34 toward 108; LG01 2025-07-16 187 roofs t -0.53 E +2.24 N lean 0.40 toward 182; WV02 2022-07-16 347 roofs t -0.06 E +1.09 N lean 0.09 toward 307; LG02 2025-06-30 163 roofs t -1.73 E +2.15 N lean 0.36 toward 131 |
| Upper Aire | 28 of 36 | LG01 2025-03-18 87 roofs t -0.32 E +1.33 N lean 0.44 toward 185; WV02 2023-05-27 97 roofs t -0.46 E +2.13 N lean 0.58 toward 189 |
| Southend | 7 of 49 | GE01 2025-07-12 469 roofs t +0.01 E +2.74 N lean 0.40 toward 195; WV02 2025-04-11 rejected (27 roofs, radius 0.35 above 0.29), keeps the cell shift |

Lean in m per m, azimuth in degrees. All 1,245 Ferrybridge and Upper Aire nodes are lean-corrected;
Southend has 359 lean, 2 ground shift only and 12 uncorrected nodes (bound 2.8 m). The EA WCS 403s
need a resume loop: `uncommitted/e4b/areas.sh` retries `build` and `correct` (up to 6, then 30,
attempts, 120 s apart); each attempt gained 100 to 200 nodes.

## Own visual review of the M1 renders

M-A surfaces give footprint, position and rough height of large grey buildings beside grey
pavement and keep verges flat; they round walls, ridges and crowns, underestimate raised heights,
and lift a red vehicle on the Ferrybridge road into an oversized dome (cars in the photo but not
in the older lidar are real objects: keep or drop is a policy call). The mean of the two models
tempers Geopose's oversized tree domes. Texture streaking on steep sides is the Esri image draped
on new slopes. The views sit on the tallest windows, where these models do best.

## E0 results (masked anomaly surface, held for the owner)

Run 2026-10-30 on the two 540 m boxes (scratch `uncommitted/e4b/e0/`, surfaces
`e0m|e0g|e0h-{site}-guide-x{5,30}.npz` in `scratch-archive/e4/out/`); specification in
`pixtransform-proposal.md`. Not rendered; the owner has not seen it. Scores are secondary.

- Held-out head on the boxes: Ferrybridge box accuracy 0.882, building F1 0.773 (500 building
  tokens); Upper Aire box accuracy 0.954, only 12 building tokens (700 pixels), so its building F1
  of 0.154 means nothing. The head under-predicts vegetation at Upper Aire: 3 % of pixels carry any
  raised mask against 40 % at Ferrybridge, so e0 equals the unmasked surface there.
- The guided filter did not improve agreement with the lidar: Ferrybridge 1 m building F1 0.666
  for plain bilinear, 0.665 at radius 1 to 2, 0.635 at 4, 0.467 at 8, 0.27 at 16. Radius 4 and eps
  0.01 were used (tuned on that one box; registration and lean confound it).
- Masking removes 56 % of the false raised heights in N (lidar-ground pixels with N above 1 m: 39.9
  to 17.5 % at Ferrybridge, 10.0 to 0.06 % at Upper Aire), but the final surface barely changes at
  x5 (ground lift 14.7 to 13.9 %) and rises at x30 (28.7 to 30.2 %); the coarse base and mask
  leakage dominate. The head's vegetation class includes low vegetation: of its predicted
  vegetation pixels at Ferrybridge, 59 % have lidar height under 1 m and 44 % sit on lidar ground.
- RMSE, `avg_ma` to `e0m` (e0g, e0h): Ferrybridge x5 0.869 to 0.838 (0.829, 0.910); Ferrybridge
  x30 2.294 to 1.723 (1.825, 1.764), open-ground RMSE 2.21 to 1.34, edge slope 0.330 to 0.133;
  Upper Aire x5 1.663 to 1.664; Upper Aire x30 2.105 to 2.152 (2.138, 2.152). Buildings and trees
  get slightly worse (Ferrybridge x30 building bias -1.50 to -1.89 for e0m, -2.65 for e0g; tree
  RMSE 2.68 to 2.91). Cell-edge step ratios stay 1.0 to 1.2.
- Per-class gains (e0g, ground-smoothness fit) are not usable: all four fits sit at a grid edge or
  on a flat curve (Ferrybridge x5 building 1.9, vegetation 0.5; x30 both 0.5; Upper Aire x5
  building 0.5, vegetation 1.2; x30 2.8 and 3.0); the lidar-regression oracle gain at Ferrybridge
  is 1.25 to 1.38 for buildings and 0.33 to 1.11 for vegetation. The signal fails at x30 and at
  Upper Aire.
- Footprint extrusion (e0h): Ferrybridge 111 components (median 88 px, max 5,373; 15 under 16 px),
  median building height 5.06 m; best on x30 ground lift (26.4 %) and NMAD, worst at x5 (RMSE
  0.910, building RMSE 1.01 against 0.82); Upper Aire has no components.
- Traps: `seg/work/*-labels.npz` stores a `box` that does not match the area corners, so use
  `AREA_SW`; the lidar ground class has 4 to 7 % of pixels where DSM is over 1 m above DTM, so
  report false lift as well; `compose2.py` took 415 s (x5) and 669 s (x30) against 157 s for all
  16 fields with `OMP_NUM_THREADS=1` (thread oversubscription suspected).

## Traps

- The first depth-model fit regressed the coarse DSM elevation, not height above ground; the scale
  came out negative in 11 of 12 fits. Fit `s - B(dtm)`.
- The trial kriging ran per 270 m tile and shows seams (edge step 12 to 22 times the normal at x30);
  the owner's low opinion of the kriging panels came partly from that.
- CHMv2 on the 0.25 m texture overpredicts canopy (open-ground RMSE 7 m); it was trained near
  0.6 m, so feed it 0.5 m.
- The EA WCS answers a few requests with 403 mid-build; `build` resumes from its saved nodes, so a
  retry loop (`uncommitted/e4b/areas.sh`) finished the 5.4 km builds.
- Southend `correct` failed on a cell with no lidar points (estuary); fixed in `satmesh_eval`.
- Scripts that start worker processes need a `__main__` guard (spawn re-imports the main module).
- The kriging is exactly coherent only up to x10; at x30 the cell residual is up to 1 cm, and a
  540 m box takes about 7 min.
- The majority label biases vegetation: ground returns under canopy outvote vegetation returns,
  so cells under trees label as ground and vegetation recall drops.
- The 1,008 px feature window with stride 504 does not land on the 16 px token grid (31.5 tokens);
  a stride of 31 tokens with a clamped final window fixes it.

## Not checked

- Seams and tiling of RS3DAda windows by eye beyond the review pages.
- Whether CHMv2 and the building models merge cleanly (waits for the segmentation head).
- Anything on a real coarse source (GLO-30) or at Yemen.
