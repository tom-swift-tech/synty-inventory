"""Weapon directory W2: hints (spec 3.6, AC35). Synthetic records; every bound is a literal."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from synty_inventory.weapons.hints import build_group_stats, derive_hints
from synty_inventory.weapons.rules import load_rules
from synty_inventory.weapons.schema import validate_record

_FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("wfx", _FIX / "wfx.py")
wfx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wfx)


@pytest.fixture(scope="module")
def rules():
    return load_rules()


def rec(asset_id="SM_Wep_Rifle_01", archetype="rifle", role="whole", genre="modern", length=0.5, lateral=0.1,
        tris=1000, flags=(), geometry=True):
    geo = None
    if geometry:
        geo = {"length_m": length, "long_axis": "z", "triangles": tris,
               "bounds": {"min": [0, 0, 0], "max": [lateral, 0.05, length], "size": [lateral, 0.05, length]}}
    return {"asset_id": asset_id, "archetype": archetype, "role": role, "genre": genre, "flags": list(flags),
            "geometry": geo}


def hints(r, rules, stats=None):
    return derive_hints(r, stats or {}, rules)


# --- size_class ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("length,want", [
    (0.0, "tiny"), (0.1999, "tiny"), (0.20, "small"), (0.4499, "small"), (0.45, "medium"), (0.8999, "medium"),
    (0.90, "large"), (1.4999, "large"), (1.50, "huge"), (3.0, "huge"),
])
def test_size_class_boundaries_take_the_upper_class_on_the_cut(rules, length, want):
    assert hints(rec(length=length), rules)["size_class"] == want


def test_size_basis_is_raw_for_mech_scale_and_measured_otherwise(rules):
    assert hints(rec(), rules)["size_basis"] == "measured"
    assert hints(rec(flags=["mech_scale"]), rules)["size_basis"] == "raw"
    assert hints(rec(flags=["mech_scale"], length=2.0), rules)["size_class"] == "huge"


# --- inventory_cells ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("length,want_w", [
    (0.05, 1), (0.30, 1), (0.3001, 2), (0.60, 2), (0.9, 3), (0.91, 4), (1.5, 5), (1.8, 6), (2.5, 6), (9.0, 6),
])
def test_cells_wide_is_ceil_of_length_over_30cm_clamped_1_to_6(rules, length, want_w):
    assert hints(rec(length=length), rules)["inventory_cells"][0] == want_w


@pytest.mark.parametrize("lateral,want_h", [(0.05, 1), (0.1199, 1), (0.12, 2), (0.4, 2)])
def test_cells_tall_is_two_when_the_larger_lateral_extent_reaches_12cm(rules, lateral, want_h):
    assert hints(rec(lateral=lateral), rules)["inventory_cells"][1] == want_h


def test_the_long_axis_is_excluded_from_the_lateral_extent(rules):
    r = rec(length=1.0, lateral=0.05)
    r["geometry"]["long_axis"] = "x"
    r["geometry"]["bounds"]["size"] = [1.0, 0.05, 0.05]
    assert hints(r, rules)["inventory_cells"] == [4, 1]


# --- weight_class ---------------------------------------------------------------------------------------------

def test_weight_comes_from_the_archetype_table_and_shifts_one_step_for_huge_or_tiny(rules):
    assert hints(rec(archetype="rifle", length=0.7), rules)["weight_class"] == "medium"
    assert hints(rec(archetype="rifle", length=2.0), rules)["weight_class"] == "heavy"  # huge: +1
    assert hints(rec(archetype="rifle", length=0.1), rules)["weight_class"] == "light"  # tiny: -1
    assert hints(rec(archetype="pistol", length=0.1), rules)["weight_class"] == "light"  # clamped at the bottom
    assert hints(rec(archetype="turret", length=2.0), rules)["weight_class"] == "very_heavy"  # clamped at the top
    assert hints(rec(archetype="hammer", length=2.0), rules)["weight_class"] == "very_heavy"


def test_weight_without_geometry_has_no_size_step(rules):
    assert hints(rec(geometry=False), rules)["weight_class"] == "medium"
    assert hints(rec(archetype="unknown", geometry=False), rules)["weight_class"] is None


# --- quality_tier ---------------------------------------------------------------------------------------------

def test_tier_is_the_archetype_base_with_up_and_down_tokens(rules):
    assert hints(rec("SM_Wep_Rifle_01"), rules)["quality_tier"] == 3
    assert hints(rec("SM_Wep_Rifle_Gold_01"), rules)["quality_tier"] == 4
    assert hints(rec("SM_Wep_Rifle_Rusty_01"), rules)["quality_tier"] == 2
    assert hints(rec("SM_Wep_Rifle_Gold_Rusty_01"), rules)["quality_tier"] == 3  # +1 -1
    assert hints(rec("SM_Wep_Rifle_Gold_Royal_01"), rules)["quality_tier"] == 4  # one up step however many tokens
    assert hints(rec("SM_Wep_Knife_Rusty_01", archetype="knife"), rules)["quality_tier"] == 1  # clamped low
    assert hints(rec("SM_Wep_Launcher_Elite_01", archetype="launcher"), rules)["quality_tier"] == 5  # clamped high


@pytest.mark.parametrize("role", ["part", "ammo", "carrier"])
def test_tier_is_null_for_non_weapon_roles(rules, role):
    assert hints(rec(role=role), rules)["quality_tier"] is None


def test_tier_is_null_for_an_unknown_archetype_but_present_for_a_geometry_less_known_one(rules):
    assert hints(rec(archetype="unknown"), rules)["quality_tier"] is None
    assert hints(rec(geometry=False), rules)["quality_tier"] == 3


def _group(n, tris_of, archetype="rifle", genre="modern"):
    return [rec(f"SM_Wep_Rifle_{i:02d}", archetype=archetype, genre=genre, tris=tris_of(i)) for i in range(n)]


def test_triangle_term_adds_one_above_p75_of_a_group_of_at_least_eight(rules):
    members = _group(8, lambda i: 1000 + 100 * i)  # 1000..1700; linear p75 = 1525
    stats = build_group_stats(members, rules)
    assert stats[("rifle", "modern")]["n"] == 8 and stats[("rifle", "modern")]["p75"] == 1525
    tiers = [hints(m, rules, stats)["quality_tier"] for m in members]
    assert tiers == [3, 3, 3, 3, 3, 3, 4, 4]  # 1600 and 1700 exceed 1525


def test_triangle_term_is_strictly_above_the_percentile(rules):
    members = _group(8, lambda i: 1000)  # every member sits exactly on p75
    stats = build_group_stats(members, rules)
    assert stats[("rifle", "modern")]["p75"] == 1000
    assert {hints(m, rules, stats)["quality_tier"] for m in members} == {3}


def test_groups_under_eight_get_no_triangle_term(rules):
    members = _group(7, lambda i: 1000 * (i + 1))
    stats = build_group_stats(members, rules)
    assert stats == {}
    assert hints(members[-1], rules, stats)["quality_tier"] == 3


def test_groups_are_per_archetype_and_genre_and_skip_geometry_less_and_non_weapon_members(rules):
    members = _group(8, lambda i: 1000 + i) + _group(8, lambda i: 50, genre="fantasy")
    members += [rec("SM_Wep_X_01", role="part", tris=99999), rec("SM_Wep_Y_01", geometry=False)]
    stats = build_group_stats(members, rules)
    assert sorted(stats) == [("rifle", "fantasy"), ("rifle", "modern")]
    assert stats[("rifle", "modern")]["n"] == 8


def test_triangle_term_and_tokens_stack_and_clamp_at_five(rules):
    members = _group(8, lambda i: 1000 + i)
    members[7]["asset_id"] = "SM_Wep_Rifle_Elite_07"
    stats = build_group_stats(members, rules)
    assert hints(members[7], rules, stats)["quality_tier"] == 5  # 3 + token + triangles
    launchers = _group(8, lambda i: 1000 + i, archetype="launcher")
    stats = build_group_stats(launchers, rules)
    assert hints(launchers[7], rules, stats)["quality_tier"] == 5  # 5 + triangles clamps


# --- ammo_family ----------------------------------------------------------------------------------------------

def test_ammo_family_comes_from_the_archetype_table(rules):
    assert hints(rec(archetype="pistol"), rules)["ammo_family"] == "handgun"
    assert hints(rec(archetype="bow"), rules)["ammo_family"] == "arrow"
    assert hints(rec(archetype="sword"), rules)["ammo_family"] is None
    assert hints(rec(archetype="unknown"), rules)["ammo_family"] is None
    assert hints(rec(role="part"), rules)["ammo_family"] is None


def test_energy_token_overrides_the_family_only_when_the_archetype_already_has_one(rules):
    assert hints(rec("SM_Wep_Plasma_Rifle_01"), rules)["ammo_family"] == "energy"
    assert hints(rec("SM_Wep_Laser_Pistol_01", archetype="pistol"), rules)["ammo_family"] == "energy"
    assert hints(rec("SM_Wep_Plasma_Sword_01", archetype="sword"), rules)["ammo_family"] is None


# --- AC35: the strict schema ------------------------------------------------------------------------------------

def test_ac35_every_fixture_record_gets_hints_and_quality_tier_is_null_iff_the_rule_says(tmp_path):
    cat = wfx.make_catalogs_dir(tmp_path)
    directory, _ = wfx.build(cat, measure=False)
    assert directory["weapons"]
    for r in directory["weapons"]:
        h = r["hints"]
        assert set(h) == {"size_class", "size_basis", "inventory_cells", "weight_class", "quality_tier", "ammo_family"}
        null_tier = r["role"] in ("part", "ammo", "carrier") or r["archetype"] == "unknown"
        assert (h["quality_tier"] is None) == null_tier, r["id"]
        if h["quality_tier"] is not None:
            assert isinstance(h["quality_tier"], int) and not isinstance(h["quality_tier"], bool)
            assert 1 <= h["quality_tier"] <= 5
        assert r["geometry"] is None and h["size_class"] is None and h["inventory_cells"] is None
        assert r["provenance"]["hints"] == "rules"


def test_ac35_a_whole_weapon_with_null_geometry_and_an_integer_tier_is_schema_valid(tmp_path):
    cat = wfx.make_catalogs_dir(tmp_path)
    directory, _ = wfx.build(cat, measure=False)
    whole = next(r for r in directory["weapons"] if r["role"] == "whole" and r["archetype"] != "unknown")
    assert whole["geometry"] is None and isinstance(whole["hints"]["quality_tier"], int)
    assert validate_record(whole) == []


def test_ac35_the_schema_rejects_a_tier_on_a_non_weapon_and_a_missing_tier_on_a_weapon(tmp_path):
    cat = wfx.make_catalogs_dir(tmp_path)
    directory, _ = wfx.build(cat, measure=False)
    whole = next(r for r in directory["weapons"] if r["role"] == "whole" and r["archetype"] != "unknown")
    broken = {**whole, "hints": {**whole["hints"], "quality_tier": None}}
    assert validate_record(broken) != []
    part = next(r for r in directory["weapons"] if r["role"] in ("part", "ammo", "carrier"))
    broken = {**part, "hints": {**part["hints"], "quality_tier": 3}}
    assert validate_record(broken) != []
