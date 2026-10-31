---
status: current
topic: evaluation
summary: Plan for recovering camera poses and calibration from ordered photos of a roughly known area: stages P0 to P4 that run the six experiments of the research on synthetic photos, in the order that settles the most per hour, with the dependencies and forks for the owner. H3 follows this work.
answers: In what order will photo-only pose recovery be built and tested; what does each stage settle; which stages need a new dependency; what synthetic flights test it; what are the success criteria; which forks wait for the owner
---

# Photo-only pose recovery plan

Owner order 2026-10-31: pose recovery and search come before H3 (the real-photo run), which tests
this work afterwards. Method and sources: `photo-only-calibration-research.md`. Harness it builds
on: `harness-plan.md`. Everything is tried on synthetic photos rendered from stores at known poses,
so error is measured against truth.

Unproven as a whole (named as such in the results doc and review pages): the joint pipeline. Parts
are established (MeshLoc, OrthoLoC, SeqSLAM, pycolmap focal estimation, GTSAM factors).

## Test flights

Fixed before any run, so the stages share them:

- Slice store (49 leaves, one location): 16 single poses (the altitude sweep), for P0.
- A flight of 40 photos along a smooth path (constant speed, gentle turns, 25 to 100 m above
  ground, pitch -25 to -45 degrees) over a larger store than the slice, so the area is not
  covered by a few renders. Photos get a lens: focal length and k1 unlike the nominal values.
- Failures injected on copies of the flight: 10 % photos with no usable content, a 30 % gap, a
  wrong-era texture (the reference colours shifted).

## Stages

| Stage | Settles | Needs | Done when |
| --- | --- | --- | --- |
| P0 | How far off a render pose can be and still solve (5 to 200 m, 5 to 45 degrees); whether focal length is observable at nadir, 30 and 60 degree pitch over flat and hilly ground, free against fixed focal | Existing code; focal by scanning a grid of values for the lowest reprojection error | Success rate against offset, and focal error against pitch and relief, in a results doc with a review page |
| P1 | The first fix with no prior: grid of rendered views against the first photos, ranked by raw XFeat inlier count; then voting across consecutive photos (Viterbi over top-k). Grid spacing 20, 50, 100 m | Existing code; a retrieval model (MegaLoc) only if inlier counts rank poorly | First-photo pose within 5 m on the test flight; recall against grid spacing and top-k |
| P2 | Tracking and calibration in a factor graph (owner's design, 2026-10-31): predict, render, match, solve per photo; then a GTSAM graph with one shared lens (focal, k1) and a pose per photo over fixed mesh-lifted points, robust loss on reprojection error, inliers reselected and refit; compared with per-photo solving at the nominal lens and with the true lens. The first fix comes from P1 (emulated here by the true pose plus the default prior offset) | `gtsam` (via `uv run --with` until production code needs it); `pycolmap` only as an optional focal baseline | Whole flight tracked; focal within 2 %, poses within 1 m; k1 error against the position error it causes; the marginal covariance says when the lens is determined |
| P3 | Robustness of the P2 graph: 10 % wrong fixes, 30 % missing photos, a gap, a different-era texture; motion-prior and between-pose factors; sliding window against batch | `gtsam` | Trajectory RMS and calibration error with and without the factors |
| P4 | Dropped: ground-level and low-altitude photos (under 25 m) are out of scope (owner, 2026-10-31). Different-era texture stays as a robustness check of P2 and P3 | none | Not run |

- P0 and P1 add no dependency and are the quickest; they decide whether retrieval and the graph are
  needed at all.
- Each stage ends in a results doc with measurements and traps, a decisions row, and an updated
  `status.md`. A review page where the result is judged by eye (match lines, trajectory against
  truth).
- Output of the finished pipeline: the pose file of `satmesh eval localise` plus a calibration file,
  with per-photo inliers, residual and, from P3, covariance.

## Scope

Cameras are at least 25 m above the ground (owner, 2026-10-31). Ground-level and low-altitude
photos are not a target; results below 25 m are ignored.

## Forks for the owner

1. Order and scope: run P0 and P1 first and stop for a review, or go through P3 in one pass.
   Default: stop after P1.
2. Calibration scope: focal length and k1 (OrthoLoC estimates focal only; k2 and the principal
   point held at the nominal values). Default: focal and k1.
3. Dependencies, asked when a stage needs them: `pycolmap` (P2), `gtsam` (P3), MegaLoc (P1, only if
   needed). `pycolmap` has no aarch64 wheel, which matters if the tool must run on ARM boards.
4. Test area for the flight: a store of at least 2 km across with repetitive built-up terrain.
   Default: the existing 5.4 km Ferrybridge store (`uncommitted/e4b/ferry-store`; 961 leaves, 5.3 GB
   of RAM to load).
