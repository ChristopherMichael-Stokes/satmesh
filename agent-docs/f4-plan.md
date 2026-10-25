# Plan: F4 `satmesh-mesh`, DTM plus texture to GLB

Approved 2026-10-25 with option A for both decisions; implemented the same day. Turns the S5
spike (`s5-results.md`) into a package. Inputs come from F2 (DTM GeoTIFF) and F3 (cropped Web
Mercator `Raster`).

As built, against the plan:

- `drape_texture(raster, box)` takes the TIN's box (the DTM's extent, carrying its CRS) rather
  than an AOI and a CRS, so texture and mesh cover the same box by construction.
- Checking the DTM CRS against `metric_crs(aoi)` moves to F5, which picks the DTM.
- Pillow is a direct dependency: trimesh textures are Pillow images.

## Scope

In: reproject the texture to the mesh CRS, triangulate the DTM, drape, export one GLB with its
georeference.

Out, each with its own later task:

- CLI wiring and default paths (F5).
- Esri-to-DTM horizontal offset (S6 measured 2.4 m between Esri and EA imagery): measured in F6,
  corrected in E2 if needed.
- Chunked meshes or tiled textures for AOIs past the texture cap (later, quantized-mesh or split
  GLBs).
- DSM meshes, skirts, a solid base.

## Units

| Unit | Shape |
| --- | --- |
| `drape_texture(raster, aoi, crs, pixel_m) -> Raster` | Bilinear reprojection of the F3 crop onto a north-up grid exactly covering the AOI box in `crs` |
| `triangulate(dtm_path, aoi, max_error_m) -> Tin` | pydelatin on the DTM heights; `Tin` holds vertices in CRS metres (E, N, height) and triangles |
| `to_glb(tin, texture, path) -> MeshReport` | Local glTF frame, affine UVs, non-metallic material, JPEG texture, georeference in `extras` |
| `MeshReport` | Frozen dataclass: vertex and triangle counts, Delatin error, origin (E, N, height), CRS, texture px and pixel size, point scale |

- Mesh CRS is the DTM's CRS (BNG for EA), checked against `metric_crs(aoi)`.
- glTF frame as in S5: x east, y up, z south, origin at the AOI centre and the DTM minimum. The
  origin and CRS go in the scene's `extras`, so a consumer can put the mesh back on the map.
- Delatin vertices map by the raster's affine transform, with y counted from the bottom row (S5).
  `rescale_positions` is not used: it assumes a square raster.
- Winding is set so face normals point up, checked on the built arrays rather than via
  `trimesh.invert` (stale normals under `process=False`, S5).
- `MAX_ERROR_M` default 0.1 m: under the EA composite's quoted 15 cm RMSE, so the TIN adds less error
  than the source carries. 61k vertices per km2 at Upper Aire (S5).

## Decisions (owner chose A for both)

### 1. Texture size cap

At z19 (about 0.18 m at 54 N), a 1 km AOI wants about 5,700 px; WebGL guarantees only 4,096 px on
some mobile GPUs, and most desktops take 16,384.

| Option | Effect |
| --- | --- |
| A. Cap at 8,192 px; coarsen the pixel size to fit and record it in `MeshReport` (recommended) | Full source detail up to about 1.4 km; larger AOIs degrade gracefully and visibly in the report |
| B. Cap at 8,192 px and raise past it | No silent loss; the caller must shrink the AOI or pass a coarser pixel |
| C. Cap at 4,096 px | Works on every WebGL device; loses detail past about 0.7 km |

Default pixel size is the source tile GSD, so the texture never upsamples past the source.

### 2. BNG and UTM scale factor

Projected XY is off ground distance by the point scale k: 0.9996 at Upper Aire (0.04%, 0.5 m over
1.4 km), up to about 1.001 at a UTM zone edge. Heights are true metres.

| Option | Effect |
| --- | --- |
| A. Leave XY in CRS metres; record k in `extras` and `MeshReport` (recommended) | Mesh overlays other BNG data exactly; error under one DTM pixel below about 2.5 km |
| B. Divide XY by k about the origin | True ground scale; overlays with CRS data need the factor undone |

## Dependencies

| Package | New dependencies | Why |
| --- | --- | --- |
| `satmesh-mesh` | `satmesh-core`, `satmesh-data`, pydelatin, trimesh, numpy, rasterio | Triangulation, glTF export |
| dev group | pygltflib, matplotlib | Independent glTF reader for the UV contract; TIN interpolation for the error check |

pydelatin and trimesh need only numpy; `uv.lock` is checked for PyTorch after adding them.

## Tests

- Synthetic DTMs written in the test: a tilted plane (exact with two triangles), a Gaussian hill.
- Worst |mesh − DTM| over every pixel centre, by interpolation on the TIN's own triangles
  (`matplotlib.tri`), is at most `max_error_m`.
- Orientation: a peak placed in the DTM's north-east quadrant lands at x > 0, z < 0 in the GLB.
- UV contract: raw `TEXCOORD_0` read with pygltflib follows glTF's top-left origin for the AOI box.
- Every face normal points up; the material is non-metallic; the texture is JPEG.
- `extras` round-trip: origin and CRS read back with pygltflib put a vertex at its CRS coordinate.
- Live harness: the S5 box through F2, F3 and F4 reproduces the S5 report (counts, extents, height
  range) and renders north-up in three.js.

## Docs

`TODO.md` F4 ticked; `AGENTS.md` layout lists `satmesh-mesh`.
