"""What the monitor reads from a run directory: event-file pages and the run's photo names."""

from dataclasses import dataclass
from pathlib import Path

from satmesh_locate.events import EVENTS_FILE, Event, RunEnd, RunStart, read_events


@dataclass(frozen=True)
class EventPage:
    """Events from one index on, the number of events in the file and whether the run ended."""

    events: list[Event]
    total: int
    finished: bool


def read_page(run_dir: Path, after: int) -> EventPage:
    """Events with index >= `after`; a run that has not written its file yet has none."""
    path = run_dir / EVENTS_FILE
    events = list(read_events(path)) if path.is_file() else []
    return EventPage(
        events=events[after:],
        total=len(events),
        finished=bool(events) and isinstance(events[-1], RunEnd),
    )


def run_photo_names(run_dir: Path) -> list[str]:
    """The photo names the run declared, empty before its first event."""
    path = run_dir / EVENTS_FILE
    first = next(read_events(path), None) if path.is_file() else None
    return first.photos if isinstance(first, RunStart) else []
