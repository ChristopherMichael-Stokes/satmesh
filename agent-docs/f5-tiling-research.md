# F5 tiling research: tile formats, georeference, Gazebo and offline rendering

Researched 2026-10-25. `[measured]` is run locally (pyproj 3.8.0, PROJ 9.8.1). `[unverified]` has
no primary source found.

## Recommendation

1. **Canonical tile store, thin exporters.** One leaf tile per Web Mercator XYZ tile at a chosen
   level, holding heights, a texture made of whole Esri tiles, a TIN in true-metre local ENU, and
   a georeference record. Exporters write 3D Tiles 1.1 (CesiumJS, QGIS), GLB plus SDF (Gazebo) and
   GLB or OBJ in one area ENU frame (renderers).
2. **3D Tiles 1.1 as the primary format.** Cesium-native, but Gazebo and Python renderers need
   their own exporter anyway, and editing tiles means repacking GLBs.
3. **Quantized-mesh plus an XYZ imagery pyramid.** Best Cesium terrain behaviour, CesiumJS only.
4. **Obj2Tiles on one big OBJ.** Ruled out: needs the whole mesh and texture in memory.

Risks: cracks between tiles (no shared-edge option in pydelatin), the DTM-versus-DSM choice,
and missing PROJ grids, which silently cost about 51 m of height.

## 1. Formats

| | 3D Tiles 1.1, glTF content | Quantized-mesh plus imagery layer |
| --- | --- | --- |
| Tile holds | One GLB: mesh plus embedded texture ([spec](https://github.com/CesiumGS/3d-tiles/tree/main/specification)) | `.terrain`: header, u/v/height quantized to 0 to 32767, indices, edge-vertex lists ([spec](https://github.com/CesiumGS/quantized-mesh)); imagery is separate `z/x/y.jpg` |
| Level of detail | `tileset.json` tree; `geometricError` in metres; `REPLACE` swaps in children | Fixed quadtree; CesiumJS error per level is `154,135 m / 2^level` ([source](https://github.com/CesiumGS/cesium/blob/main/packages/engine/Source/Core/CesiumTerrainProvider.js)) |
| Depth per place | Leaves stop wherever data stops (explicit tree, or implicit availability bits ([spec](https://github.com/CesiumGS/3d-tiles/blob/main/specification/ImplicitTiling/README.adoc))) | `layer.json` `available` rectangles per level ([spec](https://raw.githubusercontent.com/CesiumGS/quantized-mesh/main/SPECIFICATION.md)); sparse imagery behaviour `[unverified]` |
| Seams | Ours to solve: skirts or shared edge vertices | Client builds skirts from edge indices ([CesiumJS](https://cesium.com/learn/cesiumjs/ref-doc/QuantizedMeshTerrainData.html)) |
| Heights | Any; we place them by transform | Metres above the WGS84 ellipsoid (same page) |
| Viewers | CesiumJS, QGIS 3.44 (explicit tilesets only, EPSG:4978 only ([QGIS](https://docs.qgis.org/latest/en/docs/user_manual/working_with_3d_tiles/3d_tiles.html))), 3DTilesRendererJS, deck.gl `Tile3DLayer` ([deck.gl](https://deck.gl/docs/api-reference/geo-layers/tile-3d-layer)), Cesium for Unreal/Unity, a WIP Blender add-on ([forum](https://community.cesium.com/t/cesium-for-blender-streaming-world-terrain-imagery-3d-tiles-incl-google-photorealistic-into-blender-open-source-wip/46938)) | CesiumJS, QGIS terrain, 3DTilesRendererJS overlay ([demo](https://nasa-ammos.github.io/3DTilesRendererJS/three/quantMeshOverlays.html)) |
| Static files | Yes | Yes; the spec asks clients to send an `Accept` header, which a static server ignores |

- Since 1.130, CesiumJS can drape imagery layers over 3D Tiles
  ([blog](https://cesium.com/blog/2025/06/30/draping-imagery-over-3d-tiles-in-cesiumjs/)), so 3D
  Tiles could also take a separate texture layer.
- `layer.json` accepts `"projection": "EPSG:3857"` (code linked above), so a quantized-mesh
  pyramid can follow the Esri grid.

## 2. Tooling

| Tool | Status | Role here |
| --- | --- | --- |
| pydelatin 0.4.0 | 2026-10-09 release, active ([PyPI](https://pypi.org/project/pydelatin/)) | TIN per tile. No constrained edges; `border_size` and `base_height` only |
| quantized-mesh-encoder 0.5.0 | 2025-06 release, pushed 2026-10 ([repo](https://github.com/kylebarron/quantized-mesh-encoder)) | Takes pydelatin output rescaled to lon, lat, ellipsoidal height. Writes edge indices (`encode.py`). No `layer.json` |
| py3dtiles 12.1.1 | 2026-03 ([PyPI](https://pypi.org/project/py3dtiles/)) | Point clouds and IFC to pnts/b3dm; glTF content is roadmap. Not a fit |
| 3d-tiles-tools 0.5.4 (npm) | 2026-07 ([repo](https://github.com/CesiumGS/3d-tiles-tools)) | Checks, `upgrade`, `merge`, `createTilesetJson` over existing GLBs; not a tiler |
| cesium-native | Active C++; no Python bindings found | None |
| Cesium Terrain Builder | Last push 2023; quantized-mesh only in a fork branch ([Docker](https://www.asg.ed.tum.de/en/gis/software/cesium-terrain-builder-docker/)) | Avoid |
| tin-terrain | Archived | Avoid |
| Obj2Tiles 1.8.0 (.NET) | 2026-10 ([repo](https://github.com/OpenDroneMap/Obj2Tiles)) | One OBJ in, LOAD tileset out |

No maintained Python tool writes a glTF-content `tileset.json`. That JSON is small and plain;
trimesh writes the GLBs and 3d-tiles-tools `validate`/`analyze` check the result.

## 3. Georeference

The correct pipeline is compound BNG+ODN (EPSG:7405) to WGS84 3D (EPSG:4979) through OSTN15 and
OSGM15, then ECEF (EPSG:4978) `[measured]`. PROJ picks "OSGB36 to ETRS89 (2) + ETRS89 to ODN
height (2) + ETRS89 to WGS 84 (1)", accuracy 1.04 m. Most of that 1 m is the ETRS89 = WGS84
identity, a shift common to the whole area. OS quotes OSGM15 at 8 mm rms on the mainland
([OS](https://docs.os.uk/more-than-maps/a-guide-to-coordinate-systems-in-great-britain/from-one-coordinate-system-to-another-geodetic-transformations/national-geoid-model-osgm15-etrs89-orthometric-height)).

The pyproj wheel ships neither grid, and the default network setting is off. Without the grids:

| Fallback at Upper Aire | Horizontal | Height |
| --- | --- | --- |
| Helmert "OSGB36 to WGS 84 (6)" | 1.6 m | −50.8 m (ODN treated as ellipsoidal) |
| Ballpark | 100.7 m | −50.8 m |

- To get the grids, set `PROJ_NETWORK=ON` (cached in the user data directory) or run `pyproj sync`
  ([pyproj](https://pyproj4.github.io/pyproj/stable/transformation_grids.html)). Grids:
  `uk_os_OSTN15_NTv2_OSGBtoETRS.tif`, `uk_os_OSGM15_GB.tif`.
- Guard: require `TransformerGroup(...).best_available` and raise otherwise.
- Frame each tile in topocentric ENU at its centre: `+proj=cart` then `+proj=topocentric`, both in
  PROJ. This gives true ground metres, Earth curvature included (−0.079 m at 1 km)
  `[measured]`.
- In glTF, write x = east, y = up, z = −north; the runtime turns y-up into z-up. The tile
  `transform` is ENU-to-ECEF at the centre. The BNG point-scale error (0.9996) disappears.
- Others: Cesium stores heights above the ellipsoid. Cesium ion converts orthometric heights with
  EGM96 by default (staff,
  [forum](https://community.cesium.com/t/what-height-options-to-select-for-cesiumion-terrain-upload/14422)).
  OSGM15 is more accurate in GB.
- Record both heights per tile: ellipsoidal h and orthometric H, linked by geoid N (+50.79 m
  here).

## 4. Grid and level of detail

- **Use the Web Mercator XYZ grid.** Each leaf texture is then a mosaic of whole Esri tiles with
  no resampling, and per-place native zoom is just leaf depth. Geographic TMS would resample
  every texel. A custom grid buys nothing.
- **Use an explicit `tileset.json`, not implicit tiling.** An implicit quadtree splits a region
  evenly in latitude, which Mercator rows are not. QGIS also reads only explicit tilesets.
- **Leaf size:** 4 × 4 Esri tiles, a 1,024 px texture. At z19 and 54°N that is about 180 m
  square, and a 20 km box needs about 12,400 leaves. Cesium terrain uses 65 × 65 heightmaps
  ([spec](https://github.com/CesiumGS/cesium/wiki/heightmap-1%2E0)). The 512 to 2,048 px texture
  range is common practice `[unverified]`.
- **Parents:** average 2 × 2 child textures down, keeping 1,024 px. Re-run Delatin on the DEM
  resampled to the parent grid, with `max_error` doubling per level.
- **Error:** `geometricError` = the tile's Delatin `max_error` combined with its texel size;
  leaves get roughly their GSD. Cesium's default `maximumScreenSpaceError` is 16
  ([doc](https://cesium.com/learn/cesiumjs/ref-doc/Cesium3DTileset.html)).
- **Seams:** add skirts, short walls hanging down from each tile edge (Cesium's method), about
  20 lines. Delatin cannot share edge vertices with a neighbour.

## 5. Fit to constraints

| Constraint | Canonical store + exporters | 3D Tiles primary | Quantized-mesh + imagery |
| --- | --- | --- | --- |
| Per-place depth (z17 vs z20) | Leaf depth | Leaf depth | `available`; imagery `[unverified]` |
| Enhanced texture or DEM swap | Replace the tile's file, re-export | Repack GLB (or external image URI) | Imagery swap trivial; DEM re-encode |
| Resumable, slow source | One tile is one unit, skip if present | Same | Same |
| CesiumJS from static files | Via exporter | Native | Native |
| Gazebo and renderers | Direct | Need a GLB-unpacking exporter | Need a decoder |
| Hand-rolled code | Tileset JSON, skirts | Same | `layer.json`, imagery pyramid |

## 6. Gazebo

- Formats: Harmonic's mesh manager (gz-common5) loads STL, COLLADA, OBJ, glTF/GLB and FBX; glTF goes
  through assimp
  ([source](https://github.com/gazebosim/gz-common/blob/gz-common5/graphics/include/gz/common/MeshManager.hh)).
  Current LTS releases are Harmonic (to 2029) and Jetty (to 2031)
  ([releases](https://gazebosim.org/docs/latest/releases/)).
- Georeference: `<spherical_coordinates>` with WGS84 and ENU, the only world frame
  ([docs](https://gazebosim.org/api/sim/8/spherical_coordinates.html)). gz-math converts through
  ECEF but calls `elevation` "relative to sea level"
  ([source](https://github.com/gazebosim/gz-math/blob/gz-math7/src/SphericalCoordinates.cc)).
  Ellipsoidal or orthometric is unclear `[unverified]`; set it once and test against NavSat.
- Large worlds: no terrain level-of-detail streaming found. "Levels" load and unload models by
  robot distance in one server (`--levels`) ([docs](https://gazebosim.org/api/sim/8/levels.html)).
  So: one static model per leaf at full resolution, all in one world ENU frame, grouped into levels.
- Collision: use a simplified or heightmap collider, not the visual mesh, because mesh contacts are
  expensive
  ([ROSCon 2024](https://roscon.ros.org/2024/talks/Optimizing_Gazebo_simulation-_Challenges_in_building_complex_simulation_environments..pdf)).
- Limits: DEM heightmaps load through GDAL, padded to 2^n + 1
  ([Dem](https://gazebosim.org/api/common/6/classgz_1_1common_1_1Dem.html)). Practical tile-count
  and VRAM limits are `[unverified]`; benchmark them.

## 7. Offline camera rendering

| Renderer | Takes | Convention |
| --- | --- | --- |
| pyrender | trimesh scenes (GLB, OBJ) | OpenGL camera: looks down −z, y up ([docs](https://pyrender.readthedocs.io/en/latest/examples/cameras.html)) |
| nvdiffrast | Clip-space tensors and textures; no file loader, no camera model ([docs](https://nvlabs.github.io/nvdiffrast/)) | We supply the matrices |
| Open3D, Blender, three.js | GLB/OBJ; Blender converts glTF y-up to z-up on import `[unverified]` | Per tool |
| CesiumJS headless | The 3D Tiles export | ECEF |

- What the store should expose: a TIN in tile ENU metres, its UVs and texture, the tile's ECEF
  origin and ENU-to-ECEF rotation, ellipsoidal and orthometric datum, and source and GSD.
- An exporter re-bases tiles into one area ENU frame for Gazebo and renderers. Across a 20 km
  box the tangent plane sits 7.8 m above the ground at the edges and 15.7 m at the corners, so
  area ENU must be built from ECEF, not by offsetting tile ENU frames.

## 8. Store format and DTM versus DSM

- Canonical store over 3D Tiles: three consumers want three framings, so 3D Tiles is one exporter
  among them.
- An orthophoto on a bare-earth DTM paints buildings and trees flat on the ground. Low or
  ground cameras then see through where walls should be. On a DSM, buildings become 2.5D lumps:
  no overhangs, and facades are stretched roof-edge texels.
- A conventional orthophoto still shows buildings leaning, because it was corrected only to terrain
  ([ISPRS](https://isprs-archives.copernicus.org/articles/XLII-2/1199/2018/isprs-archives-XLII-2-1199-2018.pdf)).
  True orthophotos need a DSM and occlusion handling. Whether Esri imagery is true-ortho is
  `[unverified]`.
- Prior art for realistic views is photogrammetric meshes from oblique imagery, such as Google
  Photorealistic 3D Tiles
  ([Google](https://developers.google.com/maps/documentation/tile/3d-tiles)), used for simulation in
  AirSim ([arXiv 2401.07962](https://arxiv.org/abs/2401.07962)).
- Implication: store DTM and DSM layers per tile. EA serves a 1 m first-return DSM (s5-results).
  Use the DSM for visibility checks, the DTM for ground and collision. Expect facades to be wrong
  either way.

## Thin first version

A 2 km box at Upper Aire, z19 leaves of 4 × 4 Esri tiles (about 120 leaves, ~2,000 tiles, ~35 min
uncached). Per leaf: DTM crop, Delatin, skirts, ENU GLB, store record. Plus one parent level,
an explicit `tileset.json`, and a check that it opens in CesiumJS from `python -m http.server`.
Then one Gazebo world from the same store. Checks:

- Vertex ECEF against pyproj with the grid available.
- No cracks at tile edges.
- The DTM height at a known benchmark.
