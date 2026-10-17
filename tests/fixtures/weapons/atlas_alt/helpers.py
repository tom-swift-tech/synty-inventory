"""Synthetic ``atlas_alt`` world for the W5 tests (variants, ``icons --variants``). Loaded by path, like ``wfx``.

``extracted/`` (committed, text and 8x8 solid-colour PNGs) is a stand-in for an extracted Unity tree, one folder per
pack, each holding ``Assets/Synty/<Pack>/...``:

* ``FAKE_AtlasAlt`` ships Alts atlas 01 with three sibling materials A (red texture), B (green), C (blue); C's
  texture file is named differently from its material, so only the material's texture guid finds it. Atlas 02 has
  A and B where B's texture is a ``.tga``; atlas 03 has a lone ``A``. ``FakeAtlas_01_Extra.mat`` and a ``.mat.meta``
  sit beside the siblings as decoys that must not count as colourways.
* ``FAKE_NoAlts`` has one dedicated weapon material and no Alts folder.

``make_catalogs`` writes matching pack catalogs; ``write_textured_glb`` writes a GLB whose material carries a
base-colour texture, so the icon harness has a ``map`` to replace. Nothing here is pack data.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
EXTRACTED = HERE / "extracted"
ATLAS_PACK, NOALTS_PACK = "FAKE_AtlasAlt", "FAKE_NoAlts"
_ALTS = "Assets/Synty/FakeAtlas/Materials/Alts"
_NOALTS = "Assets/Synty/FakeNoAlts/Materials"

# asset id -> (pack, files.unity_materials). The default colourway is the letter the catalog points at.
ASSETS = {
    "SM_Wep_Sword_Atlas_01": (ATLAS_PACK, [f"{_ALTS}/FakeAtlas_01_A.mat"]),   # default A of A, B, C
    "SM_Wep_Axe_Atlas_01": (ATLAS_PACK, [f"{_ALTS}/FakeAtlas_01_B.mat"]),     # default B of A, B, C
    "SM_Wep_Mace_Atlas_01": (ATLAS_PACK, [f"{_ALTS}/FakeAtlas_02_A.mat"]),    # B has a .tga texture
    "SM_Wep_Spear_Atlas_01": (ATLAS_PACK, [f"{_ALTS}/FakeAtlas_03_A.mat"]),   # lone letter: no choice
    "SM_Wep_Knife_Atlas_01": (ATLAS_PACK, ["Assets/Synty/FakeAtlas/Materials/Misc/Metal_01.mat",
                                           f"{_ALTS}/FakeAtlas_01_C.mat"]),    # the Alts material is not first
    "SM_Wep_Club_NoMaterial_01": (ATLAS_PACK, []),                             # colourway_unknown
    "SM_Wep_Pistol_NoAlts_01": (NOALTS_PACK, [f"{_NOALTS}/FakeNoAlts_Wep_01.mat"]),
}
PACK_SETTINGS = {ATLAS_PACK: {"setting": "fantasy", "era": "medieval"}, NOALTS_PACK: {"setting": "modern", "era": "modern"}}
PACK_DIRS = {ATLAS_PACK: "FakeAtlas", NOALTS_PACK: "FakeNoAlts"}
# colour of each sibling's texture in the committed PNGs
COLOURS = {"A": (200, 40, 40), "B": (40, 200, 40), "C": (40, 40, 200)}


def make_catalogs(tmp_path: Path, name: str = "catalogs") -> Path:
    """Pack catalogs for the two fixture packs, with ``files.unity_materials`` as above."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("make_catalogs", HERE.parent / "make_catalogs.py")
    mk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mk)
    skeleton = json.loads((HERE.parent / "review_FAKE_Review.json").read_text(encoding="utf-8"))
    skeleton.pop("assets")
    cat = tmp_path / name
    cat.mkdir(parents=True, exist_ok=True)
    for pack in (ATLAS_PACK, NOALTS_PACK):
        assets = []
        for aid, (apack, materials) in ASSETS.items():
            if apack != pack:
                continue
            asset = mk._asset(pack, aid)
            asset["files"]["unity_materials"] = list(materials)
            assets.append(asset)
        doc = {**skeleton, "pack_id": pack, "assets": assets, "asset_count": len(assets)}
        (cat / f"{pack}.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return cat


def write_textured_glb(path: Path, rgb=(200, 40, 40), long_axis: int = 2, length: float = 0.9) -> Path:
    """A thin box with UVs over its whole surface and a solid ``rgb`` base-colour texture embedded in the file:
    the texture a variant has to replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(textured_glb_bytes(rgb, long_axis, length))
    return path


def _png(rgb, n: int = 8) -> bytes:
    import zlib

    raw = b"".join(b"\x00" + bytes(rgb) * n for _ in range(n))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def textured_glb_bytes(rgb=(200, 40, 40), long_axis: int = 2, length: float = 0.9) -> bytes:
    half = [0.03, 0.03, 0.03]
    half[long_axis] = length / 2
    faces = [  # (normal, 4 corner signs in uv order)
        ((1, 0, 0), [(1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1)]),
        ((-1, 0, 0), [(-1, -1, 1), (-1, 1, 1), (-1, 1, -1), (-1, -1, -1)]),
        ((0, 1, 0), [(-1, 1, -1), (-1, 1, 1), (1, 1, 1), (1, 1, -1)]),
        ((0, -1, 0), [(-1, -1, 1), (-1, -1, -1), (1, -1, -1), (1, -1, 1)]),
        ((0, 0, 1), [(-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]),
        ((0, 0, -1), [(1, -1, -1), (-1, -1, -1), (-1, 1, -1), (1, 1, -1)]),
    ]
    pos, nrm, uv, idx = [], [], [], []
    for n, quad in faces:
        base = len(pos)
        for k, signs in enumerate(quad):
            pos.append([s * h for s, h in zip(signs, half)])
            nrm.append(list(n))
            uv.append([(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)][k])
        idx += [base, base + 1, base + 2, base, base + 2, base + 3]
    pos_b = np.asarray(pos, dtype="<f4").tobytes()
    nrm_b = np.asarray(nrm, dtype="<f4").tobytes()
    uv_b = np.asarray(uv, dtype="<f4").tobytes()
    idx_b = np.asarray(idx, dtype="<u2").tobytes()
    img = _png(rgb)
    blob = bytearray()
    views = []
    for data in (pos_b, nrm_b, uv_b, idx_b, img):
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)})
        blob.extend(data)
    pa = np.asarray(pos, dtype=np.float32)
    doc = {
        "asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"name": "Atlas_Fixture", "mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2}, "indices": 3,
                                    "material": 0, "mode": 4}]}],
        "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicFactor": 0.0,
                                                "roughnessFactor": 1.0}}],
        "textures": [{"source": 0, "sampler": 0}], "images": [{"bufferView": 4, "mimeType": "image/png"}],
        "samplers": [{"magFilter": 9728, "minFilter": 9728, "wrapS": 33071, "wrapT": 33071}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(pos), "type": "VEC3",
             "min": pa.min(axis=0).tolist(), "max": pa.max(axis=0).tolist()},
            {"bufferView": 1, "componentType": 5126, "count": len(pos), "type": "VEC3"},
            {"bufferView": 2, "componentType": 5126, "count": len(pos), "type": "VEC2"},
            {"bufferView": 3, "componentType": 5123, "count": len(idx), "type": "SCALAR"},
        ],
        "bufferViews": views, "buffers": [{"byteLength": len(blob)}],
    }

    def pad(b: bytes, fill: bytes) -> bytes:
        return b + fill * (-len(b) % 4)

    js = pad(json.dumps(doc, separators=(",", ":")).encode("utf-8"), b" ")
    bn = pad(bytes(blob), b"\0")
    body = struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(bn), 0x004E4942) + bn
    return struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body
