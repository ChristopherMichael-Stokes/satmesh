# TODO

## Next

- [ ] Recover photo poses and camera calibration from the photos alone (`satmesh-track`, built):
      the first fix is found with no position given, in about 6 to 24 minutes on a 3 km area, on
      Bexhill, Old Sarum and Kenilworth; it finds nothing on Penshaw (a sunset clip looking out
      to the horizon). The quick-search settings tuned on Bexhill failed on Kenilworth and stay off
- [ ] Housekeeping on that work, tonight where the machine is free: run the CPU-variant tests
      once, a make target for the demo runs, the first-photo-against-render image written by the
      tool itself, and the tracker tests rerun after the render range change (500 to 1000 m)
- [ ] Speed up the first fix and the tracker: the 3 to 4 seconds a photo spent tracking each
      candidate place, the 30 seconds a photo after the fix on Kenilworth (hundreds of renders per
      lost photo), the coarse search over the whole area, and the renders repeated in the
      screening; quick-search shortcuts only if they hold on every clip, then on your own clips
- [ ] Make the first fix work on Penshaw: the candidates are all at the monument but searched at a
      steep pitch while the photo looks across the horizon, so search shallower pitches and estimate
      the pitch and roll from the photos (a pretrained model, GeoCalib); show the tracking
      updates on the monitor page after the first fix
- [ ] Check the first fix on footage without a surface model: verify by the satellite imagery
      warped to the candidate view, then the sealed Hergest Court clip (one run, no tuning), then
      larger areas (5 km, then 10 km square; the downloads need your go)
- [ ] Add building and tree height to the build from pretrained models (Geopose and RS3DAda for
      buildings, CHMv2 for trees) laid onto the coarse elevation, with a land-cover segmentation
      that keeps ground flat and cleans up roofs, walls and tree crowns; judge it by eye on fixed
      views, score it on degraded England lidar
- [ ] Try a successor to PixTransform that corrects those model heights area by area, with the
      segmentation and image features as extra input (a written proposal comes first)
- [ ] Re-check earlier rejections whose reference was biased by roof lean: measure the imagery
      position truth on open ground only, then re-score the lean fits, the rejected
      re-registration step, the correction rule and the Southend overshoot
- [ ] Imagery choice per build: pick the source and the capture date or season (Esri releases
      and NAIP years), with Esri as the default; first check how many dated releases Esri holds
      at a site and what NAIP years exist, and look at the seasonal differences side by side

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
- [ ] Texture refinement with sharper source imagery (NAIP, county flights, dated Esri releases); a
      super-resolution pass on the 0.3 to 0.5 m Esri imagery gave little visible gain

## Last

- [ ] Gazebo: a lighter collision mesh, then test in a running simulator

## Needs you

- [ ] Go-ahead for the 5 km store download and the sealed Hergest Court run, when the first fix
      is ready for them

## Done

- Acceptance harness proven on real footage: the Bexhill clip against its GPS log (98 of 110 frames
  at 3.5 m median), and the first fixes on Old Sarum and Kenilworth checked by eye
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
- The build works outside Great Britain through a source registry: Yemen (Copernicus GLO-30 and
  FABDEM) and the contiguous United States (USGS 3DEP lidar); imagery is capped at 30 cm
- Progress bars for the build and the position correction, loguru logging with a run log in each
  store folder, and the area given as north-west and south-east "lat, lon" corners
