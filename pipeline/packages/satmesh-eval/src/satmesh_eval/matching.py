"""Feature matchers between two RGB images: OpenCV SIFT and XFeat with LighterGlue.

Every matcher returns pixel coordinates in the convention of `satmesh_eval.camera` (the centre of
pixel (column c, row r) at (c + 0.5, r + 0.5)), so matches feed straight into projection with an
`Intrinsics`.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import numpy.typing as npt
from xfeat_ort.models import LighterGlueModel, XFeatModel
from xfeat_pairs.preprocess import MAX_PIXEL_VALUE, PreparedImage, to_original_coordinates

SIFT_FEATURE_LIMIT = 8000
SIFT_RATIO = 0.8  # Lowe, "Distinctive Image Features from Scale-Invariant Keypoints", IJCV 2004
PIXEL_CENTRE_OFFSET = 0.5  # OpenCV and XFeat put pixel centres at integers, camera.py at +0.5
KNN_NEIGHBOURS = 2


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


class XFeatLighterGlueMatcher:
    """XFeat features (Potje et al., CVPR 2024) matched by LighterGlue, on ONNX Runtime.

    The graphs are exported by the `third-party/xfeat-rt` reference and take one fixed input size.
    Images are fitted to it keeping their aspect ratio, and keypoints are mapped back to the input
    images' pixels.
    """

    def __init__(self, xfeat_path: Path, lighterglue_path: Path) -> None:
        """Load an exported XFeat graph and a LighterGlue graph with the same keypoint count."""
        self._xfeat = XFeatModel(xfeat_path)
        self._lighterglue = LighterGlueModel(lighterglue_path)
        if self._xfeat.metadata.top_k != self._lighterglue.metadata.top_k:
            msg = (
                f"XFeat keeps {self._xfeat.metadata.top_k} keypoints, "
                f"LighterGlue takes {self._lighterglue.metadata.top_k}"
            )
            raise ValueError(msg)
        self._model_size = (self._xfeat.metadata.width, self._xfeat.metadata.height)

    def __call__(self, image_a: npt.NDArray[np.uint8], image_b: npt.NDArray[np.uint8]) -> Matches:
        """Match two RGB images."""
        prepared_a, prepared_b = (
            _fit_to_model(image, self._model_size) for image in (image_a, image_b)
        )
        features_a, features_b = (
            self._xfeat.extract(p.pixels)[0] for p in (prepared_a, prepared_b)
        )
        index_pairs = self._lighterglue.match(features_a, features_b)
        if len(index_pairs) == 0:
            return _no_matches()
        points_a = to_original_coordinates(features_a.keypoints[index_pairs[:, 0]], prepared_a)
        points_b = to_original_coordinates(features_b.keypoints[index_pairs[:, 1]], prepared_b)
        return Matches(
            points_a.astype(np.float64) + PIXEL_CENTRE_OFFSET,
            points_b.astype(np.float64) + PIXEL_CENTRE_OFFSET,
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
    resized = cv2.resize(image, content_size, interpolation=cv2.INTER_LINEAR)
    content = resized.astype(np.float32).mean(axis=2) / MAX_PIXEL_VALUE
    offset = ((model_width - content_size[0]) // 2, (model_height - content_size[1]) // 2)
    canvas = np.zeros((model_height, model_width), dtype=np.float32)
    canvas[offset[1] : offset[1] + content_size[1], offset[0] : offset[0] + content_size[0]] = (
        content
    )
    scale = (content_size[0] / width, content_size[1] / height)
    return PreparedImage(canvas[None, None], (width, height), scale, offset)


def _gray(image: npt.NDArray[np.uint8]) -> npt.NDArray[np.uint8]:
    return np.asarray(cv2.cvtColor(image, cv2.COLOR_RGB2GRAY), dtype=np.uint8)


def _no_matches() -> Matches:
    return Matches(np.zeros((0, 2)), np.zeros((0, 2)))
