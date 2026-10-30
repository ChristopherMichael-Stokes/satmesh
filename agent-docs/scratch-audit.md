---
status: historical
topic: process
summary: Read-only audit of uncommitted/ against agent-docs before cleanup: keep e4b and e4 scratch, about 3.4 G freeable, and a per-doc list of facts missing from the docs.
answers: Which scratch directories can be freed safely?; Which uncommitted scripts and data must be kept?; Which facts live only in scratch and not in docs?; How large is each scratch directory?; What lives only in /tmp session scratchpads?
---

# Scratch audit before cleanup

Read-only audit, 2026-10-30, of `uncommitted/` (git-ignored) against `agent-docs/`. Nothing was
moved or deleted. Docs read at commit `0082a1f` (which already added `m1-model-recipes.md`,
`dinov3-landcover-results.md` and the 5.4 km store table to `e4b-results.md`, so those are not
counted as gaps). "Verified" = I read the file or ran the listing. Sizes are `du -sh`.

## Conclusions

- Keep, whatever else happens: `uncommitted/e4b/` (10 G) and `uncommitted/scratch-archive/e4/` (1.5
  G, but see the glb/page split below). Every e4b script reads `e4/{ferry,aire}-inputs.npz`,
  `-texture.npz`, `out/`, `scores.json`, `score.py`, `render.py`, `make_page.py`, `glbs.py`
  (verified by grep: `m1/common.py`, `e0/common.py`, `dino/common.py`, `m1render.sh`, `s1.sh`,
  `m2render.sh`, `combine.py`, `s2_check.py`). The stores, `seg/feats` (2.7 G), `seg/work`,
  `m1/pred` and `e0/` are inputs of the E0 / E1 / PixTransform-successor work in `status.md`.
- Keep until the open-ground-truth re-check (`metric-bias-audit.md` re-check 1, listed in
  `status.md` "Open risks") is done: `scratch-archive/lean2/{southend_t,ferry_t}.npz` (680 MB) with
  `*_obs.pkl`, `fits.py`, `*_results.json`, plus `scratch-archive/c6/gate.py` and
  `scratch-archive/s0b/lean.py` (imported by `lean2/fits.py`). `c6/gate.py` loads
  `lean2/{box}.npz` and `{box}_obs.pkl`.
- Safe to free about 3.4 G now, after small text extractions below: `scratch-archive/lean` (1.0 G),
  `s0b` npz (about 700 MB), `lean2/southend_l.npz` (276 MB), `c5/work` (495 MB), `c3c4` (342 MB),
  `uncommitted/t0` store nodes (1.6 G), `e2b-lean` images (356 MB), `offset-survey` (94 MB),
  `s0` stores (80 MB), `eval-slice` (1.4 MB; `make eval-slice` regenerates).
- The biggest real gaps (facts only in scratch text files) are in `e2b-results.md`: it has no
  lean2 section and no C5 section; `status.md` carries the lean2 ground errors but not the
  per-fit tables, and the C5 results exist only in `c5/progress.log`, `c5/work/*.json`. `status.md`
  "Next: C5 before/after strips" is stale: C5 was run on 2026-10-29 (page built, 2.7 MB).
- `e4-results.md` misses the kriging variogram fits and a trap: the Upper Aire fits are degenerate.
- `offset-survey.md` lacks the BNG corners of its six boxes (only in a /tmp session scratchpad).
- Not recreatable from docs and living only in /tmp session scratchpads (see last section):
  `c4_check.py` (the C4 UV check), the `c1c2` scripts, `torchenv` (hard-coded in
  `e4/run_all*.sh` and `e4b/m1/run.sh`), and the survey box list.

## Table, one row per directory

Sizes: S = size. Large kinds from `find -size +5M`. "Doc" = the agent-docs file recording results.

| Directory | What it is (verified from scripts/logs) | S, large kinds | Doc, and honest check | Still needed by upcoming work? | Verdict |
| --- | --- | --- | --- | --- | --- |
| `scratch-archive/e4` | E4 PixTransform trial: inputs, texture, per-method outputs `out/` (227 files), scores, renders, GLBs, 2 small stores; later M1/M2/E0 surfaces are written into `out/` and `glb/` by e4b scripts | 1.5 G: `glb/` 990 M (78 GLBs 13 to 32 MB), `page/` 216 M, `out/` 164 M, `*-inputs.npz` 14 M, `*-texture.npz` 8 to 11 M, stores 80 M | `e4-results.md`, `e4b-results.md`. RMSE and edge-slope tables, shift runs, runtimes, traps are in. Not in docs: fitted kriging variograms (below), `scores.json` strata (MedAE, NMAD, slope class, cover; file kept), `pix-progress*.log` schedule | Yes, hard: all e4b scripts (list in Conclusions) | KEEP `out/`, inputs, texture, scripts, `vendor/`, `scores.json`, stores. `glb/` + `page/` (1.2 G) regenerable by `render.py`, `make_page.py`, `glbs.py` (cost not measured); keep until the owner finishes judging E0 / M2 renders, then optional delete. EXTRACT the variogram facts to `e4-results.md` first |
| `scratch-archive/lean` | First lean fit at 4 sites (Worcester, Southend, Newcastle, Brighton, Brighton2): box search, prep, matcher, closure, strips; S0b cross-check | 1.0 G: 5 x 212 MB `*.npz` (DSM/DTM/RGB), scripts 15 + 8 KB, `progress.log` 8 KB | `e2b-results.md` "Lean fit at four sites". Scene table and closure before/after are in. Missing: box search counts, matcher funnel, t and l per scene and per height definition, t-only closure, S0b cross-check (below) | No. `lean2` superseded it; nothing imports `lean/` (`lean2/fits.py` imports `s0b/lean.py`) | EXTRACT THEN DELETE npz. Keep `progress.log`, `*_polys.json`, `boxes.json`, `fit.py` (about 50 KB) |
| `scratch-archive/lean2` | Conditioning study of the joint (t, l) fit: F0 to F5, bootstrap, closure, truth sensitivity, at southend_t, ferry_t, southend_l | 912 M: `southend_t.npz`, `ferry_t.npz` 340 M each, `southend_l.npz` 276 M; `*_obs.pkl` 31 KB each; `results.md` 7.8 KB, `results_tables.md`, `*_results.json`, `progress.log` 12 KB | `status.md` (F0 to F5 ground errors at both truth sites, owner chose F2) and `e2b-results.md` C1/C2 (F2 reproduction). No lean2 section in `e2b-results.md`; per-fit table, F3, F4 trace, truth sensitivity, windows and thresholds are missing | Yes: `metric-bias-audit.md` re-check 1 re-scores these fits on open-ground truth; `c6/gate.py` loads the npz and pkl. Repo test fixture `lean2-observations.json` holds the roofs only | KEEP `southend_t`, `ferry_t` npz and pkl until re-check 1 is done. `southend_l.npz` EXTRACT/DELETE (no truth; regenerated by `prep2.py`, about 12 min with cached Esri). Add the lean2 section to `e2b-results.md` first |
| `scratch-archive/s0b` | S0b: is Esri a true orthophoto? Worcester 8-box survey, Aire and Ferry, synthetic lean checks, `lean.py` matcher | 777 M: 8 x 22 to 84 MB `x*.npz`, `aire/ferry*.npz` 43 M, `results*.json` 12 to 62 KB, `progress.log` 26 KB, `offset_vs_height.png` 118 KB | `e9-results.md` S0b, `e2b-results.md` (halving). Pooled slope, azimuth, synthetic "about half" are in. Missing: matcher variants and counts, Aire/Ferry ground-window medians, synthetic table, per-box acceptance (below) | `lean.py` is imported by `lean2/fits.py` (keep with scripts); the npz are not read by anything still planned | EXTRACT THEN DELETE npz (about 700 M). KEEP all `*.py`, `*.json`, `progress.log`, `*.out`, png (about 300 KB) |
| `scratch-archive/c5` | C5: before/after review page for the Southend lean correction (strips, ground crops, store-wide ground check, consistency checks) | 479 M: `work/analysis.pkl` 250 M, `render.npz` 206 M, `ref_gradient.npy` 40 M; `index.html` 2.7 MB; scripts 7 files; `progress.log` 6.7 KB; `work/{consistency,ground_store}.json` 2 KB | No doc records C5. `metric-bias-audit.md` says "`c5/progress.log` holds only scores". `e2b-results.md` has no C5 section; `status.md` calls it "Next". Gap is total (below) | No. Page was built and shown; regenerable from the `c3c4` stores in about 10 min (progress.log 19:54 to 20:04) | EXTRACT THEN DELETE `work/` pkl/npz/npy. Keep scripts, `progress.log`, `work/*.json`, `index.html` (about 2.9 MB) |
| `scratch-archive/c3c4` | C3/C4 real flow at Southend 0.79 km: three copies of one build (`l500`, `l500-nolean`, `l500-uncorrected`), slice100, GLB and Gazebo exports, correct/build outputs | 342 M: 3 x 32 MB export GLBs, node GLBs 9 to 11 MB each | `e2b-results.md` "C3/C4 build": table, 4 lean nodes, vertex counts, UV check, traps. Complete. Logs hold nothing extra (verified `progress.log`, `*.out`) | No. Only a use was C5, which is done. Note it has no corrected cell, so it cannot show ground-only against lean | SAFE TO DELETE. Regenerate: `satmesh build --nw .. --se .. --store S`, `satmesh correct --store S` (74 s + 63 s, network) for each variant, about 5 min |
| `scratch-archive/c6` | C6 gate: de-leaned re-registration then F2 refit, southend_t and ferry_t | 24 K: `gate.py` 4.8 KB, `progress.log`, 2 gate JSONs | `e2b-results.md` "C6 result": declaration, table, gate verdict, trap. Complete; extra: thresholds (de-leaned 0.0761 vs raw 0.0955 at Southend; 0.0979 vs 0.0880 at Ferrybridge), runtimes 5 to 12 s | Yes if re-check 1 reruns the gate on open-ground truth | KEEP (24 KB) |
| `scratch-archive/c1c2` | Only `progress.log` here; build log of C1/C2 (roof port identical to lean2 on 3 boxes, F2 reproduced) | 8 K | `e2b-results.md` C1/C2 build covers it (219 tests, identical = True, 3 s per box) | No | KEEP the log (4 KB) or delete; nothing missing from docs. The scripts are not here (see /tmp section) |
| `scratch-archive/t0` | E2b T0 helpers: identify grid, cell-vs-polygon cover (`cells_cover.json`), EA aerial crops, 4 `offset-*.txt` truth results | 2.6 M: `town.png` 1.4 MB, JSON 12 KB, 9 scripts | `e2b-results.md` T0. Group tables and truth values are in. Missing: per-cell cover shares, truth intervals and window counts (below) | No | KEEP (2.6 MB, small); or delete `town.png` |
| `scratch-archive/t1` | E2b T1 ground-only mask experiment, 14 boxes | 92 K: `results_main.json`, `results_b95.json`, `results_smoke.json`, `progress.log` 10 KB, `t1.py` | `e2b-results.md` T1 summary only; per-box counts are missing (below) | No | KEEP (92 KB) |
| `scratch-archive/q` | Esri `MapServer/4` query probes (layer 4 definition, stats, polygons, overlap scripts `ov*.py`, `simp2.pbf`) | 3.5 M | `e2b-results.md` "Esri scene polygons by one query" holds the working query and fields. Complete | No | SAFE TO DELETE (regenerable from the documented query; a few seconds) |
| `scratch-archive/txt` | Text extracts of 5 PDFs (Yamakawa and Fraser affine model, Gunay true orthophoto, Mapflow data sheet, Mastin 2009, Parmehr 2013) | 124 K | Cited in `e2b-results.md` T2 prior-art, `e2-research.md` | No | SAFE TO DELETE (the PDFs are public; the docs hold the verified quotes). Keep if offline reading is wanted |
| `scratch-archive/page` | Review page "Steep Face Stretch" (E9 S0), 6 ONGs | 264 K | `e9-results.md` S0 has the numbers | No | SAFE TO DELETE |
| `scratch-archive/leanpage` | Generator of the "Lean Correction Check" page (E2b lean fit review) | 40 K | Page URL not recorded in any doc | No | SAFE TO DELETE, or keep with `lean` scripts (40 KB) |
| `scratch-archive/s0_stretch.py`, `s0_views.py` | E9 S0 stretch histogram and views scripts | 3.4 + 4.0 KB | `e9-results.md` names `s0_stretch.py` but not its command | Only if E9 reopens (closed by owner) | KEEP both (8 KB), small |
| `uncommitted/t0` | Ferrybridge 5 km store used for T0 (310 nodes), `build.log`, `correct.log`; also used to exercise the old-store refusal | 1.6 G: node GLBs and JPEGs; JSON 1 to 11 KB; `run.log` 33 KB; `correction.json` 11 KB | `e2b-results.md` T0. Aggregates are in; per-cell shifts (36 cells) only in `run.log` and `correction.json` | No (the refusal test is in the repo test suite; schema 1 store) | EXTRACT THEN DELETE nodes. Keep `run.log`, `correction.json`, `build.log`, `correct.log` (about 70 KB). Regenerate: build 10 min, `correct` 213 s |
| `uncommitted/e2b-lean` | Images for the lean review page: per site full original / ground-shift-only / lean-corrected ONGs (22 to 26 MB each), overviews, 8 roof strips, `stats.json` | 356 M, PNG | `e2b-results.md` "Lean fit at four sites" summary; page was judged by the owner. `stats.json` (11 to 16 KB each) holds per-scene fits and roof choices | No | EXTRACT THEN DELETE ONGs. Keep the 5 `stats.json` (about 40 KB) |
| `uncommitted/offset-survey` | 6 GLBs of the E2 survey stores for Blender | 94 M: 2-southend.glb 46 M, 4-loughborough 19 M, 1-dunster 15 M, 5-neston 14 M | `offset-survey.md` table complete; no logs here | No | SAFE TO DELETE after adding the box corners (below). Regenerable by rebuilding each box, about 1 to 3 min each plus `export glb` |
| `uncommitted/s0` | E9 S0 stores (Upper Aire, Ferrybridge, Snettisham) plus stretch histograms and `views/` | 80 M; text 10 KB | `e9-results.md` S0 has the main table. The per-bin area and face shares (7 bins) exist only in `*.s0.txt` | No (E9 closed) | SAFE TO DELETE after keeping `ferrybridge.s0.txt`, `snettisham.s0.txt`, `builds.log` (4 KB) |
| `uncommitted/eval-slice` | Output of `make eval-slice` (100 m slice store) | 1.4 M | Regenerated by the Makefile target (needs network) | No | SAFE TO DELETE |
| `uncommitted/contract-test` | Output of `make test-contract` | 32 K | Regenerated by the Makefile target | No | SAFE TO DELETE (not in the brief's list; noted for completeness) |
| `uncommitted/e4b` | Active E4b work: 5.4 km stores (aire 1.4 G, ferry 2.0 G, southend 2.7 G, ferry-slice 89 M), `seg/` (feats 2.7 G, work 787 M, maps, slice 125 M), `m1/` (pred 95 M, tables), `e0/` (E0 in progress, 38 M), `dino/` (184 M), review page builds (`s1-page` 26 M, `m1-page` 19 M, `m2-page` 18 M, `dino-page` 3.6 M), `eye/` 20 M | 10 G | `e4b-results.md` and `dinov3-landcover-results.md` hold the headline numbers and recipes. Not in docs: E0 first numbers, full per-method M1 tables, S2 port check detail | Yes, everything: the next steps are E0 then E1 and the successor PixTransform proposal | KEEP ALL. Review page folders (about 70 M) could go after the owner has seen them, but are not worth the risk now |

## Gap list per target doc (facts to add before deleting)

All facts are from the scratch files named in brackets; page and line numbers are not applicable
(logs, JSON). Numbers are as printed.

### `e2b-results.md`

1. New section "Lean2: conditioning of the joint fit (2026-10-29)" [`lean2/results.md`,
   `results_tables.md`, `progress.log`]. `status.md` has only ground errors. Add:
   - Declaration: soft-L1, f_scale 1 m, 300 bootstrap reps over roofs and 4 x 4 window blocks;
     F0 roofs only; F1 roofs plus windows; F2 F0 plus ground prior as pseudo-observation (sd from
     block bootstrap interval / 3.92 in quadrature with 0.4 m); F3 centred F0; F4 alternation from
     l = 0; F5 whole-image Powell on NCC.
   - Boxes: southend_t (BNG 587000, 185000, EA aerial 2024-06, truth +0.23, +1.57); ferry_t (448500,
     423500, aerial 2020, truth -0.31, +0.71); southend_l (588300, 186400, no truth). Scene 20250712
     GE01 (two polygons 3297692 and 3298659 fitted as one); ferry_t scene 20250716 LG01.
   - Roofs and windows: southend_t 13 roofs (h 3.2 to 16.1, mean 5.0) of 52 that passed the building
     tests (714 components), 13 windows of 900 at threshold 0.0955; ferry_t 20 roofs (h 3.4 to
     6.7), 63 windows (0.0880); southend_l 23 roofs (3.0 to 8.4), 17 windows (0.0826). Ground
     priors t0: southend_t (+0.45, +2.12) sd (0.61, 0.48); ferry_t (-0.46, +0.26) sd (0.41, 0.51);
     southend_l (+0.23, +0.75) sd (0.82, 0.88).
   - Table (t E, N; k; az; t sd): southend_t F0 +0.60 +2.40, 0.424, 210, sd 0.28 1.13; F1 +0.49
     +2.62, 0.438, 207, 0.44 0.43; F2 +0.54 +2.23, 0.403, 210, 0.24 0.32; F4 +0.46 +1.77, 0.448;
     F5 +0.38 +2.12, 0.326. ferry_t F0 -1.37 +5.79, k 1.128 (above cap), roof residual 1.99, tN sd
     3.83; F1 -0.46 +0.65, 0.148; F2 -0.57 +0.46, 0.146 (k95 0.04 to 0.71); F4 -0.01 +0.09; F5 -0.60
     +1.65. southend_l F0 +0.25 +3.54 (reproduces the published t); F1 +0.76 +1.52; F2 +0.24
     +2.44; F4 +0.01 +1.20; F5 +0.17 +1.90.
   - F3 finding: bootstrap sd of t at mean roof height is 0.12 / 0.40 (southend_t), 0.22 / 0.89
     (ferry_t), 0.13 / 0.30 (southend_l) against 0.28 / 1.13, 0.95 / 3.83, 0.30 / 1.01 at h = 0:
     the extrapolation to the ground is what is poorly conditioned.
   - F4 trace at southend_t: dt per iteration 0.24, 0.27, 0.18, 0.23, 0.80 m, windows 20, 18, 22,
     22, 21 (window set changes with the warp).
   - Uncorrected closure (median |offset| of re-matched roofs): southend_t 1.15, ferry_t 2.84,
     southend_l 1.07 m; closure values are not comparable across fits (n changes).
   - Truth sensitivity: southend_t all 233 windows (+0.28, +1.42); raised fraction under 5 % n = 12
     (+0.92, +2.67); ferry_t all 67 (-0.26, +0.53), under 5 % n = 2 (-0.31, +1.19).
2. New section "C5: lean-corrected render review (2026-10-29)" [`c5/progress.log`,
   `c5/work/consistency.json`, `ground_store.json`; page `c5/index.html`, artifact URL not
   recorded]:
   - Subject rule fixed before results: 8 tallest GE01 roofs, 4 worst after correction, 6
     unfiltered rejected roofs, 3 WV02 roofs; 80 buildings in the store, 16 accepted on Esri-direct
     luma (13 GE01 + 3 WV02), matching production. Ground-window rule needed 3 amendments (absolute
     thresholds gave 0 candidates; 40 m windows were a third to half roofs or trees; single 64 m
     windows gave phase-correlation shifts of up to 18 m, so the ground check became store-wide).
   - Render check: best-fit shift of the lean render's ground against the uncorrected one
     (0.05, 2.10) vs stored t (0.07, 2.13), 0.03 m apart; luma RMS 36.5 unshifted to 5.6 shifted.
   - Store-wide ground registration (windows reliable on Esri-direct, 11 of 529): direct E -0.01 N
     +2.10; A (ground shift only) E -0.09 N +2.92 (10 windows); B (lean render) E +0.10 N +1.25 (7
     windows). Per-window N on direct from -9.27 to +6.4 m: the check is noise, as
     `metric-bias-audit.md` says. The "Southend over-correction" claim therefore rests on these
     numbers, not on a documented eye judgement.
   - Consistency blocks (n = 31): B(p) = A(p+d) median N +1.93 sd 0.74; A(p) = direct(p+d) median
     (-0.06, +0.06), sd about 0.02.
   - Page: 19 strips, 3 ground crops, 2.7 MB.
3. In "Lean fit at four sites" [`lean/progress.log`]: boxes chosen by search (Worcester 385500,
   254600: 223 buildings of 5 m or more, 267 buildings; Southend 588300, 186400: 136 / 187;
   Newcastle first 425500, 564500: 63 / 78, then 426700, 564500: 129 / 158; Brighton 531500, 106300:
   112 / 130; Brighton2 532000, 104600: 50). Funnel (components, passed tests, accepted): Worcester
   833, 264, 32; Southend 1110, 184, 23; Newcastle 567, 149, 25; Brighton 644, 127, 5; Brighton2
   734, 64, 2. Fits (t, l, k with h = p10 of roof height): Worcester WV03 t (-1.16, +1.04) l
   (+0.138, -0.341); Worcester LG02 t (+2.13, +1.86) l (-0.492, -0.261) k 0.557 (0.202 to 1.607);
   Southend GE01 t (+0.25, +3.54) l (-0.124, -0.524) k 0.538 (0.265 to 0.830), with median height t
   (+0.30, +3.08) k 0.387; Newcastle WV03 t (+1.76, -1.32) k 0.118. Shift-only closure (t_only) was
   worse than as published at three of four scenes: Worcester WV03 1.80 to 2.32 (lean 1.54), LG02
   0.81 to 3.18 (lean 0.55), Southend 1.68 to 2.46 (lean 1.22); Newcastle improved 2.79 to 0.87
   (lean 0.67). S0b cross-check (`s0b_xcheck`): 83 buildings in 7 boxes, k 0.654 (0.509 to 0.796)
   with eave p10 height, 0.555 (0.433 to 0.681) with plain height, azimuth 209.5; the doc quotes
   only "about 0.55". Note the log's place label for the S0b boxes differs from the Worcester in
   `e9-results.md` (86 buildings, 8 boxes): same data set or not is unresolved; resolve it in the
   doc.
4. T0 [`t0/ferrybridge-5km/run.log`, `correction.json`, `scratch-archive/t0/cells_cover.json`,
   `offset-*.txt`]: add the 36-cell table or state that it lives in those files; truth intervals
   and windows: T-town E -0.31 (-0.38, -0.23), N +0.71 (+0.37, +0.97), NMAD 0.56 / 1.10, 113 of
   870 windows; B2 WV02-2022 E -0.09, N +0.14 (-0.31, +1.01), NMAD 1.33 / 2.04, 98 of 870; D2 LG02
   E +0.05, N +0.50 (+0.44, +0.65), 166 of 870; E2 LG01 E -0.25, N +1.07 (+0.81, +1.49), 140 of 870.
5. T1 [`t1/progress.log`]: per-box windows, baseline then masked (setting A, at least 50 % unmasked,
   eligible in brackets): Dunster 31 to 50 (666), Southend 21 to 7 (340), Loughborough 23 to 93
   (551), Snettisham 155 to 163 (900), town 50 to 178 (813), 445050 60 to 380 (882), 446100 33 to
   94, 447200 42 to 127, Ferrybridge 57 to 105, Upper Aire 13 to 52, Belford 82 of 196 both.
   Raised/masked shares: Dunster 0.222 / 0.280, Southend 0.371 / 0.482, Loughborough 0.304 / 0.381,
   Snettisham 0.003 / 0.003. The text says Ferrybridge and Upper Aire "could not be compared"; the
   log has their masked counts.
6. C6: add thresholds and runtimes (above) and the "info only" raw-threshold variant: 19 and 43
   windows, errors 0.97 and 0.70 m (text has the errors; windows counts are in the table already).

### `e9-results.md`

[`s0b/progress.log`, `run_extra.out`, `synth2*.json`, `s0/*.s0.txt`]

- S0b matcher variants (dsm, dsm with footprint template `dsmt`, intensity `int`, `intt`):
  Ferrybridge 10 buildings passed, accepted dsm 3, dsmt 2, int 6, intt 1. Worcester boxes accepted
  (dsm / dsmt): 13/16, 14/16, 24/29, 14/13, 11/15, 5/8, 2/0, 0/1 of 37, 57, 48, 25, 31, 21, 4, 5
  attempted; funnel per box (e.g. 323 components, 57 passed, 31 edge, 62 solidity, 226 rough).
- Ground registration on DTM edges does not work at either site: Ferrybridge 3 of 36 windows ok,
  median (-4.17, +2.81) sd (3.5, 1.2); Upper Aire 14 of 96 ok, median (+0.63, +0.39) sd (2.6, 2.9).
- Synthetic check table. Null: slope 0.004 (dsm), 0.019 (dsmt), no lean. Forward projection with
  lean (-0.15, -0.25) (k 0.29): recovered slope (-0.075, -0.122), k 0.143, azimuth 211, i.e. 0.49 of
  truth; dsmt 0.166. Small lean (0.10, 0.05): recovered 0.05 to 0.064. Step-edge variant: 0.16 to
  0.17. The first synth2 variant (lean added to the DSM before matching) missed the lean at (-0.25,
  -0.5): dsm 0.024, dsmt 0.047 with `lean_present` False for dsm; why the forward variant was added
  is not documented.
- S0 stretch bins (share of terrain 3D area; share of faces): Ferrybridge 69.4 / 25.2 % in [1, 1.1),
  stretch over 2: 17.7 % of area, 166,317 faces; over 5: 6.3 % of area, 36,058 faces. Snettisham
  97.2 % in [1, 1.1), over 2: 0.61 % of area, 20,872 faces. Upper Aire histogram file is missing
  from `s0/`.

### `e4-results.md`

[`e4/out/kriging-variograms.json`, `krige-progress.log`, `pix-progress*.log`]

- Fitted point exponential covariance (sill m2, practical range m): Ferrybridge x2 6.28 / 27.3, x5
  7.08 / 53.6, x30 8.10 / 423. Upper Aire x2 1.7e5 / 1.6e6, x5 6.6e7 / 3.8e8, x30 4.6e7 / 1.1e8:
  degenerate fits (the DSM has a trend, not a stationary variogram), so Upper Aire kriging behaves
  as an almost linear trend interpolator. This is a trap the doc does not state.
- PixTransform run schedule: x2 and x5 about 6.6 min per site per guide for four tiles
  (about 100 s per tile), x30 about 43 to 60 min per site per guide. 18-run plan, executed in two
  scripts (`run_all.sh`, `run_all_2.sh`) that hard-code the torchenv path in
  `/tmp/claude-1000/.../3047c0e6.../scratchpad/torchenv/bin/python`.
- `scores.json` (172 entries, 232 KB) holds MedAE, NMAD and the slope-class and cover strata the
  doc says it computed; the doc prints none of them. The file stays (it is read by
  `e4b/m1/tables.py`).

### `offset-survey.md`

[/tmp session scratchpad `3809ac2d.../survey/*.log`, `box1.txt`] Add the 1 km candidate-box SW
corners in BNG, needed to rebuild the deleted stores: Dunster 299250, 143250 (500 m slice
299250, 143250 to 299750, 143750); Southend 587250, 185250 (TQ8585, aerial 2024); Snettisham
562250, 328250 (TF6025, aerial 2023); Loughborough 454250, 319250 (SK5015, aerial 2025); Neston
328250, 376250 (SJ2575, aerial 2024); Belford 408250, 641250 (NU0540, aerial 2023).

### `status.md`

- "Where to resume" item 2, "Next: C5 before/after strips from `c3c4`": C5 was done (see above);
  say so and point to the new C5 section. State that `lean2` npz, `c6/gate.py` and `s0b/lean.py`
  are needed for the open-ground re-check.
- Name the dependency of the e4b scripts on `scratch-archive/e4` so nobody cleans it up.

### `e4b-results.md` (after the E0 stage lands)

[`e0/e0.log`, `e0/probs.out`, `m1/tables.txt`, `m2score.out`, `s2check.out`] E0 is in progress and
its numbers are not in docs: token-probability heads Ferrybridge box accuracy 0.882 building F1
0.773, area accuracy 0.866 F1 0.733; Upper Aire box 0.954 F1 0.154, area 0.954 F1 0.786 (the box has
almost no buildings); `surfaces.py` gains (Ferrybridge x5 building 1.9, vegetation 0.5, 111
footprints; Upper Aire 0 footprints). `m1/tables.txt` (15 KB) is the complete method x site x factor
table (RMSE, NMAD, bld / tree / open, edge, cell residual); the doc quotes a subset. The S2 check
(`s2check.out`): x5 original 95 s and 90 s per training, RMSE 1.296 and 1.316, port 83 s and
1.317; x30 original-vs-port 0.517 and 0.564; cell residual max 0.100 original, 0.098 port. Some of
these are already in the doc as "0.344 vs 0.343": check before adding. All of this stays in `e4b/`,
which is kept.

## Reusable scripts to keep after the bulk data goes

| Script (absolute path under `/home/chris/xfeat_dev/satmesh/uncommitted/`) | Size | Why |
| --- | --- | --- |
| `scratch-archive/s0b/lean.py` (matcher, imported by lean2) | 7.8 KB | `lean2/fits.py` imports it |
| `scratch-archive/lean2/{fits.py, prep2.py, mkresults.py}` | 14.0 + 4.2 + 2.7 KB | re-score on open-ground truth; `prep2.py` rebuilds the npz |
| `scratch-archive/lean2/{*_results.json, *_obs.pkl, results.md, results_tables.md, progress.log}` | about 125 KB | saved observations and fits for re-check 1 |
| `scratch-archive/c6/{gate.py, progress.log, *_gate.json}` | about 9 KB | gate rerun on a new truth |
| `scratch-archive/c5/{analyse,build_page,common,consistency,ground_store,make_html,render,subjects,sheet*}.py`, `template.html`, `progress.log`, `work/*.json` | about 45 KB | C5 page generator and results |
| `scratch-archive/lean/{fit,lean,prep,search,search2,probe,s0b_xcheck}.py`, `progress.log`, `*_polys.json`, `boxes.json` | about 45 KB | first lean fit and the S0b cross-check |
| `scratch-archive/t0/*.py`, `cells_cover.json`, `offset-*.txt`, `progress.log` | about 25 KB | T0 helpers and truth |
| `scratch-archive/t1/{t1.py, dbg.py, *.json, progress.log}` | 92 KB | T1 experiment |
| `scratch-archive/s0_stretch.py`, `s0_views.py`, `s0b/{run,run_extra,synth2,summ,plot,scene,prep*}.py` | about 30 KB | E9 measurements |
| `scratch-archive/leanpage/{make_assets,make_page}.py` | 9.5 KB | lean review page |
| `scratch-archive/q/ov*.py` | 1.9 KB | scene polygon overlap |
| `scratch-archive/e4/*.py`, `vendor/`, `run_all*.sh` | about 70 KB | whole E4 trial; kept with the dir |
| `scratch-archive/c1c2/{c4_check,check_fit,check_roofs,live_c1,mkfixture,probe,record,trim}.py` (copied from the `6a248a7f` session scratchpad) | 13 KB | C4 UV check and the sources of the committed `esri-scenes-*.json` fixtures; the fixture JSONs `southend_query.json`, `southend_z19.json`, `ferrybridge_z18.json` were not copied (the committed fixtures hold them) |
| `scratch-archive/e2-survey/{aerial,b12,b13,b4,esri_poly,lidar_fetch,lidar_list,mi,mi_test}.py`, `{aerial_all,b12_slices,b13_all,build_all,full1km}.sh`, `box1.txt`, `rest.txt`, `full-main.py`, `full-README.md`, `full-status.md` (copied from the `3809ac2d` session scratchpad) | about 55 KB | E2 survey scripts and box list; `full-README.md` and `full-status.md` are old copies of the repo's README and status |
| `t0/ferrybridge-5km/{run.log, correction.json}`, `t0/{build.log, correct.log}`, `s0/*.s0.txt`, `s0/builds.log`, `e2b-lean/*/stats.json` | about 125 KB | small result files before bulk deletion |

## Items outside the repo scratch (from /tmp session scratchpads)

Listed because the brief asked for anything not recreatable from docs. These live in
`/tmp/claude-1000/-home-chris-xfeat-dev-satmesh/<session>/scratchpad` and vanish with /tmp.

- `6a248a7f-.../scratchpad/c4_check.py` (3.3 KB) and `c1c2/` (`check_fit.py`, `check_roofs.py`,
  `mkfixture.py`, `live_c1.py`, `probe.py`, `record.py`, `trim.py`, plus `southend_query.json`,
  `southend_z19.json` 374 KB, `ferrybridge_z18.json` 570 KB): the C4 UV check cited in
  `e2b-results.md` ("scratch `c4_check.py`") and the sources of the committed fixtures
  `esri-scenes-*.json`. Not recreatable from docs. Copy `c4_check.py` and `c1c2/*.py` (about 15 KB)
  into `scratch-archive/c1c2/` or into a doc before /tmp is cleared.
- `3809ac2d-.../scratchpad/survey/` (box logs and corners) and `full/` (`main.py`, `status.md` 11
  KB, `README.md`): E2 survey scripts (`aerial.py`, build logs). Corners are in the gap list above;
  the scripts are not.
- `07b5e904-.../scratchpad` (this session): `m1-research-a` 8.1 G and `m1-research-b` 2.5 G (venvs
  and weights) are recreatable from `m1-model-recipes.md`; `m1/run.sh` hard-codes these paths.
  `torchenv` (1.7 G) is recreatable from the command in `e4b-plan.md`. Small items: `align.py`,
  `make_crop.py`, `gf_check.py` (guided-filter check), `chm_find.py`, `chm_tiles.geojson` (57 MB,
  the CHMv2 global tile index, re-downloadable), `old-ref/` (6 pre-fix M1 npz, 5.7 MB; superseded),
  `crop90x5/`. `make_crop.py` reads `e4/ferry-inputs.npz` (another reason to keep e4).
- `26047419-...` is the original of `scratch-archive/{lean,lean2,leanpage,page,q,s0b,s0_*}`, a
  stale copy (its `lean2/progress.log` is shorter than the archived one): safe to delete.
- `3047c0e6-.../scratchpad/torchenv` is the interpreter named in `e4/run_all*.sh`.
- Other session folders (`7b0118d9` 3.4 G, `532d0073` 4.6 G, `f11fea70` 1.3 G, `91561170` 940 M,
  `6fb1fb7f` 441 M) were not audited (outside the brief).
