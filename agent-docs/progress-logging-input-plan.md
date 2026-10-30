---
status: historical
topic: baseline-pipeline
summary: Built plan: --nw and --se lat/lon corner input, progress display, loguru run.log in the store
answers: How do I give corners to satmesh build and eval?; Where is the run log written?; Why was the BNG bbox option removed?; How is progress reported?
---

# Plan: progress display, loguru run log, lat/lon corner input

Approved by the owner on 2026-10-26 with its recommendations (two options `--nw` and `--se`, BNG
form dropped, `run.log` in the store); `threadpoolctl` was added with it. Built as described.

## Recommendation

Do all three in one change, in this order: corners (small, changes every command line), progress
(needs a reporting hook through `build_store` and `measure_correction`), run log (reads the same
hook). One checkpoint each.

## 1. Corner input

- Replace `--bbox W S E N [--crs ...]` on `build` and the five `eval` commands with
  `--nw "LAT, LON" --se "LAT, LON"`, text as copied from a map (`"53.9236, -2.0015"`). Remove the
  old option and `--crs` everywhere in the same change; update the Makefile slice target, README
  and AGENTS.md.
- Parsing: one function turning the string into `(lat, lon)`, rejecting anything but two numbers,
  latitude outside -90..90, longitude outside -180..180, and corners that are not north-west and
  south-east of each other. Typer calls it as a `click`-style parser, so the error is one line.
- `build`: corners to a WGS84 `Aoi` (already supported by `Aoi`), then the existing outward snap to
  whole BNG metres.
- `eval`: corners to BNG through OSTN15 (`wgs84_to_bng`), snapped inward to whole metres, so the
  box stays inside the store and the EA WCS request is on whole metres. Today these commands take
  BNG metres directly.
- Open choice: keep a BNG-metres form for scripts and the survey stores. Recommendation: no, per the
  sole-maintainer rule; BNG corners convert to lat/lon with one line of `pyproj` when needed.

## 2. Progress

- Show step name, steps done of total, elapsed time and time remaining. Library: `rich.progress`
  (`BarColumn`, `TimeElapsedColumn`, `TimeRemainingColumn`, a text column for the running step).
  `rich` is already in `pipeline/uv.lock` through typer; it becomes a declared dependency of
  `satmesh-cli`, with no new package installed.
- Reporting hook: `build_store` and `measure_correction` take a required
  `report: Callable[[str, int, int], None]` (step name, done, total) and stay free of any display
  library. The CLI builds it from a `Progress` task; tests pass a list-appending function.
- Steps. `build`: one step per node, the name says leaf or parent and its tile. `correct`: lidar
  squares downloaded, reading points (all cells in one pass), one step per cell matched, tiles
  updated. Time remaining is a straight extrapolation from steps done, which is rough while the
  lidar download (minutes) and the per-cell matching (about 30 s) differ so much; the display
  shows the step name so the wait is explained.
- Output goes to stderr, as now. With stderr not a terminal, `rich` prints no bar; the run log
  below carries the same events.

## 3. Logging (loguru) and the run log

- Add `loguru` to `satmesh-cli` only. Library packages keep `logging.getLogger(__name__)` calls;
  the CLI installs the standard loguru handler that forwards stdlib records (needed for `httpx`
  and the existing `built node ...` lines).
- Sinks: stderr at INFO as now, and `<store>/run.log` at DEBUG, appended by every command that
  takes `--store` (`build`, `correct`, the three exports, the store-based `eval` commands). A
  command opens the file sink after it has the store path and removes it on exit.
- Content per run: a first record with the command, its arguments, versions of satmesh and the
  main libraries, worker and thread counts; one line per step with its duration; for `correct`
  the per-cell result (windows used of total, shift, bound, corrected or not), lidar download
  sizes and times, and the final summary. Timings use `time.perf_counter`.
- Existing `logging.basicConfig` in `configure_logging` is removed in the same change.
- The correction prints nothing today until it finishes; with the hook above it logs per cell as
  results arrive.

## Questions for the owner

1. Approve `loguru` and the `rich` declaration?
2. Option names: `--nw` and `--se`, or one `--corners "LAT, LON; LAT, LON"`? Recommendation: two
   options, since each is what a map copy gives.
3. Is dropping the BNG-metres form on `build` and `eval` acceptable?
4. Run log file name: `run.log` in the store directory (recommended).
