"""Weapon directory W7 slice 3: icon albedo from the Unity material (AC56) and the blend-retry opacity (AC57).

docs/weapon_directory.md section 3.8 PATCH W7. The pure logic runs with a fake renderer standing in for
``icons.Renderer`` (no browser); the two real-renderer tests (AC56 colour, AC57 alpha) skip with their reason when
Chromium or the synty-glb checkout is not available. Everything here is synthetic: a made-up pack, made-up ids, a
made-up extracted tree written into ``tmp_path``. Every bound is a literal, not a constant under test.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import struct
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
import pytest

from synty_inventory.cli import main
from synty_inventory.weapons import guards, icons
from synty_inventory.weapons import variants as V
from synty_inventory.weapons.directory import write_directory
from synty_inventory.weapons.rules import icon_albedo_entries, load_rules

_FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("wfx", _FIX / "wfx.py")
wfx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wfx)
_spec = importlib.util.spec_from_file_location("atlas_alt_helpers", _FIX / "atlas_alt" / "helpers.py")
AA = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(AA)

PACK = "FAKE_Shields"
SET_ID = "SM_Wep_Shield_Set_Fake_01"      # matches the entry below
SINGLE_ID = "SM_Wep_Shield_Single_01"     # same pack, id does not match
MATERIAL = "Assets/Synty/FakeShields/Materials/FakeShield.mat"
ENTRY = {"name": "fake_shield_sets", "packs_any": ["FAKE_Shields"], "id_regex": "^SM_Wep_Shield_Set_"}
RED, GREEN = (200, 40, 40), (40, 200, 40)
BASIS = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
GUID = "c0ffee00000000000000000000000001"
ENV_KEYS = ("SYNTI_CONFIG", "SYNTI_UNITY_ROOT", "SYNTI_EXTRACTED_ROOT", "SYNTI_THREEJS_V2", "SYNTI_VIEWER_DATA",
            "SYNTI_CATALOGS", "SYNTI_GODOT_ROOT", "SYNTI_UNREAL_ROOT", "SYNTI_SYNTY_GLB_ROOT")
# the input sha of the synthetic record SINGLE_ID as it was before W7 (its GLB bytes are deterministic)
SINGLE_SHA_BEFORE_W7 = "bd788c5cb7b8e86a"  # computed with the d9caf47 icon_input_sha


# --- a synthetic world: two textured GLBs and an extracted tree whose material uses _Base_Texture ---------------------


def material_text(slot: str = "_Base_Texture") -> str:
    return (
        "%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n--- !u!21 &2100000\nMaterial:\n  serializedVersion: 8\n"
        "  m_Name: FakeShield\n  m_SavedProperties:\n    serializedVersion: 3\n    m_TexEnvs:\n"
        "    - _Albedo_Map:\n        m_Texture: {fileID: 0}\n        m_Scale: {x: 1, y: 1}\n"
        f"    - {slot}:\n        m_Texture: {{fileID: 2800000, guid: {GUID}, type: 3}}\n"
        "        m_Scale: {x: 1, y: 1}\n        m_Offset: {x: 0, y: 0}\n")


def make_extracted(root: Path, *, slot: str = "_Base_Texture", texture: bool = True, rgb=GREEN) -> Path:
    """``root/<PACK>/Assets/Synty/FakeShields`` with the material and (optionally) its texture ``FakeShield_Tex.png``
    (a different stem than the material, so only the guid in the material finds it)."""
    base = root / PACK / "Assets" / "Synty" / "FakeShields"
    (base / "Materials").mkdir(parents=True, exist_ok=True)
    (base / "Textures").mkdir(parents=True, exist_ok=True)
    (base / "Materials" / "FakeShield.mat").write_text(material_text(slot), encoding="utf-8", newline="")
    if texture:
        (base / "Textures" / "FakeShield_Tex.png").write_bytes(AA._png(rgb))
        (base / "Textures" / "FakeShield_Tex.png.meta").write_text(
            f"fileFormatVersion: 2\nguid: {GUID}\nTextureImporter:\n  serializedVersion: 11\n", encoding="utf-8", newline="")
    return root


def record(asset_id: str, materials=(MATERIAL,)) -> dict:
    return {"id": f"{PACK}/{asset_id}", "pack": PACK, "asset_id": asset_id, "kind": "shield", "archetype": "shield",
            "geometry": {"item_basis": BASIS}, "files": {"glb": f"{PACK}/{asset_id}.glb", "unity_materials": list(materials)},
            "visuals": {"icon": None, "thumb": None, "icon_input_sha": None, "variants": []}}


@pytest.fixture
def world(tmp_path, monkeypatch):
    threejs = tmp_path / "threejs"
    for aid in (SET_ID, SINGLE_ID):
        AA.write_textured_glb(threejs / PACK / f"{aid}.glb", RED)  # the embedded (wrong) texture is red
    extracted = make_extracted(tmp_path / "extracted")
    monkeypatch.setattr(icons, "check_renderer", lambda root: Path("."))
    return SimpleNamespace(tmp=tmp_path, threejs=threejs, extracted=extracted, out=tmp_path / "weapons" / "icons")


def block(size: int, rgb) -> np.ndarray:
    px = np.zeros((size, size, 4), dtype=np.uint8)
    q = size // 4
    px[q:size - q, q:size - q] = (*rgb, 255)
    return px


class FakeRenderer:
    """Stands in for ``icons.Renderer``; logs ``(glb name, texture name, force_blend)`` per render. A drawn picture is red
    for the embedded texture and green for any substituted one; ``blank_first`` makes the normal pass blank."""

    def __init__(self, blank_first: bool = False):
        self.calls: list[tuple] = []
        self.blank_first = blank_first

    def __call__(self, root, *, gpu=False, **_kw):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def render(self, glb, nodes, scale, item_basis, shield, size, texture=None, force_blend=False):
        self.calls.append((Path(glb).name, Path(texture).name if texture is not None else None, bool(force_blend)))
        if self.blank_first and not force_blend:
            return np.zeros((size, size, 4), np.uint8)
        return block(size, RED if texture is None else GREEN)


def run(world, monkeypatch, records, *, entries=(ENTRY,), extracted="default", fake=None):
    fake = fake or FakeRenderer()
    monkeypatch.setattr(icons, "Renderer", fake)
    report: dict = {}
    results = icons.render_icons(
        records, world.out, threejs_v2_dir=world.threejs, synty_glb_root=Path("."), report=report,
        extracted_root=world.extracted if extracted == "default" else extracted, albedo_entries=list(entries))
    return results, report, fake


def glb_sha(world, asset_id: str) -> str:
    return hashlib.sha256((world.threejs / PACK / f"{asset_id}.glb").read_bytes()).hexdigest()


# --- matching and the pure sha ------------------------------------------------------------------------------------------


def test_an_entry_matches_on_pack_glob_and_on_the_bare_asset_id():
    match = icons.albedo_entry_for
    assert match(record(SET_ID), [ENTRY]) == ENTRY
    assert match(record(SINGLE_ID), [ENTRY]) is None
    other_pack = {**record(SET_ID), "pack": "FAKE_Other", "id": "FAKE_Other/" + SET_ID}
    assert match(other_pack, [ENTRY]) is None
    assert match(other_pack, [{"name": "any", "id_regex": "^SM_Wep_Shield_Set_"}]) is not None  # packs_any is optional
    assert match(record(SET_ID), [{"name": "glob", "packs_any": ["FAKE_Shi*"], "id_regex": "Set_Fake"}]) is not None
    # the regex sees the asset id, not "<pack>/<asset id>": an anchored pattern that fits only the pack-prefixed form fails
    assert match(record(SET_ID), [{"name": "x", "id_regex": "^FAKE_Shields/"}]) is None
    assert match(record(SET_ID), []) is None and match(record(SET_ID), None) is None


def test_the_input_sha_of_a_record_without_a_substitute_is_the_pre_w7_literal():
    basis = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    assert icons.icon_input_sha("a" * 64, None, 1.0, basis) == "5c92357186eb2891"  # also pinned by the W6 test
    assert icons.icon_input_sha("a" * 64, None, 1.0, basis, None) == "5c92357186eb2891"
    with_albedo = icons.icon_input_sha("a" * 64, None, 1.0, basis, "b" * 64)
    assert with_albedo != "5c92357186eb2891"
    assert with_albedo != icons.icon_input_sha("a" * 64, None, 1.0, basis, "c" * 64)  # the texture bytes are hashed
    assert icons.ICON_HARNESS_VERSION == 1


# --- the extra slot ---------------------------------------------------------------------------------------------------


def test_the_default_slots_still_miss_a_base_texture_only_material_and_the_extra_slot_finds_it(tmp_path):
    extracted = make_extracted(tmp_path / "ex")
    source = f"{PACK}/{MATERIAL}"
    assert V._ALBEDO_SLOTS == ("_Albedo_Map", "_BaseMap", "_MainTex", "_BaseColorMap")  # the colourway set, unchanged
    assert V.MATERIAL_ALBEDO_SLOTS == ("_Albedo_Map", "_BaseMap", "_MainTex", "_BaseColorMap", "_Base_Texture")
    with pytest.raises(V.TextureNotFound):
        V.resolve_variant_texture(extracted, source)  # the stem FakeShield.png does not exist: only the guid could find it
    found = V.resolve_variant_texture(extracted, source, slots=V.MATERIAL_ALBEDO_SLOTS)
    assert found.name == "FakeShield_Tex.png"
    # an Albedo_Map material resolves the same way with both slot sets
    other = make_extracted(tmp_path / "ex2", slot="_Albedo_Map")
    assert V.resolve_variant_texture(other, source).name == "FakeShield_Tex.png"
    assert V.resolve_variant_texture(other, source, slots=V.MATERIAL_ALBEDO_SLOTS).name == "FakeShield_Tex.png"


# --- the batch (fake renderer) -------------------------------------------------------------------------------------------


def test_a_matching_record_is_drawn_with_the_material_texture_and_hashes_it(world, monkeypatch):
    recs = [record(SET_ID), record(SINGLE_ID)]
    results, report, fake = run(world, monkeypatch, recs)
    calls = {name: (tex, blend) for name, tex, blend in fake.calls}
    assert calls[f"{SET_ID}.glb"] == ("FakeShield_Tex.png", False)  # the substituted albedo is passed to the renderer
    assert calls[f"{SINGLE_ID}.glb"] == (None, False)  # a record not in the table renders as before
    tex_sha = hashlib.sha256(AA._png(GREEN)).hexdigest()
    basis = BASIS
    assert results[f"{PACK}/{SET_ID}"]["sha256"] == icons.icon_input_sha(glb_sha(world, SET_ID), None, 1.0, basis, tex_sha)
    assert results[f"{PACK}/{SINGLE_ID}"]["sha256"] == icons.icon_input_sha(glb_sha(world, SINGLE_ID), None, 1.0, basis)
    assert report["warnings"] == [] and report["failed"] == []
    assert report["rendered"] == sorted(r["id"] for r in recs)


def test_only_matching_records_carry_the_albedo_key_so_no_other_icon_is_redrawn(world, monkeypatch):
    with_entry, _r, _f = run(world, monkeypatch, [record(SET_ID), record(SINGLE_ID)])
    without_entry, _r, _f = run(world, monkeypatch, [record(SET_ID), record(SINGLE_ID)], entries=())
    set_id, single_id = f"{PACK}/{SET_ID}", f"{PACK}/{SINGLE_ID}"
    assert with_entry[set_id]["sha256"] != without_entry[set_id]["sha256"]  # the entry changes the matching record
    assert with_entry[single_id]["sha256"] == without_entry[single_id]["sha256"] == SINGLE_SHA_BEFORE_W7
    # so an icon stored before W7 for a record outside the table still matches its hash (it is not drawn again)
    stored = record(SINGLE_ID)
    stored["visuals"].update(icon_input_sha=SINGLE_SHA_BEFORE_W7)
    assert stored["visuals"]["icon_input_sha"] == with_entry[single_id]["sha256"]


def test_the_blend_retry_keeps_the_substituted_texture(world, monkeypatch):
    _res, report, fake = run(world, monkeypatch, [record(SET_ID)], fake=FakeRenderer(blank_first=True))
    assert fake.calls == [(f"{SET_ID}.glb", "FakeShield_Tex.png", False), (f"{SET_ID}.glb", "FakeShield_Tex.png", True)]
    assert report["blend_retry"] == [f"{PACK}/{SET_ID}"] and report["failed"] == []


@pytest.mark.parametrize("how", ["material_missing", "no_materials", "texture_missing", "no_extracted_root"])
def test_an_unresolvable_material_keeps_the_embedded_texture_and_is_reported(world, monkeypatch, tmp_path, how):
    rec = record(SET_ID)
    extracted = "default"
    if how == "material_missing":
        rec["files"]["unity_materials"] = ["Assets/Synty/FakeShields/Materials/Nowhere.mat"]
    elif how == "no_materials":
        rec["files"]["unity_materials"] = []
    elif how == "texture_missing":
        extracted = make_extracted(tmp_path / "bare", texture=False)
    else:
        extracted = None
    results, report, fake = run(world, monkeypatch, [rec, record(SINGLE_ID)], extracted=extracted)
    assert fake.calls[0][:2] == (f"{SET_ID}.glb", None)  # drawn with the embedded texture, as before
    assert len(report["warnings"]) == 1 and f"{PACK}/{SET_ID}" in report["warnings"][0], report["warnings"]
    assert report["failed"] == []  # a warning, never a failed run
    assert results[f"{PACK}/{SET_ID}"]["sha256"] == icons.icon_input_sha(glb_sha(world, SET_ID), None, 1.0, BASIS)
    assert f"{PACK}/{SINGLE_ID}" not in report["warnings"][0]


def test_a_cached_record_whose_texture_cannot_be_resolved_is_still_reported(world, monkeypatch):
    rec = record(SET_ID, materials=[])
    sha = icons.icon_input_sha(glb_sha(world, SET_ID), None, 1.0, BASIS)
    first, _r, _f = run(world, monkeypatch, [rec])
    assert first[f"{PACK}/{SET_ID}"]["sha256"] == sha
    rec["visuals"].update(icon=first[rec["id"]]["icon"], thumb=first[rec["id"]]["thumb"], icon_input_sha=sha)
    _res, report, fake = run(world, monkeypatch, [rec])
    assert fake.calls == [] and report["skipped"] == [rec["id"]]  # nothing is drawn again ...
    assert len(report["warnings"]) == 1 and rec["id"] in report["warnings"][0]  # ... but the fault is not silent


def test_a_repainted_material_texture_renders_the_record_again(world, monkeypatch):
    rec = record(SET_ID)
    first, _r, _f = run(world, monkeypatch, [rec])
    rec["visuals"].update(icon=first[rec["id"]]["icon"], thumb=first[rec["id"]]["thumb"],
                          icon_input_sha=first[rec["id"]]["sha256"])
    again, report, fake = run(world, monkeypatch, [rec])
    assert fake.calls == [] and report["skipped"] == [rec["id"]] and again[rec["id"]]["sha256"] == first[rec["id"]]["sha256"]
    tex = world.extracted / PACK / "Assets" / "Synty" / "FakeShields" / "Textures" / "FakeShield_Tex.png"
    tex.write_bytes(AA._png((10, 10, 200)))
    changed, report, fake = run(world, monkeypatch, [rec])
    assert report["rendered"] == [rec["id"]] and changed[rec["id"]]["sha256"] != first[rec["id"]]["sha256"]


# --- the CLI wiring ------------------------------------------------------------------------------------------------------


def test_the_icons_verb_hands_the_rules_entries_and_the_extracted_root_to_render_icons(tmp_path, monkeypatch):
    cat = wfx.make_catalogs_dir(tmp_path)
    directory, excluded = wfx.build(cat, measure=False)
    write_directory(cat, directory, excluded)
    seen: dict = {}

    def fake_render_icons(records, out_dir, **kw):
        seen.update(kw)
        kw["report"].update(rendered=[], skipped=[], failed=[], blend_retry=[],
                            warnings=["P/x: albedo from material (n) not resolved, the embedded texture is used: why"])
        return {}

    monkeypatch.setattr(icons, "render_icons", fake_render_icons)
    monkeypatch.setattr(icons, "check_renderer", lambda root: Path("."))
    monkeypatch.setattr(guards, "other_inventory_processes", lambda: [])
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f'unity_root: "{tmp_path.as_posix()}/unity"\nextracted_root: "{tmp_path.as_posix()}/extracted"\n'
                   f'catalogs: "{cat.as_posix()}"\nsynty_glb_root: "."\n', encoding="utf-8")
    out = io.StringIO()
    with mock.patch.dict(os.environ), contextlib.redirect_stdout(out):
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        assert main(["--config", str(cfg), "weapons", "icons"]) == 0  # no --variants
    assert seen["albedo_entries"] == icon_albedo_entries(load_rules()) and seen["albedo_entries"] != []
    assert seen["extracted_root"] == tmp_path / "extracted"  # needed for the albedo even without --variants
    summary = json.loads(out.getvalue())
    assert summary["warnings"] == ["P/x: albedo from material (n) not resolved, the embedded texture is used: why"]


# --- the real harness: AC56 colour and AC57 alpha ---------------------------------------------------------------------------


def real_glb_root() -> Path:
    env = os.environ.get("SYNTI_SYNTY_GLB_ROOT")
    candidates = ([Path(env)] if env else []) + [
        Path(__file__).resolve().parents[2] / "synty-glb",
        Path("D:/") / "_".join(("game", "assets", "library")) / "tools" / "synty-glb",
    ]
    root = next((c for c in candidates if (c / "node_modules" / "three" / "build" / "three.module.js").is_file()), None)
    if root is None:
        pytest.skip("synty-glb root with node_modules/three not found (set SYNTI_SYNTY_GLB_ROOT)")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("the playwright package is not installed")
    try:
        with sync_playwright() as pw:
            icons._launch_browser(pw, False).close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Chromium cannot be launched: {str(exc).splitlines()[0] if str(exc) else exc!r}")
    return root


def covered_mean(png: Path) -> tuple[float, float, float]:
    img = icons.decode_png(png.read_bytes())
    px = img[img[..., 3] > 0][:, :3].astype(float)
    assert len(px) > 500  # a real picture, not a stray pixel
    return tuple(px.mean(axis=0))


def test_ac56_the_real_render_takes_its_colour_from_the_material_texture(tmp_path):
    glb_root = real_glb_root()
    threejs = tmp_path / "threejs"
    AA.write_textured_glb(threejs / PACK / f"{SET_ID}.glb", RED)  # texture A (red) is embedded
    extracted = make_extracted(tmp_path / "extracted", rgb=GREEN)  # texture B (green) is the material's
    rec = record(SET_ID)
    out_with, out_without = tmp_path / "with" / "icons", tmp_path / "without" / "icons"
    reports = []
    for out, entries in ((out_with, [ENTRY]), (out_without, [])):
        report: dict = {}
        icons.render_icons([rec], out, threejs_v2_dir=threejs, synty_glb_root=glb_root, report=report,
                           extracted_root=extracted, albedo_entries=entries)
        assert report["failed"] == [] and report["warnings"] == [], report
        reports.append(report)
    r_with, g_with, _b = covered_mean(out_with / PACK / f"{SET_ID}.png")
    r_without, g_without, _b = covered_mean(out_without / PACK / f"{SET_ID}.png")
    assert g_with > r_with + 30  # texture B (green) dominates the tile
    assert r_without > g_without + 30  # without the entry the embedded texture A (red) is drawn


def gltf_with(path: Path, *, factor_alpha: float, png: bytes | None = None, cutoff: float = 0.5) -> Path:
    """The textured box fixture as a MASK material with base-colour factor alpha ``factor_alpha``; ``png`` (when given)
    replaces the embedded texture image (it is the last buffer view of the fixture)."""
    data = AA.textured_glb_bytes(RED)
    jlen, jtype = struct.unpack("<II", data[12:20])
    assert jtype == 0x4E4F534A
    doc = json.loads(data[20:20 + jlen])
    blen, _btype = struct.unpack("<II", data[20 + jlen:28 + jlen])
    binary = data[28 + jlen:28 + jlen + blen]
    if png is not None:
        view = doc["bufferViews"][4]
        assert view["byteOffset"] + view["byteLength"] <= blen
        binary = binary[:view["byteOffset"]] + png
        view["byteLength"] = len(png)
        doc["buffers"][0]["byteLength"] = len(binary)
    mat = doc["materials"][0]
    mat["pbrMetallicRoughness"]["baseColorFactor"] = [1.0, 1.0, 1.0, factor_alpha]
    mat["alphaMode"], mat["alphaCutoff"] = "MASK", cutoff
    js = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    binary += b"\0" * (-len(binary) % 4)
    body = struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(binary), 0x004E4942) + binary
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body)
    return path


def rgba_png(rgba=(200, 40, 40, 153), n: int = 8) -> bytes:
    raw = b"".join(b"\x00" + bytes(rgba) * n for _ in range(n))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def test_ac57_the_retry_draws_an_atlas_with_a_factor_alpha_fully_opaque_and_texture_alpha_still_blends(tmp_path):
    glb_root = real_glb_root()
    threejs = tmp_path / "threejs"
    # factor alpha 0.4 on an opaque RGB atlas: 0.4 < the 0.5 cutoff, so the first render is blank (the Mech case)
    gltf_with(threejs / "P" / "atlas.glb", factor_alpha=0.4)
    # factor alpha 0.4 on a texture whose alpha channel is 153/255 = 0.6: blank first as well (0.24 < 0.5), then the
    # texture alpha alone decides
    gltf_with(threejs / "P" / "alpha.glb", factor_alpha=0.4, png=rgba_png())
    recs = []
    for name in ("atlas", "alpha"):
        rec = record(name)
        rec.update(id=f"P/{name}", pack="P", asset_id=name)
        rec["files"] = {"glb": f"P/{name}.glb"}
        recs.append(rec)
    out = tmp_path / "weapons" / "icons"
    report: dict = {}
    results = icons.render_icons(recs, out, threejs_v2_dir=threejs, synty_glb_root=glb_root, report=report)
    assert report["failed"] == [], report
    assert report["blend_retry"] == ["P/alpha", "P/atlas"]
    assert results["P/atlas"]["icon_mode"] == "blend_retry" and results["P/alpha"]["icon_mode"] == "blend_retry"
    atlas = icons.decode_png((out / "P" / "atlas.png").read_bytes())[..., 3]
    alpha = icons.decode_png((out / "P" / "alpha.png").read_bytes())[..., 3]
    assert len(atlas[atlas > 0]) > 500 and len(alpha[alpha > 0]) > 500
    assert int(np.median(atlas[atlas > 0])) == 255  # not about 102 (0.4 * 255): the factor alpha is dropped
    assert 150 <= int(np.median(alpha[alpha > 0])) <= 156  # 153: the texture alpha still blends (not 255, not 61)
