"""Textured mesh exported as a GLB."""

import io

import numpy as np
import pygltflib
import trimesh
from PIL import Image
from trimesh.visual import TextureVisuals
from trimesh.visual.material import PBRMaterial

from satmesh_data import Raster

JPEG_QUALITY = 92
# glTF sampler constants (Khronos glTF 2.0 spec, sampler.schema.json)
LINEAR = 9729
LINEAR_MIPMAP_LINEAR = 9987
CLAMP_TO_EDGE = 33071


def glb_bytes(
    vertices: np.ndarray, uv: np.ndarray, triangles: np.ndarray, texture: Raster
) -> bytes:
    """Return a GLB of the mesh in the glTF frame (x east, y up, z south) draped with `texture`.

    `uv` has v up from the texture's bottom edge; trimesh flips v on export to glTF's top-left
    origin. The material is non-metallic with a white base so the photo renders unlit-looking
    instead of near black.
    """
    material = PBRMaterial(
        baseColorTexture=_jpeg(texture),
        baseColorFactor=[255, 255, 255, 255],
        metallicFactor=0.0,
        roughnessFactor=1.0,
    )
    mesh = trimesh.Trimesh(
        vertices, triangles, visual=TextureVisuals(uv=uv, material=material), process=False
    )
    data = trimesh.Scene(mesh).export(file_type="glb")
    if not isinstance(data, bytes):
        msg = f"trimesh exported {type(data).__name__}, expected bytes"
        raise TypeError(msg)
    return with_clamped_textures(data)


def with_clamped_textures(glb: bytes) -> bytes:
    """Return `glb` with every texture sampled clamp-to-edge.

    glTF's default sampler repeats the texture, so a bilinear tap at a tile's edge mixes in the
    opposite edge and draws a dotted line along every tile boundary. trimesh writes no sampler and
    drops any it reads, so the sampler is added after each export.
    """
    gltf = pygltflib.GLTF2.load_from_bytes(glb)
    gltf.samplers = [
        pygltflib.Sampler(
            magFilter=LINEAR,
            minFilter=LINEAR_MIPMAP_LINEAR,
            wrapS=CLAMP_TO_EDGE,
            wrapT=CLAMP_TO_EDGE,
        )
    ]
    for texture in gltf.textures:
        texture.sampler = 0
    return b"".join(gltf.save_to_bytes())


def upward(vertices: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    """Return `triangles` wound counter-clockwise seen from above (+y), as glTF front faces need."""
    a, b, c = (vertices[triangles[:, i]] for i in range(3))
    normal_y = np.cross(b - a, c - a)[:, 1]
    if (normal_y > 0).all():
        return triangles
    if (normal_y < 0).all():
        return triangles[:, ::-1].copy()
    msg = "TIN winding is inconsistent: some faces point up, some down"
    raise ValueError(msg)


def _jpeg(texture: Raster) -> Image.Image:
    buffer = io.BytesIO()
    Image.fromarray(np.moveaxis(texture.pixels, 0, -1)).save(
        buffer, format="JPEG", quality=JPEG_QUALITY
    )
    # an image opened from JPEG bytes keeps format "JPEG", which trimesh embeds as JPEG, not PNG
    return Image.open(buffer)
