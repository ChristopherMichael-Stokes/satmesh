from typer.testing import CliRunner

from satmesh_cli.grids import Region, grid_files
from satmesh_cli.main import app

runner = CliRunner()

GB_FILES = ["uk_os_OSTN15_NTv2_OSGBtoETRS.tif", "uk_os_OSGM15_GB.tif"]
GLOBAL_FILES = ["us_nga_egm08_25.tif"]
US_FILES = ["us_noaa_g2018u0.tif"]


def test_each_region_lists_its_own_files() -> None:
    assert grid_files([Region.GB]) == GB_FILES
    assert grid_files([Region.GLOBAL]) == GLOBAL_FILES
    assert grid_files([Region.US]) == US_FILES


def test_no_region_lists_every_file_once() -> None:
    assert grid_files([]) == GB_FILES + GLOBAL_FILES + US_FILES


def test_repeated_regions_do_not_repeat_files() -> None:
    assert grid_files([Region.US, Region.US, Region.GLOBAL]) == US_FILES + GLOBAL_FILES


def test_dry_run_with_two_regions_prints_both_regions_files() -> None:
    result = runner.invoke(app, ["grids", "--dry-run", "--region", "gb", "--region", "us"])
    assert result.exit_code == 0
    assert result.output.split() == GB_FILES + US_FILES


def test_dry_run_without_region_prints_all_files() -> None:
    result = runner.invoke(app, ["grids", "--dry-run"])
    assert result.exit_code == 0
    assert result.output.split() == GB_FILES + GLOBAL_FILES + US_FILES


def test_unknown_region_is_rejected_with_the_valid_names() -> None:
    result = runner.invoke(app, ["grids", "--dry-run", "--region", "mars"])
    assert result.exit_code == 2
    for name in ("gb", "global", "us"):
        assert name in result.output
