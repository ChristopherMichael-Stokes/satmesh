"""Textured TIN exported as a georeferenced GLB."""

import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image
from pyproj import Proj, Transformer
from trimesh.visual import TextureVisuals
from trimesh.visual.material import PBRMaterial

from satmesh_core import WGS84
from satmesh_data import Raster
from satmesh_mesh.terrain import Tin

JPEG_QUALITY = 92
# texture edges rebuilt from its transform carry float64 rounding (order 1e-10 m at BNG
# coordinates);
# 1e-6 m clears that and still rejects any real shift, which is a sizeable fraction of a pixel
BOX_MATCH_TOLERANCE_M = 1e-6
EXTRAS_KEY = "satmesh"


@dataclass(frozen=True)
class MeshReport:
    """What was written: sizes, accuracy and the georeference of the local glTF frame.

    glTF axes are x east, y up, z south in metres; local (0, 0, 0) is `origin` = (easting, northing,
    height) in `crs`. XY are CRS metres, not ground metres: ground distance is CRS distance /
    `point_scale`.
    """

    path: Path
    vertices: int
    triangles: int
    error_m: float
    crs: str
    origin: tuple[float, float, float]
    point_scale: float
    texture_px: tuple[int, int]
    texture_pixel_m: tuple[float, float]


def to_glb(tin: Tin, texture: Raster, path: Path) -> MeshReport:
    """Write `tin` draped with `texture` (which must cover exactly `tin.box`) to a GLB at `path`."""
    _require_matching_box(tin, texture)
    box = tin.box
    origin = (
        (box.west + box.east) / 2,
        (box.south + box.north) / 2,
        float(tin.vertices[:, 2].min()),
    )
    local = gltf_local(tin.vertices, origin)
    triangles = upward(local, tin.triangles)
    uv = np.column_stack(
        [
            (tin.vertices[:, 0] - box.west) / (box.east - box.west),
            (tin.vertices[:, 1] - box.south) / (box.north - box.south),
        ]
    )
    # trimesh takes OpenGL UVs (v up) and flips v on glTF export
    material = PBRMaterial(
        baseColorTexture=_jpeg(texture),
        baseColorFactor=[255, 255, 255, 255],
        metallicFactor=0.0,
        roughnessFactor=1.0,
    )
    mesh = trimesh.Trimesh(
        local, triangles, visual=TextureVisuals(uv=uv, material=material), process=False
    )
    point_scale = _point_scale(box.crs, origin[0], origin[1])
    report = MeshReport(
        path=path,
        vertices=len(local),
        triangles=len(triangles),
        error_m=tin.error_m,
        crs=box.crs,
        origin=origin,
        point_scale=point_scale,
        texture_px=(texture.pixels.shape[2], texture.pixels.shape[1]),
        texture_pixel_m=(texture.transform.a, -texture.transform.e),
    )
    scene = trimesh.Scene(
        mesh,
        metadata={
            EXTRAS_KEY: {
                "crs": box.crs,
                "origin": list(origin),
                "axes": "x east, y up, z south; metres",
                "point_scale": point_scale,
            }
        },
    )
    path.write_bytes(scene.export(file_type="glb"))
    return report


def gltf_local(vertices: np.ndarray, origin: tuple[float, float, float]) -> np.ndarray:
    """Map (easting, northing, height) to glTF's right-handed, y-up frame: x east, y up, z south."""
    east, north, height = origin
    return np.column_stack(
        [vertices[:, 0] - east, vertices[:, 2] - height, -(vertices[:, 1] - north)]
    )


def upward(local: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    """Return `triangles` wound counter-clockwise seen from above (+y), as glTF front faces need."""
    a, b, c = (local[triangles[:, i]] for i in range(3))
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


def _point_scale(crs: str, easting: float, northing: float) -> float:
    """Scale factor k of a conformal projection at a point: CRS distance = k * ground distance."""
    lon, lat = Transformer.from_crs(crs, WGS84, always_xy=True).transform(easting, northing)
    return float(Proj(crs).get_factors(lon, lat).meridional_scale)


def _require_matching_box(tin: Tin, texture: Raster) -> None:
    rows, cols = texture.pixels.shape[1:]
    t = texture.transform
    texture_box = (t.c, t.f + rows * t.e, t.c + cols * t.a, t.f)
    box = tin.box
    if texture.crs != box.crs or not np.allclose(
        texture_box, (box.west, box.south, box.east, box.north), rtol=0, atol=BOX_MATCH_TOLERANCE_M
    ):
        msg = f"texture {texture.crs} {texture_box} does not match TIN box {box}"
        raise ValueError(msg)
