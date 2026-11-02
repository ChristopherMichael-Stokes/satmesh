---
status: current
topic: evaluation
summary: F3 of the first fix with priors, packaged in satmesh-track and run on the Bexhill clip: one process renders, describes with MegaLoc in chunks, fuses five frames by estimated yaw offsets, ranks two levels, verifies six places by tracking 12 photos and widens the priors when nothing verifies; Bexhill frame 1 and the 2.5 km frames 1 and 75 end 14 to 19 m from the tracker pose with and without right priors, a wrong heading prior recovers through the ladder, peak GPU 11.6 of 12.3 GB, events cost under 0.01 % of the run.
answers: Does the packaged first fix find the same winner as the scratch two-stage runs; what do priors save; does a wrong heading prior recover; how long does each stage take against the scratch runs; how much GPU memory and RAM does one process need; what does writing events cost; which choices were made in the build and which traps were found
---

# F3: prior-aware first fix in satmesh-track

Run 2026-11-02. Plan: `photo-only-first-fix-plan.md`. Code in
`locate/packages/satmesh-track/src/satmesh_track/`: `priors.py` (settings, TOML and `CENTRE+-HALF`
loaders), `yaw.py` (F1 port), `grid.py` (level views, fusion), `first_fix.py` (orchestration, ladder,
events), `cli.py` (`--priors`, `--heading`, `--pitch`, `--height`, `--start`/`--radius-m`;
`events.jsonl` in `--out`). Harness (scratch): `uncommitted/photo-only/f3/run_fix.py` (first fix only,
20 photos, peak RAM and GPU, event write time) and `events_summary.py`; outputs and logs in
`uncommitted/photo-only/f3/<run>/` and `<run>.log`. Truth is the tracker pose of the first frame
(`bexhill-e2e/track/poses.jsonl`), compared as geodetic distance.

## Acceptance

| Run | Store, first frame, priors | Winner from tracker pose | Winner rank, inliers, tracked | First fix time | Notes |
| --- | --- | ---: | --- | ---: | --- |
| a | Bexhill, f001, none (`satmesh-track` CLI, whole clip tracked) | 17.1 m | 1, 388, 12/12 | 430 s | clip: 92 tracked, 5 relocalised, 1 rejected, 12 lost, as the scratch run |
| b | Bexhill, f001, heading 30+-45, circle 150 m centred 50 m off | 17.1 m | 1, 388, 12/12 | 167 s | level 1 140 views, level 2 3,150 |
| c | 2.5 km, f001, none | 18.6 m | 2, 421, 12/12 | 573 s | level 2 rank 1 was 1,037 m off (9 inliers, rejected) |
| c | 2.5 km, f075, none | 14.5 m | 4, 99, 12/12 | 747 s | rank 2 (92 m place, 231 inliers) also tracked 12/12; rank 4 won on median inliers |
| d | Bexhill, f001, heading 88+-45 (60 off) | 17.8 m | 4, 290, 12/12 | 201 s | verified without the ladder: the window edge (60) plus the +-30 refinement reached 28 |
| d2 | Bexhill, f001, heading 88+-15 (60 off) | 17.1 m | 1, 388, 12/12 | 565 s | no place verified in the window (146 s); `PriorRelaxed` heading 15 to 180; the full search gave the run a winner |

Scratch reference: Bexhill frame 1 two-stage winner 20 m, 388 inliers, 12 of 12; 2.5 km nearest
final place 66 m (rank 2) for f001 and 41 m (rank 1) for f075, never verified.

## Cost (2.5 km, frame 1)

| Stage | Views | Seconds | Render / describe | Scratch |
| --- | ---: | ---: | --- | --- |
| Level 1 | 5,808 | 113 | 47 / 65 | 7,260 views, 143 s (render then rank, separate processes) |
| Level 2 | 20,040 | 339 | 125 / 215 | 21,840 views, 390 s |
| Verification, 6 places | 6 x 585 | 105 | | 100 s (refine) |

- Level 1 has 48 views a position (12 headings, 2 heights, 2 pitches), not the 14,520 of the brief:
  that count was 5 heights; the plan's level 1 is heights 90 and 110 only.
- One process: peak GPU 11.6 GB of 12.3 (whole card, about 2.4 GB of it other processes), peak RAM
  4.9 GB. No chunking change needed; chunks are 256 renders (about 180 MB).
- Events: 428 to 455 a run on the 2.5 km store, 0.02 s writing in all (under 0.01 % of the run);
  cell batches at least 0.1 s apart.
- Level 2 dominates (60 to 75 % of the time); describing is 60 % of each level. F7's profile
  starts there.

## Choices made in the build

- Level stages are `level N: render and describe` (render and describe interleave by chunk; their
  split is in the stage times) and `level N: rank`, plus `yaw offsets`, `describe photos`,
  `verification`.
- Cell similarity and level 1 candidate similarity are the fused score (sum over up to five
  frames), so level 1 values run to about 1.25 and level 2 values to about 0.25.
- The level 1 heading window widens by the largest offset after rounding to the 30 degree lattice.
- A height prior whose lower end exceeds 90 m raises both coarse heights by the same amount.
- A run with fewer photos than `min_tracked_photos` needs all of them tracked.
- The `RunStart` level 2 plan is an upper bound (five places, every lattice point within 250 m).
- `satmesh-locate rank` stays: AGENTS.md and `test_megaloc.py` use it.
- The TOML position prior is in store ENU metres (the event model); `--start` takes latitude and
  longitude.

## Traps

- The essential matrix collapses to zero yaw at short baselines: synthetic pairs 1 to 2 m apart at
  100 to 400 m depth returned 0 degrees for a 9 degree turn (pure-yaw homography exact). On the clip
  it was fine (F1); a hovering start would fuse with wrong offsets. `agree` guards this at the cost
  of falling back to one frame.
- A wrong heading window does not always fail: with +-45 the window edge sits 43 degrees from the
  truth and the verification refinement adds +-30, so the window catches it.
- zsh does not split a command held in a variable (`$R args`): exit 127 with nothing run.
- The first fix's pose is the verification's first-photo pose solved at the nominal focal (as the
  scratch driver returned it), so it carries the focal bias: 11.7 m on the synthetic town, 14 to
  19 m here; `track` rescans the focal. The synthetic test checks it against the tracker's 30 m basin.
