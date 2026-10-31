"""Prepare a photo for the harness: undistorted, with pinhole intrinsics, at working size."""

from dataclasses import dataclass, replace
from pathlib import Path

import cv2
import numpy as np
import numpy.typing as npt

from satmesh_eval.camera import Intrinsics

WORKING_LONG_SIDE_PX = 1280  # the XFeat export's input width; larger photos are reduced to it


@dataclass(frozen=True)
class WorkingPhoto:
    """RGB image with the pinhole intrinsics that describe it exactly."""

    image: npt.NDArray[np.uint8]
    intrinsics: Intrinsics


def load_working_photo(path: Path, intrinsics: Intrinsics) -> WorkingPhoto:
    """Read `path`, remove radial distortion and reduce to `WORKING_LONG_SIDE_PX` if larger.

    Undistortion keeps the camera matrix, so the returned intrinsics are the input's without
    distortion, scaled by the reduction. Raises `ValueError` if the file cannot be read or its size
    differs from the intrinsics'.
    """
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        msg = f"cannot read image {path}"
        raise ValueError(msg)
    height, width = bgr.shape[:2]
    if (width, height) != (intrinsics.width_px, intrinsics.height_px):
        msg = (
            f"{path} is {width} x {height} px but its intrinsics describe "
            f"{intrinsics.width_px} x {intrinsics.height_px}"
        )
        raise ValueError(msg)
    rgb = np.asarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), dtype=np.uint8)
    pinhole = replace(intrinsics, radial_distortion=())
    if intrinsics.radial_distortion:
        k1, k2, *k3 = intrinsics.radial_distortion
        coefficients = np.array([k1, k2, 0.0, 0.0, *k3])
        rgb = np.asarray(
            cv2.undistort(rgb, intrinsics.matrix(), coefficients, None, intrinsics.matrix()),
            dtype=np.uint8,
        )
    return _reduced(WorkingPhoto(rgb, pinhole))


def _reduced(photo: WorkingPhoto) -> WorkingPhoto:
    intrinsics = photo.intrinsics
    scale = WORKING_LONG_SIDE_PX / max(intrinsics.width_px, intrinsics.height_px)
    if scale >= 1.0:
        return photo
    width, height = round(intrinsics.width_px * scale), round(intrinsics.height_px * scale)
    image = np.asarray(
        cv2.resize(photo.image, (width, height), interpolation=cv2.INTER_AREA), dtype=np.uint8
    )
    scaled = Intrinsics(
        width,
        height,
        intrinsics.focal_x_px * width / intrinsics.width_px,
        intrinsics.focal_y_px * height / intrinsics.height_px,
        intrinsics.principal_x_px * width / intrinsics.width_px,
        intrinsics.principal_y_px * height / intrinsics.height_px,
        (),
    )
    return WorkingPhoto(image, scaled)
