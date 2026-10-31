"""Read a directory of photos in order, at the size the tracker works at.

Photos are ordered by file name with digit runs compared as numbers (`2.jpg` before `10.jpg`).
Large photos are reduced so the long side is `WORKING_LONG_SIDE_PX`; the lens is estimated at that
size and scaled back to the originals' pixels when written.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from satmesh_eval.photos import WORKING_LONG_SIDE_PX
from satmesh_track.tracker import PhotoImage

IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".tif", ".tiff"})
DIGIT_RUN = re.compile(r"(\d+)")


@dataclass(frozen=True)
class LoadedPhoto:
    """A photo at working size and the size of the file it came from."""

    image: PhotoImage
    original_width_px: int
    original_height_px: int

    @property
    def scale_to_original(self) -> float:
        """Original pixels per working pixel."""
        return self.original_width_px / int(self.image.rgb.shape[1])


def list_photos(directory: Path) -> list[Path]:
    """Image files of `directory` in natural name order; raises `ValueError` if there are none."""
    paths = sorted(
        (p for p in directory.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES),
        key=lambda p: [int(t) if t.isdigit() else t.lower() for t in DIGIT_RUN.split(p.name)],
    )
    if not paths:
        msg = f"no images in {directory}"
        raise ValueError(msg)
    return paths


def load_photo(path: Path) -> LoadedPhoto:
    """Read one photo as RGB, reduced to the working size; raises `ValueError` if unreadable."""
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        msg = f"cannot read image {path}"
        raise ValueError(msg)
    height, width = (int(side) for side in bgr.shape[:2])
    rgb = np.asarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), dtype=np.uint8)
    scale = WORKING_LONG_SIDE_PX / max(width, height)
    if scale < 1.0:
        size = (round(width * scale), round(height * scale))
        rgb = np.asarray(cv2.resize(rgb, size, interpolation=cv2.INTER_AREA), dtype=np.uint8)
    return LoadedPhoto(PhotoImage(path.name, rgb), width, height)
