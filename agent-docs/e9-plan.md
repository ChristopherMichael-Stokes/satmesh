# E9 plan: stretched texture on steep faces

Survey: `e9-research.md`. Awaiting owner approval.

## Problem in our data

Each node is one nadir JPEG draped by planar UV on a TIN of the 1 m DSM (sampled every 0.5 m). A
face whose normal is tilted by `theta` from vertical samples a strip of texture `1 / cos(theta)`
times thinner than the ground: building walls, tree sides and steep roof pitches show a smeared
streak of whatever lies under them in the image. Nothing about those faces was observed, so no
method can recover it; the choice is how to show it honestly.

## Proposal

Do the cheapest option first and make every non-measured pixel visible to tests: snap the UVs of
steep triangles to measured texels, and flag them.

- A triangle is steep when `1 / cos(theta)` exceeds a threshold (starting value 3, about 70 degrees,
  to be set from the stretch histogram in S0).
- "Snap": each vertex of a steep triangle takes the UV of the nearest vertex that belongs to no
  steep triangle and lies at the same level (a wall's top vertices take roof-edge texels, its
  bottom vertices take ground texels). The GPU then blends smoothly between two measured colours
  across the wall. No texel is created, resampled or generated; the JPEG is untouched. It adds
  no high-frequency structure for a matcher to lock onto.
- Flag: a per-vertex glTF attribute `_FILL` (0 measured, 1 stretched and left alone, 2 snapped)
  and a per-node count in the node record. The original UV is the planar projection of the
  vertices, so the step is reversible and repeatable like `correct`.

## Stages

| Stage | Work | Go criterion |
| --- | --- | --- |
| S0 | Per-triangle stretch for the Upper Aire, Ferrybridge and Snettisham stores: histogram, share of mesh area and of area seen by the low-oblique camera rig in `eval visibility`; choose the threshold | Steep triangles are under 10 % of visible area at ground cameras, or the owner wants it regardless |
| S0b | Is the Esri imagery a true orthophoto? At 20 buildings, compare roof outlines in the lidar nDSM with the roof edges in the image, by azimuth; shared with plan E2b stage T2 | Result recorded: lean present or not |
| S1 | `satmesh fill-steep --store DIR` (or as part of `correct`), writing `_FILL`, UVs and the node record; unit tests on a synthetic wall | Tests pass; second run rewrites nothing |
| S2 | Textured renders from fixed low and oblique cameras, store as built against snapped, side by side, plus a flat-colour pass of `_FILL` | The owner judges by eye that the snapped walls read better than the streaks |
| S3 | Matching check: render pairs of low oblique views with known poses, match with OpenCV SIFT, report inliers, reprojection error and the share of matches on flagged triangles, for built against snapped | Snapped inliers not below built; matches on flagged triangles that fail the known geometry are counted as fabrications |
| S4 | Results doc, status, TODO, `make check` | Checks pass |

S2 comes before S3 because earlier scores against the DSM did not predict the owner's ranking.

## Not in this plan

Exemplar or learned fills (Resynthesizer, LaMa, catalogue facades) and wall-strip UV charts
(xatlas). They need S1's flag and a baseline to beat; the survey ranks them 2 to 5. Revisit only if
S2 says the snapped walls are not good enough.

## Decisions for the owner

1. Where the flag lives. Proposed: `_FILL` vertex attribute in the node GLB, plus a flat-colour
   export (`export glb --fill-map`) for renderers that cannot read custom attributes. Alternative:
   a sidecar mask only.
2. Whether snapping is on by default in exports or an explicit step. Proposed: an explicit step
   recorded in the node record, so `positional_error.json`-style reporting can state it.
3. Threshold (proposed 3, set in S0).

## Risks

- A tall wall between a roof and the ground becomes a vertical gradient, which looks plausible but
  is not the wall. That is the point of the flag.
- Triangles that span both a wall and flat ground (the TIN is decimated to 0.1 m error) are not
  steep by normal; they keep their stretch. Measured in S0.
- Skirts are steep by construction; they are excluded.
