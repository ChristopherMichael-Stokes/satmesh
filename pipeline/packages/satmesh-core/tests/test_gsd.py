import pytest

from satmesh_core import ground_sample_distance_m, zoom_for_resolution

# Esri World_Imagery service definition: 0.0187 m/px at level 23 (equator).
ESRI_LEVEL_23_RESOLUTION_M = 0.0187


def test_equator_zoom_23_matches_esri_service_definition() -> None:
    assert ground_sample_distance_m(23, 0.0) == pytest.approx(ESRI_LEVEL_23_RESOLUTION_M, abs=5e-5)


def test_gsd_halves_per_zoom_level() -> None:
    assert ground_sample_distance_m(11, 30.0) == pytest.approx(
        2 * ground_sample_distance_m(12, 30.0)
    )


def test_gsd_shrinks_by_cosine_of_latitude() -> None:
    assert ground_sample_distance_m(10, 60.0) == pytest.approx(
        0.5 * ground_sample_distance_m(10, 0.0)
    )


def test_zoom_for_resolution_reaches_source_resolution() -> None:
    source_resolution_m = 0.34
    zoom = zoom_for_resolution(source_resolution_m, 45.0, max_zoom=23)
    assert ground_sample_distance_m(zoom, 45.0) <= source_resolution_m
    assert ground_sample_distance_m(zoom - 1, 45.0) > source_resolution_m


def test_zoom_for_resolution_is_capped() -> None:
    assert zoom_for_resolution(0.01, 0.0, max_zoom=19) == 19


def test_zoom_for_resolution_rejects_non_positive_resolution() -> None:
    with pytest.raises(ValueError, match="positive"):
        zoom_for_resolution(0.0, 0.0, max_zoom=19)
