"""Files a track writes: the pose file, the lens calibration, a report and a review page.

`poses.jsonl` uses the pose-file schema of `satmesh eval localise` (`satmesh_eval.poses`), so a
track can be scored against logged poses with that command. Poses and the lens are in the
photos' original pixels: the tracker works on reduced photos and the focal length scales back.
Lost and rejected photos have no line in the pose file; they are in the report.
"""

import base64
import csv
import json
import math
import statistics
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from satmesh_core import EnuFrame, geodetic_to_ecef
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
REVIEW_IMAGE_HEIGHT_PX = 450  # shown full width when selected, reduced in the strip
REVIEW_IMAGE_QUALITY = 65
REFERENCE_COLUMNS = ("photo", "latitude_deg", "longitude_deg")
JSON_INDENT = 2


@dataclass(frozen=True)
class ReferencePoint:
    """A logged position of a photo (a drone's telemetry), to contrast with the recovered one.

    `height_m` is in whatever datum the log uses (a drone logs height above its take-off point);
    the page compares heights up to one constant offset.
    """

    photo: str
    latitude_deg: float
    longitude_deg: float
    height_m: float | None


def read_reference(path: Path) -> list[ReferencePoint]:
    """Read a CSV with columns photo, latitude_deg, longitude_deg and optionally height_m."""
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in REFERENCE_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            msg = f"{path} lacks columns {missing}"
            raise ValueError(msg)
        return [
            ReferencePoint(
                row["photo"],
                float(row["latitude_deg"]),
                float(row["longitude_deg"]),
                _optional_float(row.get("height_m")),
            )
            for row in reader
        ]


def _optional_float(text: str | None) -> float | None:
    return None if text is None or text == "" else float(text)


def write_outputs(
    out: Path,
    result: TrackResult,
    photos: Sequence[LoadedPhoto],
    area: EnuFrame,
    reference: Sequence[ReferencePoint] = (),
) -> None:
    """Write the four files into `out`, creating it; `reference` adds a logged track to the page."""
    out.mkdir(parents=True, exist_ok=True)
    lens = original_lens(result.lens.lens, photos[0])
    records = pose_records(result, photos, lens, area)
    (out / POSES_FILE).write_text("".join(r.model_dump_json() + "\n" for r in records))
    calibration = calibration_dict(result.lens, photos[0])
    (out / CALIBRATION_FILE).write_text(json.dumps(calibration, indent=JSON_INDENT))
    (out / REPORT_FILE).write_text(json.dumps(report_dict(result), indent=JSON_INDENT))
    (out / REVIEW_FILE).write_text(review_html(result, photos, calibration, area, reference))


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
    result: TrackResult,
    photos: Sequence[LoadedPhoto],
    calibration: dict[str, Any],
    area: EnuFrame,
    reference: Sequence[ReferencePoint],
) -> str:
    """The single-file review page: plan view, lens, photos, photo table, searches, reference."""
    entries = [
        _photo_entry(tracked, loaded) for tracked, loaded in zip(result.photos, photos, strict=True)
    ]
    summary = _contrast_with_reference(entries, reference, area)
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
        "photos": entries,
        "searches": [asdict(s) for s in result.searches],
        "reference": summary,
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


def _contrast_with_reference(
    entries: list[dict[str, Any]], reference: Sequence[ReferencePoint], area: EnuFrame
) -> dict[str, Any] | None:
    """Add each photo's reference position and residuals to `entries`; return the summary figures.

    The horizontal residual is the distance between the recovered and logged positions. The height
    residual is the recovered height minus the logged one, minus the median of that difference over
    the photos (the two heights are in different datums).
    """
    if not reference:
        return None
    logged = {point.photo: point for point in reference}
    for entry in entries:
        point = logged.get(entry["name"])
        entry["ref_east"] = entry["ref_north"] = entry["residual_m"] = None
        entry["height_residual_m"] = None
        if point is None:
            continue
        ecef = np.array(geodetic_to_ecef().transform(point.longitude_deg, point.latitude_deg, 0.0))
        east, north = (float(v) for v in area.to_enu(ecef[None, :])[0][:2])
        entry["ref_east"], entry["ref_north"] = east, north
        if entry["east"] is not None:
            entry["residual_m"] = math.hypot(entry["east"] - east, entry["north"] - north)
        entry["_height_difference"] = (
            None
            if entry["east"] is None or point.height_m is None
            else entry["height"] - point.height_m
        )
    differences = [
        e["_height_difference"] for e in entries if e.get("_height_difference") is not None
    ]
    offset = statistics.median(differences) if differences else None
    for entry in entries:
        difference = entry.pop("_height_difference", None)
        if difference is not None and offset is not None:
            entry["height_residual_m"] = difference - offset
    residuals = [e["residual_m"] for e in entries if e["residual_m"] is not None]
    return {
        "compared": len(residuals),
        "horizontal_median_m": statistics.median(residuals) if residuals else None,
        "horizontal_max_m": max(residuals) if residuals else None,
        "height_offset_m": offset,
        "height_residual_median_m": statistics.median(
            abs(e["height_residual_m"]) for e in entries if e["height_residual_m"] is not None
        )
        if offset is not None
        else None,
    }


def _thumbnail(photo: LoadedPhoto) -> str:
    rgb = photo.image.rgb
    scale = REVIEW_IMAGE_HEIGHT_PX / rgb.shape[0]
    small = cv2.resize(
        rgb, (round(rgb.shape[1] * scale), REVIEW_IMAGE_HEIGHT_PX), interpolation=cv2.INTER_AREA
    )
    _, encoded = cv2.imencode(
        ".jpg",
        cv2.cvtColor(small, cv2.COLOR_RGB2BGR),
        [cv2.IMWRITE_JPEG_QUALITY, REVIEW_IMAGE_QUALITY],
    )
    return "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode()
