---
status: historical
topic: surface-refinement
summary: E9 survey: no method recovers wall texture from one nadir image; generative texturing needs GPU and lacks provenance
answers: Can wall texture be recovered from nadir imagery?; Does inpainted texture hurt feature matching?; Which texturing tools suit city meshes?; What non-generative baseline is suggested?
---

# E9 research: stretched texture on steep faces

Survey by a research subagent, 2026-10-26. Sources marked VERIFIED were opened and read;
UNOPENED were seen only as search snippets.

## Conclusions

- No published method gets real wall texture from a single nadir capture. The wall pixels were
  never observed, so any fill is invented. Reallocating texels to walls (UV re-parameterisation,
  atlas budget) adds no information; it only gives filled pixels somewhere to live.
- No study measures how inpainted or generated texture affects feature matching or localisation.
  MeshLoc is the closest: rendered real texture localises almost as well as real photos, and
  geometry alone localises far worse. Hallucinated texture is untested.
- Generative mesh texturing (TEXTure, Text2Tex, Paint3D) needs a GPU, targets single objects with
  text prompts, and exports no per-texel provenance. Text2Tex is CC BY-NC-SA 3.0.
- Satellite-to-3D-city generators (Sat2Scene, Sat2City, Skyfall-GS) fill facades with diffusion
  models; no public code seen, GPU only, no provenance.
- Facade work that suits aerial input recolours catalogue patterns from colours and openings read
  off the aerial image (Despine and Colleu 2015); the authors say window estimates are distorted by
  the aerial projection.
- Recommended first trial: the non-generative baseline. Gate faces by slope, write a provenance
  channel, fill flagged texels with low-frequency colour from measured neighbours. CPU only,
  deterministic, adds no matchable structure, every fill flagged.

## Comparison

| Method | Needs | Flags synthesised pixels? | CPU? | Licence | Code | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| MVS-Texturing (Waechter 2014) | Several posed images, mesh | Option to keep unseen faces; no mask output found | Yes | BSD-3 | github.com/nmoehrle/mvs-texturing (2026-03-11) | Repo VERIFIED; paper UNOPENED |
| xatlas UV atlas | Mesh | n/a (packing) | Yes | MIT | github.com/jpcy/xatlas | VERIFIED |
| Slope-gated drape (LuciadRIA) | Face normals | Implicit: steep faces untextured | Yes | Commercial | n/a | UNOPENED |
| Biharmonic inpainting (scikit-image) | Mask | Own mask | Yes | BSD | `skimage.restoration.inpaint_biharmonic` | VERIFIED |
| OpenCV Telea / Navier-Stokes | Mask | Own mask | Yes | Apache-2 | OpenCV photo | UNOPENED |
| Criminisi exemplar (2003/04) | Mask, exemplar | Own mask | Yes | Paper | third-party ports | MSR page VERIFIED |
| PatchMatch (Barnes 2009) | Mask, exemplar | Own mask | Yes | Paper | n/a | Project page VERIFIED |
| Image quilting (Efros, Freeman 2001) | Exemplar | Own mask | Yes | Paper | n/a | UNOPENED |
| Resynthesizer (Harrison) | Mask, exemplar | Own mask | Yes | GPL-3 | github.com/bootchk/resynthesizer | VERIFIED |
| LaMa (Suvorov, WACV 2022) | Mask, weights | Own mask | Yes (`device=cpu`), runtime not stated | Code Apache-2; weights not stated | github.com/advimman/lama | VERIFIED |
| SD inpainting | GPU, prompt, mask | Own mask | Effectively no | Model card unreadable | n/a | UNOPENED |
| TEXTure (2023) | GPU, prompt, mesh | Internal trimap, not exported | No | MIT | github.com/TEXTurePaper/TEXTurePaper | VERIFIED |
| Text2Tex (2023) | GPU 12 GB+, prompt | Internal mask | No | CC BY-NC-SA 3.0 | github.com/daveredrum/Text2Tex | VERIFIED |
| Paint3D (CVPR 2024) | GPU, prompt or image | No | No | Apache-2 | github.com/OpenTexture/Paint3D | VERIFIED |
| Despine, Colleu 2015 | Aerial imagery, catalogue | Not stated | Not stated | n/a | none | Abstract VERIFIED |
| Shang et al. 2023 (GAN facade repair) | Label map, style image | No | No | n/a | none linked | Abstract VERIFIED |
| Sat2Scene, Sat2City, Skyfall-GS | GPU, diffusion | No | No | Skyfall-GS paper CC BY 4.0 | none linked | Abstracts VERIFIED |

## Notes

- MVS-Texturing picks one view per face, then levels colour across seams (global, then local
  Poisson). Options `--keep_unseen_faces`, `--skip_hole_filling`. With one image the view choice is
  moot; its data term (size and sharpness of a face in the source) is a usable per-face quality
  score.
- Biharmonic and Telea fills grow smoothly inward from the mask border: no false edges, flat
  smeared walls.
- Exemplar fills (Criminisi, PatchMatch, quilting, Resynthesizer, LaMa) can only copy nadir
  pixels (roofs, ground), so walls look like roof or ground, and repeated patches can create
  matchable structure that does not exist. LaMa trained at 256 px; its README claims ~2k works.
- Text2Tex demo: about 500 s to generate plus 360 s to refine on a GPU.
- Facade modelling from ground photos (Müller 2007, Dai ICCV 2013) needs a ground-level photo;
  UNOPENED.

## Evidence on synthetic texture and matching

MeshLoc (Panek, Kukelova, Sattler, ECCV 2022, arxiv.org/abs/2207.10762, VERIFIED), Aachen v1.1
night queries localised within (0.25 m/2°, 0.5 m/5°, 5 m/10°), SuperPoint + SuperGlue:

| Database source | Localised (%) |
| --- | --- |
| Real images | 74.3 / 93.2 / 99.0 |
| Textured-mesh renders | 72.3 / 91.1 / 99.0 |
| Per-vertex colour renders | 68.1 / 90.1 / 97.4 |
| Geometry only | 0.5 / 3.1 / 24.6 |

Patel, Barfoot, Schoellig (ICRA 2020, UAV to Google Earth renders): UNOPENED. Toker et al. 2021
(arxiv.org/abs/2103.06818): retrieval, not pixel matching.

## Ranked shortlist

| # | Candidate | Risk to matching | Flagging | CPU |
| --- | --- | --- | --- | --- |
| 1 | Slope gate, provenance channel, low-frequency fill (biharmonic or Telea from the measured edge; fallback roof-edge band or ground colour at the wall base) | Lowest | Per-texel measured / stretched / filled, plus stretch factor 1/cos θ | Yes |
| 2 | Wall-strip UV charts (xatlas) plus 1 | None alone | Same | Yes |
| 3 | Exemplar fill on wall strips (Resynthesizer or PatchMatch style) | Medium: false repeats | Mask | Yes |
| 4 | LaMa on wall strips | Medium to high: invented windows | Mask | Yes, untimed |
| 5 | Catalogue or procedural facades | High | Mask plus catalogue ID | Yes |

Recommendation: 1 first; it sets up the provenance channel the others need and is the baseline
they must beat.

Scoring without oblique ground truth:

1. Hold-out fill test: where relief displacement shows a sliver of wall, hide those measured
   pixels, fill, score against them.
2. Provenance-aware matching: render low oblique views with the provenance channel; match pairs
   with known poses; report inliers, reprojection error and the share of matches on flagged
   pixels.
3. Real video, if the owner's tests have frames: localise against renders with and without fill,
   then again with flagged-pixel matches excluded.
4. Side-by-side renders for judging by eye.

## Open questions

- Are Esri tiles in Great Britain true orthophotos? If not, one side of each building shows
  measured wall pixels.
- Threshold angle and stretch factor for the flag: choose from rendered streaks.
- LaMa CPU runtime at 2k px and weights licence; Stable Diffusion inpainting weights licence.
- No measurement exists for matching on hallucinated texture; protocol step 2 would be the first.
