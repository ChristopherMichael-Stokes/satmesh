---
status: current
topic: process
summary: Open risks and known limitations of the pipeline and the correction, with the evidence behind each.
answers: What can go wrong in the build; what is the Gazebo collision risk; what happens on DSM nodata or water; what are the memory limits of correct; which limits apply to large areas and the lean correction; what is untested
---

# Open risks

- Outside England the surface is 30 m data (GLO-30): buildings and trees are absent and FABDEM
  leaves residual building bumps in dense towns (RMSE about 2.7 m in built-up terrain). Imagery
  position is bounded only by Esri's stated 4 to 12 m accuracy, with no correction (needs lidar).
- US builds (`regions-r1-results.md`): the DSM is the highest first return per 1 m cell, so cells
  with no return (glass, water, shadowed courtyards; up to 29 % of a Denver leaf) show the ground
  and the lidar year differs from the Esri capture date. A listed 1 m DEM tile can be all nodata
  (New Mexico) and falls through to the ImageServer or the 1/3 arc-second COGs. The TNM API
  sometimes answers 200 with an error body. Imagery position is bounded only by Esri's stated
  8.47 m; `correct` is England only. Exporters do not yet carry the USGS attribution or
  `elevation_provenance`. Alaska and Hawaii have no registry entry.
- FABDEM is non-commercial (CC BY-NC-SA 4.0); a commercial use needs Fathom or GEDTM30.
- Zip reads for FABDEM have no retry; the `N51W001` member name did not resolve (`regions-results.md`).
- Node records written before the region work use `origin_odn_height_m`; the exporters cannot read
  those stores until they are rebuilt or their keys renamed.
- Lean-biased truth (`metric-bias-audit.md`, 2026-10-30): the Esri-to-EA-aerial truth used for every
  position and lean fit is a median over all windows, roofs included, so lean pulls it south;
  against a 12-window open-ground truth at Southend the C6 refit would pass and the north
  overshoot shrinks. Unverified until an open-ground truth with more windows is measured. The
  re-check reads `uncommitted/scratch-archive/lean2/{southend_t,ferry_t}.npz`, `*_obs.pkl` and
  `fits.py`, `c6/gate.py` and `s0b/lean.py`; keep them.
- `correct` memory: about 2 GB per worker, 8 workers at most, all cells' lidar points held at
  once; a many-km area needs a bounded reader.
- Crown and roof-edge fidelity against the lidar is traded for a smooth look (see the 0.5 m sampling
  decision); E8 tried three ways of recovering it and the owner rejected all three by eye.
- Gazebo collision uses the visual (DSM) mesh until F5b: robots would collide with canopies.
- DSM nodata (water, survey edges) raises and stops the build; untested on such a box.
- Esri imagery sits 0.2 to 2.8 m north of EA imagery across eight England boxes (F6 checkpoint 2,
  `offset-survey.md`; S6's 2.4 m was a Helmert-reprojection artifact), and raised objects are
  displaced differently from open ground, so a rigid correction will not do; matching pipelines
  will see it.
- Esri imagery is not a true orthophoto at Worcester (the location of the S0b boxes is unverified,
  see `e2b-results.md` "Lean fit at four sites"; roofs displaced about 0.3 to 0.6 m per m of height
  toward south-west; S0b, `e9-results.md`); undetermined at the survey sites, so buildings can lean
  in the texture and the position correction does not remove it.
- No ground-truth scoring yet: DEM, texture and geoid chain are untested against raw lidar and
  EA aerial imagery.
- Gazebo untested: roll pose for glTF, `elevation` datum (gz-math treats it as ellipsoidal),
  levels, mesh collision cost, tile-count and VRAM limits.
- Large areas: parents past about 6 km need a DTM fetch not yet tried (WCS tested to 6000 x 6000
  px); a 20 km box is about 198,000 Esri tiles, about 55 h at 1 request/s.
- Texture seam lines were wrap-around sampling, fixed with a clamp sampler (2026-10-25). Geometric
  cracks between tiles are hidden by skirts, not removed; not seen in renders since the fix.
- `sources_at` is not cached, so a cached rerun still makes one identify request.
- Wales and Scotland have no EA DTM; zoom comes from sources at the area centre only.
