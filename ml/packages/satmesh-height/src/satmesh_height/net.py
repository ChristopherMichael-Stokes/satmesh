"""The PixTransform network (de Lutio et al., ICCV 2019).

Ported from prs-eth/PixTransform, pix_transform/pix_transform_net.py, commit 3db98d5, MIT licence
(LICENSE-PixTransform in the package root).
"""

from typing import override

import torch
from torch import nn

POSITION_CHANNELS = 2  # x, y; always the last two input channels
BRANCH_WIDTH = 32
FEATURE_WIDTH = 2048


def _branch(in_channels: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(in_channels, BRANCH_WIDTH, kernel_size=1),
        nn.ReLU(),
        nn.Conv2d(BRANCH_WIDTH, FEATURE_WIDTH, kernel_size=1),
    )


class PixTransformNet(nn.Module):
    """Per-pixel map from guide colour and image position to height.

    Every convolution is 1 x 1, so each output pixel depends on its own input pixel only. Input is
    (batch, guide_channels + 2, rows, cols) with the position channels last; output is
    (batch, 1, rows, cols). The two branch outputs are summed before the head.
    """

    def __init__(self, guide_channels: int) -> None:
        """Build a net for a guide with `guide_channels` colour channels."""
        super().__init__()
        self.guide_channels = guide_channels
        self.spatial_net = _branch(POSITION_CHANNELS)
        self.color_net = _branch(guide_channels)
        self.head_net = nn.Sequential(
            nn.ReLU(),
            nn.Conv2d(FEATURE_WIDTH, BRANCH_WIDTH, kernel_size=1),
            nn.ReLU(),
            nn.Conv2d(BRANCH_WIDTH, 1, kernel_size=1),
        )

    @override
    # torch types Module.forward as a callable attribute, which a method cannot override
    def forward(self, features: torch.Tensor) -> torch.Tensor:  # ty: ignore[invalid-mutable-override]
        """Predict normalised height for each pixel of `features`."""
        color = features[:, : self.guide_channels]
        position = features[:, self.guide_channels :]
        height = self.head_net(self.spatial_net(position) + self.color_net(color))
        assert isinstance(height, torch.Tensor)  # noqa: S101
        return height
