---
status: historical
topic: height-refinement
summary: Prior art on using land-cover segmentation to constrain a predicted nDSM; the cheapest established step is a ground mask that sets nDSM to zero.
answers: How is a land-cover mask used to clean a predicted nDSM?; Is there prior art for setting ground height to zero?; What minimum vegetation height thresholds do other tools use?; How are flat roofs or building heights regularised in published work?; Which semantic-constraint steps are verified?
---

# Semantic constraints on predicted height rasters: prior art

Research date 2026-10-30. Scope: published methods that use a land-cover segmentation (ground,
vegetation, building, water) to constrain or clean a predicted nDSM (Geopose, RS3DAda, CHMv2) before
it is added to a coarse DEM (5 to 30 m). Tags: **[V]** means I opened the source and checked the
claim. **[U]** means the claim is unverified (from a secondary summary or my own inference).

## Conclusions

1. **Ground mask sets nDSM to zero.** This is the cheapest established step and it targets the false
   lifts on flat painted objects.
   - RS3DAda builds its height pseudo-labels on the prior that "only trees and buildings have height
     values". It multiplies height by the inverse of the predicted ground mask [V, SynRS3D paper].
   - UMEP keeps vegetation heights only above 0.5 m and then runs a majority filter [V]. gloBFPr
     uses a `min_tree_height` noise threshold [V].
   - The DEM is untouched, so the output stays at the measured coarse DEM wherever the class is
     ground or water.
2. **Fusing a building model and a canopy model into one nDSM has precedent only in tool
   documentation, not in a dedicated paper.**
   - gloBFPr `get_fused_dsm()`: `DEM + max(canopy height, building height)` [V].
   - UMEP: split surfaces by building footprint, buffer the footprints by 2 m and remove vegetation
     inside the buffer, keep CDSM > 0.5 m, apply a majority filter [V].
   - I found no peer-reviewed method that fuses a monocular building-height model with a
     canopy-height model. Mask-select fusion (building model inside the building mask, CHM inside
     the vegetation mask, 0 elsewhere) is the documented practice [V for the tools; "no paper" is a
     negative search result].
3. **Building regularisation has mature open tools. The ladder runs from cheapest to richest:**
   - (a) Polygonise the building mask and regularise the footprint: `buildingregulariser`, MIT, an
     open alternative to the ArcGIS tool [V]. CGAL Shape_regularization is GPL-3 [V].
   - (b) LoD1-style extrusion: one robust height per footprint gives vertical walls and flat roofs.
     This is used as a label/evaluation convention in HTC-DC Net (RMSE-B), in the imperfect-labels
     paper (uniform height per building) and in gloBFPr (footprints rasterised at building height)
     [V].
   - (c) LoD2.2 from points plus footprint: **roofer** (3DBAG, GPL-3, C++ with Python bindings,
     active) [V]. **City3D** (GPL-3, based on PolyFit) [V]. Plane primitives: Efficient RANSAC
     (Schnabel 2007) and region growing (Lafarge & Mallet) in CGAL (GPL-3) [V], or Open3D
     `segment_plane` / `detect_planar_patches` (MIT) [V].
   - (d) Satellite-DSM-specific LoD2: **SAT2LoD2** (Gui & Qin 2021, ISPRS J) is the closest regime
     match (satellite DSM plus orthophoto) [V]. Its licence is an OSU EULA: non-commercial, no
     derivatives [V], so it is unusable as a dependency.
   - None of these tools has published evidence on *monocular-predicted* DSMs. All were shown on
     lidar or stereo DSMs [U for absence].
4. **Tree crowns.**
   - Crown delineation on a CHM is well established: local maxima with a variable window (Popescu &
     Wynne 2004), then marker-controlled watershed or Dalponte & Coomes (2016) region growing. lidR
     (GPL-3) and PyCrown (GPL-3, archived 2021) implement these [V].
   - Pit-free CHM (Khosravipour 2014) needs a point cloud, so it does not apply to us [V].
   - **I found no established method for regularising crown shape or "capping" bulbous predicted
     crowns.** I searched and found nothing. Report it as a gap rather than invent one.
5. **Refining the 8 m tokens to image boundaries.** Two families exist:
   - Training-free edge-aware filters on class probabilities: guided filter (He et al. TPAMI 2013,
     O(N), in OpenCV ximgproc), fast bilateral solver (Barron & Poole ECCV 2016, in OpenCV
     ximgproc), DenseCRF (Krähenbühl & Koltun NIPS 2011; pydensecrf, MIT) [V].
   - Feature upsamplers:
     - FeatUp (MIT; no DINOv3 checkpoint) [V]
     - LoftUp (ICCV 2025, MIT; no DINOv3) [V]
     - JAFAR (NeurIPS 2025, Apache-2.0; DINOv3 S/S+/B/L checkpoints; any timm backbone trainable
       without HR labels) [V]
     - AnyUp (ICLR 2026, CC-BY-4.0; backbone-agnostic at inference) [V]
     - NAF (arXiv 2025, Apache-2.0; zero-shot for any VFM, DINOv3 named) [V]
   - No upsampler reports results on satellite DINOv3 (SAT-493M) features [U, not found].
   - Learned mask refiners (CascadePSP MIT, SegRefiner Apache-2.0) are class-agnostic. They were
     trained on natural images [V for licence/venue; U for remote sensing transfer].
6. **The published monocular height pipelines do not post-process with masks.**
   - HTC-DC Net uses no masks at all, only a 1 m height threshold for its head-tail cut [V].
   - The imperfect-labels MHE paper uses footprints only for label construction and evaluation, and
     does not cover vegetation [V].
   - RS3DAda uses ground masking only during training (pseudo-labels). Its height inference takes
     only the image [V].
   - The Geopose repo makes no mention of masks [V].
   - So mask-based cleanup is an add-on that these papers do not test.
7. **Learned DSM refinement** (ResDepth, MIT, 0.25 m stereo DSMs; DSM-to-LoD2 cGAN, 0.5 m, no code
   found) needs training pairs of reference DSMs. Training-time losses (edge-aware smoothness from
   Godard 2017; P3Depth piecewise planarity; multi-task height+semantics) need fine-tuning. Both are
   lower priority for frozen models [V for the methods].

### Recommended pipeline (all steps use established methods)

1. Refine the segmentation boundaries: upsample the class logits bilinearly to 0.5 m, then apply an
   image-guided **guided filter** (or the fast bilateral solver) per class probability, then argmax.
   Escalate to JAFAR/AnyUp/NAF feature upsampling only if boundaries still miss by more than 1 to 2
   px.
2. **Ground/water: nDSM = 0.** Vegetation/building: keep values only above a threshold (0.5 to 2 m,
   as in UMEP and gloBFPr) and apply a majority filter to the masks.
3. **Mask-select fusion:** building model inside the building mask, CHMv2 inside the vegetation
   mask. Where both apply, use max (gloBFPr). Drop vegetation within a 2 m buffer of footprints
   (UMEP).
4. **Buildings:** connected components, then polygonise, then `buildingregulariser`, then
   **LoD1 extrusion** at a robust per-footprint height (median, as in the imperfect-labels and
   HTC-DC evaluation convention). Next tier: feed the DSM cells as points plus the regularised
   footprint to **roofer** for LoD2.2 (GPL-3 licence check needed).
5. **Trees:** local maxima (variable window) plus marker watershed on the CHM within the vegetation
   mask, giving crown polygons. The height inside each crown stays as predicted. No established
   shape regularisation exists.
6. Height is added to the coarse DEM only where nDSM > 0. Ground pixels equal the DEM.

**Cheapest first test:** on one existing E4 scene, apply steps 1 and 2 (guided filter plus ground =
0), then step 4 at LoD1 only (median per footprint). Measure the change in RMSE/bias against the
reference nDSM separately for ground, building and tree pixels, and look at walls and roofs in the
mesh. This is a few hundred lines of numpy/skimage/OpenCV, takes seconds per km², and needs no new
model.

## Comparison table

Fit for satmesh: H = high, M = medium, L = low.

| # | Method | Source | Code / licence | Input | Evidence in our regime | Fit |
|---|---|---|---|---|---|---|
| A | Ground-mask zeroing of nDSM | Song et al. 2024, SynRS3D/RS3DAda, NeurIPS (training-time) | MIT (SynRS3D) | nDSM + ground mask | Synthetic + real 0.09 to 1 m data; used for pseudo-labels, not inference [V] | **H** |
| B | Height threshold + majority filter on veg/building | UMEP lidar tutorial; gloBFPr `min_tree_height` | UMEP (QGIS plugin); gloBFPr (R) | nDSM + masks | Lidar-derived; documentation, not a paper [V] | **H** |
| C | Fusion DEM + max(CHM, building) | gloBFPr `get_fused_dsm` | R package (licence not checked) | DEM, CHM (Meta CHM), footprint heights | Documentation only [V] | **H** |
| D | Footprint regularisation (principal directions, 45°, circles) | buildingregulariser 0.2.5 (DPIRD-DMA) | MIT, PyPI, active 2026 | Polygons | No paper; ArcGIS-equivalent [V] | **H** |
| E | Contour regularisation (parallel/orthogonal/collinear) | CGAL Shape_regularization | GPL-3 / commercial | Segments, contours | [V] | M |
| F | LoD1 extrusion: one height per footprint | Convention in HTC-DC Net (RMSE-B), Chen et al. imperfect-labels MHE, gloBFPr | trivial | Footprint + nDSM | Used for labels/eval at 0.5 to 3 m [V] | **H** |
| G | LoD2.2 from points + footprint | roofer (3DBAG / 3DGI) | GPL-3, C++/Python, active Oct 2026 | Point cloud + roofprint | Dutch national ALSO (3DBAG) [V tool; U for DSM-as-points] | M-H |
| H | LoD2 hypothesis-and-selection | City3D, Huang et al. 2022, Remote Sensing | GPL-3 | ALSO points + footprint | Airborne lidar [V] | M |
| I | Plane detection (Efficient RANSAC, region growing) | Schnabel et al. 2007 CGF; Lafarge & Mallet (CGAL) | CGAL GPL-3; Open3D MIT | Points | Generic [V] | M (building block) |
| J | SAT2LoD2 model-driven LoD2 | Gui & Qin 2021, ISPRS J 181 | OSU EULA: non-commercial, no derivatives; Windows exe | Satellite DSM + ortho | Satellite DSM, best regime match [V] | L (licence) |
| K | Polygonisation by frame field learning | Girard et al. CVPR 2021 | BSD-3, last push 2023 | Image (own model) | Aerial (Inria, CrowdAI) [U for numbers] | L-M |
| L | Learned DSM refinement (residual CNN, image-guided) | Stucker & Schindler 2022, ISPRS J (ResDepth) | MIT, old stack (PyTorch 1.9) | Initial DSM + ortho images | Stereo satellite, 0.25 m grid [V] | L-M (needs GT) |
| M | DSM-to-LoD2 cGAN | Bittner et al. 2018, Remote Sensing 10:1926 | no code found | Stereo DSM (0.5 m) | Satellite stereo [V] | L |
| N | Tree tops: LMF variable window | Popescu & Wynne 2004, PE&RS | lidR GPL-3 | CHM | Lidar CHM [V] | **H** |
| O | Crowns: marker watershed / Dalponte 2016 / Silva 2016 | Dalponte & Coomes 2016 MEE; lidR | lidR GPL-3 (EBImage watershed); PyCrown GPL-3 archived | CHM + tree tops | Lidar CHM 0.5 to 1 m [V] | M-H |
| P | RGB crown detection | DeepForest (Weinstein 2019); detectree2 (Ball 2023) | both MIT, active | RGB 0.1 to 0.5 m | Aerial RGB [V licence/venue] | M (alternative seeds) |
| Q | Crown shape / bulb regularisation | none found | n/a | n/a | n/a | **gap** |
| R | Guided filter (+ fast) | He, Sun, Tang TPAMI 2013; He & Sun 2015 | OpenCV ximgproc | Image + probability map | Generic, O(N) [V] | **H** |
| S | Fast bilateral solver | Barron & Poole ECCV 2016 | OpenCV ximgproc | Image + target + confidence | Generic [V] | H |
| T | DenseCRF | Krähenbühl & Koltun NIPS 2011 | pydensecrf MIT | Image + unaries | Widely used in RS segmentation [U] | M (cost at 1e8 px) |
| U | FeatUp | Fu et al. ICLR 2024 | MIT; no DINOv3 | Image + features | Natural images [V] | M |
| V | LoftUp | Huang et al. ICCV 2025 | MIT; DINOv2/CLIP/SigLIP | Image + features | Natural images [V] | M |
| W | JAFAR | Couairon et al. NeurIPS 2025 | Apache-2.0; DINOv3 S/S+/B/L ckpts; any timm backbone | Image + features | Natural images [V] | M-H |
| X | AnyUp | Wimmer et al. ICLR 2026 | CC-BY-4.0; torch.hub | Image + any features | Natural images [V] | M-H |
| Y | NAF | Chambon et al. arXiv 2511.18452 | Apache-2.0; needs NATTEN | Image + any VFM features | Natural images [V] | M-H |
| Z | CascadePSP / SegRefiner | Cheng et al. CVPR 2020; Wang et al. NeurIPS 2023 | MIT / Apache-2.0 | Image + coarse mask | Natural images [V licence] | L-M |
| AA | Edge-aware smoothness loss | Godard et al. CVPR 2017 | n/a (loss) | Training | Driving scenes [V] | L (fine-tune only) |
| AB | Piecewise-planarity prior | Patil et al. P3Depth, CVPR 2022 | repo, licence unspecified | Training | Indoor/KITTI [V] | L |
| AC | Multi-task height + semantics | Srivastava et al. IGARSS 2017; Liu et al. TGRS 2022 (ASSEH) | not checked | Training | Aerial (Vaihingen etc.) [V citation] | L |

## Notes

### Where each published height model stands on masks

- **RS3DAda (SynRS3D, Song et al., NeurIPS 2024):** multi-task (8-class land cover + height), ViT-L
  DPT, MIT [V].
  - Ground-guided pseudo-labels zero the height on predicted ground. Height loss is weighted by
    consistency under augmentation [V].
  - Inference: the height checkpoint takes the image only. The segmentation checkpoint is separate
    [V].
  - The paper notes that nDSMs for several real datasets were made with dsm2dtm, which can introduce
    noise [V].
  - Its 8-class head (bareland, rangeland, developed, road, trees, water, agriculture, buildings)
    could serve as a second opinion to our DINOv3 head [V for classes].
- **Geopose (Christie et al. CVPR 2020; CVPRW 2021):** predicts AGL plus flow (vflow) [V paper/DOI].
  The repo is Apache-2.0 [V] and says nothing about masks [V].
- **HTC-DC Net (Chen et al. TGRS 2023):** no semantic input or loss.
  - The foreground/background split is a 1 m height threshold. Losses are L1, Chamfer, CE and KL.
    There is no edge/smoothness loss [V].
  - Footprints are used only for RMSE-B [V]. The repo has no licence file [V via GitHub API].
- **Imperfect-labels MHE (Chen, Shi, Zhu; arXiv 2506.02534; JSTARS per LMU page [U]):** mid-quality
  labels are uniform per building instance (LoD1); non-building pixels are 0 [V].
  - Vegetation is explicitly out of scope [V]. Code: zhu-xlab/weakim2h, MIT [V].
- **CHMv2 (Brandt et al., arXiv 2603.06382, 2026):** DINOv3 + DPT trained on ALSO CHMs [V].
  - Weights are on HF under `dinov3-license`, gated (manual) [V].
  - The abstract does not mention masks or post-processing [V]. Claims of improved canopy edges/gaps
    come from a secondary summary [U].
  - Underestimation in CHMv1 is reported [U, secondary].

### Building regularisation details

- **LoD1 vs. walls:** sloped walls are a raster blur across footprint edges. LoD1 extrusion inside a
  boundary-refined, regularised footprint makes the walls vertical by construction. The label
  conventions above (F) support this as a representation [V]. Its accuracy effect on our data is
  untested [U].
- **roofer:** inputs are a point cloud plus a roofprint polygon. Outputs are LoD1.2, LoD1.3 and
  LoD2.2 as CityJSONSequence [V].
  - A 0.5 m nDSM grid converted to points gives about 4 pts/m², similar to typical ALSO density [U,
    inference]. Monocular DSM noise on roofs is an untested input regime [U].
  - GPL-3 matters if satmesh is distributed with roofer linked in. Running it as a separate CLI
    process is the usual way around this [U, legal].
- **SAT2LoD2 / Gui & Qin 2021:** decomposes footprints into rectangles and fits parametric roof
  models (hip lines etc.) [V abstract].
  - It is the best regime match (satellite DSM), but the EULA forbids derivatives and commercial use
    [V]. Treat it as a reference design only.
- **Plane fitting per footprint:** iterative Open3D `segment_plane` (RANSAC) is MIT and established
  [V]. Assembling the planes into a watertight roof is the hard part, and that is what roofer/City3D
  solve.

### Tree handling details

- Watershed on a CHM: lidR `watershed()` wraps EBImage::watershed. `dalponte2016()` uses seeds from
  `lmf()` [V source]. scikit-image's watershed is a permissive-licence implementation of the same
  operator [U, not opened].
- CHM median-filter smoothing (3×3) before tree-top detection appears in the lidR book. It does not
  say which option is best [V].
- Bulbous crowns: I found no published post-hoc correction for monocular-predicted crown shape.
  Per-crown operations (e.g. clamp to the crown maximum, fit a parametric crown) would be new
  methods under the task rules, so I do not recommend them here.

### Boundary refinement on 8 m tokens

- 8 m tokens are 16 to 32 px at 0.25 to 0.5 m. The guided filter cost is independent of radius, O(N)
  [V]. A 5 km tile at 0.5 m is 1e8 px per class channel, which is tractable [U, inference].
- JAFAR's DINOv3 checkpoints are for the web-image DINOv3. The satellite DINOv3 variant would need
  retraining (no HR labels needed per the paper) [V for the training claim; U that a sat checkpoint
  is absent].
- AnyUp and NAF claim zero-shot use on unseen backbones [V abstracts]. Neither reports
  remote-sensing results [U].

### Learned refinement / losses (lower priority)

- ResDepth regresses a per-pixel residual to an initial DSM, given ortho images. It was tested on
  0.25 m grid DSMs, with optional building/water/forest masks used for evaluation [V].
- DSM-to-LoD2 trains a cGAN on artificial DSMs rendered from CityGML. That is a route to LoD2-like
  targets if CityGML exists for a training city [V].
- Edge-aware smoothness `|∂d| e^{-|∂I|}` (Godard 2017, eq. 3) [V]. A class-aware variant (masking
  the weight by class boundaries) is a common idea, but I did not verify a primary source for it in
  remote sensing [U].

## Open questions

- Does LoD1/LoD2 extrusion improve building RMSE on E4 scenes, or only appearance? Untested.
- Does roofer accept dense, smooth, non-lidar points without its outlier/plane parameters retuned?
- Is GPL-3 (roofer, CGAL, lidR) acceptable for satmesh distribution?
- Do the AnyUp/NAF zero-shot claims hold for satellite DINOv3 features?
- No method found for crown-shape regularisation or for fusing a building model with a CHM beyond
  max/mask-select. Either accept that or treat it as research.

## Sources (opened unless marked)

- Song et al. 2024, SynRS3D/RS3DAda, NeurIPS: <https://arxiv.org/html/2406.18151v1> ; code
  <https://github.com/JTRNEO/SynRS3D> (MIT)
- Chen, Shi, Xiong, Zhu 2023, HTC-DC Net, IEEE TGRS 61, doi:10.1109/TGRS.2023.3321255 ;
  <https://ar5iv.labs.arxiv.org/html/2309.16486> ; <https://github.com/zhu-xlab/HTC-DC-Net>
- Chen, Shi, Zhu 2025, Enhancing MHE via weak supervision from imperfect labels:
  <https://arxiv.org/html/2506.02534v2> ; <https://github.com/zhu-xlab/weakim2h>
- Christie et al. 2020 CVPR, doi:10.1109/CVPR42600.2020.01452 ; Christie et al. 2021 CVPRW,
  doi:10.1109/CVPRW53098.2021.00127 ; <https://github.com/pubgeo/monocular-geocentric-pose>
- Brandt et al. 2026, CHMv2: <https://arxiv.org/abs/2603.06382> ; weights
  <https://huggingface.co/facebook/dinov3-vitl16-chmv2-dpt-head> (metadata via HF API)
- gloBFPr vignette: <https://stat.ethz.ch/CRAN/web/packages/gloBFPr/vignettes/data_acquisition.html>
- UMEP lidar tutorial:
  <https://umep-docs.readthedocs.io/projects/tutorial/en/latest/Tutorials/LidarProcessing.html>
- buildingregulariser: <https://pypi.org/project/buildingregulariser/> ;
  <https://github.com/DPIRD-DMA/Building-Regulariser>
- CGAL Shape detection / Shape regularization docs (source):
  <https://github.com/CGAL/cgal/tree/master/Shape_detection> , .../Shape_regularization
- Schnabel, Wahl, Klein 2007, Efficient RANSAC, CGF, doi:10.1111/j.1467-8659.2007.01016.x
- Open3D point-cloud tutorial:
  <https://www.open3d.org/docs/release/tutorial/geometry/pointcloud.html> (MIT)
- roofer: <https://github.com/3DBAG/roofer> (GPL-3)
- Huang, Stoter, Peters, Nan 2022, City3D, Remote Sensing 14:2254, doi:10.3390/rs14092254 ;
  <https://github.com/tudelft3d/City3D>
- Gui & Qin 2021, ISPRS J, doi:10.1016/j.isprsjprs.2021.08.025 ;
  <https://arxiv.org/abs/2109.03876> ; <https://github.com/GDAOSU/LOD2BuildingModel> (licence file
  read)
- Girard et al. 2021 CVPR, frame field learning:
  <https://github.com/Lydorn/Polygonization-by-Frame-Field-Learning>
- Stucker & Schindler 2022, ResDepth, ISPRS J, doi:10.1016/j.isprsjprs.2021.11.009 ;
  <https://github.com/prs-eth/ResDepth>
- Bittner et al. 2018, DSM-to-LoD2, Remote Sensing 10:1926, doi:10.3390/rs10121926 ;
  <https://elib.dlr.de/124505>
- Popescu & Wynne 2004, PE&RS 70(5):589, doi:10.14358/PERS.70.5.589 (Crossref)
- Dalponte & Coomes 2016, MEE 7:1236, doi:10.1111/2041-210X.12575 (Crossref + lidR source)
- Khosravipour et al. 2014, pit-free CHM, PE&RS 80(9):863, doi:10.14358/PERS.80.9.863 (Crossref)
- lidR source and book: <https://github.com/r-lidar/lidR> (GPL-3) ;
  <https://r-lidar.github.io/lidRbook/itd.html>
- PyCrown, Zörner et al. 2018: <https://github.com/manaakiwhenua/pycrown>
- Weinstein et al. 2019 DeepForest, Remote Sensing 11:1309, doi:10.3390/rs11111309 ; Ball et al.
  2023 detectree2, RSEC, doi:10.1002/rse2.332 (Crossref + GitHub API licences)
- He, Sun, Tang 2013, Guided image filtering, TPAMI, doi:10.1109/TPAMI.2012.213 ; He & Sun 2015 Fast
  guided filter <https://arxiv.org/abs/1505.00996> ; OpenCV ximgproc edge_filter.hpp
- Barron & Poole 2016, Fast bilateral solver, ECCV, doi:10.1007/978-3-319-46487-9_38
- Krähenbühl & Koltun 2011, DenseCRF, NIPS: <https://arxiv.org/abs/1210.5644> ; pydensecrf (MIT)
- Fu et al. 2024 FeatUp, ICLR: <https://github.com/mhamilton723/FeatUp>
- Huang et al. 2025 LoftUp, ICCV: <https://arxiv.org/abs/2504.14032> ;
  <https://github.com/andrehuang/loftup>
- Couairon et al. 2025 JAFAR, NeurIPS: <https://arxiv.org/abs/2506.11136> ;
  <https://github.com/PaulCouairon/JAFAR>
- Wimmer et al. 2026 AnyUp, ICLR: <https://arxiv.org/abs/2510.12764> ;
  <https://github.com/wimmerth/anyup>
- Chambon et al. 2025 NAF: <https://arxiv.org/abs/2511.18452> ; <https://github.com/valeoai/NAF>
- Cheng et al. 2020 CascadePSP (CVPR), Wang et al. 2023 SegRefiner (NeurIPS): GitHub API licence
  metadata only
- Godard et al. 2017, CVPR: <https://arxiv.org/html/1609.03677v3>
- Patil et al. 2022, P3Depth, CVPR: <https://arxiv.org/abs/2204.02091>
- Srivastava, Volpi, Tuia 2017 IGARSS, doi:10.1109/IGARSS.2017.8128167 ; Liu et al. 2022 ASSEH,
  TGRS, doi:10.1109/TGRS.2022.3177796 (Crossref only)
