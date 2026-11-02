# Poses and lens from photos

`satmesh-track` (in the `locate/` workspace) takes photos in the order they were taken and a tile
store of the area, and writes where each photo was taken from and what lens took them. No logged
poses and no calibration are needed.

```text
uv run --extra gpu --extra tensorrt satmesh-track PHOTOS --store STORE --out OUT \
  [--start "LAT, LON" --radius-m 150] [--heading 30+-45] [--pitch -35+-15] [--height 70+-30] \
  [--priors priors.toml] [--reference LOG.csv]
```

- Photos are read in file-name order (`2.jpg` before `10.jpg`) and are reduced to 1280 px on the
  long side for the work. Cameras should be at least 25 m above the ground.
- The first photo is found in two levels. Views rendered from the store every 280 m, every 30
  degrees of heading, at 90 and 110 m above the ground and two pitches are described with the
  MegaLoc model (`--megaloc-model` or `MEGALOC_MODEL`) and compared with the first photo and four
  more photos 4 apart, each turned by its heading change from the first (measured from feature
  matches between the photos). Around the five best places, views every 70 m at five heights
  are compared with the first photo. The six best places are then matched in detail, and each
  that localises the first photo follows the first 12 photos; the place with the most photos
  followed wins. Renders are described as they are made; nothing is written to disk.
- The MegaLoc model is either the ONNX graph or an FP16 TensorRT engine, which describes views
  about five times faster on the GPU. Build the engine once per MegaLoc export, TensorRT version
  and GPU with `satmesh-locate-export MODEL.onnx OUT_DIR` (from `locate/`, with the `tensorrt`
  extra; about a minute) and point `MEGALOC_MODEL` at the `.engine` file it prints. The engine
  needs an NVIDIA GPU; the `cpu` variant uses the ONNX graph.
- Priors narrow the search: `--start` and `--radius-m` a circle for the position, `--heading`,
  `--pitch` and `--height` a centre and a half-width (`CENTRE+-HALF`, degrees or metres above the
  ground). Give each window about twice the expected error: a heading hint 30 degrees off, with
  the truth at the window's edge, loses most places. When no place verifies, the heading window
  is dropped, then the pitch window, then the position circle, and the search runs again.
- `--priors FILE.toml` holds the same priors and the search settings; the options override it.
  Keys are the setting names, priors in tables, positions in the store's east and north metres:

  ```toml
  fusion_frames = 5
  [priors.heading_deg]
  centre = 30.0
  half_width = 45.0
  [priors.height_m]
  centre = 70.0
  half_width = 30.0
  ```

- Matching uses the XFeat models in `XFEAT_MODEL_DIR` (or `--matcher sift`). `--backend tensorrt`
  (the default) runs them on an NVIDIA GPU from the `_fp16` exports and builds its engines on
  first use; `--backend onnx` runs on the CPU, about 3.5 times slower on the 24-photo test flight.
- A photo that the previous position does not explain starts a search around the last position, so
  a gap of missing photos does not end the track.

## What it writes

| File | Holds |
| --- | --- |
| `poses.jsonl` | One line per located photo: latitude, longitude, ellipsoidal height, heading, pitch, roll and the estimated lens. Same format as the pose file of `satmesh eval localise`, so a track can be scored against logged poses |
| `calibration.json` | Focal length (pixels, original photo size) with its standard deviation, radial terms k1 and k2, field of view, covariance, warnings |
| `report.json` | Per photo: tracked, found again after a search, dropped as a wrong frame, or lost; inliers and residual |
| `review.html` | Plan view of the path, lens table, photo strip with a full-width viewer, photo table; with `--reference`, the logged path and per-photo residuals |
| `events.jsonl` | The first fix as it ran, one event a line: the area and priors, stages with times, searched positions with their scores, ranked places, each place's check, priors dropped, the fix |

## Limits

- The lens model is a pinhole with radial terms k1 and k2 and the principal point at the centre.
  A fisheye lens (field of view beyond about 110 degrees) does not fit; the calibration file warns.
- Straight-down photos over flat ground cannot fix the focal length; the standard deviation in
  `calibration.json` says so (above about 1 % the lens is not well determined).
- Tested on synthetic photos rendered from a store; real photos are not yet measured. The mesh's
  own error (`--mesh-error-m`, default 1 m) is assumed, not measured.
