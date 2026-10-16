"""Shared helpers for the W4 tests (review page, corrections, export). Loaded by path, like ``wfx``.

Everything is synthetic: the five committed fixture packs plus ``review_FAKE_Review.json`` (a 14-member shield set,
a 12-member knife set, an id with HTML metacharacters, a token candidate), PNGs drawn here, and GLBs from
``make_glbs.py``. Nothing is written outside the pytest tmp dir.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import struct
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wfx = _load("wfx")
M = _load("make_glbs")

REVIEW_PACK = "FAKE_Review"
SHIELD_SET = [f"{REVIEW_PACK}/SM_Wep_Shield_Set_{i:02d}" for i in range(1, 15)]
KNIFE_SET = [f"{REVIEW_PACK}/SM_Wep_Knife_Set_{i:02d}" for i in range(1, 13)]
SWORD_REVIEW = f"{REVIEW_PACK}/SM_Wep_Sword_Review_01"
ODD_ID = f'{REVIEW_PACK}/SM_Wep_Mace_<b>&"q"_01'
SWORD_02 = "FAKE_Fantasy/SM_Wep_Sword_02"
SWORD_01 = "FAKE_Fantasy/SM_Wep_Sword_01"


SHARED_PACK = "FAKE_Shared"
SHARED_BOW = f"{SHARED_PACK}/SM_Wep_Bow_Shared_01"
SHARED_GLB = f"glb/{SHARED_PACK}/shared.glb"


def pack_settings() -> dict:
    fantasy = {"setting": "fantasy", "era": "medieval"}
    return {**wfx.pack_settings(), REVIEW_PACK: fantasy, SHARED_PACK: fantasy}


def make_catalogs(tmp_path: Path, name: str = "catalogs", *, shared: bool = False) -> Path:
    """The W1 fixture catalogs plus the review pack; ``shared`` adds a pack whose one bow lives in ``Bow_B`` of
    the three-node ``shared.glb`` (a ``glb_node`` record with a non-zero ``node_offset``)."""
    cat = wfx.make_catalogs_dir(tmp_path, name)
    shutil.copyfile(HERE / "review_FAKE_Review.json", cat / f"{REVIEW_PACK}.json")
    if shared:
        doc = json.loads((HERE / "review_FAKE_Review.json").read_text(encoding="utf-8"))
        asset = _load("make_catalogs")._asset(SHARED_PACK, "SM_Wep_Bow_Shared_01", glb=SHARED_GLB)
        asset["files"]["glb_node"] = "Bow_B"
        doc.update(pack_id=SHARED_PACK, assets=[asset], asset_count=1)
        (cat / f"{SHARED_PACK}.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return cat


def build(cat: Path, **kw):
    kw.setdefault("pack_settings", pack_settings())
    return wfx.build(cat, **kw)


def build_and_write(cat: Path, **kw):
    """Build (unmeasured unless ``threejs_v2_dir`` is given) and write ``<cat>/weapons/{directory,excluded}.json``."""
    from synty_inventory.weapons.directory import write_directory

    if "threejs_v2_dir" not in kw:
        kw.setdefault("measure", False)
    directory, excluded = build(cat, **kw)
    write_directory(cat, directory, excluded)
    return directory, excluded


def png_bytes(rgb=(200, 80, 60), size=64) -> bytes:
    """A small valid PNG: a ``rgb`` disc-ish diamond on a dark square (so a capture shows something)."""
    rows = []
    c = size // 2
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            inside = abs(x - c) + abs(y - c) < c - 6
            row += bytes(rgb if inside else (24, 28, 34))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def attach_icons(directory: dict, weapons_dir: Path, ids) -> None:
    """Give ``ids`` a 256/64 px icon pair on disk (and in the in-memory records), as W3 will."""
    by_id = {w["id"]: w for w in directory["weapons"]}
    for n, rid in enumerate(sorted(ids)):
        rec = by_id[rid]
        icon = f"icons/{rec['pack']}/{rec['asset_id']}.png"
        thumb = f"icons/{rec['pack']}/{rec['asset_id']}@64.png"
        colour = [(214, 96, 70), (80, 170, 220), (110, 200, 120), (230, 190, 70)][n % 4]
        for rel, size in ((icon, 256), (thumb, 64)):
            path = weapons_dir / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(png_bytes(colour, size))
        rec["visuals"]["icon"], rec["visuals"]["thumb"] = icon, thumb


ROTATED_GUN = "FAKE_Modern/SM_Wep_Rifle_Assault_01"


def rotated_gun():
    """The Z-long rifle mesh with its y and z axes swapped: a Y-long gun, so its item_basis is not the identity."""
    verts, tris = M.gun()
    return verts[:, [0, 2, 1]], tris


def make_threejs(tmp_path: Path, cat: Path) -> Path:
    """A stand-in GLB for every fixture record that has a ``files.glb`` (same recipe as the W2 end-to-end test);
    ``ROTATED_GUN`` gets a Y-long gun so that the muzzle and support points are baked by a real rotation."""
    root = tmp_path / "threejs"
    base, _ = build(cat, measure=False)
    for rec in base["weapons"]:
        rel = rec["files"].get("glb")
        if not rel:
            continue
        dest = root / rel
        if rec["files"].get("glb_node"):
            M.write_glb(dest, M.shared_roots())  # the three-node shared GLB, not a stand-in mesh
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        mesh = rotated_gun() if rec["id"] == ROTATED_GUN else M.mesh_for(rec["archetype"], rec["kind"], rec["role"])
        roots = [{"name": rec["asset_id"], "mesh": mesh}]
        if rec["kind"] == "ranged":
            roots.append({"name": "SM_Fixture_Collision", "mesh": M.box((-1, -1, -1), (1, 1, 1))})
        M.write_glb(dest, roots)
    return root


# -- CLI harness --------------------------------------------------------------------------------------------

ENV_KEYS = ("SYNTI_CONFIG", "SYNTI_UNITY_ROOT", "SYNTI_EXTRACTED_ROOT", "SYNTI_THREEJS_V2", "SYNTI_VIEWER_DATA",
            "SYNTI_CATALOGS", "SYNTI_GODOT_ROOT", "SYNTI_UNREAL_ROOT", "SYNTI_SYNTY_GLB_ROOT")


def write_config(tmp_path: Path, cat: Path, extra: list[str] | None = None, name: str = "config.yaml") -> Path:
    cfg = tmp_path / name
    lines = [f'unity_root: "{tmp_path.as_posix()}/unity"', f'extracted_root: "{tmp_path.as_posix()}/extracted"',
             f'catalogs: "{cat.as_posix()}"', *(extra or [])]
    cfg.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return cfg


def run(cfg: Path, capsys, argv: list[str]):
    """``synty-inventory --config CFG ARGV`` -> (exit code, parsed stdout JSON)."""
    from synty_inventory.cli import main

    capsys.readouterr()
    code = main(["--config", str(cfg), *argv])
    return code, json.loads(capsys.readouterr().out)
