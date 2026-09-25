"""Skinned meshes are placed by world(joint) @ inverseBind(joint), not by
their node transform — gltfpack folds the position dequantisation into the
inverse bind matrices, so measuring through the node put every Synty
character in a [-1, 1] box centred on the origin."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

from synty_inventory.sources.glb_geometry import load_triangles
from synty_inventory.sources.glb_measure import measure_glb

GLB_MAGIC = 0x46546C67
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942


def _write_glb(path: Path, doc: dict, blob: bytes) -> None:
    body = json.dumps(doc).encode("utf-8")
    body += b" " * ((-len(body)) % 4)
    blob += b"\0" * ((-len(blob)) % 4)
    total = 12 + 8 + len(body) + 8 + len(blob)
    path.write_bytes(
        struct.pack("<III", GLB_MAGIC, 2, total)
        + struct.pack("<II", len(body), CHUNK_JSON)
        + body
        + struct.pack("<II", len(blob), CHUNK_BIN)
        + blob
    )


def _skinned_glb(path: Path) -> None:
    # Unit cube [-1, 1]^3 (the quantised space), one triangle is enough.
    pos = np.array([[-1, -1, -1], [1, -1, -1], [1, 1, 1]], dtype=np.float32)
    idx = np.array([0, 1, 2], dtype=np.uint16)
    # Joint sits at y=+1; inverse bind = scale 0.5 then +0.5 on y, so the
    # bind-pose matrix maps [-1, 1] -> x,z [-0.5, 0.5], y [1.0, 2.0].
    ibm = np.eye(4, dtype=np.float32)
    ibm[0, 0] = ibm[1, 1] = ibm[2, 2] = 0.5
    ibm[1, 3] = 0.5
    ibm_bytes = ibm.T.reshape(-1).tobytes()  # column-major
    pos_bytes, idx_bytes = pos.tobytes(), idx.tobytes() + b"\0\0"
    blob = pos_bytes + idx_bytes + ibm_bytes
    o1, o2 = len(pos_bytes), len(pos_bytes) + len(idx_bytes)
    doc = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0, 1]}],
        "nodes": [
            {"name": "Root", "translation": [0.0, 1.0, 0.0]},
            # The skinned node's own transform must be ignored.
            {"name": "Character_A", "mesh": 0, "skin": 0, "translation": [100.0, 0.0, 0.0]},
        ],
        "skins": [{"joints": [0], "inverseBindMatrices": 2}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
        "buffers": [{"byteLength": len(blob)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(pos_bytes)},
            {"buffer": 0, "byteOffset": o1, "byteLength": 6},
            {"buffer": 0, "byteOffset": o2, "byteLength": len(ibm_bytes)},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [-1, -1, -1], "max": [1, 1, 1]},
            {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"},
            {"bufferView": 2, "componentType": 5126, "count": 1, "type": "MAT4"},
        ],
    }
    _write_glb(path, doc, blob)


def test_measure_uses_skin_bind_pose(tmp_path: Path):
    path = tmp_path / "Character.glb"
    _skinned_glb(path)
    mn, mx = measure_glb(path, "Character_A")
    assert np.allclose(mn, [-0.5, 1.0, -0.5]) and np.allclose(mx, [0.5, 2.0, 0.5])


def test_triangles_use_skin_bind_pose(tmp_path: Path):
    path = tmp_path / "Character.glb"
    _skinned_glb(path)
    verts, tris = load_triangles(path, "Character_A")
    assert tris.shape == (1, 3)
    assert np.allclose(verts.min(axis=0), [-0.5, 1.0, -0.5]) and np.allclose(verts.max(axis=0), [0.5, 2.0, 0.5])


def test_shared_ibm_view_decoded_once(tmp_path: Path, monkeypatch):
    # gltfpack puts every skin's IBMs in one bufferView; decoding it per skin
    # was O(skins^2) and stalled enrich for hours on a 634-skin bundle.
    from synty_inventory.sources import glb_geometry

    path = tmp_path / "Bundle.glb"
    _skinned_glb(path)
    doc, blob = glb_geometry.read_glb(path)
    doc["skins"] = [{"joints": [0], "inverseBindMatrices": 2} for _ in range(5)]
    calls = []
    real = glb_geometry._buffer_view_bytes
    monkeypatch.setattr(glb_geometry, "_buffer_view_bytes", lambda d, b, i: calls.append(i) or real(d, b, i))
    mats = glb_geometry.skin_bind_matrices(doc, blob)
    assert len(mats) == 5 and calls == [2]
