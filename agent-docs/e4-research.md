# E4 research: fine height detail from coarse elevation data

Survey by a research subagent, 2026-10-26. VERIFIED means the page or paper text was opened;
UNOPENED means a search snippet only.

## Conclusions

- No published evaluation matches our regime: a 5 to 30 m DEM refined to about 1 m over UK or
  temperate terrain, with buildings and trees, using an aerial guide. The closest are Swiss urban
  5 m to 0.5 m DSM work (Real-GDSR, Elevate: urban only, supervised, GPU, no code), JSPSR (GLO-30 to
  a 3 m bare-earth DTM, not a DSM) and Prior2DSM (hole filling, not coarse to fine).
- Recovering building and tree relief at about x30 is not established anywhere. PixTransform's
  authors call x32 results "not satisfactory for all images"; the best real-data x10 urban results
  still have 2.6 to 3.5 m RMSE. Expect real gains at 2 m to 1 m and 5 m to 1 m; at 30 m, mostly
  plausible texture, not recovered truth.
- Domain gap: models trained on block-averaged lidar do not carry over to real coarse sources
  (radar DSM for GLO-30, a DTM for OS Terrain 50, 2 m lidar). Scores on degraded EA data are an
  upper bound.
- Texture copying (guide texture turned into relief where no height edge exists) is the documented
  failure of every guided method.
- Recommended first trial: PixTransform per tile, against bilinear, guided-filter and
  area-to-point kriging baselines, at x2 and x5 on degraded EA DSM.

## Comparison

| Method | Scales shown | Data needed | CPU? | Licence | Code | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| Joint bilateral upsampling (Kopf 2007) | general | none | yes | in OpenCV ximgproc | opencv_contrib | Abstract VERIFIED |
| Guided filter (He 2013) | x4 to x16 | none | yes, linear time | in OpenCV ximgproc | same | Survey numbers VERIFIED; paper UNOPENED |
| Anisotropic TGV (Ferstl 2013) | Middlebury | none | yes, iterative | not found | not found | Abstract VERIFIED |
| PixTransform (de Lutio 2019) | x4 to x32 | none, per image | possible, unmeasured; 120 s per x8 image on GPU | MIT | prs-eth/PixTransform (85 stars, last commit 2022-04-06) | VERIFIED |
| DADA (Metzger 2023) | x4 to x32 | supervised | GPU trained | MIT | prs-eth/Diffusion-Super-Resolution (122 stars, 2024-12-24) | Abstract and repo VERIFIED |
| DKN / FDKN (Kim 2020) | x4 to x16 | supervised | GPU trained | GPL-3.0 | cvlab-yonsei/dkn (79 stars, 2020-07) | Repo VERIFIED |
| Real-GDSR (Panangian, Bittner 2024) | x10, real 5 m to 0.5 m | supervised, about 2k patches | GPU | none found | none found | VERIFIED |
| Elevate (Nicolicioiu 2026) | x10, real | supervised, Stable Diffusion fine-tune | GPU only | none found | none found | VERIFIED |
| JSPSR (Cai, Wilson 2025) | 30 m to 3 m and 8 m DTM | supervised, DFC30 | not stated | dataset CC BY 4.0 | none found | Partly VERIFIED; paper 403 |
| Argudo 2018 | "up to one order of magnitude" | supervised | unknown | unknown | none found | UNOPENED |
| Depth Anything V2 Small | monocular | pretrained | yes, slow | Apache-2.0 (Small only) | DepthAnything/Depth-Anything-V2 (9,032 stars, 2026-03) | Repo VERIFIED |
| Prompt Depth Anything (2025) | low-res lidar prompt to 4K | pretrained, indoor | unknown | Apache-2.0 code; weights unstated | DepthAnything/PromptDA | Repo VERIFIED |
| Marigold / Marigold-DC | monocular, completion | pretrained, zero-shot | GPU in practice | Apache-2.0 | prs-eth/Marigold | Abstracts VERIFIED |
| Prior2DSM (Rafaeli 2026) | hole filling | test-time adaptation | GPU, 8.2 min/km2 | none found | none found | VERIFIED |
| HighResCanopyHeight (Meta 2024) | canopy height from RGB | pretrained, US aerial lidar | yes; compressed models CPU-only | Apache-2.0 | facebookresearch/HighResCanopyHeight | Repo VERIFIED |
| Area-to-point kriging (Kyriakidis 2004) | any | variogram fit | yes | method | none checked | Abstract VERIFIED |
| ANUDEM / Topo to Raster | vector to raster | contours, streams | yes | proprietary | none | Docs VERIFIED |
| Fractal synthesis (Fournier 1982) | any | none | yes | method | none | UNOPENED |
| Unguided DEM SR (TfaSR, DuffNet) | DEM only | supervised | GPU | GPL-3.0 (DuffNet) | Geo-Tell/DuffNet (code incomplete) | Repo VERIFIED |

## Notes

### Classical guided upsampling

- NYU v2 RMSE in cm at x4 / x8 / x16 (Zhong et al., ACM Computing Surveys 2023,
  arxiv.org/abs/2302.09598, VERIFIED): bicubic 4.27 / 7.17 / 11.37; guided filter 5.05 / 6.97 /
  11.13; DKN 1.62 / 3.26 / 6.51; JIIF 1.37 / 2.76 / 5.27. The guided filter is barely better than
  bicubic; filtering methods copy texture.
- Anisotropic TGV: convex, image-derived diffusion tensor, primal-dual solver (Ferstl et al.,
  ICCV 2013, VERIFIED abstract). No maintained code found.
- PixTransform fits a small network per image from guide pixels to height, constrained to
  reproduce each source cell after downsampling; no training data; integer scale only. Swiss forest
  canopy height (40 maps, 10 m target, Sentinel-2 guide), MSE in m2:

  | Factor | Bicubic | Guided filter | PixTransform |
  | --- | --- | --- | --- |
  | x8 | 18.1 | 19.0 | 17.6 |
  | x16 | 29.1 | 27.7 | 19.7 |
  | x32 | 41.5 | 40.2 | 21.2 |

  32k iterations, about 120 s per x8 image on a GTX 1080 Ti. Reported failures: spurious depth
  patterns where similar colours sit at different depths, texture transfer at x32. de Lutio et al.,
  ICCV 2019, arxiv.org/abs/1904.01501, VERIFIED.

### Learned guided super-resolution

- DADA: guided anisotropic diffusion plus a CNN and an adjustment step keeping the output
  consistent with the source; largest gains at x32; checkpoints trained on indoor benchmarks
  (Metzger et al., CVPR 2023, arxiv.org/abs/2211.11592, VERIFIED).
- Real-GDSR: real Cartosat-1 5 m DSM to swisstopo 0.5 m lidar DSM, 0.5 m RGB guide, Zurich and
  Bern built-up only. RMSE: bicubic 5.59 m, DADA 5.55 m, Real-GDSR 3.54 m; the diffusion stage
  raises NMAD (arxiv.org/abs/2404.03930, VERIFIED).
- Elevate: same task, Stable Diffusion fine-tuned on about 10k patches. Winterthur RMSE: bicubic
  5.33 m, Real-GDSR 3.13 m, Elevate 2.56 to 2.64 m. Munich: 6.44 / 3.74 / 3.24 m. Dortmund:
  5.70 / 4.60 / 4.73 m (no better than Real-GDSR). Larger errors at vegetation and building edges;
  GPU only (arXiv 2609.11886, VERIFIED).
- JSPSR: GLO-30 DSM to a 3 m or 8 m bare-earth DTM. A FOSS4G 2026 talk reports over 70 % RMSE
  reduction and about 1.1 m open-terrain RMSE (VERIFIED); the paper (Remote Sensing 17:3591, 2025)
  returned 403, so its tables are UNOPENED. Dataset: zenodo.org/records/17478574 (CC BY 4.0).

### Monocular height from imagery

- Prior2DSM: Depth Anything V2 relative depth plus DINOv3 features; test-time LoRA and an MLP fit
  scale and shift to metric height. NAIP 0.3 m (Denver) and WorldView-3 0.6 m (Fresno) with 25 to
  75 % of a lidar DSM removed. Denver RMSE 5.3 to 6.7 m against 8.4 to 9.8 m for bilinear. Coarse
  priors untested (arXiv 2604.02009, VERIFIED).
- Rafaeli et al.: SRTM 30 m plus NAIP refined to 0.3 m, MAE below 5 m against lidar, at most 18 %
  better than SRTM (arXiv 2507.09681, abstract VERIFIED).
- Depth2Elevation (IEEE TGRS 2025): up to 42 % relative improvement on GAMUS; no code found.
- HighResCanopyHeight: aerial test-set MAE 2.5 m (aerial model), 3.15 m (satellite model); trees
  only.
- Nadir imagery makes models lean on shadows; a snippet reports over 30 % error under changing
  illumination (UNOPENED).

### Geostatistical and terrain-specific

- Area-to-point kriging gives mass-preserving predictions (the average over each coarse cell
  reproduces it) and a per-point standard error; adds no detail beyond the variogram. Useful as a
  base layer and as the consistency constraint any detail layer must meet.
- ANUDEM / Topo to Raster: thin-plate spline with drainage enforcement for contour, point and
  stream inputs; the docs do not describe densifying a gridded DEM. Possibly relevant to OS Terrain
  50, which is contour-derived (not verified).
- Fractal synthesis adds plausible roughness, not true relief; no evaluation against lidar found.
- Unguided DEM SR (TfaSR, DuffNet) cannot recover buildings.

The closed work (bilinear, Catmull-Rom, PCHIP, raw-point Delaunay, roof planes) is interpolation
within the source band; it is the "bicubic" row that the papers above beat only at x8 and higher.

## Ranked shortlist

| Rank | Candidate | Expected gain | Risk | CPU |
| --- | --- | --- | --- | --- |
| 1 | PixTransform per tile | Modest at x2; meaningful at x5 to x8 on tree and building edges, by analogy with canopy MSE 29.1 to 19.7 at x16 | Texture copying; imagery offset puts edges in the wrong place; runtime unmeasured | Feasible, unmeasured |
| 2 | Guided filter or JBU (OpenCV) | Small, about bicubic | Halos, texture copying | Yes, fast |
| 3 | Area-to-point kriging base, optionally plus fBm detail | Little at x2; smoother and more correct at x30 | No buildings; fBm detail is fake | Yes |
| 4 | Depth Anything V2 Small or HighResCanopyHeight as a detail layer, fitted to the coarse DEM by per-window scale and shift | Unknown here; published coarse-prior result is MAE below 5 m at 30 m to 0.3 m | Shadow dependence, leaning objects; Base and Large weights non-commercial | Small model yes, slow |
| 5 | Small guided network (DADA, MIT) trained on EA DSM plus Esri pairs | Highest ceiling (about 40 to 50 % RMSE cut at x10 in Real-GDSR and Elevate) | Domain gap to real GLO-30 and OS Terrain 50; GPU training | Inference maybe |

First trial: PixTransform. It is the only candidate that is in-regime without training,
permissively licensed and consistent with the source by construction, and it tests directly whether
the Esri guide carries height information. If it fails the edge-leakage check, candidates 4 and 5
inherit the problem.

## Scoring protocol

1. Degrade: block-average the 1 m EA DSM by x2, x5 and x30.
2. Refine each to 1 m with Esri imagery resampled onto the same grid.
3. Compare every 1 m pixel with the original: RMSE, MedAE, NMAD.
4. Baselines: bilinear (the current mesh choice) and guided filter.
5. Split by slope class from the original DTM and by cover: nDSM above 2 m with a green index
   high is trees, above 2 m otherwise buildings, the rest open ground.
6. Edge leakage: Canny on the guide; keep guide-edge pixels where the original DSM gradient is
   below a small threshold; report mean |grad h| of the refined output there against the original
   and bilinear.
7. Offset sensitivity: repeat with the guide shifted 0, 1 and 3 m.
8. Render the results for the owner to judge by eye; scores did not predict the owner's ranking in
   the lidar surface refinement trials.

## Open questions

- CPU runtime of PixTransform on one 256 x 256 tile at 1 m; needs a one-tile timing.
- JSPSR numbers and code.
- Any model trained on UK lidar plus aerial imagery: none found.
- Whether to correct the guide's position and mask shadows before guiding.
- Whether 2 m lidar coverage of Wales and Scotland makes the x30 case a niche; not verified.
