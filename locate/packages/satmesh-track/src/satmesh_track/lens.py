"""Lens calibration from photos' matches to mesh points, solved as a factor graph.

Each photo contributes pixels matched to 3D points that a render of the mesh put at those
pixels (area ENU metres). The graph holds one shared lens (focal length, radial k1 and k2 of the
OpenCV model x_d = x (1 + k1 r^2 + k2 r^4) on normalised coordinates, principal point fixed at the
image centre), a camera pose per photo and a point per match with a prior at its lifted position.
The prior sigma is the mesh error budget: with a tight one the lens is wrong and confident when the
mesh is off (photo-only P2). Reprojection error is a Huber loss, so single bad matches count little.

Frames that are wrong as a whole are removed first: a frame is rejected if the robust z-score
(median and MAD) of its reprojection RMS exceeds `rejection_z`, or if the z-score of the second
difference of consecutive positions does, at a local peak. A wrong pose raises three neighbouring
second differences and only the peak is the wrong frame. The MAD is floored at the noise the graph
already assumes (the pixel sigma for the residual, the mesh error for the jump), so noise-free data
has no outliers. The graph is solved again without the rejected frames.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import NamedTuple

import gtsam
import numpy as np
import numpy.typing as npt
from gtsam import symbol

from satmesh_eval.camera import Intrinsics

POSE_SYMBOL, POINT_SYMBOL, LENS_SYMBOL = "x", "l", "c"
MAD_TO_SIGMA = 1.4826  # median absolute deviation of a normal distribution is sigma / 1.4826
MIN_FRAMES_FOR_REJECTION = 5
LM_MAX_ITERATIONS = 100
FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class Lens:
    """Focal length (pixels) and radial distortion of an image of the given size."""

    focal_px: float
    k1: float
    k2: float
    width_px: int
    height_px: int

    def intrinsics(self) -> Intrinsics:
        """The lens as the camera module's type: square pixels, principal point at the centre."""
        return Intrinsics(
            self.width_px,
            self.height_px,
            self.focal_px,
            self.focal_px,
            self.width_px / 2,
            self.height_px / 2,
            (self.k1, self.k2),
        )


@dataclass(frozen=True)
class LensEstimate:
    """A lens and the 3 x 3 covariance of (focal_px, k1, k2)."""

    lens: Lens
    covariance: FloatArray

    @property
    def focal_sigma_px(self) -> float:
        """One standard deviation of the focal length, in pixels."""
        return float(np.sqrt(self.covariance[0, 0]))


@dataclass(frozen=True)
class CameraPoseEnu:
    """Camera centre and camera-to-ENU rotation (columns right, down, forward) in area ENU."""

    centre_enu: FloatArray
    camera_to_enu: FloatArray


@dataclass(frozen=True)
class FrameObservations:
    """One photo's matches: pixels (N, 2) and the area-ENU points (N, 3) they were matched to."""

    frame_id: int
    pose: CameraPoseEnu
    pixels: FloatArray
    points_enu: FloatArray


@dataclass(frozen=True)
class LensConfig:
    """Noise model and priors of the graph.

    `pixel_sigma_px` is the keypoint noise (a render-to-render residual of 2.4 px was measured,
    `harness-results.md`). The point sigma is `mesh_error_m + range_error_per_m * range`; the
    default 1.0 m is the mesh error assumed until real photos measure it. The focal prior sigma is
    relative to the initial focal, the radial priors are absolute.
    """

    pixel_sigma_px: float = 2.0
    huber_k: float = 1.345  # Huber's constant for 95 % efficiency under normal noise
    mesh_error_m: float = 1.0
    range_error_per_m: float = 0.005
    focal_prior_relative: float = 0.3
    radial_prior_sigma: float = 0.3
    max_points_per_frame: int = 100
    rejection_z: float = 4.0
    seed: int = 0


@dataclass(frozen=True)
class LensFit:
    """The fitted lens, a pose per kept frame and the frames that were rejected."""

    estimate: LensEstimate
    poses: dict[int, CameraPoseEnu]
    rejected: tuple[int, ...]


class _Solution(NamedTuple):
    graph: gtsam.NonlinearFactorGraph
    values: gtsam.Values
    estimate: LensEstimate
    frames: tuple[FrameObservations, ...]


def fit_lens(
    frames: Sequence[FrameObservations],
    initial: Lens,
    config: LensConfig = LensConfig(),  # noqa: B008  # frozen
) -> LensFit:
    """Fit the lens and the poses, rejecting wrong frames; frames are in photo order.

    Raises `ValueError` without frames.
    """
    if not frames:
        msg = "no frames to fit"
        raise ValueError(msg)
    subsampled = _subsample(frames, config)
    first = _solve(subsampled, initial, config)
    rejected = _rejected_ids(first, config)
    kept = tuple(f for f in subsampled if f.frame_id not in rejected)
    solution = _solve(kept, initial, config) if rejected and kept else first
    poses = {f.frame_id: _pose_of(solution.values, f.frame_id) for f in solution.frames}
    return LensFit(solution.estimate, poses, tuple(sorted(rejected)))


def _subsample(
    frames: Sequence[FrameObservations], config: LensConfig
) -> tuple[FrameObservations, ...]:
    rng = np.random.default_rng(config.seed)
    out = []
    for frame in frames:
        count = len(frame.pixels)
        keep = rng.choice(count, min(config.max_points_per_frame, count), replace=False)
        out.append(
            FrameObservations(
                frame.frame_id, frame.pose, frame.pixels[keep], frame.points_enu[keep]
            )
        )
    return tuple(out)


def _solve(frames: tuple[FrameObservations, ...], initial: Lens, config: LensConfig) -> _Solution:
    graph = gtsam.NonlinearFactorGraph()
    values = gtsam.Values()
    lens_key = symbol(LENS_SYMBOL, 0)
    start = gtsam.Cal3Bundler(
        initial.focal_px, initial.k1, initial.k2, initial.width_px / 2, initial.height_px / 2
    )
    values.insert(lens_key, start)
    prior_sigmas = np.array(
        [config.focal_prior_relative * initial.focal_px, *[config.radial_prior_sigma] * 2]
    )
    graph.add(
        gtsam.PriorFactorCal3Bundler(
            lens_key, start, gtsam.noiseModel.Diagonal.Sigmas(prior_sigmas)
        )
    )
    reprojection_noise = gtsam.noiseModel.Robust.Create(
        gtsam.noiseModel.mEstimator.Huber.Create(config.huber_k),
        gtsam.noiseModel.Isotropic.Sigma(2, config.pixel_sigma_px),
    )
    point_index = 0
    for frame in frames:
        pose_key = symbol(POSE_SYMBOL, frame.frame_id)
        values.insert(
            pose_key, gtsam.Pose3(gtsam.Rot3(frame.pose.camera_to_enu), frame.pose.centre_enu)
        )
        for pixel, point in zip(frame.pixels, frame.points_enu, strict=True):
            point_key = symbol(POINT_SYMBOL, point_index)
            point_index += 1
            sigma = config.mesh_error_m + config.range_error_per_m * float(
                np.linalg.norm(point - frame.pose.centre_enu)
            )
            values.insert(point_key, point)
            graph.add(
                gtsam.PriorFactorPoint3(
                    point_key, point, gtsam.noiseModel.Isotropic.Sigma(3, sigma)
                )
            )
            graph.add(
                gtsam.GeneralSFMFactor2Cal3Bundler(
                    pixel, reprojection_noise, pose_key, point_key, lens_key
                )
            )
    params = gtsam.LevenbergMarquardtParams()
    params.setMaxIterations(LM_MAX_ITERATIONS)
    result = gtsam.LevenbergMarquardtOptimizer(graph, values, params).optimize()
    cal = result.atCal3Bundler(lens_key)
    covariance = gtsam.Marginals(graph, result).marginalCovariance(lens_key)
    lens = Lens(cal.fx(), cal.k1(), cal.k2(), initial.width_px, initial.height_px)
    return _Solution(graph, result, LensEstimate(lens, np.asarray(covariance)), frames)


def _pose_of(values: gtsam.Values, frame_id: int) -> CameraPoseEnu:
    pose = values.atPose3(symbol(POSE_SYMBOL, frame_id))
    return CameraPoseEnu(np.asarray(pose.translation()), np.asarray(pose.rotation().matrix()))


def _rejected_ids(solution: _Solution, config: LensConfig) -> set[int]:
    frames = solution.frames
    if len(frames) < MIN_FRAMES_FOR_REJECTION:
        return set()
    rms = np.array([_reprojection_rms(solution, f) for f in frames])
    bad_residual = _robust_z(rms, config.pixel_sigma_px) > config.rejection_z
    jump = _robust_z(_second_differences(solution), config.mesh_error_m)
    is_peak = np.array(
        [jump[i] >= jump[max(i - 1, 0) : i + 2].max() for i in range(len(frames))], dtype=bool
    )
    flagged = bad_residual | ((jump > config.rejection_z) & is_peak)
    return {f.frame_id for f, bad in zip(frames, flagged, strict=True) if bad}


def _reprojection_rms(solution: _Solution, frame: FrameObservations) -> float:
    cal = solution.values.atCal3Bundler(symbol(LENS_SYMBOL, 0))
    camera = gtsam.PinholeCameraCal3Bundler(
        solution.values.atPose3(symbol(POSE_SYMBOL, frame.frame_id)), cal
    )
    projected = np.array([camera.project(p) for p in frame.points_enu])
    return float(np.sqrt(np.mean(np.sum((projected - frame.pixels) ** 2, axis=1))))


def _second_differences(solution: _Solution) -> FloatArray:
    """Norm of x[i-1] - 2 x[i] + x[i+1] per frame; zero where the three ids are not consecutive."""
    frames = solution.frames
    positions = np.array([_pose_of(solution.values, f.frame_id).centre_enu for f in frames])
    out = np.zeros(len(frames))
    for i in range(1, len(frames) - 1):
        ids = [frames[i - 1].frame_id, frames[i].frame_id, frames[i + 1].frame_id]
        if ids[1] - ids[0] == 1 and ids[2] - ids[1] == 1:
            out[i] = np.linalg.norm(positions[i - 1] - 2 * positions[i] + positions[i + 1])
    return out


def _robust_z(values: FloatArray, spread_floor: float) -> FloatArray:
    centre = np.median(values)
    spread = max(MAD_TO_SIGMA * np.median(np.abs(values - centre)), spread_floor)
    return (values - centre) / spread
