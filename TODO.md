# TODO

## Next

- [ ] Make the position correction work in towns and woodland, where it currently leaves the
      imagery as it was (plan written, awaiting approval)
- [ ] Try the best candidate for recovering fine height detail from coarse elevation data (Yemen
      has no lidar, so this is where it matters); score it first on degraded England lidar
- [ ] Test a completely different region, Yemen: find open elevation data and imagery coverage
      there (surveyed: GLO-30 is open and 0.31 to 0.46 m imagery exists, but no open reference
      height data), make the build work outside Great Britain (UTM, geoid, coarse
      elevation), and choose a test area

## Later

- [ ] Combine several captures of the same place into one sharper image
- [ ] Source registry: which imagery and elevation data to use per region, with fallbacks
- [ ] Terrain for areas larger than about 6 km, averaged rather than point-sampled for coarse tiles
- [ ] Smoother, hole-free elevation data by classical processing, scored against lidar
- [ ] Sharpen imagery past its native zoom, only where the automatic check says it helps
- [ ] Fine-tune a super-resolution model on our own imagery pairs, only if the step above falls short
- [ ] Use single-image height estimates as a fine detail layer
- [ ] Find lidar point data for Wales (the position correction needs it; it is England only for now)
- [ ] Find the Scottish lidar download route
- [ ] Check whether older Esri releases hold finer imagery at a point, and how many capture dates a
      site has
- [ ] Check elevation coverage at the UK test sites
- [ ] Choose more England test sites with lidar and 10 cm aerial imagery
- [ ] Split out a separate environment for ML tools if their dependencies clash with the pipeline

## Last

- [ ] Gazebo: a lighter collision mesh, then test in a running simulator

## Needs you

- [ ] Supply photographs with known camera positions for the real-photo localisation test
      (required before the first release)

## Done

- Project scaffold, checks and workspace
- Esri imagery and elevation fetch with caching and throttling; imagery mosaic
- Terrain mesh builder with skirts and textured GLB output
- Tiled store with 3D Tiles, Gazebo and single-GLB export; buildings and trees included
- Evaluation tools: height error, smoothness, camera visibility, imagery offset, texture detail
- Imagery offset survey over eight England sites and a lidar-based correction trial
- Lidar surface refinement trials; the current mesh stays
- Imagery position correction (`satmesh correct`) with an error bound on every export; England only
- Faster build (imagery fetched ahead of the node being built) and faster position correction
  (cells measured in parallel, one read of each lidar file); the results are byte-identical
- Progress bars for the build and the position correction, loguru logging with a run log in each
  store folder, and the area given as north-west and south-east "lat, lon" corners
