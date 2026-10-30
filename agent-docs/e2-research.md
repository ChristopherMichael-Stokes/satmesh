---
status: historical
topic: position-correction
summary: Desk research on correcting the Esri-to-ground offset; recommends a per-polygon shift model and lidar reference (design B) over AROSICS-style grids
answers: How do I register Esri basemap imagery to a ground reference; What does AROSICS or COSI-Corr offer and what are its limits; How is building lean modelled for satellite imagery; Can UV offsets apply a shift without resampling; Which candidate correction designs exist
---

# E2 research: correcting the Esri-to-ground offset

Desk research, no experiments on project data. `[verified]` means checked against the source named
(paper abstract or full text, package source, PyPI JSON, live service). `[unverified]` means a
search snippet or memory that was not opened. Dates are as of 2026-10-26.

## Answer

- Every survey site is Vantor (Maxar) Vivid satellite imagery, not aerial: one source polygon per
  site, sensors WV02, GE01, LG01 and LG02, captured 2023-05 to 2025-07 `[verified, live identify]`.
  A satellite strip is close to a parallel (affine) projection over a few km, so within one source
  polygon the error should be a near-constant shift plus a building lean that is one direction and
  one metres-per-metre-of-height factor for the whole polygon. That gives a small, physically
  grounded model instead of a free shift field.
- The established tool for a local shift field is the AROSICS / COSI-Corr family (moving-window
  phase correlation, quality filtering, interpolated tie-point grid). satmesh's `eval offset`
  already is this method. AROSICS itself needs the GDAL Python bindings (hard `from osgeo import
  gdal`), so it runs only in a conda-forge env or a GDAL container, not in the `pipeline/` venv.
- Where no EA aerial exists, the best-evidenced reference is EA lidar intensity plus DSM, matched
  by mutual information (Parmehr et al.). Vector references are weaker in GB: OS MasterMap is
  accurate (0.5 m RMSE urban) but licensed; OSM buildings are mostly traced from the same imagery.
- A shift field can be applied without resampling by moving mesh UVs: per-vertex UV offsets with
  barycentric interpolation inside a triangle are exactly the piecewise-linear (Delaunay
  rubber-sheet) warp of the conflation literature. Lean correction is the same operation with the
  offset scaled by height above ground (differential rectification with an affine camera).

## 1. Co-registration methods

| Method | Varying shift | Outlier rejection | Applied how | Source |
| --- | --- | --- | --- | --- |
| AROSICS local (COREG_LOCAL) | Yes, tie-point grid | Reliability, SSIM gain, RANSAC | GCPs to GDAL warp (resamples); grid exportable | Scheffler 2017 |
| COSI-Corr | Yes, dense per-pixel | Signal-to-noise mask, iterative | Displacement maps; ortho resamples | Leprince 2007 |
| Tie points + TPS / piecewise affine / polynomial | Yes (TPS, piecewise), global (polynomial) | Needs a separate step (RANSAC) | Any warp; piecewise linear maps to mesh UVs | Bookstein 1989; Zitova 2003 |
| Optical flow (GeFolki, DIS, TV-L1) | Yes, dense | Implicit (regularisation) only | Dense field | Brigot 2016; Kroeger 2016 |
| Learned matchers (LoFTR, LightGlue, RoMa) | Yes, as sparse/dense matches | Confidence plus RANSAC/MAGSAC | Matches feed TPS or grid | Sun 2021; Lindenberger 2023; Edstedt 2024 |

Evidence:

- AROSICS: phase correlation in moving windows, dense shift-vector grid filtered by validation
  metrics; "root mean square error fits around 0.3 pixels and better" on two inter- and two
  intra-sensor cases, tested on over 9000 satellite images. Scheffler et al., Remote Sensing 9(7)
  676, 2017, <https://doi.org/10.3390/rs9070676> `[verified, abstract]`. Source 1.13.2: filters are
  level 1 reliability (default 60 %), level 2 SSIM improvement, level 3 RANSAC (default up to 10 %
  outliers); `Tie_Point_Grid_Interpolator` offers RBF, GPR ("equivalent to Simple Kriging") and
  ordinary kriging via pykrige; correction passes the GCP list to a GDAL warp, so it resamples
  `[verified, sdist source]`.
- COSI-Corr: iterative unbiased phase-plane estimation in the Fourier domain; raw images
  coregistered "with a 1/50 pixel accuracy" (SPOT null test). Leprince et al., IEEE TGRS 45(6)
  1529-1558, 2007, <https://doi.org/10.1109/TGRS.2006.888937> `[verified, abstract via OpenAlex]`.
  Open Python port Geospatial-COSICorr3D (Aati et al., RSE 277 113038, 2022), installed by conda
  or Docker only, no PyPI release, <https://github.com/SaifAati/Geospatial-COSICorr3D>
  `[verified, README]`. Built for deformation from raw pushbroom scenes with RPCs, which Esri tiles
  do not have.
- Warps from control points: TPS, Bookstein, IEEE PAMI 11(6) 1989,
  <https://doi.org/10.1109/34.24792> `[verified, title]`. Survey of global/local mapping functions:
  Zitova and Flusser, Image and Vision Computing 21(11) 2003,
  <https://doi.org/10.1016/s0262-8856(03)00137-9> `[verified, title]`. A comparison of polynomial,
  piecewise linear (finite element) and multiquadric warps notes polynomials are "unconstrained
  between points" and piecewise linear gives "a faceted irregular warp" when distortion is strongly
  nonlinear ("Image registration using multiquadric functions, the finite element method, bivariate
  mapping polynomials and thin plate spline", report 96-1, 1996, eScholarship) `[verified,
  abstract via OpenAlex; URL not resolved]`. RANSAC: Fischler and Bolles 1981,
  <https://doi.org/10.1016/b978-0-08-051581-6.50070-2> `[verified, title]`.
- GeFolki: multiscale Lucas-Kanade with rank and rolling-guidance filtering, dense nonparametric
  registration of radar, lidar and optical images; accuracy shown with task-specific metrics,
  no single figure in the abstract. Brigot et al., IEEE JSTARS 9(7) 2016,
  <https://doi.org/10.1109/jstars.2016.2578362> `[verified, abstract]`. DIS flow: Kroeger et al.,
  ECCV 2016, <https://doi.org/10.1007/978-3-319-46493-0_29> `[verified, title]`.
- Learned matchers: LoFTR (CVPR 2021, <https://doi.org/10.1109/cvpr46437.2021.00881>), LightGlue
  (ICCV 2023, <https://doi.org/10.1109/iccv51070.2023.01616>), RoMa (CVPR 2024,
  <https://doi.org/10.1109/cvpr52733.2024.01871>) `[verified, abstracts]`. Remote sensing evidence
  is thin: one IGARSS 2024 comparison on high-resolution satellite stereo (SIFT, SuperPoint +
  SuperGlue, SuperPoint + LightGlue, LoFTR) found SuperPoint + LightGlue best overall,
  <https://doi.org/10.1109/igarss53475.2024.10641727> `[verified, abstract; no numbers]`. No
  benchmark found for satellite-basemap against aerial-orthophoto at sub-metre accuracy. Their
  matches are pixel-level and need refinement (phase correlation) for 0.1 m work `[judgement]`.

Fit: our offsets are 0.2 to 2.8 m against 0.25 m pixels (1 to 11 px), smooth at metre scale and
broken by relief. Window phase correlation already resolves this; learned matchers add value only
where appearance differs strongly (leaf-on/off, flood), which is where `eval offset` loses windows.

## 2. How basemap offsets are reported

- Esri World Imagery metadata layers 5 to 18 carry `SRC_DATE`, `SRC_RES`, `SRC_ACC`, `SAMP_RES`,
  `SRC_DESC`, `MinMapLevel`, `MaxMapLevel`, `NICE_NAME`, `DrawOrder`, `SRC_DATE2`, `NICE_DESC`,
  `BlockName`, `ReleaseName` `[verified, MapServer/9?f=json]`. `identify` on layer 0 returns them
  with aliases (`ACCURACY (M)`, `RESOLUTION (M)`, `DESCRIPTION` = sensor, `SOURCE_INFO`, `SOURCE`)
  and the source polygon `[verified]`.
- At approximate town centres of the survey sites (not the exact boxes):

| Site | Date | Res m | ACCURACY m | Sensor | Product | Block |
| --- | --- | --- | --- | --- | --- | --- |
| Upper Aire | 2025-03-18 | 0.34 | 8.47 | LG01 | Vivid | DYNAMIC_ESRI_50_GB01_25Q4 |
| Ferrybridge | 2025-07-16 | 0.34 | 8.47 | LG01 | Vivid Advanced | DYNAMIC_ESRI_Leeds_25Q3 |
| Southend | 2025-07-12 | 0.46 | 8.47 | GE01 | Vivid Advanced | DYNAMIC_ESRI_London_GB_25Q3 |
| Snettisham | 2023-06-10 | 0.50 | 8.47 | WV02 | Vivid | DYNAMIC_ESRI_50_GB01_25Q4 |
| Loughborough | 2024-11-26 | 0.50 | 8.47 | WV02 | Vivid Advanced | DYNAMIC_ESRI_Leicester_25Q3 |
| Neston | 2025-06-26 | 0.46 | 8.47 | GE01 | Vivid Advanced | DYNAMIC_ESRI_Liverpool_25Q3 |
| Belford | 2023-05-11 | 0.46 | 8.47 | GE01 | Vivid | DYNAMIC_ESRI_50_GB01_25Q4 |
| Dunster | 2025-07-13 | 0.34 | 8.47 | LG02 | Vivid | DYNAMIC_ESRI_50_GB01_25Q4 |

- `ACCURACY` is 8.47 m everywhere: a product-level figure, not a per-scene measurement, and it
  says nothing about the 0.2 to 2.8 m we measure. Its definition (CE90?) is not documented in a page
  we could open; an Esri June 2019 blog reportedly said Vivid's stated accuracy changed to 4 m CE90
  from 10 m CE90 `[unverified, search snippet; esri.com returned 403]`.
- Maxar developer docs give Vivid Mosaic 15 cm and 30 cm as "5m CE90 accuracy",
  <https://developers.maxar.com/docs/streaming-basemap/guides/basemap-api-guide> `[verified]`.
  Our 0.2 to 2.8 m is well inside that.
- Esri does not expose sensor azimuth, elevation or off-nadir angle `[verified, field list]`.
  Whether Vivid is orthorectified on a DTM (lean kept) or a DSM is not published in anything found
  `[unverified]`.
- Offsets varying by scene: RPC errors of a satellite scene are mostly a bias that "two additional
  parameters in image space that effect a translation" remove, giving sub-metre geopositioning
  with one or more GCPs. Fraser and Hanley, PE&RS 69(1) 2003,
  <https://doi.org/10.14358/pers.69.1.53> `[verified, abstract]`. A mosaic of scenes therefore
  carries one bias per scene: shift is piecewise constant over source polygons `[inference]`.
- OpenStreetMap keeps a crowd-sourced Imagery Offset Database (per imagery layer, per place, with
  calibration geometries), <https://wiki.openstreetmap.org/wiki/Imagery_Offset_Database>
  `[verified, search summary of the wiki; current status not checked]`. Confirms practice: offsets
  are local and per layer.

## 3. Correcting without reference imagery

| Reference | Established method | Evidence of accuracy | Fit |
| --- | --- | --- | --- |
| Lidar intensity + DSM | Mutual information, template grid, affine or EOP model | Template success: DSM 50 %, intensity 90 %, combined 98 % (aerial 20 cm); no RMSE given | Good: EA LAZ carries intensity |
| Lidar DSM edges / linear features | Line correspondence in bundle adjustment | Method paper; no figure in abstract | Fair, urban only |
| Road / building vectors | Conflation: control points, filtering, Delaunay rubber-sheeting | Reported qualitatively | Weak in GB, see below |
| Learned map-to-image alignment | Multi-scale CNN displacement field | Not opened | Weak, needs training data |
| Interpolate measured shifts | RBF / GPR / kriging of tie-point grid | No published accuracy for basemaps | Within one source polygon only |

- Parmehr, Fraser, Zhang, Leach, "Automatic registration of optical imagery with 3D lidar data
  using local combined mutual information", ISPRS Annals II-5/W2 229, 2013,
  <https://doi.org/10.5194/isprsannals-II-5-W2-229-2013> `[verified, full text]`: WorldView-2 and
  20 cm aerial against 4 pts/m2 lidar; intensity gives a sharper MI peak than the DSM; combined MI
  registered 98 % of templates. Journal version: ISPRS J. 2014,
  <https://doi.org/10.1016/j.isprsjprs.2013.11.015> `[verified, title]`. Mastin et al., CVPR 2009,
  <https://doi.org/10.1109/cvpr.2009.5206539> `[verified, abstract]`, MI with lidar elevation.
- Habib et al., PE&RS 71(6) 2005, <https://doi.org/10.14358/pers.71.6.699> `[verified, abstract]`:
  lidar linear features as control.
- Chen, Knoblock, Shahabi, GeoInformatica 10, 2006, <https://doi.org/10.1007/s10707-006-0344-6>
  `[verified, title; method from ISI page]`: road vectors to orthoimagery by matched control points,
  filtering, triangulation and rubber-sheeting; a USGS follow-up found it failed in some areas,
  <https://doi.org/10.1145/1146598.1146680> `[verified, abstract]`.
- Girard, Charpiat, Tarabalka, ACCV 2018 (HAL hal-01923568), and IGARSS 2019,
  <https://doi.org/10.1109/igarss.2019.8898071> `[verified, abstract]`: CNN predicts a displacement
  field aligning OSM/cadastre polygons to imagery. Accuracy numbers not opened `[unverified]`.
- OS MasterMap Topography: absolute RMSE under 0.5 m at 1:1250 urban, about 1.1 m at 1:2500 rural
  (HM Land Registry practice guide 40 supplement 1, gov.uk) `[unverified, search summary]`. Needs a
  licence. OS OpenMap Local accuracy not found. OSM buildings in GB are often traced from aerial or
  satellite basemaps and inherit their offset `[judgement]`.
- Hillshade as reference: depends on sun direction, which Esri does not expose; no established
  method with reported accuracy found for basemap-to-hillshade registration.

## 4. Building and tree lean

- True orthophoto: differential rectification on a DSM moves roofs to their footprints but leaves
  occluded ground ("double mapping") that only other images can fill. Habib, Kim, Kim, PE&RS 73(1)
  2007, <https://doi.org/10.14358/pers.73.1.25> `[verified, abstract]`. Both need the sensor model.
- A high-resolution satellite pushbroom scene is close to affine over a scene. Fraser and
  Yamakawa, ISPRS J. 58, 2004, <https://doi.org/10.1016/j.isprsjprs.2003.10.001> `[verified,
  title]`; Christie et al. state "a satellite pushbroom sensor model is well-approximated locally by
  affine projection" and predict one flow orientation per image, with magnitude proportional to
  height. Christie et al., CVPR 2020, <https://doi.org/10.1109/cvpr42600.2020.01452>
  `[verified, full text]`. From a single image with predicted heights they report angle error
  16 to 23 degrees, magnitude error 2.4 to 4.2 px; registration fraction with IoU > 0.5 rose from
  0.40 to 0.93.
- Roof-to-footprint offset vectors per building from off-nadir images: Wang et al. (BONAI),
  IEEE TPAMI 2022, <https://doi.org/10.1109/tpami.2022.3162583> `[verified, abstract]`.
- Feasibility here: with unknown sensor position the lean is still two unknowns per source polygon
  (direction, metres of lean per metre of height = tan off-nadir), because the projection is near
  parallel. We have height from the EA nDSM, so those two plus the bias shift can be fitted from
  matches. That fit combines the affine model and bias compensation above; no paper doing exactly
  this on a basemap was found `[gap]`. Occluded ground behind leaning objects stays wrong.
- Our checkpoint 3 data (object shifts disagree in direction between Upper Aire and Ferrybridge,
  weak height correlation) is consistent with a per-scene lean direction, but EA aerial is itself a
  frame-camera ortho with its own radial lean, so object windows mix two leans `[judgement]`.

## 5. Libraries on CPython 3.13

| Package | Version, date | 3.13 install | Notes |
| --- | --- | --- | --- |
| arosics | 1.13.2, 2025-10-20 | sdist; needs `gdal` | `from osgeo import gdal` in CoReg, CoReg_local, Tie_Point_Grid |
| py_tools_ds, geoarray | 0.24.1 (2026-01), 0.19.2 (2025-09) | sdist; need `gdal>=3.8` | AROSICS deps; use osgeo throughout |
| gdal (bindings) | 3.13.3, 2026-08-18 | sdist only | Builds against system libgdal-dev of the same version; host has libgdal26 3.0.4, no gdal-config |
| Geospatial-COSICorr3D | no PyPI release | conda or Docker | Raw-scene oriented |
| gefolki | 1.1.0, 2026-06-08 | py3 wheel | GPL-3.0; packaging of aplyer/gefolki |
| opencv-python-headless | 5.0.0.93, 2026-07 | wheel, already in pipeline | DIS flow, ECC, USAC/MAGSAC present |
| scikit-image | 0.26.0, 2025-12 | cp313 wheel, in pipeline | phase_cross_correlation, optical_flow_tvl1, optical_flow_ilk |
| scipy | 1.18.1, 2026-08 | cp313 wheel | RBFInterpolator thin_plate_spline kernel |
| pykrige | 1.7.3, 2025-10 | cp313 wheel | Ordinary kriging (AROSICS uses it) |
| scikit-learn | 1.9.1, 2026-09 | cp313 wheel | GaussianProcessRegressor |
| kornia | 0.9.0, 2026-10-23 | py3 wheel, torch >= 2.5.1 | LoFTR, LightGlue, DISK, DeDoDe, ALIKED, XFeat modules |
| romatch | 0.1.2, 2025-10-24 | py3 wheel | Pulls torch, timm, wandb, poselib, albumentations |

Running AROSICS without the venv's GDAL: conda-forge (the documented, "preferred" route,
<https://danschef.git-pages.gfz-potsdam.de/arosics/doc/installation.html> `[verified]`), or the
official `ghcr.io/osgeo/gdal:ubuntu-small-*` images, which ship GDAL Python
(<https://github.com/OSGeo/gdal/blob/master/docker/README.md> `[verified]`) with
`pip install arosics` on top `[untested]`. It cannot run without the bindings: the imports are
unconditional `[verified, source]`. The project's `gdal-ecw` image builds with
`-DBUILD_PYTHON_BINDINGS=OFF`.

## Candidate designs

### A. Per-source-polygon shift from EA aerial, propagated by polygon

Measure the open-ground shift with the existing phase correlation inside each Esri source polygon
that overlaps EA aerial; apply it as a constant UV offset to every tile in that polygon.

- For: matches the bias-compensation model; uses metadata Esri already serves; no new dependency;
  correction is a UV translation, no resampling.
- Against: polygons with no EA overlap get nothing; constancy within a polygon is untested
  (offset-survey "Not checked": smoothness across a region); ignores lean.
- Evidence thin on: whether Vivid polygons are single scenes (`BlockName` suggests regional
  releases containing many scenes).

### B. Lidar intensity + nDSM as the reference everywhere, fitting shift and lean per polygon

Render EA lidar intensity (and DSM) on the BNG grid; match Esri to it per window (MI or phase
correlation on gradients); fit per polygon a bias shift plus lean direction and tan(off-nadir)
using nDSM height; apply as per-vertex UV offsets `shift + h * k * (sin a, cos a)`.

- For: works wherever EA lidar exists (most of England), not only where 2020+ aerial exists;
  corrects lean on roofs; model has three to four parameters per polygon, so robust.
- Against: MI registration accuracy against intensity is reported only as template success, not
  RMSE; leaf-on canopy differs from lidar; occluded ground stays wrong; the combined fit is not a
  published method. Validate on the EA-aerial sites first, with EA aerial as held-out truth.

### C. AROSICS-style dense tie-point grid against EA aerial, interpolated, applied to UVs

Run the full local pipeline (window grid, reliability + RANSAC filtering, kriging or TPS) in a
conda or GDAL container, export the tie-point grid, and offset mesh UVs from it.

- For: the established, published tool; handles arbitrary smooth variation; outlier filters
  already built.
- Against: only where EA aerial exists; a free field absorbs lean as noise on roofs; 15 to 20 % of
  windows survive at our sites, so the field is sparse in fen, woodland and floodplain; separate
  conda/container environment.

Recommendation: A first (cheap, falsifiable: does shift stay constant within a polygon?), then B
if lean matters for the camera-render checks. Use C's AROSICS run only as an independent check of
`eval offset` on one site, not as the production path.
