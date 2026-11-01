---
status: current
topic: evaluation
summary: Evidence for a first fix that uses priors on a video-only feed: level 1 recall of 97 Bexhill clip frames on the 1.5 km and the 2.5 km stores under heading, pitch and height windows (right and wrong), multi-frame fusion with the tracker's heading offsets (K=1 recall 0.75 to 0.94 single frame, 1.00 fused on the 2.5 km store), and the prior art on horizon attitude, altitude from one image, sequence place recognition, relative rotation and skylines.
answers: How much do heading, pitch and height priors shrink level 1 and what do wrong priors cost; does summing several frames fix confusers; which methods estimate pitch, roll and altitude from video frames; which sequence and relative-rotation methods are established; does skyline matching fit; what is not tested
---

# First fix with priors: measurements and prior art

Run 2026-11-01. Scripts: `uncommitted/photo-only/bexhill/scripts/prior_queries.py`,
`prior_experiments.py`, `prior_describe.py`. Queries are the 110 clip frames described by MegaLoc;
truth is the tracker's pose for the 97 frames it located (3.5 m median from the GPS). Level 1 =
280 m positions, 12 headings, 5 heights (40 to 110 m above ground), 2 pitches (-35, -50). Success:
a place among the top K (280 m apart) lies within 250 m of the truth. The clip is 51 to 74 m above
ground at pitch -25 to -43 degrees.

## Level 1 recall, single frame, 97 frames (K=1 / K=3 / K=5)

| Search | 1.5 km store | 2.5 km store | Views (2.5 km) |
| --- | --- | --- | ---: |
| No prior | 0.89 / 0.95 / 0.96 | 0.73 / 0.89 / 0.94 | 14,520 |
| 6 headings (60 degrees) | 0.87 / 1.00 / 1.00 | 0.70 / 0.91 / 0.94 | 7,260 |
| 4 headings (90 degrees) | 0.51 / 0.81 / 0.99 | 0.65 / 0.86 / 0.90 | 4,840 |
| Heading window +-45, hint right | 0.89 / 1.00 / 1.00 | 0.72 / 0.87 / 0.93 | 3,630 |
| Heading window +-45, hint 30 off | 0.78 / 0.96 / 0.96 | 0.37 / 0.46 / 0.64 | 3,630 |
| Heading window +-45, hint 60 off | 0.59 / 0.69 / 0.86 | 0.19 / 0.26 / 0.29 | 3,630 |
| Heading window +-45, hint 180 off | 0.36 / 0.64 / 0.70 | 0.05 / 0.16 / 0.26 | 3,630 |
| One pitch (-35) | 0.90 / 0.96 / 0.97 | 0.59 / 0.71 / 0.76 | 7,260 |
| Pitch nearest the truth | 0.88 / 0.96 / 0.97 | 0.59 / 0.72 / 0.77 | 7,260 |
| The other pitch | 0.77 / 0.97 / 1.00 | 0.49 / 0.68 / 0.75 | 7,260 |
| Heights 40 to 72 m | 0.76 / 0.97 / 1.00 | 0.11 / 0.44 / 0.67 | 8,712 |
| Heights 55 to 90 m | 0.57 / 0.97 / 0.99 | 0.21 / 0.35 / 0.44 | 8,712 |
| Heights 72 to 110 m | 0.89 / 0.95 / 0.96 | 0.73 / 0.89 / 0.94 | 8,712 |
| Heights 90 to 110 m | 0.89 / 0.95 / 0.96 | 0.73 / 0.89 / 0.94 | 5,808 |

- The 1.5 km store flatters every row: a 250 m circle covers 11 % of it (3 % of the 2.5 km store).
  Read the 2.5 km column.
- Six headings lose nothing against twelve. A right heading window of +-45 degrees loses nothing and
  costs a quarter of the views. The window is brittle: a hint 30 degrees off, with the truth at
  the window's edge, drops K=5 from 0.93 to 0.64; 60 degrees or more off leaves 0.3 or less.
- Retrieval does not want the photo's own height or pitch. Cells at 90 to 110 m recall as well as
  all heights for photos at 51 to 74 m, and windows around the true height recall far worse. One
  pitch loses 18 points at K=5, and the pitch nearest the truth is no better than the other: the
  photo-to-render match is not pitch-matched. The cause is not found (the render is 640 x 360 squashed
  to 322 x 322; the photo is squashed the same way).

## Multi-frame fusion (K=1 recall, single centre frame to fused)

A candidate (position, heading) scores the sum of the per-frame similarities, frame i taken at the
heading of frame 0 plus the tracker's heading difference, rounded to 30 degrees. Success is against
the window's centre frame.

| Window | 1.5 km store | 2.5 km store |
| --- | --- | --- |
| 3 frames, 2 s apart | 0.89 to 1.00 (n=18) | 0.89 to 0.94 (n=18) |
| 5 frames, 2 s apart | 0.94 to 1.00 (n=16) | 0.94 to 1.00 (n=16) |
| 5 frames, 5 s apart | 0.92 to 1.00 (n=12) | 0.83 to 1.00 (n=12) |
| 9 frames, 2 s apart | 0.92 to 1.00 (n=12) | 0.75 to 1.00 (n=12) |

- K=3 and K=5 are 1.00 for fused windows on both stores; single-frame K=5 on the 2.5 km store is
  0.94 over all 97 frames.
- Limits: 12 to 18 windows that overlap, so the counts are not independent; the heading offsets
  come from the tracker's own poses (a best case); one clip. The offsets must be estimated from
  the video before this counts.

## Prior art (reports of research agents; sources not re-opened by the session)

| Need | Candidate | Source, licence | Reported | Caveat |
| --- | --- | --- | --- | --- |
| Pitch and roll from one image | GeoCalib | Veicht et al., ECCV 2024, arXiv 2409.06704; code Apache-2.0, weights CC-BY-4.0 | MegaDepth median roll 0.36, pitch 1.94 degrees; about 100 ms; PyTorch | not evaluated on aerial images; focal output weakest; needs the horizon or strong lines |
| Altitude from one image | MoGe-2-Aerial | Song et al., ECCV 2026, arXiv 2606.29716; code MIT, weight licence unconfirmed | internet drone video 0 to 400 m: AbsRel 21 %, delta1 54 % | no method found better than about +-30 % at 50 to 300 m |
| Altitude (others) | UniDepth V2 | CC BY-NC 4.0 | AbsRel 17 to 31 % | non-commercial |
| Altitude (others) | Depth Anything V2 metric | outdoor model trained to 80 m | | unusable above about 80 m |
| Sequence scoring | SeqSLAM | Milford and Wyeth, ICRA 2012; OpenSeqSLAM GPL-3.0 | | same sum as the fusion above |
| Sequences help | SeqVLAD | Mereu et al., RA-L 2022, arXiv 2207.03868; MIT | MSLS R@1 78.2 (1 frame) to 95.2 (15) | street-level data |
| Aerial sequences | Wang et al., IEEE TGRS 2024 | DOI 10.1109/TGRS.2024.3359605 | abstract unverified | nadir satellite patches, not renders |
| Relative rotation | `findEssentialMat` and `recoverPose` (five-point, Nister) | OpenCV, Apache-2.0 | | degenerate at zero translation; sideways motion looks like rotation on narrow lenses |
| Rotation-only | Kneip and Lynen, ICCV 2013 | DOI 10.1109/ICCV.2013.292 | rotation below 1 degree per pair on Vicon video | OpenGV licence unclear |
| Rotation and focal | Brown, Hartley and Nister, CVPR 2007 | DOI 10.1109/CVPR.2007.383082 | | no maintained Python code found |
| Closest system | UAVD4L | Wu et al., 3DV 2024, arXiv 2401.05971 | renders at 100 and 150 m, IMU yaw prior within 30 degrees, retrieval R@3 98.8, 96 % within (3 m, 3 degrees) | repository has no licence: ideas only |
| Skyline against a DEM | Baatz et al., ECCV 2012 | DOI 10.1007/978-3-642-33709-3_37 | top-1 within 1 km: 88 % in Switzerland | needs sky and mountain relief; accuracy about 1 km; not pursued |

- Pitch and roll from a horizon line: roll = angle of the line to the image x-axis; pitch =
  atan(d / f) with d the distance of the line from the principal point and f the focal length in
  pixels (derived by the agent, not quoted). A 10 % focal error costs about 2.5 degrees of pitch at
  30 degrees down. The horizon leaves a typical wide frame once the camera is 22 to 28 degrees down
  (inferred).
- Not found: a published method that sums rotation-compensated render similarities over frames; a
  published interval formulation of heading, height and pitch priors inside retrieval.

## Not tested

- Any altitude above 74 m, any horizon in frame, any site but Bexhill.
- Estimated heading offsets from video (the fusion above used tracker poses).
- GeoCalib, the altitude models and the essential-matrix yaw on these frames.
- Why the matching pitch differs from the photo's pitch.
