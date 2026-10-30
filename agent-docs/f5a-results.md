---
status: historical
topic: baseline-pipeline
summary: F5a results: EA first-return DSM visual mesh with DTM ground grid; 3.4x vertices, 11 MB for 18 nodes
answers: Does the EA DSM WCS work unauthenticated?; What does the DSM mesh cost in size?; Why sample the DSM at 0.5 m?; Does Gazebo collision hit tree canopies?
---

# F5a results: first-return DSM visual mesh, DTM ground grid

Built 2026-10-25 at Upper Aire, near Skipton. `[live]` marks what was observed against endpoints or
a renderer; the rest is covered by `make test`. Builds on `f5-results.md`.

## Conclusions

- The EA first-return DSM `GetCoverage` works unauthenticated and returns the same raster shape as
  the DTM `[live]`. Every node now meshes the DSM and stores its DTM as a ground grid.
- Trees, hedgerows, walls and roofs now exist as geometry: the wooded road verge and the plantation
  rise out of the ground in CesiumJS `[live]`. Facades and trunks are stretched roof-edge or
  canopy texels, never walls, as expected of a 2.5D surface.
- Cost at 0.1 m `max_error`, first build (1 m bilinear grid): a leaf averages 5,094 vertices against
  1,483 for the DTM (3.4 times), and the 18-node store is 7.4 MB against 2.8 MB. Bilinear
  sampling at 0.5 m, adopted after F6 found the 1 m grid smoothed crowns and roof edges, costs
  about 1.5 times more again: 11 MB for the same 18 nodes. A build of 18 nodes from the Esri
  cache plus 36 WCS requests took 13 s.
- The Gazebo exporter still points collision at the visual mesh, so a robot would now collide with
  tree canopies until F5b builds the collision mesh from the ground grid.

## Live DSM request `[live]`

```text
https://environment.data.gov.uk/spatialdata/lidar-composite-digital-surface-model-first-return-dsm-1m/wcs
  ?service=WCS&version=2.0.1&request=GetCoverage&format=image/tiff
  &coverageId=df4e3ec3-315e-48aa-aaaf-b5ae74d7b2bb__Lidar_Composite_Elevation_FZ_DSM_1m
  &subset=E(399748,400252)&subset=N(447248,447752)
```

- 504 x 504 float32, EPSG:27700, 1 m pixels, bounds equal the requested integers, nodata
  -3.4028235e38 with none in the box, 1.05 MB. `check_lidar` accepts it unchanged.
- No vertical datum is stated in the response, as for the DTM. ODN is assumed for both.
- DSM minus DTM over that box:

| Statistic | Value |
| --- | --- |
| Mean | 0.73 m |
| 1st, 50th, 99th percentile | -0.036, 0.010, 15.1 m |
| Maximum | 27.6 m |
| Minimum | -0.33 m |
| Pixels with DSM more than 1 cm below DTM | 5.0 % |

The DSM sits below the DTM at a twentieth of pixels, by up to 0.33 m: the composites are built from
different survey epochs. The mesh follows the DSM as given and is not clamped; the 0.33 m exceeds
the quoted 0.15 m RMSE, so F6 should measure it.

## Design as built

- `satmesh-data`: `ea_dtm.py` became `ea_lidar.py`. `EaLidarProduct` (WCS URL and coverage id) with
  `EA_DTM` and `EA_DSM`; `fetch_ea_lidar(http, box, cache_dir, product)`, `check_lidar`,
  `LidarCheckError`. The cache path already held the coverage id, so cached DTMs stay valid.
- `satmesh-tiles`: `build_node` takes `SurfacePaths(dsm, dtm)`. Both are sampled at the same grid
  nodes, every 0.5 m, bilinearly (finer than first built, which smoothed crowns and edges; nearest
  pixel was tried and rejected for terracing and blocky trees, see `f6-results.md`); the TIN, UVs,
  skirts, ECEF placement and origin height come from the DSM. The DTM grid is returned as
  `Node.ground_tif`, a float32 deflate GeoTIFF in EPSG:3857 with one pixel per grid node (pixel
  centres on the tile edges), ODN metres.
- Store layout adds `<store>/nodes/{z}/{x}/{y}.ground.tif` (`ground_path`). `NodeRecord` gains
  `dsm`, the DSM file name. The origin height is now the minimum DSM height of the node. Parents
  grid and mesh at 2 m per level as before, so their ground grids are coarser.
- Stores built before this change lack `dsm` in their records and do not load; build a new store.

## Checks

| Check | Result |
| --- | --- |
| Leaf mesh heights against a synthetic DSM plane 3 m above a DTM plane, through OSTN15 and OSGM15 | within `max_error` plus float32 resolution |
| Ground grid against the DTM plane at every node, positions via the GeoTIFF transform and PROJ | within 1 mm |
| Ground grid corner pixel centres on the tile's Web Mercator edges | within float precision |
| Store build: a ground grid beside every node, two WCS requests per node, rerun repeats none | pass |
| `make check`, `make test` (95 tests) | pass |
| Live build at Upper Aire, 500 m box, 18 nodes | pass; achieved TIN error 0.0999 m |
| CesiumJS 1.140.0 headless, low oblique and oblique views | tree belt and plantation stand up; no cracks or seams |

## Not checked

- DSM nodata over water or at survey edges: a gap raises `LidarCheckError` and stops the build. One
  coastal 200 m box off Spurn returned no gaps in either product, but it is unclear it was sea.
- A building: the Upper Aire box has farm roofs only; wall stretching on a larger building is
  unseen.
- Parents sample bilinearly at 1 m, 2 m, and so on up the tree, so coarse parents alias
  canopy. Area averaging is F5c.
- Whether first-return canopy height is a fair stand-in for what a camera sees through leaf-off
  trees; F6 camera visibility settles this.
