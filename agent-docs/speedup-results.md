# Speed-up of `build` and `correct` (2026-10-26)

Owner requirement: output parity, lower latency, higher throughput. Every change below was checked
by running the old code (clean worktree of `4c255bb`) and the new code on copies of one store and
comparing the stores with `diff -r`: identical bytes in every run.

## Conclusions

- `correct`, 12 cells (3 x 2 km at Upper Aire, Esri z18, 87 nodes): 424 s to 75.5 s (5.6x).
- `correct`, one 0.5 km2 cell (18 nodes): 33.6 s to 26.3 s. One 1 km2 cell: about 64 s to 35 s.
- `build`, cold cache, 4 leaves, 4 requests/s: 24.0 s to 18.8 s. The floor is 64 tiles / 4 per s =
  16 s of Esri schedule plus about 2 s of start-up, so `build` now runs at the request rate.
- Averaging lidar points into grid cells was dropped. It is 60x faster for the reference image
  (0.7 s against 42 s) but does not reproduce it: against the EA-aerial truth at the eight survey
  sites it keeps 2 to 4 of 8 boxes within 0.3 m (old: 4), and single-site shifts move by 0.3 to
  1.0 m. Bin sizes 0.25 m (sigma 1 to 4 px), 0.5 m and 1 m with linear upsampling were tried.
- Splitting the Delaunay triangulation into overlapping strips also changes the output (26 % of
  reference pixels differ by up to 100 intensity units at Belford, margin 30 m): Qhull's result
  on raw BNG coordinates (about 4e5 m) is sensitive to the point subset.

## What changed

| Change | Effect | Output |
| --- | --- | --- |
| `build_store` fetches imagery and DSM/DTM of later leaves on 2 threads while the current node is meshed | Esri request schedule never idles | identical |
| `read_first_return_intensity` reads each LAZ once and returns the points of every cell, in file order | 12 cells: 6.6 s against 12 reads | identical points |
| `KDTree.query(workers=-1)` for the lidar gap mask | 7.2 s to 0.8 s per km2 | identical |
| `LinearNDInterpolator` evaluated in row strips on threads, after one warm-up point | 8.5 s to 1.3 s per km2 | identical |
| BNG to Web Mercator transform in row strips on threads, one PROJ transformer per strip | 4.8 s to 1.2 s per km2 | identical |
| Window matching on threads | 8.7 s to 3.4 s per km2 (with BLAS limited) | identical |
| Lidar reference and Esri resampling concurrently in one cell | 24 s to 17 s per km2 | identical |
| Cells measured in up to 8 worker processes (`spawn`); Esri tiles fetched in the main process | scales across cells | identical |
| `OPENBLAS_NUM_THREADS` and `OMP_NUM_THREADS` default to 1 in `satmesh_cli` | 12 cells: 206 s to 75.5 s | identical |

## Profile of one 1 km2 cell, before

Reference image 42 s (Delaunay 16.5 s, barycentric transforms 7 s, evaluation 8.5 s, KD-tree 7 s),
reading points 8.4 s, Esri luma 7.5 s (4.8 s of it the pyproj transform), window matching 5.2 s.
After: the Delaunay triangulation and the barycentric transforms (about 23 s, serial inside scipy)
are the floor of one cell; cells run in parallel.

## Traps

- Qhull (`scipy.spatial.Delaunay`) is not thread-safe: threads building triangulations returned
  garbage with no error. Parallelise it with processes.
- A PROJ transformer keeps its grid file open and must not be shared between threads
  (`TIFFFetchDirectory ... Seek error`, worker crash). One transformer per thread.
- `LinearNDInterpolator` builds its barycentric transforms on the first call; threads that race
  there each repeat the 7 s. Evaluate one point first.
- BLAS pools inside threads inside processes oversubscribe the cores: window matching went from
  4.7 s to 38 s per cell with 4 workers. `OPENBLAS_NUM_THREADS=1` fixes it. `threadpoolctl` would
  set this at run time instead of through the environment; it is not a dependency yet.
- laspy's scaled views (`chunk.x[mask]`) return empty coordinates for a mask with few hits;
  convert with `np.asarray` first (unit test `test_lidar_reference.py`).
- `pkill -f "sleep 3"` matches the calling shell's own command line.

## Limits

- Memory: a worker holds about 2 GB for a 0.8 km2 cell; 12 cells on 8 workers peaked at 17.6 GB in
  all (`MAX_CELL_WORKERS`). The reader holds all cells' points at once, about 25 bytes per point.
- Spawned workers import the pipeline once each (about 4 s).
- The 12-cell store: `big_new` run at 10 requests/s; Esri tiles were cached.
