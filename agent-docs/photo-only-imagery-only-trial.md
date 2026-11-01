---
status: current
topic: evaluation
summary: Imagery-only matching on the Bexhill clip does not work with XFeat and LighterGlue: a flat plane textured with the Esri imagery, the bare-earth DTM and the photo warped onto the ground plane against the top-down imagery give a median of 0 to 1 matches at the true pose on 20 frames against 328 to 414 for the full-surface mesh; at short range even the surface fails, so the useful matches come from distant buildings.
answers: Does matching the photo against the imagery alone, flat or warped to the ground plane, work on real drone frames; how does it compare with the mesh render; what range and scale effects were checked; what did the top-down warp look like
---

# Imagery-only matching on the Bexhill clip

Run 2026-11-01 with the existing harness (`satmesh eval localise`, references `surface`, `ground`,
`flat`, `top-down`; method and prior work in `harness-plan.md` and `harness-results.md`). Poses: the
`run7` track of the clip (`photo-only-bexhill-results.md`), every fifth frame, 20 frames, plus the 10
frames the tracker lost. Scratch: `uncommitted/photo-only/bexhill/refs/` and `scripts/ref_poses.py`.
The tracked pose is the mesh's own result, so recall against it favours the surface; the counts of
matches and inliers at the true pose below do not depend on a solve.

| Reference | What the photo is matched against |
| --- | --- |
| surface | the DSM mesh draped with the imagery, rendered at the pose |
| ground | the bare-earth DTM draped with the imagery, rendered at the pose |
| flat | the imagery on a plane at the local ground height, rendered at the pose |
| top-down | the photo warped onto the ground plane (plane-induced homography), against the imagery from above |

## Results (20 tracked frames, range 500 m)

| Prior offset | Solved: surface | ground | flat | top-down |
| --- | ---: | ---: | ---: | ---: |
| 3 m, 3 degrees | 19 | 2 | 0 | 0 |
| 15 m, 8 degrees | 12 | 1 | 0 | 0 |
| 30 m, 15 degrees | 1 | 0 | 0 | 0 |

- Matches at the true pose, median over the 20 frames: surface 414 (211 inliers), ground 1, flat 1,
  top-down 0. On the 10 lost frames with the last good pose as prior: surface 2 solved, the rest 0.
- Range 200 m: surface 328 matches (15 of 20 solved), the others median 0 with at most 4, 15 and 44
  matches (ground, flat, top-down). Range 120 m: even the surface has a median of 0: on this clip the
  features the mesh matches are distant buildings, not the cemetery lawn within 120 m.
- The top-down view is sized to the ground within the range, so at 500 m the near ground is
  rendered at a few times coarser than the photo and the 200 m render disc did not cover the warped
  footprint. Reducing the photo by 1, 2, 4 and 8 before the warp (the photo's ground detail is about
  6 times finer than the 0.3 m imagery) gave medians of 0, 0, 0.5 and 0 matches, 1, 1, 4 and 0
  frames of 20 with 30 raw matches or more.
- Direction: `flat` and `ground` warp the satellite imagery into the drone's view (the imagery
  draped on a plane or the DTM and rendered at the pose); `top-down` warps the photo onto the ground
  plane and leaves the imagery as it is. Photo reduction on `flat` (imagery in the photo's view):
  at range 500 m the median raw matches were 1, 13.5, 4 and 3 for reductions of 1, 2, 4 and 8
  (5 of 20
  frames with 30 or more at a reduction of 2); at range 200 m 0, 6, 5 and 0.5 (4 of 20 at a reduction
  of 4). Raw matches before any geometric check, against a median of 328 to 414 on the surface.
- Not tried: a different matcher or scale-space (SIFT, a descriptor trained across aerial-ground
  scale), a photo-to-imagery model such as an aerial-ground matcher, or sharper imagery.

## Reading

Scope: one clip at 50 to 110 m above ground, oblique views, 20 frames. The owner reports that
warping the satellite imagery to the estimated view and matching works at sufficient altitude
(prior experience, not tested here); no altitude above this clip's was tried.

The imagery alone is not matchable by XFeat and LighterGlue against these photos: the Esri imagery
is blurrier, from another date and light, and the warp assumes a flat plane under houses and trees.
The mesh render carries the same imagery on relief, and 200 to 400 matches survive on it. The
suggestion to use imagery only to escape the mesh's poor look is not supported on this clip with
these matchers.
