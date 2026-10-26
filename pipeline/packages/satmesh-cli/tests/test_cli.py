from pathlib import Path

from typer.testing import CliRunner

from satmesh_cli.main import app

runner = CliRunner()
PARIS = ["--nw", "48.86, 2.29", "--se", "48.85, 2.30"]


def test_help_lists_build_and_the_export_group() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "build" in result.output
    assert "export" in result.output


def test_build_outside_great_britain_fails_before_any_request(tmp_path: Path) -> None:
    result = runner.invoke(app, ["build", *PARIS, "--store", str(tmp_path / "store")])
    assert result.exit_code == 1
    assert "only Great Britain" in result.output


def test_build_with_an_empty_box_reports_it(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["build", "--nw", "48.86, 2.30", "--se", "48.85, 2.29", "--store", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "empty box" in result.output


def test_build_rejects_a_corner_that_is_not_lat_lon(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["build", "--nw", "48.86", "--se", "48.85, 2.30", "--store", str(tmp_path)]
    )
    assert result.exit_code == 2
    assert "lat, lon" in result.output


def test_cache_dir_comes_from_the_environment_variable() -> None:
    result = runner.invoke(app, ["build", "--help"], env={"SATMESH_CACHE_DIR": "/somewhere"})
    assert result.exit_code == 0
    assert "SATMESH_CACHE_DIR" in result.output


def test_exports_of_an_empty_store_report_no_nodes(tmp_path: Path) -> None:
    for command in (
        ["export", "3dtiles", "--store", str(tmp_path)],
        ["export", "gazebo", "--store", str(tmp_path), "--out", str(tmp_path / "gz")],
        ["export", "glb", "--store", str(tmp_path), "--out", str(tmp_path / "a.glb")],
    ):
        result = runner.invoke(app, command)
        assert result.exit_code == 1, command
        assert "no nodes" in result.output, command


def test_eval_group_lists_the_four_checks() -> None:
    result = runner.invoke(app, ["eval", "--help"])
    assert result.exit_code == 0
    for check in ("heights", "smoothness", "visibility", "offset"):
        assert check in result.output
