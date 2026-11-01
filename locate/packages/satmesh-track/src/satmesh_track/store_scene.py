"""The tracker's scene from a tile store: GPU renders of the full surface and bare-earth heights."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from satmesh_eval.gpu import GpuRenderer
from satmesh_eval.ground import ground_height_m, load_ground_scene
from satmesh_eval.perspective import GroundExtent, load_area_scene
from satmesh_track.tracker import Scene


@dataclass(frozen=True)
class StoreScene:
    """A `Scene`, the area the store covers and a key that changes when the store does."""

    scene: Scene
    bounds: GroundExtent
    key: str


def load_store_scene(store: Path) -> StoreScene:
    """Load every finest-level leaf of `store`; the surface is rendered by `GpuRenderer`."""
    surface = load_area_scene(store)
    ground = load_ground_scene(store)
    low = np.min([leaf.mesh.bounds[0] for leaf in surface.leaves], axis=0)
    high = np.max([leaf.mesh.bounds[1] for leaf in surface.leaves], axis=0)
    newest = max(path.stat().st_mtime_ns for path in store.rglob("*.glb"))
    return StoreScene(
        Scene(
            GpuRenderer(surface).render,
            surface.frame,
            lambda east, north: ground_height_m(ground, east, north),
        ),
        GroundExtent(float(low[0]), float(high[0]), float(low[1]), float(high[1])),
        f"{store.resolve()}:{len(surface.leaves)}:{newest}",
    )
