import numpy as np
import pytest
import torch

from satmesh_height.config import PixTransformConfig
from satmesh_height.net import POSITION_CHANNELS
from satmesh_height.pixtransform import (
    cell_batches,
    cell_patches,
    ensemble,
    initial_net,
    predict,
    prepare_guide,
    refine,
    refine_area,
)

CPU = torch.device("cpu")
FAST = PixTransformConfig(steps=6, batch_size=4)


def smooth_scene(cells: int, factor: int) -> tuple[np.ndarray, np.ndarray]:
    """Source and 3-channel guide where the guide encodes the height."""
    side = cells * factor
    rows, cols = np.mgrid[0:side, 0:side].astype(np.float64)
    height = 10.0 + rows + 2.0 * np.sin(cols / 3.0)
    source = height.reshape(cells, factor, cells, factor).mean(axis=(1, 3))
    return source, np.stack([height, height**2, cols + rows])


def test_patches_equal_the_original_double_loop() -> None:
    channels, cells, factor = 4, 3, 5
    guide = torch.randn(channels, cells * factor, cells * factor)
    patches = cell_patches(guide, factor)
    reference = torch.zeros((cells * cells, channels, factor, factor))
    for i in range(cells):
        for j in range(cells):
            reference[j + i * cells] = guide[
                :, i * factor : (i + 1) * factor, j * factor : (j + 1) * factor
            ]
    for i in range(cells):
        for j in range(cells):
            assert torch.equal(patches[i, j], reference[j + i * cells])


def test_patches_share_memory_with_the_guide() -> None:
    guide = torch.zeros(2, 6, 6)
    cell_patches(guide, 3)[0, 0].fill_(1.0)
    assert guide[:, :3, :3].eq(1.0).all()
    assert guide[:, 3:, :].eq(0.0).all()


@pytest.mark.parametrize("chunk_rows", [1, 3, 5, 12])
def test_chunked_inference_equals_full_image_inference(chunk_rows: int) -> None:
    net = initial_net(guide_channels=3, seed=1)
    guide = torch.randn(3 + POSITION_CHANNELS, 12, 12)
    full = predict(net, guide, chunk_rows=12)
    chunked = predict(net, guide, chunk_rows=chunk_rows)
    # float32 sums over 2048 channels may differ in the last bits between batch shapes
    torch.testing.assert_close(chunked, full, rtol=1e-4, atol=1e-5)


def test_batches_cover_every_cell_each_pass_and_keep_the_partial_batch() -> None:
    generator = torch.Generator().manual_seed(0)
    batches = list(cell_batches(cell_count=10, batch_size=4, steps=6, generator=generator))
    assert [len(batch) for batch in batches] == [4, 4, 2, 4, 4, 2]
    for first, last in ((0, 3), (3, 6)):
        assert sorted(torch.cat(batches[first:last]).tolist()) == list(range(10))


def test_batches_stop_mid_pass_at_the_step_count() -> None:
    generator = torch.Generator().manual_seed(0)
    assert len(list(cell_batches(cell_count=10, batch_size=4, steps=2, generator=generator))) == 2


def test_prepared_guide_has_unit_channels_and_position_axes_in_ij_order() -> None:
    _, guide = smooth_scene(cells=3, factor=4)
    prepared = prepare_guide(guide, greyscale=False)
    assert prepared.shape == (3 + POSITION_CHANNELS, 12, 12)
    np.testing.assert_allclose(prepared[:3].mean(axis=(1, 2)), 0, atol=1e-12)
    np.testing.assert_allclose(prepared[:3].std(axis=(1, 2)), 1, atol=1e-12)
    np.testing.assert_allclose(prepared[3, :, 0], np.linspace(-0.5, 0.5, 12))
    np.testing.assert_allclose(prepared[3, 0, :], -0.5)
    np.testing.assert_allclose(prepared[4, 0, :], np.linspace(-0.5, 0.5, 12))


def test_greyscale_collapses_the_guide_to_one_channel() -> None:
    _, guide = smooth_scene(cells=3, factor=4)
    assert prepare_guide(guide, greyscale=True).shape[0] == 1 + POSITION_CHANNELS


def test_same_seed_gives_identical_output_and_different_seeds_differ() -> None:
    source, guide = smooth_scene(cells=4, factor=3)
    first = refine(source, guide, FAST, seed=3, device=CPU)
    again = refine(source, guide, FAST, seed=3, device=CPU)
    other = refine(source, guide, FAST, seed=4, device=CPU)
    assert first.dtype == np.float32
    assert first.shape == (12, 12)
    np.testing.assert_array_equal(first, again)
    assert not np.allclose(first, other)


def test_training_pulls_cell_means_toward_the_source() -> None:
    source, guide = smooth_scene(cells=4, factor=3)
    untrained = refine(source, guide, PixTransformConfig(steps=1, batch_size=4), seed=0, device=CPU)
    trained = refine(source, guide, PixTransformConfig(steps=300, batch_size=4), seed=0, device=CPU)

    def cell_error(fine: np.ndarray) -> float:
        means = fine.astype(np.float64).reshape(4, 3, 4, 3).mean(axis=(1, 3))
        return float(np.abs(means - source).mean())

    assert cell_error(trained) < 0.25 * cell_error(untrained)


def test_refine_rejects_a_constant_source() -> None:
    _, guide = smooth_scene(cells=2, factor=3)
    with pytest.raises(ValueError, match="constant"):
        refine(np.ones((2, 2)), guide, FAST, seed=0, device=CPU)


def test_area_windows_are_refined_independently_and_stitched() -> None:
    source, guide = smooth_scene(cells=4, factor=3)
    area = refine_area(source, guide, 3, 6, FAST, seed=2, device=CPU)
    corner = refine(source[2:, :2], guide[:, 6:, :6], FAST, seed=2, device=CPU)
    np.testing.assert_array_equal(area[6:, :6], corner)


def test_area_rejects_an_extent_that_does_not_divide_it() -> None:
    source, guide = smooth_scene(cells=4, factor=3)
    with pytest.raises(ValueError, match="does not divide"):
        refine_area(source, guide, 3, 9, FAST, seed=0, device=CPU)
    with pytest.raises(ValueError, match="multiple of factor"):
        refine_area(source, guide, 3, 4, FAST, seed=0, device=CPU)


def test_ensemble_is_the_per_pixel_mean_and_population_standard_deviation() -> None:
    outputs = [np.full((2, 2), value, np.float32) for value in (1.0, 3.0, 5.0)]
    mean, spread = ensemble(outputs)
    np.testing.assert_allclose(mean, 3.0)
    np.testing.assert_allclose(spread, np.sqrt(8.0 / 3.0))
