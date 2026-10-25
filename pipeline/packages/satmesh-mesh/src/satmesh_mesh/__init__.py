"""Textured terrain mesh from a DTM and an imagery raster, exported as georeferenced GLB."""

from satmesh_mesh.glb import MeshReport, to_glb
from satmesh_mesh.terrain import DEFAULT_MAX_ERROR_M, Tin, triangulate
from satmesh_mesh.texture import MAX_TEXTURE_PX, drape_texture

__all__ = [
    "DEFAULT_MAX_ERROR_M",
    "MAX_TEXTURE_PX",
    "MeshReport",
    "Tin",
    "drape_texture",
    "to_glb",
    "triangulate",
]
