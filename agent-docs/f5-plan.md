---
status: historical
topic: baseline-pipeline
summary: F5 plan, built: tiled ENU store, 3D Tiles, Gazebo and GLB exporters, Typer CLI; replaced the single GLB
answers: How is the tile store designed?; Why tiles instead of one GLB?; How do parent nodes and tileset.json work?; What gaps did F5 leave?; Which CLI choices did the owner make?
---

# Plan: F5 tiled terrain store, exporters and `satmesh-cli`

> **Status note (2026-10-30).** The first-return DSM visual mesh listed here as not built was
> built as F5a (`f5a-results.md`).

Approved and implemented 2026-10-25 except the DSM (decision 2), which is not built: see `TODO.md`
F5a. Replaces the single-GLB F5 draft. Evidence and sources are in `f5-tiling-research.md`. Owner
chose Typer, a platformdirs cache with overrides, the EA DTM hard-wired for Great Britain, and no
quality compromise with the cost kept down.

As built, against the plan:

- Package `satmesh-tiles` holds the store, tiler and exporters; `satmesh-mesh` keeps grid
  triangulation, skirts and the GLB writer.
- A node's height grid is its own Web Mercator grid sampled by bilinear interpolation at 1 m for a
  leaf, so every vertex has an exact UV; parents sample at 2 m per level and mesh at twice the
  error.
- A parent exists only where all four children do. `tileset.json` is a contentless container over
  the maximal complete nodes, with the container's `geometricError` set to its extent so CesiumJS
  refines it. Use `maximumScreenSpaceError` 1 to 2 in the viewer for crisp texture.
- `export 3dtiles` writes `tileset.json` into the store directory (no copies).
- Gazebo collision uses the visual mesh for now (F5b). The glTF roll pose, `elevation` datum and
  levels follow gz-common and gz-math source reading and are untested in a running Gazebo.
- Verified live on Upper Aire: a 500 m box built 18 nodes in 3 s from cache; CesiumJS render
  seamless across levels; area GLB render; Gazebo SDF generated. No Gazebo run.

## Goals driving the design

- Render from a virtual camera over the tiles and check that what is visible on the ground in
  reality is visible in the render (video-to-map matching): true ground scale, accurate
  georeference, known height datum.
- Populate Gazebo with the tiles and run a robotics stack on them.
- View in CesiumJS.
- Each tile at the best resolution its location supports; any size of area, with no whole-area
  texture cap.

## Design

One canonical tile store; exporters write what each consumer needs.

| Piece | Shape |
| --- | --- |
| Grid | Web Mercator XYZ, the Esri grid. A leaf is 4 x 4 Esri tiles at the place's native zoom: 1,024 px, about 180 m square at z19 and 54 N. Depth per place is native zoom, so z17 places get coarser leaves |
| Leaf texture | The 16 Esri tiles stitched as they are: no resampling, no size cap, and the same pixels an enhanced texture later replaces |
| Leaf mesh | pydelatin TIN of the DTM at `max_error` 0.1 m, vertices in true-metre topocentric ENU at the leaf centre. UVs come from each vertex's lon/lat projected to Web Mercator, so they are exact and the BNG reprojection step disappears |
| Seams | Skirts: short walls hanging from every leaf edge. pydelatin cannot share edge vertices with a neighbour |
| Parents | 2 x 2 child textures averaged to 1,024 px; the DEM resampled to the parent grid and re-triangulated at `max_error` doubling per level |
| Record per leaf | ECEF origin and ENU-to-ECEF rotation, ellipsoidal height h and orthometric height H with geoid N, Esri source, capture date and GSD, DTM source |
| Georeference | EPSG:7405 (BNG with ODN height) to EPSG:4979 through OSTN15 and OSGM15, then ECEF, with `+proj=topocentric` for ENU. The BNG point-scale error and Earth curvature drop out |
| Build | Resumable: a leaf with its files present is skipped, and the Esri cache persists per tile |

### Georeference guard

The pyproj wheel ships neither UK grid. Without them the transform falls back silently and heights
come out 50.8 m low, horizontal 1.6 m off (Helmert) or 100.7 m (ballpark) at Upper Aire
(`f5-tiling-research.md`). The build requires `TransformerGroup(...).best_available` and raises
otherwise, with the fix in the message (`PROJ_NETWORK=ON` or `pyproj sync`).

### Exporters

| Command | Writes | For |
| --- | --- | --- |
| `export 3dtiles` | Explicit `tileset.json` (implicit tiling cannot follow Mercator rows; QGIS reads explicit only) plus the leaf and parent GLBs with an ENU-to-ECEF `transform` | CesiumJS, QGIS |
| `export gazebo` | One SDF world with `spherical_coordinates` (ENU), one static model per leaf at full resolution, grouped into levels, simplified collision | Gazebo Harmonic |
| `export glb` | One GLB or OBJ in a single area ENU frame, built from ECEF so a 20 km box is not off by 8 to 16 m at its edges | pyrender, Blender, Open3D |

### CLI

```text
satmesh build  --bbox W S E N [--crs EPSG:4326] --store DIR [--cache-dir DIR] [--max-error-m 0.1]
satmesh export {3dtiles|gazebo|glb} --store DIR --out PATH
```

Typer app with an `@app.callback()` so subcommands stay named. The cache defaults to
`platformdirs.user_cache_dir("satmesh")` and takes `--cache-dir` or `SATMESH_CACHE_DIR`. The build
raises when `metric_crs(aoi)` is not BNG. The AOI is snapped outward to whole BNG metres, then to
whole leaves.

## Decisions for you

| # | Fork | Recommendation | Alternative |
| --- | --- | --- | --- |
| 1 | Primary format | Canonical store with exporters: Cesium, Gazebo and renderers each want a different frame, and swapping an enhanced texture or DEM means replacing one leaf | 3D Tiles as the store; Gazebo and renderers unpack GLBs |
| 2 | Surface | Store DTM and the EA 1 m first-return DSM per leaf; visual mesh from the DSM so buildings and trees exist for cameras, DTM for ground and collision. A DSM gives lumps with smeared facades, never real walls; photogrammetric meshes are the only realistic source and are out of scope | DTM only first: buildings and trees stay painted flat on the ground, so a low or oblique camera cannot see them. The EA DSM `GetCoverage` has never been run |
| 3 | Leaf size | 4 x 4 Esri tiles (1,024 px) | 2 x 2 (more, smaller leaves, finer Gazebo levels) or 8 x 8 (heavier leaves) |
| 4 | New package | `satmesh-tiles` (store, tiler, exporters); `satmesh-mesh` keeps triangulation and GLB writing; `satmesh-cli` stays thin | Everything in `satmesh-mesh` |

## Removed or reshaped

- `drape_texture` and `MAX_TEXTURE_PX` go: leaves use whole Esri tiles.
- F4's BNG-metre frame and the point-scale record in `extras` give way to ENU plus the leaf record
  (F4 decision 2 is superseded).
- `to_glb` is reshaped to write one leaf with skirts.

## Cost

Fetch time is the limit: 1 Esri request/s. A 2 km box is about 2,000 tiles (about 35 min uncached),
a 20 km box about 198,000 tiles (about 55 h), resumable per tile. No code removes this; the cache
makes every rerun and every re-export free.

## Known gaps

- Esri imagery sits about 2.4 m off EA imagery (S6) and the drape is unmeasured: a matching
  pipeline will see it. Measured in F6, corrected in E2.
- Whether Esri imagery is a true orthophoto is unknown; if not, buildings lean in the texture.
- Gazebo's `elevation` datum (ellipsoidal or orthometric) is unverified; set once and test against
  NavSat. Tile-count and VRAM limits are unverified; benchmark.
- Wales and Scotland have no EA coverage; the DTM check should fail loudly there (to confirm live).
- `sources_at` is not cached, so a cached rerun still makes one identify request.
- Cracks between same-level neighbours are hidden by skirts, not removed.
- Cesium handling of sparse tiles, and Blender's glTF axis conversion, are unverified.

## Dependencies

| Package | New dependencies |
| --- | --- |
| `satmesh-tiles` | `satmesh-core`, `satmesh-data`, `satmesh-mesh`; `pyproj` already present |
| `satmesh-cli` | `satmesh-tiles`, `typer`, `platformdirs` |

`[project.scripts] satmesh = "satmesh_cli.main:app"`. `uv.lock` is regenerated. The tileset JSON is
written by hand (small and plain; no maintained Python writer); 3d-tiles-tools (npm) validates it
outside the build.

## Tests

- ENU and ECEF round trip against pyproj with the grids present, plus the guard raising without
  them. Expected values from the definitions, not from the code.
- Leaf: a synthetic DTM gives a mesh within `max_error`; UVs sampled through the Web Mercator
  definition; skirts reach below the edge; every face points up.
- Tiling: leaf set for a known box worked out from the XYZ definition; a rerun skips finished
  leaves.
- Exporters read back with an independent reader (pygltflib; SDF parsed as XML; `tileset.json`
  against its schema).
- Live smoke, outside `make test`: 2 km Upper Aire box (about 120 leaves), opened in CesiumJS from
  `python -m http.server`, one Gazebo world, one renderer view; checks: vertex ECEF against pyproj,
  no visible cracks, DTM height at a known benchmark.

## Checkpoints

1. Georeference module, grid guard and leaf mesher with tests.
2. Tiler and store with the resumable build; one leaf, then the 2 km box.
3. `export 3dtiles`, opened in CesiumJS.
4. `export gazebo` and `export glb`; a camera render.
5. CLI, docs (`TODO.md`, `AGENTS.md`, `README.md`).
