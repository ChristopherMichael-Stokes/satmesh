from pathlib import Path

import pytest
from pydantic import ValidationError

from satmesh_locate.events import Interval, PositionPrior
from satmesh_track.priors import FirstFixConfig, load_config, parse_interval, with_priors


def test_interval_text_gives_centre_and_half_width() -> None:
    assert parse_interval("30+-45") == Interval(centre=30.0, half_width=45.0)
    assert parse_interval("-35+-10") == Interval(centre=-35.0, half_width=10.0)
    assert parse_interval(" 72.5 +- 7.5 ") == Interval(centre=72.5, half_width=7.5)


@pytest.mark.parametrize("text", ["30", "30+-", "north+-10", "30+--5"])
def test_malformed_interval_text_is_refused(text: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011  # ValidationError for the negative width
        parse_interval(text)


def test_a_toml_file_sets_priors_and_settings_and_leaves_the_rest(tmp_path: Path) -> None:
    path = tmp_path / "priors.toml"
    path.write_text(
        'yaw_method = "homography"\n'
        "fusion_frames = 3\n"
        "[priors.heading_deg]\ncentre = 30.0\nhalf_width = 45.0\n"
        "[priors.position]\neast_m = 100.0\nnorth_m = -50.0\nradius_m = 300.0\n"
    )

    config = load_config(path)

    assert config.yaw_method == "homography"
    assert config.fusion_frames == 3
    assert config.priors.heading_deg == Interval(centre=30.0, half_width=45.0)
    assert config.priors.position == PositionPrior(east_m=100.0, north_m=-50.0, radius_m=300.0)
    assert config.priors.pitch_deg is None
    assert config.priors.height_m is None
    assert config.fusion_frame_step == FirstFixConfig().fusion_frame_step


@pytest.mark.parametrize(
    "text",
    [
        "fusion_frame = 3\n",  # misspelt
        "heading_step_deg = 25.0\n",  # does not divide the circle
        "[priors.heading_deg]\ncentre = 30.0\nhalf_width = -1.0\n",
    ],
)
def test_a_bad_toml_file_is_refused(tmp_path: Path, text: str) -> None:
    path = tmp_path / "priors.toml"
    path.write_text(text)

    with pytest.raises(ValidationError):
        load_config(path)


def test_command_line_priors_override_the_file_and_keep_the_others() -> None:
    from_file = FirstFixConfig.model_validate(
        {
            "priors": {
                "heading_deg": {"centre": 30.0, "half_width": 45.0},
                "pitch_deg": {"centre": -40.0, "half_width": 15.0},
            }
        }
    )

    config = with_priors(from_file, heading_deg=Interval(centre=200.0, half_width=30.0))

    assert config.priors.heading_deg == Interval(centre=200.0, half_width=30.0)
    assert config.priors.pitch_deg == Interval(centre=-40.0, half_width=15.0)
    assert config.priors.position is None
