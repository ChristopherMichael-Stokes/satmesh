"""The progress hook that long-running steps call, free of any display library."""

from collections.abc import Callable

# (phase, steps done, steps in the phase): called when a phase starts with done = 0 and after each
# step; a phase that reaches done == total is finished
ProgressReport = Callable[[str, int, int], None]
