# Implementation plan: satmesh

Goal: a research tool that builds textured 3D terrain meshes from Esri World Imagery tiles and DEMs,
with
the highest ground sample distance (GSD) the sources support, enhanced by classical processing and
ML.
Research-only use; Esri terms accepted by the owner.

## Findings that shape the plan

| Finding | Consequence |
|---|---|
| Esri native resolution varies by location; layer 4 reports `SRC_RES`, `SRC_DATE`, `MinMapLevel`, `MaxMapLevel` | Pick zoom per location from metadata, never a fixed zoom |
| Past the cached depth the server returns HTTP 200 with a 2521-byte "Map data not yet available" tile (md5 prefix `f27d9de7`) | Detect by hash; stop requesting beyond it |
| Live max cached zoom: Denver z20, London z19, North Dakota z19, Sahara z17 | Test sites decide how fine imagery can go |
| Some "30 cm" Vantor products are vendor-upsampled ("HD") | A second SR pass stacks guesses; no SR on native tiles |
| Wayback has per-release metadata; release date is not capture date | Dedupe by capture date before judging whether finer scenes exist |
| 3DEP 1 m is bare earth with partial US coverage; GLO-30 (30 m) is a DSM; FABDEM is bare earth but CC BY-NC-SA | Record DSM or DTM per source; mixing leaves seams |
| EPSG:3857 metres are 1/cos(lat) too long | Reproject to a local metric CRS before meshing |
| GAN and diffusion SR hallucinate structure that will not match the geometry | Classical SR only (SwinIR, HAT), gated by a consistency check |
| Guided DEM super-resolution copies image edges into height | Cap the factor; score against lidar |

The ML effort goes mostly to the DEM, where the source is coarse, and not to the texture, where the
best Esri
tiles are already near the limit.

## Source registry

Esri is the fallback. A registry maps each region to an ordered list of imagery sources and an ordered
list of DEM sources; lookup walks the list and takes the first source that covers the AOI. The
registry is a validated data file (pydantic models), not code. Each entry records:

- kind (imagery or DEM), surface (DTM or DSM), native resolution, CRS and vertical datum
- access type: ArcGIS tile cache, WCS, COG range read, tile download, or index-then-download
- region polygon, capture years where known, licence and attribution

Each access type needs its own adapter in `satmesh-data`. UK entries and their evidence are in
`uk-sources.md`; other regions are added after their own survey. Source choice is per AOI, so a
mesh can combine a lidar DEM with Esri imagery.

## Stack

| Step | Library |
|---|---|
| Raster I/O, reprojection | rasterio, pyproj |
| Tile math | mercantile |
| Triangulation | pydelatin (Garland and Heckbert greedy insertion); pymartini as the regular-grid alternative |
| Mesh and glTF output | trimesh, pygltflib |
| Tiled terrain output (later) | quantized-mesh-encoder |
| Feature-preserving DEM smoothing | WhiteboxTools |
| Void fill | GDAL FillNodata |
| Seam blending, histogram matching | OpenCV, scikit-image |
| Consistency and hallucination metrics | opensr-test |
| Package and environment management | uv, as in xfeat-rt |

UVs for the drape are an affine function of projected XY, so no atlas unwrapping is needed.

## Layout

- `pipeline/`: uv workspace without PyTorch. Packages: `satmesh-core`, `satmesh-data`, `satmesh-
  mesh`,
  `satmesh-cli`.
- `ml/`: second uv workspace with PyTorch, created when a model's dependencies conflict with
  `pipeline/`.
  Models cross over as exported files (ONNX) with a contract test.
- Tile cache, DEM cache, models, and meshes are build outputs and are gitignored.

## Stages

### 0. Scaffold

Copy xfeat-rt tooling per `TODO.md`. Exit: `make setup`, `make check`, `make test` pass on a stub
package.

### 1. Source spikes (S1 to S7)

- S1 settles how finely each location can be imaged: confirm layer 4 `SRC_RES` against the
  placeholder-hash
  depth at the test sites.
- S2 settles whether Wayback adds finer imagery: for each release that changed at a point, read
  `SRC_RES`
  and keep the finest. Success: at least one site where an older release is measurably finer.
- S3 and S4 pick test sites that have NAIP and 3DEP 1 m lidar, so enhancements have ground truth.

Exit: a site table (location, best `SRC_RES`, max usable zoom, DEM sources available) in `agent-
docs/`.

### 2. Baseline pipeline (S5, F1 to F5)

Fetch, mosaic, crop, reproject, triangulate, drape, export GLB, from the CLI. No enhancement. Exit:
a
metrically correct mesh for each test site, viewable in a glTF viewer.

### 3. Evaluation harness (F6)

Built before any enhancement so each experiment has a score.

- DEM: RMSE and NMAD against 3DEP lidar, split by slope and land cover.
- Texture: comparison against co-registered NAIP.
- Super-resolution: downsample the output to the input grid and diff against the input
  (consistency), plus
  the opensr-test synthesis and hallucination split.

### 4. Classical enhancement (E1, E2)

Terrain: feature-preserving smoothing, then void fill, then bicubic up to mesh resolution. Texture:
histogram matching and multiband blending at source and zoom boundaries. Exit: each step improves or
holds the F6 scores.

### 5. ML experiments

The two owner-set directions come first; the rest follow by expected value.

1. **A. Continuous depth for low-resolution DEMs (E4).** Turn a coarse DEM (GLO-30 at 30 m, OS Terrain
   50 at 50 m, or 2 m lidar) into a continuous, higher-resolution height field. Candidates:
   PixTransform per tile (fitted without training data, constrained to agree with the coarse DEM),
   DADA retrained on lidar and imagery pairs, and monocular height as a detail layer (E7). Scored
   against 1 m lidar at UK sites, split by slope and land cover. Guided methods copy image edges
   (road paint, shadows) into height, so the score includes an edge-leakage check.
2. **B. Super-resolution over multiple captures (E6).** Fuse several captures of the same location
   into one higher-resolution texture. Inputs: Esri Wayback releases deduplicated by capture date,
   plus any other-source captures (EA aerial years, other APGB-free imagery). Candidates: HighRes-net
   and Deep Burst SR, with a classical register-and-merge baseline. S2 measures how many distinct
   captures exist per site; E6 runs regardless, and a site with a single capture is a negative
   result to record. Real multi-frame gain needs sub-pixel shifts between captures, so registration
   accuracy is measured first.
3. E3 SwinIR or HAT x2 with the non-GAN weights, applied only where the source resolution is coarser
   than the tile GSD.
4. E5 Real-ESRGAN fine-tuned on in-domain pairs, only if E3 shows a gap.

Each experiment records its dataset, scores, and a keep or drop decision in `agent-docs/`.

## Risks

- Hallucinated texture or terrain detail that scores well on perceptual metrics but conflicts with
  geometry.
  Mitigation: consistency gating and lidar scoring.
- Mixing DSM and DTM sources across a seam. Mitigation: store the surface type per source.
- Esri rate limits are undocumented. Mitigation: cache by (z, y, x), throttle to a few requests per
  second
  with backoff, set a descriptive User-Agent, never request past `MaxMapLevel`.

## Unverified

- Whether Esri tiles below native resolution are resampled, and whether older Wayback releases are
  finer
  in practice (spikes S1, S2).
- ONNX export and runtime of SwinIR and HAT.
- Copernicus DEM licence terms, OpenAerialMap licence, IGN BD ORTHO details.
- Several citations given from memory (Real-ESRGAN, SwinIR, classical papers) need checking before
  they
  appear in any write-up.
