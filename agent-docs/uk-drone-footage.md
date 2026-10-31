---
status: current
topic: evaluation
summary: Candidate real drone videos from England with open licences for use as a surrogate for
the owner's photos in `satmesh track`: Wikimedia Commons clips by one Bexhill-on-Sea uploader (CC
BY-SA 3.0, 4K, 2022 to 2024), Hergest Court and two East Sussex castles. Bexhill Cemetery is
downloaded and probed: 4K VP9 at 29.97 fps, 98 s, with a 1 Hz DJI telemetry track (GPS, height,
speeds) that the earlier search missed.
answers: Which open-licence drone videos of England could stand in for the owner's photos; where
were they filmed; what licences do they carry; is telemetry available; what was rejected and why;
what has to be checked before use; what the downloaded clip holds
---

# UK drone footage candidates

Search of 2026-10-31 by a research subagent (web search and page reading only; no file was
downloaded
and no video viewed). Licence, duration, resolution and date were read on the Wikimedia Commons file
pages; coordinates marked "page" are the uploader's, the others are from memory (about 1 km).
Purpose: frames (1 to 2 a second) for `satmesh track`, then a mesh of the area to compare with.

## Best set: Bexhill-on-Sea, East Sussex (Commons user Dr-Mx, Alexis Markwick)

All CC BY-SA 3.0 (attribution "Alexis Markwick (Dr-Mx), CC BY-SA 3.0", derivatives share-alike), 4K,
VP9 WebM. One mesh tile covering Bexhill to Pevensey to Herstmonceux serves the whole cluster.

| Clip | Where (lat, lon) | Length, date | Note |
| --- | --- | --- | --- |
| Bexhill Cemetery | 50.8603, 0.4492 (page) | 98 s, 2022-01-14 | Cemetery and houses |
| Pastures, Clavering Walk | 50.8378, 0.4235 (page) | 96 s, 2022-05-18 | Farmland now a housing estate: the imagery may predate it |
| Bexhill Down | 50.8473, 0.4616 (page) | 61 s, 2022-01-14 | Common and houses |
| BMX and Skate Park, Sidley | 50.8537, 0.4679 (page) | 82 s, 2022-06-22 | Suburban |
| Egerton Park | 50.8379, 0.4656 (page) | 95 s, 2024-09-04 | Titled "pan", described as a fly-through |
| Abnormal Load, Little Common Road | 50.8457, 0.4682 (page) | 174 s, 2022-03-20 | Follows a lorry convoy, possibly forward flight |
| Northeye Campus | 50.8486, 0.4101 (page) | 48 s, 2022-02-26 | Short |

Files are under `commons.wikimedia.org/wiki/File:` with the names `Bexhill_Cemetery.webm`,
`Pastures,_Clavering_Walk,_Bexhill.webm`, `Bexhill_Down.webm` and so on.

## Others worth a look

| Clip | Where | Licence | Length | Risk |
| --- | --- | --- | --- | --- |
| Hergest Court, Kington, Herefordshire | 52.1923, -3.0527 (page) | CC BY 3.0 (from "Drones Over Wales") | 174 s, 4K, 2023-05-15 | Edited montage, music |
| Pevensey Castle, inner bailey | about 50.8185, 0.3374 | CC BY 3.0 ("Beautiful Landmarks") | 227 s, 4K, 2016 | Castle-centred, probable orbit and cuts |
| Herstmonceux Castle | about 50.8890, 0.3466 | CC BY 3.0 (same) | 180 s, 3840x2026, 2016 | Promo edit |
| St James' Church, Seacroft, Leeds | about 53.83, -1.46 | CC0 | 94 s, 1080p, 2016 | Phantom standard (wide lens), old |
| Old Sarum, Salisbury | about 51.0928, -1.8014 | CC BY 3.0, licence not yet reviewed | 102 s, 1080p, 2019 | Unreviewed licence |

Wales (open Welsh lidar): Ceinewydd (New Quay), Aberaeron and Lavister clips by Llywelyn2000, CC
BY-SA
4.0, 4K, 2024, with music tracks.

## Telemetry

None published for any candidate. Three Bexhill pages show DJI file names (`DJI_0331.MP4`,
`DJI_0366.MP4`,
`DJI_0291.MP4`), a DJI consumer drone. The uploader gives one object and one camera point per
clip: a sanity check to 1 to 2 km, not a pose. Real telemetry (SRT files) would have to be asked
from the
uploaders. A Kaggle set `kmader/drone-videos` with SRT files and Scottish clips, licence reported as
CC BY-NC-SA 4.0, was not opened.

## Rejected

Wells Cathedral and Chew Valley Lake (640 x 480), Stonehenge at Sunrise (interlaced, TV edit),
Exeter
Rowing Club (miniature effect), Solent Flyer (sea), the Bexhill clock tower (not a drone shot), the
Bexhill "pan" and Galley Hill clips (rotations on the spot), Pexels, Pixabay and Videvo (own
licences, vague places), Co-Curate Newcastle (YouTube standard licence), Historic England and
Environment Agency (no open drone video found).

## To check before use

Cuts, pitch, height above ground, lens (a Phantom-style wide lens breaks the lens model beyond
about 110 degrees), grading and frame rate (`ffprobe`; not on any page). YouTube licences could not
be verified, so only Commons is relied on. First step: download Bexhill Cemetery and Bexhill Down,
extract frames, look at them, and build a store of the area (Environment Agency lidar covers
Bexhill).

## Downloaded: Bexhill Cemetery (2026-10-31)

`uncommitted/photo-only/footage/bexhill-cemetery/Bexhill_Cemetery.webm`, 1,845,634,522 bytes (the
size Commons lists), CC BY-SA 3.0, Alexis Markwick (Dr-Mx), filmed 2022-01-14.

- ffprobe: VP9, 3840 x 2160, 29.97 fps, progressive, bt709, 98.0 s, 150 Mbit/s, a WebVTT stream.
- The WebVTT stream (`subs.vtt`, 98 lines) is DJI telemetry once a second: `F/2.8, SS, ISO, EV,
  DZOOM, GPS (longitude, latitude, satellites), D (distance from home, m), H (height above the
  take-off point, m), H.S and V.S (horizontal and vertical speed, m/s)`. First line: GPS (0.4506,
  50.8580), H 72.4 m. GPS has 4 decimals (about 11 m east-west, 7 m north-south), so it gives a
  start position for `--start` and a coarse track, not a pose. No attitude is recorded.
- 19 frames at one every 5 s are in `thumbs/`, judged by a research agent: one continuous shot, no
  cuts, overlays or horizon; all frames oblique (about 30 to 55 degrees), medium to high; forward
  flight and descent toward the chapel (frames 1 to 6), an arc past it (6 to 10), an orbit around it
  (10 to 14), a slow pull-back (14 to 19); little visible lens distortion, a standard to moderately
  wide lens (about 80 degrees, not fisheye), so distortion is weakly constrained. Best frames 3 to 14.
  Shadows change fast on the orbit and the grave rows repeat.
- Next: pick frames (1 to 2 a second), build the store for the area (EA lidar covers Bexhill), run
  `satmesh track` with `--start` from the telemetry.
