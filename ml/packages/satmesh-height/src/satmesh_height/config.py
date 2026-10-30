"""Training settings of PixTransform."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Published values: DEFAULT_PARAMS in prs-eth/PixTransform, pix_transform/pix_transform.py,
# commit 3db98d5 (keys in parentheses).
PUBLISHED_WEIGHT_DECAY_SPATIAL = 1e-4  # weights_regularizer[0]
PUBLISHED_WEIGHT_DECAY_COLOR = 1e-3  # weights_regularizer[1]
PUBLISHED_WEIGHT_DECAY_HEAD = 1e-3  # weights_regularizer[2]
PUBLISHED_LEARNING_RATE = 1e-3  # lr
PUBLISHED_STEPS = 1024 * 32  # iteration: optimiser steps, each on one batch of cells
PUBLISHED_BATCH_SIZE = 32  # batch_size, in coarse cells

type Loss = Literal["l1", "mse"]


class PixTransformConfig(BaseModel):
    """Settings of one PixTransform training run; the defaults are the published ones."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    weight_decay_spatial: float = Field(default=PUBLISHED_WEIGHT_DECAY_SPATIAL, ge=0)
    weight_decay_color: float = Field(default=PUBLISHED_WEIGHT_DECAY_COLOR, ge=0)
    weight_decay_head: float = Field(default=PUBLISHED_WEIGHT_DECAY_HEAD, ge=0)
    learning_rate: float = Field(default=PUBLISHED_LEARNING_RATE, gt=0)
    steps: int = Field(default=PUBLISHED_STEPS, gt=0)
    batch_size: int = Field(default=PUBLISHED_BATCH_SIZE, gt=0)
    loss: Loss = "l1"
    greyscale: bool = False
