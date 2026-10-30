---
status: historical
topic: sources
summary: Probe of Esri World Imagery native depth at 38 sites: deepest zoom comes from layer 4 metadata, all UK sites reach z19 with 0.31 to 0.5 m source resolution
answers: What is the deepest Esri zoom at a given place; How do I detect the Esri no-data placeholder tile; What is Esri's native source resolution in the UK; How much are Esri z19 tiles oversampled
---

# S1 results: Esri World Imagery native depth

Probe: layer 4 (`Citations`) `identify` at a point, polygon with the highest `TO_CACHE_LEVEL`, then
the tile at that zoom and one deeper. Run 2026-10-25. At all 38 sites the deepest zoom is a real
tile and the next zoom is the "Map data not yet available" placeholder (2521 bytes, md5 prefix
`f27d9de7`), so zoom selection can come from metadata alone.

## UK (18 sites)

Every site reaches z19, about 0.15 to 0.19 m/px on the tile grid. Native `SRC_RES` is 0.31 to 0.5 m,
so the tiles are oversampled about 1.6 to 2.7 times. Capture dates range from 2020 to 2025.

| Site | Source | `SRC_RES` m | Date |
| --- | --- | --- | --- |
| London | Vivid Advanced | 0.31 | 2025-08 |
| Manchester | Vivid Advanced | 0.46 | 2020-04 |
| Norfolk fens | Vivid | 0.5 | 2023-06 |
| Peak District | Vivid | 0.34 | 2025-04 |
| Lake District | Vivid | 0.5 | 2025-05 |
| Cornwall coast | Vivid | 0.34 | 2025-09 |
| Northumberland | Vivid | 0.31 | 2021-04 |
| Edinburgh | Vivid Advanced | 0.5 | 2023-03 |
| Cairngorms | Vivid | 0.5 | 2021-06 |
| Assynt | Vivid | 0.34 | 2025-05 |
| Skye | Vivid | 0.5 | 2025-04 |
| Orkney | Vivid | 0.31 | 2024-03 |
| Shetland | Vivid | 0.5 | 2025-05 |
| Cardiff | Vivid Advanced | 0.5 | 2025-05 |
| Snowdonia | Vivid | 0.5 | 2025-08 |
| Mid Wales | Vivid | 0.5 | 2024-09 |
| Belfast | Vivid Advanced | 0.46 | 2025-04 |
| Sperrins | Vivid | 0.31 | 2024-09 |

## Other countries (20 sites)

| Site | Source | `SRC_RES` m | Max z |
| --- | --- | --- | --- |
| Berlin | Berlin2026 | 0.2 | 20 |
| Brandenburg (rural) | Brandenburg2019 | 0.2 | 20 |
| Denver | Vivid Premium | 0.34 | 20 |
| N. Dakota, Nevada, Paris, Massif Central, Brasilia, Nairobi, Canberra, Delhi, Tokyo | Vivid, Vivid Advanced | 0.31 to 0.5 | 19 |
| Turkana, Rajasthan, Hokkaido | Vivid | 0.34 | 18 |
| Mato Grosso, Outback, Sahara | Vivid | 0.31 to 0.34 | 17 |

- Layer 4 polygons carry their own cache-level ranges: Denver's 0.34 m source exists only at level
  20, and a 0.5 m source covers levels 12 to 19. Choose the polygon by `TO_CACHE_LEVEL`.
- `SRC_RES` overstates delivered detail where the cache stops at z17 or z18: those tiles are about
  1 m/px while `SRC_RES` reads 0.31 to 0.34 m.
- Tile GSD figures are computed from the Web Mercator formula, not measured.
