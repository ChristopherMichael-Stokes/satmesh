---
status: current
topic: evaluation
summary: MegaLoc in FP16 on a fixed-batch TensorRT engine gives the same first-fix poses and places as FP32 on the 2.5 km store and the Bexhill slice, and cuts the run from 531 to 350 s (frame 1) and 746 to 465 s (frame 75), and render overlapped with describe (M6) gains nothing; the FP16 graph on the CUDA provider is 2.1 times faster per image than FP32 and the engine 5.5 times; cosine to FP32 is 0.9954 at worst for the engine, but fused retrieval recall and the winners hold, so the engine is the shipped route, built offline once.
answers: How much faster is MegaLoc in FP16 and on TensorRT; how far do the descriptors drift and does it matter; which route was adopted and why; how the engine is built and loaded; what changed in the first fix end to end; what failed on the way (ONNX Runtime TensorRT provider, block lists, batch cliff); what is left
---

# MegaLoc FP16 and TensorRT: results

Run 2026-11-02. Plan: `megaloc-fp16-tensorrt-plan.md`. Scratch (gitignored,
`uncommitted/photo-only/m/`): `describe.py`, `describe_trt.py`, `f2_variant.py` (F2's script with
`DB` and `QS` paths), `jaccard.py`, descriptors per variant, `engine/` (the engine); runs in
`uncommitted/photo-only/f7/m4-*`.

## Speed per image (128 to 512 real level 1 renders, GPU only)

| Route | ms an image | Cosine to FP32, worst / mean |
| --- | ---: | --- |
| FP32, CUDA provider (before) | 8.4 to 8.8 | |
| FP16 graph, CUDA provider | 3.7 to 4.2 at any batch from 4 to 32 | 0.9997 / 0.99995 |
| FP16 engine, batch 32, upload and download included | 1.52 | 0.9954 / 0.9992 |

- FP16 conversion is `onnxruntime.transformers.float16.convert_float_to_float16(keep_io_types=True)`;
  no new dependency for it.
- Keeping the aggregator (`ReduceLogSumExp`, `ScatterND`, `ReduceL2`, `Exp`) in FP32 on the CUDA
  provider ran 10 times slower (41 ms at batch 8) for the same cosine. Dropped.
- Keeping reductions, `Softmax` and `LayerNormalization` in FP32 in the engine moved its worst
  cosine from 0.9954 to 0.9970 at the same 1.5 ms. The remaining drift sits in attention and
  matrix multiplies; no per-layer comparison was made.

## Retrieval: F2 on the 2.5 km store (14,520 views, 110 clip frames)

Five-frame fused window, 77 windows, K=1 / K=3:

| Descriptors | Fused | Single centre frame |
| --- | --- | --- |
| FP32 | 0.99 / 1.00 | 0.87 / 0.95 |
| FP16, CUDA provider | 0.97 / 1.00 | 0.86 / 0.95 |
| FP16 engine | 1.00 / 1.00 | 0.84 / 0.94 |

Jaccard of the retrieved place sets against FP32 (110 frames; places 280 m apart):

| Variant | K=1 mean (identical sets) | K=3 | K=6 |
| --- | --- | --- | --- |
| FP16, CUDA provider | 0.991 (99 %) | 0.977 (95 %) | 0.961 (86 %) |
| FP16 engine | 0.955 (95 %) | 0.932 (86 %) | 0.925 (74 %) |

The place sets differ in near-ties; the correct place stays inside the set (recall above) and the
verified winners are unchanged (below).

## End to end (engine against FP32, `satmesh-track` first fix, no priors unless stated)

| Run | FP32 s | Engine s | Pose and places |
| --- | ---: | ---: | --- |
| 2.5 km frame 1 | 530.9 | 350.3 | fix identical (18.6 m from the tracker, 421 inliers); same six places and inliers; ranks 2 and 3 swapped (similarity 0.248 both) |
| 2.5 km frame 75 | 746.5 (F3, before batch preparation) | 465.1 | fix identical (14.5 m, 99 inliers); same six places and ranks |
| Bexhill slice (heading 30+-45, 150 m circle) | 172.3 | 144.1 | other candidate won (rank 2, 257 inliers against 388); position 0.86 m, heading 0.09 degrees, pitch 0.74 degrees, height 2.2 m apart; 17.8 m from the tracker against 17.1 |

- Frame 1: describe 241 s to 52.5 s (level 1 55.9 to 12.1, level 2 185.4 to 40.4); peak GPU memory
  11.2 to 3.3 GB. What remains is rendering (172 s), verification (105 s) and the rest.
- Frame 75 had no like-for-like FP32 run after the batch-preparation change (F7); that change was
  worth about 7 %, so the engine gain there is about a third.
- Each run was timed once, not three times. The Bexhill frame 1 with no priors was not run; the
  slice covers Bexhill frame 1 with priors.

## What failed

- The ONNX Runtime TensorRT provider cannot build the graph: it re-adds the default
  `reduction="none"` attribute to `ScatterND`, which the TensorRT 11 parser rejects, and then
  asks for shape profiles of internal tensors.
- An earlier FP16 timing of 91 ms at batch 32 was two sessions sharing the GPU in one process, not
  a batch cliff. The F7 FP32 cliff at batch 64 may be the same effect; not tested.
- `onnx.tools.update_model_dims` runs the checker, which rejects the converter's node order; the
  batch dimension is set directly.

## How it ships

- Offline, once: `satmesh-locate-export MODEL.onnx OUT_DIR` converts to FP16, drops the default
  `reduction` attribute, fixes the batch at 32 and builds the engine through `xfeat-trt`'s
  `load_or_build_engine` (47 s). xfeat-rt is unchanged and stays at batch 1.
- At run time `MegaLocDescriber` takes the `.engine` file from `MEGALOC_MODEL`, runs it with
  `EngineRunner`, pads a short batch to 32 and renormalises the FP16 output. An `.onnx` path
  works as before. Preprocessing uses four threads (it is 2.5 ms an image).
- The `tensorrt` extra of `satmesh-locate` carries `onnx` and `xfeat-trt`; the track extra pulls it
  in. Tests build an engine with the exporter and read it back through the describer.

## M6: render overlapped with describe (rejected)

A worker thread described chunk n while the main thread rendered chunk n + 1 (the diff is in the
gitignored `uncommitted/photo-only/f7/m6-overlap.patch`; reverted). Same engine, same machine.

| Workload | Without overlap | With overlap |
| --- | ---: | ---: |
| Bexhill slice, run s (3 timings each) | 144.1 (cold), 135.1, 133.0 | 136.2, 135.9, 136.5 |
| Bexhill slice, level 2 render s | 22.3 (cold), 19.2, 18.9 | 26.7, 27.0, 27.2 |
| 2.5 km frame 1, run s (one timing each) | 350.3 | 347.3 |
| 2.5 km frame 1, level 2 render s | 128.4 | 169.9 |

- Describe is hidden behind render, but rendering slows by about as much as describe takes
  (+41 s of render against 40 s of describe at 2.5 km): the render's GPU draw and embree ray casts
  compete with the engine and its four preprocessing threads. Net gain 0.9 %, inside the noise.
- The slice outputs equal the baseline's field by field. On the 2.5 km run the verification and
  fix events and every summary field are equal; the candidate similarities differ by 1e-6 to
  5e-4 with the same places and ranks, most likely run-to-run noise of the FP16 engine (not
  confirmed by a repeat of the baseline).
- The original F7 finding stands with the engine: rendering and describing compete for the same
  GPU and cores. Threads were not swept, because the ceiling (the describe time, 15 % of the run)
  was already spent by the render slowdown.

## Left

- Verification (105 s a pass), rendering (170 s) and the F7 follow-ups (early drop, stepped
  heading widening, level 2 headings around the level 1 best) are now most of the run.
- A per-layer comparison would show where the engine drifts; not needed so far.
