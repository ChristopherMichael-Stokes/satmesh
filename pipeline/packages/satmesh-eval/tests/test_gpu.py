import math

import numpy as np
import pytest
import wgpu
from test_perspective import (
    CAMERA_HEIGHT_M,
    CENTRE_COL,
    CENTRE_ROW,
    FOCAL_PX,
    INTRINSICS,
    MAX_RANGE_M,
    ground_scene,
    pose,
)
from trimesh.creation import box

from satmesh_eval.camera import CameraPose, Intrinsics
from satmesh_eval.gpu import GpuRenderer
from satmesh_eval.perspective import AreaScene, SceneLeaf, render

RANGE_TOLERANCE_M = (
    1e-3  # float32 vertex positions at tens of metres, fixed-point range step 0.03 mm
)
COLOUR_TOLERANCE_LEVELS = 3  # trilinear sampling of a linear gradient, plus 8-bit rounding
AGREEMENT_FRACTION = 0.999  # pixels on triangle edges may land on either side
EMBREE_DEPTH_TOLERANCE_M = 0.05


@pytest.fixture(scope="module")
def adapter_available() -> None:
    try:
        wgpu.gpu.request_adapter_sync()
    except RuntimeError as error:
        pytest.skip(f"no wgpu adapter: {error}")


@pytest.mark.usefixtures("adapter_available")
def test_nadir_depths_match_the_analytic_range_and_z_depth() -> None:
    result = GpuRenderer(ground_scene()).render(INTRINSICS, pose(), MAX_RANGE_M)

    assert result.hit_mask.all()
    assert result.depth_m[CENTRE_ROW, CENTRE_COL] == pytest.approx(
        CAMERA_HEIGHT_M, abs=RANGE_TOLERANCE_M
    )
    row, col = CENTRE_ROW + 5, CENTRE_COL + 10
    tangent_squared = (10.0**2 + 5.0**2) / FOCAL_PX**2
    assert result.depth_m[row, col] == pytest.approx(
        CAMERA_HEIGHT_M * math.sqrt(1 + tangent_squared), abs=RANGE_TOLERANCE_M
    )
    assert result.z_depth_m[row, col] == pytest.approx(CAMERA_HEIGHT_M, abs=RANGE_TOLERANCE_M)


@pytest.mark.usefixtures("adapter_available")
def test_off_centre_principal_point_moves_the_optical_axis_pixel() -> None:
    shifted = Intrinsics(65, 49, FOCAL_PX, FOCAL_PX, 10.5, 40.5, ())

    result = GpuRenderer(ground_scene()).render(shifted, pose(), MAX_RANGE_M)

    assert result.depth_m[40, 10] == pytest.approx(CAMERA_HEIGHT_M, abs=RANGE_TOLERANCE_M)


@pytest.mark.usefixtures("adapter_available")
def test_hits_beyond_max_range_are_misses() -> None:
    result = GpuRenderer(ground_scene()).render(INTRINSICS, pose(), CAMERA_HEIGHT_M - 1.0)

    assert not result.hit_mask.any()
    assert np.isnan(result.depth_m).all()
    assert (result.rgb == 0).all()


@pytest.mark.usefixtures("adapter_available")
def test_distorted_intrinsics_are_refused() -> None:
    distorted = Intrinsics(65, 49, FOCAL_PX, FOCAL_PX, 32.5, 24.5, (-0.1, 0.01))

    with pytest.raises(ValueError, match="pinhole"):
        GpuRenderer(ground_scene()).render(distorted, pose(), MAX_RANGE_M)


@pytest.mark.usefixtures("adapter_available")
def test_a_nearer_box_hides_the_ground_and_a_width_off_the_row_alignment_reads_back_whole() -> None:
    ground = ground_scene()
    block = box(extents=(10.0, 10.0, 10.0))
    solid_red = np.zeros((2, 2, 3), np.uint8)
    solid_red[..., 0] = 200
    leaf = SceneLeaf(block, np.zeros((len(block.vertices), 2)), solid_red)
    scene = AreaScene((*ground.leaves, leaf), ground.frame)

    result = GpuRenderer(scene).render(INTRINSICS, pose(), MAX_RANGE_M)

    assert result.depth_m[CENTRE_ROW, CENTRE_COL] == pytest.approx(
        CAMERA_HEIGHT_M - 5.0, abs=RANGE_TOLERANCE_M
    )
    assert result.rgb[CENTRE_ROW, CENTRE_COL].tolist() == [200, 0, 0]


@pytest.mark.usefixtures("adapter_available")
def test_oblique_render_agrees_with_the_ray_traced_render() -> None:
    ground = ground_scene()
    block = box(extents=(10.0, 10.0, 10.0), transform=np.diag([1, 1, 1, 1.0]))
    block.apply_translation((12.0, 25.0, 0.0))
    solid_red = np.zeros((2, 2, 3), np.uint8)
    solid_red[..., 0] = 200
    leaf = SceneLeaf(block, np.zeros((len(block.vertices), 2)), solid_red)
    scene = AreaScene((*ground.leaves, leaf), ground.frame)
    oblique = CameraPose(
        pose().latitude_deg, pose().longitude_deg, pose().ellipsoidal_height_m, 10.0, -30.0, 4.0
    )
    wide = Intrinsics(160, 120, 100.0, 100.0, 80.0, 60.0, ())

    gpu = GpuRenderer(scene).render(wide, oblique, MAX_RANGE_M)
    reference = render(scene, wide, oblique, MAX_RANGE_M)

    assert (gpu.hit_mask == reference.hit_mask).mean() >= AGREEMENT_FRACTION
    both = gpu.hit_mask & reference.hit_mask
    depth_close = np.abs(gpu.depth_m - reference.depth_m)[both] <= EMBREE_DEPTH_TOLERANCE_M
    assert depth_close.mean() >= AGREEMENT_FRACTION
    colour_error = np.abs(gpu.rgb.astype(int) - reference.rgb.astype(int))[both]
    assert np.median(colour_error) <= COLOUR_TOLERANCE_LEVELS
