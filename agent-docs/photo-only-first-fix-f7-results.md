---
status: current
topic: evaluation
summary: F7 of the first fix: a sampling profile of the packaged first fix on the 2.5 km store (no priors, frame 1) puts MegaLoc inference at 53 % of the run, its CPU preprocessing at 9.5 %, rendering at 14 % and verification at 17 %; preparing the next MegaLoc batch while the GPU runs the current one cut the 604 s profiled run to 531 s (573 s unprofiled before) with identical outputs, rendering overlapped with describing gained nothing and was reverted, and FP16, IO binding and GPU resize were not tried.
answers: Where does the first fix spend its time on the 2.5 km store; which levers were tried and what did each gain; are the outputs identical; what was rejected and why; what was not profiled or tried; what ruins a timing on this machine
---

# F7: profile and optimise the packaged first fix

Run 2026-11-02, following the `profile-optimise` skill. Plan: `photo-only-first-fix-plan.md`.
Scratch (gitignored, `uncommitted/photo-only/f7/`): `run.sh` (wraps `f3/run_fix.py`, optional py-spy),
`shares.py` (profile to share table), `compare.py` (field-by-field comparison), logs and
`events.jsonl` per run, `render-overlap.patch` (the reverted change).

## Workload and machine

- Workload: `satmesh-track` first fix on the 2.5 km Bexhill store (`bexhill25/store`), frame 1, no
  priors, 20 photos, five fused frames. Level 1 5,808 views, level 2 about 20,040, verification 6
  places. A second slice (Bexhill 1.5 km store, heading 30+-45, 150 m circle) was the cheap check.
- Machine: AMD Ryzen 7 5800X3D (8 cores, 16 threads), RTX 4070 Ti (12.3 GB), ONNX Runtime 1.31.1
  (CUDA provider, FP32 graph), XFeat on TensorRT, WSL2.
- Profiler: py-spy 0.4.2, 20 Hz, non-blocking, started as the parent of the run (WSL refuses
  attaching to a running process). The profile costs 3 s on a 172 s slice.

## Baseline

| Run | Seconds | Level 1 | Level 2 | Verification | Winner |
| --- | ---: | ---: | ---: | ---: | --- |
| F3 run c1, unprofiled | 573.0 | 112.7 | 339 | 105 | rank 2, 18.6 m, 421 inliers |
| F7 profiled | 603.9 | 115.1 | 367.8 | 104.3 | the same |
| slice, F3 run b | 166.8 | 3.1 | 53.0 | 106.1 | rank 1, 17.1 m |
| slice, F7 unprofiled | 172.3 | 3.4 | 56.9 | 107.0 | the same |

Each configuration was timed once after the F3 run, not three times: a 2.5 km run takes 9 to
10 minutes. The slice reproduces F3 within 3 %. The profile adds about 5 % on the long run.

## Profile (2.5 km, 9,231 samples)

| Share | Where |
| ---: | --- |
| 78 % | `_ranked_level`, both levels' render and describe |
| 53 % | MegaLoc `InferenceSession.run` on the GPU |
| 9.5 % | MegaLoc preprocessing on the CPU (`cv2.resize` INTER_AREA 640 x 360 to 322 x 322, float32 normalise), run serially between GPU batches |
| 14 % | rendering one position's views (GPU draw 9.5 %, readback and decode the rest) |
| 17 % | verification: refine and tracking, XFeat matches |
| 3 % | ground height of lattice points (`in_scene`), embree set-up per render |

Memory: peak GPU 11.0 of 12.3 GB (whole card), peak RAM 4.8 GB.

Cost model from the baseline: level 1 5,808 views at 19.8 ms a view (8.5 render, 11.4 describe),
level 2 about 20,040 views at 18.4 ms (7.1 render, 11.3 describe); verification 17.4 s a place.

## Describer: batch size and the GPU feed

Standalone, 512 synthetic 640 x 360 frames through the describer (real flow confirms below):

| Batch | ms an image, preprocess included | GPU utilisation |
| ---: | ---: | ---: |
| 8 | 10.76 | 81 % |
| 16 | 10.94 | 82 % |
| 32 (default) | 11.40 | 81 % |
| 64 | 58.7 | 96 % |
| 128 | 207 | 98 % |

- A batch of 64 or more falls off a cliff; the default
  of 32 stays. Preprocessing is 2.5 ms an image and the GPU is 81 % busy: the 19 % idle is the
  serial preprocessing.

## Changes

1. **Prepare the next batch while the GPU runs the current one** (`megaloc.py`, one worker thread,
   OpenCV and numpy release the GIL). Describer alone: 10.77 to 9.23 ms an image (14 %), maximum
   absolute difference of the descriptors 0.0. Real flow, 2.5 km frame 1: 573.0 s (profiled
   baseline 603.9 s) to 530.9 s. Level 1 100.4 s, level 2 311.7 s, describe time 55.9 and 185.4 s
   against 66.0 and 226.2 s. Every summary field, the candidate events and the verification and
   fix events equal the baseline's (`compare.py`): same winner (rank 2, 18.6 m, 421 inliers), same
   six places. Against the unprofiled F3 run the gain is 7 %; against the profiled baseline 12 %,
   which is the better like-for-like because the profile slows the run only a few percent.
2. **Render the next chunk while the previous is described** (tried, reverted). Outputs identical,
   but on the slice level 2 went from 56.9 s to 60.3 s: render time rose from 21.4 to 57.9 s and
   describe time from 35.6 to 54.9 s. Render's GPU draw and the session compete for the same GPU
   and the embree ray casts for the same cores. The diff is kept in `render-overlap.patch`.

## Not done

- **FP16 or TensorRT for MegaLoc**: the inference step is 53 % of the run and the graph is FP32, so
  FP16 would be the largest remaining lever (tensor cores). It changes descriptors, so it is the
  owner's decision once the K=1 recall and the winner are compared; it needs an FP16 conversion
  (`onnxconverter-common`) or a TensorRT engine: a new dependency. Not measured.
- **Resize and normalise on the GPU or in the graph, ONNX Runtime IO binding**: after change 1
  the preprocessing hides behind the GPU run; the remaining gap is 0.9 ms an image (9.23 against
  about 8.3 ms of GPU time). Not tried.
- **Fewer views** (heights, pitches, headings, position circle): the priors already do this; any
  further cut changes what is searched.
- **Verification** (17 %): XFeat matching on TensorRT; the six places are independent but the GPU
  is shared. Not profiled below the call level.
- Native frames (`py-spy --native`): at 50 Hz it slowed the run by more than 2.5 times and was
  dropped; the GPU kernels are in the ONNX Runtime row, not broken out.
- Tracking the whole clip and `build`/`correct` were not part of this pass.

## Traps

- **CPU-only ONNX Runtime in the `locate` venv ruined every timing.** After a `cpu`-variant sync
  the environment held `onnxruntime` without the GPU provider; the first fix then ran 8 to 13
  times slower on 15 cores with no error (the describer falls back only when the CUDA provider is
  missing from the install, not from the session). `onnxruntime-gpu` had to be reinstalled
  (`uv sync --frozen --extra gpu --extra tensorrt --reinstall-package onnxruntime-gpu`). Test the cpu
  variant in a separate environment (`UV_PROJECT_ENVIRONMENT=<dir> uv run --frozen --extra cpu
  pytest ...`). Check `get_available_providers()` before any timing.
- A blocking py-spy (the default) on a 16-thread process made a 172 s run take more than 15
  minutes; `--nonblocking` costs 3 s. WSL denies `py-spy dump` of a running process (ptrace);
  start the run under py-spy.
- `pkill -f` and `pgrep -f` with a pattern in the same command line matches the shell running it
  (exit 144); use `ps -eo pid,args | grep "[p]attern"` and kill the pid.

## Wrong-prior run (U4 demo), stage times

Bexhill 1.5 km store, frame 1, heading 88+-15 (about 60 degrees off), 150 m circle; 465 s, fix
17.1 m from the tracker pose (rank 1, 388 inliers). Pass 1 failed and the heading widened to 180.

| Pass | Level 1 | Level 2 | Verification | Total |
| --- | ---: | ---: | ---: | ---: |
| 1, heading 88+-15 | 2.4 s (84 views) | 23.9 s (1,360 views) | 105.8 s | 138 s |
| 2, heading +-180 | 6.3 s (336 views) | 212.1 s (12,600 views) | 105.3 s | 327 s |

- The position circle shrinks level 1 only, which is 1 to 2 % of the run. Level 2 costs by views a
  position (120 with no heading, height or pitch prior), and verification is about 105 s a pass for
  six places whatever the verdicts.
- Verification per place (Process tab, 1.5 km store, right priors): refine 16 to 18 s (585 renders
  matched to the first photo), tracking 1 s for a solved place and 0 s for a rejected one.
- The ladder went from +-15 straight to +-180. Run d of F3 (60 degrees off, +-45 window) verified
  in one pass, so a +-45 step would have saved about 100 s here.
- Follow-ups (owner decisions, none measured) are listed in `photo-only-first-fix-plan.md`; the
  MegaLoc FP16 and TensorRT plan is `megaloc-fp16-tensorrt-plan.md`.
