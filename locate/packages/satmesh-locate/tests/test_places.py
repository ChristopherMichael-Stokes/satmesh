from pathlib import Path

import numpy as np
import pytest

from satmesh_locate.places import Cells, iter_render_chunks, load_cells, top_places

SEPARATION_M = 100.0


def cells_on_a_line(east: list[float]) -> Cells:
    n = len(east)
    zeros = np.zeros(n)
    return Cells(np.array(east), zeros, zeros + 10.0, zeros + 70.0, zeros + 90.0, zeros - 35.0)


def test_places_are_the_best_views_more_than_the_separation_apart() -> None:
    cells = cells_on_a_line([0.0, 50.0, 150.0, 160.0])
    similarity = np.array([0.9, 0.8, 0.7, 0.95], dtype=np.float32)

    places = top_places(similarity, cells, count=3, separation_m=SEPARATION_M)

    # 160 m wins; 0 m is 160 m away and stays; 50 m is 50 m from 0 m; 150 m is 10 m from 160 m
    assert [p.east for p in places] == [160.0, 0.0]
    assert places[0].similarity == pytest.approx(0.95)
    assert (places[0].ground, places[0].height, places[0].heading, places[0].pitch) == (
        10.0,
        70.0,
        90.0,
        -35.0,
    )


def test_a_view_exactly_at_the_separation_is_skipped() -> None:
    cells = cells_on_a_line([0.0, SEPARATION_M, 2 * SEPARATION_M + 1.0])
    similarity = np.array([0.9, 0.8, 0.7], dtype=np.float32)

    places = top_places(similarity, cells, count=3, separation_m=SEPARATION_M)

    assert [p.east for p in places] == [0.0, 2 * SEPARATION_M + 1.0]


def test_cells_and_renders_are_read_in_the_order_written(tmp_path: Path) -> None:
    meta = np.arange(12, dtype=np.float64).reshape(2, 6)
    np.save(tmp_path / "meta.npy", meta)
    first, second = np.zeros((1, 2, 2, 3), np.uint8), np.ones((2, 2, 2, 3), np.uint8)
    np.save(tmp_path / "renders_000.npy", first)
    np.save(tmp_path / "renders_001.npy", second)

    cells = load_cells(tmp_path)
    chunks = list(iter_render_chunks(tmp_path))

    assert cells.east.tolist() == [0.0, 6.0]
    assert cells.pitch.tolist() == [5.0, 11.0]
    assert [len(c) for c in chunks] == [1, 2]
    assert chunks[1][0].max() == 1


def test_cells_with_the_wrong_column_count_are_rejected(tmp_path: Path) -> None:
    np.save(tmp_path / "meta.npy", np.zeros((3, 5)))

    with pytest.raises(ValueError, match="6 columns"):
        load_cells(tmp_path)
