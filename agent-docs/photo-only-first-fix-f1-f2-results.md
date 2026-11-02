---
status: current
topic: evaluation
summary: F1 and F2 of the first fix with priors, run on the Bexhill clip: yaw differences between frames from XFeat matches (essential matrix and rotation-only homography, nominal 80 degree lens) are within 1.3 degrees median of the tracker's at 2 s apart, and fusing five frames 2 s apart with those estimated offsets lifts K=1 level 1 recall on the 2.5 km store from 0.87 to 0.99; the clip's small yaw spread, one site and overlapping windows limit what this shows.
answers: How accurate is yaw from video against the tracker; does a wrong focal matter for the yaw estimate; do estimated offsets fuse as well as the tracker's; how many frames and how far apart; what does the fusion not prove; where are the scripts and outputs
---

# F1 and F2: yaw offsets from video and fusion

Run 2026-11-02. Plan: `photo-only-first-fix-plan.md`. Evidence before: `photo-only-first-fix-priors.md`.
Scripts (scratch, `locate/` environment): `uncommitted/photo-only/bexhill/scripts/f1_yaw.py` and
`f2_fusion.py`; outputs `uncommitted/photo-only/f1/` (`yaw_pairs.json`, `f2_*.txt`). Truth is the
tracker's heading for the 97 located frames (3.5 m median from the GPS).

## F1: yaw difference between two frames

- XFeat and LighterGlue matches (TensorRT, 4,096 keypoints, 25.6 s for 110 frames and all pairs), then
  OpenCV `findEssentialMat` (RANSAC, 1 px) with `recoverPose`, and a rotation-only homography
  (`findHomography`, K^-1 H K projected to a rotation by SVD).
- The relative rotation becomes a heading change by taking the camera rotation's component about the
  world vertical, whose direction in the camera frame comes from the pitch. Sign and the pitch
  convention were checked by the errors: a wrong sign would leave errors as large as the signal.
- K is nominal: principal point at the image centre, focal for an 80 degree horizontal field of view
  (1,144 px). The tracker's recovered lens is 64.5 degrees (1,521 px), so the nominal K is 25 % off.

Error against the tracker's heading difference, degrees (median / 90th percentile; share under 5):

| Pairs apart | Pairs | True change, median | Essential, nominal K | Homography, nominal K | Essential, recovered K |
| --- | ---: | ---: | --- | --- | --- |
| 1 s | 92 | 3.5 | 0.7 / 1.2; 1.00 | 0.2 / 0.8; 1.00 | 0.2 / 1.0; 0.97 |
| 2 s | 90 | 7.3 | 1.3 / 2.0; 1.00 | 0.3 / 0.9; 1.00 | 0.3 / 0.8; 1.00 |
| 5 s | 87 | 18.7 | 3.4 / 4.5; 0.95 | 0.6 / 1.9; 0.98 | 0.4 / 1.8; 1.00 |

(Pitch assumed -35 degrees; the tracker's pitch is -25 to -43. Using the tracker's pitch changes the
essential matrix medians by under 0.2 degrees and the homography's by up to 1.6 degrees at 5 s, in
the worse direction.)

- Pass line was a median under 5 degrees at 2 s: 1.3 degrees essential, 0.3 homography.
- A wrong focal costs the essential matrix about 1 degree at 2 s and 3 degrees at 5 s; the
  homography is nearly immune on this clip because the drone hovers and orbits, so the motion is
  close to a pure rotation. On a translating flight the homography will not hold and the essential
  matrix is the one to trust; this is untested.

## F2: fusion with estimated offsets

Same fusion as before (a candidate scores the sum of the frames' similarities, frame i at the
candidate heading plus its offset from frame 0, rounded to 30 degrees); offsets are the chained
estimates between consecutive window frames. Level 1 grid: 280 m positions, 12 headings, 5 heights,
2 pitches (14,520 views, 2.5 km store). Success: a top-K place within 250 m of the centre frame.
Windows start every frame (dense, heavily overlapping) so counts are not independent.

| Window | Windows | Single centre frame K=1 / 3 | Fused, essential offsets K=1 / 3 | Fused, homography offsets K=1 / 3 |
| --- | ---: | --- | --- | --- |
| 3 frames, 2 s apart | 85 | 0.81 / 0.94 | 0.93 / 1.00 | 0.94 / 1.00 |
| 5 frames, 2 s apart | 77 | 0.87 / 0.95 | 0.99 / 1.00 | 0.99 / 1.00 |
| 5 frames, 5 s apart | 57 | 0.89 / 0.98 | 0.96 / 1.00 | 1.00 / 1.00 |
| 9 frames, 2 s apart | 61 | 0.89 / 0.95 | 1.00 / 1.00 | 1.00 / 1.00 |

- Pass line was K=1 at least 0.95 and K=3 at least 0.98: met by five frames 2 s apart (0.99 / 1.00)
  and by nine frames; three frames fall short at K=1 (0.93). Chosen window: five frames, 2 s apart
  (8 s of video).
- On windows starting every fifth frame (n = 12 to 18, 2.5 km store) the tracker's offsets and the
  estimated ones scored alike: five frames 2 s apart 1.00 / 1.00 at K=1 for both, three frames 0.94
  (tracker) against 0.89 (essential) and 0.94 (homography).
- On the 1.5 km store every fused window reaches 1.00 (single frames 0.89 to 0.94); a 250 m circle
  covers 11 % of that store, so it flatters.

## Limits

- One clip and one site. The clip's yaw rate is slow: a 5 s pair turns 19 degrees at the median, so
  the frames of a window cover 15 to 30 degrees of heading. The plan's preference for frames with
  20 to 90 degrees of spread was not tested; a clip that pans faster is the test.
- The essential-matrix pairs assume some translation; a pure hover would be degenerate, and the
  homography covers that case here.
- Estimated offsets chain consecutive pairs, so errors accumulate along a window; at 1 degree per
  pair this is under 5 degrees over eight frames, well inside the 30 degree heading step.
- Pitch entered the yaw conversion as a fixed -35 degrees. F5 replaces it with an estimated pitch;
  a pitch 10 degrees from the assumed one showed no effect on the essential matrix here, but the clip
  never goes above -25 degrees, so a near-level camera with the horizon is untested.
