"""Area of interest and the metric CRS it is meshed in."""

from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from pyproj import CRS, Transformer
from pyproj.aoi import AreaOfInterest
from pyproj.database import query_utm_crs_info
from pyproj.exceptions import CRSError

WGS84 = "EPSG:4326"
BRITISH_NATIONAL_GRID = "EPSG:27700"
# Irish Transverse Mercator; its area of use marks the part of BNG's bounding box that is Ireland
IRISH_TRANSVERSE_MERCATOR = "EPSG:2157"


class Aoi(BaseModel):
    """A box `(west, south, east, north)` in `crs` units: degrees for EPSG:4326, metres for BNG."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    crs: str
    west: float
    south: float
    east: float
    north: float

    @field_validator("crs")
    @classmethod
    def _known_crs(cls, crs: str) -> str:
        try:
            CRS.from_user_input(crs)
        except CRSError as error:
            raise ValueError(str(error)) from error
        return crs

    @model_validator(mode="after")
    def _non_empty(self) -> Self:
        if self.west >= self.east or self.south >= self.north:
            msg = (
                f"empty box: west {self.west}, south {self.south}, "
                f"east {self.east}, north {self.north}"
            )
            raise ValueError(msg)
        return self

    def bounds_in(self, crs: str) -> tuple[float, float, float, float]:
        """Return `(west, south, east, north)` of the box reprojected to `crs`, edges densified."""
        transformer = Transformer.from_crs(self.crs, crs, always_xy=True)
        return transformer.transform_bounds(self.west, self.south, self.east, self.north)

    def wgs84_bounds(self) -> tuple[float, float, float, float]:
        """Return `(west, south, east, north)` in degrees."""
        return self.bounds_in(WGS84)

    def grown(self, margin_m: float) -> "Aoi":
        """Return the box in its metric CRS, grown by `margin_m` ground metres on each side."""
        if margin_m < 0:
            msg = f"margin_m must be non-negative, got {margin_m}"
            raise ValueError(msg)
        crs = metric_crs(self)
        west, south, east, north = self.bounds_in(crs)
        return Aoi(
            crs=crs,
            west=west - margin_m,
            south=south - margin_m,
            east=east + margin_m,
            north=north + margin_m,
        )


def metric_crs(aoi: Aoi) -> str:
    """Return BNG for an AOI inside Great Britain, else the WGS 84 UTM zone at the AOI centre.

    Great Britain is BNG's area-of-use box minus Irish Transverse Mercator's, so an AOI in Northern
    Ireland gets UTM. Both boxes are coarse: the south tip of Kintyre also gets UTM.
    """
    west, south, east, north = aoi.wgs84_bounds()
    if _inside(BRITISH_NATIONAL_GRID, west, south, east, north) and not _overlaps(
        IRISH_TRANSVERSE_MERCATOR, west, south, east, north
    ):
        return BRITISH_NATIONAL_GRID
    lon, lat = (west + east) / 2, (south + north) / 2
    (zone,) = query_utm_crs_info(
        datum_name="WGS 84", area_of_interest=AreaOfInterest(lon, lat, lon, lat)
    )
    return f"{zone.auth_name}:{zone.code}"


def _area_of_use(crs: str) -> tuple[float, float, float, float]:
    area = CRS.from_user_input(crs).area_of_use
    if area is None:
        msg = f"{crs} has no area of use"
        raise ValueError(msg)
    return area.bounds


def _inside(crs: str, west: float, south: float, east: float, north: float) -> bool:
    a_west, a_south, a_east, a_north = _area_of_use(crs)
    return a_west <= west and a_south <= south and east <= a_east and north <= a_north


def _overlaps(crs: str, west: float, south: float, east: float, north: float) -> bool:
    a_west, a_south, a_east, a_north = _area_of_use(crs)
    return west < a_east and a_west < east and south < a_north and a_south < north
