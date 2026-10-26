"""The satmesh command."""

import os

# The correction runs its own threads and processes; a BLAS pool inside each of them oversubscribes
# the cores (window matching took 8.7 s with it, 3.4 s without). Read when numpy loads, so this
# must run before any import of it; an exported value wins.
for _variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS"):
    os.environ.setdefault(_variable, "1")
