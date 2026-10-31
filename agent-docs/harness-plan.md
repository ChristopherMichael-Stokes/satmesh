---
status: current
topic: evaluation
summary: Plan for the acceptance harness: render the mesh at a photo's known pose (GPU rasterisation), match photo against render, lift matches to 3D through the render's depth, solve the pose with perspective-n-point and RANSAC, and report pose error, inliers and coverage; MeshLoc is the established basis; stages H0 to H3 and forks for the owner.
answers: How will real photos be tested against the mesh; which reference variants, renderer, matcher and solver does the harness use; what does the flat, DTM and DSM comparison show about height; what metrics does it report; what is established and what is our own; which stages come first and what each delivers; what will the harness not tell us
---

# Acceptance harness plan

Drafted 2026-10-31 after the owner fixed v1 (England, US, Middle East) and the order: harness, then
Gazebo tooling, then height lifting (`decisions.md`). Replaces the out-of-scope row for the
real-photo localisation test in `f6-plan.md`.

## Method

Basis: MeshLoc (Panek, Kukelova, Sattler, ECCV 2022, arXiv 2207.10762; code BSD-3,
github.com/tsattler/meshloc_release): render the mesh, match query against render, lift render
keypoints to 3D through the rendered depth, perspective-n-point with RANSAC. MeshLoc retrieves
database poses; the harness renders at the photo's known pose instead. MeshLoc reports recall
within 0.25 m / 2 degrees, 0.5 m / 5 and 5 m / 10 on Aachen. Its textured renders matched real
images within a few points (SuperGlue 72.3 / 91.1 / 99.0 against 74.3 / 92.7 / 99.5); misalignment
of texture and geometry cost far more than missing realism.

### Reference variants (the comparison the owner asked for)

| Variant | Reference | Matching view | Geometry assumed |
| --- | --- | --- | --- |
| A1 | ortho draped on a flat plane at the camera's ground height, rendered to the photo's view (equals a ground-plane homography warp) | photo view | flat |
| A2 | photo warped by the same homography to a nadir view, matched against the ortho | nadir view | flat |
| B | perspective render of the DTM draped with the ortho | photo view | bare earth |
| C | perspective render of the full mesh (DSM), RGB and depth | photo view | terrain, buildings, trees |

- A1, B and C are the same ray caster fed a flat plane, the DTM and the DSM. A2 needs only a
  homography warp of the photo.
- A against B against C isolates what each geometry layer buys; B against C is the value of height
  lifting for localisation. Anything above the ground plane is displaced by parallax in A, so A
  matches only roads, paint and field edges. A1 and A2 differ in where resolution is lost: A2
  upsamples the far field of the photo and loses its near-field detail, A1 upsamples the ortho in
  the near field.
- No-transform matching of photo against ortho is the floor and is expected to fail.

### Pipeline

1. **Render.** Perspective RGB and range from the store's leaves in the area ENU frame
   (`export_area_glb` frame), so one code path serves England, the US and the Middle East (the
   existing top-down render is BNG only). Target: milliseconds per frame, vendor-neutral (the owner
   may run on NVIDIA, Apple Silicon or ARM and Raspberry Pi GPUs). Measured on the RTX 4070 Ti
   (WSL2, 1280 x 960, 49-leaf 2.0 M triangle slice, data resident, readback included, output
   against the Embree reference: hit masks 99.9999 %, range within 0.05 m + 0.005 per metre on
   99.999 %, colour 0.06 and 0.19 of 255 with mipmaps):
   - Embree CPU, structures reused: 4.4 s per frame.
   - `moderngl` 5.13 on headless EGL (MIT): 4.9 to 5.4 ms, 6.5 to 7.0 ms for 49 leaves of the 43 M
     triangle full store. Needs OpenGL 3.3 core, so it does not run on a Raspberry Pi 4 or 5 (GL
     3.1, ES 3.1) and is deprecated on macOS: not adopted.
   - `wgpu-py` 0.32.0 (BSD-2, wheels for Linux x86 and aarch64, macOS, Windows, Python 3.13, no
     PyTorch), built as `satmesh_eval.gpu.GpuRenderer`: 8 to 12 ms p50 at 1280 x 960 through its
     OpenGL backend on this machine, on the 49-leaf slice and on the full 961-leaf store alike
     (12 to 14 leaves in the frustum at 500 m range), output matching Embree as above. WSL2 has no
     Vulkan hardware driver (the Vulkan adapter is lavapipe on the CPU, 83 to 117 ms), so native
     Vulkan and Metal speed is unmeasured.
   - Per-frame cost on the GL path, ground-level pose: draw 5.7 ms, readback 2.2 ms, decode
     2.4 ms. Two persistent staging buffers or one combined buffer made no difference to
     readback. The first version spent 13 ms in decode because `np.ascontiguousarray` of an RGBA
     slice to RGB took 6.6 ms; `cv2.cvtColor(RGBA2RGB)` takes under 1 ms. The GL backend
     refuses float colour targets and depth readback, so range goes through a 24-bit fixed-point
     RGBA8 target on every backend (0.03 mm step at 500 m).
   Chosen: `wgpu-py` as the renderer, Embree as the CPU fallback and correctness reference in
   tests. Design: one texture per leaf (no texture arrays, so no layer limit and no uniform
   texture size), geometry and texture resident per leaf on first use and evicted least recently
   used past a 2 GiB budget; frustum and range culling of leaf bounds, drawn nearest first.
   Cold cost: about 50 ms per leaf for mip generation and upload (600 ms for the first frame of
   12 leaves). Not built: coarser parents for the far field (screen-space error selection), so a
   long-range render draws every leaf in the frustum at full detail; add when a pose needs more
   than a few hundred leaves. Pinhole only: a GPU render takes undistorted intrinsics and
   raises on distortion; undistort the photo to compare. `RenderResult` no longer carries
   per-pixel triangle and leaf indices (nothing used them). Loading all 961 leaves into an
   `AreaScene` takes 8 s and 5.3 GB of host RAM. Spike scripts: scratchpad `speed/`, `speed2/`
   and `h0b/` (session scratch, will go).
2. **Match.** Photo against reference. SIFT (OpenCV, ratio test, mutual check) is the floor.
   XFeat with LighterGlue is the learned basis, from the owner's `xfeat-rt`
   (github.com/ChristopherMichael-Stokes/xfeat-rt, MIT): `xfeat-core` features, the ONNX Runtime
   or TensorRT backend, no PyTorch, about 10 ms per pair on TensorRT FP16; MegaDepth-1500 AUC@5
   0.56 on ordinary photo pairs. Added as the git submodule `third-party/xfeat-rt` (H1); the
   exported ONNX graphs are build outputs, read from `XFEAT_MODEL_DIR` in tests. On the slice the
   learned pair recovers poses within 0.25 m where SIFT loses most matches once the photo is
   re-lit and blurred (`harness-results.md`). A stronger matcher (DISK plus LightGlue, or RoMa) is a
   ceiling check on the same pairs, to tell whether the matcher or the data is the limit.
3. **Solve.** `cv2.solvePnPRansac` with SQPnP on render keypoints lifted by depth (reprojection
   threshold 20 px as MeshLoc, then Levenberg-Marquardt on the inliers); compare with the known
   pose. P3P-family solvers flip to the wrong side of a plane when all points are coplanar, as
   with the flat references. A2 uses the same solver on points of the ground plane, with photo
   pixels mapped back through the inverse homography.
4. **Report** per photo, per variant and over the set:
   - pose recall at 0.25 m / 2 degrees, 0.5 m / 5 and 5 m / 10; translation (camera-centre
     distance) and rotation (angle of R_est^T R_gt) errors;
   - at the known pose: inliers, median 2D displacement of inliers (pixels), fraction of 8 x 8
     image cells holding an inlier, split by render depth band. A large consistent displacement
     means georegistration error; empty cells mean content missing from the render;
   - fraction of the frame with hits (not sky).

## Established and own

Verified by a prior-art survey (2026-10-31):

- Published, so not ours:
  - Photo warped to a bird's-eye view by a ground-plane homography and matched to an ortho (A2):
    Noda et al., ACCV workshops 2010 (SURF, mean error 0.6 to 1.0 m on road markings), HC-Net,
    NeurIPS 2023 (learned).
  - Ortho or satellite content projected into the ground view (A1): Shi and Li, CVPR 2022
    (learned features, KITTI lateral error within 5 m for 80 %).
  - Warp the ortho toward an oblique query, rematch, lift to 3D with a DSM: OrthoLoC, NeurIPS 2025,
    UAV images; it benchmarks XFeat and XFeat plus LightGlue (XFeat 92.8 % within 1 m and 1 degree
    in-domain, 28.8 % under ortho domain shift). CC BY-NC-SA 4.0 data and code.
  - Matching photos against mesh renders (C): MeshLoc, ECCV 2022; imperfect models: Panek et al.,
    CVPR 2023. Photos against a render of an ortho-textured DEM (B): LandscapeAR, ECCV 2020, which
    needed a trained descriptor.
  - Off-the-shelf matchers fail on unwarped ground-to-satellite pairs (ViewBridge, arXiv 2508.10716:
    LoFTR, SuperGlue and RoMa 0.3 to 0.8 % of matches within 15 px), so the unwarped floor is
    expected to fail.
- Not found, so possibly ours: a controlled comparison of A1, A2, B and C on the same known-pose
  photos (flat against bare earth against DSM as the only variable); a comparison of the two warp
  directions; XFeat plus LighterGlue on ground photos against an ortho or a render. It is an
  evaluation study, not a new method.
- Own and unproven: the label-free "visible thing is visible" score (coverage by depth band plus
  displacement); a nadir-orthophoto-draped DSM as the reference mesh.
- Expected limit: draping smears or omits facade texture, ground photos mostly see facades, so
  matches will concentrate on the ground plane, roof edges and skyline, and recall at fine
  thresholds will be low. That is a data limit, not a harness fault.
- Scale guidance: OrthoLoC finds matching robust down to 512 px for both raster and query; at 256 px
  translation error rises 44 %.

## Stages

| Stage | Delivers | Check |
| --- | --- | --- |
| H0 (built 2026-10-31, `camera.py`, `perspective.py`, Embree backend, 94 package tests pass) | Perspective textured RGB and depth render at a pose in the area ENU frame (`satmesh-eval`, camera model with intrinsics and radial distortion, pose as WGS 84 position plus heading, pitch and roll in the local ENU), for any mesh including a flat plane | Flat synthetic mesh: depth equals the analytic ray-plane distance and texture colours equal the source texels, worked out in the test; a store render at a ground-level pose opens as an image |
| H0b (built 2026-10-31, `gpu.py`, `projection.py`, 111 package tests pass) | `GpuRenderer`: wgpu rasterisation returning the H0 result type, frustum and range culling, leaves resident on the device | 8 to 12 ms p50 at 1280 x 960 on the slice and the 961-leaf store; against Embree hit masks 99.9999 %, range within 0.05 m + 0.005 per metre on 99.999 % |
| H1 (built 2026-10-31, `matching.py`, `localise.py`, `references.py`, `ground.py`, 117 package tests pass, results in `harness-results.md`) | A1, A2, B and C references, SIFT and XFeat plus LighterGlue, perspective-n-point solve, recovery of a known perturbation | Render at pose A as the "photo", localise from a pose perturbed by a known offset: pose recovered within tolerance; repeat with the photo re-lit (gain, gamma) and blurred as a stand-in for the domain gap |
| H2 (next; owner approved the harness work and said to complete it, pose-file format still his call, default below) | Metrics, JSON report and a review page (photo, render, matches, depth bands); reject solutions with too few inliers; emit inlier count and reprojection residual per fix so a later EKF can gate measurements | `satmesh eval localise PHOTOS --poses FILE --store DIR` runs end to end on synthetic photos; report fields match this plan |
| H3 | Run on the owner's real photos | Run when the owner supplies photos and poses; results into a results doc |

## Forks for the owner

1. Ceiling-check matcher (new dependency, in `ml/`): DISK plus LightGlue (Apache-2.0) or RoMa
   (MIT). SuperPoint weights are non-commercial. Decided after H1 results.
2. `pycolmap` (BSD-3, Python 3.13 wheels) in place of `cv2.solvePnPRansac`: only if the OpenCV
   solver proves too weak.
3. Pose-file format (default: one JSON line per photo, `lat`, `lon`, ellipsoidal height, heading,
   pitch, roll, intrinsics; owner to confirm) is defined by the harness (WGS 84 latitude,
   longitude, ellipsoidal height,
   heading, pitch, roll, intrinsics, distortion); the photos' own format is converted to it.
