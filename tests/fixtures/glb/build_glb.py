"""Tiny in-memory GLB (binary glTF) builder for offline measurement tests.

Only builds what ``sources.glb_measure`` actually reads: the 12-byte header
and a JSON chunk with ``scenes``/``nodes``/``meshes``/``accessors``. No BIN
chunk, buffers, or bufferViews are needed since the measurer never decodes
vertex data — it only reads accessor ``min``/``max``.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

GLB_MAGIC = 0x46546C67
CHUNK_JSON = 0x4E4F534A


def write_glb(path: Path, doc: dict) -> None:
    body = json.dumps(doc).encode("utf-8")
    pad = (-len(body)) % 4
    body += b" " * pad
    header = struct.pack("<III", GLB_MAGIC, 2, 12 + 8 + len(body))
    chunk_header = struct.pack("<II", len(body), CHUNK_JSON)
    path.write_bytes(header + chunk_header + body)


def quantized_position_accessor(min_i16: list[int], max_i16: list[int]) -> dict:
    return {
        "type": "VEC3",
        "componentType": 5122,  # SHORT
        "count": 2,
        "normalized": True,
        "min": min_i16,
        "max": max_i16,
    }


def plain_position_accessor(min_f: list[float], max_f: list[float]) -> dict:
    return {
        "type": "VEC3",
        "componentType": 5126,  # FLOAT
        "count": 2,
        "min": min_f,
        "max": max_f,
    }


def make_single_node_doc(node: dict, accessor: dict) -> dict:
    return {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [dict(node, mesh=0)],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "accessors": [accessor],
    }


def make_parent_child_doc(parent_node: dict, child_node: dict, accessor: dict) -> dict:
    """node 0 = parent (no mesh, child [1]); node 1 = child with mesh."""
    return {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [
            dict(parent_node, children=[1]),
            dict(child_node, mesh=0),
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "accessors": [accessor],
    }


# --- real geometry (for sources.glb_geometry / sources.sockets tests) -------

CHUNK_BIN = 0x004E4942


def write_mesh_glb(path: Path, vertices: list[list[float]], triangles: list[list[int]], node: dict | None = None) -> None:
    """Uncompressed GLB with one float32 POSITION accessor + uint16 indices
    in a BIN chunk; ``node`` may carry translation/rotation/scale."""
    import itertools

    pos = struct.pack(f"<{len(vertices) * 3}f", *itertools.chain.from_iterable(vertices))
    flat = list(itertools.chain.from_iterable(triangles))
    idx = struct.pack(f"<{len(flat)}H", *flat)
    idx += b"\0" * ((-len(idx)) % 4)
    blob = pos + idx
    mins = [min(v[i] for v in vertices) for i in range(3)]
    maxs = [max(v[i] for v in vertices) for i in range(3)]
    doc = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [dict(node or {}, mesh=0, name="Mesh")],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "mode": 4}]}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(vertices), "type": "VEC3", "min": mins, "max": maxs},
            {"bufferView": 1, "componentType": 5123, "count": len(flat), "type": "SCALAR"},
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(pos)},
            {"buffer": 0, "byteOffset": len(pos), "byteLength": len(flat) * 2},
        ],
        "buffers": [{"byteLength": len(blob)}],
    }
    body = json.dumps(doc).encode("utf-8")
    body += b" " * ((-len(body)) % 4)
    total = 12 + 8 + len(body) + 8 + len(blob)
    path.write_bytes(
        struct.pack("<III", GLB_MAGIC, 2, total)
        + struct.pack("<II", len(body), CHUNK_JSON)
        + body
        + struct.pack("<II", len(blob), CHUNK_BIN)
        + blob
    )


def box_mesh(mn: list[float], mx: list[float]) -> tuple[list[list[float]], list[list[int]]]:
    """Closed axis-aligned box, outward-facing CCW triangles (right-handed)."""
    x0, y0, z0 = mn
    x1, y1, z1 = mx
    v = [
        [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],  # z0 face (0-3)
        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],  # z1 face (4-7)
    ]
    quads = [
        (0, 3, 2, 1),  # -z
        (4, 5, 6, 7),  # +z
        (0, 1, 5, 4),  # -y
        (3, 7, 6, 2),  # +y
        (0, 4, 7, 3),  # -x
        (1, 2, 6, 5),  # +x
    ]
    tris = []
    for a, b, c, d in quads:
        tris.append([a, b, c])
        tris.append([a, c, d])
    return v, tris
