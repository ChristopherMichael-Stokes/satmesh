---
status: historical
topic: baseline-pipeline
summary: S5 spike: EA DTM plus Esri drape to GLB works; 1 km at 0.1 m error gives 61k vertices; four library traps
answers: Does the baseline mesh chain work end to end?; Why mesh in BNG instead of Web Mercator?; Is delatin's error bound exact?; What pydelatin and trimesh traps exist?
---

# S5 results: mesh baseline, EA DTM plus Esri drape to GLB

Run 2026-10-25 at Upper Aire, near Skipton. `[live]` marks what was observed against endpoints.

## Conclusions

- The baseline chain works end to end: EA 1 m DTM from WCS, Esri z19 reprojected to BNG, pydelatin
  TIN, affine UV drape, GLB. A 1 km square gives 61k vertices and a 4.2 MB GLB at 0.1 m max error,
  and it renders correctly in three.js.
- Vertical scale is right by construction when XY and height are both metres in one projected CRS.
  The GLB height range equals the DTM range to the millimetre, so no `z_scale` is needed. The
  EPSG:3857 trap (XY 1/cos(lat) too long, about 1.7 times at 54 N) is avoided by meshing in BNG.
- BNG XY is 0.04% short of ground distance at this site (point scale 0.9996013), while height is
  true metres. That is 0.5 m over the 1.4 km diagonal, under the 1 m DTM pixel. F4 can ignore it in
  the UK or divide XY by the point scale. Elsewhere F4 needs its own local metric CRS.
- Delatin's error bound holds: the worst |mesh − DTM| over every DTM pixel equals `max_error` at
  each setting tried. Triangulation takes under 0.3 s for 1 M pixels, so `max_error` is a free knob
  for output size.
- Four library traps to handle in F4:
  - pydelatin's y axis counts rows up from the bottom of the array.
  - pydelatin's `rescale_positions` assumes a square tile.
  - trimesh's default material renders an orthophoto near black.
  - `trimesh.Trimesh.invert` leaves cached normals stale under `process=False`.

## Site and sources

| Item | Value |
| --- | --- |
| Box | BNG 399500 to 400500 E, 447000 to 448000 N (1 km square, centre -2.0015, 53.9236) |
| DTM | EA LIDAR Composite DTM 1 m, WCS 2.0.1 GetCoverage [live]; 1000 × 1000 float32, 88.96 to 211.90 m |
| Imagery | Esri Vivid 2025-03, `SRC_RES` 0.34 m, z19, 576 tiles at 1 request/s [live] |
| Texture | Bilinear reproject to BNG, 4096 px square (0.244 m/px), embedded JPEG |

DTM request, no key [live]:

```text
https://environment.data.gov.uk/spatialdata/lidar-composite-digital-terrain-model-dtm-1m/wcs
  ?service=WCS&version=2.0.1&request=GetCoverage&format=image/tiff
  &coverageId=13787b9a-26a4-4775-8523-806d13af58fc__Lidar_Composite_Elevation_DTM_1m
  &subset=E(x0,x1)&subset=N(y0,y1)
```

- The response is EPSG:27700, 1 m pixels, and its edges match the requested integer box exactly.
  Nodata is -3.4028235e38; the box had none.
- The 1 m first-return DSM is coverage
  `df4e3ec3-315e-48aa-aaaf-b5ae74d7b2bb__Lidar_Composite_Elevation_FZ_DSM_1m` on
  `.../lidar-composite-digital-surface-model-first-return-dsm-1m/wcs`. Its id came from
  GetCapabilities; no GetCoverage was run against it.
- No size limit was found: 6000 × 6000 (151 MB) returned in 9.6 s.
- DescribeCoverage states no vertical datum. ODN is assumed, not confirmed.

## Mesh

- Vertices sit on DTM pixel centres, so the mesh spans 999 m; the texture spans the full 1000 m box
  and UVs are an affine function of BNG XY.
- glTF axes: x east, y up, z south, origin at the box centre and the DTM minimum (BNG 400000 E,
  447500 N, 88.963 m). Local float32 coordinates stay under 1 km, so precision is not an issue.

| `max_error` m | Vertices | Triangles | Worst \|mesh − DTM\| m | Triangulation s |
| --- | --- | --- | --- | --- |
| 0.05 | 153,460 | 306,009 | 0.050 | 0.28 |
| 0.1 | 60,955 | 121,387 | 0.100 | 0.15 |
| 0.25 | 16,029 | 31,817 | 0.250 | 0.09 |
| 0.5 | 5,542 | 10,931 | 0.500 | 0.06 |
| 1.0 | 2,043 | 4,004 | 1.000 | 0.05 |

The worst error is measured by linear interpolation on the TIN's own triangles
(`matplotlib.tri.LinearTriInterpolator`). A Delaunay re-triangulation of the vertices, as
`scipy.interpolate.LinearANDInterpolator` does, reports 0.37 m at a 0.1 m setting and is wrong for
this check.

## Checks

| Check | Result |
| --- | --- |
| GLB extent x, y, z (reloaded) | 999.0, 122.938, 999.0 m |
| GLB height range against DTM range | 88.965 to 211.903 against 88.963 to 211.903 m |
| Box diagonal, BNG against WGS84 geodesic | 1414.214 against 1414.738 m |
| Raw `TEXCOORD_0` against glTF top-left UV origin, read with pygltflib | exact |
| Faces with an upward normal | 100% |
| three.js r170 `GLTFLoader` render, top and oblique | north up; road, River Aire meander and wooded slope sit on the matching relief |

The render ran headless through Playwright 1.49.1. Playwright 1.64 does not support Ubuntu 20.04.

## Library notes

- pydelatin `Delatin(arr, max_error=…)`: `vertices[:, 0]` is the column, and `vertices[:, 1]` is
  `rows − 1 − row`, so BNG N = south + y + 0.5. `max_error` is in height units, which are metres
  here.
- pydelatin `rescale_positions` scales both axes by the larger of the x and y extents, which skews
  non-square rasters. Map vertices with the raster's affine transform instead.
- trimesh `TextureVisuals(uv, image)` exports a material with `metallicFactor` 1 and
  `baseColorFactor` 0.4 grey, which renders near black. Pass a `PBRMaterial` with metallic 0,
  roughness 1 and a white base.
- trimesh embeds the texture as JPEG only when the PIL image's `format` is `JPEG`; a fresh array
  goes in as PNG (4 times larger at 200 m).
- trimesh takes OpenGL UVs (v up) and flips v on glTF export.

## Not checked

- Horizontal alignment of Esri imagery to the EA DTM. S6 found Esri about 2.4 m off EA imagery at a
  nearby crop; the drape looks right by eye, but the offset is not measured.
- Very large AOIs: texture size limits in viewers (4096 px here), and tiling the GLB.
