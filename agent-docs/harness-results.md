---
status: current
topic: evaluation
summary: H1 of the acceptance harness built and run on the S0b cross-check site slice with the photo a full-surface render at a known pose; XFeat plus LighterGlue recovers 6 of 8 poses within 0.25 m and 2 degrees against the full-surface render and none against the bare-earth, flat or top-down references; SIFT collapses when the photo is re-lit and blurred.
answers: Does matching a photo against a render recover the camera pose; how do flat, bare-earth and full-surface references compare; does XFeat with LighterGlue beat SIFT; what breaks on coplanar references; how long does a localisation take; which traps were hit in H1
---

# Harness H1 results: pose recovery against the four references

Built 2026-10-31. Plan and method: `harness-plan.md`. Review page (eight poses, four references,
match lines): `uncommitted/harness/pose-recovery.html`.

## What exists

| Module (`satmesh_eval`) | Does |
| --- | --- |
| `matching.py` | `sift_match` (ratio 0.8, mutual check) and `XFeatLighterGlueMatcher` (ONNX Runtime, from the `third-party/xfeat-rt` submodule); both return pixels with centres at half-integers |
| `localise.py` | `lift_matches` (render depth to area-ENU points), `solve_pose` (`cv2.solvePnPRansac` with SQPnP, 20 px threshold, Levenberg-Marquardt refinement on the inliers), `pose_error`, `localise` |
| `references.py` | `perspective_views` (a scene rendered at the prior pose) and `nadir_views` (photo warped onto the ground plane by the plane homography, against the flat ortho from a camera looking straight down) |
| `ground.py` | `load_ground_scene` (bare-earth mesh from each leaf's `.ground.tif`, every 4th node, the leaf's texture), `flattened`, `ground_height_m` |
| `camera.py` | added `pose_from_enu`, `PoseOffset`, `offset_pose` |

Tests: `test_localise.py` (solver on projected points with 30 % outliers, the nadir warp against
the flat render from above, SIFT recovery within 0.25 m and 2 degrees, XFeat recovery of a re-lit
and blurred photo within 0.5 m and 5 degrees when `XFEAT_MODEL_DIR` names the exported models).
117 `satmesh-eval` tests pass.

## Setup

- Slice store of the S0b cross-check site (49 leaves), 1280 x 960, 70 degree field of view,
  range 300 m, `GpuRenderer` for every render.
- The photo is a full-surface render at the true pose, so photo and references share their
  texture and only the geometry differs. This is an upper bound for real photos.
- Reference rendered at a prior pose 2.9 m and 3 degrees off (2 m east, 2 m south, 0.5 m up,
  heading +3, pitch +1).
- Eight poses fixed before the run: ground level (2 m, pitch -5) and raised (25 m, pitch -20),
  headings 0, 90, 180, 270, at one location.
- Flat plane at the ground height under the camera (DTM). The bare-earth mesh is the DTM draped
  with the same texture.
- XFeat models: `models-chunked` (FP32, K 2048, 1280 x 960) from the `xfeat-rt` reference export.

## Results

Poses recovered of 8 within 0.25 m / 2 degrees, 0.5 m / 5, 5 m / 10 (MeshLoc's operating points).
Median error is over the poses where a pose was found.

| Photo | Matcher | Reference | Median matches | 0.25 m | 0.5 m | 5 m | Median error |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| As rendered | XFeat + LighterGlue | Full surface | 874 | 6 | 6 | 6 | 0.05 m |
| As rendered | XFeat + LighterGlue | Bare earth | 258 | 0 | 0 | 4 | 0.76 m |
| As rendered | XFeat + LighterGlue | Flat ortho | 248 | 0 | 1 | 4 | 0.78 m |
| As rendered | XFeat + LighterGlue | Photo warped top-down | 69 | 0 | 0 | 4 | 0.89 m |
| As rendered | SIFT | Full surface | 215 | 4 | 4 | 5 | 0.05 m |
| As rendered | SIFT | Bare earth | 53 | 0 | 0 | 4 | 0.70 m |
| As rendered | SIFT | Flat ortho | 47 | 0 | 1 | 4 | 0.87 m |
| As rendered | SIFT | Photo warped top-down | 12 | 0 | 0 | 4 | 0.95 m |
| Re-lit, blurred | XFeat + LighterGlue | Full surface | 804 | 6 | 6 | 7 | 0.05 m |
| Re-lit, blurred | XFeat + LighterGlue | Bare earth | 231 | 0 | 0 | 4 | 0.71 m |
| Re-lit, blurred | XFeat + LighterGlue | Flat ortho | 246 | 0 | 1 | 4 | 0.90 m |
| Re-lit, blurred | XFeat + LighterGlue | Photo warped top-down | 86 | 0 | 0 | 4 | 0.71 m |
| Re-lit, blurred | SIFT | Full surface | 24 | 3 | 4 | 4 | 0.10 m |
| Re-lit, blurred | SIFT | Bare earth | 6 | 0 | 0 | 3 | 2.69 m |
| Re-lit, blurred | SIFT | Flat ortho | 7 | 0 | 0 | 3 | 2.60 m |
| Re-lit, blurred | SIFT | Photo warped top-down | 2 | 0 | 0 | 2 | 1.54 m |

Re-lighting is gain 0.7, gamma 1.3, then a 1.5 px Gaussian blur.

- Geometry decides the result. With the full surface the median error is 0.05 m; with bare earth,
  flat or top-down it is 0.7 to 0.9 m and no pose reaches 0.25 m.
- Bare earth and the flat plane do about the same: the matches that exist lie on the ground, and
  roofs and trees displaced by parallax are the error.
- The top-down route gets a quarter of the matches of the perspective routes and no better error.
  The photo's near field is stretched into streaks by the warp, and at ground level the warped
  image is mostly a smear.
- XFeat with LighterGlue is unaffected by the re-lighting and blur (804 against 874 matches).
  SIFT falls from 215 to 24 matches.
- The four ground-level poses are mostly misses even for the full surface (709, 1, 517 and 39
  matches): the camera 2 m above the ground stands among trees and hedges. The bare-earth, flat
  and top-down references find no matches there (0 in all 12 runs).
- XFeat plus LighterGlue on ONNX Runtime CPU takes 0.4 to 0.5 s per photo including lifting and
  solving; SIFT 0.1 to 0.3 s. A render takes 8 to 12 ms (`harness-plan.md`).

## Altitude sweep (16 poses)

Same setup at 10, 25, 50 and 100 m above the ground, pitch -25, headings N, E, S, W, range 500 m
(the ground-level and 2 m poses above were replaced: the owner asked for 10 to 100 m). Photo as
rendered, poses of 16 within 0.25 m / 2 degrees, 0.5 m / 5, 5 m / 10; median error over solved poses.

| Matcher | Reference | Median matches | 0.25 m | 0.5 m | 5 m | Median error |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| XFeat + LighterGlue | Full surface | 1017 | 16 | 16 | 16 | 0.04 m |
| XFeat + LighterGlue | Bare earth | 603 | 0 | 1 | 16 | 0.73 m |
| XFeat + LighterGlue | Flat ortho | 610 | 0 | 2 | 15 | 1.06 m |
| XFeat + LighterGlue | Photo warped top-down | 275 | 0 | 2 | 8 | 1.72 m |
| SIFT | Full surface | 1210 | 15 | 16 | 16 | 0.02 m |
| SIFT | Bare earth | 232 | 0 | 0 | 15 | 0.71 m |
| SIFT | Flat ortho | 204 | 0 | 1 | 15 | 0.92 m |
| SIFT | Photo warped top-down | 28 | 0 | 0 | 8 | 1.04 m |

- Bare earth and flat stay near 1 m at every height; altitude does not close the gap.
- Top-down fails at 10 and 25 m (0 to 27 matches; two runs returned poses 233 m and 126 m wrong from
  27 and 5 matches). From 50 m it has 316 to 826 matches and 0.3 to 8 m errors. The solver does not
  yet reject solutions with few inliers (H2 item).
- Warp check (flat-ortho photo warped top-down against the ortho from above): median difference 2
  grey levels of 255 at 50 m, 6 at 10 m. With the full-surface photo 16 and 24: buildings and trees
  smear, which is real. The wedge-shaped warp is the photo's footprint on the ground, not a bug.

## Review page and scratch

- Page: <https://claude.ai/artifact/BRVC7jePdPXSWeJcDicpZH> (private), copy
  `uncommitted/harness/pose-recovery.html`: how-to-read, recall table, explainer strips per
  technique, warp check, all 16 poses with match lines.
- Scripts that built it are in `uncommitted/harness/scratch/`: `exp2.py` (recall rows, writes
  `exp2.json`), `exp3.py` (match-line images per pose), `exp4.py` (warp check), `exp5.py`
  (explainer strips), `build_page.py` plus `page_template.html`, `speed_common.py` (scene pickle
  cache, cameras; paths in it point at the session scratchpad and the slice store). They import
  `satmesh_eval` and need `XFEAT_MODEL_DIR`-style paths edited (models-chunked under
  `xfeat-rt/reference/uncommitted/`). The session scratchpad itself will vanish.

## Traps

- P3P-family solvers flip to the wrong side of the plane when every 3D point is coplanar (flat
  references): errors of 137 to 257 m and 103 to 157 degrees on 6 of 24 runs on the bare-earth,
  flat and top-down references at 25 m with AP3P. SQPnP (Terzakis and
  Lourakis, ECCV 2020) removes them. The solver is part of the contract for flat references.
- Exports in `xfeat-rt/reference/uncommitted/models/` predate the `precision` metadata field and
  fail to load; `models-chunked/` loads. The models are build outputs and never committed; tests
  read them from `XFEAT_MODEL_DIR`.
- The typos hook rewrites "PnP" to "OnP" in code and docs, which silently breaks `cv2.solvePnPRansac`;
  `_typos.toml` now maps `Pn` to itself.
- OpenCV returns no descriptors for an image without keypoints although its stubs say otherwise;
  `sift_match` checks the keypoint count.
- A synthetic scene (noise ground plus boxes) did not show the flat reference doing worse than the
  surface reference: the matches that exist lie on the ground, so a flat plane suffices there. The
  ordering shows on the real slice only, and is therefore not asserted in a test.
- A synthetic ground texture at 0.2 m per texel gave too few SIFT matches (69 against 93 with a
  0.1 m texel, and a 0.98 m error); texture scale decides whether SIFT works at all.

## Differences from the plan

- The top-down route solves the pose by perspective-n-point on plane points like the others, not by
  reading a 2D homography residual back as a pose offset. One solver serves all four references.
- The solver is SQPnP, not P3P (above).

## Open

- Real photos (H3): textures will differ, so the gap between the full surface and the other
  references will shrink while the matcher gap widens.
- One location, eight poses, one prior offset: no spread across places, offsets or lighting.
- Far-field parent tiles are not built; a long-range pose loads every leaf in view.
