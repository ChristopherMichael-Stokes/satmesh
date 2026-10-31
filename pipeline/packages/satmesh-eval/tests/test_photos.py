from pathlib import Path

import cv2
import numpy as np
import pytest

from satmesh_eval.camera import Intrinsics
from satmesh_eval.photos import WORKING_LONG_SIDE_PX, load_working_photo

BYTE_MAX = 255.0


def blotchy(width: int, height: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal((height, width, 3)).astype(np.float32)
    smooth = cv2.GaussianBlur(noise, (0, 0), 6.0)
    scaled = (smooth - smooth.min()) / (smooth.max() - smooth.min())
    return np.rint(BYTE_MAX * scaled).astype(np.uint8)


def save(path: Path, rgb: np.ndarray) -> None:
    assert cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


def test_a_pinhole_photo_at_working_size_is_returned_unchanged(tmp_path: Path) -> None:
    rgb = blotchy(640, 480)
    save(tmp_path / "p.png", rgb)
    intrinsics = Intrinsics(640, 480, 400.0, 400.0, 320.0, 240.0, ())

    photo = load_working_photo(tmp_path / "p.png", intrinsics)

    assert np.array_equal(photo.image, rgb)
    assert photo.intrinsics == intrinsics


def test_a_large_photo_is_reduced_with_its_intrinsics_scaled_by_the_same_factor(
    tmp_path: Path,
) -> None:
    save(tmp_path / "p.png", blotchy(2560, 1920))
    intrinsics = Intrinsics(2560, 1920, 1800.0, 1800.0, 1290.0, 950.0, ())

    photo = load_working_photo(tmp_path / "p.png", intrinsics)

    assert photo.image.shape[:2] == (960, 1280)
    assert max(photo.image.shape[:2]) == WORKING_LONG_SIDE_PX * 960 // 1280 * 4 // 3
    assert (photo.intrinsics.focal_x_px, photo.intrinsics.principal_x_px) == (900.0, 645.0)
    assert (photo.intrinsics.focal_y_px, photo.intrinsics.principal_y_px) == (900.0, 475.0)


def test_undistortion_inverts_the_opencv_radial_model(tmp_path: Path) -> None:
    width, height, focal, k1 = 640, 480, 400.0, -0.2
    ideal = blotchy(width, height, seed=3)
    # the distorted photo samples the ideal image where the model sends each distorted pixel:
    # normalised ideal x = x_d / (1 + k1 r_d^2) solved by fixed-point iteration, written here
    # independently of the loader
    columns, rows = np.meshgrid(np.arange(width), np.arange(height))
    x_d = (columns - width / 2) / focal
    y_d = (rows - height / 2) / focal
    x, y = x_d.copy(), y_d.copy()
    for _ in range(50):
        scale = 1.0 + k1 * (x**2 + y**2)
        x, y = x_d / scale, y_d / scale
    distorted = cv2.remap(
        ideal,
        (x * focal + width / 2).astype(np.float32),
        (y * focal + height / 2).astype(np.float32),
        cv2.INTER_LINEAR,
    )
    save(tmp_path / "p.png", distorted)
    intrinsics = Intrinsics(width, height, focal, focal, width / 2, height / 2, (k1, 0.0))

    photo = load_working_photo(tmp_path / "p.png", intrinsics)

    centre = (slice(100, 380), slice(140, 500))  # away from borders where sampling leaves the image
    difference = np.abs(photo.image[centre].astype(float) - ideal[centre].astype(float))
    # two bilinear resamplings of a smooth field
    assert np.mean(difference) < 3.0
    assert photo.intrinsics.radial_distortion == ()


def test_a_photo_of_the_wrong_size_is_an_error(tmp_path: Path) -> None:
    save(tmp_path / "p.png", blotchy(640, 480))

    with pytest.raises(ValueError, match="640 x 480"):
        load_working_photo(tmp_path / "p.png", Intrinsics(800, 600, 400.0, 400.0, 400.0, 300.0, ()))


def test_an_unreadable_file_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "p.png").write_bytes(b"not an image")

    with pytest.raises(ValueError, match="cannot read"):
        load_working_photo(tmp_path / "p.png", Intrinsics(8, 8, 4.0, 4.0, 4.0, 4.0, ()))
