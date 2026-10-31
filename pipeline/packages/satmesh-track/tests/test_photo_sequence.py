from pathlib import Path

import cv2
import numpy as np
import pytest

from satmesh_track.photos import list_photos, load_photo


def write(path: Path, width: int, height: int) -> None:
    assert cv2.imwrite(str(path), np.full((height, width, 3), 120, dtype=np.uint8))


def test_photos_are_ordered_by_name_with_digit_runs_as_numbers(tmp_path: Path) -> None:
    for name in ("IMG_10.jpg", "IMG_2.jpg", "IMG_1.png", "notes.txt"):
        (tmp_path / name).write_bytes(b"x")

    assert [p.name for p in list_photos(tmp_path)] == ["IMG_1.png", "IMG_2.jpg", "IMG_10.jpg"]


def test_a_directory_without_images_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no images"):
        list_photos(tmp_path)


def test_a_large_photo_is_reduced_to_the_working_size_and_remembers_the_original(
    tmp_path: Path,
) -> None:
    write(tmp_path / "big.png", 2560, 1920)

    photo = load_photo(tmp_path / "big.png")

    assert photo.image.rgb.shape == (960, 1280, 3)
    assert (photo.original_width_px, photo.original_height_px) == (2560, 1920)
    assert photo.scale_to_original == pytest.approx(2.0)


def test_a_small_photo_is_kept_as_it_is(tmp_path: Path) -> None:
    write(tmp_path / "small.png", 640, 480)

    photo = load_photo(tmp_path / "small.png")

    assert photo.image.rgb.shape == (480, 640, 3)
    assert photo.scale_to_original == 1.0


def test_an_unreadable_file_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "bad.png").write_bytes(b"not an image")

    with pytest.raises(ValueError, match="cannot read"):
        load_photo(tmp_path / "bad.png")
