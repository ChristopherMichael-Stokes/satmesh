"""Skirts: walls hung from a mesh's boundary so neighbouring tiles leave no visible crack."""

import numpy as np

EDGE_VERTICES = 2


def add_skirts(
    vertices: np.ndarray, uv: np.ndarray, triangles: np.ndarray, depth_m: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the mesh with a wall `depth_m` deep below every boundary edge.

    `vertices` are in the glTF frame (y up) and `triangles` wind counter-clockwise seen from above.
    Each wall vertex copies the UV of the vertex above it, and the walls face away from the mesh.
    """
    edges = triangles[:, [0, 1, 1, 2, 2, 0]].reshape(-1, EDGE_VERTICES)
    seen = {(int(a), int(b)) for a, b in edges}
    boundary = np.array([(a, b) for a, b in seen if (b, a) not in seen], dtype=np.int64)
    if len(boundary) == 0:
        return vertices, uv, triangles
    top = np.unique(boundary)
    lowered = vertices[top] - [0.0, depth_m, 0.0]
    wall_index = {int(vertex): len(vertices) + i for i, vertex in enumerate(top)}
    below_a = np.array([wall_index[int(a)] for a in boundary[:, 0]], dtype=np.uint32)
    below_b = np.array([wall_index[int(b)] for b in boundary[:, 1]], dtype=np.uint32)
    a, b = boundary[:, 0].astype(np.uint32), boundary[:, 1].astype(np.uint32)
    walls = np.concatenate(
        [np.column_stack([a, below_b, b]), np.column_stack([a, below_a, below_b])]
    )
    return (
        np.concatenate([vertices, lowered]),
        np.concatenate([uv, uv[top]]),
        np.concatenate([triangles, walls]),
    )
