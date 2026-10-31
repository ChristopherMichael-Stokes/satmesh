import numpy as np

from satmesh_eval.grey import write_grey

MAX_PIXEL = 255.0
FLOAT32_RELATIVE_TOLERANCE = 2e-7  # one float32 rounding of the quotient is 6e-8 relative


def test_a_pixel_becomes_the_mean_of_its_channels_scaled_to_unit_range() -> None:
    rgb = np.array([[[30, 60, 90], [255, 255, 255], [0, 0, 0], [255, 0, 0]]], dtype=np.uint8)
    destination = np.zeros((1, 4), dtype=np.float32)

    write_grey(rgb, destination)

    expected = np.array([60.0, 255.0, 0.0, 85.0]) / MAX_PIXEL
    np.testing.assert_allclose(destination[0], expected, rtol=FLOAT32_RELATIVE_TOLERANCE)


def test_a_random_image_matches_the_float64_mean() -> None:
    rgb = np.random.default_rng(0).integers(0, 256, size=(37, 53, 3), dtype=np.uint8)
    destination = np.zeros((37, 53), dtype=np.float32)

    write_grey(rgb, destination)

    expected = rgb.astype(np.float64).sum(axis=2) / 3.0 / MAX_PIXEL
    np.testing.assert_allclose(destination, expected, rtol=FLOAT32_RELATIVE_TOLERANCE)


def test_writing_into_a_window_of_a_canvas_leaves_the_margin_alone() -> None:
    rgb = np.full((4, 6, 3), 255, dtype=np.uint8)
    canvas = np.zeros((8, 10), dtype=np.float32)

    write_grey(rgb, canvas[2:6, 2:8])

    assert canvas[2:6, 2:8].min() == 1.0
    assert canvas.sum() == 4 * 6
