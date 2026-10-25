# F6 results: evaluation harness

Plan: `f6-plan.md`. `[live]` marks what was observed against the cached Upper Aire data.

## Checkpoint 1: package, height scores, pipeline check (2026-10-25)

### Conclusions

- `satmesh-eval` installs on Python 3.13 with xdem 0.2.3, geoutils 0.2.5 and scikit-image 0.26.0.
- Ray caster: trimesh with embreex. Open3D 0.20 has no CPython 3.13 wheel for this Ubuntu 20.04
  (its 0.20 wheels need glibc 2.35); embreex 4.4.0.post1 resolves on 3.13.
- The georeference chain checks out against an independent path on the DSM store built in F5a
  `[live]`: over 18 nodes the terrain vertices sit within 0.07 mm median and 1.7 mm at the 95th
  percentile of the DSM raster at their own BNG position, and each ground grid within 7 micrometres
  of the DTM. The path is pyproj ECEF to EPSG:7405 plus a separate bilinear sampler; the build used
  neither.
- This does not measure lidar accuracy: the mesh is built from the same raster.

### Built

- `heights.py`: median, NMAD, 68.3 % and 95 % quantiles (Höhle and Höhle 2009, order-statistic
  definition), RMSE for comparison, per-stratum scores and a block (cluster) bootstrap interval.
  NMAD comes from `geoutils.stats.nmad`; `xdem.spatialstats.nmad` is deprecated.
- `strata.py`: xdem slope classes (edges 5, 15, 30 degrees, tunable) and the raised-object mask
  (first-return surface more than 2 m above the ground, tunable).
- `pipeline_check.py`: `check_store` and `check_node`. `satmesh-data` gained `cached_lidar_path`
  so the check finds the rasters a record names.

### Tests

- Statistics against values worked from the definitions (hand-counted order statistics); NMAD
  against an outlier that moves RMSE; block bootstrap against blockwise-constant errors where a
  pixel bootstrap must come out at least 3 times narrower; slope classes against a plane of known
  angle.
- Check against a synthetic store with analytic planes; a DSM shifted by 1.5 m after the build must
  read -1.5 m.
- `make check` and `make test` (104 tests) pass.

### Next

Checkpoint 2: EA aerial slice (index search, tile download, ECW to GeoTIFF in the `gdal-ecw`
container), then the offset measurement on a synthetic shift and at Upper Aire.

## Checkpoint 2: EA aerial slice and Esri-to-EA offset (2026-10-25)

### Conclusions

- Esri sits about 0.8 to 1.0 m north of the EA 2020 imagery and at most 0.3 m west `[live]`. This
  replaces S6's "about 2.4 m (0.8 m south, 2.3 m west)", which is not reproduced. A first version of
  this checkpoint measured 2.2 to 2.9 m north and was wrong for the reason below.
- The offset is not one rigid shift: windows on raised objects differ from open ground (D, below).

| Site (1 km box, BNG SW corner) | East m (95 % interval) | North m (95 % interval) | NMAD E, N m | Reliable windows |
| --- | --- | --- | --- | --- |
| Upper Aire (399500, 447000), Vivid 2025-03, z19 | -0.02 (-0.11, 0.04) | 0.76 (0.55, 0.96) | 0.49, 0.83 | 143 of 900 |
| Ferrybridge (448000, 424000), z19 | -0.34 (-0.42, -0.22) | 0.99 (0.78, 1.24) | 0.48, 1.56 | 196 of 900 |

Positive east and north mean Esri is displaced east and north of EA. EA is RGBN 2020, 0.1 m
(captured 2020-02-27); both images go to a 0.25 m BNG grid, 256 px windows at 50 % overlap. The
intervals reflect window sampling only, not variation between sites.

### Trap: GDAL as bundled with rasterio has no UK grids

`rasterio.warp` from EPSG:3857 to EPSG:27700 uses a Helmert fallback because the rasterio wheel
ships no OSTN15. At Upper Aire it differs from pyproj with the grids by 0.23 m west and 1.56 m
north, the size of the offset being measured. The first measurement reprojected Esri with it and so
reported the Helmert error as an imagery offset. `luminance_on_grid` now samples non-BNG rasters
through pyproj's best transformation, raises if it lacks the grids, and is tested against a
Web Mercator raster with a bright spot at a known WGS84 point (expected BNG position from pyproj,
tolerance 0.3 m, far under the 1.5 m error). S6's number very likely carries the same error. The
store build uses pyproj and was never affected.

### Site change

The planned Lower Aire box (BNG 452000 425000) failed: the 2020-02-27 survey caught the River Aire
in flood, so the floodplain fields are under water in EA and dry in Esri, and only 31 of 900
windows were reliable with an NMAD of 3 m. Replaced by a box at Ferrybridge and Knottingley, also
inside the Lower Aire block: river, a road and rail bridge, factory roofs, terraced housing. A box
at 448000 423000 was rejected because the 2020 coverage ends inside it (55 % black).

### Method and what it took to make it work

- Phase correlation per window (`skimage` with 100 times subpixel upsampling) recovers known
  displacements of 2.4 m east 0.8 m south, 1.137 m west 0.523 m north and zero to within 2.5 mm
  (0.01 px) on synthetic band-limited texture with exact Fourier shifts. Windows need a Hann taper
  and mean removal, or the window edge makes the zero-shift peak win.
- On real pairs the raw shifts are unusable: on Upper Aire 402 textured windows gave shifts across
  -16 to 16 m, and skimage's `error` is 1 for every window under phase normalisation. The
  correlation peak height from `cv2.phaseCorrelate` separates real matches: median 0.22 inside the
  main cluster against 0.04 outside. The threshold is the 99th percentile of the peak between
  unrelated windows of the same two images (0.08 to 0.11 at the two sites); 15 to 20 % of windows
  survive, mostly hedges, roads and buildings.
- AROSICS 1.13.2 (the established tool for this) resolves on Python 3.13 but its `gdal` Python
  dependency fails to build here, so it is not used.
- `skimage.registration.phase_cross_correlation` accuracy is 1/upsample_factor px (documented), so
  the test tolerance is 1.5 times 0.01 px.

### Built

- `satmesh-data` `ea_aerial.py`: `find_aerial_tiles` (the search endpoint wants
  `application/geo+json`), `fetch_aerial_ecws` (streaming zip with a byte cap, flat file names,
  zip deleted after unpacking), `crop_aerial` (VRT and `gdal_translate -projwin` for the RGB bands
  in the `satmesh-gdal-ecw` container; requires `docker`). A 5 km square of 10 cm RGBN is 257 MB
  zipped, downloads in 10 s and holds 1 km ECWs named by flight frame, not by grid reference.
- `satmesh-eval` `offset.py` (`luminance_on_grid`, `window_shifts`, `null_response_threshold`,
  `reliable`, `summarise`, `measure_offset`) and `imagery.py`; opencv-python-headless added.
- 116 tests pass; `make check` passes.

### Not checked

- Date effect: EA is 2020 and Esri 2022 to 2025, so moved or growing objects add noise to windows
  but not a bias in the median unless changes are directional.
- Two sites; each interval reflects window sampling only, not variation between sites.

## Checkpoint 3: relief dependence and end-to-end drape (2026-10-25)

### Conclusions

- The drape is registered: a top-down orthographic render of the store (rays through the leaf
  meshes in BNG, texture sampled at the hit's UV) against the Esri mosaic it was built from offsets
  by 0.08 m east and -0.08 m north (0.25 m grid; 778 windows, NMAD 0.0 m) at Ferrybridge `[live]`.
  The render against EA gives -0.22 m east, 0.78 m north, against 0.99 m north for Esri against EA
  at the same site: the store adds no offset of its own and carries the Esri-to-EA one.
- Raised objects are displaced differently from open ground, which a rigid correction cannot fix:

| Site | Open ground windows | North m (95 %) | Object windows | North m (95 %) |
| --- | --- | --- | --- | --- |
| Upper Aire | 52 | 0.80 (0.72, 0.94) | 13 | 1.26 (0.10, 2.39) |
| Ferrybridge | 17 | 1.26 (-0.57, 1.68) | 50 | -0.35 (-1.41, 0.99) |

  East on Upper Aire objects is 1.79 m (0.24, 2.42) against -0.08 on open ground. Intervals are
  wide and the directions disagree between sites, so this shows relief dependence is likely but
  does not yet say which image leans. Spearman correlation of shift with mean height above ground
  is weak (|rho| 0.22 or less).

- Whether Esri is a true orthophoto stays open. A lean test needs the offset against radial
  distance from each image's nadir point, which neither source gives us.

### Method

- A window is an object window if at least 30 % of its pixels stand 2 m or more above the DTM
  (first-return DSM minus DTM), open ground if at most 2 % do (all tunables, `relief.py`).
- Render: `store_mesh`-style loader in `render.py` reads each leaf GLB, moves vertices to BNG and
  ODN height by pyproj, and casts one ray per 0.25 m cell with trimesh and Embree
  (`embreex 4.4.0.post1`). 36 leaves and 555,000 faces render in 36 s. Pixel difference to the
  source mosaic: median 1.3, 95th percentile 8 luma levels (JPEG and resampling).
- The render test is close to tautological for flat UVs, since a top view of a planimetrically
  mapped texture is the texture. It does check that vertex positions, UVs and the OSTN15 chain
  agree.

### Not checked

- Skirts and seams in the render: no cell fell outside a leaf, but the coverage test only shows
  every cell was hit.
- Upper Aire render (a 500 m store); only Ferrybridge was rendered.

## Checkpoint 4: height error of the store and camera visibility (2026-10-25)

`visibility.py` and `mesh_score.py` in `satmesh-eval`. Reference is the EA first-return DSM
triangulated at 1 m (2 million triangles per km2); test meshes are the store's finest nodes (555,000
faces at Ferrybridge) and a DTM-only mesh standing for a store without F5a. Cameras are pinhole,
90 degree horizontal field of view, 320 x 240 px, 30 per rig, placed at random on open ground
(surface within 0.5 m of the ground, so none starts inside a building or tree); ground rig 1.7 m up
and level, drone rig 60 m up at -25 degrees pitch. Range limit 300 m (Ferrybridge) and 150 m (Upper
Aire, a 500 m store). Tolerance tau(r) = 0.5 m + 1 % of range. All are tunables.

### Conclusions

- The DSM store carries what cameras see; a DTM-only store does not `[live]`. Pixel agreement with
  the reference within tau (reference-hit pixels):

| Site | Rig | DSM store | DTM only |
| --- | --- | --- | --- |
| Ferrybridge | ground | 95.5 % | 53.2 % |
| Ferrybridge | drone | 98.0 % | 69.5 % |
| Upper Aire | ground | 93.1 % | 80.9 % |
| Upper Aire | drone | 97.3 % | 81.7 % |

- Surface points on raised objects (patches 2 m or more above the DTM, at least 4 m2, 3,000
  sampled): a DTM-only store shows 0 of them from ground cameras and 0.2 % from the drone, as
  expected, since the ground has no objects. The DSM store shows only 69 % (ground) and 89 % (drone)
  at Ferrybridge, and 56 % and 70 % at Upper Aire. The loss is not a tolerance effect: loosening it
  by 8 times lifts Ferrybridge's ground-camera figure from 69 % to 78 %; the store's hit is
  typically within 0.2 m of the point (median +0.16 m) and the misses are rays that pass through a
  smoothed crown or edge and land tens of metres behind (95th percentile +56 m).
- The cause is in the store, not the metric. Height error of the store against the DSM at the DSM's
  own pixel centres (vertical rays, `surface_height_error`):

| Stratum | Ferrybridge NMAD m | p95 m | Upper Aire NMAD m | p95 m |
| --- | --- | --- | --- | --- |
| Open ground | 0.041 | 0.30 | 0.038 | 0.13 |
| Raised objects (2 m or more) | 0.133 | 1.39 | 1.106 | 5.33 |
| Slope under 5 degrees | 0.030 | 0.07 | 0.034 | 0.07 |
| Slope over 30 degrees | 0.370 | 1.53 | 0.984 | 5.07 |

  Medians are within 4 cm everywhere except Upper Aire raised objects (-0.34 m): the store
  loses height at tree crowns and roof edges. Cause, by reading `node.py`: a leaf samples the DSM
  bilinearly on its own Web Mercator grid at 1 m spacing. Those nodes fall between the DSM's
  pixel centres, so bilinear interpolation averages up to four neighbours and flattens 1 m crowns
  and edges, and the 0.1 m TIN error then applies to the already smoothed grid. `max_error_m` is
  therefore an error against the resampled grid, not against the lidar.

- Pixels the store hits where the reference does not (skirts, edges) are 0.01 to 0.03 % of the
  reference-hit pixels.

### Method notes

- The reference and store share a source, so agreement on open ground (about 4 cm NMAD) checks the
  georeference chain and TIN, not the lidar.
- A flat-topped building has no single apex, so objects are tested by sampled surface points. A
  first apex-based version failed on a flat roof whose interior a 1.7 m camera cannot see.
- A first version let cameras land inside buildings; rays from there gave range errors of 100 to
  200 m. Cameras are now drawn on open ground only.
- Tests: synthetic ground and blocks with ranges worked out by trigonometry (45 degree look-down
  gives 20 / sin 45 degrees), heading clockwise from north, projection against ray round trip,
  ground-only mesh shows no raised point, occluded points not visible.

### Not checked

- Probable viewshed under DSM error (Fisher), planned once the error model exists; the height
  error table above is that model.
- Camera sets beyond 30 per rig and one seed.
- Whether first-return canopy is what a leaf-off or oblique camera sees through trees.

### Follow-up: nearest-pixel DSM sampling at 0.5 m (2026-10-25)

Tried on Upper Aire (500 m) with four ways of sampling the DSM, then adopted the best in the
pipeline. Height error of the store against the DSM, and share of reference-visible raised points
shown (ground rig, drone rig):

| Sampling | Raised-object NMAD, p95 m | Raised points shown | Store size |
| --- | --- | --- | --- |
| Bilinear, 1 m (before) | 1.11, 5.33 | 56 %, 70 % | 7.3 MB |
| Nearest, 1 m | 1.05, 5.10 | 67 %, 79 % | 7.2 MB |
| Bilinear, 0.5 m | 0.54, 3.24 | 61 %, 75 % | 19 MB |
| Nearest, 0.5 m (adopted) | 0.00, 0.02 | 85 %, 92 % | 25 MB |

Nearest at 0.5 m hits each 1 m DSM pixel with four grid nodes, so every pixel value survives; at
1 m the nodes fall between pixel centres and nearest sampling drops or doubles pixels. The DTM
ground grid stays bilinear. Built through the pipeline (`LEAF_GRID_SPACING_M` 0.5):

| Site | Raised-object NMAD, p95 m | Raised points shown, ground, drone | Pixel agreement, ground, drone | Store size |
| --- | --- | --- | --- | --- |
| Ferrybridge | 0.000, 0.049 (was 0.133, 1.39) | 87 %, 97 % (was 69 %, 89 %) | 95.7 %, 98.4 % | 81 MB (was 27 MB) |
| Upper Aire | see table above | 85 %, 92 % (was 56 %, 70 %) | 93.5 %, 97.7 % | 30 MB (was 7.3 MB) |

Open ground improved too (Ferrybridge NMAD 0.041 to 0.021 m). Vertices at the 18 and 46 nodes sit
within 0.07 mm of their DSM pixel value. Remaining misses are 0.25 m lateral slack at steps and
the 1 m pixel staircase against the reference's sloped ramps. Cost: about 3 times the vertices and
store size; the ground grid, bilinear on a 0.5 m node grid, is 4 times larger than before.
