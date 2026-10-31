"""Quadtree of nodes over an area and the resumable build that fills the store."""

import json
import logging
import math
from collections.abc import Iterable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import httpx
import mercantile
import numpy as np
from rasterio.transform import from_bounds

from satmesh_core import (
    Aoi,
    ProgressReport,
    ellipsoidal_height_from,
    metric_crs,
    wgs84_to,
)
from satmesh_data import (
    WEB_MERCATOR,
    EsriClient,
    EsriSource,
    Raster,
    SurfacePair,
    SurfaceSource,
    choose_zoom,
    fetch_surfaces,
    mosaic_tiles,
    select_surface_source,
)
from satmesh_mesh import DEFAULT_MAX_ERROR_M
from satmesh_tiles.node import (
    LEAF_ZOOM_DEPTH,
    MeshSettings,
    NodeRecord,
    build_node,
    esri_tiles,
)

logger = logging.getLogger(__name__)

CHILDREN_PER_PARENT = 4
# (dx, dy) of the north-west, north-east, south-west and south-east child; mercantile.children
# lists them in another order
CHILD_ORDER = ((0, 0), (1, 0), (0, 1), (1, 1))
STORE_NODE_DIR = Path("nodes")
CORRECTION_FILE = "correction.json"
# 2: per-vertex correction with one ground shift and lean per Esri scene; 1 (no version key) moved
# every vertex of a node by the ground shift at its centre
CORRECTION_SCHEMA_VERSION = 2
# one thread fetching a leaf's Esri tiles and one its DSM and DTM, so the Esri request schedule
# never idles while a node is meshed or the EA WCS answers
PREFETCH_WORKERS = 2
NODES_PHASE = "nodes"


@dataclass(frozen=True)
class TilePlan:
    """The nodes to build: leaves at one zoom and the parents whose four children all exist.

    A parent needs all four children so its texture has no hole. The ragged edge of an area
    therefore stays at leaf resolution, and `roots` lists the maximal complete nodes.
    """

    leaf_zoom: int
    imagery: EsriSource
    source: SurfaceSource
    leaves: tuple[mercantile.Tile, ...]
    children: dict[mercantile.Tile, tuple[mercantile.Tile, ...]]
    roots: tuple[mercantile.Tile, ...]


@dataclass(frozen=True)
class BuildSummary:
    """Nodes written and nodes found already present."""

    built: int
    skipped: int


def snap_outward(aoi: Aoi) -> Aoi:
    """Return the AOI as a box in its metric CRS with whole-metre edges, grown outward."""
    crs = metric_crs(aoi)
    west, south, east, north = aoi.bounds_in(crs)
    return Aoi(
        crs=crs,
        west=math.floor(west),
        south=math.floor(south),
        east=math.ceil(east),
        north=math.ceil(north),
    )


def plan_tiles(aoi: Aoi, esri: EsriClient) -> TilePlan:
    """Plan the tree for `aoi`: native zoom from Esri metadata at the centre, leaves covering it."""
    # fail before any fetch if the datum grids the AOI's elevation source needs are missing
    wgs84_to(metric_crs(aoi))
    source = select_surface_source(aoi)
    ellipsoidal_height_from(source.height_crs)
    west, south, east, north = snap_outward(aoi).wgs84_bounds()
    zoom, imagery = choose_zoom(
        esri.sources_at((west + east) / 2, (south + north) / 2), (south + north) / 2
    )
    leaf_zoom = zoom - LEAF_ZOOM_DEPTH
    if leaf_zoom < 0:
        msg = f"native zoom {zoom} is shallower than a leaf's {LEAF_ZOOM_DEPTH} levels"
        raise ValueError(msg)
    leaves = tuple(mercantile.tiles(west, south, east, north, [leaf_zoom]))
    children, roots = complete_tree(leaves)
    return TilePlan(leaf_zoom, imagery, source, leaves, children, roots)


def complete_tree(
    leaves: Iterable[mercantile.Tile],
) -> tuple[dict[mercantile.Tile, tuple[mercantile.Tile, ...]], tuple[mercantile.Tile, ...]]:
    """Return each complete parent's children, and the maximal complete nodes.

    A tile is a node if it is a leaf or all four of its children are nodes.
    """
    nodes = set(leaves)
    children: dict[mercantile.Tile, tuple[mercantile.Tile, ...]] = {}
    level = nodes
    while level:
        candidates = {mercantile.parent(tile) for tile in level if tile.z > 0}
        level = set()
        for candidate in candidates:
            kids = ordered_children(candidate)
            if all(kid in nodes for kid in kids):
                children[candidate] = kids
                level.add(candidate)
        nodes |= level
    inside = {kid for kids in children.values() for kid in kids}
    return children, tuple(sorted(nodes - inside))


def ordered_children(tile: mercantile.Tile) -> tuple[mercantile.Tile, ...]:
    """Return the four children of `tile`: north-west, north-east, south-west, south-east."""
    return tuple(
        mercantile.Tile(2 * tile.x + dx, 2 * tile.y + dy, tile.z + 1) for dx, dy in CHILD_ORDER
    )


def parent_texture(children: Sequence[Raster], parent: mercantile.Tile) -> Raster:
    """Return the texture of `parent`: its four children (north-west first) halved by 2 x 2 mean."""
    if len(children) != CHILDREN_PER_PARENT:
        msg = f"a parent has {CHILDREN_PER_PARENT} children, got {len(children)}"
        raise ValueError(msg)
    rows, cols = children[0].pixels.shape[1:]
    stitched = np.empty((children[0].pixels.shape[0], 2 * rows, 2 * cols), np.uint8)
    for child, (dx, dy) in zip(children, CHILD_ORDER, strict=True):
        stitched[:, dy * rows : (dy + 1) * rows, dx * cols : (dx + 1) * cols] = child.pixels
    halved = stitched.reshape(stitched.shape[0], rows, 2, cols, 2).mean(axis=(2, 4))
    bounds = mercantile.xy_bounds(parent)
    transform = from_bounds(bounds.left, bounds.bottom, bounds.right, bounds.top, cols, rows)
    return Raster(np.rint(halved).astype(np.uint8), transform, WEB_MERCATOR)


def node_paths(store_dir: Path, tile: mercantile.Tile) -> tuple[Path, Path]:
    """Return the GLB and record paths of a node; the record is written last."""
    base = store_dir / STORE_NODE_DIR / str(tile.z) / str(tile.x)
    return base / f"{tile.y}.glb", base / f"{tile.y}.json"


def ground_path(store_dir: Path, tile: mercantile.Tile) -> Path:
    """Return the path of a node's ground (DTM) height grid, a Web Mercator GeoTIFF."""
    return node_paths(store_dir, tile)[0].with_suffix(".ground.tif")


class StaleCorrectionError(ValueError):
    """The store was corrected by an older `satmesh correct` whose records cannot be read."""


def require_current_correction(store_dir: Path) -> None:
    """Raise `StaleCorrectionError` if the store's correction predates the current schema.

    A store that was never corrected passes. Its node records and texture coordinates follow the
    correction file, so there is no reading an older one: the store is rebuilt and corrected again.
    """
    path = store_dir / CORRECTION_FILE
    if not path.exists():
        return
    version = json.loads(path.read_text()).get("schema_version")
    if version != CORRECTION_SCHEMA_VERSION:
        msg = (
            f"{store_dir} was corrected by an older satmesh (correction schema {version or 1}, "
            f"this one writes {CORRECTION_SCHEMA_VERSION}); rebuild it with `satmesh build` "
            "into a fresh store and re-run `satmesh correct`"
        )
        raise StaleCorrectionError(msg)


def read_record(store_dir: Path, tile: mercantile.Tile) -> NodeRecord:
    """Return the record of a built node."""
    return NodeRecord.model_validate_json(node_paths(store_dir, tile)[1].read_text())


def build_store(  # noqa: PLR0913 (edges of the build: network clients, directories, tolerance)
    plan: TilePlan,
    store_dir: Path,
    *,
    esri: EsriClient,
    http: httpx.Client,
    cache_dir: Path,
    report: ProgressReport,
    max_error_m: float = DEFAULT_MAX_ERROR_M,
) -> BuildSummary:
    """Write every missing node of `plan` to `store_dir`; nodes already present are skipped.

    Leaves fetch their 16 Esri tiles (cached by the client) and a DSM and a DTM box (cached by the
    fetch);
    parents are halved from their children's textures and meshed at twice the grid spacing and
    error per level. A rerun after an interruption repeats no network request and no finished node.
    Fetches for the leaves still to come run ahead of the node being built, in build order.
    `report` is called with phase "nodes" before the first node and after each one.
    """
    counts = {"built": 0, "skipped": 0}
    total = len(plan.leaves) + len(plan.children)
    report(NODES_PHASE, 0, total)
    prefetcher = ThreadPoolExecutor(PREFETCH_WORKERS)
    fetches = {
        leaf: _submit_fetches(
            prefetcher, leaf, plan, esri, http, cache_dir, surfaces_missing=surfaces_missing
        )
        for leaf, surfaces_missing in _leaves_to_fetch(plan, store_dir)
    }

    def build(tile: mercantile.Tile, *, texture_needed: bool) -> Raster | None:
        missing = not node_paths(store_dir, tile)[1].exists()
        needed = missing or texture_needed
        kids = plan.children.get(tile, ())
        child_textures = [build(kid, texture_needed=needed) for kid in kids]
        if not needed:
            counts["skipped"] += 1
            report(NODES_PHASE, counts["built"] + counts["skipped"], total)
            return None
        for fetch in fetches.get(tile, ()):
            fetch.result()
        texture = (
            parent_texture([t for t in child_textures if t is not None], tile)
            if kids
            else mosaic_tiles(esri, esri_tiles(tile), plan.leaf_zoom + LEAF_ZOOM_DEPTH)
        )
        if not missing:
            counts["skipped"] += 1
            report(NODES_PHASE, counts["built"] + counts["skipped"], total)
            return texture
        _write_node(
            store_dir,
            tile,
            texture,
            _fetch_surfaces(http, tile, cache_dir),
            plan.imagery,
            MeshSettings.for_level(plan.leaf_zoom - tile.z, max_error_m),
        )
        counts["built"] += 1
        report(NODES_PHASE, counts["built"] + counts["skipped"], total)
        return texture

    try:
        for root in plan.roots:
            build(root, texture_needed=False)
    finally:
        prefetcher.shutdown(cancel_futures=True)
    return BuildSummary(counts["built"], counts["skipped"])


def _leaves_to_fetch(plan: TilePlan, store_dir: Path) -> list[tuple[mercantile.Tile, bool]]:
    """Return the leaves `build_store` reads imagery for, in its order, each with its surface need.

    A leaf needs its DSM and DTM when the leaf itself is missing, not only an ancestor.
    """
    found: list[tuple[mercantile.Tile, bool]] = []

    def visit(tile: mercantile.Tile, *, texture_needed: bool) -> None:
        missing = not node_paths(store_dir, tile)[1].exists()
        needed = missing or texture_needed
        kids = plan.children.get(tile, ())
        for kid in kids:
            visit(kid, texture_needed=needed)
        if needed and not kids:
            found.append((tile, missing))

    for root in plan.roots:
        visit(root, texture_needed=False)
    return found


def _submit_fetches(  # noqa: PLR0913, PLR0917 (one leaf's inputs and the two clients)
    pool: ThreadPoolExecutor,
    leaf: mercantile.Tile,
    plan: TilePlan,
    esri: EsriClient,
    http: httpx.Client,
    cache_dir: Path,
    *,
    surfaces_missing: bool,
) -> list[Future[object]]:
    """Queue the fetches of one leaf; each fills a cache that the build then reads."""
    zoom = plan.leaf_zoom + LEAF_ZOOM_DEPTH
    fetches: list[Future[object]] = [pool.submit(mosaic_tiles, esri, esri_tiles(leaf), zoom)]
    if surfaces_missing:
        fetches.append(pool.submit(_fetch_surfaces, http, leaf, cache_dir))
    return fetches


def _write_node(  # noqa: PLR0913, PLR0917 (one node's inputs)
    store_dir: Path,
    tile: mercantile.Tile,
    texture: Raster,
    surfaces: SurfacePair,
    imagery: EsriSource,
    settings: MeshSettings,
) -> None:
    node = build_node(tile, texture, surfaces, imagery, settings)
    glb_path, record_path = node_paths(store_dir, tile)
    glb_path.parent.mkdir(parents=True, exist_ok=True)
    write_atomically(glb_path, node.glb)
    write_atomically(ground_path(store_dir, tile), node.ground_tif)
    write_atomically(record_path, node.record.model_dump_json(indent=1).encode())
    logger.info("built node z%d x%d y%d: %d vertices", tile.z, tile.x, tile.y, node.record.vertices)


def _fetch_surfaces(http: httpx.Client, tile: mercantile.Tile, cache_dir: Path) -> SurfacePair:
    bounds = mercantile.xy_bounds(tile)
    footprint = Aoi(
        crs=WEB_MERCATOR, west=bounds.left, south=bounds.bottom, east=bounds.right, north=bounds.top
    )
    return fetch_surfaces(http, footprint, cache_dir)


def write_atomically(path: Path, data: bytes) -> None:
    """Write `data` to `path` through a sibling `.part` file, so a reader never sees half of it."""
    partial = path.with_suffix(path.suffix + ".part")
    partial.write_bytes(data)
    partial.replace(path)
