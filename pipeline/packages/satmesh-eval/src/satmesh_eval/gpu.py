"""GPU rasterisation of an `AreaScene` through wgpu (Vulkan, Metal, Direct3D 12 or OpenGL).

The same pinhole render as `satmesh_eval.perspective.render`, rasterised instead of ray traced:
leaves in the view frustum are drawn nearest first with trilinear, anisotropic texture sampling
and the per-pixel range is read back. Leaf geometry and textures become resident on the device on
first use and are evicted least recently used first once a byte budget is exceeded.

Range travels in a second RGBA8 target as a 24-bit fixed-point fraction of the maximum range, with
alpha marking a hit. Float render targets are not available on every backend (wgpu's OpenGL
backend refuses them); fixed point works everywhere at 0.03 mm resolution for a 500 m range.
"""

import math
from collections import OrderedDict
from dataclasses import dataclass

import cv2
import numpy as np
import wgpu

from satmesh_eval.camera import CameraPose, Intrinsics, camera_centre_and_rotation
from satmesh_eval.perspective import AreaScene, RenderResult, SceneLeaf
from satmesh_eval.projection import (
    boxes_in_frustum,
    boxes_within_range,
    frustum_planes,
    projection_matrix,
    view_matrix,
)

NEAR_PLANE_M = 0.5
ANISOTROPY = 16
RANGE_FIXED_POINT_MAX = 2**24 - 1
BYTES_PER_PIXEL = 4
ROW_ALIGNMENT_BYTES = 256  # WebGPU: bytes_per_row of a texture-to-buffer copy
DEFAULT_RESIDENT_BUDGET_BYTES = 2 * 1024**3
VERTEX_STRIDE_BYTES = 20  # float32 x, y, z, u, v
UNIFORM_FLOATS = 36  # mat4 clip_from_world, mat4 camera_from_world, max_range, 3 pad
FLOAT32_BYTES = 4
MIP_DOWNSCALE = 2
OPAQUE = 255

SHADER = """
struct Frame {
  clip_from_world: mat4x4<f32>,
  camera_from_world: mat4x4<f32>,
  max_range_m: vec4<f32>,
};
@group(0) @binding(0) var<uniform> frame: Frame;
@group(1) @binding(0) var leaf_texture: texture_2d<f32>;
@group(1) @binding(1) var leaf_sampler: sampler;

struct Vertex {
  @builtin(position) clip: vec4<f32>,
  @location(0) camera_position: vec3<f32>,
  @location(1) uv: vec2<f32>,
};

@vertex
fn vertex_main(@location(0) position: vec3<f32>, @location(1) uv: vec2<f32>) -> Vertex {
  var out: Vertex;
  out.clip = frame.clip_from_world * vec4<f32>(position, 1.0);
  out.camera_position = (frame.camera_from_world * vec4<f32>(position, 1.0)).xyz;
  out.uv = uv;
  return out;
}

struct Pixel {
  @location(0) colour: vec4<f32>,
  @location(1) range_packed: vec4<f32>,
};

@fragment
fn fragment_main(in: Vertex) -> Pixel {
  let range_m = length(in.camera_position);
  if (range_m > frame.max_range_m.x) {
    discard;
  }
  let packed = u32(clamp(range_m / frame.max_range_m.x, 0.0, 1.0) * 16777215.0 + 0.5);
  var out: Pixel;
  out.colour = vec4<f32>(textureSample(leaf_texture, leaf_sampler, in.uv).rgb, 1.0);
  out.range_packed = vec4<f32>(
    f32((packed >> 16u) & 255u), f32((packed >> 8u) & 255u), f32(packed & 255u), 255.0) / 255.0;
  return out;
}
"""


@dataclass(frozen=True)
class _ResidentLeaf:
    vertex_buffer: wgpu.GPUBuffer
    index_buffer: wgpu.GPUBuffer
    index_count: int
    texture: wgpu.GPUTexture
    texture_bind_group: wgpu.GPUBindGroup
    size_bytes: int

    def release(self) -> None:
        self.vertex_buffer.destroy()
        self.index_buffer.destroy()
        self.texture.destroy()


@dataclass(frozen=True)
class _Targets:
    """Render targets, readback buffer and per-pixel constants for one set of intrinsics."""

    intrinsics: Intrinsics
    colour: wgpu.GPUTexture
    packed_range: wgpu.GPUTexture
    depth: wgpu.GPUTexture
    readback: wgpu.GPUBuffer
    row_stride_bytes: int
    optical_axis_cosine: np.ndarray


class GpuRenderer:
    """Renders one `AreaScene` on the GPU; owns the device, pipeline and resident leaves.

    Distortion-free pinhole intrinsics only: undistort photos before comparing them with renders.
    """

    def __init__(
        self, scene: AreaScene, resident_budget_bytes: int = DEFAULT_RESIDENT_BUDGET_BYTES
    ) -> None:
        """Open the best adapter and compile the pipeline; leaves upload on first use."""
        self._scene = scene
        self._budget_bytes = resident_budget_bytes
        self._lower = np.array([leaf.mesh.bounds[0] for leaf in scene.leaves])
        self._upper = np.array([leaf.mesh.bounds[1] for leaf in scene.leaves])
        adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
        self.adapter_description: str = (
            f"{adapter.info['backend_type']}: {adapter.info['description']}"
        )
        self._texture_limit = adapter.limits["max-texture-dimension-2d"]
        self._device: wgpu.GPUDevice = adapter.request_device_sync(
            required_limits={"max-texture-dimension-2d": self._texture_limit}
        )
        self._uniforms = self._device.create_buffer(
            size=UNIFORM_FLOATS * FLOAT32_BYTES,
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
        )
        self._sampler = self._device.create_sampler(
            mag_filter="linear",
            min_filter="linear",
            mipmap_filter="linear",
            max_anisotropy=ANISOTROPY,
            address_mode_u="clamp-to-edge",
            address_mode_v="clamp-to-edge",
        )
        self._frame_layout, self._texture_layout, self._pipeline = self._create_pipeline()
        self._frame_group = self._device.create_bind_group(
            layout=self._frame_layout,
            entries=[
                {
                    "binding": 0,
                    "resource": {
                        "buffer": self._uniforms,
                        "offset": 0,
                        "size": UNIFORM_FLOATS * FLOAT32_BYTES,
                    },
                }
            ],
        )
        self._resident: OrderedDict[int, _ResidentLeaf] = OrderedDict()
        self._targets: _Targets | None = None

    def render(self, intrinsics: Intrinsics, pose: CameraPose, max_range_m: float) -> RenderResult:
        """Render from `pose`; hits farther than `max_range_m` along the ray count as misses."""
        if intrinsics.radial_distortion:
            msg = "the GPU renderer is pinhole only; undistort the photo instead"
            raise ValueError(msg)
        centre, camera_to_enu = camera_centre_and_rotation(pose, self._scene.frame)
        view = view_matrix(centre, camera_to_enu)
        projection = projection_matrix(intrinsics, NEAR_PLANE_M, max_range_m)
        visible = self._visible_leaves(projection @ view, centre, max_range_m)
        self._make_resident(visible)
        targets = self._targets_for(intrinsics)
        self._write_uniforms(projection @ view, view, max_range_m)
        self._draw(targets, visible)
        return _decode(targets, self._read_back(targets), max_range_m)

    def _visible_leaves(
        self, clip_from_world: np.ndarray, centre: np.ndarray, max_range_m: float
    ) -> list[int]:
        """Leaf indices in the frustum and range, nearest first for early depth rejection."""
        inside = boxes_in_frustum(
            frustum_planes(clip_from_world), self._lower, self._upper
        ) & boxes_within_range(centre, max_range_m, self._lower, self._upper)
        indices = np.flatnonzero(inside)
        midpoints = (self._lower[indices] + self._upper[indices]) / 2.0
        return [int(i) for i in indices[np.argsort(np.linalg.norm(midpoints - centre, axis=1))]]

    def _make_resident(self, visible: list[int]) -> None:
        for index in visible:
            if index in self._resident:
                self._resident.move_to_end(index)
            else:
                self._resident[index] = self._upload(self._scene.leaves[index])
        in_use = set(visible)
        for index in list(self._resident):
            if sum(leaf.size_bytes for leaf in self._resident.values()) <= self._budget_bytes:
                return
            if index not in in_use:
                self._resident.pop(index).release()

    def _upload(self, leaf: SceneLeaf) -> _ResidentLeaf:
        vertices = np.column_stack([leaf.mesh.vertices, leaf.uv]).astype(np.float32)
        indices = np.asarray(leaf.mesh.faces, dtype=np.uint32)
        vertex_buffer = self._device.create_buffer_with_data(
            data=vertices, usage=wgpu.BufferUsage.VERTEX
        )
        index_buffer = self._device.create_buffer_with_data(
            data=indices, usage=wgpu.BufferUsage.INDEX
        )
        texture, texture_bytes = self._upload_texture(leaf.texture)
        group = self._device.create_bind_group(
            layout=self._texture_layout,
            entries=[
                {"binding": 0, "resource": texture.create_view()},
                {"binding": 1, "resource": self._sampler},
            ],
        )
        return _ResidentLeaf(
            vertex_buffer,
            index_buffer,
            indices.size,
            texture,
            group,
            vertices.nbytes + indices.nbytes + texture_bytes,
        )

    def _upload_texture(self, rgb: np.ndarray) -> tuple[wgpu.GPUTexture, int]:
        height, width = rgb.shape[:2]
        if max(height, width) > self._texture_limit:
            msg = f"texture {width}x{height} exceeds the device limit {self._texture_limit}"
            raise ValueError(msg)
        levels = [np.dstack([rgb, np.full((height, width), OPAQUE, np.uint8)])]
        while max(levels[-1].shape[:2]) > 1:
            h, w = levels[-1].shape[:2]
            levels.append(
                cv2.resize(
                    levels[-1],
                    (max(1, w // MIP_DOWNSCALE), max(1, h // MIP_DOWNSCALE)),
                    interpolation=cv2.INTER_AREA,
                )
            )
        texture = self._device.create_texture(
            size=(width, height, 1),
            format="rgba8unorm",
            usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
            mip_level_count=len(levels),
        )
        for mip, level in enumerate(levels):
            contiguous = np.ascontiguousarray(level)
            self._device.queue.write_texture(
                {"texture": texture, "mip_level": mip},
                contiguous,
                {
                    "bytes_per_row": level.shape[1] * BYTES_PER_PIXEL,
                    "rows_per_image": level.shape[0],
                },
                (level.shape[1], level.shape[0], 1),
            )
        return texture, sum(level.nbytes for level in levels)

    def _targets_for(self, intrinsics: Intrinsics) -> _Targets:
        targets = self._targets
        if targets and targets.intrinsics == intrinsics:
            return targets
        if targets:
            for resource in (targets.colour, targets.packed_range, targets.depth, targets.readback):
                resource.destroy()
        width, height = intrinsics.width_px, intrinsics.height_px
        stride = math.ceil(width * BYTES_PER_PIXEL / ROW_ALIGNMENT_BYTES) * ROW_ALIGNMENT_BYTES
        colour_usage = wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.COPY_SRC
        self._targets = _Targets(
            intrinsics,
            self._device.create_texture(
                size=(width, height, 1), format="rgba8unorm", usage=colour_usage
            ),
            self._device.create_texture(
                size=(width, height, 1), format="rgba8unorm", usage=colour_usage
            ),
            self._device.create_texture(
                size=(width, height, 1),
                format="depth32float",
                usage=wgpu.TextureUsage.RENDER_ATTACHMENT,
            ),
            self._device.create_buffer(
                size=2 * stride * height,
                usage=wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.MAP_READ,
            ),
            stride,
            _optical_axis_cosine(intrinsics),
        )
        return self._targets

    def _write_uniforms(
        self, clip_from_world: np.ndarray, camera_from_world: np.ndarray, max_range_m: float
    ) -> None:
        # WGSL matrices are column-major
        data = np.concatenate(
            [clip_from_world.T.ravel(), camera_from_world.T.ravel(), [max_range_m, 0, 0, 0]]
        ).astype(np.float32)
        self._device.queue.write_buffer(self._uniforms, 0, data)

    def _draw(self, targets: _Targets, visible: list[int]) -> None:
        encoder = self._device.create_command_encoder()
        clear = {"load_op": "clear", "store_op": "store", "clear_value": (0, 0, 0, 0)}
        render_pass = encoder.begin_render_pass(
            color_attachments=[
                {"view": targets.colour.create_view(), **clear},
                {"view": targets.packed_range.create_view(), **clear},
            ],
            depth_stencil_attachment={
                "view": targets.depth.create_view(),
                "depth_clear_value": 1.0,
                "depth_load_op": "clear",
                "depth_store_op": "discard",
            },
        )
        render_pass.set_pipeline(self._pipeline)
        render_pass.set_bind_group(0, self._frame_group)
        for index in visible:
            leaf = self._resident[index]
            render_pass.set_bind_group(1, leaf.texture_bind_group)
            render_pass.set_vertex_buffer(0, leaf.vertex_buffer)
            render_pass.set_index_buffer(leaf.index_buffer, "uint32")
            render_pass.draw_indexed(leaf.index_count)
        render_pass.end()
        size = (targets.intrinsics.width_px, targets.intrinsics.height_px, 1)
        height = targets.intrinsics.height_px
        plane_bytes = targets.row_stride_bytes * height
        for plane, texture in enumerate((targets.colour, targets.packed_range)):
            encoder.copy_texture_to_buffer(
                {"texture": texture},
                {
                    "buffer": targets.readback,
                    "offset": plane * plane_bytes,
                    "bytes_per_row": targets.row_stride_bytes,
                    "rows_per_image": height,
                },
                size,
            )
        self._device.queue.submit([encoder.finish()])

    def _read_back(self, targets: _Targets) -> np.ndarray:
        """The two target planes as bytes, shape (2, height, row_stride_bytes)."""
        targets.readback.map_sync("read")
        planes = np.frombuffer(targets.readback.read_mapped(copy=False), np.uint8).copy()
        targets.readback.unmap()
        return planes.reshape(2, targets.intrinsics.height_px, targets.row_stride_bytes)

    def _create_pipeline(
        self,
    ) -> tuple[wgpu.GPUBindGroupLayout, wgpu.GPUBindGroupLayout, wgpu.GPURenderPipeline]:
        frame_layout = self._device.create_bind_group_layout(
            entries=[
                {
                    "binding": 0,
                    "visibility": wgpu.ShaderStage.VERTEX | wgpu.ShaderStage.FRAGMENT,
                    "buffer": {"type": "uniform"},
                }
            ]
        )
        texture_layout = self._device.create_bind_group_layout(
            entries=[
                {
                    "binding": 0,
                    "visibility": wgpu.ShaderStage.FRAGMENT,
                    "texture": {"sample_type": "float", "view_dimension": "2d"},
                },
                {
                    "binding": 1,
                    "visibility": wgpu.ShaderStage.FRAGMENT,
                    "sampler": {"type": "filtering"},
                },
            ]
        )
        shader = self._device.create_shader_module(code=SHADER)
        pipeline = self._device.create_render_pipeline(
            layout=self._device.create_pipeline_layout(
                bind_group_layouts=[frame_layout, texture_layout]
            ),
            vertex={
                "module": shader,
                "entry_point": "vertex_main",
                "buffers": [
                    {
                        "array_stride": VERTEX_STRIDE_BYTES,
                        "attributes": [
                            {"format": "float32x3", "offset": 0, "shader_location": 0},
                            {"format": "float32x2", "offset": 12, "shader_location": 1},
                        ],
                    }
                ],
            },
            primitive={"topology": "triangle-list", "cull_mode": "none"},
            depth_stencil={
                "format": "depth32float",
                "depth_write_enabled": True,
                "depth_compare": "less",
            },
            fragment={
                "module": shader,
                "entry_point": "fragment_main",
                "targets": [{"format": "rgba8unorm"}, {"format": "rgba8unorm"}],
            },
        )
        return frame_layout, texture_layout, pipeline


def _decode(targets: _Targets, planes: np.ndarray, max_range_m: float) -> RenderResult:
    width, height = targets.intrinsics.width_px, targets.intrinsics.height_px
    colour = planes[0, :, : width * BYTES_PER_PIXEL].reshape(height, width, BYTES_PER_PIXEL)
    # little-endian RGBA bytes read as one word: alpha << 24 | blue << 16 | green << 8 | red
    word = np.ascontiguousarray(planes[1, :, : width * BYTES_PER_PIXEL]).view(np.uint32)
    hit = (word >> 24) > 0
    fixed = ((word & 0xFF) << 16) | (word & 0xFF00) | ((word >> 16) & 0xFF)
    ranges = np.full((height, width), np.nan, np.float32)
    np.multiply(
        fixed.astype(np.float32),
        np.float32(max_range_m / RANGE_FIXED_POINT_MAX),
        out=ranges,
        where=hit,
    )
    z_depths = np.full((height, width), np.nan, np.float32)
    np.multiply(ranges, targets.optical_axis_cosine, out=z_depths, where=hit)
    return RenderResult(
        rgb=cv2.cvtColor(colour, cv2.COLOR_RGBA2RGB),
        depth_m=ranges,
        z_depth_m=z_depths,
        hit_mask=hit,
    )


def _optical_axis_cosine(intrinsics: Intrinsics) -> np.ndarray:
    """Per pixel, the cosine between the ray and the optical axis: z-depth = range x cosine."""
    x = (np.arange(intrinsics.width_px) + 0.5 - intrinsics.principal_x_px) / intrinsics.focal_x_px
    y = (np.arange(intrinsics.height_px) + 0.5 - intrinsics.principal_y_px) / intrinsics.focal_y_px
    return (1.0 / np.sqrt(1.0 + x[None, :] ** 2 + y[:, None] ** 2)).astype(np.float32)
