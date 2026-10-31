---
status: current
topic: evaluation
summary: The photo-only pipeline is built as `satmesh track` in the new `satmesh-track` package (lens graph with frame rejection, tracker, local search, MegaLoc first fix, outputs, review page); on the 24 distorted slice photos from a start 50 m off it tracked all, recovered the focal length to 0.22 % and positions to 0.08 m median, and the notes list what is untested and where the time goes.
answers: What was built for photo-only pose and lens recovery and where does it live; what did the first end-to-end run measure; which parts are tested and how; what differs from the plan; what is untested; where is the time spent and what should be optimised first
---

# Photo-only pipeline: implementation results

Built 2026-10-31 against `photo-only-productionisation-plan.md` (approved). Method and evidence:
`photo-only-calibration-research.md`, `photo-only-p0-results.md` to `photo-only-p3-results.md`.
User-facing description: `docs/02-track.md`.

## What exists

New workspace member `pipeline/packages/satmesh-track` (module `satmesh_track`), depending on
`satmesh-eval` for rendering, matching and the PnP solve, and on `gtsam` (4.3, locked) and
`onnxruntime`.

| Module | Does |
| --- | --- |
| `lens.py` | `fit_lens`: GTSAM graph with a shared `Cal3Bundler` (focal, k1, k2), a pose per photo, points with mesh-error priors, Huber loss; `LensEstimate` with the 3 x 3 covariance; frame rejection by robust z of reprojection RMS and position-jump peaks, floored at the assumed noise |
| `tracker.py` | `track(photos, start, context)`: focal scan on the first photo, constant-velocity prediction scaled by `sequence_index` gaps, render, match, lift, solve; local search after fewer than 30 inliers; the lens graph at the end; `TrackedPhoto` statuses tracked, relocalised, rejected, lost |
| `search.py` | Local search grid centred on the last fix (radius from the missed steps), ranking by match count |
| `first_fix.py` | Global grid (70 m, heights 25/50/100 m, 2 pitches, 4 headings), cached MegaLoc descriptors, `find_start`; `start_near` for a known rough position |
| `retrieval.py` | MegaLoc on ONNX Runtime |
| `photos.py`, `store_scene.py`, `outputs.py`, `track_review.html` | Reading and ordering photos, the tile store as a scene, the four output files and the review page |
| CLI | `satmesh track` in `satmesh-cli` |

## First end-to-end run

`satmesh track` on the 24 distorted photos of flight L (P2: 25 to 50 m up, true lens focal 1005.4
px, k1 -0.10) against the slice store, `--start` 50 m from the first photo, `--radius-m 120`, XFeat
plus LighterGlue on ONNX CPU:

- All 24 photos tracked, no search needed.
- Focal 1003.2 px (-0.22 %, 1 sigma 0.7 % at the working size), k1 -0.0936, k2 -0.0046 (true 0).
- Position error against the flight's truth: median 0.08 m, max 0.15 m (24 poses read back from
  `poses.jsonl` with the harness reader).
- The acceptance criteria of the plan (focal within 1 %, poses within 1 m) hold.

## Tests

`packages/satmesh-track/tests`: 26 tests, 3 gated on model files (`XFEAT_MODEL_DIR`,
`MEGALOC_MODEL`) and skipped without them.

- Lens: a known lens projected with OpenCV's own model is recovered noise-free and within the
  reported uncertainty with noise; a frame of bad matches and a frame moved 15 m are rejected;
  straight-down views over a plane give a focal sigma more than 3 times the oblique one.
- Tracker (synthetic town, distorted lens, SIFT): a flight is tracked, focal within 2 %, poses within
  1 m; with XFeat, a turn inside a gap is recovered by the local search (poses within 2 m).
- Search, first fix, outputs, photos, retrieval: grid counts worked out by hand, descriptor cache hit
  and key changes, pose file read back by `satmesh_eval.poses.read_pose_file`, a fisheye warning,
  MegaLoc batch independence, a first fix within 5 m from the grid with no prior.

## Differences from the plan

- Photos are ordered by file name only; `--order exif` is not built (no EXIF reader dependency yet).
  `PhotoImage.sequence_index` carries the step for missing photos once time stamps are read.
- `track` takes a `TrackingContext` (scene, matcher, config, progress callback) instead of separate
  arguments.
- The search grid is centred on the last fix, so the last fix itself is a candidate (the experiments
  started the grid at the circle's edge).
- The rejection floors its spread at the assumed noise (pixel sigma, mesh error), which the P3
  experiments did not have; the three corrupted-frame cases are covered by tests, the P3 flights
  were not rerun.
- Local search ranks candidates with the full matcher on both images; it is correct but slower than
  extracting the photo's features once.

## Not tested

- Store-wide first fix through the CLI (`MEGALOC_MODEL`, no `--start`): only the unit and
  integration tests with a 36-render grid. A slice-sized grid is about 7,800 renders; describing
  them is about 83 minutes on CPU.
- Real photos; `--matcher sift` through the CLI; a store of several kilometres.

## Where the time goes (candidates for the optimisation pass)

| Step | Cost now | Idea |
| --- | --- | --- |
| Describing grid renders with MegaLoc | 0.64 s each on CPU, first run per store | GPU or TensorRT execution provider; fewer pitches or a coarser grid at the 100 m level |
| Local search ranking | each candidate extracts both images' features (about 0.25 s on CPU) | extract the photo once, batch the candidates; TensorRT |
| Matching during tracking | ONNX CPU, about 0.4 s a photo | TensorRT backend of `xfeat-rt` (10 to 15 ms a pair) |
| Test suite | the gap test takes about 60 s, the tracker flight 15 s | smaller scene, fewer candidates |
| Store scene load | 8 s and 5 GB of RAM for 961 leaves | far-field parent tiles |

## Traps

- Two test files named `test_photos.py` in different packages break `pytest packages` collection;
  test file base names are unique across the pipeline packages.
- Renaming a helper `_solved` to `solved` made a local variable of the same name shadow it.
- SIFT's basin on the small synthetic town is under 25 m, so the gap test needs XFeat.
