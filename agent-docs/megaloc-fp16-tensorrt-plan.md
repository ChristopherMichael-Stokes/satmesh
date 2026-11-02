---
status: current
topic: evaluation
summary: Done; M6 rejected (results in megaloc-fp16-tensorrt-results.md). Plan to run MegaLoc in FP16 and on TensorRT in the first fix (inference is 53 % of a 2.5 km run, FP32 on the ONNX Runtime CUDA provider, 8.3 ms an image on the GPU): probe what is installed, convert the graph to FP16 with ONNX Runtime's own converter keeping sensitive operators in FP32, build a TensorRT engine through xfeat-rt's engine cache, gate on descriptor cosine, level 1 recall and the same winners, then package a precision option; estimated gain 100 to 160 s of 531 s, unmeasured; waits for the owner's go.
answers: What would FP16 and TensorRT change in the first fix; which route and dependency; what accuracy bar must pass before adoption; which stages, checks and time estimates; what could go wrong; what is decided by the owner
---

# MegaLoc in FP16 and on TensorRT: plan

Draft 2026-11-02, run the same day: stages M0 to M5 are done and M6 was tried and rejected; the
numbers are in
`megaloc-fp16-tensorrt-results.md`. Evidence: `photo-only-first-fix-f7-results.md`.

Changes against the draft, from the runs:

- The cached level 1 set is 14,520 views (12 headings), not 7,260.
- The ONNX Runtime TensorRT provider cannot build the graph (`ScatterND` `reduction` attribute);
  the engine is built with `xfeat-trt`'s builder on a graph with the batch fixed at 32, so
  `xfeat-rt` is unchanged and stays at batch 1.
- Conversion and the engine build are offline (`satmesh-locate-export`); the describer only
  loads a file.
- The gate is the outcome (fused recall, Jaccard of the place sets, the same winners), not the
  descriptor cosine; the owner accepted the drift.
- Adopted route: the engine; the FP16 graph on the CUDA provider is the fallback.

## Why

- On the 2.5 km store, no priors, the first fix takes 531 s. MegaLoc inference is 53 % of the
  profile (about 8.3 ms an image of GPU time, FP32 graph on the CUDA provider, batch 32), and its
  CPU preprocessing now hides behind it.
- Describing is 241 s of the run (25,848 views); rendering is 171 s. Cutting describe to a third
  saves about 160 s; to a half about 120 s. Both are estimates: no FP16 number exists for this
  graph. The nearest evidence is `xfeat-rt`, where FP16 LighterGlue ran 2.7 times faster than FP32
  at 4,096 keypoints on this card.
- Once describing is shorter than rendering the run is render-limited. Overlapping render with
  describe failed in F7 because both compete for the GPU; a lighter describe may change that and is
  retried at the end.

## Facts the plan rests on

- The graph (`megaloc.onnx`, 671 nodes) is FP32 with a dynamic batch and a 322 x 322 input. Its
  operators include `LayerNormalization`, `Einsum`, `Erf`, `Softmax`, `ReduceLogSumExp`,
  `ScatterND` and `ReduceL2`.
- `onnxruntime.transformers.float16.convert_float_to_float16` ships in the installed
  `onnxruntime-gpu` 1.31.1 (arguments `keep_io_types`, `op_block_list`, `node_block_list`). No new
  dependency is needed for the conversion. `onnxconverter-common` is not installed.
- TensorRT 11.4 is installed (the `tensorrt` extra). In TensorRT 11 the networks are strongly
  typed: FP16 comes from the tensor types in the ONNX, there is no builder flag
  (`xfeat-rt/agent-docs/c1-tensorrt-spike.md`). An FP16 engine therefore needs an FP16-typed ONNX.
- `xfeat_trt.engine` builds and caches engines from an ONNX file, keyed on the ONNX bytes, the
  TensorRT version, the GPU and the build options (`load_or_build_engine`). Its runner is written
  for XFeat's inputs; whether it takes a dynamic batch of 32 is not yet checked.
- The ONNX Runtime TensorRT provider is listed as available in this environment. It was not run;
  `xfeat-rt/agent-docs/research-03-runtimes.md` records its compatibility with TensorRT 11 as
  unverified.
- Batches of 64 or more run 5 times slower on the CUDA provider at FP32 (F7); FP16 halves
  activation memory and may move that cliff.
- The whole first fix peaks at 11.0 of 12.3 GB of GPU memory.

## Stages

| Stage | Does | Check | Estimate |
| --- | --- | --- | --- |
| M0 Probe | List the graph's operators by role (backbone, aggregator); create an ONNX Runtime TensorRT-provider session on the FP32 graph; read how `xfeat_trt` takes shapes | the provider loads or fails with a reason; the operator list names what must stay FP32 | 20 min |
| M1 FP16 graph on the CUDA provider | Convert with `convert_float_to_float16(keep_io_types=True)` and a block list for the aggregator (`ReduceLogSumExp`, `ScatterND`, `ReduceL2`) and normalisation if the first try drifts; time batches 8, 16, 32, 64 | cosine of each FP16 descriptor to its FP32 one on 2,000 real renders and the 20 photos: 0.999 or better; ms an image against 8.3 | 1 h |
| M2 TensorRT engine | Build an engine from the FP16 ONNX with a batch profile 1 to 32 (optimum 32), through `xfeat_trt` if it takes a dynamic batch, else through the ONNX Runtime provider with an engine cache; time batches | same cosine bar; ms an image; engine build time (one-off, cached); GPU memory | 1 to 2 h |
| M3 Retrieval gate | Describe the cached level 1 renders (7,260 views, `bexhill25/level1_h12`) in FP16, rerun the F2 fusion scores | K=1 and K=3 recall of the five-frame window equal to F2's (0.99 and 1.00) within one window of 77 | 30 min |
| M4 End to end | First fix on the 2.5 km frames 1 and 75 and Bexhill frame 1, no priors, against the F3 outputs; three timings of frame 1 | same winner and verification verdicts; places within a lattice step; winner within 1 m of the FP32 pose | 30 min compute, 1 h to read |
| M5 Package | A `precision` option on `MegaLocDescriber` with the FP16 graph or engine built once and cached by a key over the ONNX bytes, library versions and GPU; tests; docs; the CPU variant stays FP32 | tests pass on both variants; `make check`; descriptors from the packaged path equal M1's or M2's | 2 h |
| M6 Retry overlap | Render the next chunk while the previous is described, on the faster describer | gain or revert, outputs identical | 30 min |

Longest single run: the 2.5 km first fix, 10 minutes. Nothing approaches the one-hour cap.

## What could go wrong

- The aggregator uses a log-sum-exp normalisation; FP16 overflows past 65,504 and loses precision in
  sums. M1 keeps it in FP32 first and relaxes only if the cost justifies it.
- FP16 descriptors can match well pairwise and still reorder places that are close; M3 and M4 test
  the outcome, not only the cosine.
- A TensorRT build for a ViT takes minutes and an engine is tied to the TensorRT version and the
  GPU; the cache key covers both and an unreadable plan is rebuilt.
- A fused TensorRT engine hides per-operator precision; if M2 drifts, find the layer by comparing
  M1 (per-node control) with M2.

## Decisions for the owner

1. Adoption: FP16 changes the descriptors. The bar above (cosine, K=1 and K=3 recall, same winners)
   decides, and the descriptors differ from FP32 by design. Default stays FP32 until the owner
   accepts the M4 numbers.
2. Route: the CUDA provider with the FP16 graph (M1) if the TensorRT engine gains little over it;
   otherwise the engine (M2). The plan builds both and reports the gap before choosing.
3. A conversion with PyTorch (the weights are in the Hugging Face cache) is not planned: ONNX
   Runtime's converter needs no new dependency. PyTorch arrives with GeoCalib in F5 and could later
   export a mixed-precision graph if the converter's block list is not enough.
