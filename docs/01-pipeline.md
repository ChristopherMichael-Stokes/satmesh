# Pipeline details

Reference for `satmesh build` and `satmesh correct`. The README holds the short version.

## Progress and run log

`build` and `correct` show a progress bar per step (done of total, elapsed, time remaining), and
every command that takes `--store` appends to `run.log` in the store: the command line, versions,
settings, timings, and for `correct` the shift and error bound of each cell and the lean of each
satellite capture.

## Elevation sources

`build` asks a registry for the heights of the area: the first entry in `registry.toml` whose
longitude and latitude boxes contain the area's centre wins, and an area that is only partly
inside it is an error. An entry names its access method, CRS, vertical datum, licence and
attribution; a new source is a TOML block, plus an adapter function when it needs a new access
method. Heights stay in the source's vertical datum, each node records both that height and the
ellipsoidal one (the geoid separation is the difference), and the CRS of the heights is stored with
the node. A source that only has a surface model (GLO-30 outside the Middle East) serves as its own
ground, and the node record says so. In the contiguous United States the ground is the 3DEP 1 m
DEM (with fallbacks recorded per window in `elevation_provenance`) and the surface is the highest
first return per 1 m cell from the newest lidar project covering the window; cells with no return
show the ground. The geoid grids a source needs must be installed before any
fetch (`make setup` for all, `make grids REGIONS="gb global us"` for a subset); a missing grid
stops the build.

## Position correction

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
0.29 m per m where the lean applies, 0.58 m per m elsewhere). A store `correct` never ran on,
including every store outside England, carries Esri's stated accuracy for its imagery source (4 to
12 m) as the bound on open ground and 0.58 m per m for raised objects. Where the shift pulls a
tile's imagery past its edge, the edge pixels are stretched over the gap. A store corrected by an
older version must be rebuilt and corrected again. England only.

## Caching and request rate

`build` caches fetched tiles under `~/.cache/satmesh` (`--cache-dir` or
`SATMESH_CACHE_DIR` to change it). Esri tiles are fetched at 20 requests per second by default;
`--esri-requests-per-second` on `build` and `correct` changes the rate. Esri publishes no limit.
