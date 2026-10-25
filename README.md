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
Esri World Imagery and heights are the Environment Agency 1 m lidar DTM.

```sh
cd pipeline
uv run satmesh build --bbox 399750 447250 400250 447750 --crs EPSG:27700 --store ../out/store
uv run satmesh export 3dtiles --store ../out/store
uv run satmesh export gazebo --store ../out/store --out ../out/gazebo
uv run satmesh export glb --store ../out/store --out ../out/area.glb
```

`build` is resumable and caches fetched tiles under `~/.cache/satmesh` (`--cache-dir` or
`SATMESH_CACHE_DIR` to change it). Esri tiles are fetched at one request per second, so large areas
take hours.

## Checks

```sh
make check
```
