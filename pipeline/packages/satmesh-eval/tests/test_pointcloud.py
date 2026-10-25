from pathlib import Path

import laspy
import numpy as np
import pytest
from rasterio.transform import from_origin

from satmesh_core import Aoi
from satmesh_eval.pointcloud import (
    CLASS_NOISE,
    FirstReturns,
    height_error_at_points,
    read_first_returns,
    split_holdout,
)
from satmesh_eval.visibility import raster_mesh


def _write_laz(path: Path) -> None:
    header = laspy.LasHeader(point_format=1, version="1.2")
    header.scales = np.array([0.01, 0.01, 0.01])
    las = laspy.LasData(header)
    las.x = np.array([10.0, 10.0, 20.0, 30.0, 500.0])
    las.y = np.array([10.0, 10.0, 20.0, 30.0, 500.0])
    las.z = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    las.return_number = np.array([1, 2, 1, 1, 1])
    las.number_of_returns = np.array([2, 2, 1, 1, 1])
    las.classification = np.array([2, 5, 6, CLASS_NOISE, 2])
    las.write(str(path))


def test_only_first_returns_inside_the_box_and_not_noise_are_read(tmp_path: Path) -> None:
    path = tmp_path / "cloud.laz"
    _write_laz(path)
    box = Aoi(crs="EPSG:27700", west=0, south=0, east=100, north=100)
    points = read_first_returns(path, box)
    assert points.xyz[:, 2].tolist() == [1.0, 3.0]
    assert points.classification.tolist() == [2, 6]


def test_holdout_is_disjoint_and_complete() -> None:
    rng = np.random.default_rng(0)
    points = FirstReturns(rng.random((1000, 3)), np.full(1000, 2))
    kept, held = split_holdout(points, 0.1, seed=1)
    assert len(kept.xyz) + len(held.xyz) == 1000
    assert 70 < len(held.xyz) < 130


def test_height_error_is_mesh_height_over_the_point_between_vertices() -> None:
    ramp = np.tile(np.arange(10.0), (10, 1))  # rises 1 m per metre eastward
    mesh = raster_mesh(ramp, from_origin(0.0, 10.0, 1.0, 1.0))
    # x = 4.25 lies between vertices at 4.0 and 5.0 (pixel centres 3.5 and 4.5): mesh height 3.75
    error = height_error_at_points(mesh, np.array([[4.25, 5.0, 3.0], [50.0, 5.0, 0.0]]))
    assert error[0] == pytest.approx(0.75)
    assert np.isnan(error[1])
