"""What a command shows and keeps: progress bars and log lines on stderr, a run log in the store."""

import logging
import os
import platform
import sys
import time
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from importlib.metadata import version
from pathlib import Path
from typing import override

from loguru import logger
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from satmesh_core import ProgressReport

RUN_LOG_FILE = "run.log"
STDERR_FORMAT = "{time:HH:mm:ss} {message}"
FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} {level: <7} {message}"
FILE_ONLY = "file_only"
HTTP_LOGGERS = ("httpx", "httpcore")

console = Console(stderr=True)
# records for the run log alone: the terminal already shows the progress bars
file_log = logger.bind(**{FILE_ONLY: True})


class _InterceptHandler(logging.Handler):
    """Forward standard-library records, which the library packages emit, to loguru."""

    @override
    def emit(self, record: logging.LogRecord) -> None:
        level = logger.level(record.levelname).name
        logger.opt(exception=record.exc_info).log(level, record.getMessage())


class _PhaseProgress:
    """One progress bar per phase, created when the phase first reports; each phase is logged."""

    def __init__(self, progress: Progress) -> None:
        self._progress = progress
        self._tasks: dict[str, TaskID] = {}
        self._started: dict[str, float] = {}

    def __call__(self, phase: str, done: int, total: int) -> None:
        if phase not in self._tasks:
            self._tasks[phase] = self._progress.add_task(phase, total=total)
            self._started[phase] = time.perf_counter()
            file_log.info("{}: {} steps", phase, total)
        self._progress.update(self._tasks[phase], completed=done, total=total)
        if done == total:
            elapsed = time.perf_counter() - self._started[phase]
            file_log.info("{}: done in {:.1f} s", phase, elapsed)


@contextmanager
def run_log(store: Path, command: str, settings: Mapping[str, object]) -> Generator[ProgressReport]:
    """Show progress and log to stderr and `<store>/run.log` for the duration of one command.

    The run log is appended to, and starts with the command line, versions and `settings`; it ends
    with the elapsed time or the error that stopped the command. Yields the progress hook.
    """
    logger.remove()
    sinks = [
        logger.add(
            lambda message: console.out(message, end=""),
            level="INFO",
            format=STDERR_FORMAT,
            filter=lambda record: not record["extra"].get(FILE_ONLY),
        ),
        logger.add(store / RUN_LOG_FILE, level="DEBUG", format=FILE_FORMAT),
    ]
    logging.basicConfig(handlers=[_InterceptHandler()], level=logging.INFO, force=True)
    for name in HTTP_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    started = time.perf_counter()
    file_log.info("satmesh {}: {}", command, " ".join(sys.argv))
    file_log.info(
        "satmesh-cli {}, python {}, {} usable cores",
        version("satmesh-cli"),
        platform.python_version(),
        os.process_cpu_count(),
    )
    for name, value in settings.items():
        file_log.info("setting {} = {}", name, value)
    columns = (
        TextColumn("{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    )
    try:
        with Progress(*columns, console=console) as progress:
            yield _PhaseProgress(progress)
    except BaseException as error:
        file_log.error("failed after {:.1f} s: {!r}", _since(started), error)
        raise
    else:
        file_log.info("finished in {:.1f} s", _since(started))
    finally:
        for sink in sinks:
            logger.remove(sink)


def _since(started: float) -> float:
    return time.perf_counter() - started
