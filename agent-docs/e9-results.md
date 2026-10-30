---
status: historical
topic: surface-refinement
summary: E9 results: stretch histograms at three sites (4 to 10 % of ground-camera pixels over 3x); Esri orthorectification
answers: How much of a ground camera's view is steep faces?; Is Esri imagery a true orthophoto?; Which sites were measured?; Why was E9 closed?
---

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

Stretch histogram, share of terrain 3D area and of terrain faces per stretch bin
(`uncommitted/s0/ferrybridge.s0.txt`, `snettisham.s0.txt`; Upper Aire's histogram file was not
kept). Ferrybridge has 463,702 terrain and 6,788 skirt faces over 630,466 m2 of terrain, Snettisham
339,846 and 4,664 over 2,212,317 m2:

| Stretch bin | Ferrybridge area | Ferrybridge faces | Snettisham area | Snettisham faces |
| --- | --- | --- | --- | --- |
| 1 to 1.1 | 69.418 % | 25.191 % | 97.181 % | 75.661 % |
| 1.1 to 1.5 | 8.885 % | 24.759 % | 2.075 % | 15.942 % |
| 1.5 to 2 | 4.030 % | 14.182 % | 0.134 % | 2.255 % |
| 2 to 3 | 5.265 % | 15.276 % | 0.171 % | 2.458 % |
| 3 to 5 | 6.131 % | 12.815 % | 0.224 % | 2.332 % |
| 5 to 10 | 5.149 % | 6.925 % | 0.191 % | 1.258 % |
| 10 and over | 1.122 % | 0.851 % | 0.023 % | 0.093 % |

- Over 2: Ferrybridge 17.667 % of area (166,317 faces), Snettisham 0.610 % (20,872 faces). Over
  5: 6.271 % (36,058 faces) and 0.214 % (4,593 faces).
- Ground-camera pixels over 2 at Ferrybridge 14.300 %, 1,208,794 pixels hit within 40 m; Snettisham
  0.038 % of 1,113,652, and 0.000 % over 3 and 5.
- The drone rig (60 m high, pitch -25 degrees, range 40 m) hits no pixel at either site.
- Command, from `pipeline/`: `uv run python ../uncommitted/scratch-archive/s0_stretch.py STORE
  "LAT, LON" "LAT, LON"` (store, then NW and SE corners; `main(store, nw, se)`). Store builds are
  logged in `uncommitted/s0/builds.log`.

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

Matcher variants and counts (`uncommitted/scratch-archive/s0b/progress.log`, `run.out`,
`run_extra.out`, `synth2*.json`). The matcher runs on four references: the DSM gradient (`dsm`), the
DSM gradient with a footprint-masked template (`dsmt`), lidar intensity (`int`) and masked
intensity (`intt`). The search radius was 6 m first; a few outliers at about 5 m led to a rerun
with 4 m, which gives the numbers below and in the pooled slope above. At 6 m the pooled `dsm`
slope was 0.656 over 89 buildings and `dsmt` 0.503 over 114.

| Site | Components over 3 m | Passed building tests | Accepted `dsm` | `dsmt` | `int` | `intt` |
| --- | --- | --- | --- | --- | --- | --- |
| Upper Aire | 30 | 0 | 0 | 0 | 0 | 0 |
| Ferrybridge | 60 | 10 | 3 | 1 | 5 | 2 |

Ferrybridge at 6 m search: `dsm` 3, `dsmt` 2, `int` 6, `intt` 1.

The eight `x35*` boxes of about 0.58 km2 (BNG E 351892 to 354925, N 237291 to 238828; see the
S0b location note in `e2b-results.md`) and the two Dunster boxes (`x299*`), accepted by `dsm` and
`dsmt` of the buildings attempted:

| Box (SW corner E, N) | Components | Passed | Attempted | `dsm` | `dsmt` |
| --- | --- | --- | --- | --- | --- |
| 351892, 237312 | 188 | 37 | 37 | 13 | 16 |
| 351899, 238064 | 323 | 57 | 57 | 14 | 16 |
| 352645, 237305 | 162 | 48 | 48 | 24 | 29 |
| 352652, 238057 | 139 | 25 | 25 | 14 | 13 |
| 353399, 237298 | 160 | 31 | 31 | 11 | 15 |
| 353406, 238050 | 154 | 21 | 21 | 5 | 8 |
| 354153, 237291 | 99 | 4 | 4 | 2 | 0 |
| 354160, 238043 | 152 | 5 | 5 | 0 | 1 |
| Dunster 299146, 143216 | 21 | 0 | 0 | 0 | 0 |
| Dunster 299530, 143209 | 10 | 0 | 0 | 0 | 0 |

The pooled `dsm` set is 83 buildings from the seven `x35*` boxes with acceptances plus the 3 at
Ferrybridge (86 in 8 boxes); pooled `dsmt` 97 in 6 boxes, slope 0.518, azimuth 218 degrees. The
box funnel for the 323-component box: 31 failed the edge test, 62 solidity or rectangle fill,
226 roughness.

Ground registration on the DTM does not work at either site (96 windows at Upper Aire, 36 at
Ferrybridge; the intensity reference gave few windows too):

| Site | DTM windows ok | Median E, N (m) | sd E, N (m) | Intensity windows ok, median E, N |
| --- | --- | --- | --- | --- |
| Upper Aire | 10 of 96 | +0.09, +0.52 | 1.73, 0.93 | 4 of 40, -0.02, +1.18 |
| Ferrybridge | 0 of 36 | none | none | 7 of 36, -0.96, +2.42 |

At the 6 m search radius: Upper Aire 14 of 96, median (+0.63, +0.39), sd (2.6, 2.9); Ferrybridge
3 of 36, median (-4.17, +2.81), sd (3.5, 1.2). A separate scene-level check of the lidar intensity
against Esri (windows of the whole box) gave Ferrybridge E -0.54, N +1.70 (7 of 196 windows, NMAD
0.79, 1.60) and Upper Aire E -0.11, N +1.36 (8 of 84, NMAD 1.06, 1.31).

Synthetic check (`synth2.py`): a synthetic image built from the DSMs and DTMs of four `x35*` boxes
(351892, 352645, 352652 and 351899 west edges; 159 to 161 buildings accepted), ground shift (1.0,
0.5) m throughout; recovered slope is |slope| in m per m, `lean_present` is the fit's own test:

| Case | Truth | `dsm` recovered | `dsmt` recovered | Ratio of truth |
| --- | --- | --- | --- | --- |
| Null, no lean | 0 | 0.004 | 0.019 | not present |
| Lean added to the DSM before matching, (-0.25, -0.5), k 0.559 | 0.559 | 0.024 (not present) | 0.047 (present) | 0.04 to 0.08 |
| Forward projection, (-0.15, -0.25), k 0.292 | 0.292 | 0.143 (E -0.075, N -0.122, az 211) | 0.166 | 0.49, 0.57 |
| Forward projection, (+0.10, +0.05), k 0.112 | 0.112 | 0.050 | 0.064 | 0.45, 0.57 |
| Forward projection with step edges, (-0.15, -0.25) | 0.292 | 0.160 | 0.170 | 0.55, 0.58 |

- The first variant (lean added to the DSM before matching) missed the lean at (-0.25, -0.5);
  why the forward-projection variant replaced it is not documented. A 10-building synthetic on the
  Ferrybridge DSM (`run.out`, truth slope (0.10, 0.05), intercept (1.0, 0.5)) recovered slope E
  +0.075 [0.022, 0.123], N -0.005 [-0.051, +0.049] with `dsm` (10 of 10 accepted) and E +0.095, N
  +0.006 with `dsmt` (9 of 10).
- Recovery is about half of the truth in the forward cases, which is the "magnitude about half"
  above.
