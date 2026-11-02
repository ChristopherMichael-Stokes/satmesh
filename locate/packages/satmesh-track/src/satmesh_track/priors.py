"""Settings of the prior-aware first fix: the priors on the first photo's pose and the search grids.

A prior is a centre and a half-width on one pose parameter (`satmesh_locate.events.Interval`), or
a circle in store ENU metres for the position; a missing prior is the full range. Heading wraps at
360 degrees; height is above the ground; pitch is positive upward. A window should be about twice
the stated error: on the 2.5 km Bexhill store a heading hint 30 degrees off, with the truth at the
window's edge, dropped level 1 recall at five places from 0.93 to 0.64.

Settings come from a TOML file whose keys are the fields of `FirstFixConfig` (priors under
`[priors.heading_deg]`, `[priors.pitch_deg]`, `[priors.height_m]` and `[priors.position]`), and
heading, pitch and height priors also from command-line text `CENTRE+-HALF_WIDTH`.

The grid values are those measured on the Bexhill clip: level 1 positions every 280 m, headings
every 30 degrees, heights 90 and 110 m above ground (retrieval prefers them even for photos at 51
to 74 m), both pitches (one pitch lost 18 points of recall at five places); level 2 positions every
70 m within 250 m of a level 1 place at five heights.
"""

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from satmesh_locate.events import Interval, PositionPrior, Priors

FULL_CIRCLE_DEG = 360.0
INTERVAL_SEPARATOR = "+-"

type YawMethod = Literal["essential", "homography", "agree"]

NO_PRIORS = Priors(position=None, heading_deg=None, pitch_deg=None, height_m=None)


class FirstFixConfig(BaseModel):
    """Priors, frame fusion and search grids of the first fix.

    `fusion_frames` photos, `fusion_frame_step` photos apart, are fused at level 1 (five frames
    2 s apart lifted K=1 recall on the 2.5 km store from 0.87 to 0.99; the Bexhill frames are
    2 a second). Their heading offsets come from XFeat matches with a nominal lens of
    `nominal_horizontal_fov_deg` and a camera pitch of `assumed_pitch_deg`. `yaw_agreement_deg`
    is a tunable from one clip: with `yaw_method="agree"` both estimators must be this close.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    priors: Priors = NO_PRIORS
    yaw_method: YawMethod = "essential"
    fusion_frames: int = Field(default=5, ge=1)
    fusion_frame_step: int = Field(default=4, ge=1)
    nominal_horizontal_fov_deg: float = Field(default=80.0, gt=0.0, lt=180.0)
    assumed_pitch_deg: float = Field(default=-35.0, ge=-90.0, le=90.0)
    yaw_agreement_deg: float = Field(default=5.0, gt=0.0)
    heading_step_deg: float = Field(default=30.0, gt=0.0, le=FULL_CIRCLE_DEG)
    render_width_px: int = Field(default=640, gt=0)
    render_height_px: int = Field(default=360, gt=0)
    coarse_spacing_m: float = Field(default=280.0, gt=0.0)
    coarse_heights_m: tuple[float, ...] = Field(default=(90.0, 110.0), min_length=1)
    coarse_pitches_deg: tuple[float, ...] = Field(default=(-35.0, -50.0), min_length=1)
    coarse_places: int = Field(default=5, ge=1)
    coarse_separation_m: float = Field(default=280.0, ge=0.0)
    fine_spacing_m: float = Field(default=70.0, gt=0.0)
    fine_radius_m: float = Field(default=250.0, ge=0.0)
    fine_heights_m: tuple[float, ...] = Field(default=(40.0, 55.0, 72.0, 90.0, 110.0), min_length=1)
    fine_pitches_deg: tuple[float, ...] = Field(default=(-35.0, -50.0), min_length=1)
    final_places: int = Field(default=6, ge=1)
    final_separation_m: float = Field(default=100.0, ge=0.0)
    refine_radius_m: float = Field(default=70.0, ge=0.0)
    refine_spacing_m: float = Field(default=35.0, gt=0.0)
    refine_height_factors: tuple[float, ...] = Field(default=(0.7, 1.0, 1.3), min_length=1)
    refine_pitch_offsets_deg: tuple[float, ...] = Field(default=(-10.0, 0.0, 10.0), min_length=1)
    refine_heading_offsets_deg: tuple[float, ...] = Field(
        default=(-30.0, -15.0, 0.0, 15.0, 30.0), min_length=1
    )
    verify_photos: int = Field(default=12, ge=1)
    min_tracked_photos: int = Field(default=6, ge=1)

    @field_validator("priors", mode="before")
    @classmethod
    def _missing_priors_are_none(cls, value: object) -> object:
        """A prior left out of a file is the full range (TOML has no null)."""
        if isinstance(value, dict):
            return dict.fromkeys(Priors.model_fields) | value
        return value

    @model_validator(mode="after")
    def _heading_step_divides_the_circle(self) -> "FirstFixConfig":
        steps = FULL_CIRCLE_DEG / self.heading_step_deg
        if abs(steps - round(steps)) > 1e-9:  # noqa: PLR2004  # float tolerance of the division
            message = f"heading_step_deg {self.heading_step_deg} does not divide 360"
            raise ValueError(message)
        return self


def load_config(path: Path) -> FirstFixConfig:
    """The settings in a TOML file; keys left out keep their defaults.

    Raises:
        tomllib.TOMLDecodeError: the file is not TOML.
        pydantic.ValidationError: a key is unknown or a value out of range.
    """
    with path.open("rb") as file:
        return FirstFixConfig.model_validate(tomllib.load(file))


def parse_interval(text: str) -> Interval:
    """`"30+-45"` as an interval with centre 30 and half-width 45.

    Raises:
        ValueError: the text is not two numbers joined by `+-`, or the half-width is negative.
    """
    centre, separator, half_width = text.partition(INTERVAL_SEPARATOR)
    if not separator:
        message = f"expected CENTRE{INTERVAL_SEPARATOR}HALF_WIDTH, got {text!r}"
        raise ValueError(message)
    return Interval(centre=float(centre), half_width=float(half_width))


def with_priors(
    config: FirstFixConfig,
    *,
    position: PositionPrior | None = None,
    heading_deg: Interval | None = None,
    pitch_deg: Interval | None = None,
    height_m: Interval | None = None,
) -> FirstFixConfig:
    """`config` with each prior that is given replacing the one it holds."""
    given = {
        "position": position,
        "heading_deg": heading_deg,
        "pitch_deg": pitch_deg,
        "height_m": height_m,
    }
    replaced = config.priors.model_copy(
        update={name: prior for name, prior in given.items() if prior is not None}
    )
    return config.model_copy(update={"priors": replaced})
