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


def read_vertices(glb: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Return the positions (glTF frame) and texture coordinates of a single-primitive GLB.

    The coordinates have v up from the texture's bottom edge, as `glb_bytes` takes them.
    """
    gltf = pygltflib.GLTF2.load_from_bytes(glb)
    blob = gltf.binary_blob()
    attributes = _only_primitive(gltf).attributes
    positions = np.frombuffer(blob, np.float32, *_float_span(gltf, attributes.POSITION, 3))
    uv = np.frombuffer(blob, np.float32, *_float_span(gltf, attributes.TEXCOORD_0, 2))
    flipped = uv.reshape(-1, 2).astype(np.float64)
    flipped[:, 1] = 1 - flipped[:, 1]
    return positions.reshape(-1, 3).astype(np.float64), flipped


def with_texture_coordinates(glb: bytes, uv: np.ndarray) -> bytes:
    """Return `glb` with its texture coordinates replaced by `uv` (v up from the bottom edge).

    The texture pixels and every other attribute are untouched; only where each vertex samples
    the texture moves. `uv` has one row per vertex of the single primitive.
    """
    gltf = pygltflib.GLTF2.load_from_bytes(glb)
    blob = bytearray(gltf.binary_blob())
    index = _only_primitive(gltf).attributes.TEXCOORD_0
    count, start = _float_span(gltf, index, 2)
    if uv.shape != (count // 2, 2):
        msg = f"{uv.shape[0]} texture coordinates for {count // 2} vertices"
        raise ValueError(msg)
    in_file = np.column_stack([uv[:, 0], 1 - uv[:, 1]]).astype(np.float32)
    blob[start : start + in_file.nbytes] = in_file.tobytes()
    accessor = gltf.accessors[index]
    accessor.min = in_file.min(axis=0).tolist()
    accessor.max = in_file.max(axis=0).tolist()
    gltf.set_binary_blob(bytes(blob))
    return b"".join(gltf.save_to_bytes())


def _only_primitive(gltf: pygltflib.GLTF2) -> pygltflib.Primitive:
    primitives = [primitive for mesh in gltf.meshes for primitive in mesh.primitives]
    if len(primitives) != 1:
        msg = f"expected one mesh primitive, found {len(primitives)}"
        raise ValueError(msg)
    return primitives[0]


def _float_span(gltf: pygltflib.GLTF2, index: int | None, components: int) -> tuple[int, int]:
    """Return (float count, byte offset) of a tightly packed float accessor in the binary blob."""
    if index is None:
        msg = "the primitive lacks a required attribute"
        raise ValueError(msg)
    accessor = gltf.accessors[index]
    if accessor.bufferView is None:
        msg = "sparse or empty accessors are not supported"
        raise ValueError(msg)
    view = gltf.bufferViews[accessor.bufferView]
    if view.byteStride not in {None, components * np.dtype(np.float32).itemsize}:
        msg = "interleaved vertex attributes are not supported"
        raise ValueError(msg)
    return accessor.count * components, (view.byteOffset or 0) + (accessor.byteOffset or 0)


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
