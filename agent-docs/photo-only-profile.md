---
status: current
topic: evaluation
summary: Sampling profile of `satmesh track` on the 24-photo slice flight with a local start search (85 % of the 104 s was candidate ranking, 82 % ONNX Runtime inference on CPU, 12 % a numpy channel mean), and the optimisation pass that took the run to 49 s with outputs bit-identical to the baseline; what remains is CPU inference, and the next levers change behaviour or add a dependency.
answers: Where does `satmesh track` spend its time; what was optimised and what did each change gain; what remains and what would remove it; why was cProfile misleading; how much does tracking itself cost; which options were measured and not adopted; which parts were not profiled
---

# `satmesh track` profile

Run 2026-10-31 on the 24 distorted photos of flight L against the slice store, `--start` 50 m off,
`--radius-m 120`, XFeat plus LighterGlue on ONNX Runtime CPU (K 2048), RTX 4070 Ti, 104 s wall in
total. Tool: py-spy 0.4 at 50 Hz, wall clock (26,831 samples). cProfile showed 50 s of thread-lock
waiting that the sampler does not: ONNX Runtime's thread pool makes cProfile's per-function times
unreliable, so the sampler is the reference.

## Where the time goes

| Share of the run | Where |
| ---: | --- |
| 85.6 % | `start_near`: ranking the 216 local-search candidates with the full matcher |
| 81.6 % | ONNX Runtime `InferenceSession.run`, everywhere |
| 52.4 % | LighterGlue match (a pair of 2048-keypoint sets, about 107 ms each) |
| 29.3 % | XFeat extraction (the photo again for every candidate, plus the candidate) |
| 12.2 % | numpy `mean` over the colour channels in `_fit_to_model` (1.3 M pixels, 633 calls) |
| 9.9 % | tracking the 24 photos (`_follow`), mostly the same matcher calls |
| about 3 % | GPU rendering of all 246 renders (`render`, `_draw`, `_read_back`, `_decode`) |
| under 1 % each | store load, photo reading, lens graph, outputs |

- The tracker proper costs about 10 s for 24 photos (0.4 s a photo); the start search costs about
  89 s for 216 candidates. Where the time goes depends on how many candidates are ranked.
- Every candidate comparison runs `matcher(photo, render)`, which extracts features of both images
  and matches them. The photo's features are computed 216 times.
- GPU work, the lens graph and the GTSAM solve are negligible at this size.

## Fixes, ordered by what they remove

| Order | Change | Removes | Outcome |
| --- | --- | --- | --- |
| 1 | Extract the photo's features once and rank candidates with features and match only | about half of the extraction share (about 15 %) | Done |
| 2 | Replace the channel mean with a numba kernel | up to 12 % | Done: `satmesh_eval/grey.py` |
| 3 | Rank with the 1,024-keypoint LighterGlue (36 ms against 107 ms) or the TensorRT backend (10 to 15 ms a pair) | most of the 52 % | Not adopted, see below |
| 4 | Batch candidates through XFeat and run candidate extraction and matching on a pool | the rest of the 29 % | Done as a pool of 3 workers and 8 ONNX threads; no batch graph exists (exports are batch 1) |
| 5 | Cheaper candidate sets: fewer headings or heights, or prefilter by a global descriptor | a multiple of everything above | Not done: changes which poses are searched |
| 6 | Reuse preallocated buffers in `_fit_to_model` | allocation churn | Not needed: the kernel writes into the canvas, `_fit_to_model` is 1.4 % self time |

## After the pass

Same run, same machine (8 cores, 16 logical CPUs, RTX 4070 Ti, ONNX Runtime on CPU, K 2048).

| | Baseline | After |
| --- | ---: | ---: |
| Wall time | 100.8 s | 49.2 s |
| `start_near` (216 candidates) | about 89 s | about 36 s |
| Tracking 24 photos | 10 s | 6 s (0.25 s a photo) |
| Imports, store load (2.4 s, 2.0 s), sessions | about 4.5 s | about 4.5 s |

- Outputs are bit-identical to the baseline run: every pose field of `poses.jsonl`, focal, k1, k2,
  the focal sigma and the per-photo statuses differ by 0 (field-by-field diff of the two output
  directories).
  Focal 1003.2 px, k1 -0.0936, k2 -0.0046 as before.
- Features once: `XFeatLighterGlueMatcher.extract` and `match_features` split the old call;
  `match_against` fixes the first image. Matches are array-equal to the direct call.
- Grey kernel: 18.5 ms to 0.28 ms for a 1280 x 960 image, float32-bit-identical to
  `astype(float32).mean(axis=2) / 255`. A parallel version competed with ONNX Runtime's threads and
  made matching slower, so it runs on one thread.
- Threads: ONNX Runtime's default is every logical CPU; half of them (the physical cores here) is
  faster, and a pool of ranking workers adds more. `start_near` seconds by (ONNX threads, workers):

| Threads \ workers | 1 | 2 | 3 | 4 | 8 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 16 (default) | 65.5 | | | 55.1 | |
| 8 | 48.6 | 37.6 | 36.7 | 36.6 | |
| 6 | | | 35.6 | | |
| 4 | | 45.2 | | 37.9 | |
| 2 | | | | | 42.0 |

  The chosen 8 threads and 3 workers sit on the plateau. The halving assumes 2-way SMT
  (`LOGICAL_CPUS_PER_CORE`), which the stdlib cannot detect.

- Second profile (5,881 samples): ONNX Runtime `InferenceSession.run` is 64 % of all samples
  (LighterGlue 48 %, XFeat 16 %); rendering is 17 %, slowed to about 80 ms from 14.6 ms idle by the
  CPU contention (its `_decode` is 2.5 ms idle, so a kernel there would save about 0.5 s).

### TensorRT

Owner decision 2026-10-31: XFeat and LighterGlue run on TensorRT (FP16 exports) on this machine,
at K 4096 (see below). `--backend tensorrt` is the CLI default and `--backend onnx` the CPU path.

| | ONNX CPU | TensorRT |
| --- | ---: | ---: |
| Wall time, flight L (K 2048) | 49.2 s | 13.9 s |
| Position error median (max) against truth | 0.081 m (0.150) | 0.055 m (0.135) |
| Focal error (1 sigma) | -0.22 % (6.9 px) | -0.03 % (6.7 px) |
| k1, k2 (true -0.100, 0) | -0.0936, -0.0046 | -0.1000, +0.0037 |

- Keypoint count on TensorRT, flight L, tracker run in one process (engines cached):

| K | Start search | Tracking | Median inliers | Position error median (max) | Focal error | k1 (true -0.100) |
| ---: | ---: | ---: | ---: | --- | --- | ---: |
| 2048 | 6.5 s | 0.9 s | 990 | 0.059 m (0.148) | -0.06 % | -0.0995 |
| 4096 | 6.7 s | 1.1 s | 2362 | 0.060 m (0.139) | -0.00 % | -0.1040 |

  Owner's suggestion to raise K on the GPU; the cost is 0.3 s and accuracy is unchanged on this
  flight. The CPU path stays at 2048.

- FP16 changes the keypoints, so the output is not bit-identical to the CPU run; on this flight it is
  at least as close to the truth. Other flights were not rerun on TensorRT.
- The CUDA context belongs to the thread that built the engines and the runners share buffers, so
  the matcher is called from that thread only: ranking runs inline (`supports_concurrent_calls`).
  Ranking on a pool thread segfaulted (exit 139, no traceback).

### Measured, not adopted

- 1,024-keypoint ranking (K1024): 40 s against 60 s for 216 candidates when ranking serially, but
  the top five candidates (the ones verified) differ from K2048 in 3 of 6 flights (first photos of
  flights L, H, N, K, W, T, start 50 m off: overlap 5, 5, 4, 5, 4, 4). It changes which poses are
  verified, so it needs the owner's call; the final pose after verification was not compared.
- Pre-extracting the photos' features while the previous photo is rendered and solved would save
  about 1.5 s of the 6 s tracking.

## Owner's direction for the pass

Profile first, then optimise where the profile points (done above). Beyond moving work to the GPU:
numba JIT for CPU-bound numpy work, buffers allocated early and reused, and the right data
structures. The tracker's accuracy must not change (compare poses and the lens against the
baseline run, `uncommitted/photo-only/profile/prof.log` and the numbers in
`photo-only-implementation-results.md`). Then the method report with worked examples.

## Not profiled

- The store-wide first fix (MegaLoc description of the grid: 0.64 s an image on CPU, thousands of
  images), because it was not run end to end.
- A longer sequence, a larger store (8 s and 5 GB of RAM to load 961 leaves), a search after a lost
  track, the GTSAM solve on thousands of points and real photos.
- GPU execution providers and the TensorRT backend (timed in isolation: LighterGlue 10.4 ms at 2048
  keypoints, `photo-only-p1-results.md`).
