# TODO

## Scaffold

- [x] Root config copied from xfeat-rt (prek, ruff, rumdl, typos, bake, checkmake, Makefile,
      LICENSE)
- [x] `AGENTS.md`, `CLAUDE.md`, `README.md`
- [x] `pipeline/` uv workspace with `satmesh-core` stub and a passing test
- [x] `make setup`, `make check`, `make test` pass

## Spikes

- [ ] S1 Esri native-resolution probe: layer 4 `identify` gives `SRC_RES`/`MaxMapLevel`;
      placeholder-tile hash detects the end of native data
- [ ] S2 Wayback scan: do older releases hold finer `SRC_RES` at a point? Measure over ~20 sites
- [ ] S3 DEM source coverage at the test sites: 3DEP 1 m, 3DEP 10 m, GLO-30
- [ ] S4 Ground-truth test sites: US sites with NAIP and 3DEP 1 m lidar, mixed terrain and land
      cover
- [ ] S5 Mesh baseline: DEM plus Esri drape to GLB with pydelatin; check vertical scale in a metric
      CRS

## Features

- [ ] F1 `satmesh-core`: AOI, CRS and tile math (mercantile, pyproj), GSD and zoom selection
- [ ] F2 `satmesh-data`: throttled, cached Esri tile fetch; DEM fetch per source; source-selection
      policy
- [ ] F3 Tile mosaic and cropping to the AOI
- [ ] F4 `satmesh-mesh`: reproject to local metric CRS, adaptive triangulation, UV drape, GLB export
- [ ] F5 `satmesh-cli`
- [ ] F6 Evaluation harness: DEM error against lidar, texture against NAIP, consistency check

## Experiments

- [ ] E1 DEM classical chain: feature-preserving smoothing, void fill, bicubic; error against lidar
- [ ] E2 Texture harmonisation across zoom and source boundaries
- [ ] E3 SwinIR/HAT x2 on tiles past native depth, gated by the consistency check
- [ ] E4 PixTransform image-guided DEM refinement, capped factor, scored against lidar
- [ ] E5 Real-ESRGAN fine-tuned on in-domain pairs (only if E3 shows a gap)
- [ ] E6 Wayback multi-date fusion (only if S2 finds distinct captures)
- [ ] E7 Monocular height as a high-frequency detail layer

## Open

- [ ] Create `ml/` workspace when the first model's dependencies conflict with `pipeline/`
