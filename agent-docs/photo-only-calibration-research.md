---
status: current
topic: evaluation
summary: Survey of recovering camera poses and calibration from ordered photos alone against the mesh: a render, match and PnP tracker with a sliding-window factor graph (GTSAM) and a shared calibration variable; the combination is not a published system; initialisation, near-planar focal ambiguity and ground-level facades are the risks; six cheap experiments decide between approaches.
answers: How could poses and camera calibration be recovered from ordered photos of a roughly known area; are factor graphs a fit; which published systems do parts of it; how is the first photo localised without a prior; when is focal length unobservable; which tools have Python 3.13 wheels on aarch64; which experiments should run first
---

# Photo-only poses and calibration: research

Requested by the owner 2026-10-31: take only the photos (ordered, from a roughly known area) and
produce the pose file and the camera calibration by visual matching and perspective-n-point; factor
graphs suggested. Survey by a research subagent, sources opened unless marked search-only. Nothing
is built. The harness it extends: `harness-plan.md`.

## Recommendation

A render, match and PnP tracker followed by a sliding-window factor graph with a shared calibration
variable, using the existing harness for every absolute fix and GTSAM for the graph:

1. **First fix.** Render candidate views on a grid over the known area (heights such as 2, 10, 30,
   60, 100 m above ground, headings every 30 degrees, a few pitches), rank them against the first
   5 to 10 photos with a global descriptor (MegaLoc or AnyLoc), then XFeat with LighterGlue, depth
   lift and PnP with unknown focal length on the top candidates. Accept a candidate only when it is
   confirmed across consecutive photos (Viterbi or HMM over per-photo top-k lists, the SeqSLAM
   idea).
2. **Calibration.** Estimate focal length with `pycolmap.estimate_and_refine_absolute_pose`
   (`estimate_focal_length`, then `refine_focal_length` and `refine_extra_params`), starting from
   max(width, height) as OrthoLoC does. Pool focal and k1 over well-conditioned photos, then fix
   them or keep them as one shared variable.
3. **Tracking.** Predict the next pose with a constant-velocity model, render there, match, PnP with
   fixed intrinsics. Widen the search on a low inlier count; fall back to the first-fix search
   limited to a radius around the last fix.
4. **Refinement.** GTSAM: a `Pose3` per photo, one shared `Cal3DS2`, `GeneralSFMFactor2` on the
   mesh-lifted 2D-3D inliers (tight prior on each point or constants), optional `BetweenFactor`
   relative poses from photo-to-photo matching, smoothness priors, Huber or Cauchy kernels;
   Levenberg-Marquardt per window or iSAM2.
5. **Output.** Pose file, calibration, per-photo inliers, residual and the 6 x 6 marginal
   covariance. The EKF should take the covariance of the single-photo PnP, not the smoothed one, so
   the motion prior is not counted twice.

Each part is established; OrthoLoC, PiLoT and MeshLoc each do part of it. The joint pipeline (photos
only, unknown intrinsics, no prior, a sequence against a DSM or ortho mesh) is unproven and no paper
doing exactly this was found.

## Candidate approaches

| Approach | Status | Effort |
| --- | --- | --- |
| Per-photo render, match, PnP with unknown focal (MeshLoc, OrthoLoC) | Established for localisation; intrinsics only by OrthoLoC (focal) | Low, the harness exists |
| Grid render plus global retrieval for the first fix | Established in UAVD4L (offline synthetic data); unproven at our scale | Medium |
| Sequence voting (SeqSLAM, HMM) over candidates | Established for place recognition, not 6-DoF on meshes | Low |
| Particle filter over pose (Kinnari et al. 2021, Jurevicius 2019) | Established for downward UAV over an ortho, needs odometry | Medium to high |
| Sliding-window factor graph with shared calibration | Factor types established; this use unproven | Medium |
| COLMAP SfM on the sequence, then Sim3 alignment to the mesh from the fixes | Established; strong for calibration | Medium |
| Learned alignment to renders (PiLoT) | Recent (arXiv 2026); initialisation unclear | High |
| DEM skyline matching (Baatz, ECCV 2012) | Established in the Alps; weak on flat terrain | High, poor fit |

## Verified findings

- MeshLoc (arXiv 2207.10762, BSD-3 code): localisation against a mesh with render features; the
  abstract does not cover intrinsics.
- OrthoLoC (arXiv 2509.18350, NeurIPS 2025): UAV image matched to an ortho, lifted through the DSM,
  PnP. Estimates focal length only (EPnP-RANSAC from f0 = max(W, H), then Levenberg-Marquardt over
  K and pose, Huber loss), ignores distortion. 0.32 m and 0.12 degrees with known K; with K
  estimated, focal error 1.6 % and translation error 2.09 m, recall at 1 m and 1 degree falling from
  75 % to 22 %. It assumes a reference crop around the true pose (10 to 20 m offsets), no retrieval.
  Estimating focal length cost roughly 4 to 6 times the single-photo translation accuracy.
- PiLoT (arXiv 2603.20778): live UAV video against a georeferenced 3D map at over 25 FPS; how it
  initialises and whether intrinsics are known is unverified; the repository link returned 404.
- UAVD4L (arXiv 2401.05971): textured-mesh reference, offline synthetic data, online localisation.
- LandscapeAR (ECCV 2020): photos to textured DEMs with learned cross-domain descriptors.
- Radial-distortion absolute pose: Kukelova et al., ICCV 2013 (P5Pfr); Larsson et al., ICCV 2019.
  Planar scenes are degenerate for P4Pfr (Larsson et al., ICCV 2017, search snippet only).
- Planar ambiguity: a nadir camera over flat ground cannot separate focal length from height; tilt,
  relief or buildings break it. Standard geometry, not taken from one source.
- pycolmap 4.2.1: `AbsolutePoseEstimationOptions.estimate_focal_length` (discrete sampling around
  the given focal), `AbsolutePoseRefinementOptions.refine_focal_length`, `refine_extra_params`,
  `return_covariance`, and a pose-prior bundle adjuster.
- PoseLib: released minimal solvers include `p4pf`, none for focal plus radial distortion;
  `estimate_absolute_pose` takes a fixed camera. Focal and extra-parameter estimation are on master;
  whether the 2.0.5 wheel has them is unverified.
- GTSAM has `GeneralSFMFactor2` (pose, point, shared calibration) and `Cal3DS2`, `Cal3Fisheye`,
  `Cal3f`, `Cal3Bundler`.

## Tools (PyPI, checked 2026-10-31)

| Package | Version, licence | cp313 Linux x86 | cp313 Linux aarch64 | cp313 macOS arm64 |
| --- | --- | --- | --- | --- |
| gtsam | 4.3.0, BSD | yes | yes | yes |
| pycolmap | 4.2.1, BSD-3 | yes | no | yes |
| poselib | 2.0.5, BSD-3 | yes | no | yes |
| pyceres | 2.6, Apache-2.0 | yes | no | yes |
| symforce | 0.12.0, Apache-2.0 | yes | yes | yes |
| kornia | 0.9.0, Apache-2.0 | pure Python | pure Python | pure Python |

hloc and OpenSfM are not on PyPI (git or source build). MegaLoc is MIT, via torch hub; AnyLoc is
stale since 2024-03; glomap is archived.

## Failure modes

- **Kidnapped start.** Over repetitive fields or housing the top-1 retrieved render is often wrong;
  require agreement across the sequence and keep top-k candidates alive for several photos.
- **Featureless spans** (water, crops, tarmac, blur). The motion prior carries the track and its
  covariance must grow; photo-to-photo relative-pose factors bridge the gap; re-localisation radius
  scales with elapsed time.
- **Near-planar calibration.** Nadir photos over flat ground couple focal length and height.
  Estimate intrinsics on oblique or high-relief photos, then fix them; watch the focal-height
  correlation in the marginals; fall back to a sensor-database focal.
- **Photo era against imagery era.** Changed buildings, trees, season, shadows, and ortho or DSM
  misregistration of 0.5 to 2 m show up as pose bias that inlier counts do not reveal.
- **Ground-level photos.** The draped ortho has no facades, so matches fall to ground texture near
  the camera (poor for height and pitch) and the skyline against the DSM. For handheld street
  sequences, COLMAP SfM on the photos plus a Sim3 alignment to the mesh is likely more robust, and
  gives self-calibration.

## Cheap experiments (synthetic photos at known poses)

1. Focal observability: nadir, 30 and 60 degree pitch over flat and hilly tiles; free against fixed
   focal; record the focal-height correlation.
2. First-fix search: grid spacing 20, 50, 100 m with 30 degree headings; MegaLoc top-k recall
   against raw XFeat inlier counts.
3. Basin of convergence: perturb the render pose 5 to 200 m and 5 to 45 degrees; PnP success rate.
   Sets the re-render threshold and the re-localisation radius.
4. Sequence voting: a 20-photo flight over repetitive terrain; top-1 per photo against Viterbi over
   top-5.
5. Graph benefit: per-photo PnP against a GTSAM window with shared `Cal3DS2` and a motion prior;
   10 % wrong fixes and 30 % photos without a fix.
6. Ground-level stress: 2 m poses with a facade-less reference and a different-era ortho texture;
   measure the inlier collapse.

## Open

- Whether the PoseLib 2.0.5 wheel exposes focal and distortion estimation for absolute pose.
- How PiLoT initialises, and whether it needs known intrinsics.
- Real-photo accuracy on draped-ortho meshes, as opposed to OrthoLoC's ortho plus DSM references.
