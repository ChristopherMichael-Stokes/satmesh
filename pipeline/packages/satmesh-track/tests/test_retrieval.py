import os
from pathlib import Path

import numpy as np
import pytest
import scene

from satmesh_eval.perspective import render
from satmesh_track.retrieval import DESCRIPTOR_SIZE, MegaLocDescriber

MODEL_VARIABLE = "MEGALOC_MODEL"
UNIT_TOLERANCE = 1e-4  # float32 arithmetic through a transformer
BATCH_TOLERANCE = 1e-3  # batch composition changes float32 summation order


@pytest.mark.skipif(MODEL_VARIABLE not in os.environ, reason=f"{MODEL_VARIABLE} not set")
def test_descriptors_are_unit_length_and_do_not_depend_on_the_batch() -> None:
    describer = MegaLocDescriber(Path(os.environ[MODEL_VARIABLE]), batch_size=2)
    images = [
        render(scene.town(), scene.pinhole(), scene.pose_at(x, y, 0.0), scene.MAX_RANGE_M).rgb
        for x, y in ((-80.0, -80.0), (0.0, 0.0), (80.0, 40.0))
    ]

    together = describer.describe(images)
    alone = describer.describe(images[1:2])

    assert together.shape == (3, DESCRIPTOR_SIZE)
    assert np.allclose(np.linalg.norm(together, axis=1), 1.0, atol=UNIT_TOLERANCE)
    assert np.allclose(together[1], alone[0], atol=BATCH_TOLERANCE)
    assert describer.describe([]).shape == (0, DESCRIPTOR_SIZE)
