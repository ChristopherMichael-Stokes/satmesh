---
status: current
topic: evaluation
summary: P1 of photo-only pose recovery on synthetic slice photos for cameras at 25 m and above:
MegaLoc ranking of a rendered grid plus XFeat verification gives a first fix within 1 m for 16 of
18 queries at 100 m spacing and 17 of 18 at 50 m with no wrong accepted fix at 100 m and one at 50
m; a render up to 2 times higher than the photo still matches; sequence voting made no difference
because every single-photo fix already succeeded; TensorRT cuts a LighterGlue match from 107 to 10
ms.
answers: Can the first fix be found with no prior pose; how dense must the render grid be; does
MegaLoc ranking work for rendered aerial views; how large a scale gap can the matcher bridge for
coarse-to-fine search; did sequence voting help; how fast are XFeat and LighterGlue on TensorRT;
what did P1 leave unproven
---

# P1 results: first fix with no prior pose

Run 2026-10-31. Plan: `photo-only-plan.md` (P1); P0: `photo-only-p0-results.md`. Scripts, logs and
data: `uncommitted/photo-only/p1/`. Scope: cameras at 25 m and above ground (decision log); the 10 m
queries were run but are left out of every figure below.

## Setup

- Slice store (49 leaves, 1.27 km square), photos are full-surface renders at known poses, so
  texture is shared with the grid: an upper bound.
- Grid: positions every 100 m or 50 m over +-600 m, heights 15, 40, 100 m above ground, headings
  every 90 degrees, pitch -25 degrees (2,028 and 7,500 renders). Queries: 24 random positions
  within +-450 m, heights 10, 25, 50, 100 m in turn, random heading; 18 of them at 25 m and above.
- Method: MegaLoc (Berton and Masone, MIT; DINOv2 ViT-B/14 backbone, 8448-dimension descriptor,
  434 x 322
  input in fp16, 3.4 ms per image on the 4070 Ti) cosine ranking of the grid against the query; the
  top 20 are each localised with the harness (XFeat plus LighterGlue, surface reference); a fix
  counts as good within 1 m and 2 degrees of the truth. MegaLoc ran in a throwaway venv outside the
  repo (torch 2.15, `torch.hub` from a local clone); `ml/.venv` lacks torchvision and
  huggingface_hub.

## First fix, single photo (18 queries at 25 m and above)

| Grid spacing | Good fix at rank 1 | Good fix in top 5 | In top 10 | Best-inlier fix within 1 m | Other |
| --- | ---: | ---: | ---: | ---: | --- |
| 100 m | 14 | 17 | 17 | 16 | one fix 1.26 m off, one query with no fix (25 m up) |
| 50 m | 15 | 16 | 18 | 17 | one accepted fix 22 m wrong (25 m up) |

- Taking the fix with the most inliers among the verified top 20 is the rule that produced these
  numbers. At 25 m the 50 m grid found a good fix for all 6 queries within the top 10 but chose a
  wrong one for one of them; at 50 to 100 m it chose right for all 12.
- Brute-force baseline (XFeat plus LighterGlue against every render of the 100 m grid, ONNX CPU,
  107 ms per pair): the run hit the 30 minute background limit after 7 queries, 5 of them at 25 m
  and above. All 5 fixes were within 0.35 m; the nearest grid cell ranked first or fourth by
  match count. No JSON was written; numbers are from the log. Matching took 100 to 400 s per
  query (the other jobs shared the CPU).

## Speed

| Step | Time |
| --- | ---: |
| XFeat extraction, ONNX CPU, 2048 keypoints | 57 ms |
| LighterGlue match, ONNX CPU, 2048 / 1024 keypoints | 107 / 36 ms |
| XFeat extraction, TensorRT FP16, 2048 / 4096 | 5.6 / 6.1 ms |
| LighterGlue match, TensorRT FP16, 2048 / 4096, Python call included | 10.4 / 15.1 ms |
| MegaLoc, 434 x 322, fp16, batch 16 | 3.4 ms |
| GPU render, 1280 x 960 | 8 to 12 ms |

TensorRT comes from the `xfeat-rt` submodule's `backends/tensorrt` (`xfeat-trt`, tensorrt-cu13),
installed into a scratch environment outside the repo; `satmesh-eval` still uses ONNX Runtime. At
10 to 15 ms a pair, brute force over a 2,000-render grid is about 25 s per photo.

## Scale gap, for coarse-to-fine

The render camera sits r times farther back along the photo's optical axis (r times higher, same
target and pitch); 8 photos at 25 and 50 m:

| r | Median matches | Fixes within 1 m | Note |
| ---: | ---: | ---: | --- |
| 1 | 1,959 | 8 | |
| 2 | 414 | 8 | |
| 4 | 57 | 1 | two more solved but 4 to 7 m off |
| 8, 16 | 0 | 0 | |

A coarse level can therefore sit at most about 2 times above the photos it serves. A height ladder
of 25, 50 and 100 m covers any photo height with a level in range; wider spacing at the higher
levels reduces the render count, which matters on areas of several kilometres (a 5 km store at 70
m spacing, 3 heights and 4 headings is about 72,000 renders; the slice is 3,900). The hierarchical
search itself is not built or measured.

## Sequence voting

Two 10-photo flights (25 to 40 m and 60 to 100 m, photos 10 m apart), first 8 photos, 10 MegaLoc
candidates each on the 50 m grid, Viterbi over the verified fixes with a 40 m step limit. Clean
and re-lit (gain 0.7, gamma 1.3, 1.5 px blur) photos:

| Flight | Photos | Single-photo first fix | Sequence first fix |
| --- | --- | ---: | ---: |
| 25 to 40 m | clean / re-lit | 0.53 m / 0.31 m | 0.53 m / 0.31 m |
| 60 to 100 m | clean / re-lit | 0.17 m / 0.16 m | 0.17 m / 0.16 m |

Voting changed nothing, because the first photo's best candidate was already right in all four
runs. The test did not contain an ambiguous start, so it says nothing about whether voting would
help where the single-photo fix fails (the one 22 m wrong fix above was in the query set, not in
these flights).

## MegaLoc without torch

The Hugging Face repo ships `megaloc.onnx` (458 MB, input 322 x 322, dynamic batch). On ONNX Runtime
CPU it takes 0.64 s per image and matches the torch model to cosine 0.99999 or better on six
renders. Ranking the 100 m grid at 322 x 322 gave the same result as 434 x 322 on the 18 queries at
25 m and above: good fix in the top 20 for 18 (17 at 434 x 322), best-inlier fix within 1 m for 16,
one fix 3.14 m off.

## Not established

- Repetitive terrain, a real domain gap (real photos against Esri imagery) and other seasons: the
  site is distinctive and the photos share the grid's texture.
- Pitch and roll uncertainty: the grid had one pitch, the queries the same one.
- The hierarchical search, and MegaLoc ranking on a grid of thousands of renders per kilometre
  (the 50 m grid has 7,500).
- Distinguishing a wrong accepted fix from a right one without the truth: the 22 m wrong fix had
  inliers like a good one; the gate at 30 inliers does not catch it (P0 found the same).

## Traps

- Background jobs are stopped after 30 minutes; the brute-force run wrote its JSON only at the end
  and lost it. Scripts should write per-query results.
- A Monitor on `tail -f` of a log that does not exist yet exits at once; `tail -F` works.
- Playwright has no Chromium for this Ubuntu 20.04, so no page here was rendered.
