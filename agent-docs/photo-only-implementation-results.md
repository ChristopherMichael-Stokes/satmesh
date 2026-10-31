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

## Further runs (method report examples, 2026-10-31)

`satmesh track` through the CLI, same store, start 50 m from the first photo, 24 photos each unless
noted. Truth from each flight's `flight.json`.

| Run | Statuses | Position error median (max) | Focal error (1 sigma) | k1 (true) | k2 |
| --- | --- | --- | --- | --- | --- |
| Flight L, photos 6, 13, 19 with 70 % random pixels | 21 tracked, 3 lost | 0.06 m (0.13) | -0.07 % (0.7 %) | -0.0926 (-0.100) | -0.0144 |
| Flight N, camera pitch -90 to -81 degrees | 24 tracked | 0.47 m (0.54) | -1.09 % (6.2 %) | -0.0954 | -0.0011 |
| Flight W, 100 degree lens, k1 -0.25, k2 +0.08 | 24 tracked | 0.57 m (1.05) | +0.93 % (0.6 %) | -0.2480 | +0.0809 |
| Sharp-turn flight, photos 8 to 16 missing, by file name | 13 tracked, 1 rejected (photo 17), 1 relocalised | 0.16 m (0.28) | -0.40 % (1.1 %) | -0.0914 | -0.0090 |
| Same, true sequence indices (API) | search at photo 17: 600 renders, radius 205 m, recovered | | | | |

Flight N's focal sigma is 9 times flight L's (62 px against 7 px). Scripts and data:
`uncommitted/photo-only/report/`.

## Tests

`packages/satmesh-track/tests`: 28 tests, 3 gated on model files (`XFEAT_MODEL_DIR`,
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
- Local search ranks candidates by extracting the photo's features once and matching each render's
  on a pool of 3 workers (after the optimisation pass, `photo-only-profile.md`).

## Not tested

- Store-wide first fix through the CLI (`MEGALOC_MODEL`, no `--start`): only the unit and
  integration tests with a 36-render grid. A slice-sized grid is about 7,800 renders; describing
  them is about 83 minutes on CPU.
- Real photos; `--matcher sift` through the CLI; a store of several kilometres.

## Where the time goes

After the optimisation pass the flight L run takes 49 s on the CPU (100.8 s before), outputs
unchanged, and 13.9 s on TensorRT (`photo-only-profile.md`).

| Step | Cost now | Idea |
| --- | --- | --- |
| Describing grid renders with MegaLoc | 0.64 s each on CPU, first run per store | GPU or TensorRT execution provider; fewer pitches or a coarser grid at the 100 m level |
| Local search ranking | about 36 s for 216 candidates on CPU | Done on TensorRT; K1024 ranking or a cheaper candidate set change behaviour |
| Matching during tracking | about 0.25 s a photo on CPU | Done: TensorRT backend |
| Test suite | the gap test takes about 60 s, the tracker flight 15 s | smaller scene, fewer candidates |
| Store scene load | 8 s and 5 GB of RAM for 961 leaves | far-field parent tiles |

## Rerun recipes

All from `pipeline/`. Model files are build outputs, never committed.

| What | How |
| --- | --- |
| XFeat models | `XFEAT_MODEL_DIR=/home/chris/xfeat_dev/xfeat-rt/reference/uncommitted/models-chunked` (the `models/` folder there fails to load); FP16 exports in `models-fp16` |
| MegaLoc ONNX | `huggingface_hub.hf_hub_download("gberton/MegaLoc", "megaloc.onnx")` into `~/.cache/huggingface/hub/models--gberton--MegaLoc/snapshots/*/megaloc.onnx` (458 MB, already there); `MEGALOC_MODEL=` that path |
| Whole pipeline tests | `XFEAT_MODEL_DIR=... MEGALOC_MODEL=... uv run --frozen pytest packages` (392 passed, 2 skipped, about 3 minutes); `make test` runs the same without models (model-gated tests skip) |
| End-to-end run | `uv run satmesh track PHOTOS --store uncommitted/e4b/ferry-slice-store --start "53.712453, -1.275374" --radius-m 120 --out OUT` with `PHOTOS` the 24 PNGs of `uncommitted/photo-only/flights/flightL` (start is 50 m from photo 0) |
| Synthetic flight with a lens | `uncommitted/photo-only/p3/p2_flight.py NAME H_LOW H_HIGH SEED N [PITCH_LO PITCH_HI]` with env `TRUE_SCALE`, `TRUE_K1`, `TRUE_K2`, `TURN_SD_DEG`; needs `uncommitted/photo-only/p0/p0_common.py` on the path (`sys.path` `../p0`); writes `NAME/flight.json` and PNGs |
| Profiling | `uvx py-spy record -r 50 -f raw -o spy.raw -- .venv/bin/python .venv/bin/satmesh track ...`; aggregate the raw stacks by frame (inclusive and self shares); data in `uncommitted/photo-only/profile/` |
| TensorRT matcher | Part of the pipeline venv (`make setup`, `--all-extras`); `XFEAT_MODEL_DIR=/home/chris/xfeat_dev/satmesh/uncommitted/models/xfeat-rt` (symlinks to `models-chunked` and `models-fp16`); engines build on first use into `~/.cache/xfeat-rt/tensorrt` |
| Torch MegaLoc (only for comparisons) | a throwaway venv with torch, torchvision, huggingface_hub, safetensors, pillow and a clone of `github.com/gmberton/MegaLoc` loaded with `torch.hub.load(path, "get_trained_model", source="local")`; production needs none of it |

Scratch, all gitignored under `uncommitted/photo-only/`: `p0/` to `p3/` (experiment scripts and
JSON), `flights/` (flights L, H, N, K, W, T with truth in `flight.json`, 196 MB together), `profile/`
(cProfile and py-spy output). The session scratchpad held the 4.7 GB TensorRT environment, a 5.2 GB
torch environment, the P1 render grids (126 MB and 349 MB) and the P2 and P3 pickles; they are
rebuilt by the recipes above and the scripts and can be left to vanish.

## Traps

- Two test files named `test_photos.py` in different packages break `pytest packages` collection;
  test file base names are unique across the pipeline packages.
- Renaming a helper `_solved` to `solved` made a local variable of the same name shadow it.
- SIFT's basin on the small synthetic town is under 25 m, so the gap test needs XFeat.
- `_follow` counted failed local searches but reset the count only on a recovered search, so three
  isolated unusable photos (3 searches that failed, each followed by good photos) aborted a flight
  as "3 local searches in a row". A photo that localises without a search now resets the count
  (`test_isolated_unusable_photos_do_not_add_up_to_a_failed_track`). Found by the method report's
  corrupted-frame example.
- Photos are ordered by file name with one step between neighbours, so a run of missing photos looks
  like one long step: the search radius stays at its margin and a correct fix after the gap is
  flagged as a position jump and rejected (sharp-turn flight with photos 8 to 16 removed: photo 17
  rejected, photo 18 relocalised). Passing true sequence indices (EXIF order, not built) removes
  this.
