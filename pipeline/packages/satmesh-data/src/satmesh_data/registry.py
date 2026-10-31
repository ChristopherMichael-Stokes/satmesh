"""The elevation sources satmesh can fetch, read from `registry.toml`, and the choice among them."""

import tomllib
from functools import cache
from importlib.resources import files
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pyproj import CRS
from pyproj.exceptions import CRSError

from satmesh_core import Aoi

REGISTRY_FILE = "registry.toml"
LonLatBox = tuple[float, float, float, float]


class SourceSelectionError(Exception):
    """No registry entry serves a footprint, or the entry at its centre covers only part of it."""


class SurfaceSource(BaseModel):
    """One elevation source: where it applies and how its rasters are described."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    covers: tuple[LonLatBox, ...] = Field(min_length=1)
    xy_crs: str
    height_crs: str
    ground_is_surface: bool
    licence: str
    attribution: str

    @field_validator("xy_crs", "height_crs")
    @classmethod
    def _known_crs(cls, crs: str) -> str:
        try:
            CRS.from_user_input(crs)
        except CRSError as error:
            raise ValueError(str(error)) from error
        return crs

    @field_validator("height_crs")
    @classmethod
    def _compound(cls, crs: str) -> str:
        if not CRS.from_user_input(crs).is_compound:
            msg = f"height_crs must be a compound CRS with a vertical part, got {crs}"
            raise ValueError(msg)
        return crs

    @field_validator("covers")
    @classmethod
    def _boxes_not_empty(cls, boxes: tuple[LonLatBox, ...]) -> tuple[LonLatBox, ...]:
        for west, south, east, north in boxes:
            if west >= east or south >= north:
                msg = f"empty covers box [{west}, {south}, {east}, {north}]"
                raise ValueError(msg)
        return boxes

    def covers_point(self, lon: float, lat: float) -> bool:
        """Return whether `(lon, lat)` lies inside one of the covers boxes."""
        return any(w <= lon <= e and s <= lat <= n for w, s, e, n in self.covers)

    def covers_box(self, west: float, south: float, east: float, north: float) -> bool:
        """Return whether one covers box contains the whole box `(west, south, east, north)`."""
        return any(
            w <= west and s <= south and east <= e and north <= n for w, s, e, n in self.covers
        )


class EaWcsSource(SurfaceSource):
    """England's Environment Agency LIDAR Composite, by WCS 2.0.1."""

    adapter: Literal["ea_wcs"]
    dtm_wcs_url: str
    dtm_coverage_id: str
    dsm_wcs_url: str
    dsm_coverage_id: str


class CogTilesSource(SurfaceSource):
    """Surface model in 1-degree Cloud-Optimised GeoTIFF tiles named by their south-west corner.

    `url_template` takes `ns` ("N"/"S"), `lat` (whole degrees, unsigned), `ew` ("E"/"W") and `lon`
    (whole degrees, unsigned).
    """

    adapter: Literal["cog_tiles"]
    url_template: str


class CogTilesWithZipGroundSource(SurfaceSource):
    """GLO-30-style surface tiles plus a ground model read from tiles inside zip blocks.

    The ground model shares the surface tiles' pixel grid. `ground_path_template` is a GDAL path
    with `{block}` (the zip file's name before its first underscore) and `{tile}` (e.g. `N15E044`),
    and `ground_index_url` is a GeoJSON listing each ground tile and its zip file.
    """

    adapter: Literal["cog_tiles_with_zip_ground"]
    url_template: str
    ground_path_template: str
    ground_index_url: str

    @field_validator("ground_path_template")
    @classmethod
    def _has_block_and_tile(cls, template: str) -> str:
        if "{block}" not in template or "{tile}" not in template:
            msg = f"ground_path_template needs {{block}} and {{tile}}, got {template}"
            raise ValueError(msg)
        return template


class TnmDemWithEptDsmSource(SurfaceSource):
    """USGS 3DEP: 1 m bare-earth DEM tiles and a first-return DSM rasterised from EPT lidar.

    The ground comes from the TNM Access API's `tnm_dataset` COGs, else the ImageServer at
    `image_server_url`, else the 1/3 arc-second COGs at `seamless_path_template` (a GDAL path with
    `{tile}`, e.g. `n40w105`). The surface comes from the EPT projects listed in the GeoJSON
    `ept_index_url`. Rasters are written on a 1 m grid in the NAD83(2011) UTM zone of each area,
    so `xy_crs` names only the geographic CRS that grid is based on.
    """

    adapter: Literal["tnm_dem_with_ept_dsm"]
    tnm_products_url: str
    tnm_dataset: str
    image_server_url: str
    seamless_path_template: str
    ept_index_url: str

    @field_validator("seamless_path_template")
    @classmethod
    def _has_tile(cls, template: str) -> str:
        if "{tile}" not in template:
            msg = f"seamless_path_template needs {{tile}}, got {template}"
            raise ValueError(msg)
        return template


type RegistryEntry = Annotated[
    EaWcsSource | CogTilesSource | CogTilesWithZipGroundSource | TnmDemWithEptDsmSource,
    Field(discriminator="adapter"),
]


class Registry(BaseModel):
    """The ordered entries of `registry.toml`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sources: tuple[RegistryEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_names(self) -> Self:
        names = [source.name for source in self.sources]
        if len(set(names)) != len(names):
            msg = f"duplicate source names in {names}"
            raise ValueError(msg)
        return self


@cache
def load_registry() -> Registry:
    """Return the packaged registry, validated."""
    text = files("satmesh_data").joinpath(REGISTRY_FILE).read_text(encoding="utf-8")
    return Registry.model_validate(tomllib.loads(text))


def select_surface_source(footprint: Aoi) -> SurfaceSource:
    """Return the first registry entry covering the centre of `footprint`, if it covers all of it.

    Raises `SourceSelectionError` when no entry covers the centre or the entry that does covers
    only part of the footprint.
    """
    return select_from(load_registry(), footprint)


def select_from(registry: Registry, footprint: Aoi) -> RegistryEntry:
    """Apply `select_surface_source`'s rule to `registry`."""
    west, south, east, north = footprint.wgs84_bounds()
    centre = ((west + east) / 2, (south + north) / 2)
    for source in registry.sources:
        if not source.covers_point(*centre):
            continue
        if not source.covers_box(west, south, east, north):
            msg = (
                f"{source.name} covers the centre of the footprint but not all of it: "
                f"lon {west:.5f} to {east:.5f}, lat {south:.5f} to {north:.5f}"
            )
            raise SourceSelectionError(msg)
        return source
    msg = (
        f"no elevation source covers the footprint centre lon {centre[0]:.5f}, lat {centre[1]:.5f}"
    )
    raise SourceSelectionError(msg)
