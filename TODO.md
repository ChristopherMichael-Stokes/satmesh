# TODO

## Scaffold

- [x] Root config copied from xfeat-rt (prek, ruff, rumdl, typos, bake, checkmake, Makefile,
      LICENSE)
- [x] `AGENTS.md`, `CLAUDE.md`, `README.md`
- [x] `pipeline/` uv workspace with `satmesh-core` stub and a passing test
- [x] `make setup`, `make check`, `make test` pass

## Spikes

- [x] S1 Esri native-resolution probe: layer 4 `identify` gives `SRC_RES`/`MaxMapLevel`;
      placeholder-tile hash detects the end of native data
- [ ] S2 Wayback scan: do older releases hold finer `SRC_RES` at a point? Measure over ~20 sites
- [ ] S2b Count distinct capture dates per site across Wayback releases (feeds E6)
- [ ] S3 DEM source coverage at the test sites: 3DEP 1 m, 3DEP 10 m, GLO-30
- [ ] S4 Ground-truth test sites: US sites with NAIP and 3DEP 1 m lidar, mixed terrain and land
      cover
- [x] S6 UK imagery: EA covers about 7,000 km2 of England from 2020 on, at 10 to 25 cm; real detail
      gain over Esri z19 where present; ECW needs a custom GDAL build
- [ ] S7 Scottish lidar tile download mechanism (portal API)
- [x] S5 Mesh baseline: EA 1 m DTM (WCS) plus Esri z19 drape to GLB with pydelatin works; vertical
      scale is exact in BNG, whose XY is 0.04% short; 61k vertices for 1 km2 at 0.1 m error

## Features

- [ ] F1 `satmesh-core`: AOI, CRS and tile math (mercantile, pyproj), GSD and zoom selection
- [ ] F2 `satmesh-data`: throttled, cached Esri tile fetch; DEM fetch per source; source-selection
      policy
- [ ] F2a Source registry (pydantic data file) with region preference lists; UK entries first
- [ ] F2b Access adapters: ArcGIS tile cache, WCS, COG range read, index-then-download (ECW via
      GDAL with libecwj2 3.3, in Docker)
- [ ] F3 Tile mosaic and cropping to the AOI
- [ ] F4 `satmesh-mesh`: reproject to local metric CRS, adaptive triangulation, UV drape, GLB export
- [ ] F5 `satmesh-cli`
- [ ] F6 Evaluation harness: DEM error against lidar, texture against NAIP, consistency check

## Experiments

- [ ] E1 DEM classical chain: feature-preserving smoothing, void fill, bicubic; error against lidar
- [ ] E2 Texture harmonisation across zoom and source boundaries
- [ ] E3 SwinIR/HAT x2 on tiles past native depth, gated by the consistency check
- [ ] E4 (A) Continuous high-resolution height from low-resolution DEMs: PixTransform per tile,
      DADA retrained on lidar and imagery pairs; edge-leakage check; scored against lidar
- [ ] E5 Real-ESRGAN fine-tuned on in-domain pairs (only if E3 shows a gap)
- [ ] E6 (B) Multi-capture super-resolution: registration accuracy first, then classical
      register-and-merge baseline, then HighRes-net / Deep Burst SR; Wayback and other-source captures
- [ ] E7 Monocular height as a high-frequency detail layer for E4

## Open

- [ ] Create `ml/` workspace when the first model's dependencies conflict with `pipeline/`
