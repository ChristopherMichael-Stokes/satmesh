---
status: current
topic: baseline-pipeline
summary: Plan for texture refinement of the Esri imagery: fixed views and an EA check first, then seam and colour measurement, classical sharpening behind a consistency gate, and one generic super-resolution model as an unproven side-by-side; multi-capture compositing deferred. Awaiting the owner.
answers: What is the plan for sharpening and harmonising the texture; what prior art and tools exist; where does a texture pass plug into the store; which stages come first and what each settles; which forks wait for the owner; what was deferred and why
---

# Texture refinement plan

Drafted 2026-10-31 from a prior-art survey, a repo inventory and an independent design review.
Owner order: texture refinement is next, E2 is parked, no long training runs (`decisions.md`).
Nothing is built. Reading is by eye on fixed views against the 10 cm England aerial (EA); scores
never decide.

## Starting facts

- Esri/EA spectral power at Upper Aire: 0.51, 0.31, 0.46, 0.46 in the bands 0.25 to 0.5, 0.5 to 1,
  1 to 1.5 and 1.5 to 2.85 cycles/m; Esri has nothing above 2.85. Part of the gap is date change
  (`s6-results.md`, `f6-results.md`).
- Esri's processing chain is not documented. The Vantor imagery is probably already sharpened and
  resampled, so a second deconvolution may add only halos. Unverified.
- No pretrained remote-sensing SR model with released weights takes 0.3 m RGB: SEN2SR, LDSR-S2,
  SatlasSuperRes and SR4RS take Sentinel-2 at 10 m. Generic Real-ESRGAN x4plus (BSD-3) and SwinIR
  real-SR (Apache-2.0) apply, as GANs trained on photographs, with hallucination risk.
- No established method super-resolves from a few dated captures with unknown registration.
  Co-registration (AROSICS, Apache-2.0) plus median or best-pixel compositing cleans an image and
  does not sharpen it.
- Esri's scene query returns one capture per point. Dated releases (Wayback) were never checked.
  Cached scenes at z19: Ferrybridge 4, Upper Aire 2, Southend 2.
- No published study isolates whether SR helps keypoint matching on aerial orthophotos.
- Texture exists only inside each node's GLB as a JPEG (quality 92). `correct` already rewrites
  UVs only (`glb.py` `with_texture_coordinates`, `correction.py` `apply_correction`). Parents are
  2x2 means of their children, built in memory (`tiler.py`).
- `consistency(enhanced, source)` in `satmesh_eval` has no caller. `eval texture` compares live
  Esri with EA only. `render_luma` renders store textures top-down.
- Cached EA 10 cm ECW tiles: Ferrybridge area and Dunster (2020). Others are 0.2 to 0.25 m. The
  Upper Aire tile is not cached. Crops need the `satmesh-gdal-ecw` image.

## Stages

| Stage | Work | Settles | Cost |
| --- | --- | --- | --- |
| 1 | 4 to 6 fixed crops in one box with a cached EA tile: Esri as built, EA degraded to the Esri ground sample distance, EA at 10 cm, A/B blink, consistency readout. A degrade-and-restore check (Wald protocol) runs as a halo and ringing detector only | Whether any change can be judged by eye; whether degraded EA matches Esri's spectrum in 0.5 to 2.85 cycles/m (if not, the degradation model is wrong) | half a day |
| 2 | Measure seams and colour: mean and standard deviation across adjacent leaf textures in a strip each side of the seam; per-band histograms across Esri scene boundaries | Whether harmonisation is a real problem. Drop it if the mismatch is invisible on the views; otherwise `skimage` `match_histograms` to a reference scene plus feathering, multi-band blending only if feathering leaves seams | half a day |
| 3 | Classical sharpening at native size, then 2x upsampling: unsharp mask and Wiener or Richardson-Lucy with a small Gaussian PSF (`skimage`). Gates: the consistency check passes and no halo shows on roof lines and road paint | Whether any headroom exists. Halos at low strength confirm vendor sharpening and cap the gain | one day |
| 4 | One generic SR model, inference only, one box, labelled unproven: Real-ESRGAN x4plus or SwinIR real-SR, output reduced to 2x, same views and gate | Whether SR adds believable detail or invents it | half a day of GPU |
| 5 | Review page for the owner. Nothing changes `build` before it | The go or no-go | |

The pass is store-wide and reversible, modelled on `apply_correction`: `satmesh texture --store DIR`
on a copy or a slice, with the original JPEG kept. It needs a new `with_texture_image` next to
`with_texture_coordinates` and must rebuild parents from the processed leaves with the same 2x2
mean. A sharpening kernel at a tile edge needs neighbour pixels, so a leaf is processed with a
margin read from its neighbours.

## Deferred

- Multi-capture compositing, Wayback, NAIP and AROSICS: Esri exposes one capture per point, so they
  need new sources. Moves ahead of SR if a Wayback listing for one box shows three or more
  distinct capture dates.
- SR fine-tuning on our own pairs: no long training now, and no evidence yet that classical and
  generic methods fall short.
- opensr-test: built around Sentinel-2, 3x scale unverified.
- Keypoint-inlier checks against real photos: after camera renders exist; count inliers after
  geometric verification, not raw matches.
- IR-MAD: only if stage 2 shows differences `match_histograms` cannot fix.

## Risks

- The gain may be near zero if Esri is already sharpened. The views show this within one to two
  days.
- Degraded EA is not a valid proxy for Esri (JPEG compression, vendor sharpening, unknown PSF), so
  the harness cannot rank methods.
- SR can invent ground features the visibility check is meant to confirm.
- The Esri and EA dates differ; the Ferrybridge Esri date is unchecked.

## Forks for the owner

1. New dependencies: Real-ESRGAN or SwinIR code and weights in `ml/` (stage 4);
   `opencv-python` for multi-band blending (only if feathering fails).
2. Whether leaf textures may grow from 1,024 to 2,048 px (store size, Gazebo and CesiumJS memory).
3. Whether SR output is acceptable at all for the visibility check.
4. Whether `build` gets the step and whether it is on by default (decided after stage 5).
5. New imagery sources (Wayback, NAIP).
