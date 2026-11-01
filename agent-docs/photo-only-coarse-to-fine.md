---
status: current
topic: evaluation
summary: Coarse-to-fine place retrieval for a 10 km square, analysed on the cached Bexhill MegaLoc descriptors (8 frames, 1.5 km store): a 280 m coarse level with 6 headings, 5 heights and 2 pitches (1,800 cells against 44,880) keeps the truth place in the top 1 to 3 places for 7 to 8 frames within 250 m; the two-level search then finds it in the final top 6 for 8 of 8 frames with a median 20,160 cells described, 3,015 with a heading and height hint; a cost model for 100 km2 and what is not yet measured.
answers: How coarse can the first retrieval level be; how many places must level 1 keep; how large must the refinement radius be; how many views does a 10 km square need with and without hints; what does the hint save; what is not tested
---

# Coarse-to-fine place retrieval

Analysis 2026-11-01 on the cached descriptors of the two Bexhill grids (70 m spacing, 5 heights,
12 headings, pitch -35 and -50; `photo-only-megaloc-first-fix.md`), scripts
`uncommitted/photo-only/bexhill/scripts/coarse_to_fine.py` and `two_level.py`. Eight frames (f001,
f020, f040, f060, f075, f085, f090, f100), truth is the tracker's pose. Hierarchical retrieval is the
established shape (UAVD4L renders a database of poses and retrieves by global descriptor,
arXiv 2401.05971); the level sizes and the radius below are measured here, not published.

## Level 1 alone: frames of 8 with a top-K place near the truth

Success radius 250 m, K places 100 m or more apart (the store holds about 180 such places):

| Level 1 | Cells | K=1 | K=3 | K=5 |
| --- | ---: | ---: | ---: | ---: |
| 70 m, 12 headings, 5 heights, 2 pitches (flat) | 44,880 | 8 | 8 | 8 |
| 140 m, 6 headings | 5,940 | 8 | 8 | 8 |
| 280 m, 12 headings | 3,600 | 7 | 8 | 8 |
| 280 m, 6 headings | 1,800 | 7 | 8 | 8 |
| 280 m, 4 headings | 1,200 | 5 | 7 | 8 |
| 420 m, 6 headings | 720 | 6 | 6 | 6 |
| 560 m, 12 headings | 1,080 | 8 | 8 | 8 |

- With a 150 m radius, spacing above 140 m fails (280 m: 3 of 8): the nearest coarse view is up to
  200 m away and its descriptor no longer matches. The refinement radius must be about the coarse
  spacing: 250 m for a 280 m level.
- 420 m and 560 m rows are noisy and cannot be trusted in a store only 1.5 km across.
- Fewer heights (one or three) and one pitch cost one frame at most at 280 m.

## Two levels

Level 1 = 280 m, 6 headings, 5 heights, 2 pitches (1,800 cells in this store); the top K1 places
280 m
apart; level 2 = the 70 m cells within R of them, ranked, final top 6 places 100 m apart; success
is a
final place within 100 m of the truth:

| Setting | Truth in final top 6 | Cells described per frame (median) |
| --- | ---: | ---: |
| K1 5, R 250 m | 8 of 8 | 20,160 |
| K1 3, R 250 m | 8 of 8 | 13,320 |
| K1 10, R 250 m | 8 of 8 | 33,120 |
| K1 5, R 150 m | 7 of 8 | 9,000 |
| heading hint +-45 degrees | 7 of 8 | 4,995 |
| heading +-45 and heights 55 to 90 m | 8 of 8 | 3,015 |

Level 2 costs the same at any area: K1 times the cells inside a 250 m circle, not the store.

## Cost model for a 10 km square (100 km2; a 10 km2 area is 10 times less)

Unit costs from the end-to-end run: render 10 to 11 ms a view, describe 9.7 ms a view.

| Search | Views | Time |
| --- | ---: | ---: |
| Flat grid, 70 m, 12 headings, 5 heights, 2 pitches | about 48 million | about 260 hours |
| Level 1, 280 m, 6 headings, 5 heights, 2 pitches (1,000 views a km2) | about 100,000 | about 33 min once per area |
| Level 2 a frame, K1 3 to 10, R 250 m | 13,000 to 33,000 | 4.5 to 11 min |
| Level 2 a frame with a heading and height hint | about 3,000 | about 1 min |

- Level 1 is computed once and cached; level 2 can be cached for places that were visited.
- Not measured: the number of confusers in 100 km2 (80 times Bexhill) and so the K needed; recall
  was 8 of 8 only against about 180 places. The store build, store RAM (an earlier store of 961
leaves took 8 s
  and 5 GB to load; the Bexhill store has 12 leaves, RAM not measured; 100 km2 is about 670 leaves
at
  that density, so far-field levels of detail may be needed) and the lidar and imagery downloads
for 100 km2.
- Level 2 renders and describes on demand, which crosses two environments today (renders in the
  pipeline environment, MegaLoc in an `onnxruntime-gpu` one); a single environment would remove
  that.
