# satmesh

Textured 3D terrain meshes from Esri World Imagery tiles and DEMs, enhanced with classical processing
and ML. Research use.

- `pipeline/`: tile and DEM fetching, meshing, texture draping and export.

## Setup

Needs [uv](https://docs.astral.sh/uv/) and [prek](https://prek.j178.dev/).

```sh
uv tool install prek@0.5.7
make setup
```

## Use

Needs the UK PROJ grids (`make setup` fetches them) and, for Great Britain, nothing else: imagery is
Esri World Imagery and heights are the Environment Agency 1 m lidar: the first-return DSM for the
visual mesh and the DTM for the ground grid stored beside it.

```sh
cd pipeline
uv run satmesh build --bbox 399750 447250 400250 447750 --crs EPSG:27700 --store ../out/store
uv run satmesh correct --store ../out/store
uv run satmesh export 3dtiles --store ../out/store
uv run satmesh export gazebo --store ../out/store --out ../out/gazebo
uv run satmesh export glb --store ../out/store --out ../out/area.glb
```

`correct` moves the Esri imagery to its true position. Esri imagery sits 0.2 to 2.8 m from the
ground in England, by a different amount in different places. `correct` measures the shift against
the Environment Agency lidar intensity over cells of about 1 km, applies it where the match is
reliable, and leaves the rest as it was. It downloads lidar point clouds (about 100 to 500 MB per
5 km square, cached). Every export writes `positional_error.json` with a 95 % error bound per tile:
0.4 to 1.5 m where corrected, 2.8 m where not, and "unmeasured" if `correct` was never run. Raised
objects such as roofs and tree crowns are not corrected. England only.

`build` is resumable and caches fetched tiles under `~/.cache/satmesh` (`--cache-dir` or
`SATMESH_CACHE_DIR` to change it). Esri tiles are fetched at one request per second, so large areas
take hours.

## Checks

```sh
make check
```
