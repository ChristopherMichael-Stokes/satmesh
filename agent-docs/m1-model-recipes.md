---
status: current
topic: height-refinement
summary: Validated run recipes for RS3DAda, Geopose, Depth Anything 3, CHMv2 and DINOv3-Sat: licences, environments, GPU memory, tiling, weights URLs and traps.
answers: How do I run RS3DAda on an Esri tile?; How do I run the Geopose first-place model?; What GPU memory does each height model need?; What licences do the pretrained height models carry?; Where do the model weights come from?; What traps affect running these models?
---

# Pretrained height model recipes

Validated 2026-10-30 by research agents (read in source, smoke-tested on the RTX 4070 Ti) and used
in the M1 sweep (`e4b-results.md`). Each model gets its own throwaway venv; none is a project
dependency. All inputs below are the corrected Esri RGB as uint8 HxWx3 unless noted. Weight files
sit in the session scratchpad, which is ephemeral; the download URLs here recreate them.

## Summary

| Model | Output | Licence (code / weights) | Env | Peak GPU | Notes |
| --- | --- | --- | --- | --- | --- |
| RS3DAda (Song et al., NeurIPS 2024) | nDSM, metres | MIT / MIT | Python 3.12, torch 2.15 | 3 GB per flip at 1,022 px | Windows of 1,022 px, stride 511 |
| Geopose first place (selim_sef) | height above ground, metres | MIT / Dropbox links, DataPort licence CC BY 4.0 | Python 3.12, torch, timm 0.9.7, smp 0.3.4 | 4.2 GB at 2,176 px | Two folds, 4-flip TTA |
| Depth Anything 3 (Small, Base, Mono-L, Metric-L) | relative depth | Apache-2.0 | Python 3.12, repo install | 0.7 to 2.4 GB at 1,008 px | Needs an affine fit to height |
| Depth Anything V2 Small | relative inverse depth | Apache-2.0 | transformers | 0.5 GB at 1,008 px | Needs an affine fit |
| CHMv2 (model) | canopy height, metres (trees only) | DINOv3 licence, gated | transformers | 6.9 GB | Feed 0.5 m input |
| CHMv2 (global tiles) | canopy height, uint8 metres | CC BY 4.0 | rasterio | none | About 0.7 m, Vantor imagery 2016 to 2019 |
| Depth Any Canopy | canopy fraction (units undocumented) | Apache-2.0 | transformers | 0.5 to 1 GB | US-trained; not used |
| DINOv3-Sat ViT-L | features | DINOv3 licence, gated | transformers | 2.3 GB | Patch 16, 4 register tokens |

## RS3DAda

- Repo github.com/JTRNEO/SynRS3D (commit ab5a485, 2025-05-16). Checkpoint
  `RS3DAda_vitl_DPT_height.pth` (1.47 GB):
  <https://huggingface.co/JTRNEO/RS3DAda/resolve/main/RS3DAda_vitl_DPT_height.pth> or Zenodo record
  13940407. No login.
- Env: `uv venv --python 3.12 venv-rs3d`; `uv pip install torch torchvision albumentations
  rasterio tqdm huggingface_hub numpy`. The README's Python 3.8 and torch 2.2.1 are not needed.
  The stock `infer_height.py` needs `osgeo.gdal` only to write output, so call the model from
  Python.
- `DPT_DINOv2` fetches DINOv2 code from GitHub main with `torch.hub` on first load (not pinned).
- Model: `DPT_DINOv2(encoder='vitl', head_configs=[{'name':'regression','nclass':1},
  {'name':'segmentation','nclass':8}], pretrained=False)`. Declare the segmentation head or
  `load_state_dict` fails. Output head `regression` = nDSM in metres, can be negative.
- Normalisation: raw 0..255 with ImageNet mean (123.675, 116.28, 103.53) and std (58.395, 57.12,
  57.375), `max_pixel_value=1`. No resizing; sliding 1,022 px windows (multiple of 14), stride 511,
  linear-taper blending. Pad by reflection, not zeros (a zero pad leaves black edges).
- TTA: original plus hflip, vflip, hvflip, averaged. Run the four flips one at a time; a batch of
  four at 1,022 px did not fit next to other GPU users.
- 90 s per 540 m box at 0.25 m with 16 windows by 4 flips.

## Geopose first place

- Repo github.com/drivendataorg/overhead-geopose-challenge, folder `1st Place` (commit 3ec4abc).
  Weights are not in the repo: the Dockerfile downloads two Dropbox files, login-free:
  `https://www.dropbox.com/s/0uplf7b5d502ul2/folds_TimmUnet_tf_efficientnetv2_l_in21k_5_r2?dl=1`
  and `.../s/54dhmlbdip23fif/folds_TimmUnet_tf_efficientnetv2_l_in21k_6_r2?dl=1` (485 MB each). The
  IEEE DataPort copy needs a free account (not used). Keep local copies; Dropbox links can rot.
- Env: `uv venv --python 3.12 venv-geo`; `uv pip install torch timm numpy
  "segmentation_models_pytorch==0.3.4" "huggingface_hub<1"` (hub 2.x breaks timm 0.9.7).
- Two shims for current smp: `segmentation_models_pytorch.base.modules.Flatten = torch.nn.Flatten`,
  and stub `segmentation_models_pytorch.unet.decoder` in `sys.modules` (unused imports).
- Model: `TimmUnet('tf_efficientnetv2_l_in21k')`; load the checkpoint's `state_dict` with the
  `module.` prefix stripped. Input `(x/255 - 0.5) * 2`, size divisible by 32. Outputs `height`
  (AGL, metres; clamp at 0), `mag`, `xydir`, `scale`; for near-nadir imagery only `height` is used.
- The first-place code runs the two folds with 4-flip TTA (hflip negates `xydir[:,0]`, vflip
  `xydir[:,1]`). Whole 2,176 px image in one pass, reflect-padded. 8 s per box.

## Depth Anything 3 and V2

- DA3 repo github.com/ByteDance-Seed/Depth-Anything-3 (commit 3d835ec). Apache-2.0: DA3-SMALL,
  DA3-BASE, DA3MONO-LARGE, DA3METRIC-LARGE (`depth-anything/<id>`); Large, Giant and Nested are CC
  BY-NC. Install from a clone: `VIRTUAL_ENV=... uv pip install torch torchvision "numpy<2"`,
  `xformers`, then the repo.
- `DepthAnything3.from_pretrained(id).to('cuda').eval()`;
  `m.inference([rgb], process_res=1008, process_res_method='upper_bound_resize')`;
  `p.depth[0]` at the processed resolution (resample back). MONO and METRIC give relative depth;
  METRIC's raw output needs `focal_px * out / 300` and no intrinsics are returned. Treat all as
  relative.
- DA2: `depth-anything/Depth-Anything-V2-Small-hf` with transformers
  (`AutoModelForDepthEstimation`, size 1,008). Output is disparity (larger = closer).
- Both need an affine fit to the coarse source: fit `s_c - B(dtm)_c ~ a * B(D)_c + b`, D oriented
  larger = higher (DA2 as is, DA3 `-depth`), per box and factor. Fitting `s` itself regresses on
  terrain and gave negative scales in 11 of 12 fits. Corrected fits give a > 0 everywhere and
  surfaces within 0.03 m RMSE of kriging: no added detail.

## CHMv2

- Model `facebook/dinov3-vitl16-chmv2-dpt-head`: gated (manual approval, DINOv3 licence); needs an
  HF login. `transformers` 5.x has `CHMv2ForDepthEstimation` and `CHMv2ImageProcessor`.
  Defaults: mean (0.420, 0.411, 0.296), std (0.213, 0.156, 0.143), no resize, pad to 16,
  `max_depth` 96. Output canopy height in metres, 0.01 to 32 m seen.
- Input scale matters: the 0.25 m texture overpredicts canopy (open-ground RMSE 7 m at
  Ferrybridge); area-average to 0.5 m for a better result (RMSE 4.3 m). Windows of 1,008 px,
  stride 504, tapered blending.
- Global product (CC BY 4.0, anonymous HTTPS):
  `https://dataforgood-fb-data.s3.amazonaws.com/forests/v2/global/dinov3_global_chm_v2_ml3/chm/<quadkey>.tif`
  with `tiles.geojson` to find the quadkey (Ferrybridge 0313113120, Upper Aire 0313113012).
  32,768 px EPSG:3857 uint8, 1.19 m pixels (about 0.71 m on the ground), about 70 MB per tile; read
  windows by HTTP range; 0 means no canopy.

## Depth Any Canopy (not used)

`DarthReca/depth-any-canopy-small` and `-base` (Apache-2.0), `AutoModelForDepthEstimation`,
518 px. The preprocessor config does no normalisation, the correct input scaling and the output
units are undocumented, and it was trained on US NEON data.

## DINOv3-Sat

- `facebook/dinov3-vitl16-pretrain-sat493m` (1.2 GB, gated, same login). `AutoModel`, fp16;
  patch 16, hidden 1,024, 24 layers, 4 register tokens (drop CLS and registers). Normalisation
  mean (0.43, 0.411, 0.296), std (0.213, 0.156, 0.143). "last" = `last_hidden_state`; "mid" =
  `hidden_states[12]`.
- Whole 2,160 px image in one pass is fine (2.3 GB); over 5.4 km use 1,008 px windows with a stride
  of 31 tokens (a 504 px stride does not land on the token grid) and a clamped final window.

## Traps

- Running scripts that start worker processes needs an `if __name__ == "__main__"` guard.
- `python -I` breaks imports of sibling scratch modules.
- A GPU shared with other jobs distorts timings; peak memory figures are reliable.
- Weights downloaded by the agents also sit in `~/.cache/huggingface` (15 GB with other models).
