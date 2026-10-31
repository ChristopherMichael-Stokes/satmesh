# TODO

## Next

- [ ] Add building and tree height to the build from pretrained models (Geopose and RS3DAda for
      buildings, CHMv2 for trees) laid onto the coarse elevation, with a land-cover segmentation
      that keeps ground flat and cleans up roofs, walls and tree crowns; judge it by eye on fixed
      views, score it on degraded England lidar
- [ ] Try a successor to PixTransform that corrects those model heights area by area, with the
      segmentation and image features as extra input (a written proposal comes first)
- [ ] Re-check earlier rejections whose reference was biased by roof lean: measure the imagery
      position truth on open ground only, then re-score the lean fits, the rejected
      re-registration step, the correction rule and the Southend overshoot
- [ ] Test a completely different region, Yemen: find open elevation data and imagery coverage
      there (surveyed: GLO-30 is open and 0.31 to 0.46 m imagery exists, but no open reference
      height data), make the build work outside Great Britain (UTM, geoid, coarse
      elevation), and choose a test area
- [ ] Imagery choice per build: pick the source and the capture date or season (Esri releases
      and NAIP years), with Esri as the default; first check how many dated releases Esri holds
      at a site and what NAIP years exist, and look at the seasonal differences side by side
- [ ] Texture processing and refinement on the orthophotos: sharpen past native zoom only where
      the automatic check says it helps, combine several captures of a place into one sharper
      image, even out colour and shadow between captures and across tile seams, and fine-tune a
      super-resolution model on our own imagery pairs if classical sharpening falls short; judge
      by eye on fixed views against the 10 cm England aerial imagery

## Later

- [ ] Find why the lean correction overshoots north at Southend (ground shift 0.7 m off the aerial
      reference)
- [ ] Source registry: which imagery and elevation data to use per region, with fallbacks
- [ ] Terrain for areas larger than about 6 km, averaged rather than point-sampled for coarse tiles
- [ ] Smoother, hole-free elevation data by classical processing, scored against lidar
- [ ] Use single-image height estimates as a fine detail layer
- [ ] Find lidar point data for Wales (the position correction needs it; it is England only for now)
- [ ] Find the Scottish lidar download route
- [ ] Check elevation coverage at the UK test sites
- [ ] Choose more England test sites with lidar and 10 cm aerial imagery

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
- Roof and tree lean correction per satellite capture, in `satmesh correct`: towns and woodland
  are now corrected where enough roofs match the lidar
- ML workspace with PixTransform, kriging and a file contract with the pipeline
- Pretrained height models compared on two England boxes; the mean of Geopose and RS3DAda on a
  kriged coarse base is the chosen start, CHMv2 for trees
- Progress bars for the build and the position correction, loguru logging with a run log in each
  store folder, and the area given as north-west and south-east "lat, lon" corners
