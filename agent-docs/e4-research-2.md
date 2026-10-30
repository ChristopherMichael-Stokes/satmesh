---
status: historical
topic: height-refinement
summary: Second survey of learned height from one RGB image on a coarse DEM; recommends a pretrained nDSM network (RS3DAda, Geopose, CHMv2) plus a mass-preserving composition onto the coarse DEM.
answers: Which pretrained models predict height above ground from one RGB image?; Is there released code for a 30 m DSM plus RGB to 1 m DSM method?; What is the licence of RS3DAda, Geopose, CHMv2 and Depth Anything 3?; How do I keep coarse cell means when adding a predicted nDSM?; Was HighResCanopyHeight superseded?
---

# E4 research 2: learned height detail from one RGB image on a coarse DEM

Survey by a research subagent, 2026-10-29 to 30, building on `e4-research.md` and `e4-results.md`.
VERIFIED means the paper, repo or model card was opened; UNOPENED means a search snippet only, and
no numbers are taken from those.

## Conclusions

- No published method with released code does exactly this job: a 30 m DSM plus one 0.3 m RGB
  image in, a 1 m DSM with buildings and trees out. Closest: Rafaeli et al. 2025 (SRTM fed into a
  Depth Anything V2 / PromptDA-style network on NAIP imagery, no code), Elevate and Real-GDSR (5 m
  input, no code).
- The workable answer combines two published parts:
  1. A pretrained monocular nDSM network (height above ground, buildings and trees) run on the
     Esri tile.
  2. Composition onto the coarse DEM with an exact consistency step, so every coarse cell keeps
     its mean (the adjustment step of DADA, Metzger 2023; scale and shift fitting to a prior as in
     Song 2025 and Prior2DSM 2026).
  These networks are trained to output about 0 on flat ground, which targets PixTransform's
  texture copying (0.30 to 0.74 m/m slope on flat ground in E4).
- First trial: RS3DAda height model (Song et al., NeurIPS 2024). DINOv2 ViT-L with a DPT head,
  nDSM in metres, MIT code and MIT weights, no gating. Run zero-shot, then fine-tune on EA lidar
  nDSM with Esri imagery; compose mass-preservingly onto kriged or DTM bases.
- Runner-up: the Overhead Geopose Challenge first-place model (selim_sef; MIT code; weights on
  IEEE DataPort). Trained on WorldView-2/3 off-nadir satellite images (US3D: Jacksonville, Omaha,
  Atlanta, San Fernando, Argentina), the sensor family behind Esri / Vantor imagery. Predicts
  height above ground plus a lean vector field; Christie et al. 2021 test it on orthorectified
  images.
- Trees at no compute: CHMv2 (Meta / WRI, March 2026), a global canopy height map from Vantor
  imagery, about 1.2 m pixels, covers Yemen. Buildings are trained to 0, so trees only.
- Ranked low: plain Depth Anything V2/V3 or Marigold with a per-tile scale fit (Song et al. 2025
  measured large errors and heavy shadow dependence, below), and PixTransform with another guide.
- Expected outcome (subagent's estimate, not measured): at x30, buildings and trees appear as
  discrete blocks with flat ground between, with RMSE near kriging (2.08 m at Ferrybridge),
  perhaps better after fine-tuning. At x5, little or no RMSE gain over kriging (0.87 m): zero-shot
  nDSM errors elsewhere are 3 to 7 m RMSE, and the consistency step limits the damage.
- Corrections to `e4-research.md`:
  - HighResCanopyHeight (Tolan 2024) is superseded by CHMv2: on SatLidar v2, MAE 4.3 to 3.0 m, R²
    0.53 to 0.86.
  - PromptDA-Small weights are Apache-2.0 (was "unstated").
  - Depth Anything 3: Small, Base, Metric-Large and Mono-Large are Apache-2.0; Large and Giant are
    CC BY-NC 4.0.
  - Rafaeli 2507.09681 v3 (April 2026) now has tables: vegetated site MAE 4.645 against SRTM
    5.661 m; bare site 2.132 against 2.217 m. Still no code.

## Comparison

| Method | Input | Output | Coarse-DEM conditioning | Reported accuracy (dataset, GSD) | Licence code / weights | GPU, runtime | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RS3DAda (Song, Chen, Xuan, Xia, Yokoya; NeurIPS 2024) | RGB, 0.05 to 1 m | nDSM (m) | None; added by composition | Mean of 7 real sets (DFC18, DFC19 JAX/OMA, GeoNRW rural/urban, OGC ARG/ATL): MAE 2.534, RMSE 4.122 m (source-only 5.040) | MIT / MIT (HF JTRNEO/RS3DAda, Zenodo 13940407); SynRS3D training data CC BY-NC per a third-party card (UNOPENED at source) | ViT-L, 366.5M params; memory not stated; env Python 3.8, PyTorch 2.2.1 | VERIFIED (repo, Zenodo, HF card) |
| RS3DAda zero-shot on new cities (Song, Chen, Yokoya; ISPRS JPRS, arXiv 2505.06905) | RGB 0.5 m | nDSM | Corrected with ICESat-2 plus FABDEM | Mean of 6 regions (Tokyo, Paris, Saint-Omer, São Paulo): MAE 5.214 to 3.600, RMSE 9.218 to 7.064 after BitFit; shadowless test MAE 6.96 m | Paper CC BY-NC-SA; no code found | A100; calibration 0.22 to 1.52 min/km² | VERIFIED |
| Depth Anything V2 + linear fit (same paper) | RGB | Relative depth to height | ICESat-2 linear fit, then RF residual | MAE 5.692 to 4.321, RMSE 9.119 to 7.717; shadowless test MAE 11.98 m | Apache (Small) | | VERIFIED |
| Geopose (Christie, Foster, Hagstrom, Hager, Brown; CVPRW 2021, arXiv 2105.08229) | WorldView-2/3 RGB, off-nadir, also orthorectified | Height above ground (m) plus lean vector field | None | DFC19 custom test MAE 2.52, RMSE 3.89 m (IM2HEIGHT 3.62 / 5.40); RMSE by city JAX 3.33, OMA 4.15, ATL 4.86, ARG 3.00 m | Baseline Apache-2.0 (pubgeo/monocular-geocentric-pose); winners MIT (drivendataorg/overhead-geopose-challenge); weights on IEEE DataPort | Not stated | VERIFIED |
| Geopose first place (selim_sef) | Same | Same | None | Challenge private score 0.902 (R²-type) | MIT / DataPort | EfficientNetV2-L UNet | VERIFIED (repo) |
| CHMv2 (Brandt, Yi, Tolan et al.; arXiv 2603.06382, submitted to Sci. Data) | Vantor/Maxar Vivid2 RGB, about 0.6 m | Canopy height only; buildings trained to 0 | None | SatLidar v2 MAE 3.0 m, R² 0.86; NAIP-3DEP MAE 1.4 m, R² 0.93; GEDI RMSE 6.4 m; worse at sun elevation below 45° (ICESat-2 R² 0.42) | Model under the DINOv3 License (gated; bars military/warfare use and trade-control targets); global product CC BY 4.0 per the AWS registry but the DINOv3 licence per the paper (conflict) | ViT-L, about 0.3B params | VERIFIED |
| DINOv3 Sat ViT-L + DPT (Siméoni et al. 2025, arXiv 2508.10104 sec. 8.2) | Satellite RGB | Canopy height | None | SatLidar1M val MAE 2.2, test 3.2; Open-Canopy 2.07 (Tolan 2.42) | DINOv3 License (gated) | | VERIFIED |
| Rafaeli, Svoray, Nahlieli 2025 (arXiv 2507.09681 v3) | NAIP 0.6 m + SRTM 30 m | DEM (DSM or DTM not stated) | Yes: SRTM through a shallow CNN, zero-initialised conv added to DPT features | DEM-OPT-Depth RMSE 5.535 m against bicubic 14.891 | No code | RTX A4000, about 150 km²/h | VERIFIED |
| Prior2DSM (Rafaeli 2026, arXiv 2604.02009) | RGB + partial DSM | Metric DSM | Yes: test-time LoRA plus scale/shift MLP | Up to 46 % RMSE cut against a linear MDE fit (abstract) | No code | | VERIFIED (abstract) |
| PromptDA-Small (Lin et al. 2025) | RGB + low-res metric depth prompt | Metric depth | Yes, by design (indoor lidar prompt) | No remote-sensing results | Apache / Apache | 25.1M params | VERIFIED |
| Depth Anything 3 | RGB | Relative or metric depth | No | No nadir results | Small, Base, Metric-L, Mono-L Apache; Large, Giant CC BY-NC | | VERIFIED (repo table) |
| HTC-DC Net (Chen, Shi, Xiong, Zhu; TGRS 2023) | RGB, 0.09 to 3 m | nDSM | No | Tables not extractable | No licence file; no weights | | VERIFIED (repo); numbers unread |
| Weak supervision from imperfect labels (Chen, Shi, Zhu; arXiv 2506.02534) | RGB | nDSM | No | Up to 22.94 % RMSE cut on DFC23 | No code found | | VERIFIED (abstract) |
| Depth2Elevation (Hong et al.; TGRS 2025) | RGB | Height | No | "up to 42 %" on GAMUS | No code found | | UNOPENED |
| Training-free DA-V2 building heights (Chen et al.; ISPRS Archives 2025) | Google 0.5 m RGB | Relative building height | Subtracts a morphological DEM | R² 0.73, Wuhan 20 km² | No code | | VERIFIED (abstract) |
| Depth Any Canopy (Cambrin, Corley, Garza; ECCVW 2024) | RGB | Canopy height | No | No numbers on the repo page | Apache / Apache | 24.8M / 97.5M params | VERIFIED (repo) |
| AltiMap (RS3DAda fine-tuned on GAMUS; hackathon) | 0.33 m aerial | nDSM | No | GAMUS RMSE 4.55 to 5.02 m; zero-shot RS3DAda 7.25 m | MIT (v1); v2 treated as non-commercial | | VERIFIED card, self-reported; anecdotal |
| Google Open Buildings 2.5D | Sentinel-2 | Building height at about 4 m | | MAE 1.5 m (North America, Europe, Japan only) | CC BY 4.0 / ODbL | | VERIFIED; does not cover Yemen |

## Ranked shortlist

| Rank | Candidate | Expected gain x30 | Expected gain x5 | Risks |
| --- | --- | --- | --- | --- |
| 1 | RS3DAda nDSM, zero-shot then EA fine-tune, mass-preserving composition | Large by eye (discrete roofs and trees, flat ground); RMSE about kriging, perhaps 10 to 30 % better after fine-tuning (estimate) | Little RMSE gain; better edges | Shadow dependence (shadowless MAE 6.96 m); roof displacement from lean, so apply the lean correction first; domain gap from synthetic and US/EU training to Yemeni mud-brick and tower houses; Python 3.8 env to port to 3.13 |
| 2 | Geopose first-place model (height plus lean field) | Similar; possibly better on the Vantor off-nadir look | Similar | DataPort access unverified; US-only training cities; a CNN backbone may generalise less than DINO features (subagent's judgement) |
| 3 | CHMv2 product tiles as the tree layer | Trees only, no compute | Trees only | Licence conflict; DINOv3 military clause; sun elevation below 45° degrades it; about 1.2 m grid |
| 4 | Rafaeli-style coarse-DSM prompt (PromptDA-Small, Apache) fine-tuned on EA DSM | Highest ceiling for GLO-30 conditioning | Moderate | No published code; training needed; one paper; buildings not evaluated |
| 5 | Depth Anything V2/V3 Small + per-tile scale/shift fit to the coarse DEM | Weak | Weak | RMSE 9.1 m zero-shot; shadowless MAE 11.98 m |
| 6 | PixTransform with a deep-feature guide | Unknown | Unknown | Nothing published for DSM; inherits texture copying |

## First-trial protocol (proposed)

Reuses the E4 scoring.

1. Sites and grid: Ferrybridge and Upper Aire, the same four 270 m tiles, plus one dense-urban EA
   site for building statistics (the greenness cover split was unreliable).
2. Guide: Esri z19 with the store's lean correction, on the 0.5 m and 1 m grids; once without the
   lean correction to measure what lean costs.
3. nDSM prediction: RS3DAda `infer_height.py` with and without `--use_tta`. Score against lidar
   nDSM (EA DSM minus DTM): RMSE, MedAE, NMAD by cover, and slope on flat ground at guide edges
   against the lidar's 0.033 m/m.
4. Composition at each factor f in {2, 5, 30}, with N the predicted nDSM and S the coarse source:
   - (A) Anomaly: Z = kriged(S) + (N - upsample(blockmean_f(N))), then an additive per-cell
     correction so blockmean_f(Z) = S exactly (DADA-style adjustment).
   - (B) DTM base: Z = kriged(blockmean_f(EA DTM)) + N, a proxy for FABDEM plus nDSM.
   - (C) Scaled: as (B), with a per-coarse-cell gain on N fitted so the cell mean matches the
     degraded DSM; a proxy for the GLO-30 case (Song 2025 / Prior2DSM style).
5. Scores: RMSE, MedAE, NMAD, edge slope at flat guide edges, coarse-cell residual, and errors
   split by shadow (dark-pixel mask), against the existing bilinear, kriging and PixTransform rows.
6. Fine-tune: BitFit or LoRA plus the DPT head on EA tiles from other towns, split by geography
   (Song 2025 found BitFit best for RS3DAda); expected to fit 12 GB with a frozen encoder (not
   measured). Repeat steps 3 to 5.
7. Runner-up: geopose weights, steps 3 to 5. CHMv2 tiles: score tree pixels only.
8. Renders by eye at x30 and x5: (A), (B), (C), kriging and PixTransform, views fixed before
   results.
9. Yemen dry run on one Sana'a or Aden tile: FABDEM plus N, and GLO-30 with scaled N; checked by
   eye against ICESat-2 ATL08 points where available.
10. Pass gate: flat-ground edge slope at most twice the lidar's, x30 RMSE no worse than kriging,
    and the owner prefers it by eye.

## Open questions

- Whether Esri World Imagery terms permit using tiles to train or fine-tune models: not checked.
  The EA Vertical Aerial Photography record lists "No Licence Provided" with "All rights reserved"
  wording (VERIFIED), so it is not a clean alternative.
- The DINOv3 licence bars military/warfare use and trade-control targets: whether the Gazebo and
  virtual-camera end use falls under it (matters for CHMv2 and DINOv3-Sat only), and which licence
  governs the CHMv2 product (CC BY 4.0 on AWS, DINOv3 in the paper).
- Whether the IEEE DataPort geopose weights are free to download, and their licence.
- RS3DAda GPU memory and runtime on a 540 px tile, and whether it runs on Python 3.13 and current
  PyTorch.
- Whether GLO-30's partial building and tree response (radar DSM) suits recipe (A) or (C); only
  testable on real GLO-30 over EA lidar.
- Domain gap to Yemen (flat-roofed mud-brick towers, few trees, desert shadows); no public lidar
  nDSM from the Arabian Peninsula was found.
- Song 2025's random-forest correction from ICESat-2 plus FABDEM (CPU, 0.22 min/km²) fits Yemen,
  but no code was found.

## Sources

- RS3DAda / SynRS3D: <https://github.com/JTRNEO/SynRS3D>, <https://zenodo.org/records/13940407>,
  <https://huggingface.co/JTRNEO/RS3DAda>, <https://arxiv.org/abs/2406.18151>
- Sparse lidar correction of MHE/MDE (Song, Chen, Yokoya): <https://arxiv.org/abs/2505.06905>
- Geopose: <https://arxiv.org/abs/2105.08229>, <https://github.com/pubgeo/monocular-geocentric-pose>,
  <https://github.com/drivendataorg/overhead-geopose-challenge>
- CHMv2: <https://arxiv.org/abs/2603.06382>,
  <https://huggingface.co/facebook/dinov3-vitl16-chmv2-dpt-head>,
  <https://registry.opendata.aws/dataforgood-fb-forestsv2>
- DINOv3: <https://arxiv.org/abs/2508.10104>,
  <https://github.com/facebookresearch/dinov3/blob/main/LICENSE.md>
- Rafaeli 2025: <https://arxiv.org/abs/2507.09681>. Prior2DSM: <https://arxiv.org/abs/2604.02009>
- PromptDA: <https://github.com/DepthAnything/PromptDA>,
  <https://huggingface.co/depth-anything/prompt-depth-anything-vits>
- Depth Anything 3: <https://github.com/ByteDance-Seed/Depth-Anything-3>
- HTC-DC Net: <https://elib.dlr.de/201223/1/HTC-DC_Net_Monocular_Height_Estimation_From_Single_Remote_Sensing_Images.pdf>,
  <https://github.com/zhu-xlab/HTC-DC-Net>
- Imperfect-label MHE: <https://arxiv.org/abs/2506.02534>
- Training-free DA-V2 building heights:
  <https://isprs-archives.copernicus.org/articles/XLVIII-1-W5-2025/7/2025/>
- Depth Any Canopy: <https://github.com/DarthReca/depth-any-canopy>
- AltiMap: <https://huggingface.co/Dilavesh/altimap-height>
- Open Buildings 2.5D: <https://sites.research.google/gr/open-buildings/temporal>
- EA Vertical Aerial Photography: <https://ckan.publishing.service.gov.uk/dataset/vertical-aerial-photography>
- Depth2Elevation (UNOPENED): <https://openrepository.aut.ac.nz/items/4d5713c5-f7ea-4a08-9a73-4c2555e29743>
