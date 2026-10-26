# E9 results: stretched texture on steep faces

Plan: `e9-plan.md`. Stretch of a triangle is `1 / |cos θ|` with θ the angle of its normal from
vertical, in the BNG/ODN mesh. Skirt triangles are excluded (their faces are those that use a
vertex at or past `terrain_vertices` of the node record).

## S0: stretch histogram (2026-10-26)

Stores built for this measurement (git-ignored): `uncommitted/s0/{upper-aire,ferrybridge,snettisham}`,
500 m boxes at Upper Aire (Esri z19) and Ferrybridge (z19), and a 740 m box at Snettisham (z18).
Script: scratch, `s0_stretch.py`. "Camera view" is the share of pixels from 30 random open-ground
cameras (320 x 240, 90 degree field of view, 1.7 m high, level, range 40 m, seed 1) whose first hit
is a triangle above the threshold.

| Site | Terrain 3D area over 3 | Faces over 3 | Ground-camera pixels over 2 | over 3 | over 5 |
| --- | --- | --- | --- | --- | --- |
| Upper Aire (farmland, hedges, houses) | 31.0 % | 213,399 of 417,012 | 9.0 % | 4.1 % | 2.4 % |
| Ferrybridge (town, industry) | 12.4 % | 95,480 of 463,702 | 14.3 % | 10.5 % | 4.4 % |
| Snettisham (fen, coast) | 0.44 % | 12,518 of 339,846 | 0.04 % | 0.0 % | 0.0 % |

- The threshold 3 meets the plan's go criterion (under 10 % of ground-camera pixels) at two of three
  sites; Ferrybridge is at 10.5 %. Threshold 5 gives 4.4 % there.
- By 3D area the mesh is far steeper than by view: at Upper Aire 13.5 % of the terrain area has
  stretch over 10 (tree crowns, hedges and walls with a rough 0.5 m DSM), yet ground cameras
  see 4 % of their pixels on faces over 3.
- The drone rig (60 m high, range 40 m) hits nothing within range; its steep-face share is not
  measured.

## S0b: is Esri a true orthophoto? (2026-10-26)

Method (subagent, scratch scripts, nothing in the repo): buildings are 4-connected nDSM > 3 m
components of 40 to 20,000 m2 that pass solidity (convex hull at least 0.75, min-area rectangle
fill at least 0.60) and a roughness test against trees (median absolute Laplacian of the 1 m DSM
at most 0.30 m, set at the gap in the roughness histogram before any offset was seen). Per
building, normalised cross-correlation of the DSM gradient magnitude against the Esri luma
gradient magnitude within 4 m (accepted: peak at least 0.30, runner-up at most 0.9 of the peak),
then least squares of the offset on roof height with a bootstrap over buildings.

- Upper Aire: untestable. 30 candidates over 3 m, none pass: everything is woodland and moor.
- Ferrybridge: inconclusive. 10 pass the building tests, 3 to 5 match; slope CI spans zero.
- Worcester (not a survey site; its Esri z19 tiles and DSM were already cached): 86 buildings in 8
  boxes of about 0.58 km2. Pooled slope of offset on height, E -0.26 [-0.35, -0.19] and
  N -0.49 [-0.60, -0.38] m per m, azimuth 208 degrees (roofs displaced south-south-west as they get
  taller); the sign is negative in all 7 boxes with at least 5 buildings. Median offset by roof
  height: 3 to 5 m (-0.5 E, +1.4 N), 9 to 14 m (-2.8 E, -1.7 N).
- Synthetic check (known lean added to Worcester DSMs): no false positive on the null case,
  direction recovered, magnitude about half the truth. The real lean is therefore larger than
  measured.

Conclusion: Esri imagery is not a true orthophoto at Worcester, where a 10 m roof sits about 3 to
6 m from its lidar footprint. For England generally and for the plan's sites it is undetermined.
Match quality is the weak part (peak NCC 0.3 to 0.7, about 12 % of offsets over 3 m north are
probably false matches). Worcester is one scene set; scene geometry, not place, sets the lean.
