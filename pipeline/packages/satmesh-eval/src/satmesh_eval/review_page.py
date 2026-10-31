"""Self-contained HTML review page of a localisation run: recall table, then every photo.

Images are embedded as JPEG data URIs, so the page is one file.
"""

import base64
import json
from dataclasses import asdict
from importlib.resources import files
from typing import Any

from satmesh_eval.camera import CameraPose
from satmesh_eval.harness import Fix, PhotoResult, Reference, RunResult
from satmesh_eval.localise import RECALL_THRESHOLDS
from satmesh_eval.localise_report import report_dict

TEMPLATE_NAME = "localise_review.html"
DATA_PLACEHOLDER = "__DATA__"
REFERENCE_NAMES = {
    Reference.SURFACE: "Full-surface render (DSM)",
    Reference.GROUND: "Bare-earth render (DTM)",
    Reference.FLAT: "Flat ortho in the photo view",
    Reference.TOP_DOWN: "Photo warped to top-down",
}
CAVEAT = (
    "Errors are against the pose file's pose, so they include any error in that pose and in the "
    "georegistration of the mesh. Where no prior is given the reference is rendered from the true "
    "pose displaced by the run's fixed offset."
)


def review_page(result: RunResult) -> str:
    """The run's review page as an HTML document."""
    template = files("satmesh_eval").joinpath(TEMPLATE_NAME).read_text()
    summary = report_dict(result)["summary"]
    data = {
        "matcher": result.matcher,
        "minimum_inliers": result.minimum_inliers,
        "max_range_m": result.max_range_m,
        "thresholds": [list(threshold) for threshold in RECALL_THRESHOLDS],
        "references": [reference.value for reference in result.references],
        "names": {reference.value: REFERENCE_NAMES[reference] for reference in Reference},
        "summary": summary,
        "caveat": CAVEAT,
        "photos": [_photo(photo) for photo in result.photos],
    }
    embedded = json.dumps(data).replace("</", "<\\/")  # a script body must not close early
    return template.replace(DATA_PLACEHOLDER, embedded)


def _photo(photo: PhotoResult) -> dict[str, Any]:
    return {
        "photo": photo.photo,
        "truth": _pose_text(photo.truth),
        "prior": _pose_text(photo.prior),
        "photo_img": _data_uri(photo.photo_jpeg),
        "fixes": [_fix(fix, photo.photo_jpeg) for fix in photo.fixes],
    }


def _fix(fix: Fix, photo_jpeg: bytes) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "reference": fix.reference.value,
        "status": fix.status.value,
        "note": fix.note,
        "matches": fix.match_count,
        "inliers": fix.inlier_count,
        "rmse": fix.reprojection_rmse_px,
        "error": asdict(fix.error) if fix.error else None,
        "known": asdict(fix.at_true_pose) if fix.at_true_pose else None,
    }
    if fix.panels is None:
        return entry
    panels = fix.panels
    entry |= {
        "photo_view": None
        if panels.photo_view_jpeg == photo_jpeg
        else _data_uri(panels.photo_view_jpeg),
        "reference_img": _data_uri(panels.reference_jpeg),
        "depth": _data_uri(panels.depth_jpeg),
        "depth_range": list(panels.depth_range_m),
        "lines": [
            [
                line.photo_x,
                line.photo_y,
                line.reference_x,
                line.reference_y,
                line.agrees_with_true_pose,
            ]
            for line in panels.lines
        ],
    }
    return entry


def _pose_text(pose: CameraPose) -> str:
    return (
        f"{pose.latitude_deg:.6f}, {pose.longitude_deg:.6f}, {pose.ellipsoidal_height_m:.2f} m, "
        f"heading {pose.heading_deg:.1f}°, pitch {pose.pitch_deg:.1f}°, roll {pose.roll_deg:.1f}°"
    )


def _data_uri(jpeg: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
