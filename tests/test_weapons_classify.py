"""Weapon directory W1: tokenizer, classification rules, hold class, genre, rule hygiene.

Covers AC1, AC4, AC5, AC6, AC9 (docs/weapon_directory.md section 6). Thresholds and the expected tables below are
literals on purpose: loosening a constant in the implementation must not loosen a test.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

_spec = importlib.util.spec_from_file_location("wfx", Path(__file__).parent / "fixtures" / "weapons" / "wfx.py")
wfx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wfx)

from synty_inventory.cli import main  # noqa: E402
from synty_inventory.weapons import SchemaError  # noqa: E402
from synty_inventory.weapons.classify import classify, family_of, genre_for_pack, tokenize_id  # noqa: E402
from synty_inventory.weapons.overrides import empty_overrides  # noqa: E402
from synty_inventory.weapons.rules import load_rules, shadowed_rules, validate_rules  # noqa: E402

HOLD = {
    "pistol": "one_hand", "revolver": "one_hand", "utility_gun": "one_hand",
    "smg": "long_gun", "rifle": "long_gun", "shotgun": "long_gun", "sniper": "long_gun", "lmg": "long_gun",
    "heavy_gun": "long_gun", "launcher": "long_gun", "flamethrower": "long_gun",
    "bow": "bow", "crossbow": "crossbow",
    "knife": "melee_one", "sword": "melee_one", "axe": "melee_one", "mace": "melee_one", "whip": "melee_one",
    "wand": "melee_one", "tool": "melee_one", "fist_weapon": "melee_one",
    "spear": "melee_two", "polearm": "melee_two", "staff": "melee_two",
    "club": "melee_bat", "hammer": "melee_bat",
    "grenade": "thrown", "bomb": "thrown", "mine": "thrown", "throwing_blade": "thrown",
    "shield": "shield",
    "turret": "none", "cannon": "none", "siege_engine": "none", "mortar": "none", "unknown": "none",
}
KIND = {
    "pistol": "ranged", "revolver": "ranged", "smg": "ranged", "rifle": "ranged", "shotgun": "ranged",
    "sniper": "ranged", "lmg": "ranged", "heavy_gun": "ranged", "launcher": "ranged", "flamethrower": "ranged",
    "bow": "ranged", "crossbow": "ranged", "utility_gun": "ranged",
    "knife": "melee", "sword": "melee", "axe": "melee", "mace": "melee", "hammer": "melee", "club": "melee",
    "spear": "melee", "polearm": "melee", "staff": "melee", "wand": "melee", "whip": "melee",
    "fist_weapon": "melee", "tool": "melee",
    "grenade": "thrown", "bomb": "thrown", "mine": "thrown", "throwing_blade": "thrown",
    "shield": "shield", "turret": "ranged", "cannon": "ranged", "siege_engine": "ranged", "mortar": "ranged",
}


@pytest.fixture(scope="module")
def rules():
    return load_rules()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    directory, excluded = wfx.build(wfx.make_catalogs_dir(tmp_path_factory.mktemp("cls")))
    return directory, excluded


def _cls(rules, asset, pack="FAKE_Pack", setting=None, source="catalog", overrides=None):
    return classify(asset, pack, rules, overrides or empty_overrides(), setting, candidate_source=source)


# --- AC1 ---------------------------------------------------------------------------------------------------

def test_ac1_every_positive_has_a_record_and_accuracy_holds(built):
    directory, _ = built
    exp = wfx.expected()["weapons"]
    by_id = wfx.records_by_id(directory)
    assert len(exp) >= 100
    assert set(by_id) == set(exp)  # every positive has a record, and no record is unexpected
    n = len(exp)
    arch = sum(1 for i, w in exp.items() if by_id[i]["archetype"] == w["archetype"])
    kind = sum(1 for i, w in exp.items() if by_id[i]["kind"] == w["kind"])
    role = sum(1 for i, w in exp.items() if by_id[i]["role"] == w["role"])
    assert arch / n >= 0.95
    assert kind / n == 1.0
    assert role / n >= 0.97


def test_classification_matches_every_label(built):
    directory, _ = built
    exp = wfx.expected()["weapons"]
    for rec in directory["weapons"]:
        want = exp[rec["id"]]
        assert rec["review"]["matched_rule"] == want["rule"], rec["id"]
        assert rec["hold_class"] == want["hold_class"], rec["id"]
        assert rec["genre"] == want["genre"], rec["id"]
        assert rec["duplicate_of"] == want["duplicate_of"], rec["id"]
        assert rec["component"] == want["component"], rec["id"]
        assert rec["carrier"] == want["carrier"], rec["id"]
        assert rec["ammo"] == want["ammo"], rec["id"]
        assert sorted(rec["flags"]) == sorted(set(want["flags"]) | {"unmeasured"}), rec["id"]


def test_records_without_a_threejs_root_are_unmeasured_stubs_with_archetype_hints(built):
    # the `built` fixture passes no threejs_v2 root, so nothing can be measured; hints are still derived (W2)
    directory, _ = built
    for rec in directory["weapons"]:
        assert rec["geometry"] is None
        assert "unmeasured" in rec["flags"]
        assert "no_geometry" in rec["review"]["reasons"]
        hints = rec["hints"]
        assert hints["size_class"] is None and hints["size_basis"] is None and hints["inventory_cells"] is None
        no_tier = rec["role"] in ("part", "ammo", "carrier") or rec["archetype"] == "unknown"
        assert (hints["quality_tier"] is None) == no_tier, rec["id"]


# --- AC4 ---------------------------------------------------------------------------------------------------

def test_ac4_hold_class_follows_the_table_or_a_documented_exception(built):
    directory, _ = built
    seen_archetypes = set()
    for rec in directory["weapons"]:
        arch = rec["archetype"]
        seen_archetypes.add(arch)
        if rec["role"] != "whole":
            assert rec["hold_class"] == "none", rec["id"]
            continue
        if "mech_scale" in rec["flags"]:
            assert rec["hold_class"] == "none", rec["id"]
            continue
        allowed = {HOLD[arch]}
        if arch == "smg":
            allowed.add("one_hand")
        if rec["kind"] == "melee":
            allowed.add("melee_two")
        assert rec["hold_class"] in allowed, (rec["id"], arch, rec["hold_class"])
    assert len(seen_archetypes) >= 20


def test_ac4_mech_scale_fixture_weapons_hold_none(built):
    directory, _ = built
    mech = [w for w in directory["weapons"] if w["pack"] == "FAKE_Mech"]
    assert len(mech) >= 2
    for rec in mech:
        assert "mech_scale" in rec["flags"]
        assert rec["hold_class"] == "none"
    # the same archetype outside the mech pack keeps its table hold
    assert any(w["hold_class"] != "none" for w in directory["weapons"] if w["pack"] != "FAKE_Mech")


def test_hold_exceptions_need_gear_two_handed(rules):
    smg = {"id": "SM_Wep_SubMGun_01", "type": "weapon"}
    assert _cls(rules, smg)["hold_class"] == "long_gun"
    assert _cls(rules, {**smg, "gear": {"twoHanded": False}})["hold_class"] == "one_hand"
    assert _cls(rules, {**smg, "gear": {"twoHanded": True}})["hold_class"] == "long_gun"
    sword = {"id": "SM_Wep_Sword_01", "type": "weapon"}
    assert _cls(rules, sword)["hold_class"] == "melee_one"
    assert _cls(rules, {**sword, "gear": {"twoHanded": True}})["hold_class"] == "melee_two"
    assert _cls(rules, {**sword, "gear": {"twoHanded": False}})["hold_class"] == "melee_one"
    # a pistol ignores gear.twoHanded
    pistol = {"id": "SM_Wep_Pistol_01", "type": "weapon", "gear": {"twoHanded": True}}
    assert _cls(rules, pistol)["hold_class"] == "one_hand"


def test_hold_and_kind_tables_cover_every_archetype(rules):
    assert rules["hold_by_archetype"] == HOLD
    from synty_inventory.weapons import ARCHETYPE_KIND

    assert dict(ARCHETYPE_KIND) == KIND


# --- AC5 ---------------------------------------------------------------------------------------------------

AC5_COMBOS = [
    ("military", "modern", "modern"),
    ("modern_city", "modern", "modern"),
    ("post_apoc", "near_future", "modern"),
    ("nature", "modern", "modern"),
    ("horror", "modern", "modern"),
    ("horror", "near_future", "scifi"),
    ("horror", "far_future", "scifi"),
    ("scifi_city", "far_future", "scifi"),
    ("scifi_frontier", "far_future", "scifi"),
    ("space", "far_future", "scifi"),
    ("fantasy", "medieval", "fantasy"),
    ("western", "historical", "western"),
]


@pytest.mark.parametrize("setting,era,genre", AC5_COMBOS)
def test_ac5_genre_for_pack_table(setting, era, genre):
    assert genre_for_pack(setting, era) == genre


def test_ac5_twelve_combinations_and_undetermined():
    assert len(AC5_COMBOS) == 12
    assert genre_for_pack("generic", "modern") is None
    assert genre_for_pack("generic", None) is None
    assert genre_for_pack("never_heard_of_it", "modern") is None
    assert genre_for_pack(None, None) is None
    assert genre_for_pack("horror", "medieval") is None


def test_ac5_missing_pack_falls_back_to_the_archetype(rules, built):
    directory, _ = built
    generic = [w for w in directory["weapons"] if w["pack"] == "FAKE_Generic"]
    assert len(generic) >= 3
    for rec in generic:
        assert rec["genre_source"] == "archetype"
    assert all(w["genre_source"] == "pack" for w in directory["weapons"] if w["pack"] == "FAKE_Modern")
    pistol = _cls(rules, {"id": "SM_Wep_Pistol_01", "type": "weapon"}, setting=None)
    assert (pistol["genre"], pistol["genre_source"]) == ("modern", "archetype")
    sword = _cls(rules, {"id": "SM_Wep_Sword_01", "type": "weapon"}, setting=None)
    assert (sword["genre"], sword["genre_source"]) == ("fantasy", "archetype")
    # the pack decides over the archetype: a pistol in a fantasy pack is fantasy (NB-12)
    fantasy = _cls(rules, {"id": "SM_Wep_Pistol_01", "type": "weapon"}, setting={"setting": "fantasy", "era": "medieval"})
    assert (fantasy["genre"], fantasy["genre_source"]) == ("fantasy", "pack")


def test_ac5_a_pack_missing_from_settings_warns_in_the_report(tmp_path):
    from synty_inventory.weapons.directory import build_directory_report

    cdir = wfx.make_catalogs_dir(tmp_path)
    _, _, report = build_directory_report(cdir, rules=load_rules(), overrides=empty_overrides(),
                                          pack_settings=wfx.pack_settings())
    assert any("FAKE_Generic" in w for w in report["warnings"])
    assert not any("FAKE_Modern" in w for w in report["warnings"])


# --- AC6 ---------------------------------------------------------------------------------------------------

def test_ac6_tokenizer_examples(rules):
    assert tokenize_id("SM_Wep_SubMGun_Lite_01", rules) == ["sm", "wep", "smg", "lite"]
    assert tokenize_id("Wep_RecurveBow_01", rules) == ["wep", "recurve", "bow"]
    assert tokenize_id("Nail_Gun_02", rules) == ["utilgun"]
    assert tokenize_id("SM_Wep_Cannon_Ball_01", rules) == ["sm", "wep", "cannonball"]
    assert tokenize_id("Preset_Sword_03", rules) == ["preset", "sword"]


def test_ac6_tokenizer_defaults_to_the_shipped_rules():
    assert tokenize_id("SM_Wep_SubMGun_Lite_01") == ["sm", "wep", "smg", "lite"]


def test_ac6_digits_are_dropped_and_case_is_folded(rules):
    assert tokenize_id("SM_WEP_PISTOL_007", rules) == ["sm", "wep", "pistol"]
    assert tokenize_id("sm_wep_pistol_01", rules) == ["sm", "wep", "pistol"]
    assert tokenize_id("SM_Wep_Pistol_01_Clean", rules) == ["sm", "wep", "pistol", "clean"]


def test_family_strips_numbering_and_suffix_tokens(rules):
    assert family_of("SM_Wep_Pistol_Clean_01", rules) == "sm_wep_pistol"
    assert family_of("SM_Wep_Shield_Rigged_12", rules) == "sm_wep_shield"
    assert family_of("Preset_Sword_03", rules) == "preset_sword"
    assert family_of("SM_Wep_Pistol_01", rules) == family_of("SM_Wep_Pistol_02", rules)


# --- confidence --------------------------------------------------------------------------------------------

def test_confidence_bounds_and_name_token_cap(built):
    directory, _ = built
    for rec in directory["weapons"]:
        conf = rec["review"]["confidence"]
        assert 0.05 <= conf <= 0.99, rec["id"]
        assert conf == round(conf, 2)
        if rec["review"]["candidate_source"] == "name_token":
            assert conf <= 0.6


def test_unknown_archetype_is_kept_and_flagged_for_review(rules):
    out = _cls(rules, {"id": "SM_Wep_Zorb_01", "type": "weapon"})
    assert out["archetype"] == "unknown"
    assert out["kind"] is None
    assert out["role"] == "whole"
    assert out["confidence"] == 0.2
    assert "unknown_archetype" in out["reasons"] and "low_confidence" in out["reasons"]
    assert out["hold_class"] == "none"


def test_ambiguity_lowers_confidence(rules):
    # SubMGun carries a second known archetype alias: one clean match must score higher than an ambiguous id
    clean = _cls(rules, {"id": "SM_Wep_Pistol_01", "type": "weapon"})
    ambiguous = _cls(rules, {"id": "SM_Wep_Pistol_Sword_01", "type": "weapon"})
    assert ambiguous["confidence"] < clean["confidence"]


# --- AC9 / rule hygiene ------------------------------------------------------------------------------------

def test_ac9_every_rule_is_the_first_match_of_a_fixture_id(built, rules):
    directory, _ = built
    names = [r["name"] for r in rules["rules"]]
    assert len(names) >= 50 and len(set(names)) == len(names)
    hit = {w["review"]["matched_rule"] for w in directory["weapons"]}
    assert [n for n in names if n not in hit] == []


def test_ac9_no_shipped_table_has_a_shadowed_entry(rules):
    assert shadowed_rules(rules) == []
    assert validate_rules(rules) == []


def test_ac9_static_shadow_analysis_finds_planted_shadows(rules):
    dup = copy.deepcopy(rules)
    dup["rules"].insert(1, copy.deepcopy(dup["rules"][0]))
    rows = shadowed_rules(dup)
    assert any(r["table"] == "rules" and r["shadowed_by"] == dup["rules"][0]["name"] for r in rows)

    broad = copy.deepcopy(rules)
    broad["rules"].insert(0, {"name": "broad_gun", "match": {"tokens_any": ["pistol", "sword"]},
                              "set": {"role": "whole", "archetype": "pistol"}, "confidence": 0.5})
    narrow_names = {r["rule"] for r in shadowed_rules(broad)}
    assert "pistol" in narrow_names  # fully covered by the broad rule above it

    ex = copy.deepcopy(rules)
    ex["candidates"]["exclude"].insert(1, copy.deepcopy(ex["candidates"]["exclude"][0]))
    assert any(r["table"] == "candidates.exclude" for r in shadowed_rules(ex))
    inc = copy.deepcopy(rules)
    inc["candidates"]["include"].insert(1, copy.deepcopy(inc["candidates"]["include"][0]))
    assert any(r["table"] == "candidates.include" for r in shadowed_rules(inc))


def _cfg(tmp_path):
    cfg = tmp_path / "config.yaml"
    catalogs = tmp_path / "catalogs"
    catalogs.mkdir(exist_ok=True)
    cfg.write_text(
        "\n".join([f'unity_root: "{tmp_path.as_posix()}/unity"', f'extracted_root: "{tmp_path.as_posix()}/extracted"',
                   f'catalogs: "{catalogs.as_posix()}"']) + "\n", encoding="utf-8")
    return cfg


def test_ac9_validate_exits_6_on_shadowed_rules(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("SYNTI_CONFIG", raising=False)
    bad = load_rules()
    bad["rules"].insert(1, copy.deepcopy(bad["rules"][0]))
    import synty_inventory.weapons.rules as rules_mod

    monkeypatch.setattr(rules_mod, "load_rules", lambda path=None: bad)
    capsys.readouterr()
    code = main(["--config", str(_cfg(tmp_path)), "weapons", "validate"])
    out = json.loads(capsys.readouterr().out)
    assert code == 6
    assert out["ok"] is False
    assert out["rules"] == "shadowed"
    assert out["shadowed_rules"]


def test_validate_passes_on_the_shipped_rules(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("SYNTI_CONFIG", raising=False)
    capsys.readouterr()
    code = main(["--config", str(_cfg(tmp_path)), "weapons", "validate"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0, out
    assert out["ok"] is True and out["rules"] == "ok" and out["overrides"] == "ok"


def test_rule_loader_rejects_alias_variants_and_unknown_enums(rules):
    bad = copy.deepcopy(rules)
    bad["rules"][0]["match"] = {"tokens_any": ["handgun"]}  # alias variant of "pistol": could never match
    assert any("alias" in e for e in validate_rules(bad))

    bad = copy.deepcopy(rules)
    bad["rules"][0]["set"]["archetype"] = "blaster_rifle"
    assert validate_rules(bad)

    bad = copy.deepcopy(rules)
    bad["rules"][0]["confidence"] = 1.5
    assert validate_rules(bad)

    bad = copy.deepcopy(rules)
    bad["hold_by_archetype"]["pistol"] = "two_hand"
    assert validate_rules(bad)

    bad = copy.deepcopy(rules)
    del bad["rules"]
    assert validate_rules(bad)
    assert validate_rules("not a mapping")


def test_load_rules_raises_schema_error_naming_every_problem(tmp_path, rules):
    doc = copy.deepcopy(rules)
    doc["rules"][0]["set"]["archetype"] = "blaster_rifle"
    doc["rules"][1]["confidence"] = 7
    path = tmp_path / "bad_rules.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(SchemaError) as exc:
        load_rules(path)
    assert exc.value.code == 6
    assert "blaster_rifle" in str(exc.value)


def test_rules_file_is_lf_and_versioned():
    path = Path(__file__).resolve().parents[1] / "src" / "synty_inventory" / "data" / "weapon_rules.yaml"
    body = path.read_bytes().replace(bytes([13, 10]), bytes([10]))  # an autocrlf checkout holds CRLF
    assert 13 not in body  # no stray CR
    assert yaml.safe_load(body.decode("utf-8"))["version"] == 1
