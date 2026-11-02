---
status: current
topic: evaluation
summary: Plan for a live map monitor of the first fix, for human users of the tool: the Esri imagery as basemap from the local tile cache, the searched area ticked off as cells are rendered and scored, nodes at render and check sites, candidate places and verification results, the prior intervals drawn on the map, and a shrinking set of hypotheses converging on the fix; fed by an append-only event file so the search code carries no server; stages U0 to U4 (a replay from cached data comes first), dependencies and forks for the owner.
answers: What should the live monitor show; how does the first fix feed it without slowing down; where do the map tiles come from; which stages build it and what does each check; what can be shown today from cached data; which dependencies and decisions wait for the owner
---

# Live monitor for the first fix: plan

Owner request 2026-11-01: a live UI to turn the first fix into a real tool for human users, a map
on the Esri imagery where searched areas get ticked off and nodes appear at render and check sites
until the search converges on the fix. Plan first. Related: `photo-only-first-fix-plan.md`.

## Progress

- U0 done 2026-11-02: `satmesh_locate.events` (models, writer, reader, tests) and replays of the
  2.5 km frames 1 and 75 (`uncommitted/photo-only/replays/area25-f001` and `-f075`, scratch generator
  `bexhill/scripts/make_replay.py`). Their level 1 candidates and final places sit at the distances
  the runs recorded. Level 2 cell scores were never cached, so the replay shows level 2 as stage
  events and final places only.
- U1 done 2026-11-02 (`satmesh-monitor`), U2 done the same day: a real Bexhill frame 1 run with a wrong
  heading prior was followed live (cells, relaxed prior, rejected and accepted places, the fix arrow).
  Owner chose the web stack below and a read-only first version; U3 stays out. U4 is next.
- U1 built 2026-11-02: `locate/packages/satmesh-monitor` (replay and live tail of `events.jsonl`,
  basemap from the local Esri cache, coverage, places, verification states, fix, prior shapes,
  convergence strip, progress, scrubber); MapLibre GL JS 5.24.0 vendored. Rendered headlessly on
  the `area25-f075` replay; owner review of the replays is next.

## What the user sees

| Layer or panel | Shows |
| --- | --- |
| Basemap | Esri World Imagery of the area, with the required attribution |
| Area and priors | the store footprint, the position prior as a circle, the heading prior as a wedge, height and pitch as text; a relaxed prior (the widening ladder) redrawn when it widens |
| Coverage | one cell per searched position: pending, rendered, described, then coloured by the best similarity over its headings and heights; level 1 first, level 2 cells appear around the surviving places |
| Candidate places | numbered markers sized by rank and similarity, moving and shrinking in number as the search narrows |
| Check sites | nodes where a candidate is refined and tracked: queued, running, result (inliers, frames tracked), accepted or rejected |
| Fix and track | the final pose with its heading arrow, then the recovered path, and the logged path when a reference exists |
| Convergence | the spatial spread of the live candidates (kilometres to metres) against time, so the user sees the search close in |
| Photo panel | the frame being located beside the render of the current best candidate, with a blink toggle |
| Progress | stage timeline with counts, elapsed time and an ETA from the cost model (count times unit cost), GPU and RAM gauges |

## How the search feeds it

- The first fix writes an append-only `events.jsonl` in the run directory; a separate `satmesh-monitor
  RUN_DIR` process tails it. No server, socket or thread sits in the hot path, and a run started
  elsewhere can be watched by pointing the monitor at its directory.
- Events are typed and versioned (frozen models, `extra="forbid"`): run start (area bounds, priors,
  frames, grid plan), stage start and end, a batch of cells with their scores, the ranked candidate
  places, a verification start and result per place, a prior relaxed, the fix, run end.
- Cells are summarised per position and batched at 5 to 10 Hz, never one event per view; the 2.5 km
  level 2 holds about 180 positions and a 100 km2 level 1 about 2,000, so the files stay small.
- The same file is the replay source: the monitor opens a finished run and scrubs through it.
- Cross-component contract: tested by writing events with the emitter and reading them with the
  monitor's reader.

## Basemap

- The Esri tile cache holds `live/{z}/{x}/{y}.jpg` at z18 to z20 (72,000 tiles, 892 MB on this
  machine). The monitor serves tiles from it, so the browser never requests Esri tiles directly
  and the etiquette rule (cache by z/y/x, throttled, descriptive User-Agent) holds.
- Zooms below 18 are built from z18 tiles by the monitor and cached; a 10 km square is about 4,300
  z18 tiles. The monitor can fetch a missing tile through the existing throttled client.
- The map reads store coordinates (ENU) and converts them to longitude and latitude with the
  store's frame.
- Esri imagery stays local: no replay page with Esri tiles goes to a hosted artifact.

## Stages

| Stage | Builds | Check | Time |
| --- | --- | --- | --- |
| U0 Event contract | event models, the JSONL writer and reader in `satmesh-locate`, tests; a replay generator that turns cached runs (grids, descriptors, `places.json`, timings) into events | writer-reader round trip; the generated replay of the 2.5 km frame 75 run lists its stages and 20,400 level 2 views | hours |
| U1 Replay viewer | `satmesh-monitor` serving a map page: basemap from the cache, coverage, places, check sites, convergence, photo panel, scrubber | the owner watches the replay of the 2.5 km frames 1 and 75 and the Bexhill frame 1 run, and says whether it explains the search; screenshots from a headless browser if one is available | a day |
| U2 Live tail | the monitor follows a growing `events.jsonl`; the emitter is added to the packaged first fix as F3 lands | a real two-stage run shows cells ticking off while it runs; the emitter adds under 1 % to the run time (profile before and after) | with F3 |
| U3 Priors on the map | draw the position circle and heading wedge on the map, type height and pitch, write the config the search reads | a prior drawn on the map reproduces the same search as the same prior on the command line | after U2 |
| U4 Fusion and ladder views | the frames of a window, their heading offsets, the summed score; the widening ladder step by step | shown on a deliberately wrong prior | with F2 |

- The replay in U0 and U1 needs no new run and no change to the search: the grids, descriptors,
  query descriptors and timings of the Bexhill and 2.5 km runs are in `uncommitted/photo-only/`
  (`photo-only-two-stage-recipes.md`).
- Judged by eye first (the owner's working principle), then the numbers.

## Dependencies and forks (waiting for the owner)

- A web stack: Starlette with uvicorn for the monitor (established, no hand-rolled HTTP) and a
  vendored MapLibre GL JS for the map, with deck.gl or a canvas layer for tens of thousands of cells.
  Vendored so it runs offline. New dependencies, so they need a yes.
- Where it lives: a new package `satmesh-monitor` in `locate/packages/`, and the event models in
  `satmesh-locate`. The alternative is a separate workspace; not recommended.
- Whether U3 (priors drawn on the map) is in scope for the first version, or the monitor is read-only
  first.
- Whether the first demo is the replay from cached data (recommended: no run, no download) or waits
  for U2.
