---
status: historical
topic: surface-refinement
summary: E8 survey of lidar surface refinement: cubic resampling, raw-point Delaunay, roofer roofs, PixTransform
answers: How can the 1 m DSM mesh be refined?; Why does bilinear scoring flatter fidelity?; Does guided DSM super-resolution work at x2?; Which methods copy image texture into height?
---

# E8 research: lidar surface refinement

Try four things in order: swap bilinear for an interpolating cubic or PCHIP resampler, triangulate
the raw EA first-return points in place of the gridded DSM, rebuild roofs from footprints with
roofer, and only then fit PixTransform to Esri imagery at x2. No published method was evaluated in
our regime (x2 from a 1 m lidar DSM with an aerial guide that is offset by up to about 1 m). Every
guided-DSM paper found works at x10 from 5 m satellite DSMs.

## Scoring caveat

Any interpolant through the DSM samples (bilinear, Catmull-Rom, PCHIP) has zero error at the
pixel centres, so that score measures fidelity, or nodes missing the centres, and cannot reward
sub-metre detail. Check the 0.5 m nodes sit on the 1 m pixel centres before reading the bilinear
NMAD of 0.54 m as smoothing loss. To credit detail, degrade to 2 m, refine x2 and score at the 1 m
centres (the guided-SR literature's protocol). Real-GDSR warns that models trained on synthetic
degradation do worse on real data.

## Methods

### 1. Image-guided height super-resolution

- Joint bilateral upsampling (Kopf et al., SIGGRAPH 2007; UNOPENED). Its
  known failure is texture copying: image edges with no matching depth edge get imprinted as
  geometry (UNOPENED follow-ups). Shadows and road markings would become relief.
- Guided filter (He et al.) and L0 smoothing (Xu et al., SIGGRAPH Asia 2011, VERIFIED project
  page). Both ship in OpenCV `ximgproc` (docs returned 403, so UNOPENED). L0 output is piecewise
  constant, which recreates terraces. Avoid it.
- Anisotropic TGV guided upsampling (Ferstl et al., ICCV 2013; VERIFIED abstract). Convex,
  primal-dual, with a diffusion tensor taken from the image. TGV favours piecewise-affine output
  and does not staircase (Bredies, Kunisch and Pock, SIAM J. Imaging Sci. 2010; VERIFIED via the
  Graz page). Planar roofs and smooth ground suit it. No official code was found.
- DKN and FDKN (Kim, Ponce and Ham, IJCV; UNOPENED). The repo `jun0kim/DeformableKernelNetwork`
  returned 404, so licence and weights are unknown.
- PixTransform (de Lutio et al., ICCV 2019; VERIFIED). Fits a pixel-wise MLP for each image,
  needs no training data, and was evaluated on depth and tree-height maps. The repo is
  `prs-eth/PixTransform`, MIT licence, PyTorch, integer factor only (x2 works) (VERIFIED). The
  loss forces the downsampled output to match the source. Fit: good, but it trusts the guide, so a
  1 m offset moves edges by a whole source pixel exactly on raised objects.
- DADA (Metzger, Caye Daudt and Schindler, CVPR 2023; VERIFIED). Learned anisotropic diffusion
  plus an adjustment step that keeps the output consistent with the low-resolution source. The
  repo is `prs-eth/Diffusion-Super-Resolution`, MIT licence, weights for Middlebury, NYUv2 and DIML
  (indoor) only (VERIFIED).
  Needs retraining; on real 5 m DSMs it barely beat bicubic (RMSE 5.55 against 5.59 m).
- Real-GDSR (Panangian and Bittner, ISPRS Annals X-2-2024; VERIFIED full text). Inputs: 5 m
  Cartosat DSM, x10, Swiss 0.5 m lidar, 2000 training patches, Titan RTX. RMSE / NMAD: 3.54 /
  2.65 m, against 5.59 / 3.62 m for bicubic. The paper measures height error. No code was found.
- Elevate (Nicolicioiu et al., arXiv 2609.11886, Sep 2026; VERIFIED HTML). Fine-tunes Stable
  Diffusion to go from 5 m to 0.5 m, trained on Swiss lidar. Winterthur RMSE / NMAD: 2.56 / 1.31 m,
  against 5.33 / 5.31 m for bicubic and 3.13 / 2.07 m for Real-GDSR. The authors say 5 m is too
  coarse to reach 0.5 m "without hallucinating details". Tails are longest at vegetation and
  building boundaries. Out of distribution (Dortmund), it lost to Real-GDSR. No code or weights.

### 2. Single-input DEM super-resolution

- D-SRGAN (Demiray et al., 2021; UNOPENED). Its MSE of 0.861 m² against 0.946 m² for bicubic is
  about a 10 % gain.
- No paper found measures hallucination on lidar DSMs; without an image, detail comes only from
  priors. Low fit.

### 3. Edge-preserving reconstruction

- TV regularisation staircases. TGV does not (sources in section 1).
- Bilateral normal filtering (Zheng et al., TVCG 2011; UNOPENED) keeps creases. No library
  implementation was found.
- Breaklines: lidar roof outlines as DSM interpolation breaklines (Widyaningrum et al., ISPRS
  Archives 2018; UNOPENED); about 92 % of lines met accuracy requirements.

### 4. Roofs and crowns

- Raw points: the EA point cloud is OGL, LAZ, and classified only as ground and surface objects
  (VERIFIED in f6-research.md). The sampled tile held 1,218,591 points per km², about 1.2 pts/m².
- A Delaunay TIN of first returns puts edges at their true XY positions instead of snapping them
  to 1 m cells. Tools: lidR `dsmtin` and `pitfree`, and PDAL `filters.delaunay` with
  `filters.faceraster`.
- Pit-free CHM (Khosravipour et al., PE&RS 2014; VERIFIED in the lidR docs) removes crown pits.
  Spike-free (Khosravipour et al., 2016; adaptive: Fischer et al., 2024; VERIFIED
  in the lidR docs) is documented as unsuitable when point spacing exceeds 0.7 m. Ours is about
  0.9 m.
- roofer (3DBAG/3DGI; VERIFIED). GPLv3. Builds LoD1.2 to LoD2.2 from a point cloud plus footprint
  polygons. CLI plus C++ and Python bindings, no tagged release. Footprints: Microsoft
  GlobalMLBuildingFootprints is CDLA-Permissive-2.0 with Europe precision / recall of 94.3 / 85.9 %,
  and UK coverage implied but not stated (VERIFIED). OS Open Map Local is an alternative (UNOPENED).
- Crown segmentation: Dalponte and Coomes 2016 and Silva 2016 in lidR, and PyCrown (GPLv3,
  archived 2020; UNOPENED). These give segments, not a surface. No established method
  for meshing crowns from them was found.

### 5. Monocular height (E7)

- IM2HEIGHT (Mou and Zhu, 2018) and HTC-DC Net (arXiv 2309.16486; VERIFIED abstract, no code).
  RMSE on DFC19 at 1.3 m GSD is about 2.1 (UNOPENED table, units unstated).
- Meta/WRI canopy height (Tolan et al., RSE 2024; UNOPENED). MAE about 2.8 m.
- Errors exceed the lidar's, so these are detail sources at best, never height sources.

### 6. Resampling baselines

- Cubic convolution (Keys, IEEE TASSP 1981; UNOPENED abstract). Catmull-Rom is a = −0.5. It is C¹
  and passes through the samples, but cubic kernels overshoot at steps, which would put halos at
  walls.
- SciPy 1.18 `RegularGridInterpolator` offers `cubic`, `quintic` and `pchip` (VERIFIED). PCHIP is
  monotone along each axis (Fritsch and Carlson 1980; UNOPENED), so it limits overshoot at walls.

## Shortlist

| # | Method | Measure | Risk |
|---|--------|---------|------|
| 1 | Catmull-Rom and tensor PCHIP via SciPy, with nodes checked to sit on pixel centres | All four scores. Also check wall overshoot (PCHIP should show none) | Still rounds crowns. Cubic may halo walls |
| 2 | First-return TIN from EA LAZ (PDAL Delaunay plus faceraster, or lidR `pitfree`), sampled at 0.5 m nodes | Raised NMAD and p95, camera recall, aspect excess (should fall because edges leave the grid) | Survey date differs from the 2022 composite and Esri. Tile download endpoint unverified. Only about 1.2 pts/m² |
| 3 | roofer LoD2.2 from LAZ and footprints, merged into the surface for buildings only | Raised p95 on buildings, recall on walls, open-ground smoothness at seams | GPLv3 (run it as a separate process). Footprint and lidar dates differ. Seams at the merge |
| 4 | PixTransform x2 per tile, Esri guide, after local registration; DADA retrained only if it helps | Synthetic 2 m to 1 m protocol, then all four scores | Edge leakage and texture copying from the 1 m misregistration on raised objects |
