---
status: current
topic: evaluation
summary: Candidate real drone videos from England with open licences for use as a surrogate for
the owner's photos in `satmesh track`: Wikimedia Commons clips by one Bexhill-on-Sea uploader (CC
BY-SA 3.0, 4K, 2022 to 2024), Hergest Court and two East Sussex castles. Bexhill Cemetery is
downloaded and probed: 4K VP9 at 29.97 fps, 98 s, with a 1 Hz DJI telemetry track (GPS, height,
speeds) that the earlier search missed. Also the plan for the real-footage test and the
area-size scaling trial.
answers: Which open-licence drone videos of England could stand in for the owner's photos; where
were they filmed; what licences do they carry; is telemetry available; what was rejected and why;
what has to be checked before use; what the downloaded clip holds; what the real-footage test and the area-size trial consist of
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

## Next: the real-footage test and the area-size trial

Owner, 2026-10-31: build the map and test on this clip next; keep 4,096 keypoints on TensorRT; if
the first results look promising, find how far the area size can be pushed.

Test steps:

1. Frames at 1 to 2 a second from the 3840 x 2160 clip, in time order with consecutive names
   (file-name ordering has no gaps then); best range is frames 3 to 14 of the 5 s thumbnails
   (15 to 70 s), the whole clip is cut-free.
2. Parse `subs.vtt` to a table (time, longitude, latitude, satellites, distance from home, height
   above take-off, speeds). GPS is the start for `--start --radius-m 100` and a coarse track.
3. Store around 50.858 N, 0.4506 E: EA lidar surface (coverage of Bexhill to be confirmed) plus Esri
   imagery, then `satmesh correct`.
4. `satmesh track FRAMES --store DIR --start "50.8580, 0.4506" --radius-m 100` with the TensorRT
   default; read `review.html`.
5. Judge by eye on fixed frames, then compare the track and height with the telemetry (about 10 m
   horizontal, height is above take-off, not above the ellipsoid; no attitude is logged).

Expected trouble: a standard to moderately wide lens (about 80 degrees) with little distortion, so
k1 and k2 are weakly constrained; repetitive grave rows; shadows changing on the orbit; imagery and
lidar dates differ from January 2022; the 1 m mesh-error assumption is first measured here.

Area-size trial (proposed, not started; waits for the owner's go after the Bexhill result):
ladder Bexhill area, then 2.5, 5 and 10 km squares around it, each with a store build and a
`--start` run. Measure per rung, in this order of expected failure: scene load time and RAM (961
leaves took 8 s and 5 GB, RAM is the likely wall; far-field parent tiles are the fix), renderer
VRAM and render time, the store-wide first fix (about 7,800 renders for a slice-sized grid; needs
MegaLoc on the GPU, which has no TensorRT or CUDA path yet), and lost-track search cost (grows with
the square of the missed steps). Check accuracy against telemetry at each rung. Esri fetches at 30
requests/s; EA lidar is 100 to 500 MB per 5 km square.

Scratch for this work: footage and thumbnails in `uncommitted/photo-only/footage/bexhill-cemetery/`
(`Bexhill_Cemetery.webm`, `subs.vtt`, `thumbs/`); models in `uncommitted/models/xfeat-rt/`
(symlinks to both FP32 and FP16 exports; `XFEAT_MODEL_DIR` points there); TensorRT engines in
`~/.cache/xfeat-rt/tensorrt`.

## Candidates for held-out tests, found 2026-11-01

Found by a read-only search of Commons pages; no video was watched or downloaded. No page states
altitude, camera pitch, lens or telemetry. Latitudes and longitudes marked (memory) are unverified,
about 1 km. Owner wants clips with the horizon visible looking ahead, at least about 50 m above
ground, in places other than East Sussex; the owner reviews the list before any download.

| # | Clip (`commons.wikimedia.org/wiki/File:` ...) | Place | Licence | Length, size | Concern |
| --- | --- | --- | --- | --- | --- |
| 1 | `Hergest_Court,_Swydd_Henffordd_-_Herefordshire,_England.webm` (YouTube TLrkaTgnIGM) | Kington, Herefordshire, 52.192325, -3.052707 (page) | CC BY 3.0 | 174 s, 3840x2160, 281 MB | edited montage with cuts and music |
| 2 | `Kenilworth_Castle_drone_Footage_.webm` (YouTube hV33SeFzBdg) | Kenilworth, about 52.348, -1.583 (memory) | CC BY 3.0, reviewed 2023-05-30 | 65 s, 3840x2026, 96 MB | castle-centred, possible orbit |
| 3 | `Penshaw_Monument_Autumn_Sunset.webm` (Vimeo 195281590) | Penshaw Hill, Sunderland, about 54.856, -1.523 (memory) | CC BY 3.0 | 73 s, 1920x1080, 12 MB | sunset grade, low bitrate |
| 4 | `Old_Sarum_Salisbury_drone_footage.webm` (YouTube lcoUa0BjUgY) | Old Sarum, about 51.093, -1.801 (memory) | CC BY 3.0, page says licence review needed | 102 s, 1920x1080, 91 MB | check YouTube shows CC BY; likely an orbit |
| 5 | `Exmoor_ponies_(Equus_ferus_caballus)_in_Somerset.webm` | Mendip near Shipham, about 51.32, -2.82 (memory) | CC BY 3.0 | 88 s, 1920x1080, 33 MB | cut sections, probably low |
| 6 | `Drone_footage_of_St_James'_Church,_Seacroft.webm` (earlier list) | Leeds | CC0 | 94 s, 1080p | Phantom-style wide lens; backup |

- Outside England, if needed: `Edinburgh_Aerial.webm` (CC BY-SA 4.0, 90 s, 1080p, Scotland, so
  no EA lidar; the page does not say drone) and `Mynydd_Parys.webm` (CC BY-SA 4.0, 91 s, 1080p,
  Anglesey, Welsh lidar).
- Rejected this pass: Royal Sovereign Lighthouse (sea only), Stanton Drew and Ashen Hill Barrow
  (640x480), Liverpool city tour (not stated as drone), foreign clips, Co-Curate South Shields
  (Standard YouTube Licence), the East Sussex cluster (Bexhill, Pevensey, Herstmonceux, Northeye),
  an Eastern Bay Link clip (720p, OGL), an AFC Bournemouth FPV interior clip, the University of
  Edinburgh stock clips (8 to 30 s).
- Searches that found nothing: Internet Archive and stock sites (commercial only); Zenodo and
  Kaggle drone video with DJI SRT in the UK (Kaggle `kmader/drone-videos` page not opened,
  Sheffield ORDA record gave HTTP 403); UAV geo-localisation datasets (UAV-VisLoc is China);
  Flickr; YouTube Creative Commons filter (not searchable from the agent); councils, universities
  and the Environment Agency (still photos only). Commons "Drone videos from England" holds 35
  files, 15 of them Bexhill or Pevensey.
- Telemetry: none stated anywhere. Truth would be the start location, or `.SRT` files if the
  uploaders supply them.

## Downloaded for held-out tests (2026-11-02)

Owner approved Old Sarum and Kenilworth ("okay, not great"), Hergest Court, and Penshaw from 38 s.
Each is `uncommitted/photo-only/footage/NAME/clip.webm` with a contact sheet `sheet.jpg`; sizes match
Commons, licences read from the Commons API (all CC BY 3.0). No telemetry or subtitles in any.

| Directory | Clip | Probe | What the sheet shows |
| --- | --- | --- | --- |
| `kenilworth/` | Kenilworth Castle | 65 s, 3840 x 2026, 23.976 fps, 100.6 MB | one castle circled and descending; horizon in the first 10 s, then pitched 30 to 45 degrees down; no cuts; probably under 50 m for much of it |
| `old-sarum/` | Old Sarum | 102 s, 1920 x 1080, 50 fps, 95.7 MB | continuous orbit of the earthworks; horizon and a distant town for the first 40 s, then lower and steeper; no cuts |
| `hergest-court/` | Hergest Court | 173.6 s, 3840 x 2160, 29.97 fps, 295 MB | cut montage of one farm from several heights; a title card at the start and end (cut them); a clean horizon section at about 80 to 100 s; the continuous oblique runs last 25 to 50 s |
| `penshaw/` | Penshaw Monument | 72.7 s, 1920 x 1080, 25 fps, 13 MB | 0 to 14 s close pass silhouetted on the sun, 14 to 38 s sun-facing swings, usable from about 38 s: wide view, camera high and backing away, 10 to 20 degrees down, horizon in the upper third, dark low-contrast ground |

- Roles (`decisions.md`, 2026-11-02): Hergest Court is sealed (frozen settings, one run, stretches
  chosen beforehand); the other three are development clips.
- Start locations from the pages or memory, unverified to about 1 km: Kenilworth 52.348, -1.583;
  Old Sarum 51.093, -1.801; Penshaw 54.856, -1.523; Hergest Court from its Commons page.
- Stores for these areas are approved but not built; EA lidar coverage is unchecked.
