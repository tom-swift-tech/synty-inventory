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
