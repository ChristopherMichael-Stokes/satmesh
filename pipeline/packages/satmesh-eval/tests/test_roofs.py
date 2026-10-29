import numpy as np
import pytest

from satmesh_core import BRITISH_NATIONAL_GRID, Aoi
from satmesh_eval.offset import GRID_M
from satmesh_eval.roofs import LIDAR_GRID_M, roof_offsets

SIDE_M = 240
BOX = Aoi(crs=BRITISH_NATIONAL_GRID, west=500_000, south=200_000, east=500_240, north=200_240)
GROUND_M = 12.0
GROUND_LUMA, ROOF_LUMA = 90.0, 200.0
LATTICE_M = 40
FOOTPRINT_M = (14, 9)
# largest error measured on these scenes was 0.004 m (parabolic subpixel peak on a 0.25 m grid)
SHIFT_TOLERANCE_M = 0.02


def coverage_1d(start: float, stop: float, pixels: int, pixel_m: float) -> np.ndarray:
    """Share of each pixel [i, i + 1) * pixel_m covered by the interval [start, stop)."""
    edges = np.arange(pixels) * pixel_m
    return np.clip(np.minimum(stop, edges + pixel_m) - np.maximum(start, edges), 0, pixel_m) / (
        pixel_m
    )


def scene(
    buildings: list[tuple[int, int, float, float, float]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """DSM, DTM and an Esri luma whose roof `i` is drawn displaced by (east_i, north_i) metres.

    Each building is (east, down, height, east shift, north shift) with east and down the
    footprint's north-west corner in metres from the box's north-west corner.
    """
    lidar_px = round(SIDE_M / LIDAR_GRID_M)
    luma_px = round(SIDE_M / GRID_M)
    ground = np.full((lidar_px, lidar_px), GROUND_M)
    surface = ground.copy()
    luma = np.full((luma_px, luma_px), GROUND_LUMA)
    width, depth = FOOTPRINT_M
    for east, down, height, shift_east, shift_north in buildings:
        surface[down : down + depth, east : east + width] += height
        cols = coverage_1d(east + shift_east, east + width + shift_east, luma_px, GRID_M)
        rows = coverage_1d(down - shift_north, down + depth - shift_north, luma_px, GRID_M)
        luma += (ROOF_LUMA - GROUND_LUMA) * np.outer(rows, cols)
    return surface, ground, luma


def test_each_roof_reports_its_own_displacement_and_eave_height() -> None:
    rng = np.random.default_rng(3)
    buildings = [
        (east, down, float(rng.uniform(4, 20)), *rng.uniform(-2.5, 2.5, 2))
        for east in range(20, SIDE_M - 30, LATTICE_M)
        for down in range(20, SIDE_M - 30, LATTICE_M)
    ]
    surface, ground, luma = scene(buildings)

    offsets = roof_offsets(surface, ground, luma, BOX)

    assert len(offsets) == len(buildings)
    width, depth = FOOTPRINT_M
    by_centre = {
        (BOX.west + east + width / 2, BOX.north - down - depth / 2): (height, de, dn)
        for east, down, height, de, dn in buildings
    }
    for roof in offsets:
        height, shift_east, shift_north = by_centre[roof.easting_m, roof.northing_m]
        # flat roofs: every percentile of the roof height is the height itself
        assert roof.eave_height_m == pytest.approx(height)
        assert roof.east_m == pytest.approx(shift_east, abs=SHIFT_TOLERANCE_M)
        assert roof.north_m == pytest.approx(shift_north, abs=SHIFT_TOLERANCE_M)


def test_tree_crowns_and_buildings_cut_by_the_box_edge_are_skipped() -> None:
    rng = np.random.default_rng(5)
    surface, ground, luma = scene([(100, 100, 8.0, 1.0, 0.5)])
    crown = (slice(30, 45), slice(30, 45))
    surface[crown] = GROUND_M + rng.uniform(4, 12, (15, 15))
    surface[0:10, 150:165] = GROUND_M + 6.0

    offsets = roof_offsets(surface, ground, luma, BOX)

    width, depth = FOOTPRINT_M
    assert [(r.easting_m, r.northing_m) for r in offsets] == [
        (BOX.west + 100 + width / 2, BOX.north - 100 - depth / 2)
    ]
