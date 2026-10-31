"""JSON report of a localisation run: per photo and reference, and recall over the set.

Each fix carries what a later motion model needs to weigh it: status, inlier count, reprojection
residual and the pose with its attitude angles. Angles are degrees, distances metres, heights
ellipsoidal (WGS 84). The report holds no images.
"""

import json
from dataclasses import asdict
from typing import Any

from satmesh_eval.camera import CameraPose
from satmesh_eval.harness import Fix, PhotoResult, RunResult
from satmesh_eval.localise import RECALL_THRESHOLDS
from satmesh_eval.metrics import RecallSummary

JSON_INDENT = 2


def report_json(result: RunResult) -> str:
    """The run as indented JSON."""
    return json.dumps(report_dict(result), indent=JSON_INDENT)


def report_dict(result: RunResult) -> dict[str, Any]:
    """The run as plain dicts and lists."""
    return {
        "matcher": result.matcher,
        "minimum_inliers": result.minimum_inliers,
        "max_range_m": result.max_range_m,
        "recall_thresholds": [
            {"translation_m": metres, "rotation_deg": degrees}
            for metres, degrees in RECALL_THRESHOLDS
        ],
        "summary": {
            reference.value: _summary(result.recall(reference)) for reference in result.references
        },
        "photos": [_photo(photo) for photo in result.photos],
    }


def _summary(recall: RecallSummary) -> dict[str, Any]:
    return {
        "photos": recall.photo_count,
        "solved": recall.solved_count,
        "recalled": list(recall.recalled),
        "median_translation_m": recall.median_translation_m,
        "median_rotation_deg": recall.median_rotation_deg,
    }


def _photo(photo: PhotoResult) -> dict[str, Any]:
    return {
        "photo": photo.photo,
        "true_pose": asdict(photo.truth),
        "prior_pose": asdict(photo.prior),
        "fixes": {fix.reference.value: _fix(fix) for fix in photo.fixes},
    }


def _fix(fix: Fix) -> dict[str, Any]:
    return {
        "status": fix.status.value,
        "note": fix.note,
        "matches": fix.match_count,
        "inliers": fix.inlier_count,
        "reprojection_rmse_px": fix.reprojection_rmse_px,
        "pose": _pose(fix.pose),
        "error": asdict(fix.error) if fix.error else None,
        "at_true_pose": asdict(fix.at_true_pose) if fix.at_true_pose else None,
    }


def _pose(pose: CameraPose | None) -> dict[str, Any] | None:
    return asdict(pose) if pose else None
