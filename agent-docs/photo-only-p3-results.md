---
status: current
topic: evaluation
summary: P3 of photo-only pose recovery: the tracker survives missing photos, a 168 m gap on a gently turning flight and a harsh photo domain gap, loses the track after a 9-photo gap on a sharply turning one, and a local re-localisation search around the last fix recovers it; frame rejection by reprojection RMS and position-jump peaks removes bad matches and wrong places before the lens estimate is spoiled; a constant-velocity motion prior and carrying the lens between sliding windows did not help and are not adopted.
answers: How robust is the photo-only tracker to missing photos, gaps and a domain gap; what do wrong fixes do to the lens estimate; how are bad frames detected; does a motion prior help the graph; does a sliding window match the batch graph; when must the first-fix search be re-run
---

# P3 results: robustness of the tracker and the lens graph

Run 2026-10-31. Plan: `photo-only-plan.md` (P3). Baseline: P2 on flight L (25 to 50 m, 24 photos,
oblique): focal -0.07 %, median position error 0.06 m (`photo-only-p2-results.md`). Scripts in
`uncommitted/photo-only/p3/`. Same synthetic setup as P2: photos share the mesh's texture and
geometry.

## Tracker: missing photos, gaps, domain gap (flight L)

| Case | Focal error | Median position error after the graph |
| --- | ---: | ---: |
| 8 of 24 photos missing (33 %) | -0.05 % | 0.06 m |
| 4-photo gap (48 m) | -0.05 % | 0.05 m |
| Harsh photo: channel gains 0.6 / 0.9 / 1.2, gamma 1.5, blur 2 px, noise 8 grey levels, 8 patches replaced | +0.09 % | 0.10 m |

Prediction across a gap is constant velocity scaled by the number of missing steps.

- Gap length, smooth flight (3 degrees heading change per photo, 12 m steps): gaps of 6, 10 and 14
  photos (72, 120, 168 m) were all recovered, 1,000 or more inliers on the first photo after.
- Sharply turning flight (14 degrees per photo, same height range 30 to 70 m): a 3-photo gap
  recovered (456 to 870 inliers), a 6-photo gap recovered marginally (191 inliers on the first
  photo after), a 9-photo gap lost the track for good: every later photo failed.
- So constant-velocity prediction bridges a gap while the path stays near straight. When a photo
  is lost the tracker needs the first-fix search of P1, limited to a radius that grows with the
  time since the last fix, to re-localise; the P0 basin (50 m offsets at 25 m and above) sets the
  radius that one prediction can cover.

## Re-localisation after a lost track (sharply turning flight)

When a photo gets fewer than 30 inliers, the tracker searches a local grid around the last fix:
radius 60 m + 1.2 x the typical step x the missed steps, positions every 70 m, heights 0.7, 1.0 and
1.4 times the last height above ground (at least 25 m), 8 headings, the last pitch. Each render is
ranked by XFeat plus LighterGlue match count (1,024 keypoints), the top 5 are solved with the
normal solve and the one with most inliers (30 or more) is the new fix.

| Gap | Renders searched | Radius | First fix after | Time (ONNX CPU) |
| --- | ---: | ---: | --- | ---: |
| 9 photos (108 m) | 600 | 207 m | 605 inliers, 1.46 m, tracking resumed to the end | 120 s |
| 14 photos (168 m) | 1,080 | 280 m | 536 inliers, 0.83 m | 215 s |

Without it the 9-photo gap lost the rest of the flight. The renders grow with the square of the
missed steps, so a long gap on a large area wants the P1 retrieval to cut the candidates; at 10 to
15 ms a pair on TensorRT the same searches take about 15 to 25 s. Tested on the one flight.

## Graph: wrong fixes (flight L, 3 of 24 frames corrupted)

| Corruption | Handling | Focal error | k1 (true -0.100) | Clean-frame position error median | Corrupted frames |
| --- | --- | ---: | ---: | ---: | --- |
| None | none | -0.07 % | -0.0987 | 0.06 m | |
| 70 % of pixels replaced by random pixels | none | -0.90 % | -0.0871 | 0.30 m | 5 to 17 m wrong |
| same | rejection | -0.12 % | -0.0977 | 0.06 m | removed (3 flagged, no false positive) |
| Points and start pose moved 15 m (consistent wrong place) | none | -0.04 % | -0.0992 | 0.05 m | 15 m wrong |
| same | rejection | -0.08 % | -0.0986 | 0.05 m | removed (3 flagged, 1 false positive) |

- Rejection: after a first solve, a frame is dropped if the robust z-score (median and MAD) of its
  reprojection RMS exceeds 4, or if the z-score of the second difference of positions exceeds 4 at
  a local peak (a bad pose raises three neighbouring second differences; flagging the peak avoids
  dropping its neighbours; flagging all three dropped 10 of 24 frames), then the graph is solved
  again.
- A consistent wrong place leaves the lens estimate untouched and is invisible to the residual: the
  pose is wrong by the shift. Only the position jump finds it. The thresholds are not tuned beyond
  these three corrupted frames.

## Motion prior (second difference of positions, sigma 1.0 m)

| Case | Without | With |
| --- | --- | --- |
| Clean, oblique | 0.06 m | 0.09 m |
| Mesh noise 1 m, point sigma 1 m, oblique | focal +0.28 %, 0.51 m | focal +0.23 %, 0.57 m |
| Same, near nadir | focal +1.10 %, 1.67 m | focal -12.9 %, 5.53 m |
| 3 wrong-place frames, no rejection, oblique | 0.05 m clean frames | 0.27 m (max 0.89), wrong frames still 13 to 14 m |

The prior pulled neighbours toward the wrong frames, and near nadir it traded height against focal
because the test flights' height wanders 2 m per photo, more than the 1 m sigma allows. It gave no
benefit anywhere measured, so it is not adopted; a prior would need a realistic or horizontal-only
sigma and its own test.

## Sliding window (8 photos, step 4, lens carried as a prior)

| Case | Batch of 24 | Windows of 8 |
| --- | --- | --- |
| Clean | focal -0.07 %, 0.06 m | focal -0.05 %, 0.06 m |
| 3 random-pixel frames, no rejection | focal -0.90 %, 0.30 m | focal -1.18 %, 0.45 m |

Windows match the batch when the data is clean. The carried prior counts the overlapping photos
twice (1 sigma 0.12 % against 0.17 %), so its uncertainty is too small. Bad frames reach two
windows; rejection has to come first.

## Design consequences

- Reject frames (residual and jump) before the lens or any prior sees them.
- Keep the point sigma at the mesh error budget (P2), no motion prior for now.
- A lost track runs the local search above around the last fix, radius growing with elapsed time;
  it recovered both lost cases.
- Windows may stand in for the batch once rejection is in; the carried lens prior needs its
  covariance inflated or the overlap removed.

## Not established

- Real photos, real mesh error, and thresholds on real residual distributions.
- A different-era texture with changed geometry (the harsh photo changes colour, blur and patches
  but not geometry).
- Wrong fixes that look correct (right residual, wrong place) with no jump, such as the first photo.
- Re-localisation on more than one flight, on a store with repetitive terrain, and with the radius
  larger than the area around the last fix.
