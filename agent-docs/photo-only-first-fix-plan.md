---
status: current
topic: evaluation
summary: Plan for a first fix from video with optional priors: intervals on heading, pitch and height, a feasible-set grid at level 1 and 2, several frames fused with estimated heading offsets, verification by mesh render or by the satellite imagery warped to the candidate view (for areas with no DSM), a widening ladder when a prior is wrong, native in the locate workspace; stages F1 to F7 with checks and time estimates, held-out UK footage, and the forks that wait for the owner.
answers: How will the first fix use priors from video; what are the stages and what does each check; which new dependencies and forks wait for the owner; how will the technique be shown to transfer; what will run at 5 km and 10 km and for how long
---

# First fix with priors: plan

Evidence: `photo-only-first-fix-priors.md`. Context: `photo-only-two-stage-recipes.md` (the Bexhill
runs, 2.5 km timings). Owner direction 2026-11-01: the feed is video; pitch, roll and altitude
can be estimated from it, heading mostly cannot; a human may pass inexact values in a config;
the imagery warp is kept for areas with no DSM; more UK footage is wanted as a held-out test.
Sufficient altitude means the horizon is visible looking ahead, at least about 50 m. Work stays on
the GPU where possible; the `cpu` variant of `locate/` is tested once per change to
`satmesh-locate`.

Related: the live map monitor for human users, `photo-only-live-ui-plan.md` (its event emitter lands
with F3).

## Progress

- F1, F2 and F3 done 2026-11-02 (`photo-only-first-fix-f1-f2-results.md`,
  `photo-only-first-fix-f3-results.md`). F7 done 2026-11-02
  (`photo-only-first-fix-f7-results.md`). F4, F5, F6 next.
- F7 follow-ups (owner decisions, none measured; counts from the wrong-prior run of 2026-11-02,
  465 s: pass 1 138 s of which 106 s verification, pass 2 327 s of which 212 s level 2):
  1. MegaLoc in FP16 on TensorRT (plan to be written; inference is 53 % of a run).
  2. Drop a hopeless place early in verification; verification is a fixed 105 s a pass for six
     places, and the Process tab shows why: refine (585 renders matched, 16 to 18 s a place) is
     nearly all of it, tracking is 1 s, so the early exit has to act inside the refine.
  3. Widen the heading in steps (45, 90, 180 degrees) instead of straight to the full circle.
  4. Restrict level 2 headings to a few lattice steps around each level 1 place's best heading
     (level 2 searches all 12 at every fine position today).
- Owner approved PyTorch and GeoCalib for F5 and store downloads for the held-out clips;
  Hergest Court is the sealed clip (`decisions.md`).

## Design

- Every prior is a centre and a half-width on one pose parameter (position radius, heading,
  pitch, height). A value from an estimator or from the config enters the same way; a config
  value gets a wider half-width. A missing prior is the full range.
- Search is built only over the feasible set. Level 1 renders and describes the coarse cells;
  level 2 the fine cells around the surviving places; verification keeps places by inlier count.
- A prior is a first try. When nothing verifies, the ladder relaxes one prior at a time (heading,
  then pitch, then area) and repeats. The measured brittleness of the heading window (a hint 30
  degrees off drops 2.5 km K=5 recall from 0.93 to 0.64) is why: windows are twice the stated
  error, and a failed verification relaxes the window before anything else.
- Several frames are fused at level 1: a candidate (position, heading) scores the sum of the
  frames' similarities, each frame at the candidate heading plus its estimated yaw offset from
  frame 0. Frames with spread-out offsets (20 to 90 degrees) are chosen over neighbours.
- Verification has two references. With a DSM: the mesh render (built). Without: the satellite
  imagery on the DEM, warped to the candidate view (the owner's technique; failed on the Bexhill
  clip at 51 to 74 m, never tried higher; the F4 check).
- Everything runs in one process in `locate/`: render (`satmesh-eval` renderer), MegaLoc
  (`satmesh-locate`), match and track (`satmesh-track`). No render files between steps.

## Stages

| Stage | Builds | Check (pass = ) | Time of the check |
| --- | --- | --- | --- |
| F1 Yaw offsets from video | relative yaw between frames from XFeat matches, OpenCV `findEssentialMat` and `recoverPose` with an approximate K, cross-checked with a rotation-only homography | on the 97 Bexhill frames the yaw difference to the tracker's is under 5 degrees (median) for pairs 2 s apart | minutes, GPU |
| F2 Fusion with estimated offsets | the fused level 1 score, frame selection, window size | 2.5 km store: K=1 recall at least 0.95 (single frame 0.73), K=3 at least 0.98, with F1's offsets; windows chosen not to overlap | minutes on cached descriptors |
| F3 Prior-aware search in `locate` | `Prior` intervals; feasible-set grids; level 1 at six headings and heights from 90 m up; level 2; the widening ladder; `first_fix` returning a start pose and a report; `satmesh-track` takes priors on the command line or from a config file | Bexhill frame 1 and the 2.5 km frames 1 and 75 give the same winner as the two-stage runs (`photo-only-two-stage-recipes.md`) with and without a right prior; a prior 60 degrees wrong still ends at the same winner after the ladder; tests at the public surface | build: code-strong agent; check about 30 min |
| F4 Imagery-warp verification | the flat-ground and DEM warp as a second reference in the verifier, chosen by whether a DSM exists | on the Bexhill frames it reproduces the recorded failure (median 1 match); on a held-out clip at 100 m or more above ground with a horizon it gives inliers within 5 m of the mesh result | minutes, needs the F6 footage |
| F5 Attitude estimators | GeoCalib for pitch and roll as intervals (adds PyTorch to `locate`) | on frames with a horizon: pitch and roll within 3 degrees of the tracker's; on frames without: its uncertainty flags them | minutes; fork below |
| F6 Held-out UK footage | two or three clips from the review list, probed; start location and, if supplied, `.SRT` as truth; frozen settings from F3 | the same settings locate the first frame and track at least 80 % of the clip; tuned on Bexhill only | download and probe: ask first; run under 30 min each |
| F7 Profile and optimise | following the `profile-optimise` skill (user-level, in `claude-config`): a sampling profile of the whole first fix on the 2.5 km run (render, readback, resize and normalise, MegaLoc, matching, tracking), then only the levers it supports: render and describe overlapped, resize and normalise on the GPU, MegaLoc on TensorRT FP16 or ONNX Runtime IO binding, batch size, numba or vectorised place ranking and fusion, preallocated buffers, caches for descriptors and fine renders | identical outputs (same winner, poses equal) on Bexhill frame 1 and the 2.5 km frames, with the profile before and after and each lever timed on a slice | profile minutes; each lever on a slice first |

- F7 follows F3 so the profile is of the packaged pipeline, not the scratch scripts. The likely
  costs (render and describe in sequence, a GPU to CPU round trip per render, ONNX Runtime CUDA
  for MegaLoc, numpy ranking) come from reading the code and are unmeasured.
- Altitude is not estimated at first. The measurement shows level 1 retrieval prefers database
  heights of 90 to 110 m for photos at 51 to 74 m, so a height prior only needs a lower bound; the
  single-image altitude models reach about +-30 % at best. The altitude estimators are revisited
  when F6 footage shows retrieval needing a height.
- Pitch is not a window at level 1: the nearest-pitch grid recalled no better than the other.
  Both pitches stay until the cause of the mismatch is found.
- Skyline matching against a DEM is dropped: it needs mountain relief and sky, and gives about 1 km.

## Scale ladder

Each step is run only after the one before passes, with its time estimated from the unit costs
(render 8 ms and describe 10 ms a view) and a slice tested first.

| Area | Level 1 views (24 a position) | Level 1 time | Needs |
| --- | ---: | ---: | --- |
| 2.5 km square, 6.25 km2 (built) | about 2,900 | about 1 min | built |
| 5 km square, 25 km2 | about 11,600 | about 4 min | downloads: ask |
| 10 km x 10 km, 100 km2 | about 46,600 | about 16 min, plus the store build, over the hour | ask; split into steps |

- 24 views a position = six headings, the two heights 90 and 110 m, two pitches, at 19.4 positions
  a km2 (280 m spacing) and 20 ms a view. Six headings and heights from 90 m were each measured to
  lose nothing; the combination was not.
- With a heading window of +-45 degrees (two of six headings) the 10 km square needs about 15,500
  views, 5 min.
- These are cost-model figures; the 5 km step is the first measurement.

## Waiting for the owner

- PyTorch and GeoCalib in `locate/` (F5): GeoCalib is Apache-2.0 code with CC-BY-4.0 weights; its
  focal output is weak and it is untested on aerial frames. Alternative: horizon line by classical
  methods in OpenCV, no new dependency, fragile.
- The footage list: which clips to download for F6 (list in the chat of 2026-11-01).
- Downloads for the 5 km store.
- The altitude estimator: deferred as above unless the owner wants it earlier.
