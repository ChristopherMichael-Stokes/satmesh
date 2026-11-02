"""Events of a first-fix run and the append-only JSON Lines file that carries them.

A run writes one JSON object per line to `events.jsonl`; a monitor reads the file while the run
grows it, or afterwards as a replay. Every event holds `time_s`, seconds since the run started,
and a `kind` naming its type. Positions are store ENU metres (east, north), angles degrees.
Cells are summarised per position, never per rendered view.
"""

from collections.abc import Iterator
from pathlib import Path
from types import TracebackType
from typing import Annotated, Literal, Self, TextIO

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

SCHEMA_VERSION = 1
EVENTS_FILE = "events.jsonl"


class EventModel(BaseModel):
    """Base of all event parts: immutable, and a misspelt or extra field is an error."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Interval(EventModel):
    """A prior on one pose parameter: a centre and a half-width in the parameter's unit."""

    centre: float
    half_width: float = Field(ge=0.0)


class PositionPrior(EventModel):
    """A prior on position: a circle in store ENU metres."""

    east_m: float
    north_m: float
    radius_m: float = Field(ge=0.0)


class Priors(EventModel):
    """The priors a run starts with; a missing one is the full range."""

    position: PositionPrior | None
    heading_deg: Interval | None
    pitch_deg: Interval | None
    height_m: Interval | None


class Bounds(EventModel):
    """Rectangle of the store in ENU metres."""

    east_min_m: float
    east_max_m: float
    north_min_m: float
    north_max_m: float


class GridLevel(EventModel):
    """The plan of one search level."""

    level: int = Field(ge=1)
    spacing_m: float = Field(gt=0.0)
    positions: int = Field(ge=0)
    views: int = Field(ge=0)


class Cell(EventModel):
    """One searched position; `similarity` is the best over its views once described."""

    east_m: float
    north_m: float
    state: Literal["rendered", "described"]
    similarity: float | None


class Candidate(EventModel):
    """A ranked place: the pose of its best view and that view's similarity."""

    rank: int = Field(ge=1)
    east_m: float
    north_m: float
    height_m: float
    heading_deg: float
    pitch_deg: float
    similarity: float


class RunStart(EventModel):
    """First event: where the store sits, the priors, the frames and the grid plan."""

    kind: Literal["run_start"] = "run_start"
    time_s: float = Field(ge=0.0)
    schema_version: Literal[1] = SCHEMA_VERSION
    origin_latitude_deg: float
    origin_longitude_deg: float
    bounds: Bounds
    priors: Priors
    photos: list[str]
    levels: list[GridLevel]


class StageStart(EventModel):
    """A stage begins; `units` is the number of views or checks it will handle."""

    kind: Literal["stage_start"] = "stage_start"
    time_s: float = Field(ge=0.0)
    stage: str
    units: int = Field(ge=0)


class StageEnd(EventModel):
    """A stage ends."""

    kind: Literal["stage_end"] = "stage_end"
    time_s: float = Field(ge=0.0)
    stage: str


class CellBatch(EventModel):
    """Positions of one level that changed state since the last batch."""

    kind: Literal["cell_batch"] = "cell_batch"
    time_s: float = Field(ge=0.0)
    level: int = Field(ge=1)
    cells: list[Cell]


class Candidates(EventModel):
    """The ranked places after a level; replaces the previous candidates of that level."""

    kind: Literal["candidates"] = "candidates"
    time_s: float = Field(ge=0.0)
    level: int = Field(ge=1)
    places: list[Candidate]


class VerificationStart(EventModel):
    """A candidate is refined and tracked."""

    kind: Literal["verification_start"] = "verification_start"
    time_s: float = Field(ge=0.0)
    rank: int = Field(ge=1)


class VerificationResult(EventModel):
    """The outcome of a candidate's verification."""

    kind: Literal["verification_result"] = "verification_result"
    time_s: float = Field(ge=0.0)
    rank: int = Field(ge=1)
    inliers: int = Field(ge=0)
    frames_tracked: int = Field(ge=0)
    frames_total: int = Field(ge=0)
    accepted: bool


class PriorRelaxed(EventModel):
    """A prior was widened because nothing verified."""

    kind: Literal["prior_relaxed"] = "prior_relaxed"
    time_s: float = Field(ge=0.0)
    prior: Literal["heading", "pitch", "area"]
    half_width_before: float = Field(ge=0.0)
    half_width_after: float = Field(ge=0.0)


class Fix(EventModel):
    """The accepted first fix."""

    kind: Literal["fix"] = "fix"
    time_s: float = Field(ge=0.0)
    east_m: float
    north_m: float
    height_m: float
    heading_deg: float
    pitch_deg: float
    inliers: int = Field(ge=0)


class RunEnd(EventModel):
    """Last event; `ok` is false when the run found no fix."""

    kind: Literal["run_end"] = "run_end"
    time_s: float = Field(ge=0.0)
    ok: bool


type Event = Annotated[
    RunStart
    | StageStart
    | StageEnd
    | CellBatch
    | Candidates
    | VerificationStart
    | VerificationResult
    | PriorRelaxed
    | Fix
    | RunEnd,
    Field(discriminator="kind"),
]

_EVENT_ADAPTER: TypeAdapter[Event] = TypeAdapter(Event)


class EventWriter:
    """Appends events to a JSON Lines file, flushing each so a tailing reader sees it."""

    def __init__(self, path: Path) -> None:
        """Open `path` for appending, creating it if needed."""
        self._file: TextIO = path.open("a", encoding="utf-8")

    def write(self, event: Event) -> None:
        """Append one event."""
        self._file.write(_EVENT_ADAPTER.dump_json(event).decode("utf-8") + "\n")
        self._file.flush()

    def close(self) -> None:
        """Close the file."""
        self._file.close()

    def __enter__(self) -> Self:
        """Return the writer."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the file."""
        self.close()


def read_events(path: Path) -> Iterator[Event]:
    """Events of a file in order.

    A last line without its newline is a write in progress and is left for the next read.

    Raises:
        pydantic.ValidationError: a complete line is not a valid event or has another version.
    """
    with path.open(encoding="utf-8") as file:
        for line in file:
            if not line.endswith("\n"):
                return
            yield _EVENT_ADAPTER.validate_json(line)
