"""Pose file of the localisation harness: one JSON line per photo with its true camera pose.

A line holds the photo's file name (relative to the photo directory), the camera pose as WGS 84
latitude, longitude and ellipsoidal height with heading (clockwise from north), pitch (positive
up) and roll in degrees, and the intrinsics with radial distortion. The pose is the photo's true
pose (logged GPS and attitude); the harness renders at a prior and scores the recovered pose
against it. An optional `prior` object with the same six pose fields replaces the harness's
default prior offset for that photo.
"""

from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from satmesh_eval.camera import CameraPose, Intrinsics

Latitude = Annotated[float, Field(ge=-90.0, le=90.0)]
Longitude = Annotated[float, Field(ge=-180.0, le=180.0)]
PositivePixels = Annotated[float, Field(gt=0.0)]


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PoseFields(_Record):
    """Camera position and attitude as in `CameraPose`."""

    latitude_deg: Latitude
    longitude_deg: Longitude
    ellipsoidal_height_m: float
    heading_deg: float
    pitch_deg: Annotated[float, Field(ge=-90.0, le=90.0)]
    roll_deg: float

    def to_pose(self) -> CameraPose:
        """The pose as the camera module's type."""
        return CameraPose(
            self.latitude_deg,
            self.longitude_deg,
            self.ellipsoidal_height_m,
            self.heading_deg,
            self.pitch_deg,
            self.roll_deg,
        )


class IntrinsicsFields(_Record):
    """Intrinsics in pixels with OpenCV radial distortion, as in `Intrinsics`."""

    width_px: Annotated[int, Field(gt=0)]
    height_px: Annotated[int, Field(gt=0)]
    focal_x_px: PositivePixels
    focal_y_px: PositivePixels
    principal_x_px: float
    principal_y_px: float
    radial_distortion: Annotated[tuple[float, ...], Field(max_length=3)] = ()

    def to_intrinsics(self) -> Intrinsics:
        """The intrinsics as the camera module's type."""
        return Intrinsics(
            self.width_px,
            self.height_px,
            self.focal_x_px,
            self.focal_y_px,
            self.principal_x_px,
            self.principal_y_px,
            self.radial_distortion,
        )


class PhotoRecord(PoseFields):
    """One line of the pose file."""

    photo: Annotated[str, Field(min_length=1)]
    intrinsics: IntrinsicsFields
    prior: PoseFields | None = None


def read_pose_file(path: Path) -> list[PhotoRecord]:
    """Parse a JSON-lines pose file; blank lines are skipped.

    Raises `ValueError` naming the line for malformed JSON, a missing or unknown field or an
    out-of-range value, and for a file without records or with a photo named twice.
    """
    records = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(PhotoRecord.model_validate_json(line))
        except ValidationError as error:
            msg = f"{path}:{number}: {error}"
            raise ValueError(msg) from error
    if not records:
        msg = f"{path} holds no records"
        raise ValueError(msg)
    names = [record.photo for record in records]
    if duplicated := sorted({name for name in names if names.count(name) > 1}):
        msg = f"{path} names photos more than once: {', '.join(duplicated)}"
        raise ValueError(msg)
    return records
