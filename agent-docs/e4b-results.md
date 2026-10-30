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
