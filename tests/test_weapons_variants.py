"""Weapon directory W5: colourway discovery and the texture resolver (AC19; docs/weapon_directory.md section 3.7).

The fixture is the synthetic ``tests/fixtures/weapons/atlas_alt`` tree (see its ``helpers.py``): one pack with three
sibling Alts materials A/B/C, a two-letter atlas whose B texture is a ``.tga``, a lone-letter atlas, decoy files that
must not count as siblings, and a pack with a dedicated material and no Alts. Expected lists are literals.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

_FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("wfx", _FIX / "wfx.py")
wfx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wfx)
_spec = importlib.util.spec_from_file_location("atlas_alt_helpers", _FIX / "atlas_alt" / "helpers.py")
AA = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(AA)

from synty_inventory.weapons import variants as V  # noqa: E402
from synty_inventory.weapons.directory import (  # noqa: E402
    DIRECTORY_NAME,
    build_directory_report,
    read_json,
    write_directory,
)
from synty_inventory.weapons.overrides import empty_overrides  # noqa: E402
from synty_inventory.weapons.schema import validate_directory  # noqa: E402

PREFIX = "Assets/Synty/FakeAtlas/Materials/Alts/"
SWORD = "FAKE_AtlasAlt/SM_Wep_Sword_Atlas_01"
AXE = "FAKE_AtlasAlt/SM_Wep_Axe_Atlas_01"
MACE = "FAKE_AtlasAlt/SM_Wep_Mace_Atlas_01"
SPEAR = "FAKE_AtlasAlt/SM_Wep_Spear_Atlas_01"
KNIFE = "FAKE_AtlasAlt/SM_Wep_Knife_Atlas_01"
CLUB = "FAKE_AtlasAlt/SM_Wep_Club_NoMaterial_01"
PISTOL = "FAKE_NoAlts/SM_Wep_Pistol_NoAlts_01"


def variant(letter, atlas, *, default=False, icon=None):
    return {"variant_id": letter, "mechanism": "atlas_alt", "source": f"{PREFIX}FakeAtlas_{atlas}_{letter}.mat",
            "is_default": default, "icon": icon}


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("variants")
    cat = AA.make_catalogs(tmp)
    directory, excluded, report = build_directory_report(
        cat, overrides=empty_overrides(), pack_settings=AA.PACK_SETTINGS, measure=False, extracted_root=AA.EXTRACTED)
    return {"tmp": tmp, "cat": cat, "dir": directory, "excl": excluded, "report": report,
            "by_id": wfx.records_by_id(directory)}


def asset_of(world, rid):
    pack, aid = rid.split("/", 1)
    doc = json.loads((world["cat"] / f"{pack}.json").read_text(encoding="utf-8"))
    return next(a for a in doc["assets"] if a["id"] == aid)


# --- discover_variants ----------------------------------------------------------------------------------------------


def test_ac19_three_sibling_materials_give_a_b_c_with_the_catalog_pointer_as_default(world):
    got = V.discover_variants(asset_of(world, SWORD), AA.EXTRACTED / "FAKE_AtlasAlt")
    assert got == [variant("A", "01", default=True), variant("B", "01"), variant("C", "01")]


def test_the_default_is_the_letter_the_catalog_points_at_not_always_a(world):
    got = V.discover_variants(asset_of(world, AXE), AA.EXTRACTED / "FAKE_AtlasAlt")
    assert [(v["variant_id"], v["is_default"]) for v in got] == [("A", False), ("B", True), ("C", False)]


def test_the_alts_material_is_found_among_other_materials(world):
    got = V.discover_variants(asset_of(world, KNIFE), AA.EXTRACTED / "FAKE_AtlasAlt")
    assert [(v["variant_id"], v["is_default"]) for v in got] == [("A", False), ("B", False), ("C", True)]


def test_two_letters_are_listed_and_a_lone_letter_is_not_a_choice(world):
    root = AA.EXTRACTED / "FAKE_AtlasAlt"
    assert V.discover_variants(asset_of(world, MACE), root) == [variant("A", "02", default=True), variant("B", "02")]
    assert V.discover_variants(asset_of(world, SPEAR), root) == []


def test_decoys_beside_the_siblings_are_not_colourways(world):
    # FakeAtlas_01_Extra.mat (not one capital letter) and FakeAtlas_01_B.mat.meta sit in the same directory
    letters = [v["variant_id"] for v in V.discover_variants(asset_of(world, SWORD), AA.EXTRACTED / "FAKE_AtlasAlt")]
    assert letters == ["A", "B", "C"]


def test_a_pack_without_alts_and_a_record_without_materials_have_no_variants(world):
    assert V.discover_variants(asset_of(world, PISTOL), AA.EXTRACTED / "FAKE_NoAlts") == []
    assert V.discover_variants(asset_of(world, CLUB), AA.EXTRACTED / "FAKE_AtlasAlt") == []
    assert V.has_colourway_info(asset_of(world, PISTOL)) and not V.has_colourway_info(asset_of(world, CLUB))


def test_no_extracted_tree_or_a_missing_directory_gives_no_variants_and_no_error(world, tmp_path):
    a = asset_of(world, SWORD)
    assert V.discover_variants(a, None) == []
    assert V.discover_variants(a, tmp_path / "nope") == []
    assert V.discover_variants(a, tmp_path) == []  # a tree without the pack's Assets folder


@pytest.mark.parametrize("bad", ["/abs/Materials/Alts/X_01_A.mat", "../Materials/Alts/X_01_A.mat",
                                 "C:/Materials/Alts/X_01_A.mat", "Assets/Materials/Alts/../Alts/X_01_A.mat"])
def test_unsafe_material_paths_are_ignored(world, bad):
    assert V.discover_variants({"files": {"unity_materials": [bad]}}, AA.EXTRACTED / "FAKE_AtlasAlt") == []


def test_listing_is_cached_per_directory(world, monkeypatch):
    calls = []
    real = os.listdir
    monkeypatch.setattr(V.os, "listdir", lambda p: (calls.append(str(p)), real(p))[1])
    root, cache = AA.EXTRACTED / "FAKE_AtlasAlt", {}
    for rid in (SWORD, AXE, KNIFE, MACE, SPEAR) * 40:  # 200 lookups of one Alts directory
        V.discover_variants(asset_of(world, rid), root, cache)
    assert len(calls) == 1
    calls.clear()
    V.discover_variants(asset_of(world, SWORD), root)  # no cache given: no hidden state either
    V.discover_variants(asset_of(world, SWORD), root)
    assert len(calls) == 2


# --- the build ------------------------------------------------------------------------------------------------------


def test_the_build_carries_variants_on_the_record_visuals(world):
    by_id = world["by_id"]
    assert by_id[SWORD]["visuals"]["variants"] == [variant("A", "01", default=True), variant("B", "01"),
                                                   variant("C", "01")]
    assert [v["variant_id"] for v in by_id[MACE]["visuals"]["variants"]] == ["A", "B"]
    for rid in (SPEAR, CLUB, PISTOL):
        assert by_id[rid]["visuals"]["variants"] == [], rid
    assert validate_directory(world["dir"], world["excl"]) == []


def test_colourway_unknown_only_when_no_material_is_recorded(world):
    by_id = world["by_id"]
    assert "colourway_unknown" in by_id[CLUB]["review"]["reasons"]
    for rid in (SWORD, AXE, MACE, SPEAR, KNIFE, PISTOL):  # a lone letter or a dedicated material is still known
        assert "colourway_unknown" not in by_id[rid]["review"]["reasons"], rid


def test_sources_are_tree_relative_posix_paths_with_no_machine_path(world):
    text = json.dumps(world["dir"])
    assert "\\\\" not in text and ":/" not in text.replace("https://", "")  # no drive letter, no backslash
    for rec in world["dir"]["weapons"]:
        for var in rec["visuals"]["variants"]:
            assert var["source"].startswith("Assets/Synty/") and var["source"].endswith(".mat")


def test_the_build_is_deterministic_and_does_not_touch_the_tree(world):
    again, _, _ = build_directory_report(
        world["cat"], overrides=empty_overrides(), pack_settings=AA.PACK_SETTINGS, measure=False,
        extracted_root=AA.EXTRACTED)
    assert json.dumps(again, sort_keys=True) == json.dumps(world["dir"], sort_keys=True)


def test_without_an_extracted_tree_the_build_skips_variants_cleanly(world):
    d, _, report = build_directory_report(
        world["cat"], overrides=empty_overrides(), pack_settings=AA.PACK_SETTINGS, measure=False)
    by_id = wfx.records_by_id(d)
    assert all(r["visuals"]["variants"] == [] for r in d["weapons"])
    assert any("variants skipped" in w for w in report["warnings"])
    assert "colourway_unknown" in by_id[CLUB]["review"]["reasons"]  # needs no disk
    d2, _, _ = build_directory_report(  # a configured root that has no folder for the pack behaves the same
        world["cat"], overrides=empty_overrides(), pack_settings=AA.PACK_SETTINGS, measure=False,
        extracted_root=world["tmp"] / "nowhere")
    assert all(r["visuals"]["variants"] == [] for r in d2["weapons"])


def test_the_catalog_source_extracted_is_the_fallback_when_no_root_is_given(world, tmp_path):
    cat = AA.make_catalogs(tmp_path)
    path = cat / "FAKE_AtlasAlt.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["source"] = {"extracted": (AA.EXTRACTED / "FAKE_AtlasAlt").as_posix(), "unitypackage": None, "unreal": None}
    path.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    d, _, _ = build_directory_report(cat, overrides=empty_overrides(), pack_settings=AA.PACK_SETTINGS, measure=False)
    assert [v["variant_id"] for v in wfx.records_by_id(d)[SWORD]["visuals"]["variants"]] == ["A", "B", "C"]
    assert "Assets" not in json.dumps({k: v for k, v in d.items() if k != "weapons"})  # the path is not recorded


def test_a_listing_failure_never_fails_the_build(world, monkeypatch):
    def boom(*_a, **_k):
        raise OSError("disk went away")

    monkeypatch.setattr("synty_inventory.weapons.directory.discover_variants", boom)
    d, _, report = build_directory_report(
        world["cat"], overrides=empty_overrides(), pack_settings=AA.PACK_SETTINGS, measure=False,
        extracted_root=AA.EXTRACTED)
    assert all(r["visuals"]["variants"] == [] for r in d["weapons"])
    assert any("variants not listed" in w for w in report["warnings"])


# --- carry-forward of variant icon links ----------------------------------------------------------------------------


def _rebuild(cat):
    d, e, _ = build_directory_report(cat, overrides=empty_overrides(), pack_settings=AA.PACK_SETTINGS, measure=False,
                                     extracted_root=AA.EXTRACTED)
    write_directory(cat, d, e)
    return d


def test_variant_icon_links_survive_a_rebuild_when_both_files_exist(tmp_path):
    cat = AA.make_catalogs(tmp_path)
    _rebuild(cat)
    dpath = cat / "weapons" / DIRECTORY_NAME
    stored = read_json(dpath)
    sword = next(w for w in stored["weapons"] if w["id"] == SWORD)
    for var in sword["visuals"]["variants"]:
        if var["variant_id"] in ("B", "C"):
            icon, thumb = V.variant_link_paths("icons", "FAKE_AtlasAlt", "SM_Wep_Sword_Atlas_01", var["variant_id"])
            var["icon"], var["icon_input_sha"] = icon, "0123456789abcdef"
            for rel in ((icon, thumb) if var["variant_id"] == "B" else (icon,)):  # C lacks its thumbnail
                (cat / "weapons" / rel).parent.mkdir(parents=True, exist_ok=True)
                (cat / "weapons" / rel).write_bytes(b"png")
    from synty_inventory.weapons import to_text

    dpath.write_bytes(to_text(stored).encode("utf-8"))
    linked = dpath.read_bytes()
    again = _rebuild(cat)
    got = {v["variant_id"]: v for v in wfx.records_by_id(again)[SWORD]["visuals"]["variants"]}
    assert got["B"]["icon"] == "icons/FAKE_AtlasAlt/SM_Wep_Sword_Atlas_01@B.png"
    assert got["B"]["icon_input_sha"] == "0123456789abcdef"
    assert got["A"]["icon"] is None and "icon_input_sha" not in got["A"]
    assert got["C"]["icon"] is None  # INV-8: no link to a half-written pair
    assert [v["icon"] for v in wfx.records_by_id(again)[AXE]["visuals"]["variants"]] == [None, None, None]
    first = dpath.read_bytes()
    assert _rebuild(cat) and dpath.read_bytes() == first  # INV-4 with an existing directory in place
    assert first != linked  # only because C's dangling link was dropped
    assert validate_directory(read_json(dpath), None) == []


def test_a_link_that_is_not_the_variant_path_is_not_carried(tmp_path):
    cat = AA.make_catalogs(tmp_path)
    _rebuild(cat)
    dpath = cat / "weapons" / DIRECTORY_NAME
    stored = read_json(dpath)
    sword = next(w for w in stored["weapons"] if w["id"] == SWORD)
    sword["visuals"]["variants"][1].update(icon="icons/elsewhere.png", icon_input_sha="0123456789abcdef")
    (cat / "weapons" / "icons").mkdir(exist_ok=True)
    (cat / "weapons" / "icons" / "elsewhere.png").write_bytes(b"png")
    from synty_inventory.weapons import to_text

    dpath.write_bytes(to_text(stored).encode("utf-8"))
    assert all(v["icon"] is None for v in wfx.records_by_id(_rebuild(cat))[SWORD]["visuals"]["variants"])


# --- resolver -------------------------------------------------------------------------------------------------------


def test_the_resolver_follows_the_albedo_guid_and_ignores_the_normal_map_slot(world):
    root = AA.EXTRACTED / "FAKE_AtlasAlt"
    tex = {v["variant_id"]: V.resolve_variant_texture(root, v["source"])
           for v in V.discover_variants(asset_of(world, SWORD), root)}
    base = root / "Assets/Synty/FakeAtlas/Textures/Alts"
    assert tex["A"] == base / "FakeAtlas_01_A.png" and tex["B"] == base / "FakeAtlas_01_B.png"
    # C's texture file is not named after its material: only the guid in the material finds it
    assert tex["C"] == base / "FakeAtlas_01_C_Diffuse.png"


def test_the_resolver_falls_back_to_the_file_stem_when_the_guid_is_unknown(tmp_path):
    mat = tmp_path / "Assets/P/Materials/Alts/Atlas_01_A.mat"
    mat.parent.mkdir(parents=True)
    mat.write_text("    - _Albedo_Map:\n        m_Texture: {fileID: 2800000, guid: " + "9" * 32 + ", type: 3}\n",
                   encoding="utf-8")
    tex = tmp_path / "Assets/P/Textures/Alts/Atlas_01_A.png"
    tex.parent.mkdir(parents=True)
    tex.write_bytes(b"x")
    assert V.resolve_variant_texture(tmp_path, "Assets/P/Materials/Alts/Atlas_01_A.mat") == tex


def test_the_resolver_also_looks_in_the_parent_textures_directory(tmp_path):
    mat = tmp_path / "Assets/P/Materials/Alts/Atlas_01_B.mat"
    mat.parent.mkdir(parents=True)
    mat.write_text("    - _MainTex:\n        m_Texture: {fileID: 2800000, guid: " + "8" * 32 + ", type: 3}\n",
                   encoding="utf-8")
    tex = tmp_path / "Assets/P/Textures/Atlas_01_B.png"  # some packs keep the Alts atlases beside the base ones
    tex.parent.mkdir(parents=True)
    tex.write_bytes(b"x")
    (tex.parent / "Atlas_01_B.png.meta").write_text("fileFormatVersion: 2\nguid: " + "8" * 32 + "\n", encoding="utf-8")
    assert V.resolve_variant_texture(tmp_path, "Assets/P/Materials/Alts/Atlas_01_B.mat") == tex


def test_the_resolver_reports_why_a_texture_cannot_be_used(world, tmp_path):
    root = AA.EXTRACTED / "FAKE_AtlasAlt"
    with pytest.raises(V.TextureNotFound, match=r"unsupported texture format \.tga"):
        V.resolve_variant_texture(root, f"{PREFIX}FakeAtlas_02_B.mat")
    with pytest.raises(V.TextureNotFound, match="material not readable"):
        V.resolve_variant_texture(root, f"{PREFIX}FakeAtlas_01_Z.mat")
    with pytest.raises(V.TextureNotFound, match="no texture found"):
        V.resolve_variant_texture(root, f"{PREFIX}FakeAtlas_03_A.mat")  # the material exists, its texture does not
    with pytest.raises(V.TextureNotFound, match="unsafe"):
        V.resolve_variant_texture(root, "../outside.mat")
    mat = tmp_path / "Loose.mat"
    mat.write_text("x", encoding="utf-8")
    with pytest.raises(V.TextureNotFound, match="not under a Materials"):
        V.resolve_variant_texture(tmp_path, "Loose.mat")


def test_resolver_caches_listings_and_guid_indexes(world, monkeypatch):
    calls = []
    real = os.listdir
    monkeypatch.setattr(V.os, "listdir", lambda p: (calls.append(str(p)), real(p))[1])
    root, cache = AA.EXTRACTED / "FAKE_AtlasAlt", {}
    for _ in range(5):
        for letter in "ABC":
            V.resolve_variant_texture(root, f"{PREFIX}FakeAtlas_01_{letter}.mat", cache)
    assert len(calls) == 1  # the Textures/Alts directory, listed once
