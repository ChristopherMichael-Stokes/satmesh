import os
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from test_localise import INTRINSICS, MAX_RANGE_M, embree_renderer, truth_pose, with_buildings

from satmesh_eval.matching import (
    Matcher,
    match_against,
    onnx_matcher,
    sift_match,
    supports_concurrent_calls,
    tensorrt_matcher,
)

MODEL_DIR_VARIABLE = "XFEAT_MODEL_DIR"
SHIFT_DEG = 1.5  # heading change between the two renders: enough to leave matches, not all


def two_views() -> tuple[np.ndarray, np.ndarray]:
    renderer = embree_renderer(with_buildings())
    truth = truth_pose()
    turned = replace(truth, heading_deg=truth.heading_deg + SHIFT_DEG)
    return (
        renderer(INTRINSICS, truth, MAX_RANGE_M).rgb,
        renderer(INTRINSICS, turned, MAX_RANGE_M).rgb,
    )


def assert_same_matches(matcher: Matcher) -> None:
    first, second = two_views()

    direct = matcher(first, second)
    shared = match_against(matcher, first)(second)

    assert len(direct) > 0
    np.testing.assert_array_equal(shared.points_a, direct.points_a)
    np.testing.assert_array_equal(shared.points_b, direct.points_b)


def test_sift_matches_against_a_fixed_first_image_equal_the_direct_call() -> None:
    assert_same_matches(sift_match)


@pytest.mark.skipif(MODEL_DIR_VARIABLE not in os.environ, reason=f"{MODEL_DIR_VARIABLE} not set")
def test_xfeat_matches_against_a_fixed_first_image_equal_the_direct_call() -> None:
    assert_same_matches(onnx_matcher(Path(os.environ[MODEL_DIR_VARIABLE])))


def tensorrt_models_available() -> bool:
    model_dir = os.environ.get(MODEL_DIR_VARIABLE)
    return model_dir is not None and any(Path(model_dir).glob("xfeat_*_fp16.onnx"))


@pytest.mark.skipif(not tensorrt_models_available(), reason="no FP16 exports in XFEAT_MODEL_DIR")
def test_tensorrt_matches_against_a_fixed_first_image_equal_the_direct_call() -> None:
    matcher = tensorrt_matcher(Path(os.environ[MODEL_DIR_VARIABLE]))

    assert_same_matches(matcher)
    assert not supports_concurrent_calls(matcher)


def test_function_matchers_support_concurrent_calls() -> None:
    assert supports_concurrent_calls(sift_match)
