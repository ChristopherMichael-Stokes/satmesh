from pathlib import Path

import laspy
import numpy as np

from satmesh_core import BRITISH_NATIONAL_GRID, Aoi
from satmesh_eval.lidar_reference import CLASS_NOISE, read_first_return_intensity

MARGIN_M = 5.0


def box(west: float, south: float, east: float, north: float) -> Aoi:
    return Aoi(crs=BRITISH_NATIONAL_GRID, west=west, south=south, east=east, north=north)


def write_cloud(path: Path, x: list[float], y: list[float], *, kind: list[str]) -> None:
    """Points with intensity 100, 101, ...; kind is "first", "second" return or "noise"."""
    header = laspy.LasHeader(point_format=1, version="1.2")
    header.scales = np.array([0.01, 0.01, 0.01])
    las = laspy.LasData(header)
    las.x, las.y, las.z = np.array(x), np.array(y), np.zeros(len(x))
    las.intensity = 100 + np.arange(len(x))
    las.return_number = np.array([2 if k == "second" else 1 for k in kind])
    las.number_of_returns = np.full(len(x), 2)
    las.classification = np.array([CLASS_NOISE if k == "noise" else 2 for k in kind])
    las.write(str(path))


def test_each_box_gets_its_first_returns_in_file_order_and_noise_is_dropped(tmp_path: Path) -> None:
    path = tmp_path / "cloud.laz"
    write_cloud(
        path,
        x=[10, 12, 30, 32, 11, 50, 13],
        y=[10, 11, 10, 12, 10, 10, 12],
        kind=["first", "first", "first", "first", "second", "first", "noise"],
    )
    left, right = box(0, 0, 20, 20), box(25, 0, 40, 20)
    (left_xy, left_intensity), (right_xy, right_intensity) = read_first_return_intensity(
        [path], [left, right], MARGIN_M
    )
    assert left_xy.tolist() == [[10, 10], [12, 11]]
    assert left_intensity.tolist() == [100, 101]
    assert right_xy.tolist() == [[30, 10], [32, 12]]
    assert right_intensity.tolist() == [102, 103]


def test_points_within_the_margin_of_a_box_edge_are_kept(tmp_path: Path) -> None:
    path = tmp_path / "cloud.laz"
    write_cloud(path, x=[22, 26], y=[10, 10], kind=["first", "first"])
    ((xy, _),) = read_first_return_intensity([path], [box(0, 0, 20, 20)], MARGIN_M)
    assert xy.tolist() == [[22, 10]]
