---
status: current
topic: process
summary: Open risks and known limitations of the pipeline and the correction, with the evidence behind each.
answers: What can go wrong in the build; what is the Gazebo collision risk; what happens on DSM nodata or water; what are the memory limits of correct; which limits apply to large areas and the lean correction; what is untested
---

# Open risks

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
