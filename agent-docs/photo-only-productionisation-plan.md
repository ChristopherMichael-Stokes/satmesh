---
status: current
topic: evaluation
summary: Approved by the owner 2026-10-31. Plan to turn the photo-only experiments (P0 to P3) into a `satmesh track` command that takes ordered photos and a store and writes a pose file, a lens calibration and a report: a new `satmesh-track` package, the modules and signatures, MegaLoc on ONNX Runtime for the first fix, a local re-localisation search, a GTSAM lens graph with frame rejection, tests, stages T0 to T4 and forks for the owner. Lens: focal, k1 and k2 free.
answers: What will the photo-only pipeline look like as code; which modules and types does it have; which new dependencies does it need; how is the first fix found; how is a lost track recovered; which defaults and thresholds does it use and where do they come from; what stages build it and how is each checked; which forks wait for the owner
---

# Productionising the photo-only pipeline

Approved by the owner 2026-10-31 with the defaults of the four forks; the owner then asked for
optimisation once it is in. Evidence:
`photo-only-p0-results.md` to `photo-only-p3-results.md`; method: `photo-only-calibration-research.md`.
The re-localisation search is included at the owner's request (2026-10-31).

## Command

`uv run satmesh track PHOTOS --store DIR --out DIR [--start "LAT, LON" --radius-m M] [--focal-px F]
[--mesh-error-m 1.0] [--matcher xfeat|sift] [--order name|exif]` from `pipeline/`.

- Photos are ordered by file name (or EXIF time). Intrinsics are unknown: the principal point is the
  image centre, k1 and k2 are estimated (loose prior, sigma 0.3), the focal starts from a scan
  over 0.7 to 1.5 times a 70 degree field of
  view (or `--focal-px` as a loose prior).
- `--start` and `--radius-m` (the owner knows roughly where the first photo is) replace the global
  first-fix search by the cheap local search.
- Writes to `--out`: `poses.jsonl` (the pose-file schema of `eval localise`, with the estimated
  intrinsics, so the harness can score it), `calibration.json` (focal, k1, 3 x 3 covariance, photos
  used), `report.json` (per photo status, inliers, reprojection RMS, rejection and re-localisation
  events) and `review.html` (plan-view track, per-photo table, match panels for chosen photos).

## Package and modules

New workspace member `pipeline/packages/satmesh-track` (module `satmesh_track`), depending on
`satmesh-eval` for rendering, matching and the PnP solve (no code moves), `gtsam`, `onnxruntime`
(already through `xfeat-ort`), `pydantic`, `numpy`.

| Module | Holds |
| --- | --- |
| `lens.py` | `LensEstimate` (focal, k1, covariance), `fit_lens(frames, ...)`: GTSAM graph with a `Cal3Bundler`, a pose per photo, points with priors at the lifted position, Huber loss, loose priors; `reject_frames(...)`: robust z of reprojection RMS and position-jump peaks, then re-solve |
| `tracker.py` | `track(photos, scene, matcher, config) -> TrackResult`: constant-velocity prediction, render, match, solve; on fewer than 30 inliers calls `search.py`, on a second failure stops with the photos found so far |
| `search.py` | `local_search(...)`: grid around a centre (radius = margin + 1.2 x step x missed steps, 70 m spacing, heights 0.7/1.0/1.4 of the last, 8 headings), ranking by match count, verification of the top 5; `global_search(...)`: the store-wide grid ranked by `retrieval.py` |
| `retrieval.py` | MegaLoc descriptors on ONNX Runtime (322 x 322, fp32), a disk cache of the grid descriptors keyed by store and grid settings |
| `outputs.py` | pose file, calibration, report and review page writers |
| CLI | `satmesh track` in `satmesh-cli`, a thin call into `track` |

Types are frozen dataclasses: `Lens`, `LensEstimate`, `FirstFix`, `TrackedPhoto` (name, pose,
inliers, residual, status), `TrackResult` (lens, photos, rejected names, search events). Pure
functions take scenes and a matcher as arguments; the CLI owns files and logging.

## Defaults and where they come from

| Constant | Value | Origin |
| --- | --- | --- |
| Minimum inliers | 30 | `harness-results.md` (H2) |
| Grid spacing, heights | 70 m, 25/50/100 m ladder | P0 basin (50 m offsets at 25 m up), P1 scale gap (2 times) |
| Rejection threshold | robust z of 4 | P3, set on three corrupted frames, not tuned further |
| Pixel sigma, Huber k | 2.0 px, 1.345 | P2 (2.4 px residual), standard Huber constant |
| Mesh error sigma | 1.0 m, `--mesh-error-m` | Assumption: DSM and Esri misregistration were 0.5 to 2 m; P2 showed this value must carry the mesh error. Unmeasured, to be measured on real photos (H3) |
| Focal prior | 30 % of the scan value | P2: tighter priors centred on the scan hurt |
| Lens model | focal, k1, k2 (principal point fixed at the centre) | Owner asked why k2 was ignored; with a strong barrel lens fixing it cost 0.6 % focal and 20 % of k1, with a 100 degree lens 2.1 % focal, and freeing it cost nothing on the near-nadir flight (`photo-only-p2-results.md`) |

## Dependencies

- `gtsam` (BSD, wheels for Python 3.13 on Linux x86, aarch64 and macOS): approved by the owner.
- MegaLoc ONNX weights (MIT, 458 MB, from Hugging Face `gberton/MegaLoc`) read through ONNX Runtime;
  no torch. Matches torch to cosine 0.99999 or better; 0.64 s per image on CPU at 322 x 322;
  ranking as good as the 434 x 322 torch run on the P1 queries (16 of 18 within 1 m).
  Weights are a build output like the XFeat exports: read from `MEGALOC_MODEL` in tests and the CLI.
- TensorRT stays an optional later backend for the matcher; not in this plan.

## Stages

| Stage | Delivers | Check |
| --- | --- | --- |
| T0 | Package, `lens.py` with tests | Project points through a known lens with an independent forward model (OpenCV `projectPoints`) and recover focal and k1; a corrupted frame is rejected and the lens unchanged; covariance grows when the views are near nadir |
| T1 | `tracker.py`, `search.py` (local) with tests | Synthetic flight over the test scene with a lens: tracked, lens recovered; a gap longer than one prediction recovered by the local search |
| T2 | `retrieval.py`, `global_search` with tests | The first fix of the slice flight within 1 m from no prior, with `MEGALOC_MODEL` set; cache hit on the second run |
| T3 | CLI, outputs, review page | `satmesh track` end to end on the P2 and P3 flights of the slice store: focal within 1 %, poses within 1 m, gap recovered; `make check`, `make test` pass; docs, AGENTS.md command table, results doc |
| T4 | The full method report | The report with illustrative examples (the owner's next item) |

## Not in v1

True fisheye lenses (field of view beyond about 110 to 120 degrees; the radial polynomial and
the pinhole-only renderer both stop working there, so they need `Cal3Fisheye` and rectilinear
sub-view renders; the command warns when the estimated field of view passes 110 degrees),
hierarchical global search for areas of several kilometres (the grid is flat: 3,900 renders on the
slice; first run of the descriptor cache is about 42 minutes on CPU), sliding windows (the whole
sequence is one graph), the motion prior, TensorRT, lens terms beyond focal, k1 and k2.

## Forks for the owner

1. Package: a new `satmesh-track` member (default), or inside `satmesh-eval`.
2. Global first fix cost: accept about 42 minutes of CPU on first use of a store area (cached), with
   `--start` as the cheap path (default), or add a GPU/TensorRT descriptor path in v1.
3. Mesh error default 1.0 m: accept until real photos measure it.
4. Output pose file reuses the `eval localise` schema (default), so a track can be scored against
   logged poses with the existing command.
