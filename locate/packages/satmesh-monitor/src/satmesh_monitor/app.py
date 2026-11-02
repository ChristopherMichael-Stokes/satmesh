"""The monitor's HTTP routes: the page, the event feed, imagery tiles and the run's photos."""

import os
from pathlib import Path
from typing import override

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from satmesh_monitor.feed import read_page, run_photo_names
from satmesh_monitor.mercator import Tile
from satmesh_monitor.tiles import read_tile_jpeg

STATIC_DIR = Path(__file__).parent / "static"
TILE_CACHE_CONTROL = "public, max-age=3600"
REVALIDATE = "no-cache"  # without it a browser reuses an old script beside a new page


class RevalidatedStaticFiles(StaticFiles):
    """Static files that a browser must revalidate (a 304 when unchanged) on every load."""

    @override
    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        """The file's response with `Cache-Control: no-cache`."""
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = REVALIDATE
        return response


def create_app(
    run_dir: Path, imagery_dir: Path, assembled_dir: Path, photos_dir: Path | None
) -> Starlette:
    """The monitor for `run_dir`; imagery comes from `imagery_dir` only, never from the network.

    Raises:
        NotADirectoryError: `run_dir` is not a directory.
    """
    if not run_dir.is_dir():
        message = f"run directory {run_dir} does not exist"
        raise NotADirectoryError(message)

    def index(_: Request) -> Response:
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": REVALIDATE})

    def events(request: Request) -> Response:
        after = max(0, int(request.query_params.get("after", "0")))
        page = read_page(run_dir, after)
        return JSONResponse(
            {
                "events": [event.model_dump(mode="json") for event in page.events],
                "total": page.total,
                "finished": page.finished,
                "has_photos": photos_dir is not None,
            }
        )

    def tile(request: Request) -> Response:
        path = request.path_params
        jpeg = read_tile_jpeg(imagery_dir, assembled_dir, Tile(path["zoom"], path["x"], path["y"]))
        if jpeg is None:
            return Response(status_code=404)
        return Response(
            jpeg, media_type="image/jpeg", headers={"Cache-Control": TILE_CACHE_CONTROL}
        )

    def photo(request: Request) -> Response:
        name = str(request.path_params["name"])
        if photos_dir is None or name not in run_photo_names(run_dir):
            return Response(status_code=404)
        path = photos_dir / name
        if path.parent != photos_dir or not path.is_file():
            return Response(status_code=404)
        return FileResponse(path)

    return Starlette(
        routes=[
            Route("/", index),
            Route("/api/events", events),
            Route("/tiles/{zoom:int}/{x:int}/{y:int}.jpg", tile),
            Route("/api/photo/{name}", photo),
            Mount("/static", RevalidatedStaticFiles(directory=STATIC_DIR)),
        ]
    )
