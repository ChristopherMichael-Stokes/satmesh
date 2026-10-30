"""PixTransform guided refinement of a coarse raster (de Lutio et al., ICCV 2019).

Ported from prs-eth/PixTransform, pix_transform/pix_transform.py, commit 3db98d5, MIT licence
(LICENSE-PixTransform in the package root). The method is unchanged: normalise guide and source,
append x and y position channels, train the network so that the mean of its output over each
coarse cell matches that cell's source value (Adam, L1 or MSE), then predict the guide's full
grid and undo the source normalisation. Three changes remove size and overhead limits only:

- inference runs in row chunks (the net is per-pixel, so chunking is exact);
- training patches are indexed out of a view of the guide instead of being copied up front;
- batches come from a random permutation of the cells drawn on the device, without a DataLoader,
  and training length counts optimiser steps.
"""

from collections.abc import Iterator, Sequence

import numpy as np
import torch
from torch import nn

from satmesh_height.arrays import Float32Array, FloatArray
from satmesh_height.config import PixTransformConfig
from satmesh_height.net import POSITION_CHANNELS, PixTransformNet

POSITION_EXTENT = 0.5  # position channels span [-0.5, 0.5], as in the original
# 2048 float32 activations per pixel, about four alive at once: 2^16 pixels is about 2 GB
CHUNK_PIXELS = 2**16


def cell_patches(guide: torch.Tensor, factor: int) -> torch.Tensor:
    """View of `guide` (C, N, N) as (M, M, C, D, D); [i, j] is the D x D patch of cell (i, j).

    N = M * D with D = `factor`. The result shares memory with `guide`.
    """
    channels, rows, cols = guide.shape
    return guide.reshape(channels, rows // factor, factor, cols // factor, factor).permute(
        1, 3, 0, 2, 4
    )


def cell_batches(
    cell_count: int, batch_size: int, steps: int, generator: torch.Generator
) -> Iterator[torch.Tensor]:
    """Yield `steps` index batches over `cell_count` cells.

    Each pass over the cells uses a fresh random permutation; the last batch of a pass may be
    smaller than `batch_size`. The permutations are drawn on the generator's device.
    """
    yielded = 0
    while True:
        order = torch.randperm(cell_count, generator=generator, device=generator.device)
        for batch in order.split(batch_size):
            assert isinstance(batch, torch.Tensor)  # noqa: S101
            if yielded == steps:
                return
            yield batch
            yielded += 1


def prepare_guide(guide: FloatArray, *, greyscale: bool) -> FloatArray:
    """Normalise each channel to zero mean and unit variance and append the x, y channels.

    Position channel 0 varies along rows and channel 1 along columns (`indexing="ij"`).
    """
    if greyscale:
        guide = guide.mean(axis=0, keepdims=True)
    spread = guide.std(axis=(1, 2), keepdims=True)
    if np.any(spread == 0):
        message = "guide has a constant channel"
        raise ValueError(message)
    normalised = (guide - guide.mean(axis=(1, 2), keepdims=True)) / spread
    axis = np.linspace(-POSITION_EXTENT, POSITION_EXTENT, guide.shape[2])
    along_rows, along_cols = np.meshgrid(axis, axis, indexing="ij")
    return np.concatenate([normalised, along_rows[None], along_cols[None]], axis=0)


def initial_net(guide_channels: int, seed: int) -> PixTransformNet:
    """Network with weights drawn from `seed`, built on the CPU; global RNG state is untouched."""
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed)
        return PixTransformNet(guide_channels)


def _optimiser(net: PixTransformNet, config: PixTransformConfig) -> torch.optim.Adam:
    groups = [
        {"params": net.spatial_net.parameters(), "weight_decay": config.weight_decay_spatial},
        {"params": net.color_net.parameters(), "weight_decay": config.weight_decay_color},
        {"params": net.head_net.parameters(), "weight_decay": config.weight_decay_head},
    ]
    return torch.optim.Adam(groups, lr=config.learning_rate)


def train(
    guide: torch.Tensor,
    source: torch.Tensor,
    config: PixTransformConfig,
    seed: int,
) -> PixTransformNet:
    """Fit the network on `guide` (C + 2, N, N) and `source` (M, M), both normalised.

    Each step takes a batch of coarse cells, runs the net on their D x D guide patches and
    compares the mean of the output over each patch with the cell's source value.
    """
    cells_per_side = source.shape[0]
    factor = guide.shape[1] // cells_per_side
    device = guide.device
    net = initial_net(guide.shape[0] - POSITION_CHANNELS, seed).to(device)
    optimiser = _optimiser(net, config)
    loss_function: nn.Module = nn.L1Loss() if config.loss == "l1" else nn.MSELoss()
    patches = cell_patches(guide, factor)
    generator = torch.Generator(device=device)
    generator.manual_seed(seed)
    for cells in cell_batches(cells_per_side**2, config.batch_size, config.steps, generator):
        rows = torch.div(cells, cells_per_side, rounding_mode="floor")
        cols = cells % cells_per_side
        patch_mean = net(patches[rows, cols]).mean(dim=(2, 3))
        loss = loss_function(patch_mean, source[rows, cols].unsqueeze(1))
        optimiser.zero_grad()
        loss.backward()
        optimiser.step()
    return net


@torch.no_grad()
def predict(net: PixTransformNet, guide: torch.Tensor, chunk_rows: int) -> torch.Tensor:
    """Run `net` over `guide` (C + 2, N, N) in bands of `chunk_rows` rows; returns (N, N)."""
    bands = [
        net(guide[None, :, start : start + chunk_rows])
        for start in range(0, guide.shape[1], chunk_rows)
    ]
    return torch.cat(bands, dim=2)[0, 0]


def _check_shapes(source: FloatArray, guide: FloatArray) -> int:
    """Return the factor D with guide side N = M * D."""
    if source.ndim != 2 or source.shape[0] != source.shape[1]:  # noqa: PLR2004
        message = f"source must be square, got {source.shape}"
        raise ValueError(message)
    if guide.ndim != 3 or guide.shape[1] != guide.shape[2]:  # noqa: PLR2004
        message = f"guide must be (channels, N, N), got {guide.shape}"
        raise ValueError(message)
    cells_per_side = source.shape[0]
    side = int(guide.shape[1])
    if side % cells_per_side != 0:
        message = f"guide side {side} is not a multiple of source side {cells_per_side}"
        raise ValueError(message)
    return side // int(cells_per_side)


def refine(
    source: FloatArray,
    guide: FloatArray,
    config: PixTransformConfig,
    seed: int,
    device: torch.device,
) -> Float32Array:
    """Refine `source` (M, M) to the grid of `guide` (C, N, N), N = M * D, D = factor.

    The output has the guide's grid; its D x D cell means approximate the source only as well as
    the network fitted them (see `satmesh_height.composition` for exact variants).
    """
    _check_shapes(source, guide)
    source_mean = source.mean()
    source_spread = source.std()
    if source_spread == 0:
        message = "source is constant"
        raise ValueError(message)
    guide_tensor = (
        torch.from_numpy(prepare_guide(guide, greyscale=config.greyscale)).float().to(device)
    )
    source_tensor = torch.from_numpy((source - source_mean) / source_spread).float().to(device)
    net = train(guide_tensor, source_tensor, config, seed)
    chunk_rows = max(1, CHUNK_PIXELS // guide.shape[2])
    normalised = predict(net, guide_tensor, chunk_rows).cpu().numpy().astype(np.float64)
    return (source_mean + source_spread * normalised).astype(np.float32)


def refine_area(  # noqa: PLR0913
    source: FloatArray,
    guide: FloatArray,
    factor: int,
    training_extent_pixels: int,
    config: PixTransformConfig,
    *,
    seed: int,
    device: torch.device,
) -> Float32Array:
    """Refine an area window by window, each window trained on its own.

    `source` is (R, C) coarse cells, `guide` is (channels, R * factor, C * factor). Windows are
    squares of `training_extent_pixels` guide pixels, which must be a multiple of `factor` and
    divide both guide dimensions. Outputs are stitched into the area grid.
    """
    rows, cols = guide.shape[1:]
    if source.shape != (rows // factor, cols // factor) or rows % factor or cols % factor:
        message = f"guide {guide.shape[1:]} is not source {source.shape} times factor {factor}"
        raise ValueError(message)
    if training_extent_pixels % factor:
        message = (
            f"training extent {training_extent_pixels} px is not a multiple of factor {factor}"
        )
        raise ValueError(message)
    if rows % training_extent_pixels or cols % training_extent_pixels:
        message = (
            f"training extent {training_extent_pixels} px does not divide area {rows} x {cols} px"
        )
        raise ValueError(message)
    cells = training_extent_pixels // factor
    out = np.empty((rows, cols), np.float32)
    for top in range(0, rows, training_extent_pixels):
        for left in range(0, cols, training_extent_pixels):
            cell_window = (
                slice(top // factor, top // factor + cells),
                slice(left // factor, left // factor + cells),
            )
            pixel_window = (
                slice(top, top + training_extent_pixels),
                slice(left, left + training_extent_pixels),
            )
            out[pixel_window] = refine(
                source[cell_window], guide[:, *pixel_window], config, seed, device
            )
    return out


def ensemble(outputs: Sequence[Float32Array]) -> tuple[FloatArray, FloatArray]:
    """Per-pixel mean and population standard deviation (ddof = 0) over seeds."""
    if not outputs:
        message = "ensemble needs at least one output"
        raise ValueError(message)
    stack = np.stack(outputs).astype(np.float64)
    return stack.mean(axis=0), stack.std(axis=0)
