# External note on image-guided DSM super-resolution

Supplied by the owner on 2026-10-30; source and author unknown, claims unverified. Input to the
PixTransform return survey, not a plan.

## Claims

- PixTransform maps [R, G, B, x, y] to height with 1 x 1 convolutions, so it has no spatial
  receptive field; a larger guide adds observations, not context.
- Supervised alternative: dual-encoder CNN (optical encoder, coarse-DSM encoder, fusion, U-Net-style
  multi-scale decoder) predicting a residual over the upsampled coarse DSM, trained on paired
  imagery and high-resolution lidar degraded to coarse (0.25 m to 2 m, 0.5 m to 2 m or 4 m, 1 m to 5
  m).
- Degradation should imitate the real lidar pipeline (binning, mean or maximum aggregation, ground
  classification, interpolation, noise) and include random registration offsets and elevation noise.
- Loss: lambda1 L_HR + lambda2 L_LR (downsampled prediction against the coarse source) + lambda3
  L_gradient, plus smoothness, edge-preservation and range terms.
- Hybrid: pretrain on many areas, then fine-tune on the target area under the low-resolution
  consistency loss (test-time adaptation).
- Other directions named: multi-modal convolutional parameterisation network (MCPN,
  <https://www.mdpi.com/2313-433X/10/3/69>, not opened), diffusion reconstruction with consistency
  constraints, point-cloud upsampling.
- Proposed experiments: bicubic, PixTransform, a plain CNN and the dual-encoder CNN on held-out
  geographic areas; generalisation to an unseen area; pretrained against locally fine-tuned; several
  input resolutions and factors. Metrics: RMSE, MAE, building-edge position, roof geometry,
  roughness, artefact frequency, consistency with the coarse source.

## Check against the project's own record

- PixTransform architecture claim: confirmed in the ported code (`satmesh_height.net`).
- Supervised dual-encoder, pretrain-then-adapt, diffusion: already surveyed in `e4-research.md`
  (DADA, Real-GDSR, Elevate) and `e4-research-2.md` (Prior2DSM, Rafaeli et al.); planned as M3 and
  M4 in `e4b-plan.md`.
- Not addressed by the note: roof lean and capture-date differences between Esri imagery and lidar,
  and the domain gap from block-averaged lidar to real GLO-30.
- MCPN: citation unverified.
