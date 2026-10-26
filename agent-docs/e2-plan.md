# E2 plan: lidar-referenced correction of the Esri imagery position

Design B of `e2-research.md`. Survey: `offset-survey.md`. Awaiting owner approval.

## Goal

Place the Esri texture at its true ground position in England and Wales, including roof and
canopy lean, without EA aerial imagery at the place being built. EA aerial covers about 5 % of
England from 2020 on, so it is the test set, never an input to the correction.

## Model

Esri Vivid is satellite imagery; a scene is close to a parallel projection, so per Esri source
polygon:

- bias shift `(dE, dN)` in metres, constant over open ground;
- lean `(sin a, cos a) * k * h`, with `h` the height above ground from the EA nDSM, `a` the lean
  azimuth and `k` the metres of lean per metre of height (tan of the off-nadir angle).

Three to four parameters per polygon. Applied as a per-vertex UV offset `shift + h * k * (sin a,
cos a)`, so the texture is never resampled. The combined fit is not a published method (gap noted
in `e2-research.md`); the stages below test it before anything depends on it.

## Stages

Each stage ends with a go or stop call against its criterion. A stop returns to the owner.

| Stage | Work | Go criterion |
| --- | --- | --- |
| B0 | Download the 5 km LAZ tiles under the eight survey boxes (about 155 MB each, no auth, route in `lidar-pointcloud-spike.md`); check intensity is present and usable; fetch Esri source polygon (identify) at each box | Intensity present at all eight boxes; each box lies in one or two source polygons |
| B1 | Render the reference rasters on the 0.25 m BNG grid: first-return intensity (per-flight-line normalisation if the spike shows it is needed), DSM, nDSM | Rasters look right by eye on two boxes |
| B2 | Register Esri against the reference per window, open ground only; compare each window's shift to the EA-aerial shift from `eval offset` | Median difference from the EA-aerial result is at most the threshold in decision 1, at 5 of 8 boxes |
| B3 | Fit shift and lean per polygon from object windows, fitting on half the windows and scoring on the other half | Held-out object-window residual falls against the shift-only fit |
| B4 | Apply the parameters as per-vertex UV offsets; re-render the corrected store top-down and run `eval offset` against EA aerial on the eight boxes | Corrected offset against EA aerial within the threshold in decision 1 |
| B5 | Results doc, `status.md`, `TODO.md`; `make check` | Checks pass |

B2 first tries phase correlation on gradient-magnitude images (the tool already built and
validated in `offset.py`). Mutual information (`sklearn.metrics.mutual_info_score`, as in Parmehr et
al. 2013) is added only if gradient correlation fails the B2 criterion.

## Decisions for the owner

1. Accuracy threshold for B2 and B4. Proposed 0.3 m (about half an Esri z18 pixel), against a
   measured 0.2 to 2.8 m offset. A tunable, called out.
2. Where the parameters live. Proposed: a per-polygon parameter file beside the store, applied by
   the exporters, so a revised fit replaces one file and no node is rebuilt. Alternative: bake the
   offsets into the node GLBs at build time.
3. Wales. The Welsh Government lidar is listed only as 1 m DTM and DSM COGs (`uk-sources.md`); raw
   points and intensity are unchecked. Proposed: England first, then a short check of Welsh point
   data. With DSM alone, the literature gives 50 % template success against 90 % with intensity.
4. Seams. A polygon boundary inside a leaf gives two shifts in one texture. Proposed: apply the
   offset per vertex by the polygon containing that vertex, accept a visible step at the boundary,
   and measure how often it happens at B0.

## Costs and traps

- Download about 1.2 GB of LAZ for eight boxes at most; fewer where boxes share a 5 km tile.
- Intensity is un-normalised 16-bit; flight lines and dates differ between tiles (spike).
- Lean fit on EA aerial truth is muddied because EA aerial has its own radial lean; B3 therefore
  scores against the lidar reference, and B4 scores open ground and objects separately.
- Occluded ground behind leaning objects stays wrong; no single-image method fixes it.
- Esri `BlockName` suggests a polygon can hold many scenes; if shifts vary inside a polygon, the
  model fails at B2 and the design returns to the owner.
