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
      (on demand, before E6)
- [ ] S2b Count distinct capture dates per site across Wayback releases (on demand, feeds E6)
- [ ] S3 DEM source coverage at the UK test sites: EA 1 m DTM and DSM, OS Terrain 50, GLO-30
- [ ] S4 Ground-truth test sites: England sites with EA 1 m lidar and EA 10 cm aerial imagery,
      mixed terrain and land cover (Upper Aire first)
- [x] S6 UK imagery: EA covers about 7,000 km2 of England from 2020 on, at 10 to 25 cm; real detail
      gain over Esri z19 where present; ECW needs a custom GDAL build
- [ ] S7 Scottish lidar tile download mechanism (portal API; on demand, for Scottish sites)
- [x] S5 Mesh baseline: EA 1 m DTM (WCS) plus Esri z19 drape to GLB with pydelatin works; vertical
      scale is exact in BNG, whose XY is 0.04% short; 61k vertices for 1 km2 at 0.1 m error

## Features

- [x] F1 `satmesh-core`: AOI, metric CRS (BNG in Great Britain, else UTM), covering tiles, GSD;
      zoom selection from Esri metadata moved to F2
- [x] F2 `satmesh-data`: Esri layer 4 metadata and zoom choice, throttled and cached tile fetch with
      placeholder detection, EA 1 m DTM by WCS; source selection moved to F2a
- [ ] F2a Source registry (pydantic data file) with region preference lists and the selection policy
      that walks them; UK entries first
- [ ] F2b Access adapters: ArcGIS tile cache, WCS, COG range read, index-then-download (ECW via
      GDAL with libecwj2 3.3, in Docker)
- [x] F3 Tile mosaic (EPSG:3857, JPEG decoded by GDAL) and whole-pixel crop to the AOI plus margin;
      a placeholder inside the AOI raises
- [x] F4 `satmesh-mesh`: texture reprojected to the DTM's CRS (8,192 px cap), pydelatin TIN,
      affine UV drape, GLB with georeference in scene `extras`; XY in CRS metres, point scale recorded
- [ ] F5 `satmesh-cli`
- [ ] F6 Evaluation harness: DEM error against EA lidar, texture against EA 10 cm aerial,
      consistency check

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
