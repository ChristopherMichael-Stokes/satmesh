# F5 results: tiled store, exporters and CLI

Built 2026-10-25 at Upper Aire, near Skipton. `[live]` marks what was observed against endpoints or
a renderer; everything else is covered by `make test`. Plan: `f5-plan.md`; evidence behind the
design: `f5-tiling-research.md`.

## Conclusions

- The chain Esri tiles + EA 1 m DTM to a georeferenced, resumable tile store works, and exports to
  CesiumJS, Gazebo SDF and a single GLB. A 500 m box gives 16 leaves at z17 and 2 parents; 18
  nodes build in about 3 s with every tile cached `[live]`.
- Geometry is in true-metre local ENU. The OSGM15 geoid separation at Upper Aire is 50.8 m
  (matches the 50.79 m measured in the research); without the UK grids PROJ falls back silently
  and heights come out 50.8 m low, so the build raises instead.
- Not built: the DSM (F5a), a decimated Gazebo collision mesh (F5b), large-area DTM fetch (F5c).
  Nothing is scored against ground truth yet (F6).

## Store layout

- `<store>/nodes/{z}/{x}/{y}.glb` and `.json`; the record is written last, so its presence marks a
  finished node. Writes go to `.part` then rename.
- Record (`NodeRecord`): tile, origin lon/lat, ellipsoidal and ODN origin heights, geoid
  separation, row-major ENU-to-ECEF matrix, ENU bounds including skirts, grid spacing and nodes,
  vertex and triangle counts, `max_error_m`, achieved `error_m`, skirt depth, texture px, imagery
  source, resolution, capture date and equivalent zoom, DTM file name.
- GLB frame: x east, y up, z south, metres, origin at the node's ENU origin (centre of the tile,
  at the node's minimum ellipsoidal height). Texture is a JPEG (quality 92) embedded in the GLB.
- Leaf: 4 x 4 Esri tiles at `native zoom - 2`, 1,024 px. Height grid sampled at 1 m on the node's
  own Web Mercator grid (about 181 x 181 nodes), then pydelatin at 0.1 m. Parents: 2 x 2 mean of
  child textures, grid spacing and `max_error` doubled per level.
- Skirt depth is 4 x the node's `max_error_m`: the gap between neighbours is at most the sum of
  both TIN errors, under twice the coarser one; the factor leaves margin.

## Numbers at Upper Aire `[live]`

| Item | Value |
| --- | --- |
| AOI | BNG 399750 447250 400250 447750 (500 m) |
| Leaf zoom, Esri zoom | z17, z19 (Vivid 0.34 m, 2025-03) |
| Nodes | 16 leaves, 2 parents (z16) |
| Leaf vertices | 437 to 3,300 (terrain dependent); one leaf 1,783 vertices, 3,480 triangles, 0.16 MB GLB |
| Store size | 2.8 MB for 18 nodes |
| Build | 18 nodes in 2.8 to 8.3 s (8.3 s included one WCS request per node); rerun 0 s |
| Geoid separation | 50.8 m |

## Checks

| Check | Result |
| --- | --- |
| UV against vertex Web Mercator position, read back from the GLB with ECEF to geodetic to 3857 | within 1e-5 of the box |
| Heights against a synthetic BNG plane DTM, round trip through OSTN15 and OSGM15 | within `max_error` plus float32 resolution |
| ENU frame against PROJ `+proj=topocentric` at four latitudes | within 1e-5 m |
| Tileset: composed transforms equal each node's ENU-to-ECEF; parent box contains child boxes; boxes contain their GLB vertices | pass |
| Area GLB: every leaf vertex at its own ECEF position after rebasing | within 2 mm |
| Gazebo SDF: mesh placed at the node's ECEF position through pose, visual roll and PROJ topocentric inverse | within 5 mm (checks our convention, not Gazebo) |
| CesiumJS 1.140.0 headless (Chromium, swiftshader) | 10 tiles selected at SSE 1; seamless across z16 and z17; road, hedges and river sit correctly |
| three.js area GLB render | north up; road on the relief; faint hairline seams at some tile edges |

## Bugs the live checks found

- Cesium showed nothing: the contentless container's `geometricError` (0.7 m) was below the
  threshold, so Cesium judged it good enough and never refined. The container's error is now its
  extent. Child tiles loaded only at `maximumScreenSpaceError` 0.01.
- Parent textures had their southern quadrants swapped: `mercantile.children` returns NW, NE, SE,
  SW; `parent_texture` assumed NW, NE, SW, SE. `ordered_children` fixes the order for both.
- `stored_tiles` built `Tile(x, y, z)` from path parts in the wrong order; caught by tests.

## Library and viewer notes

- pyproj: the wheel ships no UK grids. `pyproj sync --file uk_os_OSTN15_NTv2_OSGBtoETRS.tif` and
  `--file uk_os_OSGM15_GB.tif` write to `~/.local/share/proj`; `make setup` does it. Guard:
  `TransformerGroup(...).best_available`. `plan_tiles` checks before any fetch.
- trimesh puts `Scene(metadata=...)` into glTF `scenes[0].extras`.
- 3D Tiles: children's `transform` is relative to the parent's, so each is
  `inverse(parent) @ own`. Matrices are written column-major. The container's box is the union of
  its children's, and a parent's box is the union of its own vertices and its children's boxes.
  Use an explicit tree: implicit tiling splits evenly in latitude, which Mercator rows are not,
  and QGIS reads only explicit tilesets.
- For crisp texture in CesiumJS set `maximumScreenSpaceError` to 1 to 2; the default 16 allows
  16 px blur. `geometricError` of a node is `max(max_error_m, texel size)`.
- SDF: `<pose>` rotation is Rz Ry Rx of roll, pitch, yaw (scipy `as_euler("xyz")`). A roll of
  +90 degrees sends glTF (x east, y up, z south) to (x east, y north, z up).
- Gazebo (from source reading, not run): gz-common keeps the glTF root transform and does not
  convert Y-up to Z-up; gz-math reads `elevation` as ellipsoidal height; relative mesh URIs
  resolve against the world file's directory; mesh collision takes a GLB; levels are a
  `gz::sim` plugin (`gz sim --levels`) with `<performer>` and one `<level>` per tile.
- Headless CesiumJS: `Cesium3DTileset.fromUrl`, `camera.lookAt`, GL via
  `--use-angle=swiftshader`; wait on `statistics.numberOfTilesWithContentReady`.
  Playwright 1.49.1 is the newest that supports this Ubuntu 20.04; Node is not installed in WSL.
- Typer 0.27.3 vendors Click; a one-command app collapses its subcommand, so `build` and the
  `export` group keep distinct names.

## Reproduce

```sh
cd pipeline
uv run satmesh build --bbox 399750 447250 400250 447750 --crs EPSG:27700 --store DIR --cache-dir C
uv run satmesh export 3dtiles --store DIR      # then serve DIR with python -m http.server
uv run satmesh export glb --store DIR --out area.glb
uv run satmesh export gazebo --store DIR --out gz --performer robot
```

A fresh run fetches about 16 Esri tiles per leaf at 1 request/s plus one WCS request per node.
The S5 and F3 live caches (Esri tiles and the 1 km EA DTM for the Upper Aire box, BNG 399500
447000 400500 448000) were kept in the F3 harness cache and reused here.

## Not checked

- Gazebo itself, and mesh-collision step time.
- Imagery to DEM horizontal offset, and whether Esri imagery is a true orthophoto.
- DSM coverage and GetCoverage; Wales and Scotland DTM coverage.
- Parents past about 6 km (DTM fetch size).
- DEM sampling of coarse parents is point-sampled bilinear, not area-averaged.
