"""Georeference of terrain: BNG plus ODN height to geodetic coordinates and local ENU frames."""

import math
import warnings
from dataclasses import dataclass

import numpy as np
from pyproj import Transformer
from pyproj.transformer import TransformerGroup

from satmesh_core.aoi import WGS84

BNG_ODN = "EPSG:7405"
ELLIPSOID_HEIGHT_CRS = "EPSG:4979"


class GridMissingError(Exception):
    """The best PROJ transformation between two CRSs needs a grid that is not installed."""


def require_best_transformer(source_crs: str, target_crs: str) -> Transformer:
    """Return the most accurate PROJ transformer, raising if its grids are not installed.

    PROJ otherwise falls back silently to a Helmert shift or a ballpark: for BNG with ODN height at
    Upper Aire that is 1.6 m or 100.7 m horizontally and 50.8 m vertically.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        group = TransformerGroup(source_crs, target_crs, always_xy=True)
    if not group.best_available:
        missing = ", ".join(
            grid.short_name
            for operation in group.unavailable_operations[:1]
            for grid in operation.grids
            if not grid.available
        )
        msg = (
            f"{source_crs} to {target_crs} needs PROJ grids that are not installed: {missing}. "
            "Run `pyproj sync --file <grid>` for each, or set PROJ_NETWORK=ON."
        )
        raise GridMissingError(msg)
    return group.transformers[0]


def bng_odn_to_wgs84() -> Transformer:
    """Return (easting, northing, ODN height) to (lon, lat, ellipsoidal height) via the grids."""
    return require_best_transformer(BNG_ODN, ELLIPSOID_HEIGHT_CRS)


def geodetic_to_ecef() -> Transformer:
    """Return (lon, lat, ellipsoidal height) to ECEF metres; exact, so no grids are involved."""
    return Transformer.from_crs(ELLIPSOID_HEIGHT_CRS, "EPSG:4978", always_xy=True)


def ecef_to_geodetic() -> Transformer:
    """Return ECEF metres to (lon, lat, ellipsoidal height); exact, so no grids are involved."""
    return Transformer.from_crs("EPSG:4978", ELLIPSOID_HEIGHT_CRS, always_xy=True)


def wgs84_to_bng() -> Transformer:
    """Return (lon, lat) to (easting, northing) through OSTN15."""
    return require_best_transformer(WGS84, "EPSG:27700")


@dataclass(frozen=True)
class EnuFrame:
    """Local east-north-up frame: ground metres on the tangent plane at `origin_ecef`.

    `east_north_up` rows are the unit vectors of east, north and up in ECEF, so a displacement
    `d` in ECEF is `east_north_up @ d` in ENU. The plane is tangent to the ellipsoid at the
    origin: Earth curvature appears as ENU up dropping away from the origin.
    """

    origin_ecef: np.ndarray
    east_north_up: np.ndarray

    @classmethod
    def at(cls, origin_ecef: np.ndarray, lon_deg: float, lat_deg: float) -> "EnuFrame":
        """Frame at an ECEF point whose geodetic longitude and latitude are given.

        East = (-sin(lon), cos(lon), 0); north = (-sin(lat) cos(lon), -sin(lat) sin(lon), cos(lat));
        up = (cos(lat) cos(lon), cos(lat) sin(lon), sin(lat)): the standard ECEF-to-ENU rotation.
        """
        lon, lat = math.radians(lon_deg), math.radians(lat_deg)
        east_north_up = np.array(
            [
                [-math.sin(lon), math.cos(lon), 0.0],
                [-math.sin(lat) * math.cos(lon), -math.sin(lat) * math.sin(lon), math.cos(lat)],
                [math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)],
            ]
        )
        return cls(np.asarray(origin_ecef, dtype=np.float64), east_north_up)

    @classmethod
    def at_ecef(cls, origin_ecef: np.ndarray) -> "EnuFrame":
        """Frame at an ECEF point, taking its longitude and latitude from the point itself."""
        lon, lat, _ = ecef_to_geodetic().transform(*origin_ecef)
        return cls.at(origin_ecef, lon, lat)

    def to_enu(self, ecef: np.ndarray) -> np.ndarray:
        """Return `(n, 3)` ECEF points as ENU metres."""
        return (np.asarray(ecef) - self.origin_ecef) @ self.east_north_up.T

    def enu_to_ecef_matrix(self) -> np.ndarray:
        """Return the 4 x 4 matrix taking ENU to ECEF (a 3D Tiles `transform` once column-major)."""
        matrix = np.eye(4)
        matrix[:3, :3] = self.east_north_up.T
        matrix[:3, 3] = self.origin_ecef
        return matrix
