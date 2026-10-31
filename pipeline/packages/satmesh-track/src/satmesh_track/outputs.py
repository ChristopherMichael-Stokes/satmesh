"""Files a track writes: the pose file, the lens calibration, a report and a review page.

`poses.jsonl` uses the pose-file schema of `satmesh eval localise` (`satmesh_eval.poses`), so a
track can be scored against logged poses with that command. Poses and the lens are in the
photos' original pixels: the tracker works on reduced photos and the focal length scales back.
Lost and rejected photos have no line in the pose file; they are in the report.
"""

import base64
import json
import math
from collections.abc import Sequence
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from satmesh_core import EnuFrame
from satmesh_eval.camera import pose_from_camera_to_enu
from satmesh_eval.poses import IntrinsicsFields, PhotoRecord
from satmesh_track.lens import Lens, LensEstimate
from satmesh_track.photos import LoadedPhoto
from satmesh_track.tracker import PhotoStatus, TrackedPhoto, TrackResult

POSES_FILE, CALIBRATION_FILE, REPORT_FILE, REVIEW_FILE = (
    "poses.jsonl",
    "calibration.json",
    "report.json",
    "review.html",
)
TEMPLATE_NAME = "track_review.html"
DATA_PLACEHOLDER = "__DATA__"
FISHEYE_WARNING_DEG = 110.0  # beyond this the radial polynomial and a pinhole render stop working
THUMBNAIL_HEIGHT_PX = 110
THUMBNAIL_QUALITY = 70
JSON_INDENT = 2


def write_outputs(
    out: Path, result: TrackResult, photos: Sequence[LoadedPhoto], area: EnuFrame
) -> None:
    """Write the four files into `out`, creating it."""
    out.mkdir(parents=True, exist_ok=True)
    lens = original_lens(result.lens.lens, photos[0])
    records = pose_records(result, photos, lens, area)
    (out / POSES_FILE).write_text("".join(r.model_dump_json() + "\n" for r in records))
    calibration = calibration_dict(result.lens, photos[0])
    (out / CALIBRATION_FILE).write_text(json.dumps(calibration, indent=JSON_INDENT))
    (out / REPORT_FILE).write_text(json.dumps(report_dict(result), indent=JSON_INDENT))
    (out / REVIEW_FILE).write_text(review_html(result, photos, calibration))


def original_lens(lens: Lens, photo: LoadedPhoto) -> Lens:
    """The lens in the original photos' pixels: the focal length scales, k1 and k2 do not."""
    return Lens(
        lens.focal_px * photo.scale_to_original,
        lens.k1,
        lens.k2,
        photo.original_width_px,
        photo.original_height_px,
    )


def horizontal_fov_deg(lens: Lens) -> float:
    """The horizontal field of view of an undistorted pinhole with this focal length."""
    return math.degrees(2 * math.atan(lens.width_px / 2 / lens.focal_px))


def pose_records(
    result: TrackResult, photos: Sequence[LoadedPhoto], lens: Lens, area: EnuFrame
) -> list[PhotoRecord]:
    """One pose-file line for every photo with a pose that the lens graph kept."""
    intrinsics = IntrinsicsFields(
        width_px=lens.width_px,
        height_px=lens.height_px,
        focal_x_px=lens.focal_px,
        focal_y_px=lens.focal_px,
        principal_x_px=lens.width_px / 2,
        principal_y_px=lens.height_px / 2,
        radial_distortion=(lens.k1, lens.k2),
    )
    records = []
    for tracked, _ in zip(result.photos, photos, strict=True):
        if tracked.pose is None or tracked.status == PhotoStatus.REJECTED:
            continue
        pose = pose_from_camera_to_enu(area, tracked.pose.centre_enu, tracked.pose.camera_to_enu)
        records.append(
            PhotoRecord(
                photo=tracked.name,
                latitude_deg=pose.latitude_deg,
                longitude_deg=pose.longitude_deg,
                ellipsoidal_height_m=pose.ellipsoidal_height_m,
                heading_deg=pose.heading_deg,
                pitch_deg=pose.pitch_deg,
                roll_deg=pose.roll_deg,
                intrinsics=intrinsics,
            )
        )
    return records


def calibration_dict(estimate: LensEstimate, photo: LoadedPhoto) -> dict[str, Any]:
    """The lens at the original size with its covariance of (focal_px, k1, k2)."""
    lens = original_lens(estimate.lens, photo)
    scale = np.diag([photo.scale_to_original, 1.0, 1.0])
    covariance = scale @ estimate.covariance @ scale
    fov = horizontal_fov_deg(lens)
    warnings = (
        [
            (
                f"The horizontal field of view is {fov:.0f} degrees; beyond "
                f"{FISHEYE_WARNING_DEG:.0f} a fisheye lens is likely and this lens model "
                "does not fit it."
            )
        ]
        if fov > FISHEYE_WARNING_DEG
        else []
    )
    return {
        "focal_px": lens.focal_px,
        "focal_sigma_px": float(np.sqrt(covariance[0, 0])),
        "k1": lens.k1,
        "k2": lens.k2,
        "width_px": lens.width_px,
        "height_px": lens.height_px,
        "principal_x_px": lens.width_px / 2,
        "principal_y_px": lens.height_px / 2,
        "horizontal_fov_deg": fov,
        "covariance_focal_k1_k2": covariance.tolist(),
        "warnings": warnings,
    }


def report_dict(result: TrackResult) -> dict[str, Any]:
    """Per photo status, inliers and residual, and the local searches."""
    return {
        "photos": [
            {
                "photo": p.name,
                "status": p.status.value,
                "inliers": p.inliers,
                "reprojection_rmse_px": p.reprojection_rmse_px,
            }
            for p in result.photos
        ],
        "searches": [asdict(s) for s in result.searches],
    }


def review_html(
    result: TrackResult, photos: Sequence[LoadedPhoto], calibration: dict[str, Any]
) -> str:
    """The single-file review page: plan view, lens table, thumbnails, photo table, searches."""
    data = {
        "warnings": calibration["warnings"],
        "lens": [
            [
                "Focal length",
                f"{calibration['focal_px']:.1f} px (1 sigma {calibration['focal_sigma_px']:.1f})",
            ],
            ["Radial k1, k2", f"{calibration['k1']:.4f}, {calibration['k2']:.4f}"],
            ["Horizontal field of view", f"{calibration['horizontal_fov_deg']:.1f} degrees"],
            ["Image size", f"{calibration['width_px']} x {calibration['height_px']} px"],
        ],
        "photos": [
            _photo_entry(tracked, loaded)
            for tracked, loaded in zip(result.photos, photos, strict=True)
        ],
        "searches": [asdict(s) for s in result.searches],
    }
    template = files("satmesh_track").joinpath(TEMPLATE_NAME).read_text()
    return template.replace(DATA_PLACEHOLDER, json.dumps(data).replace("</", "<\\/"))


def _photo_entry(tracked: TrackedPhoto, loaded: LoadedPhoto) -> dict[str, Any]:
    pose = tracked.pose
    forward = pose.camera_to_enu[:, 2] if pose is not None else None
    norm = float(np.hypot(forward[0], forward[1])) if forward is not None else 1.0
    return {
        "name": tracked.name,
        "status": tracked.status.value,
        "inliers": tracked.inliers,
        "rmse": tracked.reprojection_rmse_px,
        "east": None if pose is None else float(pose.centre_enu[0]),
        "north": None if pose is None else float(pose.centre_enu[1]),
        "height": None if pose is None else float(pose.centre_enu[2]),
        "fx": 0.0 if forward is None else float(forward[0]) / max(norm, 1e-9),
        "fy": 0.0 if forward is None else float(forward[1]) / max(norm, 1e-9),
        "thumb": _thumbnail(loaded),
    }


def _thumbnail(photo: LoadedPhoto) -> str:
    rgb = photo.image.rgb
    scale = THUMBNAIL_HEIGHT_PX / rgb.shape[0]
    small = cv2.resize(
        rgb, (round(rgb.shape[1] * scale), THUMBNAIL_HEIGHT_PX), interpolation=cv2.INTER_AREA
    )
    _, encoded = cv2.imencode(
        ".jpg",
        cv2.cvtColor(small, cv2.COLOR_RGB2BGR),
        [cv2.IMWRITE_JPEG_QUALITY, THUMBNAIL_QUALITY],
    )
    return "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode()
