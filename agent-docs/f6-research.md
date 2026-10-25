# F6 evaluation harness: prior-art research

Compiled 2026-10-25. Status tags: VERIFIED = text opened and read in this session. UNOPENED = a
citation known from the literature but whose text was not opened here (details are from memory;
check before quoting). UNVERIFIED = could not be confirmed.

## Q1 DEM vertical accuracy against reference

Answer:

- Report median (bias), NMAD, and the 68.3% and 95% quantiles of the absolute error, plus RMSE only
  as a comparison (Höhle and Höhle 2009). Report a bootstrap CI for each.
- Library: xdem (0.2.3, 2026-03-03, active) for `nmad`, terrain attributes and binning; numpy/scipy
  for the rest.
- EA's accuracy figure is +/-15 cm RMSE per contributing survey (not stated for the merged
  composite).
- Compare a DSM-derived mesh only to a DSM of the same return type (FZ_DSM), not to the DTM, or
  stratify by surface class.

### Definitions (VERIFIED, Höhle and Höhle 2009 full text)

Höhle J., Höhle M. (2009). "Accuracy assessment of digital elevation models by means of robust
statistical methods." ISPRS J. Photogramm. Remote Sens. 64(4), 398-406. DOI
10.1016/j.isprsjprs.2009.02.003. Open copy: <https://vbn.aau.dk/ws/files/17874509/sdarticle.pdf>.

With error `dh_i = h_i(DEM) - h_i(reference)`:

| Measure | Definition |
| --- | --- |
| Median | `Q(0.5)` of `dh` = `m_dh` |
| NMAD | `1.4826 * median_j(abs(dh_j - m_dh))` (their Eq. 2) |
| 68.3% quantile | `Q_abs(0.683)` of `abs(dh)` |
| 95% quantile | `Q_abs(0.95)` of `abs(dh)` |
| Sample quantile | `Q(p) = x_(j)`, `j = ceil(p*n)`, where `x_(j)` is the j-th order statistic |

- Why: for normal errors 68.3% of values lie within `mu +/- sigma` and 95% within
  `mu +/- 1.96 sigma`. Laser and photogrammetric DEMs are not normal because of filtering errors and
  outliers, so RMSE is not robust.
- The paper's conclusion: median, NMAD and sample quantiles should be used.
- Uncertainty of each measure: 1000-replicate bootstrap, with the 2.5% and 97.5% percentiles as the
  95% CI. For spatially dependent errors they suggest a block bootstrap.
- Stratification: quantile regression of the p-th quantile of `abs(dh)` on terrain class (R package
  `quantreg`, Koenker 2005). The simpler form is quantiles computed within each class.
- Sample sizes:
  - To show the 68.3% quantile is under 10 cm: n = 110 (alpha = beta = 0.05, distribution-free
    binomial test, reject H0 if Y > 84).
  - They cite the ASPRS Lidar Committee (2004) minimum of 20 checkpoints per land-cover class (60
    for three classes).
  - Reference data should be markedly more accurate than the DEM under test; the abstract names this
    a requirement.

### Library (xdem; VERIFIED from docs and PyPI)

- PyPI `xdem` 0.2.3 (2026-03-03); `geoutils` 0.2.5 (2026-01-28). The xdem docs track geoutils
  0.2.6.dev.
- `xdem.spatialstats.nmad(data, nfact=1.4826)`: NMAD as above.
- `xdem.DEM.get_stats(...)`: summary stats.
- `xdem.DEM.slope(...)`, `.aspect(...)`, `.get_terrain_attribute(attribute)`: stratification
  variables.
- `xdem.spatialstats.nd_binning(values, list_var, list_var_names, ...)`: per-bin statistics. Pass
  `statistics=[np.nanmedian, xdem.spatialstats.nmad]` and bin by slope/aspect (the docs list it but
  do not demonstrate slope binning on the page I read).
- `xdem.spatialstats.sample_empirical_variogram`, `number_effective_samples`, `patches_method`:
  spatially correlated uncertainty of an area-wide statistic.
- Vertical-shift/alignment: `xdem.coreg.NuthKaab` (translation plus vertical, iterative cosine fit
  on slope/aspect; needs relief, diverges on flat terrain, no rotation) and
  `xdem.coreg.VerticalShift`. Use before scoring only if separating absolute bias from shape error
  is wanted.
- The xdem robust-statistics page
  (<https://xdem-adehecq.readthedocs.io/en/latest/intro_robuststats.html>) defines
  `NMAD = 1.4826 * median(abs(x_i - median(x)))`, cites Höhle and Höhle (2009), and uses half the
  84th-16th percentile range and the absolute 68th percentile as robust sigma analogues.
- The `/latest/` and `/stable/` pages for that robust-statistics URL returned 404 on the main
  domain; the fork host above served it.

### Reference as DSM vs DTM (VERIFIED from EA guide; the scoring convention is not standardised)

EA LIDAR Composite Technical Information Guide (April 2022, v2022):
<https://environment.data.gov.uk/api/file/download?fileDataSetId=8a0b69a5-a48a-4b1f-a0a8-eef7d810340e&fileName=LIDAR%20Composite%20Technical%20Information%20Guide.docx>

- DTM: from the last or only pulse, with surface objects removed by "bespoke algorithms and manual
  editing".
- LZ_DSM: last or only pulse, includes vehicles, buildings, vegetation.
- FZ_DSM: first or only pulse, includes the same objects "as well as the terrain surface where the
  first or only return was the ground".
- Available at 1 m and 2 m, GeoTIFF 5 km tiles, EPSG:27700, AOD Newlyn via OSTN15/OSGM15.
- satmesh's `EA_DSM` coverage (`...-first-return-dsm-1m/wcs`) is the FZ_DSM; this is the right
  like-for-like reference for a surface mesh. Note the data.gov.uk page titled "LIDAR Composite DSM
  2022 1m" actually describes and links the last-return DSM.
- Accepted practice (Höhle and Höhle's abstract): built-up and wooded areas need filtering to get
  bare earth, so a DTM is evaluated on open terrain and a DSM on surface returns. No source I opened
  prescribes a procedure for scoring a DSM-derived mesh. The defensible protocol is to score
  DTM-derived geometry against the DTM and DSM-derived geometry against the FZ_DSM, and stratify by
  an object mask (`nDSM = FZ_DSM - DTM > threshold`). Mark that mask threshold as a chosen tunable.
- ASPRS Positional Accuracy Standards for Digital Geospatial Data, Edition 2 (approved 2023-08-23;
  UNOPENED, via secondary summary
  <https://lidarmag.com/2023/10/06/the-asprs-positional-accuracy-standards-edition-2/>):
  - Splits vertical accuracy into non-vegetated (NVA) and vegetated (VVA).
  - Edition 2 removed the pass/fail requirement for VVA and the 95% confidence measure.
  - Raised the minimum checkpoint count to 30 (cap 120).
  - Edition 1 (2014) reported NVA/VVA at the 95th percentile.

### EA accepted vertical accuracy (VERIFIED)

- data.gov.uk LIDAR Composite DSM 2022 1m
  (<https://data.gov.uk/dataset/cf3f1137-c12b-44a1-a835-e80fe4a60b92/lidar-composite-dsm-2022-1m>):
  each contributing survey has "a vertical accuracy of +/-15cm RMSE". Other records (2m DSM; 2017
  DTM 1m) repeat +/-15 cm RMSE. A 2022 first-return 2 m record states +/-10 cm (via search snippet,
  record
  <https://www.data.gov.uk/api/2/rest/harvestobject/143832e8-47a7-4a95-a51f-4a6e218604c8/html>, text
  not opened in full).
- The figure is a per-survey specification against ground-truth surveys (EA LIDAR Open Data FAQ v5,
  <https://www.owenboswarva.com/opendata/EA/Environment_Agency_LIDAR_Open_Data_FAQ_v5.pdf>: search
  summary only; the PDF could not be text-extracted). It does not cover vegetation penetration,
  bilinear resampling when merging resolutions, or manual DTM edits. No composite-level accuracy
  figure was found: UNVERIFIED.
- The survey year (`SRVY_YEAR`, `SD_FLOWN`, `ED_FLOWN`) is per tile in the
  `*_lidar_used_in_merging_process` layer of each download's GeoPackage; the composite mixes dates
  from 2000 to 2022.

## Q2 Horizontal co-registration of Esri vs EA orthoimages

Answer:

- Established choice for optical image-to-image georegistration: Fourier phase correlation with
  subpixel upsampling in a moving-window tie-point grid with outlier filtering. AROSICS (Scheffler
  et al. 2017) packages exactly this, with a global and a local mode.
- Fallbacks: SIFT/ORB or learned matchers plus RANSAC, or mutual information when radiometry differs
  strongly.
- A single global shift is the first-order model; orthophotos have spatially varying residuals, so
  estimate a grid of local shifts and report the median and spread.
- No source I found fixes the number of sites; use many windows and report a bootstrap CI of the
  median shift.

### Methods and sources

| Method | Source | Library call | Accuracy note |
| --- | --- | --- | --- |
| Phase correlation, subpixel by matrix-multiply DFT upsampling | Guizar-Sicairos, Thurman, Fienup 2008, Opt. Lett. 33, 156 (VERIFIED as cited by skimage); Kuglin and Hines 1975; Foroosh, Zerubia, Berthod 2002, IEEE TIP 11(3):188-200 (bibliographic record VERIFIED, content UNOPENED) | `skimage.registration.phase_cross_correlation(reference_image, moving_image, *, upsample_factor=1, space='real', disambiguate=False, reference_mask=None, moving_mask=None, overlap_ratio=0.3, normalization='phase')` returns `(shift, error, phasediff)` | Registration accurate to `1/upsample_factor` px (docs); phase normalisation copes with illumination change but is "not very robust to noise". Masks switch to masked NCC (Padfield 2012) and then `error` is NaN |
| COSI-Corr (orthorectify, coregister, subpixel correlate) | Leprince, Barbot, Ayoub, Avouac 2007, IEEE TGRS 45(6):1529-1558 (VERIFIED abstract via search) | COSI-Corr (ENVI/IDL; not a pip package) | Abstract reports about 1/50 px on SPOT after DEM orthorectification; not independently validated |
| AROSICS | Scheffler D., Hollstein A., Diedrich H., Segl K., Hostert P. (2017). Remote Sens. 9(7):676. DOI 10.3390/rs9070676 | `arosics.COREG`, `arosics.COREG_LOCAL` (class names UNVERIFIED in docs I could open; confirmed in package structure by memory only) | Abstract (search summary of edoc.hu-berlin.de record): sub-pixel RMSE about 0.3 px or better on more than 9000 images from several sensors |
| Feature matching + RANSAC | SIFT (Lowe 2004, UNOPENED), LoFTR (Sun et al. CVPR 2021, UNOPENED) | `cv2.SIFT_create`, `cv2.findHomography(..., cv2.RANSAC)`, `kornia.feature.LoFTR` | Recall drops on sparse or repetitive texture; good for gross offsets or rotation, then refine with phase correlation (hybrid SIFT + phase-correlation schemes exist; patent text and search snippets only) |
| Mutual information | Standard for multimodal registration | `cv2` has none; use `SimpleITK.ImageRegistrationMethod().SetMetricAsMattesMutualInformation()` (UNOPENED) | Heavier; same-band RGB pairs rarely need it |
| ECC / pcc / lightglue | satalign (the library opensr-test calls) | `satalign.pcc.PCC`, `satalign.ecc.ECC`, `satalign.lgm.LGM` | Seen in opensr-test source (VERIFIED) |

Versions (PyPI, checked 2026-10-25): scikit-image 0.26.0 (2025-12-20), arosics 1.13.2 (2025-10-20),
opencv-python-headless 5.0.0.93 (2026-07-02), kornia 0.9.0 (2026-10-23).

### AROSICS facts (VERIFIED, docs and GitHub README)

- Docs: <https://danschef.git-pages.gfz-potsdam.de/arosics/doc/about.html>. Apache 2.0.
- Global mode: one X/Y translation from a small window, fast, only static shifts.
- Local mode: dense grid of tie points, multistage false-positive filtering, an affine fit on the
  valid ones, then a cubic warp. This handles spatially variable shifts.
- Multi-temporal and multi-sensor robustness: outlier detection, user masks, automatic overlap.
- The docs say nothing about orthorectification or DEM use.
- Phase-correlation matching in a moving window, per the paper abstract.

### Global shift vs spatially varying warp

- Source of spatially varying error: orthorectification with an imperfect or bare-earth-only
  elevation model.
  - Conventional orthophotos use a ground model, so raised features lean (VERIFIED in search
    summaries of ESRI and PSU material, <https://www.e-education.psu.edu/geog480/node/457>). True
    orthos use a surface model and fix lean, but pass DSM errors into the result (ITC lecture, via
    search snippet).
  - Standard relief displacement: `d = r * h / H` for image radial distance `r`, object height `h`,
    flying height `H` (UNOPENED textbook formula).
- EA aerial: 10-50 cm ground resolution, "ortho-rectified using simultaneous LIDAR and GPS"
  (VERIFIED via <https://ckan.publishing.service.gov.uk/dataset/vertical-aerial-photography>
  snippet); ECW 5 km tiles in OSGB36; no accuracy figure found: UNVERIFIED. Whether EA used DTM or
  DSM orthorectification: UNVERIFIED.
- Esri World Imagery: accuracy is not published per UK location in anything I found. The layer's
  citation (metadata) layer shows source, date, resolution and accuracy in a click-popup (Esri blog,
  via search snippet). A 2019 Esri blog gave 4 m CE90 for Vivid in the US (not the UK). Query the
  citation layer at the AOI to see what Esri claims. UK sub-metre source and its orthorectification:
  UNVERIFIED.
- Consequence: a 2.4 m offset is plausible for non-true ortho Esri imagery against EA imagery.
  Expect it to vary across the AOI with the land surface and with building height.
- Conclusion: a single global number over the AOI is only defensible as a summary of a grid of local
  shifts. Report the median, the NMAD, and a map of local shifts.

### Defensible protocol (assembled from the verified parts; not one prescribed standard)

1. Resample both images to one grid and one band (luminance), same pixel size, bicubic with
   antialiasing for the downsample.
2. Grid of windows (e.g. 256-512 px with 50% overlap), each given to `phase_cross_correlation` with
   `upsample_factor` of 20 to 100 (a chosen tunable). Keep windows with a clear peak: the
   AROSICS-style reliability filter, or the peak-to-sidelobe ratio (UNOPENED). Masks from the DSM
   exclude buildings and trees if wanted (vegetation changes between dates).
3. Median shift in E and N with a bootstrap CI over windows; NMAD as the spread. Because
   neighbouring windows are correlated, use a block bootstrap (Höhle and Höhle propose block
   bootstrap for dependent data, VERIFIED) or `xdem.spatialstats.number_effective_samples` on the
   shift field.
4. Check the shift field for structure (a ramp, relief-dependent pattern). If the shift varies
   systematically use `arosics.COREG_LOCAL` (affine/grid) rather than one value.
5. How many sites: no standard was found, so call it UNVERIFIED. Honest framing: tens to hundreds of
   windows from different parts of the AOI and, if possible, several AOIs/dates. Höhle and Höhle's
   sample-size method is the closest verified analogue (n = 110 for a 68.3% quantile test,
   distribution-free).
6. Validate the pipeline itself on a synthetic known shift of the same imagery before trusting the
   2.4 m. Subpixel peak finding has a known bias toward integer pixels (UNOPENED; the 2015
   comparative study of subpixel peak estimators, via snippet, is the pointer).

## Q3 Texture sharpness and fidelity against a finer, temporally different reference

Answer:

- No metric is robust to date, season and shadow differences. PSNR and SSIM are known to reward blur
  and punish misalignment and luminance change; LPIPS is less affected by blur but still sensitive
  to content change.
- opensr-test is the only remote-sensing-specific tool found; it separates consistency (SR vs the LR
  input), synthesis (high-frequency energy added) and correctness
  (improvement/omission/hallucination vs HR), and it histogram-matches and re-aligns the SR to the
  HR before scoring.
- It still compares to an HR image with the same content, so with date-different EA aerials it
  measures appearance change as much as SR quality: treat the correctness numbers as relative
  between methods, not absolute.

### Known pitfalls (VERIFIED in search summaries; underlying papers not all opened)

- Cross-sensor SR paper (arXiv 2510.23816): the HR reference may have temporal and spatial mismatch,
  and a model can score well pixelwise by reproducing the reference's smoothness; one metric is not
  enough.
- Yangtze 1 m SR study (arXiv 2505.05367): PSNR can rank blurred images higher and is highly
  susceptible to misalignment; SSIM remains sensitive to misalignment.
- MuS2 benchmark (arXiv 2210.02745): PSNR/SSIM correlate poorly with reconstruction quality; LPIPS
  judged more suitable for single-image SR; proposes normalising each score to a bicubic baseline.
- 2026 ISPRS reference-SR paper: temporal mismatch between target and reference makes texture
  transfer unreliable.
- Claims that no-reference metrics (NIQE, MANIQA, FID) detect hallucination are unsupported: they
  measure naturalness or distribution distance, not fidelity.

### Candidate metrics and implementations

| Metric | Definition / source | Library call | Version, status |
| --- | --- | --- | --- |
| PSNR, SSIM | Wang, Bovik, Sheikh, Simoncelli 2004, IEEE TIP 13(4) (UNOPENED) | `skimage.metrics.peak_signal_noise_ratio`, `structural_similarity`; `torchmetrics.image.StructuralSimilarityIndexMeasure` | skimage 0.26.0; torchmetrics 1.9.0 (2026-03-09), active |
| LPIPS | Zhang, Isola, Efros, Shechtman, Wang, CVPR 2018 (UNOPENED) | `lpips.LPIPS(net='alex')` | lpips 0.1.4 (2021-08-25), stable, no releases since |
| LPIPS, many NR/FR metrics | pyiqa (IQA-PyTorch) | `pyiqa.create_metric('lpips')` | pyiqa 0.1.16 (2026-07-08), active |
| piq | | `piq.ssim`, `piq.LPIPS` | piq 0.8.0 (2023-07-04), slow-moving |
| Radially averaged power spectrum | Azimuthal integration of the 2D power spectrum; used in Durall, Keuper, Keuper CVPR 2020 (VERIFIED as arXiv 2003.01826) to show GAN upsampling distorts the spectrum | numpy `np.fft.fft2` plus binning by radius; no standard package function found | Compare the 1D curves of output vs reference. Not a distance metric by itself |
| MTF estimation | Slanted-edge method, ISO 12233; Burns SFRMAT5; Python port reported in an Electronic Imaging paper (2026, via snippet; the repo name was not captured: UNVERIFIED) | none confirmed. `toupy.resolution.MTF` is an edge-method estimator aimed at X-ray | Needs sharp straight edges (roof edges, road kerbs) in both images |

No standard exists for judging sharpness across dates. The defensible options are (a) edge-based
MTF/edge width on edges that persist across dates (building roofs, kerbs, road markings), and (b)
comparing the radial power spectrum within matched, masked, stable regions. Both are practice, not a
published protocol (UNVERIFIED as a named method).

### opensr-test (VERIFIED by reading the 1.3.3 wheel source)

- PyPI: `opensr-test` 1.3.3, released 2025-03-21, Python `>=3.10,<4`, MIT licence. Last GitHub push
  2025-04-07, 2 open issues, not archived. Maintained but slow (no activity since April 2025).
- Dependencies: kornia, lpips, open-clip-torch, openai-clip, opencv-python, satalign, scikit-image,
  torchvision, pydantic, mpltern.
- Citation: Aybar, Montero, Donike, Kalaitzis, Gómez-Chova (2024), "A Comprehensive Benchmark for
  Optical Remote Sensing Image Super-Resolution", IEEE GRSL 21, 5003105. DOI
  10.1109/LGRS.2024.3401394 (<https://ieeexplore.ieee.org/abstract/document/10530998>). The paper
  text was not opened.
- Docs: <https://esaopensr.github.io/opensr-test/>; code <https://github.com/ESAOpenSR/opensr-test>.
- API: `opensr_test.Metrics(params: Config | None = None, **kwargs)`;
  `.compute(lr, sr, hr, gradient_threshold="auto")` with `(C, H, W)` torch tensors;
  `hr.shape[-1] / lr.shape[-1]` must be an integer scale; `sr.requires_grad` must be False. Also
  `.consistency(lr, sr)`, `.synthesis(lr, sr, hr=None)`, `.correctness(lr, sr, hr)`.
- Return keys of `compute`: `reflectance`, `spectral`, `spatial`, `synthesis`, `ha_metric`,
  `om_metric`, `im_metric` (README example output uses `*_percent`; the code returns `*_metric`).
- Config defaults: `agg_method="pixel"`, `border_mask=16` (px cropped), `spatial_method="pcc"` (also
  `ecc`, `lgm`), `spatial_threshold_distance=5` (max translation px), `reflectance_distance="l1"`,
  `spectral_distance="sad"`, `synthesis_distance="l1"`, `correctness_distance="nd"` (also `lpips`,
  `clip`, `mtf`, `psnr`, ...), `correctness_norm="softmin"`, `correctness_temperature=0.25`,
  `im_score=om_score=ha_score=0.05`.

What each group computes:

- Consistency (SR against the LR input; this is the "downsample the output, diff against the input"
  check):
  - `sr_to_lr` = SR downsampled by `1/scale` with torch
    `interpolate(mode="bilinear", antialias=True)`.
  - `reflectance` = L1(LR, sr_to_lr); `spectral` = spectral angle distance (SAD, degrees);
    `spatial` = norm of the translation `sqrt(tx^2 + ty^2)` found by aligning LR RGB to `sr_to_lr`
    RGB (PCC by default), NaN if the aligner warns.
  - Function names in `utils.py` are swapped: `apply_upsampling` downsamples, `apply_downsampling`
    upsamples.
- Harmonisation (before synthesis and correctness): `hq_histogram_matching(SR, HR)` for reflectance,
  then spatial alignment of SR to HR (`harm_apply_spectral/spatial`). This removes global
  radiometric and shift error, so it partly absorbs date and offset differences, but not local
  change.
- Synthesis: L1 distance between `lr_to_hr` (LR upsampled to HR size with the same interpolation)
  and `sr_harm`, mean over pixels; interpreted as high-frequency detail added (higher means more
  added).
- Correctness, per pixel (or patch):
  - Distances `d_ref = d(lr_to_hr, hr)`, `d_im = d(sr_harm, hr)`, `d_om = d(sr_harm, lr_to_hr)`.
    Using the names the code assigns, relative distances are `d_im/d_ref` and `d_om/d_ref`.
  - Scores `improvement = d_im + d_om*(1 - exp(-H*lambda_im))`,
    `omission = d_om + d_im*(1 - exp(-H*lambda_om))`, `hallucination = exp(-d_im*d_om*lambda_ha)`,
    with `H = d_im + d_om - 1`. The lambdas are the `*_score` config values and are "calibrated
    according to human perception" per the docstring; the code comments call the hallucination
    setting "quite conservative".
  - A softmin over the three with temperature T gives per-pixel class weights; `*_metric` is the
    mean weight (or the class fraction if `correctness_norm="percent"`). Pixels with a low reference
    gradient are masked (`gradient_threshold="auto"` takes the 75th percentile of `d_ref`).
- The softmin/lambda/temperature constants are the authors' calibrated choices (tunables), not
  derived from a definition. The paper (not opened) is the only justification.
- For satmesh: OSR needs an LR to HR pair of integer scale. It does not model the date difference;
  run it with the EA aerial resampled to the SR grid as HR, and report both raw and harmonised
  numbers.

## Q4 Camera visibility check against a virtual 3D scene

Answer:

- No single established standard method checks "everything on the ground visible in reality is
  visible in the render". It is assembled from established parts: visibility on a surface model (ray
  casting or viewshed), object-ID/depth rendering, and a reference surface.
- The best available "visible in reality" proxy without the real photo is the first-return DSM or
  the classified lidar point cloud. Both are independent of the textured mesh and of Esri imagery,
  but not of the mesh geometry source if the mesh is built from the same DSM.
- Prior work validates synthetic renders mainly through localisation accuracy: render, match
  features against the real photo, estimate the pose.

### Established components

| Approach | Source | Library call |
| --- | --- | --- |
| Viewshed on a DEM/DSM (single observer, sightline-free sweep) | Wang, Robinson, White 2000, "Generating viewsheds without using sightlines", Photogramm. Eng. Remote Sens. (VERIFIED as the GDAL reference); Fisher 1991/1992/1993 on DEM error and algorithm uncertainty (VERIFIED via snippets: e.g. Int. J. GIS 7(4):331-347) | CLI `gdal_viewshed -ox X -oy Y -oz 1.5 -tz 0 -md 500 -cc 0.85714 -om NORMAL src.tif out.tif` (added GDAL 3.1; curvature coefficient default 0.85714; `-om` NORMAL/DEM/GROUND/ACCUM; projected CRS only; VERIFIED in docs). Python `gdal.ViewshedGenerate`: signature not verified |
| Ray casting against a triangle mesh | Embree-based BVH | `open3d.t.geometry.RaycastingScene`: `add_triangles(...)`, static `create_rays_pinhole(intrinsic_matrix, extrinsic_matrix, width_px, height_px)` (returns shape (H, W, 6)), `cast_rays(rays)` (keys `t_hit`, `geometry_ids`, `primitive_ids`, `primitive_uvs`, `primitive_normals`), `test_occlusions(rays, tnear, tfar)`, `count_intersections(rays)` (VERIFIED in docs; whether it uses Embree was not stated on the page). open3d 0.20.0 (2026-09-16) |
| Ray casting, trimesh | | `trimesh.ray.ray_pyembree.RayMeshIntersector` / `trimesh.ray.ray_triangle.RayMeshIntersector` with `intersects_location`, `intersects_first`, `intersects_any`. trimesh 5.2.0 (2026-10-24). Embree backend dependency (`embreex`) not stated on the page I read: UNVERIFIED |
| Rasterised depth and ID buffers | | `pyrender` (offscreen via EGL or OSMesa, depth image; segmentation masks: the README does not mention them; version 0.1.45 of 2021-02-18, effectively unmaintained). Alternatives: Open3D `OffscreenRenderer`, Blender (`bpy`) object-index pass (not verified here), Gazebo |
| Simulator with segmentation | gz-sensors | Gazebo `segmentation_camera` sensor (needs Gazebo Fortress or later): semantic and panoptic/instance label maps on `semantic/labels_map` and `panoptic/labels_map`, classes assigned by the `gz-sim-label-system` plugin; `depth_camera` sensor for depth (VERIFIED from docs; the pixel format of the label map was not confirmed). Doc index <https://gazebosim.org/libs/sensors> |
| Viewshed + ray casting in Python on rasters | | `rasterio` (1.5.2) for IO; `whitebox` 2.3.6 (2025-02-23) has viewshed tools (tool names UNVERIFIED) |
| CesiumJS depth/pick | | `Scene.pickPosition`, `Scene.pick`: not verified here; Cesium is the stated end-goal viewer in project memory |
| Projected landmarks with a visibility test | Project footprints (OS MasterMap, OSM) or tree points into the camera, test with ray cast against DSM/mesh | Own composition of the above; no named library or paper found |

### How "visible in reality" is obtained without the real photo

- No standard. Options in order of independence from the mesh under test:
  1. Rays against the EA classified point cloud (see Q5): needs points binned to a voxel/surfel map
     or splatted into a depth image. No established method found for point-cloud visibility beyond
     voxel/hidden-point removal (UNVERIFIED).
  2. Rays against the FZ_DSM triangulated or as a height field. Fisher (VERIFIED via snippets) found
     that viewsheds are sensitive to DEM error and to the algorithm: visible area is systematically
     smaller in DEMs with error. So report a probable viewshed (fraction of Monte Carlo realisations
     visible, using the DEM error from Q1) rather than a boolean map.
  3. Footprints from OS/OSM, which are independent of the lidar; only useful as the object list to
     check.
- The check itself: for each ground object that the reference says is visible (target visible from
  the camera by rays against the reference), test that the render shows it (depth/ID buffer at the
  projected pixel is within a tolerance of the object's range). Compute recall of visible objects
  and, separately, precision (objects in the render that the reference says are occluded). Tolerance
  and threshold values are tunables (call out in the design).

### Prior work validating synthetic renders for visual localisation

| Work | What it shows | Status |
| --- | --- | --- |
| Panek, Kukelova, Sattler, "MeshLoc: Mesh-Based Visual Localization", ECCV 2022, arXiv 2207.10762 | Features extracted from renderings of dense meshes, even geometry-only without colour, remain competitive for localisation | VERIFIED (search summary and abstract) |
| Panek, Kukelova, Sattler, "Visual Localization using Imperfect 3D Models from the Internet", CVPR 2023, arXiv 2304.05947, DOI 10.1109/CVPR52729.2023.01266 | Benchmark of CAD/footprint/aerial models of varying fidelity; localisation pipelines have room to improve on imperfect models | VERIFIED (search summary) |
| Baatz, Saurer, Köser, Pollefeys, ECCV 2012; Saurer et al., IJCV 116:213-225 (2016), DOI 10.1007/s11263-015-0830-0 | DEM-derived rendered terrain contours matched to mountain photos; over 200 then over 1000 query images with GPS ground truth | VERIFIED (existence, scope); the detail of what is matched is not confirmed |
| Patel, Barfoot, Schoellig, ICRA 2020 | UAV images localised against Google Earth renders by dense mutual information; feature-based localiser struggles under large lighting change | VERIFIED (search snippet) |
| PiLoT (arXiv 2603.20778), LoD-Loc v3 (arXiv 2603.19609), AeroMap3D (arXiv 2607.14009) | 2026 preprints: render a geo-referenced view from Google Earth/3D Tiles/LoD city models and match frames; instance masks from Unreal + Cesium plugin; roof and facade matches create height bias | VERIFIED existence via search; contents not opened; peer-review status unknown |

Common validation protocol (consistent across these): ground-truth pose, localisation error
(position m, rotation deg) and recall at thresholds; failure causes are appearance change,
vegetation and geometry error. None of the papers I saw defines a "scene coverage"/object-recall
metric as in the F6 goal: UNVERIFIED that prior work has one.

## Q5 EA data for ground truth

Answer:

- The raw point cloud exists, is free under the Open Government Licence, is delivered as LAZ in 1 km
  tiles (grouped in 5 km zips per survey year), and its index is queryable by API.
- EA's own documentation says the classification is "ground" and "surface objects" only; no source I
  could open confirms separate building/vegetation classes. A secondary search summary claiming
  ground/low/medium/high vegetation is UNVERIFIED.
- A programmatic tile download endpoint could not be confirmed; the index API gives filenames, not
  file URLs.

### Facts (VERIFIED unless marked)

- Dataset page: <https://www.data.gov.uk/dataset/lidar-time-stamped-point-cloud>.
  - Licence: Open Government Licence; attribution "(c) Environment Agency copyright and/or database
    right 2019. All rights reserved." The 2022 composites use the same OGL with a 2022 attribution.
  - "There are no public access constraints to this data."
  - Format: LAZ in "5km download zip files for each year of survey", aligned to the OS grid; British
    National Grid EPSG:27700.
  - Classification text: "During processing the point cloud classifies the laser returns in the
    'ground' and 'surface objects'." Manual DTM editing means ground-classified points do not match
    the final DTM.
  - Coverage: surveys since 1998, point cloud for surveys back to 2006; some surveys lack a point
    cloud. Updated quarterly; last updated 2026-04-07.
  - Point density and vertical accuracy: not stated; the page defers to the coverage metadata.
- Index catalogue, queried live (OGC API - Features, no key):
  - Base:
    `https://environment.data.gov.uk/geoservices/datasets/9f0fa3fc-a860-4729-adc9-47fe53f658d0/ogc/features/v1`
  - Collections include `LIDAR_Point_Cloud_Index_Catalogue`, `LIDAR_DSM_Time_Stamped_Extents`,
    `LIDAR_DTM_Time_Stamped_Extents`, `LIDAR_Composite_1m_First_Return_DSM_2022_extents` (and
    last-return, DTM, 2m variants) and `National_LIDAR_Programme_Index_Catalogue`.
  - Request:
    `GET {base}/collections/LIDAR_Point_Cloud_Index_Catalogue/items?f=application%2Fgeo%2Bjson&limit=N`.
    I ran it with `limit=2`. The standard OGC `bbox` parameter was not exercised.
  - `numberMatched` was 244324 tile records.
  - Example record properties: `filename: TF7044_P_11243_20171107_20171107.laz`, `os_ref: TF7044` (a
    1 km OS reference), `sd_flown`/`ed_flown`, `pt_count: 1218591`, `pt_spacing: 0.0`,
    `intensity: YES`, `classified: YES`, `transform: OSTN'15`, `geoid: OSGM'15`, `year`,
    `latest: No`, `polygon_id`, `filepath: .\LAZ_Point_Archive\P_11243_11244\TF7044_P_...laz`. The
    `returns` field was 0 in that example. `pt_spacing` was 0.0 in that example, so density must
    come from `pt_count` over tile area.
  - Whole index as a file:
    <https://environment.data.gov.uk/explore/9f0fa3fc-a860-4729-adc9-47fe53f658d0?download=true> and
    `.../api/file/download?fileDataSetId=7f2a4b8f-3516-4f67-961a-f6ffeaf37d8a&fileName=LIDAR_Time_Stamped_Point_Cloud.{shp|gpkg|geojson|gdb}.zip`
    (index shapefile/GPKG/GeoJSON; not the points).
  - WFS: `.../spatialdata/survey-index-files/wfs` answers GetCapabilities. A guessed
    `spatialdata/lidar-point-cloud/wfs` returned 404; do not rely on it.
- Tile download: the official route is the Defra Data Services Platform portal
  (<https://environment.data.gov.uk/DefraDataDownload/?Mode=survey>), a JavaScript app (the fetched
  HTML is a shell only). The `api/file/download?fileDataSetId=...&fileName=...` pattern works for
  the guide docx and the index files, which suggests tile downloads use the same endpoint with a
  per-survey `fileDataSetId`. I did not find or test the `fileDataSetId` for a point-cloud tile or
  zip: UNVERIFIED. To find it programmatically, inspect the portal's network calls once in a browser
  (not done here). The QGIS plugin "LIDAR Downloader UK" 0.15.0 (published 2026-10-11, QGIS 3.22 to
  4.99) downloads EA point clouds, DTM, DSM and aerials by 5 km OSGB tile
  (<https://plugins.qgis.org/plugins/lidar_downloader_uk/>); its mechanism was not documented on the
  page, and its source would show the endpoints.
- Classification codes: EA does not document numeric codes in anything I opened. Verify by
  `pdal info --stats` or `lasinfo` on one tile before using classes (also look for ASPRS code 6
  building / 3-5 vegetation, which the EA text does not promise). Without a building/vegetation
  split, heights of buildings and trees can still be derived as first-return minus ground (return
  number and ground class), if the returns are stored; `returns: 0` in the sample index record means
  the multi-return count is not recorded there, so check in the LAZ header.
- Python tooling for LAZ (UNOPENED, standard): `laspy` with `lazrs` backend for reading; `pdal` for
  classification and DEM/nDSM generation. Versions not checked.

### Tile naming

- Composite DSM/DTM files: `<OSGB 5km>_<resolution>_<surface>.tif`, e.g. `TQ32se_1m_FZ_DSM.tif`
  (guide).
- Point-cloud LAZ: `<1km OS ref>_<polygon id>_<start date>_<end date>.laz` (from the index sample).
- Each composite download includes a GeoPackage with the per-tile survey extents and dates
  (`*_lidar_used_in_merging_process`), which gives the survey date of each contributing tile.

## Open items for the owner

- Confirm the point-cloud tile download endpoint (inspect the portal once) and sample one LAZ for
  class codes, return numbers and point density.
- The Esri citation-layer accuracy at the AOI and EA aerial orthorectification accuracy are both
  undocumented in what I could open; they bound what a measured 2.4 m shift can mean.
- No external source defines an object-level "visible in reality" recall metric; if F6 adopts one,
  it is new design and the owner decides.
