---
status: current
topic: evaluation
summary: MegaLoc first-fix trial on the Bexhill store with no pose prior (22,440 renders over 1.5 x 1.2 km, described on the GPU in 218 s): the truth cell ranks 1st to 7th for oblique frames (pitch -25 to -28) and 28th to 141st for steeper, closer frames; a height or heading hint changes the rank little; refining the top 6 places and tracking 12 frames from each (a multi-hypothesis check) separates right from wrong places and located the camera from frames 1, 20, 40, 60 and 75; adding a pitch -50 grid located frames 85 and 90 too.
answers: Does MegaLoc find the first fix on real drone footage; how much height or heading hint error is tolerated; how many candidate places must be verified; do wrong hypotheses fail when tracked; why did a good first fix make track fail on its first photo; what does it cost; what is unproven
---

# MegaLoc first fix on the Bexhill clip

Run 2026-11-01. Store, clip and tracker: `photo-only-bexhill-results.md`. Truth for each test
frame is
the pose the tracker recovered from the telemetry-seeded run (`run6`), itself 3.9 m median from the
1 Hz GPS. Scripts and scratch (7.3 GB of renders, descriptors, JSON): `uncommitted/photo-only/bexhill/`
(`scripts/render_grid.py`, `truth.py`, `megaloc_eval.py`, `hypotheses.py`, `megaloc/`).

## Method

- Grid: positions every 70 m over the store (1.5 x 1.2 km, 22,440 renders in 199 s), heights above
  ground 40, 55, 72, 90, 110 m, headings every 30 degrees, pitch -35, nominal 70 degree lens, 322
x 322
  views. UAVD4L renders a database the same way (arXiv 2401.05971); the heights and spacing are
ours.
- MegaLoc (ONNX) on the GPU: 8.6 ms an image with the CUDA provider in a throwaway environment with
  `onnxruntime-gpu[cuda,cudnn]` 1.31.1 (the project still uses the CPU `onnxruntime`, 0.64 s an
image);
  the grid took 218 s.
- Hypotheses: greedy non-maximum suppression of the ranked cells to places 100 m apart, the top 6;
  each place refined by a local grid (70 m radius, 35 m spacing, three heights, pitch -45, -35, -25,
  headings +-30 degrees), the best 5 by match count verified by PnP, then `track` on 12 frames (6
s).
  Scoring hypotheses by how well they track is the unproven combination here; the pieces are
  established (retrieval by render descriptors, PnP verification, sequence tracking).

## Rank of the truth cell (no hint, 22,440 candidates)

| Frame | Pitch | Rank of the best cell within 60 m and 15 degrees | Nearest of the top places |
| --- | ---: | ---: | --- |
| f001 | -26 | 1 | 19 m, first |
| f020 | -25 | 1 | 42 m, first |
| f040 | -28 | 7 | 75 m, second |
| f060 | -28 | 6 | 87 m, third |
| f075 | -27 | 28 | 31 m, third |
| f085 | -42 | 85 | 67 m, first |
| f090 | -41 | 141 | 64 m, third |

- Height hint error: with the database at one height (no heading hint) the rank of the truth cell
  was
  1 to 20 for f001, 1 to 9 for f020, 1 to 24 for f040 and 1 to 31 for f060 over heights of 40 to
110 m
  against a truth of 64 to 74 m, so a height 30 m off cost at most about 30 places; for f075 to f090
  it was 17 to 355, the best at 40 and 110 m, the worst at 55 to 90 m (the truth is 51 to 57 m).
- Heading hint: restricting the database to a window of 15 degrees around the true heading instead
  of
  all 12 headings improved the rank by a factor of 1.5 to 5 (f060 at 72 m: 19 to 6; f075 at 55 m:
  198 to 43). The hint is worth having but retrieval works without it.
- The top place is a wrong place most of the time even when the truth is near: f040 first place is
  147 m away, f060 115 m.

## Hypotheses refined and tracked (top 6 places)

| Frame | Places that located the camera | First-fix inliers | Tracked 12 frames, median inliers |
| --- | --- | --- | --- |
| f001 | 1 and 5 (133 m away converged to the same spot) | 388, 295 | 12 of 12, 548 and 530 |
| f020 | 1 and 3 | 320, 34 | 12 of 12, 192 and 181 |
| f040 | 1 and 2 | 47, 813 | 12 of 12, 540 and 484 |
| f060 | 1 and 3 | 309, 526 | 12 of 12, 497 and 502 |
| f075 | 1 and 3 | 43, 351 | 12 of 12, 208 and 242 |
| f085, f090 | none | 5 to 23 | |

- Of the 20 wrong places in f001 to f075, 18 gave under 30 inliers (no fix); two (f020) gave a fix
  with 30
  and 33 inliers 184 m and 408 m from the truth, and the tracker failed on both (tracked 0 of 12).
Tracking is a clean separator: every right hypothesis tracked 12 of 12 with
  a median of 180 inliers or more.
- Time: 16 s for a place without a fix, about 20 s to 80 s with tracking; 6 places take 1.5 to 3
  minutes
  on TensorRT.
- A place 133 to 195 m from the truth often converges to the truth because the PnP solve is not
  limited to the grid cell, so far places are not always wasted.

## Trap found: a fix at the wrong focal is biased

The first fix at f075 had 351 inliers but 10.3 px residual, and re-rendering at that pose with the
same nominal focal got 14 inliers; at 0.9 times the focal the same pose got 200. `track` localised
its
first photo once at the nominal focal and refused it. Fix (`tracker.py`): the first photo is
localised
at 0.8, 0.9, 1.0, 1.1 and 1.2 times the nominal focal, the attempt with most inliers is used, and
the
follow loop takes it as photo 0's fix instead of localising again. First-fix positions of 8 to 15 m
from the truth in the table come from the same bias; the lens graph refines them.

## Second grid at pitch -50

A second grid of 22,440 renders at pitch -50 (same cells), described in 226 s, joined the first
(44,880
cells; `megaloc_eval2.py`). Rank of the truth cell, no hint:

| Frame (pitch) | Pitch -35 grid | Pitch -50 grid | Both |
| --- | ---: | ---: | ---: |
| f001 (-26) | 1 | 41 | 1 |
| f020 (-25) | 1 | 6 | 1 |
| f040 (-28) | 7 | 1 | 2 |
| f060 (-28) | 6 | 20 | 16 |
| f075 (-27) | 28 | 57 | 39 |
| f085 (-42) | 85 | 21 | 21 |
| f090 (-42) | 141 | 12 | 12 |
| f100 (-43) | 9 | 1 | 1 |

Hypotheses on the combined grid (top 6 places, refinement pitch +-10 degrees around the cell's):

- f085: the first place (33 m from the truth) fixed with 187 inliers and tracked 11 of 12 frames,
  median
  289 inliers.
- f090: the first place (36 m) fixed with 276 inliers and tracked 7 of 12 frames, median 126.
- f100: the first place (49 m) gave a weak fix, 33 inliers 32.5 m from the truth, and `track`
  rejected its
  first photo; the other five places gave nothing.
- No wrong place gave a fix in these three frames (all under 30 inliers).

A grid at both pitches costs twice the renders and descriptors; the steep frames needed it, and the
shallow ones lost at most a few ranks (f060 6 to 16, f075 28 to 39).

## End to end, 2026-11-01

`uncommitted/photo-only/bexhill/scripts/e2e.py` runs build, correct, both grids, MegaLoc and the
hypotheses plus a full track from an empty directory (`uncommitted/photo-only/bexhill-e2e/`):
1,386 s
(23.1 min), 1,009 s of it per-store set-up. Stages in seconds: build 45, correct 57, render 221
and 247,
MegaLoc 439 (describing 44,880 views 436), hypotheses and tracking 377 (six hypotheses 100, tracking
110 photos 269 of which the 17 local searches are nearly all, 10,068 search renders). Result: 92
tracked,
6 relocalised, 1 rejected, 11 lost; 99 frames compared with the GPS at 3.5 m median. Winner: place 1
(388 inliers, 12 of 12 tracked); place 6, 133 m away, also converged. Caveat: frame 108 was
relocalised
by the local search 90 m from the log (every other frame under 10 m), a wrong recovery that the 30 m
prior gate does not cover because the search path accepts any fix with 30 inliers. The report page
is an
artifact (<https://claude.ai/artifact/BWzqStxCzY1GM3Cw7wNATg>; built by `scripts/e2e_report.py`).

Fix and rerun: a recovered fix must lie within 3 typical steps per missed photo plus 15 m of the
last fix
(`search.py`, `tracker.py`; `decisions.md`). Same winner, tracking again from the e2e store (pre-
gate files
in `bexhill-e2e/track_before_gate/`): 92 tracked, 5 relocalised, 1 rejected, 12 lost (frame 108 is
now
lost); 98 frames compared with the GPS, 3.5 m median, 9.2 m worst (was 89.8 m). Tracking took 284 s.
Tests 30 passed, 2 skipped.

## Open

- f100 gave only a weak fix; frames 95 to 110 of the clip are the near-nadir chapel-yard views the
  tracker also loses. The owner's rough height and heading hint shrinks the
  candidate set (a heading window of 15 degrees keeps one in twelve) and improves the rank modestly.
- The grid is one store of 1.5 km; a region is 100 to 10,000 times larger. Rendering cost 9 ms a
  view
  and MegaLoc 10 ms, so a 10 km square at this spacing and heights is about 24 million views.
- Only seven frames of one clip; truth is the tracker's own pose.
