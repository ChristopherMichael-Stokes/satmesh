# PixTransform successor: proposal for the owner

Drafted 2026-10-30 from `pixtransform-survey.md`, `semantic-height-research.md`, `e4-results.md`
and a strong-tier design review. Nothing here has been run. Scores sit beside renders and never
decide alone (`e4b-plan.md` caveat). Claims tagged established cite the survey; unproven parts are
named as such under the research stance in `AGENTS.md`.

## Recommendation

Replace standalone PixTransform with a per-image correction of a masked height-model prior. Height
is a smooth ground surface from the coarse source plus a non-negative height above ground. That
height starts from the mean of the Geopose and RS3DAda predictions (CHMv2 for trees) and is set to
zero on ground and water. A small convolutional net, zero-initialised and fitted per area, learns a
bounded correction. A short projection step makes every coarse cell match the source.

This joins the PixTransform track and the anomaly track into one; the owner decides that scope.
Plain PixTransform and MMSR as published stay in as controls.

## Candidate designs

| Rank | Design | Guide branch sees | Coarse source enters as | Training |
| --- | --- | --- | --- | --- |
| 1 | Prior-anchored per-image correction | RGB; four class probabilities from the segmentation head, edges refined by a guided filter; the prior's height above ground; CHMv2; x, y | Ground surface d = smooth upsampling of (s - B(n)); h = d + n | Per area, self-supervised, minutes |
| 2 | Design 1's net pretrained with supervision on EA lidar, then fitted per tile | Same, plus 16 PCA channels of DINOv3-Sat features | Same; trained with real GLO-30 and with block means of lidar as sources | 1 to 3 GPU h per fold, then minutes per tile |
| 3 | MMSR (Dong et al., ECCV 2022) plus class-probability channels plus the cell adjustment | RGB plus class probabilities; 3 x 3 kernels with mutual modulation | Cycle L1 on the average-pooled output | Per image, about 1 min |

s = coarse cell means, B = mean over each cell, n = height above ground, h = final height.

### Design 1

- n = m * softplus(n_prior + delta). m = 1 - p_ground - p_water, soft and guided-filtered. EA low
  and medium vegetation, grass verges included, count as ground, otherwise the verges return.
- delta: four residual blocks of 3 x 3 convolutions, 32 channels, receptive field about 17 px. The
  last layer is zero-initialised (ControlNet pattern), so step 0 is the masked anomaly surface. The
  field stays small because the prior and the class map carry context.
- Loss, Huber throughout: (a) cell consistency on h; (b) ground smoothness, a second difference of d
  across coarse cells plus TV of h on ground pixels, the only term that says how tall raised objects
  are (cell-to-cell variation that smooth terrain cannot explain); (c) prior anchor on delta;
  (d) a small edge-aware TV on n.
- Procedure: Adam 1e-3, full-window passes, 1,500 steps, stop on a loss plateau; guide jitter of 0
  to 2 px per step; three seeds combined by median, with the spread shown on the review page.
- Exactness: the coarse-cell match comes from kriging coherence up to x10 and from iterative
  back-projection (h <- h + upsample(s - B(h))) where kriging is only approximate (x30). Report the
  largest cell residual and the 30 m edge-step ratio.
- Base: kriging is the general base (owner decision, `status.md`); the review text assumed a
  bilinear base and is corrected here.

## One trained model, per-image fit, or hybrid

| Route | Learns from | GPU cost (estimates, measured on the slice first) | Weakness |
| --- | --- | --- | --- |
| Per-image fit (design 1) | Coarse cells and the ground-smoothness assumption | 1 to 2 min per 540 m window per seed; about 2 to 3 h for three seeds over a 5.4 km area | Weak signal for object height at x30 on hilly ground |
| One supervised model | EA lidar, leave one area out over the three areas | Inputs about 1 to 3 h; training 20k steps on 256 px crops, 1 to 2 h per fold | Domain gap to Yemen (arid ground, mud-brick roofs, radar source) |
| Hybrid | Supervised start, then the design 1 loss per tile | Sum of both | Fine-tuning can undo the supervised gain; keep the anchor high |

Use the per-image fit for Yemen, where nothing supervised has seen the domain. Use supervision for
what cells cannot say: wall sharpness, roof shape, true height scale. Train on real GLO-30 over
England as well as on block means, because synthetic degradation transfers badly (Real-GDSR).
Supervised loss: Huber on height after the best shift within +-2 m (adapted from the PROBA-V cPSNR
idea, unproven for height) plus a gradient loss; augment with +-2 m shifts between guide and target.

## Combining with the height models and segmentation

| Option | Verdict |
| --- | --- |
| Height model output as the starting n, zero-initialised correction, ground and water forced to zero | Try first (design 1) |
| Height model output only as a guide channel, net starting from zero | Control |
| Per-class gain and offset on the prior, fitted by ground smoothness (2 to 4 numbers) | Cheapest stage (E0); targets the 1.4 to 8 m underestimate |
| DINO features as extra channels | Ablation only: NAIMA found plain addition worse than no semantics; the class map already distils DINO |
| LoD1 extrusion of building footprints after the fit | Fallback if roofs and walls stay rounded |

## Experiments, cheapest first

Each stage runs first on one 540 m slice. The owner's eye decides every stage.

| Stage | Runs | GPU time | Settles | By-eye pass |
| --- | --- | --- | --- | --- |
| E0 | Masked anomaly surface: kriging base, ground = 0, per-class gains fitted on the 540 m boxes at x5 and x30 | None (CPU, minutes) | Whether masks and gains alone fix verges, vehicle domes and the underestimate | Verges flat, no cell steps, building heights right against the lidar render |
| E1 | Design 1, three seeds, x5 and x30; ablations: no prior channel, no class map, no jitter | 15 to 30 min | Whether a per-image correction adds roof dimples and wall sharpness without printing texture | Roofs sharper than E0, verges flat, grey-on-grey buildings kept |
| E1c | Controls: MMSR as published plus the adjustment; PixTransform plus the adjustment (saved) | About 30 min | Whether the prior earns its place against a context-aware net without one | E1 clearly better, or the prior is dropped |
| E2 | Design 2 at x30 on the three areas, two sources (GLO-30, block means), with and without per-tile fitting | 3 to 6 h including inputs | Whether lidar supervision beats the per-image fit and whether GLO-30 hurts | Held-out area looks better than E1 |
| E3 | Best of E1 and E2 on one 5 km Yemen area | 1 to 3 h | Plausibility where no lidar exists | Towns and fields plausible, no cell grid visible |
| E4 | Full runs over the three areas | Owner approves hours first | Product decision | |

Needs: E0 and E1 need the segmentation head's maps (running now) and the saved Geopose and RS3DAda
predictions over each box; E2 needs those over the 5.4 km areas.

## Risks and what would change the plan

1. The prior caps quality: Geopose and RS3DAda round walls and ridges and lift vehicles into domes.
   If E1 looks no sharper than E0, stop the neural work and use footprint regularisation plus LoD1
   extrusion (`semantic-height-research.md`).
2. Object height is weakly determined at x30: terrain curvature at 30 m is as large as the cell mean
   of a building. If fitted gains swing between neighbouring windows, take the height scale from E2.
3. Yemen domain gap: mud-brick roofs on same-coloured ground is the extreme grey-on-grey case. If
   the Yemen masks fail in E3, an unmasked per-image fit (design 3) may win there, and
   Yemen-specific labels become a scope question. Design 3 ranks first if MMSR without the prior
   matches E1 by eye at x30.

## Established and unproven

Established (see `pixtransform-survey.md`): the 1 x 1 limits and texture copying (de Lutio 2019); a
convolutional per-image guide with a cycle loss (MMSR, tested at x4 and x8 on one dataset); residual
over the upsampled DSM (Real-GDSR); zero-initialised branch (ControlNet); jitter and TV in a
per-image fit (FeatUp); iterative back-projection (CMSR); source-consistency step (DADA); ground set
to zero and mask-select fusion (RS3DAda labels; UMEP and gloBFPr documentation); guided filter (He
2013); gradient loss and the harm of plain semantic addition (NAIMA, indoor and supervised); seed
ensembles (Lakshminarayanan 2017).

Unproven, named as such: a per-image fit anchored to a pretrained height prior; the
ground-smoothness term as the signal for object height; class-gated non-negative height inside a
guided upsampler; best-shift loss for height; supervised pretraining followed by per-tile fitting
under cell consistency; DINO channels in a per-image fit; anything at x30 or on GLO-30 (no method
has shown buildings formed from a 30 m radar DSM; Rafaeli et al. reach at most 18 % better than
SRTM).

Thin evidence: MMSR's gain over PixTransform rests on one dataset at x4 and x8; the feature evidence
is supervised and indoor; GPU-hour figures are estimates.

## E0 as specified for the first run

CPU only, on the two 540 m boxes at x5 and x30, with N the mean of Geopose and RS3DAda and a
kriging base; scratch in `uncommitted/e4b/e0/`.

1. Class probabilities per token from the land-cover head trained on the other two areas
   (leave-one-area-out), bilinearly upsampled to 1 m and refined with a per-class guided filter on
   the 1 m Esri guide (He et al. 2013), renormalised.
2. `e0m`: height masked by `p_building + p_vegetation`; heights under 0.5 m set to 0 (the UMEP
   vegetation threshold); then the anomaly recipe. The head's vegetation class includes low
   vegetation, so grass verges are partly vegetation.
3. `e0g`: `e0m` plus one global gain per class, chosen on a grid from 0.5 to 3.0 (step 0.1) to
   minimise the squared second differences of the coarse residual `s - B(N_masked)` over cells
   that are mostly ground and their neighbours (unproven); the oracle gain from regressing lidar
   nDSM on the masked N is diagnostic only.
4. `e0h`: `e0m` with each connected building component (`p_building > 0.5`) replaced by its median
   height, giving flat roofs and vertical walls (the cheapest first test of
   `semantic-height-research.md`).
5. Scored against the lidar classes (ground, building, tree), with edge slope, cell residuals,
   cell-edge step ratio, and the fraction of lidar-ground pixels more than 1 m above ground.
