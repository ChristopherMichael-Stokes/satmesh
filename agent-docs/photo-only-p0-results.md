---
status: current
topic: evaluation
summary: P0 of photo-only pose recovery on synthetic slice photos: a render pose up to 20 m off always localises and 50 m mostly (100 % at 50 m or more above ground), 100 m and 200 m fail often and 16 of 448 trials were accepted over 5 m wrong; 45 degree heading offsets never matter; focal length is unobservable for straight-down photos and well-conditioned at 30 degrees or more off straight down.
answers: How far can a start pose be from the truth before render-match-PnP fails; does heading offset matter; how dense must the first-fix render grid be; can the 30-inlier gate catch wrong fixes; when is focal length observable from the matches; what does a wrong focal length cost in position
---

# P0 results: basin of convergence and focal observability

Run 2026-10-31. Plan: `photo-only-plan.md` (P0); method: `photo-only-calibration-research.md`.
Review page: <https://claude.ai/artifact/C4uaQpGaBf2zY5Hpjopk8H> (private); scripts, data and page in
`uncommitted/photo-only/p0/`.

## Setup

- Slice store of the S0b cross-check site (49 leaves, 1.27 km square, ground relief std 9 m),
  1280 x 960, 70 degree field of view, range 500 m, `GpuRenderer`, XFeat with LighterGlue, surface
  reference. The photo is a full-surface render at the true pose, so this is an upper bound.
- 16 poses: 10, 25, 50, 100 m above ground, headings N, E, S, W, pitch -25 degrees, camera at the
  slice centre.
- Success is an accepted fix within 1 m and 2 degrees of the truth.

## P0a: offset of the render pose

Per pose and size: 3 random horizontal directions for translation, both signs for heading. 448
localisations in 148 s.

| Offset | Trials | Within 1 m, 2 deg | No fix | Accepted, over 5 m wrong |
| --- | ---: | ---: | ---: | ---: |
| Heading 5 to 45 degrees | 160 | 160 | 0 | 0 |
| 5, 10, 20 m | 144 | 144 | 0 | 0 |
| 50 m | 48 | 42 | 5 | 1 |
| 100 m | 48 | 21 | 11 | 7 |
| 200 m | 48 | 0 | 40 | 8 |

- Height splits it: at 50 to 100 m above ground 50 m is 24 of 24, 100 m is 18 of 24 and 200 m is 0
  of
  24 (8 accepted over 5 m wrong). At 10 to 25 m, 50 m is 18 of 24, 100 m is 3 of 24, 200 m is 0 of
  24
  (all no fix).
- Pure heading offsets do not matter: the 70 degree view still overlaps the render. The search is
  over position.
- The 30-inlier gate (`MINIMUM_INLIERS`) does not catch the over-5 m fixes: they have 33 to 122
  inliers. The 367 good fixes have a median of 787 and a minimum of 59. A gate of 125 would reject
  all 16 wrong fixes and lose 4 good ones (150 loses 8, 300 loses 24). Synthetic photos share the
  render's texture, so real photos will have fewer inliers; the default stays 30 until real data
  says otherwise.
- Not tested: height, pitch and roll offsets; offsets near the store edge (the slice ends 635 m
  from the centre, so 200 m offsets at low height lose part of the view).

For cameras at 25 m and above (the scope, `photo-only-plan.md`), 50 m offsets were solved in 36
of 36 trials, 100 m in 19 of 36 (6 accepted over 5 m wrong) and 200 m in 0 of 36.

Implication for P1 (first fix by a grid of renders): the worst offset of a square grid is
spacing x 0.71, so a grid of about 70 m spacing has every pose within the 50 m basin for cameras
at 25 m and above. Grid heights and pitches were not varied here.

## P0b: focal observability

The photo has focal length 1.1 x nominal, the reference is rendered with the nominal focal at a prior
2.9 m off. Inliers come from a solve at the true focal (oracle), then the pose is re-solved for 81
focal values from 0.70 to 1.50 x nominal and the reprojection error recorded. Flat ground is the
bare earth flattened to one plane, the other world is the full surface. 4 photos per row (heights 50
and 100 m, headings N and S).

| World | Pitch (off straight down) | Focal range within 20 % of the best fit | Position error at the true focal | At 9 % low focal |
| --- | --- | ---: | ---: | ---: |
| Flat ground | 0 degrees | 73 % | 0.02 m | 6.8 m |
| Flat ground | 30 degrees | 6 % | 0.05 m | 8.1 m |
| Flat ground | 60 degrees | 2 % | 0.08 m | 11.5 m |
| Full surface | 0 degrees | 54 % | 0.05 m | 6.7 m |
| Full surface | 30 degrees | 6 % | 0.04 m | 7.9 m |
| Full surface | 60 degrees | 2 % | 0.06 m | 12.7 m |

- Straight down, the reprojection error barely changes with focal length (2.30 px at the true focal
  and at the nominal on flat ground), so focal length trades against height: a 9 % low focal
  puts the camera 6.8 m too low. On flat ground the minimum landed 36 % off the truth, at the
  edge of the scan; over buildings and trees the minimum was within 1 % but the valley is 54 %
  wide, which noise
  would move.
- At 30 degrees off straight down the valley is 6 % wide and at 60 degrees 2 %, with the minimum on
  the true value in all 16 cases, flat or not.
- A focal length 9 % off costs 7 to 13 m of position. Focal must be estimated, not assumed, and only
  tilted photos can estimate it.
- Not tested: distortion, noise beyond the render's, focal estimated from matches without the oracle
  inlier set, other fields of view.

## Decisions it supports

- The first-fix grid density follows the basin above: about 70 m for cameras at 25 m and above (P1).
- Calibration is pooled over photos at 30 degrees or more off straight down, then fixed for
  straight-down
  photos (P2).
