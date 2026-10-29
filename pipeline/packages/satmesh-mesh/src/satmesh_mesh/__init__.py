"""Adaptive terrain triangulation, skirts and textured GLB export."""

from satmesh_mesh.glb import (
    glb_bytes,
    read_vertices,
    upward,
    with_clamped_textures,
    with_texture_coordinates,
)
from satmesh_mesh.skirt import add_skirts
from satmesh_mesh.terrain import DEFAULT_MAX_ERROR_M, GridTin, triangulate_heights

__all__ = [
    "DEFAULT_MAX_ERROR_M",
    "GridTin",
    "add_skirts",
    "glb_bytes",
    "read_vertices",
    "triangulate_heights",
    "upward",
    "with_clamped_textures",
    "with_texture_coordinates",
]
