"""W8e (c): tiny synthetic GLBs with a real glTF material, for the attach-preview opaque-host test.

``make_glbs.write_glb`` writes meshes without materials, so this writes one through it and then adds a ``materials`` entry
and points the primitive at it (the JSON chunk is rewritten, the binary chunk is untouched). Nothing here is pack data: one
box per file.
"""

from __future__ import annotations

import importlib.util
import json
import struct
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("w8e_make_glbs", _HERE / "make_glbs.py")
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)


def write_box_glb(path: Path, lo, hi, *, rgba=(0.2, 0.5, 0.9, 1.0), alpha_mode: str | None = None, alpha_cutoff: float | None = None) -> Path:
    """One box (metres, ``lo``..``hi``) with a material of base colour ``rgba`` (linear). ``alpha_mode`` ``"BLEND"`` / ``"MASK"`` /
    ``"OPAQUE"`` goes into the material as written; ``None`` leaves glTF's default (OPAQUE)."""
    G.write_glb(path, [{"name": "SM_W8E_Box", "mesh": G.box(lo, hi)}])
    data = path.read_bytes()
    json_len, json_type = struct.unpack_from("<II", data, 12)
    assert json_type == G._JSON
    doc = json.loads(data[20:20 + json_len])
    material: dict = {"name": "W8E_Mat", "pbrMetallicRoughness": {"baseColorFactor": list(rgba), "metallicFactor": 0.0, "roughnessFactor": 0.6}}
    if alpha_mode is not None:
        material["alphaMode"] = alpha_mode
    if alpha_cutoff is not None:
        material["alphaCutoff"] = alpha_cutoff
    doc["materials"] = [material]
    for prim in doc["meshes"][0]["primitives"]:
        prim["material"] = 0
    js = G._pad(json.dumps(doc, separators=(",", ":")).encode("utf-8"), b" ")
    rest = data[20 + json_len:]  # the binary chunk header and payload
    body = struct.pack("<II", len(js), G._JSON) + js + rest
    path.write_bytes(struct.pack("<III", G._GLB_MAGIC, 2, 12 + len(body)) + body)
    return path


def read_material(path: Path) -> dict:
    """The first material of a GLB written by ``write_box_glb`` (so a test can assert the fixture really is translucent)."""
    data = Path(path).read_bytes()
    json_len, _ = struct.unpack_from("<II", data, 12)
    return json.loads(data[20:20 + json_len])["materials"][0]
