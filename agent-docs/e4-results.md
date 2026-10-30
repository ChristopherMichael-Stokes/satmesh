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

## Traps

- PixTransform at x30 runs 12,945 epochs of 3 tiny batches per tile; per-epoch Python overhead
  dominates, and two processes on one GPU halve each one's speed there.
- PixTransform has no nodata mask and does not enforce consistency; its `utils.utils` imports the
  removed `scipy.misc`, so only `pix_transform/` is vendored.
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
