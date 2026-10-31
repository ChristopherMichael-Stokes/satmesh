import pytest
from pydantic import ValidationError

from satmesh_core import BRITISH_NATIONAL_GRID, WGS84, Aoi
from satmesh_data import (
    EA_DSM,
    EA_DTM,
    CogTilesSource,
    EaWcsSource,
    Registry,
    SourceSelectionError,
    TnmDemWithEptDsmSource,
    load_registry,
    select_surface_source,
)
from satmesh_data.registry import select_from

SANAA = (44.207, 15.355)
DENVER = (-104.995, 39.748)
PLANO = (-96.76, 33.05)
GB_EAST_EDGE_LON = 1.9


def box_around(lon: float, lat: float, half_deg: float) -> Aoi:
    return Aoi(
        crs=WGS84,
        west=lon - half_deg,
        south=lat - half_deg,
        east=lon + half_deg,
        north=lat + half_deg,
    )


def entry(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "name": "test",
        "adapter": "cog_tiles",
        "covers": [[0.0, 0.0, 1.0, 1.0]],
        "xy_crs": "EPSG:4326",
        "height_crs": "EPSG:4326+3855",
        "ground_is_surface": True,
        "licence": "l",
        "attribution": "a",
        "url_template": "https://example.test/{ns}{lat}{ew}{lon}.tif",
    }
    return fields | overrides


def test_footprint_inside_great_britain_selects_the_ea_entry() -> None:
    source = select_surface_source(box_around(-1.5, 53.8, 0.01))
    assert source.name == "ea-lidar-composite"
    assert (source.xy_crs, source.height_crs, source.ground_is_surface) == (
        BRITISH_NATIONAL_GRID,
        "EPSG:7405",
        False,
    )


def test_footprint_in_yemen_selects_glo30_with_fabdem_ground() -> None:
    source = select_surface_source(box_around(*SANAA, 0.01))
    assert source.name == "copernicus-glo30-fabdem"
    assert (source.xy_crs, source.height_crs, source.ground_is_surface) == (
        WGS84,
        "EPSG:4326+3855",
        False,
    )
    assert "FABDEM V1-2, Hawker et al. 2022" in source.attribution
    assert "Copernicus" in source.attribution
    assert "CC BY-NC-SA 4.0" in source.licence


@pytest.mark.parametrize("lon_lat", [DENVER, PLANO])
def test_footprint_in_the_contiguous_us_selects_3dep(lon_lat: tuple[float, float]) -> None:
    source = select_surface_source(box_around(*lon_lat, 0.01))
    assert isinstance(source, TnmDemWithEptDsmSource)
    assert (source.name, source.height_crs, source.ground_is_surface) == (
        "usgs-3dep",
        "EPSG:6349",
        False,
    )


def test_us_boxes_overlap_so_an_area_on_a_box_edge_still_fits_one() -> None:
    # Denver area's box ends at 103 W; the plains box starts at 104.1 W
    source = select_surface_source(box_around(-103.0, 40.0, 0.05))
    assert source.name == "usgs-3dep"


def test_footprint_elsewhere_selects_glo30_surface_only() -> None:
    source = select_surface_source(box_around(-60.0, -10.0, 0.01))
    assert source.name == "copernicus-glo30"
    assert (source.height_crs, source.ground_is_surface) == ("EPSG:4326+3855", True)
    assert "attribution required" in source.licence


def test_footprint_straddling_the_great_britain_edge_raises() -> None:
    with pytest.raises(SourceSelectionError, match="ea-lidar-composite covers the centre"):
        select_surface_source(box_around(GB_EAST_EDGE_LON, 52.0, 0.05))


def test_packaged_ea_entry_matches_the_lidar_module_constants() -> None:
    ea = next(s for s in load_registry().sources if isinstance(s, EaWcsSource))
    assert (ea.dtm_wcs_url, ea.dtm_coverage_id) == (EA_DTM.wcs_url, EA_DTM.coverage_id)
    assert (ea.dsm_wcs_url, ea.dsm_coverage_id) == (EA_DSM.wcs_url, EA_DSM.coverage_id)


def test_glo30_url_names_the_south_west_corner() -> None:
    glo30 = next(s for s in load_registry().sources if s.name == "copernicus-glo30")
    assert isinstance(glo30, CogTilesSource)
    url = glo30.url_template.format(ns="N", lat=15, ew="E", lon=44)
    assert url.endswith(
        "Copernicus_DSM_COG_10_N15_00_E044_00_DEM/Copernicus_DSM_COG_10_N15_00_E044_00_DEM.tif"
    )


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"covers": [[1.0, 0.0, 0.0, 1.0]]}, "empty covers box"),
        ({"covers": []}, "at least 1 item"),
        ({"height_crs": "EPSG:4326"}, "compound"),
        ({"height_crs": "EPSG:99999999"}, "height_crs"),
        ({"adapter": "ftp"}, "adapter"),
        ({"surprise": 1}, "surprise"),
    ],
)
def test_invalid_entries_are_rejected(overrides: dict[str, object], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Registry.model_validate({"sources": [entry(**overrides)]})


def test_duplicate_names_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        Registry.model_validate({"sources": [entry(), entry()]})


def test_ground_template_without_block_and_tile_is_rejected() -> None:
    fields = entry(
        adapter="cog_tiles_with_zip_ground",
        ground_path_template="/vsizip/{block}.zip",
        ground_index_url="https://example.test/index.geojson",
    )
    with pytest.raises(ValidationError, match="needs"):
        Registry.model_validate({"sources": [fields]})


def test_seamless_template_without_tile_is_rejected() -> None:
    fields = entry(
        adapter="tnm_dem_with_ept_dsm",
        tnm_products_url="https://example.test/products",
        tnm_dataset="d",
        image_server_url="https://example.test/ImageServer",
        seamless_path_template="/vsicurl/https://example.test/USGS_13.tif",
        ept_index_url="https://example.test/resources.geojson",
    )
    del fields["url_template"]
    with pytest.raises(ValidationError, match="needs"):
        Registry.model_validate({"sources": [fields]})


def test_missing_adapter_parameter_is_rejected() -> None:
    fields = entry()
    del fields["url_template"]
    with pytest.raises(ValidationError, match="url_template"):
        Registry.model_validate({"sources": [fields]})


def test_footprint_outside_every_entry_raises() -> None:
    registry = Registry.model_validate({"sources": [entry()]})
    with pytest.raises(SourceSelectionError, match="no elevation source"):
        select_from(registry, box_around(10.0, 10.0, 0.1))


def test_registry_file_is_packaged() -> None:
    assert [s.name for s in load_registry().sources] == [
        "ea-lidar-composite",
        "copernicus-glo30-fabdem",
        "usgs-3dep",
        "copernicus-glo30",
    ]
