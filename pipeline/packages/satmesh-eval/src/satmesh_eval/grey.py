"""Grey-level model input from an RGB image: channel mean and scaling in one pass over the pixels.

`rgb.astype(float32).mean(axis=2) / 255` makes a float32 copy of the image, a reduction and a
second array; the kernel here writes the same float32 values straight into the destination, with the
same operation order (float32 sum of the channels, divided by 3, divided by 255), so results are
bit-identical.
"""

import numba
import numpy as np
import numpy.typing as npt
from xfeat_pairs.preprocess import MAX_PIXEL_VALUE

CHANNEL_COUNT = 3


@numba.njit(cache=True, nogil=True)
def write_grey(rgb: npt.NDArray[np.uint8], destination: npt.NDArray[np.float32]) -> None:
    """Write the channel mean of `rgb` (H, W, 3), scaled to [0, 1], into `destination` (H, W)."""
    channels = np.float32(CHANNEL_COUNT)
    maximum = np.float32(MAX_PIXEL_VALUE)
    for row in range(rgb.shape[0]):
        for column in range(rgb.shape[1]):
            total = np.float32(rgb[row, column, 0]) + np.float32(rgb[row, column, 1])
            total += np.float32(rgb[row, column, 2])
            destination[row, column] = total / channels / maximum
