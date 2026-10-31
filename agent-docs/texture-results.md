---
status: current
topic: baseline-pipeline
summary: Texture refinement trials on Esri leaf textures: classical sharpening dropped, ESRGAN plus half of the original's fine band chosen against over-smoothing, then parked after the owner saw little gain on UK meshes in Blender; measurements, weights, settings and traps. Nothing is in the store or `build`.
answers: Which texture refinement was tried and what did the owner pick; how much texture does ESRGAN remove; which Real-ESRGAN weights and settings were used; why is the Esri imagery blurry; what traps affect EA aerial comparison and ESRGAN tiling; what is not yet done
---

# Texture refinement results

Run 2026-10-31. Plan: `texture-plan.md`. Decisions: `decisions.md`. Scripts and outputs are scratch
in `uncommitted/texture/` (`preview.py`, `ea_crops.py`, `sr.py`, `compare2.py`, `large.py`,
`large2.py`); weights in `uncommitted/models/sr/`. All results were judged by the owner on review
pages; the gauge below is a rough aid.

## Outcome

- Owner: classical sharpening (unsharp mask, Richardson-Lucy) is dropped. It helped distinguish
  detail in some places and worked better after ESRGAN than before, but did nothing for the
  over-smoothing.
- Owner: Real-ESRGAN x4plus is much better than the source, which is blurry with artefacts on road
  markings; it sometimes over-smooths texture.
- Owner's pick against over-smoothing: ESRGAN x4plus plus 0.5 times the original's own fine band
  (variant 7 on `large2.html`). This is the project's own unproven trial, not an established
  method. Not applied to any store.

## Verdict on meshes

- Owner, stock against refined textures on UK meshes (Ferrybridge town 72 leaves, Upper Aire 81,
  Southend 9; refined leaves 2,048 px; `uncommitted/regions/uk-stock-vs-esrgan7.blend`,
  collections `STOCK` and `ESRGAN7`): not much improvement to be had. Texture refinement is parked
  (`decisions.md`).
- Refining 162 leaves took about 15 minutes of GPU time (about 6 s per leaf).

## Settings

- Real-ESRGAN x4plus (BSD-3), weights `RealESRGAN_x4plus.pth`, SHA-256
  `4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1`, loaded with `spandrel` 0.4.2
  through `uv run --with` in `ml/` (no dependency added). 256 px input uses 576 MiB of GPU memory
  (RTX 4070 Ti, 12 GB).
- Full leaves (1,024 px) run as 256 px tiles with a 16 px reflected margin that is cut away
  afterwards: no seams visible in the numbers; not yet checked by eye.
- Fine-band reinjection: `out = clip(ESRGAN + 0.5 * (O - gaussian(O, sigma)))`, O the Lanczos 4x
  original, sigma 1.5 texels (6 px at 4x).
- Real-ESRGAN general-x4v3 and its weak-denoise sibling (`realesr-general-wdn-x4v3`), interpolated as
  in the authors' `inference_realesrgan.py`: `net = s * general + (1 - s) * wdn`, s = 1.0, 0.5, 0.0.
  SHA-256 `8dc7edb9ac80ccdc30c3a5dca6616509367f05fbc184ad95b731f05bece96292` (general) and
  `1641f8c4464b9f097c9fdda5589273713f67cf59f3d909e0bd688f0cee269dca` (wdn).

## Measurements (full leaves, native-scale gradient energy)

Gauge: output reduced 4x by box mean, mean luma gradient magnitude. Lower than the original means
texture lost.

| Leaf | Original | x4plus | general s=0.0 | s=0.5 | s=1.0 | Matched fraction (energy) | 0.5 fraction |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Plano | 0.038 | 0.033 | 0.033 | 0.033 | 0.033 | 0.22 (0.038) | 0.044 |
| Southend | 0.052 | 0.046 | 0.045 | 0.048 | 0.050 | 0.21 (0.052) | 0.060 |
| Desert | 0.056 | 0.047 | 0.038 | 0.041 | 0.042 | 0.18 (0.056) | 0.070 |

- x4plus keeps 87 %, 88 % and 84 % of the original's native-scale edge energy. The owner's pick
  (fraction 0.5) overshoots the original by 16 %, 15 % and 25 %.

## Why the imagery is blurry

- Esri z19/z20 sources are 0.31 to 0.5 m (`us-imagery-preview.md`, `s1-results.md`). A US leaf at the
  finest zoom is Esri z20 (about 0.115 m per texel at Denver) cut from a 0.34 m source, which Esri
  only draws at level 20: about 3x oversampled. Plano is about 2.7x, Desert (z19) about 1.5x,
  Southend (z18, 0.46 m source) about 1.2x. The blur is the source resolution, not the subject choice.
- Subjects were picked by rule (the leaf at the 90th percentile of mean gradient energy per site),
  which finds the sharper leaves of a site, not the sharper sites.
- Sharper sources exist only locally: EA aerial 0.1 to 0.25 m in England, NAIP 0.3 m in the US,
  county flights such as Ames (2.4 cm; fetched at the 30 cm cap).

## Traps

- EA aerial coverage is patchy: the cached 2020 SE4520 tile has pixels over only part of each 1 km
  crop (55 % in `t0-D2`). Subjects need a per-leaf coverage test.
- ECW decoding needs Docker (`satmesh-gdal-ecw`); a WSL distro without Docker integration cannot
  crop EA aerial.
- Registering EA to Esri by phase correlation (difference-of-Gaussians band, Hann taper) gave 1.2 to
  4.4 m shifts; one leaf was rejected (shift over 5.4 m); the 4.4 m value exceeds the surveyed 0.2
  to 2.8 m and is doubtful.
- The deconvolution (Richardson-Lucy) and unsharp variants are cheap on CPU; ESRGAN of a 1,024 px
  leaf takes seconds on the GPU.
- Artifact pages are capped at 16 MB per file and 64 MB per publish: full 4,096 px leaves go up as
  published `files`, a site per publish.

## Not done

- No store or `build` change: no `with_texture_image`, no parent rebuild, no `satmesh texture`.
- Texture size past 1,024 px per leaf (store size, Gazebo and CesiumJS memory) is undecided.
- Real-photo and camera-render checks of the refined texture.
- Other sources (NAIP, dated Esri releases) and multi-capture fusion.
