"""Strata for height scores: terrain slope classes and a raised-object mask."""

import numpy as np
import xdem
from rasterio.transform import Affine

# upper edges of the slope classes, degrees; flat land, gentle, steep, very steep (tunable)
SLOPE_CLASS_EDGES_DEG = (5.0, 15.0, 30.0)
SLOPE_CLASS_NAMES = {
    0: "slope under 5 deg",
    1: "slope 5 to 15 deg",
    2: "slope 15 to 30 deg",
    3: "slope over 30 deg",
}
# a first-return surface this far above the bare earth counts as a raised object: above hedge
# stubble and crop height, below a one-storey eave (tunable)
OBJECT_HEIGHT_THRESHOLD_M = 2.0


def slope_classes(heights: np.ndarray, transform: Affine, crs: int) -> np.ndarray:
    """Label each pixel of a projected height raster with its index in `SLOPE_CLASS_NAMES`.

    Slope comes from xdem's default terrain-attribute method. Pixels with no slope get -1.
    """
    surface = xdem.DEM.from_array(heights.astype(np.float32), transform=transform, crs=crs)
    slope = np.ma.filled(surface.slope().data.astype(np.float64), np.nan)
    labels = np.digitize(slope, SLOPE_CLASS_EDGES_DEG)
    labels[np.isnan(slope)] = -1
    return labels


def raised_object_mask(
    surface: np.ndarray, ground: np.ndarray, threshold_m: float = OBJECT_HEIGHT_THRESHOLD_M
) -> np.ndarray:
    """Return True where the surface stands more than `threshold_m` above the ground."""
    return (surface - ground) > threshold_m
