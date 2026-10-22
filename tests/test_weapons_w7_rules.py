"""Weapon directory W7 slice 1: scenery / furniture excludes, vehicle attachment rules, aliases and the two new optional
rules keys (docs/weapon_directory.md 3.4.1 PATCH W7, 4.4; AC50-AC53, AC9).

Every id and expectation is a literal in tests/fixtures/weapons/w7_cases.py. Each new entry carries a mutation proof that
stays in the suite: the entry is removed from a deep copy of the loaded rules and its fixture id must then classify
differently, which also proves the id really exercises the entry and that no entry is shadowed.
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest
import yaml

_FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w7_cases", _FIX / "w7_cases.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)

from synty_inventory.weapons import SchemaError  # noqa: E402
from synty_inventory.weapons.candidates import evaluate_candidate  # noqa: E402
from synty_inventory.weapons.classify import classify, tokenize_id  # noqa: E402
from synty_inventory.weapons.overrides import empty_overrides  # noqa: E402
from synty_inventory.weapons.rules import (  # noqa: E402
    head_lead_tokens,
    icon_albedo_entries,
    load_rules,
    shadowed_rules,
    validate_rules,
)


@pytest.fixture(scope="module")
def rules():
    return load_rules()


def ev(rules, asset_id):
    """The outcome for an id as the catalog would give it: SM_Wep_* carry the weapon type, every other id only a name."""
    asset = {"id": asset_id, **({"type": "weapon"} if asset_id.startswith("SM_Wep_") else {})}
    return evaluate_candidate(asset, "FAKE_Pack", rules)


def cls(rules, asset_id):
    return classify({"id": asset_id, "type": "weapon"}, "FAKE_Pack", rules, empty_overrides(), None)


def without_exclude(rules, name):
    out = copy.deepcopy(rules)
    table = out["candidates"]["exclude"]
    kept = [r for r in table if r["name"] != name]
    assert len(kept) == len(table) - 1, name
    out["candidates"]["exclude"] = kept
    return out


def without_rule(rules, name):
    out = copy.deepcopy(rules)
    kept = [r for r in out["rules"] if r["name"] != name]
    assert len(kept) == len(out["rules"]) - 1, name
    out["rules"] = kept
    return out


def without_alias(rules, target, variant):
    out = copy.deepcopy(rules)
    assert variant in out["token_aliases"][target], (target, variant)
    out["token_aliases"][target] = [v for v in out["token_aliases"][target] if v != variant]
    return out


# --- tables ----------------------------------------------------------------------------------------------------------


def test_the_shipped_tables_hold_the_w7_entries_in_order_and_are_not_shadowed(rules):
    names = [r["name"] for r in rules["candidates"]["exclude"]]
    assert names[-len(C.W7_EXCLUDES):] == list(C.W7_EXCLUDES)
    assert names.index("strip_club") < names.index("bld_env_prefix")  # SM_Bld_StripClub_* is named for the club
    rule_names = [r["name"] for r in rules["rules"]]
    assert rule_names.index("part_misc") < rule_names.index("part_attach") < rule_names.index("part_melee")
    assert rule_names.index("emplaced_cannon") + 1 == rule_names.index("emplaced_vehicle")
    assert shadowed_rules(rules) == [] and validate_rules(rules) == []


def test_every_w7_exclude_has_a_fixture_id(rules):
    assert {c[0] for c in C.EXCLUDE_CASES} == set(C.W7_EXCLUDES)


# --- AC50 / AC51: excludes -------------------------------------------------------------------------------------------


@pytest.mark.parametrize("entry,asset_id,reason,_after", C.EXCLUDE_CASES)
def test_ac50_ac51_the_id_is_excluded_by_its_entry_first(rules, entry, asset_id, reason, _after):
    out = ev(rules, asset_id)
    assert out["candidate"] is True and out["accepted"] is False
    assert (out["matched"], out["reason"]) == (entry, reason)


@pytest.mark.parametrize("entry,asset_id,reason,after", C.EXCLUDE_CASES)
def test_ac50_ac51_removing_the_entry_changes_the_outcome_of_its_id(rules, entry, asset_id, reason, after):
    out = ev(without_exclude(rules, entry), asset_id)
    assert out["candidate"] is True  # still a weapon-noun candidate: only the exclusion went
    if after == "accepted":
        assert out["accepted"] is True and out["matched"] != entry
    else:
        assert out["accepted"] is False and out["matched"] == after


def test_ac50_removing_strip_club_makes_the_prop_a_club_and_both_entries_make_the_building_one(rules):
    no_club = without_exclude(rules, "strip_club")
    assert ev(no_club, "SM_Prop_StripClub_01")["accepted"] is True
    assert cls(no_club, "SM_Prop_StripClub_01")["archetype"] == "club"
    both = without_exclude(no_club, "bld_env_prefix")
    assert ev(both, "SM_Bld_StripClub_01")["accepted"] is True
    assert cls(both, "SM_Bld_StripClub_01")["archetype"] == "club"


@pytest.mark.parametrize("asset_id,rule", C.KEEP_CASES)
def test_ac50_ac51_counter_cases_stay_candidates(rules, asset_id, rule):
    out = ev(rules, asset_id)
    assert out["candidate"] is True and out["accepted"] is True, out
    assert cls(rules, asset_id)["matched_rule"] == rule


def test_ac50_the_club_ids_stay_club_and_ac51_the_sign_shield_stays_a_shield(rules):
    assert [cls(rules, i)["archetype"] for i in ("SM_Wep_Club_01", "SM_Prop_Club_01")] == ["club", "club"]
    assert cls(rules, "SM_Wep_Sign_Shield_01")["archetype"] == "shield"
    assert cls(rules, "SM_Prop_Crate_Bullets_01")["role"] == "ammo"
    assert cls(rules, "SM_Wep_Pistol_Case_01")["archetype"] == "pistol"


@pytest.mark.parametrize("entry,asset_id", C.OLDER_ENTRY_STILL_WINS)
def test_older_exclude_entries_keep_the_ids_they_already_caught(rules, entry, asset_id):
    assert ev(rules, asset_id)["matched"] == entry


@pytest.mark.parametrize("asset_id", [i for i, _ in C.KEEP_CASES if i.startswith("SM_Wep_")])
def test_no_sm_wep_id_is_taken_by_the_w7_excludes(rules, asset_id):
    out = ev(rules, asset_id)
    assert out["accepted"] is True and out["reason"] is None


# --- AC52: vehicle attachments / vehicle guns -------------------------------------------------------------------------


@pytest.mark.parametrize("rule,asset_id,role,archetype,slot", C.RULE_CASES)
def test_ac52_the_new_rules_decide_their_ids(rules, rule, asset_id, role, archetype, slot):
    out = cls(rules, asset_id)
    assert out["matched_rule"] == rule
    assert (out["role"], out["archetype"]) == (role, archetype)
    if slot is not None:
        assert out["component"]["slot"] == slot
    if role == "emplaced":
        assert out["kind"] == "ranged"


@pytest.mark.parametrize("rule,asset_id,role,archetype,slot", C.RULE_CASES)
def test_ac52_removing_the_rule_changes_its_id(rules, rule, asset_id, role, archetype, slot):
    before = cls(rules, asset_id)
    after = cls(without_rule(rules, rule), asset_id)
    assert after["matched_rule"] != rule
    assert (after["role"], after["archetype"], after["matched_rule"]) != (before["role"], before["archetype"], rule)


@pytest.mark.parametrize("asset_id,rule,role,archetype", C.RULE_KEEP_CASES)
def test_ac52_ammo_and_a_vehicle_cannon_stay_where_they_were(rules, asset_id, rule, role, archetype):
    out = cls(rules, asset_id)
    assert (out["matched_rule"], out["role"], out["archetype"]) == (rule, role, archetype)


def test_ac52_a_vehicle_cannon_is_not_counted_as_ambiguous(rules):
    """emplaced_vehicle also names SM_Veh_*Cannon* by its `veh` token; it must not cost the cannon a confidence step."""
    plain = classify({"id": "SM_Veh_Cannon_01", "type": "weapon"}, "FAKE_Pack", rules, empty_overrides(), None)
    assert plain["confidence"] == 0.85


# --- AC53: aliases ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("target,variant,asset_id,role,archetype", C.ALIAS_CASES)
def test_ac53_the_alias_resolves_the_spelling(rules, target, variant, asset_id, role, archetype):
    assert target in tokenize_id(asset_id, rules)
    out = cls(rules, asset_id)
    assert (out["role"], out["archetype"]) == (role, archetype)


@pytest.mark.parametrize("target,variant,asset_id,role,archetype", C.ALIAS_CASES)
def test_ac53_without_its_alias_the_id_no_longer_classifies_the_same(rules, target, variant, asset_id, role, archetype):
    bare = without_alias(rules, target, variant)
    assert target not in tokenize_id(asset_id, bare)
    out = cls(bare, asset_id)
    assert (out["role"], out["archetype"]) != (role, archetype)


def test_ac53_pickaxe_is_the_token_the_rest_of_the_file_already_uses(rules):
    assert "pickaxe" in rules["candidates"]["nouns"]
    assert next(r for r in rules["rules"] if r["name"] == "tool")["match"]["tokens_any"].count("pickaxe") == 1


# --- the two optional top-level keys ---------------------------------------------------------------------------------


def test_the_shipped_keys_carry_the_w7_values(rules):
    assert list(head_lead_tokens(rules)) != [] and set(head_lead_tokens(rules)) == set(C.HEAD_LEAD_TOKENS)
    assert icon_albedo_entries(rules) == [C.ALBEDO_ENTRY]


def test_both_keys_default_to_empty_when_absent(rules):
    doc = copy.deepcopy(rules)
    del doc["head_lead_tokens"], doc["icon_albedo_from_material"]
    assert validate_rules(doc) == []
    assert head_lead_tokens(doc) == frozenset() and icon_albedo_entries(doc) == []


def test_empty_values_are_valid(rules):
    doc = copy.deepcopy(rules)
    doc["head_lead_tokens"], doc["icon_albedo_from_material"] = [], []
    assert validate_rules(doc) == []


@pytest.mark.parametrize("bad", ["spade", ["Spade"], [3], [""], {"spade": 1}, None])
def test_head_lead_tokens_rejects_bad_values_naming_the_key(rules, bad):
    doc = copy.deepcopy(rules)
    doc["head_lead_tokens"] = bad
    errors = validate_rules(doc)
    assert errors and all(e.startswith("head_lead_tokens") for e in errors)


@pytest.mark.parametrize("mutate,needle", [
    (lambda d: d.__setitem__("icon_albedo_from_material", {"name": "x"}), "icon_albedo_from_material"),
    (lambda d: d["icon_albedo_from_material"].__setitem__(0, "x"), "icon_albedo_from_material[0]"),
    (lambda d: d["icon_albedo_from_material"][0].__delitem__("name"), "icon_albedo_from_material[0].name"),
    (lambda d: d["icon_albedo_from_material"][0].__setitem__("name", 4), "icon_albedo_from_material[0].name"),
    (lambda d: d["icon_albedo_from_material"][0].__delitem__("id_regex"), "icon_albedo_from_material[0].id_regex"),
    (lambda d: d["icon_albedo_from_material"][0].__setitem__("id_regex", "("), "icon_albedo_from_material[0].id_regex"),
    (lambda d: d["icon_albedo_from_material"][0].__setitem__("packs_any", "POLYGON_Viking_Realm"),
     "icon_albedo_from_material[0].packs_any"),
    (lambda d: d["icon_albedo_from_material"][0].__setitem__("packs_any", []),
     "icon_albedo_from_material[0].packs_any"),
    (lambda d: d["icon_albedo_from_material"][0].__setitem__("extra", 1), "icon_albedo_from_material[0].extra"),
    (lambda d: d["icon_albedo_from_material"].append(dict(d["icon_albedo_from_material"][0])),
     "icon_albedo_from_material[1].name"),
])
def test_icon_albedo_from_material_rejects_bad_values_naming_the_key(rules, mutate, needle):
    doc = copy.deepcopy(rules)
    mutate(doc)
    errors = validate_rules(doc)
    assert any(needle in e for e in errors), errors
    assert all(e.startswith("icon_albedo_from_material") for e in errors)


def test_icon_albedo_packs_any_is_optional(rules):
    doc = copy.deepcopy(rules)
    del doc["icon_albedo_from_material"][0]["packs_any"]
    assert validate_rules(doc) == []


def test_the_loader_exits_6_on_a_bad_new_key(tmp_path, rules):
    for key, value in (("head_lead_tokens", ["Spade"]), ("icon_albedo_from_material", [{"name": "x"}])):
        doc = copy.deepcopy(rules)
        doc[key] = value
        path = tmp_path / f"bad_{key}.yaml"
        path.write_text(yaml.safe_dump(doc), encoding="utf-8")
        with pytest.raises(SchemaError) as exc:
            load_rules(path)
        assert exc.value.code == 6 and key in str(exc.value)
