---
status: current
topic: evaluation
summary: First real-footage test of `satmesh track` on the Bexhill Cemetery drone clip (110 frames, 1920 x 1080, 15 to 70 s): the default start search found no fix, a finer search around the telemetry position localised frame 1 with 313 inliers, the original tracker followed 76 frames before losing the track at the gimbal pitching down, and after the lost-track search was changed to vary pitch and heading it locates 97 of 110 frames at 4.3 m median from the 1 Hz GPS; the first-fix grid and the last 16 frames are open.
answers: What killed the Bexhill track and how was it fixed; how does satmesh track do on real drone footage; why did the start search fail on the Bexhill clip; how close are the tracked poses to the DJI telemetry; what lens did it recover; where did tracking fail; how was the Bexhill store built and how long did it take
---

# Bexhill Cemetery real-footage test

Run 2026-11-01. Clip, telemetry and frames: `uk-drone-footage.md`. TensorRT, K 4096, RTX 4070 Ti.
Scratch: `uncommitted/photo-only/bexhill/` (`store`, `run3_first76`, `scripts/`); frames and
`telemetry.csv` in `uncommitted/photo-only/footage/bexhill-cemetery/`.

## Setup

- Frames: 2 a second from 15 s to 70 s, scaled to 1920 x 1080 JPEG (110 files, `f001` to `f110`).
- Store: `satmesh build --nw "50.8640, 0.4430" --se "50.8550, 0.4570"` (14 nodes, 12 leaves at z16,
  EA lidar composite DSM and DTM, Esri Vivid) took 48 s; `satmesh correct` took 70 s and left every
  node unchanged (2 cells, 9 roofs in the one scene, fewer than 10 needed).
- The render shows lidar-era tree spikes and a blurry texture; the cemetery looks like plain meadow
  from a distance.

## Results

| Step | Outcome |
| --- | --- |
| `track --start "50.8585, 0.4501" --radius-m 100` (216 renders) | no render localised frame 1 |
| same, `--radius-m 250` (888 renders) | none localised |
| Own grid, 30 m spacing within 150 m, headings 315 to 15 by 15, pitch -30/-40/-50, 72 m above ground | best 392 matches; frame 1 solves with 313 inliers at the GPS position, heading 15, pitch -30 |
| Tracker from that fix, 110 frames | tracked 75, lost at 75 and 76, three failed local searches at 77: aborted |
| Same on frames 1 to 76 (`run3_first76`) | 72 tracked, 1 relocalised (27), 3 lost (22, 75, 76); inliers median 466, minimum 51 |

- Lens (frames 1 to 76): focal 1500.8 px (sigma 4.8), horizontal FOV 65.2 degrees, k1 -0.027, k2 +0.066.
  No truth exists; k2 is likely poorly constrained (see `uk-drone-footage.md`).
- Against telemetry (73 poses, GPS interpolated at 0.5 s steps): horizontal distance median 5.4 m,
  max 13.4 m, inside the GPS's 7 to 11 m quantisation. Ellipsoidal height minus the telemetry
  height above take-off stays between 70.1 and 76.3 m (a constant offset is expected: take-off
  ground plus geoid).
- Reprojection RMS about 7.7 px at 1920 x 1080, higher than the synthetic flights; the 1 m
  mesh-error assumption is what the graph gets.
- Tracking costs about 0.035 s a frame on TensorRT.

## Why the default start search missed

The basin of the real first photo is narrow: the fix needed a heading within about 15 degrees
(search grid has 8 headings, 45 degrees apart, so the nearest is 15 degrees off only by luck),
position within about 30 m (grid spacing 70 m) and pitch near -30 (grid fixes -35). The top-ranked
candidates of the default grid were wrong places with 127 matches (too close to the chapel).
Match count alone does not rank real-photo candidates reliably against this texture. A finer or
adaptive start grid, or a telemetry-seeded one, is a change to the search and waits for the owner.

## What killed the track, and the fix

Frames 75 to 77 (about 53 s): the drone stops (telemetry horizontal speed 7 m/s to 0, 48 to 54 s) and
hovers while the gimbal pitches down about 10 degrees. Holding the f074 pose, f090 still gets 122
inliers at pitch -10 and heading -10 relative to it; with the old fixed pitch it got under 30.

- The local search centred on the last fix had radius 65 m against 70 m grid spacing, so it never left
  the last position, took the last pitch and tried headings 45 degrees apart: it could not see this.
  The constant-velocity prior also scored below the held pose on the fading matches.
- Changes (`tracker.py`, `search.py`): each photo is tried at the constant-velocity pose and at the
  last fix held; the local search is a 40 m grid, pitch offsets -20, -10, 0, +10 degrees, heading
  offsets +-30 degrees in 15 degree steps, 540 renders (about 20 s on TensorRT); ten failed searches
  in a row abort, not three.
- Result, all 110 frames from the seeded first fix: 90 tracked, 4 relocalised, 3 kept by the search
  but dropped by the lens graph (f021, f028, f077), 13 lost (f095 to f098, f102 to f110). Lens focal
  1,000 px at 1280 wide (sigma 3.0), k1 -0.047, k2 +0.116. Searches that succeeded: f075, f077 to f080.
- Against the telemetry (`reference.csv`, GPS interpolated per frame): 97 photos compared, horizontal
  distance median 4.3 m, max 10.6 m; height after removing a constant datum offset, median spread
  1.1 m. The GPS itself is quantised to 7 to 11 m.
- Tests: 27 passed, 2 skipped; new tests for the pitch and heading offsets and the reference page.
  The first-fix start grid is unchanged and still misses this clip.

## Second round: yaw, weak fixes, wrong fixes

- From f090 the heading changes 5 to 7 degrees a photo (141 to 177 degrees by f101) and the pitch
  settles near -42; the fixes at f074 and f094 have only 59 and 49 inliers. A pose re-rendered
  from a
  weak fix gets 0 inliers on the next photo, even though f094 and f095 look the same.
- Added (`decisions.md`): staged priors with angular-velocity extrapolation and earlier fixes held,
  a 30 m gate on later-stage fixes (without it the synthetic town test accepted a wrong fix 88 m off
  with 108 inliers: repeating buildings), re-solving weak fixes at their own pose, and full-circle
  headings in the local search so a 90 degree turn in a gap still recovers.
- Result (`run6`): 101 of 110 frames located (94 tracked, 6 relocalised, 1 dropped by the lens
  graph), 9 lost: f095, f096, f098, f102, f103, f105, f106, f108, f110. Against the telemetry:
  horizontal median 3.9 m, max 10.2 m; height spread median 0.8 m. Focal 1,002 px, k1 -0.038,
  k2 +0.094.
- The lost frames are near-nadir views (pitch about -60) of the chapel yard. The render there is a
  blob for the chapel, spikes for trees and smooth lawn for the graves (the owner's screenshots of
  the mesh in Blender), so little remains to match. Imagery-only matching with a perspective warp is
  proposed as the next trial, after MegaLoc.
- Tests: the gap test no longer expects a search (a prior alone recovers it).

## Third round: the gate on every stage

The synthetic town gap test accepted a wrong 48-inlier fix 104 m off from the last-fix-held prior
of the first stage (found by toggling the first-photo focal tries, the re-solve and the gate; only
the gate mattered). The 30 m gate now applies to every stage and a fix far from all its priors is
treated as no fix. The gap test is back to its original assertions (a search recovers photo 7 to
0.1 m). Bexhill again (`run7`): 97 tracked, 3 relocalised, 10 lost (f095, f096, f098, f102, f103,
f105 to f108, f110), 100 compared with the telemetry at 3.6 m median, 14.0 m max; focal 1,015 px,
k1 -0.064, k2 +0.147. The lens estimate moves by 1 to 2 percent between runs with different lost
frames: the lens graph's k1 and k2 are weakly constrained on this clip.

## Review page

`satmesh track --reference CSV` (columns photo, latitude_deg, longitude_deg, optional height_m)
adds the logged path and per-photo residuals to `review.html`; photos are stored at 450 px tall and
shown full width when selected (page 10 MB for 110 photos). The layout was not looked at in a
browser (none is installed here); the page script passes a syntax check and the data a test.

## Open

- Mesh and texture quality at the chapel; the imagery position left uncorrected.
- Esri imagery date and the unchanged correction leave a position error nobody has measured.
