from pathlib import Path

from typer.testing import CliRunner

from satmesh_cli.main import app

runner = CliRunner()
PARIS = ["--bbox", "2.29", "48.85", "2.30", "48.86"]


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
        app, ["build", "--bbox", "2.30", "48.85", "2.29", "48.86", "--store", str(tmp_path)]
    )
    assert result.exit_code == 1
    assert "empty box" in result.output


def test_build_needs_a_four_number_bbox(tmp_path: Path) -> None:
    result = runner.invoke(app, ["build", "--bbox", "1", "2", "--store", str(tmp_path)])
    assert result.exit_code == 2


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
