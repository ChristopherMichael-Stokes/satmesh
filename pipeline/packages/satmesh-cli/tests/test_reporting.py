from pathlib import Path

import pytest

from satmesh_cli.reporting import RUN_LOG_FILE, run_log


def test_the_run_log_holds_settings_phases_and_the_elapsed_time(tmp_path: Path) -> None:
    store = tmp_path / "store"
    with run_log(store, "demo", {"cache_dir": tmp_path, "rate": 2.5}) as report:
        report("matching cells", 0, 2)
        report("matching cells", 1, 2)
        report("matching cells", 2, 2)
    lines = (store / RUN_LOG_FILE).read_text().splitlines()
    text = "\n".join(lines)
    assert "satmesh demo:" in text
    assert "setting rate = 2.5" in text
    assert f"setting cache_dir = {tmp_path}" in text
    assert "matching cells: 2 steps" in text
    assert "matching cells: done in" in text
    assert "finished in" in lines[-1]


def test_a_failure_is_logged_and_still_raised(tmp_path: Path) -> None:
    store = tmp_path / "store"
    msg = "boom"
    with pytest.raises(RuntimeError, match=msg), run_log(store, "demo", {}):
        raise RuntimeError(msg)
    assert "failed after" in (store / RUN_LOG_FILE).read_text()


def test_runs_append_to_the_same_log(tmp_path: Path) -> None:
    store = tmp_path / "store"
    for command in ("first", "second"):
        with run_log(store, command, {}):
            pass
    text = (store / RUN_LOG_FILE).read_text()
    assert "satmesh first:" in text
    assert "satmesh second:" in text
