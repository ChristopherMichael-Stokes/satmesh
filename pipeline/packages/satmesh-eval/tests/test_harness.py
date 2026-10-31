import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from test_localise import (
    INTRINSICS,
    MAX_RANGE_M,
    PRIOR_OFFSET,
    embree_renderer,
    ground_only,
    truth_pose,
    with_buildings,
)

from satmesh_eval.camera import camera_centre_and_rotation
from satmesh_eval.harness import (
    FixStatus,
    Reference,
    ReferenceRenderers,
    RunResult,
    RunSettings,
    run_photos,
)
from satmesh_eval.localise_report import report_json
from satmesh_eval.matching import sift_match
from satmesh_eval.poses import PhotoRecord
from satmesh_eval.review_page import review_page

PHOTO_NAME = "synthetic.png"


def run(tmp_path: Path, references: tuple[Reference, ...], minimum_inliers: int) -> RunResult:
    scene = with_buildings()
    truth = truth_pose()
    photo = embree_renderer(scene)(INTRINSICS, truth, MAX_RANGE_M).rgb
    assert cv2.imwrite(str(tmp_path / PHOTO_NAME), cv2.cvtColor(photo, cv2.COLOR_RGB2BGR))
    record = PhotoRecord.model_validate(
        {
            "photo": PHOTO_NAME,
            "latitude_deg": truth.latitude_deg,
            "longitude_deg": truth.longitude_deg,
            "ellipsoidal_height_m": truth.ellipsoidal_height_m,
            "heading_deg": truth.heading_deg,
            "pitch_deg": truth.pitch_deg,
            "roll_deg": truth.roll_deg,
            "intrinsics": {
                "width_px": INTRINSICS.width_px,
                "height_px": INTRINSICS.height_px,
                "focal_x_px": INTRINSICS.focal_x_px,
                "focal_y_px": INTRINSICS.focal_y_px,
                "principal_x_px": INTRINSICS.principal_x_px,
                "principal_y_px": INTRINSICS.principal_y_px,
            },
        }
    )
    settings = RunSettings(
        ReferenceRenderers(scene, ground_only()),
        references,
        sift_match,
        "sift",
        prior_offset=PRIOR_OFFSET,
        minimum_inliers=minimum_inliers,
        max_range_m=MAX_RANGE_M,
    )
    return run_photos([record], tmp_path, settings)


def test_a_photo_is_localised_against_the_surface_and_reported(tmp_path: Path) -> None:
    result = run(tmp_path, (Reference.SURFACE, Reference.FLAT), minimum_inliers=30)

    surface, flat = result.photos[0].fixes
    assert surface.status == FixStatus.SOLVED
    assert surface.error is not None
    assert surface.error.within(0.25, 2.0)
    assert surface.pose is not None
    frame = with_buildings().frame
    centre, _ = camera_centre_and_rotation(surface.pose, frame)
    truth_centre, _ = camera_centre_and_rotation(truth_pose(), frame)
    assert np.linalg.norm(centre - truth_centre) == pytest.approx(
        surface.error.translation_m, abs=1e-6
    )
    assert surface.inlier_count is not None
    assert surface.inlier_count >= 30
    assert surface.reprojection_rmse_px is not None
    assert surface.at_true_pose is not None
    # the photo is a render of the same surface at the true pose; Embree and the GPU rasteriser
    # differ by sub-pixel sampling only
    assert surface.at_true_pose.median_displacement_px is not None
    assert surface.at_true_pose.median_displacement_px < 1.5
    assert flat.status != FixStatus.SKIPPED
    assert result.recall(Reference.SURFACE).recalled[0] == 1


def test_a_pose_below_the_inlier_minimum_is_rejected_with_its_inliers_kept(tmp_path: Path) -> None:
    result = run(tmp_path, (Reference.SURFACE,), minimum_inliers=100_000)

    (fix,) = result.photos[0].fixes
    assert fix.status == FixStatus.REJECTED
    assert (fix.pose, fix.error) == (None, None)
    assert fix.inlier_count is not None
    assert fix.inlier_count > 0
    assert result.recall(Reference.SURFACE).solved_count == 0


def test_the_report_and_review_page_carry_the_run(tmp_path: Path) -> None:
    result = run(tmp_path, (Reference.SURFACE,), minimum_inliers=30)

    report = json.loads(report_json(result))
    fix = report["photos"][0]["fixes"]["surface"]
    assert report["summary"]["surface"]["recalled"][0] == 1
    assert fix["status"] == "solved"
    assert set(fix) >= {"inliers", "reprojection_rmse_px", "pose", "error", "at_true_pose"}
    page = review_page(result)
    embedded = page.split("const D=", 1)[1].split(";\nconst $", 1)[0]
    data = json.loads(embedded)
    assert data["photos"][0]["photo"] == PHOTO_NAME
    assert data["photos"][0]["fixes"][0]["lines"]
    assert page.count("</script>") == 1
