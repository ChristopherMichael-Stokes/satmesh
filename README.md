# satmesh

Textured 3D terrain meshes from Esri World Imagery tiles and DEMs, enhanced with classical processing
and ML. Research use.

- `pipeline/`: tile and DEM fetching, meshing, texture draping and export.

## Setup

Needs [uv](https://docs.astral.sh/uv/); `make` runs [prek](https://prek.j178.dev/) through `uvx`.

```sh
make setup
```

## Demo

<!-- Recorded demo: add docs/demo.mp4, then replace the line below with [Demo video](docs/demo.mp4). -->

Demo video: `docs/demo.mp4` (to be added)

## Use

Needs the UK PROJ grids (`make setup` fetches them) and, for Great Britain, nothing else: imagery is
Esri World Imagery and heights are the Environment Agency 1 m lidar: the first-return DSM for the
visual mesh and the DTM for the ground grid stored beside it.

The area is two corners, north-west and south-east, as `lat, lon` text copied from a map. Run
everything from `pipeline/`. Outputs go in `uncommitted/`, which git ignores.

```sh
cd pipeline

# 1. Build a tile store for a 500 m square (resumable; fetched data is cached)
uv run satmesh build --nw "53.925897, -2.005297" --se "53.921403, -1.997683" --store ../uncommitted/store

# 2. Move the imagery to its true position (England only; downloads lidar on first use)
uv run satmesh correct --store ../uncommitted/store

# 3. Export for a consumer
uv run satmesh export 3dtiles --store ../uncommitted/store
uv run satmesh export gazebo --store ../uncommitted/store --out ../uncommitted/gazebo
uv run satmesh export glb --store ../uncommitted/store --out ../uncommitted/area.glb
```

`3dtiles` writes `tileset.json` into the store; serve the store directory to open it in CesiumJS.
`gazebo` writes `world.sdf` and its meshes. `glb` writes every finest-level tile as one GLB in a
single local frame, for renderers.

`build` and `correct` show a progress bar per step (done of total, elapsed, time remaining), and
every command that takes `--store` appends to `run.log` in the store: the command line, versions,
settings, timings, and for `correct` the shift and error bound of each cell and the lean of each
satellite capture.

`correct` moves the Esri imagery to its true position. Esri imagery sits 0.2 to 2.8 m from the
ground in England, by a different amount in different places, and roofs and tree crowns lean
further, by an amount that grows with their height, because each satellite capture was taken at an
angle. `correct` measures the ground shift against the Environment Agency lidar intensity over cells
of about 1 km. It also fits each capture's ground shift and lean from roofs matched against the
lidar surface across the whole store, and where that fit is good enough (at least 10 matched roofs
and a well-measured lean) moves every point by its own height. Elsewhere the cell's ground shift
applies where the match is reliable, and the rest is left as it was; the command prints which
captures got the lean and why the others did not. `--no-lean` skips the lean. It downloads lidar
point clouds (about 100 to 500 MB per 5 km square, cached) and the lidar surface per cell. It
measures up to 8 cells at once, about 2 GB of memory each. Every export writes
`positional_error.json` with a 95 % error bound per tile: a bound on open ground (0.4 to 1.5 m
where corrected, 2.8 m where not) plus a bound per metre of height for raised objects (at most
0.29 m per m where the lean applies, 0.58 m per m elsewhere), and "unmeasured" if `correct` was
never run. Where the shift pulls a tile's imagery past its edge, the edge pixels are stretched over
the gap. A store corrected by an older version must be rebuilt and corrected again. England only.

`build` caches fetched tiles under `~/.cache/satmesh` (`--cache-dir` or
`SATMESH_CACHE_DIR` to change it). Esri tiles are fetched at one request per second by default, so
large areas take hours; `--esri-requests-per-second 10` on `build` and `correct` raises the rate.
Esri publishes no limit.

## Checks

```sh
make check
```
