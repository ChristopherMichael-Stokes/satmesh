---
status: current
topic: evaluation
summary: P2 of photo-only pose recovery on synthetic flights with a distorted lens: tracking by render, match and PnP plus a GTSAM graph with one shared lens (focal, k1) recovers focal to 0.1 % and k1 to 0.003 with sub-metre poses on oblique flights, to under 1 % and 0.35 m near nadir, and is sensitive to mesh error unless the points' error budget is given to the graph, which then also reports an honest uncertainty.
answers: Can focal length and radial distortion be recovered from photos against the mesh with a factor graph; how many photos does the window need; how does near-nadir flying change it; how much does mesh error bias the lens and the poses; what point and focal priors should the graph use; when can the lens estimate be trusted
---

# P2 results: tracking and calibration in a factor graph

Run 2026-10-31. Plan: `photo-only-plan.md` (P2, the owner's design: calibration inside the
graph). Earlier stages: `photo-only-p0-results.md`, `photo-only-p1-results.md`. Scripts in
`uncommitted/photo-only/p2/`; data in the session scratchpad (flights are rendered by the script).

## Setup

- Slice store, three flights of 24 photos 12 m apart, rendered from the full-surface mesh and
  then distorted by a true lens: focal 1005.4 px (1.10 times the nominal 914 px), k1 = -0.10,
  k2 = 0, principal point at the centre. Flight L: 25 to 50 m above ground, pitch -50 to -25
  degrees. Flight H: 60 to 100 m, same pitch. Flight N: 40 to 100 m, pitch -90 to -80 degrees.
- Tracker: first fix emulated as the true pose plus the default prior offset (P1 supplies it);
  focal from a scan on the first photo (as P0b, k1 ignored); then each photo is rendered at the pose
  predicted by constant velocity, matched (XFeat plus LighterGlue, ONNX), lifted through the render's
  depth and solved with PnP at the scanned focal. Whole flights tracked: 24 of 24, 10 s each.
- Graph (GTSAM 4.3, installed per run with `uv run --with gtsam`): `Cal3Bundler` (focal, k1, k2;
  principal point fixed), a `Pose3` per photo, a point per correspondence (up to 100 per photo)
  with a prior at the lifted position, `GeneralSFMFactor2Cal3Bundler` per match with a Huber loss
  (k 1.345, pixel sigma 2.0 from the 2.4 px render-to-render residual), priors on calibration
  (focal sigma 30 % of the scan value, k1 sigma 0.3, k2 sigma 0.001). Levenberg-Marquardt:
  0.1 s for 24 photos. GTSAM's `Cal3Bundler` projection equals OpenCV's radial model to 0.0 px.
- Photos share the mesh's texture and geometry exactly; the mesh error tests below add error to the
  points the graph sees.

## Results

| Flight | Focal error | k1 | Position error median (max) | Tracker alone | PnP with the true lens |
| --- | --- | --- | --- | --- | --- |
| L, 24 photos | -0.07 % (1 sigma 0.18 %) | -0.0987 | 0.06 m (0.13) | 1.50 m (2.12) | 0.02 m |
| H, 24 photos | -0.07 % (0.15 %) | -0.0995 | 0.18 m (0.29) | 1.38 m (2.06) | 0.07 m |
| N (near nadir) | -0.79 % (1.4 %) | -0.0979 | 0.35 m (0.44) | 4.12 m (4.73) | 0.04 m |
| L, re-lit and blurred | +0.05 % (0.18 %) | -0.0988 | 0.06 m (0.15) | 0.96 m (1.60) | 0.03 m |

- Rotation error after the graph is 0.05 to 0.15 degrees (tracker 0.4 to 1.3).
- The scan focal at the first photo was 5.5 % low (L), 3.6 % low (H) and 10.9 % low (N). The
  graph removes that error and the pose error it causes (7 to 13 m per 9 % in P0b; here 1.4 to 4 m).
- Window length on flight L: 2 photos give focal -0.17 % (1 sigma 0.6 %), 3 give 0.00 % (0.5 %),
  5 give -0.03 % (0.4 %), 10 give -0.03 % (0.3 %); poses 0.04 to 0.11 m. The correlation of focal
  and k1 is -0.65 to -0.72 in every case.
- Near nadir the graph still determines the lens from relief and height variation, with an
  uncertainty 8 times that of the oblique flights (focal 1 sigma 14 px against 1.8 px).

## Mesh error

The points the graph sees get noise (every point) and a vertical offset (all points) that the
photos' pixels do not share. First rows keep the graph's default point sigma
(0.05 m + 0.5 % of range), the others match the point sigma to the noise.

| Flight | Noise, vertical offset | Point sigma | Focal error (1 sigma) | Position error median | True-lens PnP |
| --- | --- | ---: | --- | ---: | ---: |
| L | 1 m, 0 | default | +0.26 % (0.18 %) | 0.62 m | 0.72 m |
| L | 0, 1.5 m | default | -0.10 % (0.18 %) | 1.49 m | 1.50 m |
| L | 2 m, 1.5 m | default | +2.0 % (0.2 %) | 2.69 m | 2.87 m |
| L | 2 m, 1.5 m | 2 m | +0.7 % (0.9 %) | 1.70 m | 2.87 m |
| N | 1 m, 0 | default | +13.7 % (1.4 %) | 6.26 m | 1.97 m |
| N | 2 m, 1.5 m | default | +95 % (3 %) | 43.5 m | 4.89 m |
| N | 1 m, 0 | 1 m | +1.1 % (4.9 %) | 1.67 m | 1.97 m |
| N | 2 m, 1.5 m | 2 m | +3.2 % (6.1 %) | 4.52 m | 4.89 m |

- A vertical offset moves the poses by the offset and leaves the lens alone; no graph can see it.
- With default point sigmas the near-nadir graph is wrong and confident (focal +13.7 % and +95 %
  at 1 sigma 1.4 % and 3 %). With the point sigma set to the mesh error it is as good as PnP with
  the true lens, and its uncertainty covers the error.
- A 5 % focal prior centred on the scanned focal pulled the near-nadir estimate to -6 % and -8.5 %
  (the scan was 11 % off). A prior is useful only when centred on a known focal (sensor database,
  EXIF), not on the scan.

## k2 (added after the owner asked why it was held at zero)

k2 free (prior sigma 0.3) against held at zero (sigma 0.001), flights of 24 photos, oblique unless
noted:

| Lens (true) | k2 | Focal error | k1 | k2 estimate | Median position error |
| --- | --- | ---: | ---: | ---: | ---: |
| 70 degrees, k1 -0.20, k2 +0.06 | held | -0.63 % | -0.159 | 0.0005 | 0.10 m |
| same | free | +0.05 % | -0.204 | 0.069 (1 sigma 0.013) | 0.08 m |
| 100 degrees (focal 539 px), k1 -0.25, k2 +0.08 | held | -2.10 % | -0.168 | 0.024 | 0.33 m |
| same | free | +0.10 % | -0.248 | 0.0797 (1 sigma 0.002) | 0.15 m |
| 70 degrees near nadir, k2 = 0 | held | -0.36 % | -0.0985 | 0 | 0.19 m |
| same | free | -0.30 % | -0.104 | 0.011 (1 sigma 0.022) | 0.18 m |

Holding k2 at zero biases focal and k1 when the lens has k2; freeing it costs nothing when it does
not, and its covariance says when it is undetermined. The tracker's focal scan range was widened
to 0.4 times nominal for the 100 degree lens. A true fisheye is not covered: beyond about 110 to
120 degrees the radial polynomial and a pinhole render fail.

## What follows for the design

- The graph's point sigma is the mesh error budget, not the renderer's depth precision. The real
  budget is unmeasured (DSM against lidar and Esri against EA were 0.5 to 2 m in earlier work); H3
  on real photos is where to measure it.
- Calibrate on oblique photos when there are any; the covariance tells when the lens is
  determined: 1 sigma of focal under about 1 % held on every oblique flight and, with matching
  point sigmas, near nadir it grows to 5 to 6 %, which is the signal to keep the lens variable
  and not freeze it.
- Keep the focal prior loose unless it is centred on a known value.

## Not established

- Real photos: texture and geometry differ from the mesh, so the 2.4 px residual and the mesh error
  budget are guesses. Tracking used lost-photo handling only as a stop.
- A different lens (k2, principal point, tangential terms), other fields of view, rolling shutter.
- Missing photos, wrong fixes, gaps, motion-prior and between-pose factors, sliding window (P3).
- GTSAM is not yet a dependency of the repo; `satmesh-eval` has no tracker or graph code.
