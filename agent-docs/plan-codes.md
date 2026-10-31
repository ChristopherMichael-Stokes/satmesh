---
status: current
topic: process
summary: Glossary of the plan codes used in agent-docs (S, F, E, C, T, M series) and the TODO.md item each maps to.
answers: What does code E4 or F5b or M-A mean; which doc covers a plan code; which TODO.md item maps to which code
---

# Plan codes

`TODO.md` is human-facing and uses no codes. Agent docs use the codes below; the doc column is where
to read about it.

| Code | Meaning | Doc |
| --- | --- | --- |
| S1, S5, S6 | Spikes: Esri native depth, mesh baseline, EA aerial against Esri z19 | `s1-results.md`, `s5-results.md`, `s6-results.md` |
| S2, S2b, S3, S4, S7 | Spikes left open: older Esri releases, elevation coverage, more England sites, Scottish lidar | `status.md`, `uk-sources.md` |
| F1 to F2 | Core geometry; Esri plus EA DTM fetch | `f1-f2-plan.md` |
| F2a, F2b | Source registry and other regions | `region-research.md` |
| F4 | `satmesh-mesh`, DTM plus texture to GLB (partly superseded) | `f4-plan.md` |
| F5, F5a | Tiled store, exporters, CLI; first-return DSM visual mesh with DTM ground grid | `f5-plan.md`, `f5-results.md`, `f5a-results.md` |
| F5b | Gazebo collision mesh (open) | `risks.md` |
| F5c | Terrain past about 6 km (open) | `risks.md` |
| F6 | Evaluation harness: height, smoothness, visibility, offset, texture scores | `f6-plan.md`, `f6-results.md` |
| F7 | Real-photo localisation test, required before v1 | `decisions.md` |
| E1 | Smoother, hole-free elevation by classical processing (not started) | `status.md` |
| E2, E2b | Lidar-referenced imagery position correction; towns and woodland with lean | `e2-results.md`, `e2b-results.md` |
| C1 to C6, T0 to T2 | E2b build stages and opening measurements | `e2b-results.md` |
| E3, E5 | Sharpen imagery past native zoom; fine-tuned super-resolution (not started) | `e4-research.md` |
| R0, R1, R2 | Regions: registry and Middle East build, US 3DEP, polish for merging | `regions-plan.md`, `us-sources.md` |
| E4, E4b | Fine height detail from coarse elevation; PixTransform trials, pretrained height models | `e4-results.md`, `e4b-results.md` |
| E6 | Combine several captures (not started) | `status.md` |
| E7 | Single-image height as detail layer (superseded by the E4b height models) | `e4-research-2.md` |
| E8 | Lidar surface refinement (closed, mesh unchanged) | `e8-results.md` |
| E9 | Stretched texture on steep faces (closed, no fill built) | `e9-results.md` |
| M-A, M-B, M-C | Compositions of a height model onto the coarse DEM (anomaly, bare-earth base, per-cell gain) | `e4b-results.md` |
| M1 to M5 | Part 3 stages: zero-shot sweep, guided refinement, fine-tuning, coarse-DEM conditioning, Yemen dry run | `e4b-plan.md` |
| E0, E1 (proposal) | First stages of the PixTransform successor: masked anomaly surface, per-image correction | `pixtransform-proposal.md` |

## TODO.md items to codes

| TODO.md item | Code |
| --- | --- |
| Height detail from coarse elevation | E4, E4b |
| Stretched texture on steep faces | E9 |
| Imagery position correction (shipped) | E2 |
| Position correction in towns and woodland | E2b |
| Different region (Yemen), source registry | F2a, F2b |
| Combine several captures | E6 |
| Terrain past about 6 km | F5c |
| Smoother elevation data | E1 |
| Sharpen past native zoom | E3 |
| Fine-tuned super-resolution | E5 |
| Single-image height as detail | E7, E4b |
| Wales lidar points, Scottish lidar route | E2 follow-up, S7 |
| Older Esri releases | S2, S2b |
| Elevation coverage, more England test sites | S3, S4 |
| ML environment split | `ml/` workspace |
| Real-photo localisation test | F7 |
| Gazebo | F5b |
