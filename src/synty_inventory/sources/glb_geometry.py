"""Exact triangle geometry out of a threejs-v2 GLB (world space, Y-up).

Complements ``glb_measure`` (AABB-only, from accessor min/max): this decodes
the POSITION stream and the index buffer — through ``meshopt`` when the
bufferView is ``EXT_meshopt_compression``-encoded, raw otherwise — and
returns every triangle transformed by its node's world matrix. Used for
mating-face / socket analysis of ship-kit parts; anything unsupported
(filtered position streams, Draco, missing indices) returns ``None`` so the
caller degrades to bounds-only behaviour.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

from .glb_measure import GLB_MAGIC, CHUNK_JSON, _dequantize, _node_matrix
from .meshopt import MeshoptError, decode_index_buffer, decode_vertex_buffer

CHUNK_BIN = 0x004E4942  # b'BIN\0'

_COMPONENT_DTYPE = {
    5120: np.int8,
    5121: np.uint8,
    5122: np.int16,
    5123: np.uint16,
    5125: np.uint32,
    5126: np.float32,
}
_TYPE_WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def read_glb(path: Path) -> tuple[dict, bytes] | None:
    """(json doc, BIN chunk bytes) or None when not a GLB."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if len(raw) < 20:
        return None
    magic, _version, length = struct.unpack_from("<III", raw, 0)
    if magic != GLB_MAGIC:
        return None
    off = 12
    doc = None
    blob = b""
    while off + 8 <= min(length, len(raw)):
        clen, ctype = struct.unpack_from("<II", raw, off)
        body = raw[off + 8:off + 8 + clen]
        if ctype == CHUNK_JSON:
            try:
                doc = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return None
        elif ctype == CHUNK_BIN and not blob:
            blob = body
        off += 8 + clen
    if doc is None:
        return None
    return doc, blob


def _buffer_view_bytes(doc: dict, blob: bytes, bv_idx: int) -> tuple[bytes, int] | None:
    """Raw bytes of a bufferView plus its effective byteStride (0 = tight).
    Decodes EXT_meshopt_compression in place; only buffer 0 (the BIN chunk)
    is supported as a source."""
    views = doc.get("bufferViews") or []
    if not (0 <= bv_idx < len(views)):
        return None
    bv = views[bv_idx]
    ext = (bv.get("extensions") or {}).get("EXT_meshopt_compression")
    if ext:
        if ext.get("buffer", 0) != 0:
            return None
        start = ext.get("byteOffset", 0)
        data = blob[start:start + ext["byteLength"]]
        mode = ext.get("mode", "ATTRIBUTES")
        stride = ext["byteStride"]
        count = ext["count"]
        try:
            if mode == "ATTRIBUTES":
                if ext.get("filter", "NONE") != "NONE":
                    return None
                return decode_vertex_buffer(data, count, stride), stride
            if mode == "TRIANGLES":
                idx = decode_index_buffer(data, count)
                fmt = {1: "B", 2: "H", 4: "I"}.get(stride)
                if fmt is None:
                    return None
                return struct.pack(f"<{count}{fmt}", *idx), stride
        except (MeshoptError, IndexError, struct.error):
            return None
        return None
    if bv.get("buffer", 0) != 0:
        return None
    start = bv.get("byteOffset", 0)
    return blob[start:start + bv["byteLength"]], bv.get("byteStride", 0)


def _read_accessor(doc: dict, blob: bytes, acc_idx: int) -> np.ndarray | None:
    accessors = doc.get("accessors") or []
    if not (0 <= acc_idx < len(accessors)):
        return None
    acc = accessors[acc_idx]
    if "bufferView" not in acc or acc.get("sparse"):
        return None
    dtype = _COMPONENT_DTYPE.get(acc.get("componentType"))
    width = _TYPE_WIDTH.get(acc.get("type"))
    if dtype is None or width is None:
        return None
    got = _buffer_view_bytes(doc, blob, acc["bufferView"])
    if got is None:
        return None
    data, stride = got
    count = int(acc.get("count", 0))
    elem = np.dtype(dtype).itemsize * width
    start = int(acc.get("byteOffset", 0))
    if not stride or stride == elem:
        need = start + count * elem
        if need > len(data):
            return None
        arr = np.frombuffer(data, dtype=dtype, count=count * width, offset=start)
        return arr.reshape(count, width).astype(np.float64)
    if start + (count - 1) * stride + elem > len(data):
        return None
    rows = np.ndarray((count, width), dtype=dtype, buffer=data, offset=start, strides=(stride, np.dtype(dtype).itemsize))
    return np.array(rows, dtype=np.float64)


def load_triangles(path: Path, node_name: str | None = None) -> tuple[np.ndarray, np.ndarray] | None:
    """(vertices [N,3] float64 world-space, triangles [M,3] int) for every
    triangle-list primitive under ``node_name`` (or the whole scene)."""
    got = read_glb(path)
    if got is None:
        return None
    doc, blob = got
    meshes = doc.get("meshes") or []
    nodes = doc.get("nodes") or []
    accessors = doc.get("accessors") or []
    scenes = doc.get("scenes") or []
    scene_idx = doc.get("scene", 0)
    if not (0 <= scene_idx < len(scenes)):
        return None

    verts: list[np.ndarray] = []
    tris: list[np.ndarray] = []
    base = 0

    def walk(idx: int, parent: np.ndarray, active: bool) -> None:
        nonlocal base
        if not (0 <= idx < len(nodes)):
            return
        node = nodes[idx]
        world = parent @ _node_matrix(node)
        active = active or node_name is None or node.get("name") == node_name
        mesh_idx = node.get("mesh")
        if active and mesh_idx is not None and 0 <= mesh_idx < len(meshes):
            for prim in meshes[mesh_idx].get("primitives") or []:
                if prim.get("mode", 4) != 4 or "indices" not in prim:
                    continue
                pos_idx = (prim.get("attributes") or {}).get("POSITION")
                if pos_idx is None or not (0 <= pos_idx < len(accessors)):
                    continue
                pos = _read_accessor(doc, blob, pos_idx)
                ind = _read_accessor(doc, blob, prim["indices"])
                if pos is None or ind is None or len(ind) < 3:
                    continue
                acc = accessors[pos_idx]
                if acc.get("normalized"):
                    pos = np.array(
                        [_dequantize(list(row), acc.get("componentType")) for row in pos.tolist()], dtype=np.float64
                    )
                hom = np.hstack([pos, np.ones((len(pos), 1))]) @ world.T
                verts.append(hom[:, :3])
                t = ind.reshape(-1).astype(np.int64)
                t = t[: len(t) - len(t) % 3].reshape(-1, 3)
                t = t[(t < len(pos)).all(axis=1)]
                tris.append(t + base)
                base += len(pos)
        for child in node.get("children") or []:
            walk(child, world, active)

    for r in scenes[scene_idx].get("nodes") or []:
        walk(r, np.eye(4, dtype=np.float64), False)
    if not verts or not tris:
        return None
    v = np.vstack(verts)
    t = np.vstack(tris)
    if not len(t):
        return None
    return v, t
