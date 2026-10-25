import numpy as np
import pytest
from rasterio.transform import from_origin

from satmesh_eval.mesh_score import surface_height_error
from satmesh_eval.visibility import raster_mesh

TRANSFORM = from_origin(1000.0, 2040.0, 1.0, 1.0)


def test_error_of_a_mesh_is_its_height_over_the_reference_at_every_pixel() -> None:
    reference = np.full((40, 40), 100.0)
    reference[10:20, 10:20] = 105.0
    mesh = raster_mesh(reference + 0.25, TRANSFORM)
    error = surface_height_error(mesh, reference, TRANSFORM, margin_px=1)
    assert np.nanmax(np.abs(error - 0.25)) < 1e-9
    assert np.isnan(error[0, :]).all()
    assert np.isfinite(error[1:-1, 1:-1]).all()


def test_a_mesh_that_smooths_a_spike_shows_the_lost_height_at_the_spike() -> None:
    reference = np.full((40, 40), 100.0)
    reference[20, 20] = 110.0
    smoothed = reference.copy()
    smoothed[20, 20] = 100.0
    error = surface_height_error(raster_mesh(smoothed, TRANSFORM), reference, TRANSFORM)
    assert error[20, 20] == pytest.approx(-10.0)
    assert np.count_nonzero(np.abs(error) > 1e-9) == 1
