"""`satmesh-monitor`: serve a first-fix run's event file as a map page."""

from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from satmesh_monitor.app import create_app

CACHE_ROOT = Path.home() / ".cache" / "satmesh"
DEFAULT_IMAGERY_DIR = CACHE_ROOT / "esri-world-imagery" / "live"
ASSEMBLED_TILES_DIR = CACHE_ROOT / "monitor-tiles"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

app = typer.Typer(add_completion=False)


@app.command()
def serve(
    run_dir: Annotated[Path, typer.Argument(help="Run directory holding events.jsonl.")],
    host: Annotated[str, typer.Option(help="Address to listen on.")] = DEFAULT_HOST,
    port: Annotated[int, typer.Option(help="Port to listen on.")] = DEFAULT_PORT,
    photos: Annotated[Path | None, typer.Option(help="Directory with the run's photos.")] = None,
    tiles: Annotated[
        Path, typer.Option(help="Esri tile cache laid out ZOOM/Y/X.jpg; never fetched from.")
    ] = DEFAULT_IMAGERY_DIR,
) -> None:
    """Show a run on a map; a finished run replays, a growing one is followed."""
    uvicorn.run(create_app(run_dir, tiles, ASSEMBLED_TILES_DIR, photos), host=host, port=port)
