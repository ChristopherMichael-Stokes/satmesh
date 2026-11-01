---
status: current
topic: evaluation
summary: Run recipes, scratch inventory, traps and the next stage for the two-stage (coarse then fine) first-fix pipeline: which script does what and how to rerun it, the two environments, what lives where under uncommitted/ with sizes and regeneration costs, a ladder of larger areas under a one-hour cap per run, and what is built only as scratch scripts.
answers: How do I rerun the Bexhill end-to-end run and its stages; which environment runs MegaLoc on the GPU and how to recreate it; where are the grids, descriptors, tracks and reports; what can be deleted and what it costs to regenerate; which traps were found; what is the next stage and its scope ladder; what needs the owner
---

# Two-stage first fix: recipes, scratch and next stage

State 2026-11-01. Results: `photo-only-megaloc-first-fix.md` (MegaLoc, hypotheses, end-to-end
timing, the recovery gate), `photo-only-coarse-to-fine.md` (level sizes and cost model),
`photo-only-imagery-only-trial.md` (imagery-only matching does not work here),
`photo-only-bexhill-results.md` (the clip and the tracker changes). Nothing below is in the shipped
`satmesh` CLI except the tracker changes; the first-fix pipeline exists only as scripts.

## What is built, and where

| Piece | Where | Status |
| --- | --- | --- |
| Tracker changes (staged priors, 30 m gate, weak-fix re-solve, local search pitch and heading, five-focal first photo, recovery gate, `--reference`) | `locate/packages/satmesh-track` (moved from `pipeline/`; command `satmesh-track`) | in the package, tested (30 passed, 2 skipped), uncommitted |
| Grid render, MegaLoc places, hypotheses, end-to-end driver, report | `uncommitted/photo-only/bexhill/scripts/` | scratch scripts, not in the package |
| MegaLoc on the GPU | `locate/packages/satmesh-locate` (`satmesh-locate` command; `uncommitted/envs/ortgpu` is no longer needed) | in the package |
| Two-level search (coarse then fine) | `render_cells.py`, `twostage.py` (scratch) with `satmesh-locate rank` | runs end to end; not in the package |

## Scripts

Scratch scripts are under `uncommitted/photo-only/bexhill/scripts/` and run in the `locate/`
environment: `uv run --project locate --extra gpu --extra tensorrt python SCRIPT` (the environment
column below predates the move). `twostage.py ROOT PHOTO FRAMES REFERENCE_CSV SCRATCH [--no-track]`
drives level 1, level 2 and the hypotheses with `satmesh-locate` and per-stage timers; it replaces
`e2e.py` for new runs.

| Script | Does | Environment |
| --- | --- | --- |
| `e2e.py` | the whole run from an empty `ROOT=uncommitted/photo-only/bexhill-e2e`: build, correct, two grids, MegaLoc, hypotheses and track; times each stage; `python3 -I scripts/e2e.py` | plain python3, calls the rest |
| `render_grid.py` | renders the grid (70 m, heights 40 55 72 90 110 m, headings every 30 degrees, 640 x 360 squashed to 322 x 322) to chunked `.npy`; env `ROOT`, `GRID_DIR`, `GRID_PITCH` | pipeline (`uv run python`) |
| `megaloc_query.py ROOT PHOTO` | describes both grids, the photo, writes `ROOT/places.json` (top 6 places 100 m apart) | `uncommitted/envs/ortgpu` |
| `e2e_track.py ROOT FRAMES REFERENCE_CSV` | refines each place (585 renders), tracks 12 frames from any fix, picks the winner, tracks the clip, writes `ROOT/track/` and `track_timings.json`; needs `XFEAT_MODEL_DIR` | pipeline |
| `e2e_report.py ROOT THUMBS OUT` | the timing report page (published as an artifact) | `python3 -I` |
| `truth.py`, `megaloc_eval.py`, `megaloc_eval2.py`, `hypotheses.py` | truth poses from a track, truth-cell rank per pitch, hypotheses for named frames (`hypotheses.py f075 f085`) | pipeline / ortgpu |
| `coarse_to_fine.py`, `two_level.py` | level-1 recall and the two-level search on the cached descriptors | ortgpu |
| `ref_poses.py`, `flat_reduction.py`, `topdown_reduction.py` | the imagery-only trial | pipeline |
| `gap_test_variants.py` | toggles tracker changes on the synthetic gap scenario (found the wrong-fix cause) | pipeline |

Frames: `uncommitted/photo-only/footage/bexhill-cemetery/frames/f001.jpg` to `f110.jpg` (2 a
second, 15 s
to 70 s of the clip, 1920 x 1080); logged track `telemetry.csv` and per-frame `reference.csv`
(interpolated GPS, `--reference`).
`XFEAT_MODEL_DIR=/home/chris/xfeat_dev/satmesh/uncommitted/models/xfeat-rt`.

## Environments

- `locate/`: `make setup` (default `LOCATE_VARIANT=gpu`: `onnxruntime-gpu` and the TensorRT matcher).
  XFeat engines build on first use into `~/.cache/xfeat-rt/tensorrt`. MegaLoc runs through
  `satmesh-locate`; its graph is read from `MEGALOC_MODEL` (the Hugging Face snapshot
  `~/.cache/huggingface/hub/models--gberton--MegaLoc/snapshots/*/megaloc.onnx`): 8.6 to 10.5 ms an image.
- `pipeline/`: baseline build, correct, exports and `eval`; it no longer holds the tracker.

## Scratch inventory (`uncommitted/photo-only/`, all gitignored)

| Path | Holds | Size | Regenerate |
| --- | --- | --- | --- |
| `footage/bexhill-cemetery/` | the clip (1.8 GB), `subs.vtt`, `telemetry.csv`, `reference.csv`, `frames/`, `thumbs/` | 1.9 GB | the clip is a download from Wikimedia Commons (ask first) |
| `bexhill/store` | the Bexhill store, corrected | small | 102 s warm |
| `bexhill/megaloc`, `megaloc_p50` | renders `renders_*.npy`, `db_descriptors.npy`, `meta.npy`, `truth.json`, `tops*.json`, `hypotheses*.json` | 14.6 GB | grid 220 to 250 s and descriptors 218 s each |
| `bexhill/run1` to `run7`, `refs/` | tracks of the clip (run7 is the last seeded run), imagery-only poses and outputs | small | minutes |
| `bexhill-e2e/` | store, `grid35`, `grid50` (renders and descriptors 14 GB), `track/`, `track_before_gate/`, `pipeline_timings.json`, `track_timings*.json`, `e2e_report.html`, `thumbs/` | 14 GB | the end-to-end run, 23 min |
| `envs/ortgpu` | the GPU environment | a few GB | the recipe above |

Candidates to delete when disk is short, not deleted: the `renders_*.npy` files of all four grids
(the
descriptors are enough for ranking; regenerate by `render_grid.py`).

## Traps found

- A pose solved at a wrong focal is biased: it re-renders at the nominal focal with few inliers, so
  `track` localises its first photo at five focals and seeds the loop with that attempt.
- Extra priors let wrong fixes through on repeating scenes (a 108-inlier fix 88 m off in the
  synthetic
  town): every fix must lie within 30 m of a prior; a search recovery within 3 typical steps per
  missed photo plus 15 m of the last fix. Both are tunables from one clip.
- The local search used to keep the last pitch and take 45 degree headings on a grid that never left
  the last position; it now varies pitch and heading and also tries evenly spaced headings.
- A fix with 351 inliers can still be rejected by a re-localisation at the nominal focal; match
  counts alone mislead near-nadir views of repeating grave rows.
- Imagery-only references (flat, ground, top-down) gave about 0 to 14 raw matches at the true pose
  against 328 to 414 for the mesh, on the Bexhill clip only (50 to 110 m above ground, oblique,
  20 frames). Higher altitudes were not tried; the owner has had success with the imagery warped
  to the estimated view at sufficient altitude.
- `render_grid.py` and the report script read `ROOT`; the report reads the pre-gate files
  `track_before_gate/` and `track_timings_before_gate.json` for its body.
- Hypothesis scripts take the truth from a tracker run, so ranks are against the tracker's pose
  (3.5 m median from the GPS), not a surveyed truth.

## Result: two-stage run on Bexhill frame 1 (2026-11-01)

`scripts/twostage.py` (render, rank, render, rank, hypotheses, track; hand-off through `meta.npy`,
`renders_*.npy` and `places.json`), run in `uncommitted/photo-only/bexhill-twostage/`, 760 s total:

| Stage | Seconds | Size |
| --- | ---: | --- |
| Level 1 render, then describe and rank | 14.8, 17.2 | about 1,440 views, K1 5 places 280 m apart |
| Level 2 render, then describe and rank | 146.0, 184.7 | 18,360 views (44,880 in the flat grid), final 6 places 100 m apart |
| Six hypotheses and tracking of 110 photos | 397.3 | refine 100, track 290 |

- Set-up from a built store: 6.0 min against 17 min for the flat grid.
- Final place 1 is 20 m from the tracker's pose for frame 1 and wins (388 inliers, 12 of 12 frames
  tracked); place 6 (295 inliers, 12 of 12) also converges; places 2 to 5 give no fix (11 to 23
  inliers).
- Track of the clip: 92 tracked, 5 relocalised, 1 rejected, 12 lost; the same as the flat-grid run.
- Frames 40, 75 and 85 (levels 1 and 2 only, 390 to 412 s each, 18,000 to 19,440 level 2 views, K1 5,
  truth is the tracker's pose): the nearest coarse place is 102, 169 and 171 m from the truth (inside
  the 250 m refinement radius), and the nearest final place is 39 m (rank 2), 69 m (rank 2) and 33 m
  (rank 1). None of the three was refined or tracked. Frames 1, 40, 75 and 85 are 4 of 8 test frames;
  the effect of K1 is not measured.
- `satmesh-locate` (`locate/`) now holds the describe and rank step; it replaces
  `rank_cells.py`.
  `render_cells.py` and `twostage.py` are still scratch.

## Result: 2.5 km square (2026-11-01)

Store `uncommitted/photo-only/bexhill25/store` (nw 50.8707, 0.4323; se 50.8483, 0.4678; 6.25 km2): build
259 s, `correct` 148 s (cold lidar download), 813 MB. Two-stage search without tracking, K1 5:

| Frame | Level 1 views, time | Level 2 views, time | Nearest coarse place | Nearest final place | Total |
| --- | --- | --- | --- | --- | ---: |
| f001 | 7,260, 143 s | 21,840, 390 s | 221 m (rank 2) | 66 m (rank 2; rank 1 is 1,037 m away) | 533 s |
| f075 | 7,260, 144 s | 20,400, 390 s | 115 m (rank 1) | 41 m (rank 1) | 534 s |

- Level 1 is 1,160 views a km2 and 20 ms a view, as estimated. Level 2 costs 19 ms a view.
- Peak system RAM 8.0 GB and GPU memory 10.9 GB of 12.3 GB (render and MegaLoc in turn, other
  processes included); the GPU is close to full at this size.
- Not tracked or refined; truth is the tracker's pose.
- Trap: each store has its own ENU origin, the centre of its tiles. The 2.5 km frame sits 193 m south
  of the Bexhill store's (50.857977 against 50.859711 north), so a truth pose from one store must be
  moved into the other before distances mean anything.

## Next stage: the two-stage pipeline, then larger areas

Owner, 2026-11-01: work on the two-stage (coarse then fine) pipeline and include larger areas by a
slow
increase in scope; do not run anything expected to take more than one hour in total.

1. Build level 1 (coarse views) and level 2 (fine views rendered and described on demand around the
   top places) as one procedure, with hints optional (heading window, heights). Design and
   environments first: it crosses the pipeline and the GPU environment today; production code in
   `satmesh-track` needs a plan for the owner (a GPU `onnxruntime` dependency, the hypothesis
   selection, a CLI shape).
2. Prove it on Bexhill: level 1 from the cached grids, level 2 on demand, time it end to end against
   the flat grid (23 min set-up, 8 of 8 frames in the top 6).
3. Ladder of areas, each step only if the one before is good and fits the hour:

| Area | Level 1 views (about 1,000 a km2, 20 ms a view) | Level 1 time | Store build (linear from Bexhill, unmeasured) | Needs |
| --- | ---: | ---: | ---: | --- |
| Bexhill 1.8 km2 | 1,800 | 40 s | 102 s | built |
| 2.5 km square (6 km2) | 6,000 | 2 min | about 6 min | downloads: ask |
| 5 km square (25 km2) | 25,000 | 8 min | about 24 min | downloads (EA lidar 100 to 500 MB a 5 km square): ask |
| 10 km x 10 km (100 km2) | 100,000 | 33 min | about 95 min, over the hour | downloads, far-field detail if RAM binds |

   Level 2 adds 3,000 to 33,000 views a photo (1 to 11 min). The 10 km square exceeds one hour by
its
   store build alone; split it into steps and ask the owner before starting it.

4. At each step measure: recall of the true place against the number of candidate places (K), the
   time per stage, and RAM and GPU memory of the scene.

Rules that apply: ask before any download; plan first for design forks; no commit or push unless
asked;
announce each long process with its log and how to stop it; a test on a slice before any run over
ten minutes.
