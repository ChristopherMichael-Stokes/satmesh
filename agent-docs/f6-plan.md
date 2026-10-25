# Plan: F6 evaluation harness

Owner approved forks 1 to 5 on 2026-10-25 (fork 5 as F7, required before v1 release) and chose
Upper Aire and Lower Aire for fork 6. Evidence: `f6-research.md` (sources tagged VERIFIED,
UNOPENED or UNVERIFIED there), `s6-results.md`, `f5a-results.md`.

## Purpose

Give every later change (E1 to E7, texture harmonisation, the Esri-to-EA offset correction) a score,
and answer the two open risks in `status.md`: how far the drape sits from the ground, and whether a
camera sees in the render what it would see in reality.

## What each check can and cannot say

- The mesh is built from the EA first-return DSM, so scoring it against the same DSM checks the
  pipeline (OSTN15 and OSGM15 chain, UVs, TIN error, tile seams), not the lidar's own accuracy.
  Source accuracy needs an independent reference (the raw point cloud) and is out of reach until
  that is downloadable.
- Where enhancement matters (E1, E4) the harness degrades the DSM (for example to 30 m or 50 m) and
  scores recovery against the 1 m original, which is independent by construction.
- No standard defines an object-level "visible in reality" metric (`f6-research.md`, Q4); that
  check is new design, so it is a fork below.

## Components

| # | Check | Method (source) | Library | Output |
| --- | --- | --- | --- | --- |
| A | Pipeline height check | GLB vertices to ECEF to BNG and ODN through pyproj directly, compared with the FZ_DSM raster at the same points; DTM ground grid against the DTM raster | pyproj, rasterio | Max and NMAD error per node, expected under `max_error_m` plus float32 resolution |
| B | Height score for any height field | Median, NMAD, 68.3 % and 95 % quantiles of the absolute error, block-bootstrap CI (Höhle and Höhle 2009, verified); binned by slope and by an nDSM object mask (nDSM = DSM minus DTM, threshold a tunable); RMSE reported for comparison only | xdem 0.2.3 (`nmad`, `nd_binning`, slope) | Table per stratum; reusable by E1 and E4 |
| C | Esri-to-EA offset | Both images to one luminance grid; window grid of `skimage.registration.phase_cross_correlation` with subpixel upsampling; median and NMAD of the shifts, block bootstrap CI; shift map; validated first on a known synthetic shift of the same image | scikit-image 0.26; AROSICS 1.13.2 (`COREG_LOCAL`) only if the shift map has structure | E and N shift in metres per site, map, CI |
| D | Relief dependence | Shift within nDSM-masked tall objects against open ground: a conventional orthophoto leans raised features, a true orthophoto does not. Answers "is Esri true-ortho" | as C | Open-ground shift against tall-object shift |
| E | End-to-end drape | Orthographic top render of the store against the EA aerial, offset by C | trimesh or Open3D | Residual shift after the render path |
| F | Texture detail | Radial power spectrum of luminance in stable, masked regions (the S6 method), each normalised by its own 4 to 20 m band; edge-based MTF only if the spectrum is ambiguous. Both are practice, not a published protocol | numpy, scikit-image | Esri-to-EA power ratio by band |
| G | Consistency | Downsample the enhanced texture with area averaging to the input grid and diff against the input (L1, spectral angle, residual shift) | OpenCV `INTER_AREA` or scikit-image | One number per tile; gate for E3 and E5 |
| H | Camera visibility | See below | Open3D `RaycastingScene` or trimesh with Embree | Recall and precision of visible surface |

PSNR and SSIM are not used for texture: they reward blur and punish misalignment and date change
(`f6-research.md`, Q3).

## Camera visibility (H)

Reference "reality": rays from each camera against the FZ_DSM triangulated at full 1 m resolution.
Tested: the render of the store, via depth from the same camera, against that reference.

1. Depth difference: for random cameras (ground height 1.7 m, drone oblique, fixed intrinsics in the
   case file), per-pixel depth from the store mesh against depth from the reference. Report the
   fraction of reference-visible pixels whose depth agrees within a tolerance (tunable), and the
   fraction of render pixels the reference says are occluded.
2. Object recall: objects are connected components of nDSM above the threshold (buildings, tree
   groups, walls), so no new data source is needed. An object is visible in reference if rays to
   its sample points are unoccluded; it counts as present in the render if depth at its projected
   pixel agrees within the tolerance. Recall and precision per object class by height.
3. Fisher's finding that viewsheds shrink under DEM error: report visibility as a fraction over
   Monte Carlo draws of the DSM error from B, not a single boolean, once B has the error model.

What it will catch: datum, scale or georeference errors (a wrong ellipsoid or ODN offset moves
everything), cracks and skirt leaks, coarse parents that lose small objects (parents sample at 2 m
per level), and LOD popping. It will not catch what the DSM cannot hold (facades, space under
canopy); the point cloud would, see fork 3.

## Sites

| Site | Why | EA aerial |
| --- | --- | --- |
| Upper Aire (BNG about 398350 448350) | Moorland, hedges, tree belts; caches and the S6 numbers exist | RGBN 2020, 0.1 m; Esri Vivid 2025-03 |
| Lower Aire block, at Ferrybridge (BNG 448000 424000, 1 km) | River, bridge, factory roofs and housing, so buildings test D and H. The first Lower Aire box was under flood in the 2020 survey | RGBN 2020, 0.1 m; Esri z19 |

Severn shore (four 0.1 m captures, 2016 to 2021) joins when E6 needs multiple dates. No standard
fixes the number of sites for C (`f6-research.md`, Q2): the plan uses hundreds of windows per site
and states the CI, and says plainly that two sites are indicative, not representative.

## Data work F6 forces

- EA aerial slice of F2b: index search (WFS, verified in S6), tile download with a streaming cap,
  `funzip` of one ECW, conversion to GeoTIFF in the `gdal-ecw` container (`make gdal-ecw-image`,
  552 MB, about 3 min). One 1 km ECW is about 17 MB. Eval only; the source registry stays F2a.
- The FZ_DSM and DTM rasters are already cached per node.

## Checkpoints

1. Package `satmesh-eval`; A and B with tests against a synthetic height field whose statistics are
   worked out from the definitions. Both `xdem` and trimesh with embreex install on Python 3.13;
   Open3D has no wheel for this platform (done, `f6-results.md`).
2. EA aerial slice and C on the synthetic shift, then on Upper Aire: the first defensible offset
   number and shift map. Record in `f6-results.md`.
3. D and E on both sites.
4. H, depth difference first, then object recall.
5. F and G, a `satmesh eval` command or Make targets, docs.

Each checkpoint ends with `status.md` and `f6-results.md` updated and `make check` green. Tiny-slice
run of the whole path (one node, one window grid) before any full-site run.

## Decisions for you

| # | Fork | Recommendation | Alternative |
| --- | --- | --- | --- |
| 1 | New package and dependencies | `satmesh-eval` in the `pipeline` workspace; add xdem and scikit-image, plus Open3D or trimesh+Embree (chosen at checkpoint 1 by what installs). NMAD is one line, but slope binning and bootstrap tools justify xdem | numpy/scipy only: hand-rolled slope and binning |
| 2 | Visibility metric | Do both: depth difference (standard render-versus-reference) and the object recall defined above, which is new design with tunable thresholds | Depth difference only, no object-level claim |
| 3 | Raw point cloud (independent height truth, tree and building heights) | One-session spike: find the tile download endpoint (inspect the portal's network calls with Playwright, or read the QGIS "LIDAR Downloader UK" plugin source), fetch one tile, run `lasinfo` for classes and returns. EA documents only "ground" and "surface objects"; a building and vegetation split is unconfirmed. Decide after the spike | Skip: F6 then scores only pipeline consistency and enhancement recovery, not lidar accuracy |
| 4 | opensr-test (synthesis and hallucination split) | Defer to E3: it needs torch, CLIP and a super-resolution output to score, and its constants are the authors' tunables; G covers consistency now. Revisit with an `ml/` workspace | Add now: heavy dependencies, nothing to score |
| 5 | Real-photo localisation test (MeshLoc-style) | Out of scope: needs photographs with ground-truth poses we do not have | Add later if the owner has such data |
| 6 | Sites | Upper Aire and Lower Aire | Add Severn shore now |

Tunables to be called out when built: nDSM threshold, tolerance for depth agreement, window size and
upsample factor, camera sets, Monte Carlo draws.

## Not planned here

Offset correction (E2), Gazebo (F5b), any model.
