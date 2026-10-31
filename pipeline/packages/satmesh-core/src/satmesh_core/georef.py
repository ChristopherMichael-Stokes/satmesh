"""Georeference of terrain: a source's grid and height datum to geodetic coordinates and ENU frames.

US heights (NAVD88 on NAD83(2011)) reach WGS 84 by an explicit chain, not PROJ's direct choice
from EPSG:6349 to EPSG:4979, which takes a GEOID03 and HARN route when that grid is installed and
treats NAD83(2011) as WGS 84 (2 m accuracy) otherwise:

1. projected NAD83(2011) to geographic NAD83(2011) (a map projection, exact);
2. NAVD88 height H to NAD83(2011) ellipsoidal height h = H + N, N from GEOID18
   (`us_noaa_g2018u0.tif`, EPSG operation "NAD83(2011) to NAVD88 height (3)", 1.5 cm);
3. NAD83(2011) to WGS 84 (G2139) by the time-dependent 14-parameter Helmert through ITRF2014
   (EPSG operations "ITRF2014 to NAD83(2011) (1)" and "WGS 84 (G2139) to ITRF2014 (1)"), evaluated
   at `NAD83_2011_TO_WGS84_EPOCH`.

WGS 84 (G2139) coordinates are then used as EPSG:4979 coordinates: G2139 is the current
realisation of the WGS 84 ensemble and shares its ellipsoid.
"""

import math
import warnings
from dataclasses import dataclass

import numpy as np
from pyproj import CRS, Transformer
from pyproj.transformer import TransformerGroup

from satmesh_core.aoi import WGS84

BNG_ODN = "EPSG:7405"
ELLIPSOID_HEIGHT_CRS = "EPSG:4979"
NAVD88_HEIGHT = "EPSG:5703"
NAD83_2011 = "EPSG:6318"
NAD83_2011_3D = "EPSG:6319"
NAD83_2011_NAVD88 = "EPSG:6349"
WGS84_G2139 = "EPSG:9755"
WGS84_G2139_3D = "EPSG:9754"
# NAD83(2011) is fixed to the North American plate and WGS 84 (G2139) to ITRF2014, so the Helmert
# between them has rates and needs the date the positions refer to. 2025.0 sits among the Esri
# imagery capture dates the meshes are draped with and today's GNSS positions. At Denver a year
# either way moves a point about 1.7 cm horizontally and 1 mm vertically (PROJ, EPSG:6319 to
# EPSG:9754 at 2010.0 and 2025.0), below the 1.5 cm GEOID18 accuracy over a few years.
NAD83_2011_TO_WGS84_EPOCH = 2025.0
PIPELINE_PREFIX = "proj=pipeline "
STEP_PREFIX = "step "


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


def ellipsoidal_height_from(height_crs: str) -> Transformer:
    """Return (x, y, orthometric height) in compound CRS `height_crs` to (lon, lat, ellipsoidal).

    `height_crs` names both the horizontal CRS and the vertical datum, e.g. `BNG_ODN`,
    `EPSG:4326+3855` (WGS 84 with EGM2008 height) or `EPSG:6342+5703` (NAD83(2011) UTM 13N with
    NAVD88 height); the geoid grid it needs must be installed. NAVD88 heights go through the
    module's explicit chain and need a NAD83(2011) horizontal CRS.
    """
    crs = CRS.from_user_input(height_crs)
    if crs.is_compound:
        horizontal, vertical = crs.sub_crs_list
        if vertical.equals(NAVD88_HEIGHT):
            return _navd88_to_wgs84(horizontal)
    return require_best_transformer(height_crs, ELLIPSOID_HEIGHT_CRS)


def _navd88_to_wgs84(horizontal: CRS) -> Transformer:
    if not _on_nad83_2011(horizontal):
        msg = f"NAVD88 heights need a NAD83(2011) horizontal CRS, got {horizontal.name}"
        raise ValueError(msg)
    to_geographic = (
        []
        if horizontal.equals(NAD83_2011)
        else [require_best_transformer(horizontal.to_wkt(), NAD83_2011)]
    )
    return _concatenated(
        *to_geographic,
        require_best_transformer(NAD83_2011_NAVD88, NAD83_2011_3D),
        *_at_epoch(require_best_transformer(NAD83_2011_3D, WGS84_G2139_3D)),
    )


def _on_nad83_2011(crs: CRS) -> bool:
    geodetic = crs.geodetic_crs
    return geodetic is not None and geodetic.equals(NAD83_2011, ignore_axis_order=True)


def _at_epoch(time_dependent: Transformer) -> tuple[str, Transformer, str]:
    """Return `time_dependent` between steps fixing the coordinate time to the US epoch.

    The step comes on both sides because an inverse pipeline runs its steps in reverse order.
    """
    fix_time = f"{STEP_PREFIX}proj=set v_4={NAD83_2011_TO_WGS84_EPOCH}"
    return fix_time, time_dependent, fix_time


def _concatenated(*steps: Transformer | str) -> Transformer:
    """Return one PROJ pipeline running `steps` in order: transformers and raw pipeline steps."""
    parts: list[str] = []
    for step in steps:
        if isinstance(step, str):
            parts.append(step)
            continue
        definition = step.definition
        if not definition.startswith(PIPELINE_PREFIX):
            parts.append(STEP_PREFIX + definition)
            continue
        body = definition.removeprefix(PIPELINE_PREFIX)
        if not body.startswith(STEP_PREFIX):
            msg = f"pipeline-wide options cannot be carried into a longer pipeline: {definition}"
            raise ValueError(msg)
        parts.append(body)
    return Transformer.from_pipeline(PIPELINE_PREFIX + " ".join(parts))


def geodetic_to_ecef() -> Transformer:
    """Return (lon, lat, ellipsoidal height) to ECEF metres; exact, so no grids are involved."""
    return Transformer.from_crs(ELLIPSOID_HEIGHT_CRS, "EPSG:4978", always_xy=True)


def ecef_to_geodetic() -> Transformer:
    """Return ECEF metres to (lon, lat, ellipsoidal height); exact, so no grids are involved."""
    return Transformer.from_crs("EPSG:4978", ELLIPSOID_HEIGHT_CRS, always_xy=True)


def wgs84_to(crs: str) -> Transformer:
    """Return (lon, lat) to the projected CRS `crs`, through its datum grids when it has any.

    A NAD83(2011) CRS is reached through the time-dependent Helmert at
    `NAD83_2011_TO_WGS84_EPOCH`, the inverse of the horizontal part of `ellipsoidal_height_from`,
    so a point sampled in a US raster lands back where the height chain places it.
    """
    if not _on_nad83_2011(CRS.from_user_input(crs)):
        return require_best_transformer(WGS84, crs)
    return _concatenated(
        *_at_epoch(require_best_transformer(WGS84_G2139, NAD83_2011)),
        require_best_transformer(NAD83_2011, crs),
    )


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
