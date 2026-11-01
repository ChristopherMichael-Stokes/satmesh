# Poses and lens from photos

`satmesh-track` (in the `locate/` workspace) takes photos in the order they were taken and a tile
store of the area, and writes where each photo was taken from and what lens took them. No logged
poses and no calibration are needed.

```text
uv run --extra gpu --extra tensorrt satmesh-track PHOTOS --store STORE --out OUT \
  [--start "LAT, LON" --radius-m 150] [--reference LOG.csv]
```

- Photos are read in file-name order (`2.jpg` before `10.jpg`) and are reduced to 1280 px on the
  long side for the work. Cameras should be at least 25 m above the ground.
- `--start` is a rough position of the first photo (within about a hundred metres). Without it the
  whole store is searched with the MegaLoc model (`--megaloc-model` or `MEGALOC_MODEL`), which
  describes a few thousand renders once per store and keeps them in the cache directory. Matching
  uses the XFeat models in `XFEAT_MODEL_DIR` (or `--matcher sift`). `--backend tensorrt` (the
  default) runs them on an NVIDIA GPU from the `_fp16` exports and builds its engines on first use;
  `--backend onnx` runs on the CPU, about 3.5 times slower on the 24-photo test flight.
- A photo that the previous position does not explain starts a search around the last position, so
  a gap of missing photos does not end the track.

## What it writes

| File | Holds |
| --- | --- |
| `poses.jsonl` | One line per located photo: latitude, longitude, ellipsoidal height, heading, pitch, roll and the estimated lens. Same format as the pose file of `satmesh eval localise`, so a track can be scored against logged poses |
| `calibration.json` | Focal length (pixels, original photo size) with its standard deviation, radial terms k1 and k2, field of view, covariance, warnings |
| `report.json` | Per photo: tracked, found again after a search, dropped as a wrong frame, or lost; inliers and residual |
| `review.html` | Plan view of the path, lens table, photo strip with a full-width viewer, photo table; with `--reference`, the logged path and per-photo residuals |

## Limits

- The lens model is a pinhole with radial terms k1 and k2 and the principal point at the centre.
  A fisheye lens (field of view beyond about 110 degrees) does not fit; the calibration file warns.
- Straight-down photos over flat ground cannot fix the focal length; the standard deviation in
  `calibration.json` says so (above about 1 % the lens is not well determined).
- Tested on synthetic photos rendered from a store; real photos are not yet measured. The mesh's
  own error (`--mesh-error-m`, default 1 m) is assumed, not measured.
