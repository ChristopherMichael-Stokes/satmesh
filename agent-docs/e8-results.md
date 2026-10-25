# E8 results: lidar surface refinement

Survey: `e8-research.md`. Point cloud spike: `lidar-pointcloud-spike.md`. `[live]` marks what was
run on the cached Upper Aire 500 m box (BNG 399750 447250), scored with `satmesh_eval`.

## Step 1: resampling and node placement

### Conclusions

- Where the mesh nodes sit relative to the DSM's pixel centres matters more than the interpolation
  method. With nodes exactly on the pixel centres, plain linear interpolation reproduces the DSM
  at every pixel centre (raised-object NMAD 0.000 m), shows 92.5 % (ground cameras) and 94.7 %
  (drone) of camera-visible raised points, and has no terracing signature `[live]`. The pipeline's
  node grid is regular in Web Mercator, so its nodes sit at arbitrary offsets from the BNG
  pixel centres; 0.25 m off, the same linear mesh drops to 0.94 m NMAD and 60 % / 76 % shown,
  matching what the store measured (61 % / 75 %). The earlier "bilinear flattens crowns" reading
  was largely this misplacement, not bilinear itself.
- Where nodes cannot be aligned, cubic interpolation on a finer grid recovers most of it: cubic at
  0.25 m spacing gives raised NMAD 0.10 m (p95 0.45) and 79.5 % / 87.0 % shown, smooth on open ground.
- Nearest-pixel sampling is worst for smoothness even when aligned (aspect excess +0.593,
  normal error median 5.4 degrees).

### Table

Mesh = regular grid of the sampled DSM, triangulated without TIN simplification, 15 cameras per
rig, 150 m range, one seed. Normal error is the open-ground median in degrees.

| Sampling, spacing, node phase from pixel centres | Raised NMAD m (p95) | Normal err deg | Aspect excess | Pixel agreement g, d | Raised shown g, d |
| --- | --- | --- | --- | --- | --- |
| Linear, 0.5 m, 0 (aligned) | 0.000 (0.00) | 1.06 | +0.007 | 98.7, 99.5 % | 92.5, 94.7 % |
| Linear, 0.5 m, 0.25 m | 0.942 (4.02) | 0.58 | +0.004 | 96.1, 98.1 % | 60.3, 76.4 % |
| Nearest, 0.5 m, 0 | 0.000 (0.00) | 5.44 | +0.593 | 94.2, 97.4 % | 77.9, 88.4 % |
| PCHIP, 0.5 m, 0 | 0.000 (0.00) | 1.08 | +0.008 | 98.4, 99.4 % | 90.1, 94.0 % |
| PCHIP, 0.5 m, 0.25 m | 0.572 (2.53) | 0.92 | +0.018 | 97.7, 98.9 % | 67.3, 82.1 % |
| Cubic, 0.5 m, 0 | 0.001 (0.00) | 1.18 | +0.007 | 97.8, 98.6 % | 81.2, 87.9 % |
| Cubic, 0.5 m, 0.25 m | 0.525 (2.24) | 1.09 | +0.004 | 97.6, 98.5 % | 75.2, 84.8 % |
| Linear, 0.25 m, 0.0625 m | 0.381 (1.63) | 0.90 | +0.004 | 97.6, 99.0 % | 64.9, 79.1 % |
| Cubic, 0.25 m, 0.0625 m | 0.103 (0.45) | 1.18 | +0.005 | 97.2, 98.2 % | 79.5, 87.0 % |

Cubic is `scipy.interpolate.RegularGridInterpolator(method="cubic")` (SciPy 1.18.1); the survey's
Catmull-Rom is not in SciPy and was not hand-rolled.

### Not checked

- The TIN stage (pydelatin at 0.1 m) and the tile structure: these meshes are plain grids, so
  vertex counts and store size under each option are unmeasured.
- How each looks in Blender; the smoothness score is one ordering, not validated against the eye.
- One site, one seed, 15 cameras per rig (the earlier 30-camera runs took too long to watch).
- Aligning nodes to the BNG pixel grid conflicts with leaves cut on the Web Mercator tile grid
  (rotation 0.2 to 0.6 degrees at the two sites); a design question, see `status.md`.

## Step 2: raw point cloud (spike)

The EA raw LAZ downloads unauthenticated through the same service as the aerial imagery; a 5 km
tile is 155 MB. At Upper Aire (SD9947) first returns are 2.07 points/m2, with ground, three
vegetation heights and building classes (the EA docs mention only ground and surface objects).
Details and caveats in `lidar-pointcloud-spike.md`. No triangulation experiment yet.

## Step 3: held-out raw points as an independent reference (2026-10-25)

`pointcloud.py` in `satmesh-eval` (`read_first_returns`, `split_holdout`, `height_error_at_points`;
`laspy[lazrs]` 2.7.0 added). 10 % of the first returns (noise class dropped) are held out; each mesh
is scored by its height at the held-out points minus theirs, so the error is measured between the
raster's pixel centres. Ferrybridge tile SE4520 (survey 2020-12 to 2021-03, 31,110 held-out points:
21,391 ground, 4,839 vegetation, 4,037 building) and Upper Aire SD9545 (34,672: 31,504 ground,
3,043 vegetation, 42 building). Throwaway scripts, not committed.

### Conclusions

- Raw-point Delaunay (C) does not beat the shipped EA DSM at held-out points, and the test cannot
  show it should: the DSM was rasterised from all the points, held-out ones included, so it knows
  them. Against the shipped DSM, linear 1 m (the aligned mesh) beats C everywhere at Ferrybridge
  (building NMAD 0.043 against 0.047 m, p95 1.22 against 2.37 m; ground p95 0.63 against 1.06 m).
- Against rasters built here from the same 90 % of points, the contest is fair. C's typical error
  on buildings is about 3 times smaller (NMAD 0.047 against 0.145 to 0.150 m at Ferrybridge; 0.089
  against 0.148 to 0.194 m at Upper Aire, 42 points), ground NMAD is 0.025 against 0.029 to 0.030 m,
  and vegetation NMAD is slightly better (0.449 against 0.475 to 0.496 m). Its tails are worse on
  buildings (p95 2.37 against 1.96 to 2.06 m, RMSE 0.95 against 0.86 to 0.92 m).
- Moorland (Upper Aire) is a tie on ground and vegetation among all meshes: 91 % of its first
  returns are ground.
- The shipped DSM at the held-out points is much closer than rasters made here from 90 % of the
  points (Ferrybridge building NMAD 0.043 against 0.145 m); the gap is leakage plus EA's own
  processing, and the two cannot be separated from this data.

### Not checked

- Where C's tail errors fall (triangles bridging a wall between roof and ground is the suspect).
- Class-aware construction (ground points for terrain, building points for roofs), the route by
  which C could use what the DSM discarded.
- Whether the Ferrybridge survey epoch (2020-12 to 2021-03) matches the DSM's.
- The camera-visibility checks against a point-based reference.

## Step 4: building roofs and walls (2026-10-25)

Prototype (scratch script, not in the repo): building-class first returns are grouped into
footprints from 1 m occupancy cells, roof planes fitted per building by RANSAC (0.15 m tolerance,
up to 8 planes, 106 buildings and 363 planes at Ferrybridge), the surface inside a footprint set
to its nearest fitted plane and a 1 m ring outside it set to the DTM, on a 0.25 m grid. Rendered
textured and shaded against the current pipeline in three camera views.

- Roofs came out flat and walls vertical in two scenes. A third showed a stair-stepped roof
  outline from the 1 m footprint cells, and some roof parts the plane fit missed.
- Wall texture streaks in both versions because the aerial photo is draped from above.

## Decision (owner, 2026-10-25)

Shaded renders of the current bilinear 0.5 m pipeline mesh, node-aligned bilinear (A), raw-point
Delaunay (C) and the roof-plane prototype were compared by eye. The owner judged the current
bilinear mesh best by far in all cases except flat building sides, and A, C and the roof prototype
were rejected. E8 stops here and the pipeline's sampling stays as it is.

- A and C scored better against the DSM at pixel centres (node-aligned linear: raised NMAD 0.000 m
  against 0.94 m, 92 % against 60 % of camera-visible raised points shown at Upper Aire), and
  looked worse to the eye: spiky trees and triangle noise on roofs. Height and visibility scores
  against the DSM did not predict the eye's ranking; `satmesh eval smoothness` ranked meshes the way
  the eye did on open ground only.
- The held-out point test did not show raw points beating the shipped DSM.
- Kept: `pointcloud.py` and `laspy` in `satmesh-eval`, the point-cloud download route
  (`lidar-pointcloud-spike.md`), and the survey (`e8-research.md`) for any later geometry work.
- Not tried: PixTransform with Esri guidance, learned DSM super-resolution, tree crown models.
  Their hallucination risk is high in the survey, and E4 and E7 cover the same ground.
