# TODO

## Next

- [ ] Speed up the build: fetch imagery for the next tile while the current one is being
      processed, simplest approach first; speed up the position correction step too, on CPU only:
      profile one cell, then average lidar points into grid cells instead of triangulating them,
      read each lidar file once, and match cells in parallel across cores
- [ ] Show progress for the build and the position correction: steps done out of total, elapsed
      time and time remaining, and which step is running (downloading lidar, reading points,
      matching a cell, updating tiles)
- [ ] Switch logging to loguru and save a run log in each store folder: settings used, timings,
      and what each step did (build, correct, exports); the correction step needs this most, it
      currently prints nothing until it finishes
- [ ] Change the area input to north-west corner and south-east corner as "lat, lon" pairs (as
      copied from a map), instead of west south east north; apply to build and the eval commands
- [ ] Research the best ways to recover fine height detail from coarse elevation data, then try
      the best candidates
- [ ] Research fixes for stretched texture on steep faces (walls, tree sides, roof peaks),
      including generative fill; filled pixels must be flagged

## Later

- [ ] Make the position correction work in towns and woodland, where it currently leaves the
      imagery as it was
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

## Needs you

- [ ] Supply photographs with known camera positions for the real-photo localisation test
      (required before the first release)

## Last

- [ ] Gazebo: a lighter collision mesh, then test in a running simulator

## Done

- Project scaffold, checks and workspace
- Esri imagery and elevation fetch with caching and throttling; imagery mosaic
- Terrain mesh builder with skirts and textured GLB output
- Tiled store with 3D Tiles, Gazebo and single-GLB export; buildings and trees included
- Evaluation tools: height error, smoothness, camera visibility, imagery offset, texture detail
- Imagery offset survey over eight England sites and a lidar-based correction trial
- Lidar surface refinement trials; the current mesh stays
- Imagery position correction (`satmesh correct`) with an error bound on every export; England only
