"""Weapon directory W1: candidate selection and exclusion (docs/weapon_directory.md 3.4.1; AC2, AC3, AC8, INV-3).

Fixtures are synthetic (tests/fixtures/weapons, written by make_catalogs.py). Every threshold and closed list in
this file is a literal, never an import of the constant under test.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("wfx", Path(__file__).parent / "fixtures" / "weapons" / "wfx.py")
wfx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wfx)

from synty_inventory.weapons.candidates import catalog_signals, evaluate_candidate, select_candidates  # noqa: E402
from synty_inventory.weapons.rules import load_rules  # noqa: E402

EXCLUDE_REASONS = ("nonplaceable", "ui", "fx", "character_attachment", "mech_attachment", "scenery", "tool_prop",
                   "override")

# the survey false-positive families of spec 3.4.1: one exclude entry each
FAMILIES = (
    "chr_attach", "mech_weapon_attach", "ui_kind", "ui_crosshair", "fx_prefix", "fx_kind", "ribbon_bow",
    "road_arrow", "mine_tunnel", "club_awning", "windshield", "face_shield", "weapon_rack_sign", "grass_blade",
    "torch", "nonwep_tool_prop",
)
INCLUDES = ("veh_cannon", "prop_item_noun", "nonmesh_noun", "compound_substring")


@pytest.fixture(scope="module")
def rules():
    return load_rules()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    cdir = wfx.make_catalogs_dir(tmp_path_factory.mktemp("cand"))
    directory, excluded = wfx.build(cdir)
    return directory, excluded


def test_ac2_traps_are_excluded_with_a_closed_reason(built):
    directory, excluded = built
    traps = wfx.expected()["traps"]
    assert len(traps) >= 20
    record_ids = {w["id"] for w in directory["weapons"]}
    rows = {e["id"]: e for e in excluded["excluded"]}
    for trap_id, want in sorted(traps.items()):
        assert trap_id not in record_ids, f"{trap_id} must not be a weapon record"
        assert trap_id in rows, f"{trap_id} missing from excluded.json"
        assert rows[trap_id]["reason"] in EXCLUDE_REASONS
        assert rows[trap_id]["reason"] == want["reason"], trap_id
        assert rows[trap_id]["matched"] == want["entry"], trap_id


def test_ac8_every_false_positive_family_has_a_trap(built):
    _, excluded = built
    traps = wfx.expected()["traps"]
    trap_entries = {t["entry"] for t in traps.values()}
    missing = [f for f in FAMILIES if f not in trap_entries]
    assert missing == []
    rows = {e["id"]: e for e in excluded["excluded"]}
    for family in FAMILIES:
        ids = [i for i, t in traps.items() if t["entry"] == family]
        assert ids and all(i in rows for i in ids), family


def test_ac3_name_token_candidates_are_capped_and_flagged(built):
    directory, _ = built
    exp = wfx.expected()["weapons"]
    token_ids = sorted(i for i, w in exp.items() if w["source"] == "name_token")
    assert len(token_ids) >= 4
    by_id = wfx.records_by_id(directory)
    for wid in token_ids:
        rec = by_id[wid]
        assert rec["review"]["candidate_source"] == "name_token"
        assert rec["review"]["confidence"] <= 0.6
        assert "token_candidate" in rec["flags"]
    # and nothing the catalog called a weapon is labelled name_token
    for rec in directory["weapons"]:
        if exp[rec["id"]]["source"] == "catalog":
            assert rec["review"]["candidate_source"] == "catalog"
            assert "token_candidate" not in rec["flags"]


def test_assets_nothing_matched_get_no_row(built):
    directory, excluded = built
    not_candidates = wfx.expected()["not_candidates"]
    assert len(not_candidates) >= 6
    seen = {w["id"] for w in directory["weapons"]} | {e["id"] for e in excluded["excluded"]}
    for wid in not_candidates:
        assert wid not in seen


def test_inv3_records_plus_excluded_equal_candidates_per_pack(built):
    directory, excluded = built
    for pack in directory["packs"]:
        recs = [w for w in directory["weapons"] if w["pack"] == pack["pack"]]
        excl = [e for e in excluded["excluded"] if e["id"].split("/", 1)[0] == pack["pack"]]
        assert pack["records"] == len(recs)
        assert pack["excluded"] == len(excl)
        assert pack["candidates"] == len(recs) + len(excl)
        assert pack["candidates"] > 0
        assert pack["asset_count"] >= pack["candidates"]


def test_every_include_entry_is_the_first_match_of_a_fixture_asset(rules):
    assert [r["name"] for r in rules["candidates"]["include"]] == list(INCLUDES)
    hit = set()
    for pack_id, asset in wfx.catalog_assets().values():
        ev = evaluate_candidate(asset, pack_id, rules)
        if ev["include"]:
            hit.add(ev["include"])
    assert hit == set(INCLUDES)


def test_every_exclude_entry_is_the_first_match_of_a_fixture_asset(built, rules):
    _, excluded = built
    assert [r["name"] for r in rules["candidates"]["exclude"]] == list(FAMILIES)
    hit = {e["matched"] for e in excluded["excluded"]}
    assert set(FAMILIES) <= hit


@pytest.mark.parametrize("signal_field", ["type", "semantic_role"])
def test_one_catalog_signal_is_enough(rules, signal_field):
    asset = {"id": "SM_Zorb_Thing_01", signal_field: "weapon", "placeable": True}
    assert catalog_signals(asset) == [signal_field]
    assert select_candidates(asset, "FAKE_Pack", rules) == (True, "catalog", None)


def test_gear_kind_signal_alone_is_enough(rules):
    asset = {"id": "SM_Zorb_Thing_01", "gear": {"kind": "weapon"}, "placeable": True}
    assert catalog_signals(asset) == ["gear.kind"]
    assert select_candidates(asset, "FAKE_Pack", rules) == (True, "catalog", None)


def test_no_signal_and_no_include_is_not_a_candidate(rules):
    asset = {"id": "SM_Zorb_Thing_01", "type": "prop", "semantic_role": "exterior_prop", "gear": {"kind": "tool"}}
    assert catalog_signals(asset) == []
    out = evaluate_candidate(asset, "FAKE_Pack", rules)
    assert out["candidate"] is False
    assert select_candidates(asset, "FAKE_Pack", rules) == (False, None, None)


def test_vlm_written_tags_and_names_are_never_read(rules):
    asset = {"id": "SM_Zorb_Thing_01", "type": "prop", "tags": ["weapon", "sword"], "name": "Sword",
             "description": "a big sword", "semantic_role": "exterior_prop"}
    assert evaluate_candidate(asset, "FAKE_Pack", rules)["candidate"] is False


def test_name_pattern_exclude_beats_nonplaceable(rules):
    torch = {"id": "SM_Wep_Torch_09", "type": "weapon", "placeable": False}
    assert select_candidates(torch, "FAKE_Pack", rules) == (False, "catalog", "tool_prop")
    plain = {"id": "SM_Wep_Sword_09", "type": "weapon", "placeable": False}
    assert select_candidates(plain, "FAKE_Pack", rules) == (False, "catalog", "nonplaceable")


def test_exclude_table_is_first_match_wins(rules):
    # a Wep-prefixed pickaxe is a real improvised tool weapon: the prop-only exclude must not take it
    wep = {"id": "SM_Wep_Pickaxe_01", "type": "weapon", "placeable": True}
    assert select_candidates(wep, "FAKE_Pack", rules)[0] is True
    prop = {"id": "SM_Prop_Pickaxe_01", "type": "prop", "placeable": True}
    assert select_candidates(prop, "FAKE_Pack", rules) == (False, "name_token", "tool_prop")
