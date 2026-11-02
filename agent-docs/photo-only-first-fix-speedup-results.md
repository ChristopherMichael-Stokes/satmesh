---
status: current
topic: evaluation
summary: Benchmark of the first fix with the MegaLoc engine (2.5 km store, frame 1, no priors: 358 to 404 s, winner unchanged) and three F7 follow-up experiments on top of it, all opt-in settings that default to the old behaviour: restricting level 2 headings to one lattice step around the level 1 place's heading cut 400 s to 254 s with the same fix, dropping hopeless places after a 65-pose screening cut verification by about 44 s and the run to about 237 s, and stepping the heading widening was measured, saved 12 s when the first step sufficed and cost 62 s when it did not, and was removed. On the held-out clips (Old Sarum, Kenilworth, Penshaw) the first two were overfit to Bexhill: Kenilworth lost its fix, so they stay off and the defaults stay exhaustive; Penshaw finds no fix with the defaults (pitch grid).
answers: What does the first fix cost now and where does the time go; what did restricting level 2 headings, early drop in verification and stepped heading widening each gain and risk; how were they tested; which cases could break them; how the first fix did on Old Sarum, Kenilworth and Penshaw; what is left in the run; what waits for the owner
---

# First fix after the engine: benchmark and three follow-up experiments

Run 2026-11-02. Builds on `megaloc-fp16-tensorrt-results.md`. Scratch (gitignored,
`uncommitted/photo-only/f7/` and `m/`): `bench.sh`, `e3.sh`, `e1.sh`, `e2.sh` (run lists),
`e1_counts.py` and `e1_*.npz` (match counts of every refinement pose), per-run directories.
Machine as in `photo-only-first-fix-f7-results.md`; the card also carried 26 to 39 % load from
outside WSL during the later runs (the monitor map open in a Windows browser is the likely source),
so each experiment alternates its two arms.

## Benchmark (engine, 2.5 km store, frame 1, no priors, 20 photos)

| Run | Total s | Level 1 | Level 2 | Verification |
| --- | ---: | ---: | ---: | ---: |
| 1 (monitor attached) | 377.8 | 63.7 | 185.0 | 111.0 |
| 2 | 358.4 | 63.3 | 172.6 | 104.7 |
| 3 | 404.0 | 74.9 | 200.9 | 109.9 |

- Same fix every time (18.6 m from the tracker, 421 inliers); only the rank label of near-ties moves.
- Noise between runs reached 12 % (the earlier engine runs were 350 and 347 s). Level 2 render
  (132 to 158 s) is the noisy stage; describe is steady (41 to 43 s).
- Time splits (run 2): setup 7 s, level 1 63 s, level 2 173 s, verification 105 s.

## Restricting level 2 headings (`fine_heading_steps`)

Level 2 renders every one of 12 headings at every fine position (120 views). The setting renders,
at each fine position, only the headings within N lattice steps (30 degrees each) of a level 1
place within the fine radius; N = 1 keeps 3 headings from one place.

- Evidence it is safe: in the 8 distinct scenarios on disk, every winner and every accepted place has
  a heading within 0 or 1 steps of a level 1 place within 250 m; only places later rejected sit 3
  or 4 steps away. The same scenarios are three footage cases, so this is thin.
- Four alternating runs, 2.5 km frame 1, no priors:

| Arm | Total s | Level 2 s (render / describe) |
| --- | --- | --- |
| Unrestricted | 407.8, 398.1 | 206.9 (165.1 / 41.8), 203.4 (161.6 / 41.8) |
| N = 1 | 264.1, 243.8 | 56.9 (45.2 / 11.7), 50.2 (39.1 / 11.1) |

- Same winner (rank 3, 18.6 m, heading 27.6), same top four places and inliers; ranks 5 and 6
  are other weak places. Gain 149 s (37 %).
- Risk: a winner whose best heading is two or more steps from every nearby level 1 place's would be
  missed. None occurs in the data above; a case that does turns up as a failed pass, which the
  ladder then widens.

## Early drop in verification (`refine_screen_min_matches`)

Verification refines each of six places by matching the first photo with 585 renders (3 heights, 3
pitches, 5 heading offsets, 13 positions; 17 to 20 s). `e1_counts.py` recorded the match count of
every pose for the 20 places of three scenarios (2.5 km frames 1 and 75, the 1.5 km slice):

- The best pose's count is 73 to 477 for the 9 accepted places and 13 to 39 for the 11 rejected.
- A screening subset of 65 poses (all positions, the place's own height and pitch, all heading
  offsets, 11 %) gives at least 32 for accepted places and at most 24 for rejected ones. The
  setting drops a place whose subset best is below its value; 28 is a tunable chosen from these
  20 places.
- Four alternating runs (both arms with N = 1), 2.5 km frame 1:

| Arm | Total s | Verification s |
| --- | --- | --- |
| Heading restriction only | 285.6, 260.8 | 120.3, 118.2 |
| Plus screening at 28 | 244.1, 229.9 | 78.0, 72.6 |

- The three hopeless places stop after 65 poses in 2.4 to 2.8 s instead of 17 to 20 s. Kept places
  take 4 to 5 s longer, because the 65 screening poses are rendered twice; reusing the counts
  would remove that.
- Frame 75 with both settings: 281.3 s (465.1 s before), same winner (rank 4, 14.5 m, heading
  138.4, 99 inliers). Verification 140.7 s, of which 91 s is tracking 12 photos in the two
  accepted places (37 and 54 s).
- Risk: an accepted place whose best screening pose has few matches (pose offsets, repeating
  texture) is dropped. In the 9 accepted places the lowest is 32.

## Stepped heading widening (removed)

The ladder went from a heading prior straight to the full circle. A setting tried half-widths 45
and 90 in between (both settings above on; 1.5 km store, 150 m circle, heading prior 88+-15 and
128+-15, truth 28):

| Heading prior | Straight to 180 | Stepped 45, 90, 180 |
| --- | --- | --- |
| 60 degrees off | 125.4, 133.2 s, 2 passes | 114.0, 119.9 s, 2 passes |
| 100 degrees off | 120.0 s, 2 passes | 182.6 s, 3 passes |

- It saved 12 s when the first step contained the truth and cost 62 s when it took two steps. With
  the other two settings a pass costs about 60 s, so a ladder step has little left to save. The
  code was removed. At 60 degrees off the two ladders reach different winners (14.2 m and 17.8 m
  from the tracker, 28.4 and 27.3 degrees).

## Not done

- Reusing the screening counts in the full refinement (about 2 s a kept place).
- Tracking time in verification (3 to 4.5 s a photo, 12 photos a kept place): the largest part of
  verification once the hopeless places are dropped.
- Level 1 (63 s, 5,808 views): its cost is positions times 12 headings times 2 heights times 2
  pitches; not examined.
- Repeating each experiment on other footage; the evidence is the Bexhill clip.

## Held-out clips (2026-11-02)

Engine, 3 km stores centred on the sites, first photo from a chosen second (frame 0 is poor on every
clip), start prior 1,000 m, no heading, pitch or height prior, 20 photos given to the fusion, GPU
shared with other runs for some arms (timings inflated, outcomes not).

| Clip (start frame) | Defaults | Both settings on | Heading restriction only |
| --- | --- | --- | --- |
| Old Sarum (4 s) | fix, rank 1, 12 of 12 tracked, 333 s | same pose within 7 m, 0.3 degrees heading, 4 degrees pitch; 227 s (-32 %); the screening dropped a place that tracked 11 of 12 | not run |
| Kenilworth (4 s) | fix, rank 3, 10 of 12 tracked, 818 s (verification 558 s) | no fix, 254 s: the screening dropped all six places, two of which the defaults verified at 10 of 12 | no fix: right places, true headings never rendered, 0 of 12 tracked at all six, then the area ladder re-ran the grid |
| Penshaw (38 s) | no fix, 849 s: six places all around the monument, 0 of 12 tracked, best first-photo inliers 35 | not run | not run |

- Both settings are overfit to Bexhill. The match threshold of 28 came from 20 Bexhill places;
  Kenilworth's true places fall below it. The heading restriction assumes level 1's best heading is
  within one step of the truth; at Kenilworth it is not. The ladder only widens the area when no
  heading prior is set, so it cannot undo the restriction. Defaults stay exhaustive.
- Penshaw: the places are right (every candidate straddles the monument) but the level 2 views are
  all at pitch -35 degrees and 110 m, and verification refines pitch by only +-10 degrees. The
  photo looks across at the horizon at a much shallower pitch, so no candidate or refinement can
  reach it. The pitch grid, not the lighting alone, is the likely cause.
- The Penshaw store first built from the coordinates in `uk-drone-footage.md` (from memory) was
  about 4 km from the monument (54.8831, -1.4809 from a web search); the monument was outside it.

## Waiting for the owner

- Heuristics that hold on all four clips and then on the owner's own footage. The speedups stay
  opt-in meanwhile.
