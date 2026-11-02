# Watching a first-fix run

`satmesh-monitor` (in the `locate/` workspace) shows a first-fix run on a map. It reads the run's
`events.jsonl`, so it can replay a finished run or follow a run that is still writing.

```text
uv run --extra gpu satmesh-monitor RUN_DIR \
  [--host 127.0.0.1] [--port 8765] [--photos DIR] [--tiles DIR]
```

Open `http://127.0.0.1:8765/`. The monitor only reads: it changes nothing in the run directory.

## What the page shows

- **Map:** Esri World Imagery of the area, the area outline, and the position prior as a circle and
  the heading prior as a wedge (drawn wider when a prior is relaxed).
- **Coverage:** one square per searched position. Grey squares are rendered; described squares are
  coloured by their best similarity, with the numeric range in the legend.
- **Places:** numbered markers per search level (circles for level 1, squares for level 2). Once
  places are checked, the outline shows queued, running, accepted or rejected, with inliers and
  tracked frames. The fix is an arrow pointing along its heading.
- **Convergence:** the spread of the candidate places (RMS distance from their centroid, log scale)
  against time.
- **Progress:** each stage with its start, end, elapsed time and unit count.
- **Photo:** the first photo of the run, when `--photos` names the directory holding it.
- **Timeline:** a scrubber, play and pause at 1x, 10x and 60x. The map shows the run as it stood at
  the chosen time. A run that is still growing is followed live until the scrubber is moved back;
  End jumps to the latest event.

## Imagery

Tiles come from the local Esri cache (`~/.cache/satmesh/esri-world-imagery/live`, or `--tiles`) and
are never requested from Esri. Zoom levels 18 to 20 are served as stored. Coarser tiles are built
from the zoom 18 tiles and kept in `~/.cache/satmesh/monitor-tiles`. Where the cache has no tile the
map shows its dark background.

The page works offline; MapLibre GL JS is bundled with the package.
