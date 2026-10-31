"""Feature matchers between two RGB images: OpenCV SIFT and XFeat with LighterGlue.

Every matcher returns pixel coordinates in the convention of `satmesh_eval.camera` (the centre of
pixel (column c, row r) at (c + 0.5, r + 0.5)), so matches feed straight into projection with an
`Intrinsics`.
"""

import os
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np
import numpy.typing as npt
from xfeat_core.features import Features
from xfeat_core.metadata import LighterGlueMetadata, XFeatMetadata
from xfeat_ort.models import LighterGlueModel as LighterGlueOnnx
from xfeat_ort.models import XFeatModel as XFeatOnnx
from xfeat_pairs.preprocess import PreparedImage, to_original_coordinates

from satmesh_eval.grey import write_grey

SIFT_FEATURE_LIMIT = 8000
SIFT_RATIO = 0.8  # Lowe, "Distinctive Image Features from Scale-Invariant Keypoints", IJCV 2004
PIXEL_CENTRE_OFFSET = 0.5  # OpenCV and XFeat put pixel centres at integers, camera.py at +0.5
KNN_NEIGHBOURS = 2
XFEAT_KEYPOINTS = 2048
TENSORRT_KEYPOINTS = (
    4096  # GPU time barely grows: flight L start search 6.5 s at 2048, 6.7 s at 4096
)
XFEAT_INPUT_SIZE = "1280x960"
LOGICAL_CPUS_PER_CORE = 2  # SMT on x86; not detectable from the stdlib
# ONNX Runtime defaults to every logical CPU, which oversubscribes the cores: on an 8-core SMT CPU
# 8 threads per run beat 16 by 1.2x for one caller and 1.75x for two or more
ONNX_THREADS = max(1, (os.cpu_count() or LOGICAL_CPUS_PER_CORE) // LOGICAL_CPUS_PER_CORE)


@dataclass(frozen=True)
class Matches:
    """Corresponding points of two images, row i of `points_a` matching row i of `points_b`.

    Both arrays are (N, 2) float64 pixel coordinates, pixel centres at half-integers.
    """

    points_a: npt.NDArray[np.float64]
    points_b: npt.NDArray[np.float64]

    def __len__(self) -> int:
        """Number of correspondences."""
        return len(self.points_a)


Matcher = Callable[[npt.NDArray[np.uint8], npt.NDArray[np.uint8]], Matches]


def sift_match(image_a: npt.NDArray[np.uint8], image_b: npt.NDArray[np.uint8]) -> Matches:
    """Match two RGB images with SIFT, Lowe's ratio test and a mutual-nearest-neighbour check."""
    sift = cv2.SIFT.create(nfeatures=SIFT_FEATURE_LIMIT)
    keypoints_a, descriptors_a = sift.detectAndCompute(_gray(image_a), None)
    keypoints_b, descriptors_b = sift.detectAndCompute(_gray(image_b), None)
    if min(len(keypoints_a), len(keypoints_b)) < KNN_NEIGHBOURS:  # no keypoints, descriptors None
        return _no_matches()
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    forward = matcher.knnMatch(descriptors_a, descriptors_b, k=KNN_NEIGHBOURS)
    backward = matcher.match(descriptors_b, descriptors_a)
    pairs = [
        (best.queryIdx, best.trainIdx)
        for best, second in (found for found in forward if len(found) == KNN_NEIGHBOURS)
        if best.distance < SIFT_RATIO * second.distance
        and backward[best.trainIdx].trainIdx == best.queryIdx
    ]
    if not pairs:
        return _no_matches()
    index_a, index_b = np.array(pairs).T
    points_a = np.array([keypoint.pt for keypoint in keypoints_a])[index_a]
    points_b = np.array([keypoint.pt for keypoint in keypoints_b])[index_b]
    return Matches(points_a + PIXEL_CENTRE_OFFSET, points_b + PIXEL_CENTRE_OFFSET)


@dataclass(frozen=True)
class ImageFeatures:
    """XFeat features of one image and the letterbox mapping from model pixels back to the image."""

    prepared: PreparedImage
    features: Features


class FeatureExtractor(Protocol):
    """An XFeat graph on some backend: gray images in [0, 1] to features."""

    metadata: XFeatMetadata

    def extract(self, images: npt.NDArray[np.float32]) -> list[Features]:
        """Features of each image of a (B, 1, H, W) batch."""
        ...


class FeatureMatcher(Protocol):
    """A LighterGlue graph on some backend: two feature sets to index pairs."""

    metadata: LighterGlueMetadata

    def match(self, first: Features, second: Features) -> npt.NDArray[np.int64]:
        """(M, 2) index pairs into `first` and `second` of the mutual matches."""
        ...


class XFeatLighterGlueMatcher:
    """XFeat features (Potje et al., CVPR 2024) matched by LighterGlue.

    The graphs are exported by the `third-party/xfeat-rt` reference and take one fixed input size.
    Images are fitted to it keeping their aspect ratio, and keypoints are mapped back to the input
    images' pixels. `concurrent` says whether several threads may call the matcher at once.
    """

    def __init__(
        self, xfeat: FeatureExtractor, lighterglue: FeatureMatcher, *, concurrent: bool
    ) -> None:
        """Pair an XFeat graph with a LighterGlue graph of the same keypoint count."""
        self._xfeat = xfeat
        self._lighterglue = lighterglue
        self.concurrent = concurrent
        if xfeat.metadata.top_k != lighterglue.metadata.top_k:
            msg = (
                f"XFeat keeps {xfeat.metadata.top_k} keypoints, "
                f"LighterGlue takes {lighterglue.metadata.top_k}"
            )
            raise ValueError(msg)
        self._model_size = (xfeat.metadata.width, xfeat.metadata.height)

    def extract(self, image: npt.NDArray[np.uint8]) -> ImageFeatures:
        """XFeat features of one RGB image, with the mapping back to its pixels."""
        prepared = _fit_to_model(image, self._model_size)
        return ImageFeatures(prepared, self._xfeat.extract(prepared.pixels)[0])

    def match_features(self, first: ImageFeatures, second: ImageFeatures) -> Matches:
        """LighterGlue matches between two extracted images, in their original pixels."""
        index_pairs = self._lighterglue.match(first.features, second.features)
        if len(index_pairs) == 0:
            return _no_matches()
        points_first = to_original_coordinates(
            first.features.keypoints[index_pairs[:, 0]], first.prepared
        )
        points_second = to_original_coordinates(
            second.features.keypoints[index_pairs[:, 1]], second.prepared
        )
        return Matches(
            points_first.astype(np.float64) + PIXEL_CENTRE_OFFSET,
            points_second.astype(np.float64) + PIXEL_CENTRE_OFFSET,
        )

    def __call__(self, image_a: npt.NDArray[np.uint8], image_b: npt.NDArray[np.uint8]) -> Matches:
        """Match two RGB images."""
        return self.match_features(self.extract(image_a), self.extract(image_b))

    def against(self, image: npt.NDArray[np.uint8]) -> Callable[[npt.NDArray[np.uint8]], Matches]:
        """A matcher of `image` against others that extracts `image`'s features once."""
        first = self.extract(image)
        return lambda other: self.match_features(first, self.extract(other))


def match_against(
    matcher: Matcher, image: npt.NDArray[np.uint8]
) -> Callable[[npt.NDArray[np.uint8]], Matches]:
    """`matcher` with its first image fixed, sharing the first image's features where it can."""
    if isinstance(matcher, XFeatLighterGlueMatcher):
        return matcher.against(image)
    return partial(matcher, image)


def supports_concurrent_calls(matcher: Matcher) -> bool:
    """Whether several threads may call `matcher` at once."""
    return not isinstance(matcher, XFeatLighterGlueMatcher) or matcher.concurrent


def onnx_matcher(model_dir: Path, intra_op_threads: int = ONNX_THREADS) -> XFeatLighterGlueMatcher:
    """The matcher on ONNX Runtime (CPU) from a directory of `xfeat-rt` exports.

    Files are named `xfeat_{size}_k{keypoints}_b1.onnx` and `lighterglue_k{keypoints}_b1.onnx`.
    """
    return XFeatLighterGlueMatcher(
        XFeatOnnx(
            model_dir / f"xfeat_{XFEAT_INPUT_SIZE}_k{XFEAT_KEYPOINTS}_b1.onnx", intra_op_threads
        ),
        LighterGlueOnnx(model_dir / f"lighterglue_k{XFEAT_KEYPOINTS}_b1.onnx", intra_op_threads),
        concurrent=True,
    )


def tensorrt_matcher(
    model_dir: Path, keypoints: int = TENSORRT_KEYPOINTS
) -> XFeatLighterGlueMatcher:
    """The matcher on TensorRT (NVIDIA GPU) from a directory of FP16 `xfeat-rt` exports.

    Files are the ONNX names with `_fp16` before the extension. Engines are built on first use and
    cached by `xfeat_trt`. The engine runners share buffers and the CUDA context belongs to the
    creating thread, so the matcher must be called from that thread only.
    """
    from xfeat_trt.models import LighterGlueModel as LighterGlueTrt  # noqa: PLC0415  # optional extra
    from xfeat_trt.models import XFeatModel as XFeatTrt  # noqa: PLC0415  # optional extra

    return XFeatLighterGlueMatcher(
        XFeatTrt(model_dir / f"xfeat_{XFEAT_INPUT_SIZE}_k{keypoints}_b1_fp16.onnx"),
        LighterGlueTrt(model_dir / f"lighterglue_k{keypoints}_b1_fp16.onnx"),
        concurrent=False,
    )


def _fit_to_model(image: npt.NDArray[np.uint8], model_size: tuple[int, int]) -> PreparedImage:
    """Letterbox an RGB image into the model input, as `xfeat_pairs.preprocess.prepare_image`.

    Resizing happens on 8-bit RGB with bilinear interpolation before the channel mean, the order
    of the reference pipeline.
    """
    height, width = image.shape[:2]
    model_width, model_height = model_size
    fit = min(model_width / width, model_height / height)
    content_size = (round(width * fit), round(height * fit))
    resized = np.asarray(
        cv2.resize(image, content_size, interpolation=cv2.INTER_LINEAR), dtype=np.uint8
    )
    offset = ((model_width - content_size[0]) // 2, (model_height - content_size[1]) // 2)
    canvas = np.zeros((model_height, model_width), dtype=np.float32)
    write_grey(
        resized,
        canvas[offset[1] : offset[1] + content_size[1], offset[0] : offset[0] + content_size[0]],
    )
    scale = (content_size[0] / width, content_size[1] / height)
    return PreparedImage(canvas[None, None], (width, height), scale, offset)


def _gray(image: npt.NDArray[np.uint8]) -> npt.NDArray[np.uint8]:
    return np.asarray(cv2.cvtColor(image, cv2.COLOR_RGB2GRAY), dtype=np.uint8)


def _no_matches() -> Matches:
    return Matches(np.zeros((0, 2)), np.zeros((0, 2)))
