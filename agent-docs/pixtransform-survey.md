---
status: historical
topic: height-refinement
summary: Survey of guided elevation super-resolution since 2019; MMSR (ECCV 2022) builds on the PixTransform code and beats it at x4 and x8 but is untested at x30.
answers: What has improved on PixTransform since 2019?; What is MMSR and how does it differ from PixTransform?; Which supervised guided DEM upsamplers exist and what do they need?; Which successor changes are established in the literature?; Which methods have code available?
---

# PixTransform successors: survey of guided elevation super-resolution since 2019

Date 2026-10-30. Research report, not a plan. Every source tagged VERIFIED was opened during this
survey (abstract, HTML or repo page); UNVERIFIED means seen only in search snippets or a third-party
page. Nothing algorithmic here is new: each change listed for a PixTransform successor is a
component taken from a cited paper. Prior project surveys (`e4-research.md`, `e4-research-2.md`)
are not re-done; where they cover a method, this report points to them.

## Conclusions

- **Things have improved since 2019, and the closest successor builds directly on the PixTransform
  code.** MMSR (Dong, Yokoya, Wang, Uezato; ECCV 2022) is per-image and self-supervised, needs no
  external data, and its README says the code "was built on the repository of P2P (ICCV2019)". It
  adds what PixTransform lacks: a 3x3 convolutional guide branch with residual blocks, so it sees
  spatial context; mutual modulation (cross-domain adaptive filters, 5x5 and 3x3 for DEM) between
  the source and the guide; and a cycle-consistency L1 loss on the average-pooled output. On 54
  visible-DEM pairs from the GRSS DFC 2019 it reports RMSE x4 / x8 of 0.73 / 1.02, against
  P2P (PixTransform) 1.57 / 1.70, and it beats the supervised DKN, FDKN and FDSR at x8 (1.39 / 1.25
  / 1.55). It fits one DEM pair in 49 s against P2P's 131 s. It was tested only at x4 and x8, not
  x16 or x30. VERIFIED (paper and repo).
- **The defects the owner saw are ones the PixTransform paper itself names.** The paper reports
  "spurious texture" transfer at x32 with textured guides, and hallucinated depth where guide
  colours are similar but depths differ. It suggests stronger, factor-dependent regularisation of
  the intensity branch and an output total-variation (TV) term, and says neither was tested. Its
  1x1-only network, fixed 32,000 steps, hand-set lambdas and lack of any optimiser study ("left
  for future work") are all stated in the paper. VERIFIED.
- **Grey roofs next to grey pavement need a feature other than colour.** No per-pixel colour
  mapping can separate them. The published remedies are spatial context (MMSR, DADA, graph
  regularisation, CNNs) and semantic guide features. The only measured gain from foundation-model
  features in guided depth SR that this survey found is NAIMA (2026 preprint): frozen DINOv2 ViT-S
  tokens injected by cross-attention with a zero-initialised gate cut x8 RMSE by about 3 to 5 %
  across five indoor datasets. Plain addition instead of cross-attention did worse than leaving the
  semantics out. VERIFIED. No paper tests DINO features as extra input channels to a per-image
  PixTransform-style fit (that does not exist in the literature).
- **The cheapest first trial is MMSR as published, then MMSR plus the source-consistency
  adjustment.** Both run on one 12 GB GPU per tile with no training data. The adjustment is DADA's
  step (Metzger et al., CVPR 2023), already planned as M-A. The second step is the same
  architecture with DINOv2/v3 features (brought to full resolution with AnyUp) as extra guide
  channels, scored against MMSR alone.
- **Supervised options remain those already surveyed**: DADA (MIT code, tested to x32), graph
  regularisation (de Lutio et al., CVPR 2022, MIT code, hard low-resolution constraint), Real-GDSR
  and Elevate (no code), and PromptDA-style coarse-DSM prompting (Rafaeli). The new findings here:
  - Elevate fine-tunes Stable Diffusion 2.1 or 3 for 250k iterations on about 10k patches. That is
    unlikely to fit a cheap 12 GB trial.
  - Marigold-DC (Apache-2.0) and AdaDS (NeurIPS 2026, no code found) are zero-shot,
    test-time-guided diffusion depth methods. Neither has been evaluated on aerial DSMs.
- **No published method covers our hardest case**: GLO-30 (30 m radar) to 1 m with buildings
  formed. The nearest is Rafaeli et al. (SRTM 30 m plus NAIP to 0.3 m): MAE under 5 m against
  lidar and at most 18 % better than SRTM. This should limit expectations for Yemen. VERIFIED
  (abstract).
- **Evaluation**: the literature gives three ready tools against registration, lean and date
  effects.
  - Nuth and Kääb (2011) DEM co-registration, implemented in xDEM, estimates and removes the
    horizontal and vertical shift before differencing.
  - A best-of-shifts score with bias removal, as in the PROBA-V cPSNR (shifts within +-3 px).
  - Change masking: Elevate reports about 5 % of test data affected by DSM/RGB date differences.
    It also scores slope error (MAES), NMAD and MS-SSIM alongside RMSE.
  - For training under misalignment there is the CoBi loss (Zhang et al., CVPR 2019) and CMSR's
    learned guide deformation (Shacht et al., CVPR 2021).

## Recommended first experiment set (ordered by cost)

| # | Experiment | Cost | What it tests |
|---|---|---|---|
| X1 | MMSR (palmdong/MMSR) as published on the 540 m boxes, x2/x5/x10/x30, against the PixTransform port, bicubic and kriging. Same pooling degradation as the port | Minutes per tile, no training data | Whether spatial context plus mutual modulation fixes the verge, dimple and grey-on-grey defects. The paper's 5x5/3x3 filter neighbourhoods were tuned for x4 and x8 and may be too small at x30 (untested) |
| X2 | X1 plus the additive source-consistency adjustment (DADA step = M-A) | Negligible | Exact agreement with the coarse cell means; isolates the error the network adds within each cell |
| X3 | PixTransform-procedure ablations on the existing port, each from a cited paper: (a) output TV term (suggested, untested, in de Lutio 2019); (b) Fourier features on (x, y) (Tancik 2020) or a multiresolution hash grid (Instant-NGP, Müller 2022); (c) random-jitter multi-view consistency and a TV term, as in FeatUp's implicit per-image fit (2,000 steps, NAdam, lr 1e-3, TV weight 0.05); (d) early stopping on the running variance of the output (Wang et al., TMLR 2023) instead of a fixed 32k steps; (e) an ensemble of seeds, median-combined | Minutes | Which part of the defect is the procedure rather than the 1x1 architecture. The literature does not predict that (b) helps: Fourier/hash encodings raise the coordinate branch's frequency, and the PixTransform paper says the coordinate branch is what stops pure colour mapping |
| X4 | Best of X1/X3 with extra guide channels: DINOv2 or DINOv3 patch features, PCA to 16 to 128 channels (FeatUp used the top 128 components), upsampled to full resolution with AnyUp (CC-BY-4.0, torch.hub) or JAFAR | One encoder pass plus upsampler per tile | Whether semantics separate grey roof from grey pavement. Evidence is supervised and indoor only (NAIMA); for a per-image fit it is untested |
| X5 | Scoring protocol: Nuth-Kääb shift removal per tile (xDEM), then RMSE, MedAE, NMAD, MAES and a best-of-+-k-pixel RMSE. Report separately on building, vegetation and ground masks, excluding changed areas | Small | Removes registration and lean credit or penalty from the comparison |
| X6 | Supervised: DADA and graph regularisation retrained on EA lidar plus Esri, geographic split, x4 to x32 | Hours of GPU training | Ceiling of a trained model with spatial context. Also a pretrained initialisation for per-tile fine-tuning under the low-resolution loss (the "hybrid" in the note; no DSM paper found that does exactly this) |

## Comparison table

Columns: training need; spatial context; evidence on elevation; code and licence; fit for us (cheap
trial, 12 GB, x2 to x30); change it implies for a PixTransform successor. Status refers to the
claims in the row.

| Method (paper) | Training | Context | Elevation evidence | Code / licence | Fit | Successor change | Status |
|---|---|---|---|---|---|---|---|
| PixTransform (de Lutio et al., ICCV 2019) | Per image | None (1x1) | Swiss vegetation height from Sentinel-2, x4 to x32 | prs-eth/PixTransform | Baseline (ported) | n/a | VERIFIED |
| MMSR (Dong et al., ECCV 2022) | Per image, self-supervised | 3x3 guide branch, residual blocks, adaptive filters | DFC2019 DEM x8 RMSE 1.02 vs P2P 1.70 | palmdong/MMSR, built on P2P code; licence not shown on page | Best cheap trial; x4/x8 only tested | Replace 1x1 guide branch with 3x3 conv + residual blocks; source-to-guide and guide-to-source modulation; cycle L1 with average pooling; Adam lr 2e-3, 1,000 epochs, no augmentation | VERIFIED |
| CMSR (Shacht et al., CVPR 2021) | Per image | 3x3 CNNs (8 layers) | None (thermal, NIR, Middlebury depth) | None found ("will be published") | Idea only | Learned guide deformation (affine STN, then CPAB, then TPS) trained by the SR loss for weak alignment; residual over bicubic; LR decayed on loss plateau; geometric self-ensemble; back-projection | VERIFIED |
| Guided Deep Decoder (Uezato et al., ECCV 2020) | Per image | Encoder-decoder over the guide (multi-scale) | None (pansharpening, HS-RGB) | tuezato/guided-deep-decoder | Possible; untested on DEM | U-Net guide features gating a deep-decoder output (DIP-style) | UNVERIFIED (search listing only) |
| MCPN (Czerkawski et al., J. Imaging 10(3):69, 2024) | Per image (DIP-style) | Convolutional (shared core plus per-modality heads) | **Not a DSM method.** Sentinel-2 B9 (60 m) super-resolution guided by 10 m RGB; Sentinel-2 inpainting with S1 or historical S2. Beats PixTransform SSIM at x4 (0.847 vs 0.815) | No code link seen | Low priority | Shared core with a head per modality (RGB and height), both reconstructed; stopping by patch consistency or fixed 4,000 steps | VERIFIED (PMC full text) |
| FeatUp implicit (Fu et al., ICLR 2024) | Per image | Coordinate MLP on Fourier-encoded (x, y) and colour | None (features) | Repo via aka.ms/featup; licence not checked | Recipe source | Fourier colour features; jitter multi-view loss with learned per-pixel uncertainty; learned (attention) downsampler; TV 0.05; 2,000 steps | VERIFIED |
| Graph regularisation (de Lutio et al., CVPR 2022) | Supervised (NYU etc.), checkpoints given | Learned affinity graph from deep features | None in RS | prs-eth/graph-super-resolution, MIT | Retrain on EA; moderate | Differentiable optimisation layer with the LR source as a hard constraint | VERIFIED |
| DADA (Metzger et al., CVPR 2023) | Supervised | CNN plus guided anisotropic diffusion | Not in paper; Real-GDSR reports it on real 5 m DSM | prs-eth/Diffusion-Super-Resolution, MIT | Retrain; x32 tested | Adjustment step for exact source consistency; diffusion for edges | VERIFIED |
| DKN / FDKN (Kim, Ponce, Ham, IJCV 2021) | Supervised | Learned sparse deformable kernels | MMSR's DEM table (x8 RMSE 1.39 / 1.25) | Project page cvlab.yonsei.ac.kr | Baseline only | Per-pixel learned kernel over neighbours | UNVERIFIED (search listing only; arXiv 1910.08373) |
| JIIF (Tang et al., ACM MM 2021) | Supervised | Local latent codes, graph attention, implicit query | None in RS | git.io/JC2sU | Arbitrary-scale option | Implicit (coordinate) decoder over local joint codes | VERIFIED |
| Real-GDSR (Panangian, Bittner, ISPRS Annals 2024) | Supervised, real 5 m to 0.5 m | Residual CNN plus edge-enhancing diffusion | Cartosat-1 to swisstopo; see e4-research.md | None found | Recipe | Predict height residual over upsampled DSM; train on real coarse DSM, not synthetic | VERIFIED |
| Elevate (Nicolicioiu et al., arXiv 2609.11886, 2026) | Supervised; SD 2.1 / SD 3, 10k patches, 250k iterations | Latent diffusion | Winterthur RMSE: bicubic 5.33, Real-GDSR 3.13, Elevate 2.56 to 2.64 m | None found | Too heavy for a cheap trial | Concatenate coarse-DSM latent and image latent; normalise heights by LR-patch scale and shift; uncertainty output | VERIFIED |
| NAIMA (Nasir, Liu, Mian, arXiv 2604.04407, 2026) | Supervised (NYU only) | CNN plus DINOv2 cross-attention | Indoor only | tayyabnasir22/NAIMA-GDSR | Conditioning recipe | Frozen DINOv2 tokens (blocks 2/5/8/11) as keys and values, zero-init gate; gradient loss | VERIFIED |
| WAVE (Nasir et al., arXiv 2608.25302, 2026) | Supervised | Wavelet coarse-to-fine | Indoor | None on page | Low | Wavelet split of guide to control texture before fusion | VERIFIED (abstract) |
| PromptDA (Lin et al., CVPR 2025) | Supervised fine-tune of Depth Anything | ViT + DPT, multi-scale prompt fusion | Rafaeli et al. use the idea with SRTM (no code) | DepthAnything/PromptDA, Apache-2.0 code; Small 25.1M params | Already M4 | Coarse-DSM prompt fused at several decoder scales; edge-aware loss | VERIFIED |
| Marigold-DC (Viola et al., ICCV 2025) | None (test-time guidance) | Latent diffusion | None in RS | prs-eth/Marigold-DC, Apache-2.0 | Possible zero-shot probe; designed for sparse points | Optimise during denoising to match observations | VERIFIED |
| AdaDS (Wang et al., arXiv 2602.09510, NeurIPS 2026) | Zero-shot | Pretrained diffusion | None in RS | None found | Watch | Noise the LR prompt to an adaptive timestep, then denoise | VERIFIED (abstract) |
| AnyUp (Wimmer et al., ICLR 2026) / JAFAR (Couairon et al. 2025) / LoftUp (Huang et al., ICCV 2025) / FeatUp JBU | Pretrained once (ImageNet etc.) | Attention guided by image | None; upsample encoder features, not depth | AnyUp CC-BY-4.0 torch.hub; JAFAR, LoftUp on GitHub | Use to make full-resolution DINO guide channels | Provides the semantic guide channels for X4; using them to upsample height itself is untested | VERIFIED |
| Prior2DSM (Rafaeli et al., arXiv 2604.02009) | Test-time LoRA plus scale/shift MLP | ViT | DSM completion (holes), not coarse-to-fine | None found | Already in e4-research-2 | Test-time adaptation of a pretrained model under a metric prior | VERIFIED |

## Notes

### A. PixTransform-specific improvements

- Spatial context. The architectures with measured gains over PixTransform in the same per-image
  setting are MMSR (convolutional guide branch plus modulation; DEM evidence) and MCPN (DIP-style
  convolutional parameterisation; Sentinel-2 band SR, SSIM only). CMSR, a per-image 3x3 CNN, is
  compared with PixTransform only qualitatively. VERIFIED.
- Coordinate encodings (INR, Fourier, hash). Fourier features overcome the MLP spectral bias in low
  dimensions (Tancik et al. 2020). Instant-NGP's multiresolution hash grid lets small MLPs fit fast
  (Müller et al., SIGGRAPH 2022). FeatUp's implicit variant applies a Fourier coordinate and colour
  MLP to per-image guided feature upsampling. VERIFIED. No paper was found applying hash
  encodings to per-image guided depth or DEM SR. Note the risk: more coordinate frequency lets the
  fit reproduce each coarse cell with spatial wiggles. PixTransform itself regularises the
  coordinate branch to avoid exactly that.
- Losses and regularisers. In the literature found:
  - Output TV: suggested by de Lutio 2019; FeatUp uses TV 0.05.
  - Gradient loss: NAIMA ablation, removal hurts.
  - Edge-aware depth loss: PromptDA.
  - Cycle consistency on the pooled output: MMSR, which is equivalent to PixTransform's data term
    plus guide reconstruction.
  - Hard consistency: graph regularisation's constraint layer and DADA's adjustment.
  - Learned per-pixel uncertainty in the reconstruction loss: FeatUp.
  - Misalignment-robust CoBi loss: Zhang et al. 2019.
  All VERIFIED at abstract or method level.
- Optimisation and training procedure.
  - PixTransform: fixed 32k steps, Adam 1e-3, batch 32 cells.
  - MMSR: 1,000 epochs, lr 2e-3 decayed 0.9998 per 5 epochs.
  - CMSR: lr 1e-4 to 1e-6 driven by the loss slope, stop on plateau, geometric self-ensemble,
    iterative back-projection.
  - MCPN: stopping by fixed steps, known-region RMSE or patch consistency.
  - DIP early stopping by running variance: Wang et al., TMLR 2023 (arXiv 2112.06074; VERIFIED
    from search listing and TMLR anthology entry, abstract not opened).
  No paper studies ensembling or initialisation for PixTransform specifically (not found).
  Multi-resolution or coarse-to-fine training appears in WAVE (wavelet, supervised) and CMSR
  (coarse-to-fine deformation), not as a per-image PixTransform schedule.
- Follow-ups that cite or build on PixTransform: graph regularisation (same group), MMSR (code
  base), MCPN (baseline), CMSR (qualitative comparison). A GTFormer remote-sensing paper reportedly
  uses PixTransform as a baseline (UNVERIFIED, search snippet only).

### B. Supervised and pretrained options

- These need EA lidar plus Esri pairs split by geography. DADA, graph regularisation, JIIF and DKN
  have public code; Real-GDSR and Elevate have none. Real-GDSR's point is that training on
  synthetic downsampling transfers badly to real coarse DSMs (VERIFIED). This is the GLO-30 domain
  gap. The block-averaged EA lidar used here is synthetic in that sense.
- Foundation-model routes: PromptDA (prompt fusion), Marigold-DC and AdaDS (test-time diffusion
  guidance), Prior2DSM (test-time LoRA). Only Rafaeli et al. and Prior2DSM have remote-sensing
  evidence, and neither released code.
- The feature upsamplers (AnyUp, JAFAR, LoftUp, FeatUp) upsample encoder features. They were
  evaluated on segmentation and depth probes on NYUv2/COCO etc., none on remote sensing (AnyUp
  VERIFIED). Their role here is producing guide channels, not height.

### C. Feeding supplementary data

- Mechanisms with published evidence:
  - Cross-attention with a zero-init gate over DINOv2 tokens (NAIMA). This beat element-wise
    addition, which was worse than no semantics.
  - Zero-initialised convolution branches (ControlNet, Zhang et al. 2023; abstract VERIFIED). The
    Rafaeli SRTM injection is described in e4-research-2.md as of this kind.
  - Multi-scale prompt fusion in the decoder (PromptDA).
  - Latent concatenation (Elevate).
  - Spatial Feature Transform modulation (JAFAR).
  - Mutual modulation by adaptive filters (MMSR).
- Extra channels: no paper found that measures gains from building footprints, shadow masks,
  lean/off-nadir cues, multi-date imagery or a DTM as extra guide channels for guided DSM SR (not
  found, not shown not to exist). Elevate notes construction-site date changes and that its model
  trusts elevated DSM regions over RGB-only structures there.

### D. Evaluation against registration, lean and date effects

- DEM co-registration before differencing: Nuth and Kääb 2011 (The Cryosphere 5:271-290); xDEM
  implements it alongside ICP, LZD and CPD. VERIFIED.
- Shift-tolerant scoring: PROBA-V cPSNR takes the best of 7x7 offsets (+-3 px) after removing the
  mean brightness difference (ESA Kelvins scoring page). VERIFIED. An elevation analogue is a
  best-of-shifts RMSE after vertical bias removal. That is an adaptation, so report it alongside
  the plain RMSE, not instead of it.
- Metric set used in the DSM SR literature: RMSE, MedAE, NMAD, MAES (mean absolute slope error) and
  MS-SSIM (Elevate); Real-GDSR reports RMSE and NMAD. VERIFIED.
- Lean: CMSR learns a global-to-local deformation of the guide (one deformation for the whole
  image; per-object handling is listed as future work). Geopose (in e4-research-2.md) predicts a
  lean field. No guided-DSM-SR paper found that corrects building lean before scoring.

## External note: claim-by-claim check

| Claim in pixtransform-external-note.md | Literature |
|---|---|
| PixTransform is 1x1 convolutions with no spatial receptive field; a larger guide adds observations, not context | Supported. The paper states all kernels are 1x1 (de Lutio 2019). The second half follows from that; no paper tests it directly |
| Supervised dual-encoder CNN with U-Net decoder predicting a residual over the upsampled coarse DSM | Supported in parts. Residual height prediction is Real-GDSR's first stage; dual-branch guide/source networks are standard (MMSR, DKN, NAIMA). The specific resolution pairs (0.25 to 2 m etc.) are not addressed |
| Degradation should imitate the real pipeline and include random registration offsets and elevation noise | Partly supported. Real-GDSR shows synthetic-degradation training transfers badly to real DSMs. Learned guide deformation for weak alignment is in CMSR. Random registration offsets as augmentation for DSM SR: not addressed in sources found |
| Loss lambda1 L_HR + lambda2 L_LR + lambda3 L_gradient plus smoothness, edge-preservation and range terms | Partly supported. LR consistency (all per-image methods; hard form in graph regularisation and DADA), gradient loss (NAIMA), edge-aware loss (PromptDA), TV (FeatUp; suggested by PixTransform). Range terms: not addressed |
| Pretrain on many areas, then fine-tune on the target under LR consistency (test-time adaptation) | Supported in kind, not for this exact task. Prior2DSM uses test-time LoRA for DSM completion; Marigold-DC uses test-time guidance of a pretrained model. No paper found doing per-scene LR-consistency fine-tuning of a pretrained guided DSM SR network |
| MCPN, diffusion with consistency, point-cloud upsampling | MCPN exists (J. Imaging 10(3):69, 2024) but is a per-image DIP-style method for Sentinel-2 band SR and inpainting, not DSMs. Diffusion with consistency: Elevate (DSM; LR-derived scale/shift, no hard constraint stated), Marigold-DC, AdaDS. Point-cloud upsampling: not surveyed here |
| Proposed experiments and metrics | Consistent with practice: geographic hold-out (Elevate tests unseen cities); RMSE, MedAE, NMAD, slope error (Elevate). Building-edge position and artefact frequency are not standard metrics in the sources found |
| Check items (lean, date, GLO-30 gap not addressed by the note) | Literature agrees these are open. Elevate reports date-change effects (about 5 % of test data). No source handles lean in guided DSM SR |

## Open questions

- Does MMSR's advantage over P2P on DFC2019 DEM (x8) hold at x16 to x30? The paper did not test
  it, and its filter neighbourhoods were set for x4/x8.
- Does it hold on Esri imagery with roof lean, and on GLO-30 radar DSM in Yemen?
- Licences of the MMSR, FeatUp and JIIF repositories (not shown on the pages opened).
- Whether DINO guide channels help a per-image fit or only supervised models (no evidence either
  way).
- Whether hash or Fourier coordinate encodings make texture copying worse. Theory suggests they
  raise spatial frequency; untested for guided SR.

## Sources

- de Lutio, D'Aronco, Wegner, Schindler. Guided Super-Resolution as Pixel-to-Pixel Transformation.
  ICCV 2019. <https://arxiv.org/abs/1904.01501> (full text via ar5iv). VERIFIED
- Dong, Yokoya, Wang, Uezato. Learning Mutual Modulation for Self-Supervised Cross-Modal
  Super-Resolution. ECCV 2022. <https://arxiv.org/abs/2207.09156> ;
  <https://github.com/palmdong/MMSR>. VERIFIED
- Shacht, Danon, Fogel, Cohen-Or (arXiv v4 adds Leizerson). Single Pair Cross-Modality Super
  Resolution. CVPR 2021. <https://arxiv.org/abs/2004.09965>. VERIFIED
- Uezato, Hong, Yokoya, He. Guided Deep Decoder: Unsupervised Image Pair Fusion. ECCV 2020.
  <https://arxiv.org/abs/2007.11766> (search listing);
  <https://github.com/tuezato/guided-deep-decoder> (search listing). UNVERIFIED (not opened)
- Czerkawski et al. Multi-Modal Convolutional Parameterisation Network for Guided Image Inverse
  Problems. J. Imaging 10(3):69, 2024. doi:10.3390/jimaging10030069 ;
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC10970978>. VERIFIED (MDPI page returned 403; PMC copy
  read)
- Fu, Hamilton, Brandt, Feldmann, Zhang, Freeman. FeatUp. ICLR 2024.
  <https://arxiv.org/html/2403.10516v2>. VERIFIED
- de Lutio, Becker, D'Aronco, Russo, Wegner, Schindler. Learning Graph Regularisation for Guided
  Super-Resolution. CVPR 2022. <https://arxiv.org/abs/2203.14297> ;
  <https://github.com/prs-eth/graph-super-resolution>. VERIFIED
- Metzger, Caye Daudt, Schindler. Guided Depth Super-Resolution by Deep Anisotropic Diffusion. CVPR
  2023. <https://arxiv.org/abs/2211.11592> ;
  <https://github.com/prs-eth/Diffusion-Super-Resolution>. VERIFIED
- Kim, Ponce, Ham. Deformable Kernel Networks for Joint Image Filtering. IJCV 129, 2021.
  <https://cvlab.yonsei.ac.kr/projects/dkn/> (search listing; arXiv 1910.08373). UNVERIFIED (not
  opened)
- Tang, Chen, Zeng. Joint Implicit Image Function for Guided Depth Super-Resolution. ACM MM 2021.
  <https://arxiv.org/abs/2107.08717>. VERIFIED
- Panangian, Bittner. Real-GDSR. ISPRS Annals 2024. <https://arxiv.org/abs/2404.03930>. VERIFIED
- Nicolicioiu, Narnhofer, Metzger, Panangian, Bittner, Schindler. Guided Super-Resolution of Digital
  Elevation Models with Diffusion-Based Image Generators (Elevate). arXiv 2609.11886, 2026.
  <https://arxiv.org/html/2609.11886>. VERIFIED
- Nasir, Liu, Mian. NAIMA: Semantics Aware RGB Guided Depth Super-Resolution. arXiv 2604.04407,
  2026. <https://arxiv.org/html/2604.04407v2>. VERIFIED
- Nasir, Liu, Mian. WAVE. arXiv 2608.25302, 2026. <https://arxiv.org/abs/2608.25302>. VERIFIED
  (abstract)
- Lin et al. Prompting Depth Anything for 4K Resolution Accurate Metric Depth Estimation. CVPR 2025.
  <https://arxiv.org/abs/2412.14015> ; <https://github.com/DepthAnything/PromptDA>. VERIFIED
- Viola et al. Marigold-DC. ICCV 2025. <https://arxiv.org/abs/2412.13389> ;
  <https://github.com/prs-eth/Marigold-DC>. VERIFIED
- Wang, Zhu, Zhou, Zhao. Metric Depth Estimation from Arbitrarily Degraded Low-Resolution Depth
  Prompts (AdaDS). arXiv 2602.09510. <https://arxiv.org/abs/2602.09510>. VERIFIED (abstract)
- Wimmer et al. AnyUp: Universal Feature Upsampling. ICLR 2026. <https://arxiv.org/abs/2510.12764> ;
  <https://github.com/wimmerth/anyup>. VERIFIED
- Couairon et al. JAFAR. arXiv 2506.11136. <https://arxiv.org/abs/2506.11136>. VERIFIED
- Huang, Chen, Havrylov, Geiger, Zhang. LoftUp. ICCV 2025 per CVF listing.
  <https://arxiv.org/abs/2504.14032> ; <https://github.com/andrehuang/loftup>. VERIFIED
- Tancik et al. Fourier Features Let Networks Learn High Frequency Functions in Low Dimensional
  Domains. 2020. <https://arxiv.org/abs/2006.10739>. VERIFIED
- Müller, Evans, Schied, Keller. Instant Neural Graphics Primitives with a Multiresolution Hash
  Encoding. ACM TOG 41(4), 2022. <https://arxiv.org/abs/2201.05989>. VERIFIED
- Zhang, Rao, Agrawala. Adding Conditional Control to Text-to-Image Diffusion Models (ControlNet).
  <https://arxiv.org/abs/2302.05543>. VERIFIED
- Zhang, Chen, Ng, Koltun. Zoom To Learn, Learn To Zoom (CoBi loss). CVPR 2019.
  <https://arxiv.org/abs/1905.05169>. VERIFIED
- Wang et al. Early Stopping for Deep Image Prior. TMLR 2023. <https://arxiv.org/abs/2112.06074>.
  UNVERIFIED (search listing only)
- Rafaeli, Svoray, Nahlieli. Seamless High-Resolution Terrain Reconstruction: A Prior-Based Vision
  Transformer Approach. arXiv 2507.09681. VERIFIED (abstract)
- Rafaeli, Svoray, Nahlieli. Prior2DSM. arXiv 2604.02009. VERIFIED (abstract)
- Nuth, Kääb. Co-registration and bias corrections of satellite elevation data sets. The Cryosphere
  5:271-290, 2011. <https://tc.copernicus.org/articles/5/271/2011/>. VERIFIED
- xDEM coregistration documentation. <https://xdem.readthedocs.io/en/stable/coregistration.html>.
  VERIFIED
- ESA Kelvins PROBA-V scoring (cPSNR). <https://kelvins.esa.int/proba-v-super-resolution/scoring/> ;
  Märtens et al., Astrodynamics 2019, <https://arxiv.org/abs/1907.01821>. VERIFIED
