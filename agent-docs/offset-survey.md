---
status: historical
topic: position-correction
summary: Esri-to-EA aerial offset at eight English boxes: Esri is 0.2 to 2.8 m north of EA, east small, so the offset is regional, not one global shift
answers: How far is Esri imagery offset from EA aerial; Is the Esri offset a constant global shift; Where are the eight survey boxes and their BNG corners; What method measured the offset
---

# Esri-to-EA offset survey (E2)

Measured with `satmesh eval offset` (phase correlation, 256 px windows at 50 % overlap on a 0.25 m
BNG grid, windows kept above the null-response threshold). Positive east and north mean Esri is
displaced east and north of EA. Each box is the 500 m central slice of the 1 km candidate box,
except box 1 (full 1 km, see below). The stores are not kept; see Box corners to rebuild them.

## Conclusions

- Esri sits north of EA at every site with an interval clear of zero, but by 0.9 to 2.8 m, not a
  constant 0.8 to 1.0 m. Dunster (0.18 m, interval spans zero) and Loughborough (0.38 m, interval
  spans zero) show almost none, so the offset is regional or per tile, not one global shift.
- East is small and of either sign (-0.59 to +0.59 m).
- With the two Yorkshire sites (north 0.76 and 0.99 m), eight boxes give northward shifts of 0.2 to
  2.8 m; the largest (Snettisham 2.78 m) rests on 28 windows.

| Box | Place | EA capture | Esri zoom | East m (95 %) | North m (95 %) | Reliable windows |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Dunster, 1 km | 2020-02, 10 cm | 19 | -0.34 (-0.77, 0.06) | 0.18 (-0.55, 0.60) | 51 of 900 |
| 2 | Southend | 2024-06, 20 cm | 18 | 0.26 (0.15, 0.30) | 1.60 (1.44, 1.79) | 119 of 196 |
| 3 | Snettisham | 2023-10, 20 cm | 18 | -0.29 (-0.32, -0.19) | 2.78 (2.39, 3.03) | 28 of 196 |
| 4 | Loughborough | 2025-01, 20 cm | 18 | 0.59 (0.28, 0.87) | 0.38 (-0.09, 0.99) | 41 of 196 |
| 5 | Neston | 2024-07, 20 cm | 18 | 0.46 (0.34, 0.59) | 1.40 (1.34, 1.49) | 97 of 196 |
| 6 | Belford | 2023-09, 25 cm | 18 | -0.59 (-0.74, -0.55) | 0.94 (0.77, 1.08) | 71 of 196 |

## Box corners

BNG corners (E, N). The measurement box of each row is the 500 m slice from its slice corner
(E to E+500, N to N+500); box 1 was also measured over its 1 km box. The 1 km candidate boxes of
boxes 1 to 4 exist as measured boxes (SW corners below, aerial truth over 1 km in
`uncommitted/scratch-archive/e2-survey/full1km.sh`); boxes 5 and 6 were only ever 500 m slices,
so their "1 km SW corner" is the slice corner minus 250 m and was not used. "EA tile" is the
5 km EA lidar tile that covers the box. Scripts: `uncommitted/scratch-archive/e2-survey/`
(`build_all.sh` reads `box1.txt` and `rest.txt`, whose lines are `name E N`; `b12_slices.sh` and
`full1km.sh` hold the slice corners, zoom, tile and aerial year per box).

| Box | Place | Slice corner E, N | 1 km box SW corner | EA tile | EA aerial year |
| --- | --- | --- | --- | --- | --- |
| 1 | Dunster | 299250, 143250 | 299000, 143000 | SS9540 | 2020 |
| 2 | Southend | 587250, 185250 | 587000, 185000 | TQ8585 | 2024 |
| 3 | Snettisham | 562250, 328250 | 562000, 328000 | TF6025 | 2023 |
| 4 | Loughborough | 454250, 319250 | 454000, 319000 | SK5015 | 2025 |
| 5 | Neston | 328250, 376250 | none (not used) | SJ2575 | 2024 |
| 6 | Belford | 408250, 641250 | none (not used) | NU0540 | 2023 |

Rebuild a box store and GLB (the six GLBs in `uncommitted/offset-survey/` are not kept). The
current `satmesh build` takes `--nw` and `--se` as "LAT, LON", not BNG; the survey ran an earlier
CLI with `--bbox E N E N --crs EPSG:27700`, which no longer exists. Convert the slice with pyproj
(`Transformer.from_crs(27700, 4326, always_xy=True)`; NW is (E, N+500), SE is (E+500, N)), then,
from `pipeline/`, run `uv run satmesh build --nw "LAT, LON" --se "LAT, LON" --store DIR` and
`uv run satmesh export glb --store DIR --out FILE.glb`. Each box took about 1 to 3 minutes to
build plus the export. The converted corners (6 decimals):

| Box | `--nw` | `--se` |
| --- | --- | --- |
| 1 Dunster | 51.184068, -3.442903 | 51.179662, -3.435612 |
| 2 Southend | 51.539588, 0.698752 | 51.534931, 0.705687 |
| 3 Snettisham | 52.831866, 0.407004 | 52.827225, 0.414170 |
| 4 Loughborough | 52.772644, -1.197299 | 52.768100, -1.189971 |
| 5 Neston | 53.282862, -3.077626 | 53.278436, -3.070016 |
| 6 Belford | 55.669185, -1.870418 | 55.664684, -1.862485 |

## Traps

- The box 1 500 m slice produced no usable window (wooded, leaf-off against leaf-on, 5.4 years
  apart); the 1 km box gives 51 windows and an interval spanning zero.
- Boxes 3 and 4 have few reliable windows (flat fen farmland; town and floodplain), so their
  intervals are wide and their medians weak.
- Intervals reflect window sampling only.
- `find_aerial_tiles` returns neighbouring 5 km squares; the covering square comes from BNG
  arithmetic. Download sizes are not available before the download.
- Esri zoom was taken from the store build (finest zoom = leaf zoom + 2), z18 for boxes 2 to 6 and
  z19 for box 1.

## Not checked

- Whether the offset is smooth across a region (needs several boxes inside one region).
- Relief dependence at these sites (the object/open split of F6 checkpoint 3 was not run).
- Date gap effect: box 1's 5.4 years against 6 weeks at box 4 is confounded with the other
  differences between boxes.
