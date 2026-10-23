"""W8h-A: iron-sight classification (AC87; docs/weapon_attachments.md 3.3, amendment A2).

Synthetic ids only (``fixtures/weapons/w8h_world.py``). The expected slot/kind pairs are literals.
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("w8h_world", Path(__file__).parent / "fixtures" / "weapons" / "w8h_world.py")
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)

from synty_inventory.weapons import ATTACH_SLOTS  # noqa: E402
from synty_inventory.weapons.classify import attachment_reason, classify_attachment  # noqa: E402
from synty_inventory.weapons.rules import load_rules, validate_rules  # noqa: E402

PACK = "FAKE_SightCls"
SIDED = {  # asset id -> (slot, kind)
    "SM_Wep_IronSight_Front_01": ("sight_front", "other"),
    "SM_Wep_Ironsight_Front_Canted_01": ("sight_front", "canted"),
    "SM_Wep_Iron_Post_Sight_01": ("sight_front", "post"),
    "SM_Wep_Iron_Hooded_Front_Sight_01": ("sight_front", "hooded"),
    "SM_Wep_Ironsight_Rear_01": ("sight_rear", "other"),
    "SM_Wep_Ironsight_Rear_Ring_01": ("sight_rear", "aperture"),
    "SM_Wep_Ironsight_Rear_Notch_01": ("sight_rear", "notch"),
    "SM_Wep_Ironsight_Rear_Canted_01": ("sight_rear", "canted"),
}
UNSURE = ("SM_Wep_IronSight_01", "SM_Wep_IronSight_Front_Rear_01", "SM_Wep_Iron_Post_Rear_Sight_01")
BARE = "SM_Wep_Sight_Add_01"
COMP = {"slot": "misc", "fits": None}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    world = {PACK: {"parts": {aid: W.sight_part for aid in (*SIDED, *UNSURE, BARE)}}}
    directory, _, _, _ = W.build(tmp_path_factory.mktemp("w8h_cls"), world)
    return W.by_id(directory)


def rid(aid: str) -> str:
    return f"{PACK}/{aid}"


@pytest.mark.parametrize("aid", sorted(SIDED))
def test_ac87_a_sided_iron_sight_gets_its_slot_and_kind_and_no_unknown_kind_reason(built, aid):
    rec = built[rid(aid)]
    assert rec["role"] == "part"
    assert (rec["attachment"]["slot"], rec["attachment"]["kind"]) == SIDED[aid]
    assert "attach_kind_unknown" not in rec["review"]["reasons"] and "sight_side_unsure" not in rec["review"]["reasons"]


@pytest.mark.parametrize("aid", UNSURE)
def test_ac87_a_name_with_no_side_or_two_sides_is_null_with_the_reason_and_a_capped_confidence(built, aid):
    rec = built[rid(aid)]
    assert rec["role"] == "part" and rec["attachment"] is None
    assert "sight_side_unsure" in rec["review"]["reasons"] and "low_confidence" in rec["review"]["reasons"]
    assert rec["review"]["confidence"] <= 0.59


def test_ac87_a_bare_sight_add_part_is_null_without_the_reason(built):
    rec = built[rid(BARE)]
    assert rec["attachment"] is None and "sight_side_unsure" not in rec["review"]["reasons"]


def test_ac87_no_part_has_slot_optic_with_kind_iron_and_the_slot_list_is_seven_long(built):
    assert list(ATTACH_SLOTS) == ["optic", "muzzle", "underbarrel", "magazine", "laser_light", "sight_front", "sight_rear"]
    assert not [r for r in built.values() if (r.get("attachment") or {}).get("kind") == "iron"]
    assert all((r.get("set") or {}).get("kind") != "iron" for r in load_rules()["attachment_rules"]["rows"])  # no row sets kind iron


def test_ac87_the_table_reads_the_same_without_a_build():
    rules = load_rules()
    for aid, want in SIDED.items():
        got = classify_attachment(aid, PACK, "part", COMP, rules)
        assert (got["slot"], got["kind"]) == want, aid
    for aid in (*UNSURE, BARE):
        assert classify_attachment(aid, PACK, "part", COMP, rules) is None
    assert [attachment_reason(a, PACK, "part", COMP, rules) for a in UNSURE] == ["sight_side_unsure"] * 3
    assert attachment_reason(BARE, PACK, "part", COMP, rules) is None


def test_ac87_every_sight_row_of_the_table_is_the_first_match_of_a_part_here():
    rules = load_rules()
    used = set()
    for aid in (*SIDED, *UNSURE, "SM_Wep_IronSight_Front_Hood_01"):
        from synty_inventory.weapons.classify import _first_attachment_row

        used.add(_first_attachment_row(aid, PACK, "part", COMP, rules)["name"])
    rows = {r["name"] for r in rules["attachment_rules"]["rows"] if r["name"].startswith("sight_")}
    assert rows <= used, sorted(rows - used)


def test_ac87_component_is_untouched_on_every_part(built, tmp_path):
    bare_rules = W.sight_rules()
    del bare_rules["attachment_rules"]
    world = {PACK: {"parts": {aid: W.sight_part for aid in (*SIDED, *UNSURE, BARE)}}}
    directory, _, _, _ = W.build(tmp_path, world, rules=bare_rules)
    plain = W.by_id(directory)
    assert all(built[k]["component"] == plain[k]["component"] for k in built)


def test_ac87_an_override_on_an_unsure_part_gives_it_a_block_and_drops_the_reason(tmp_path):
    aid = rid("SM_Wep_IronSight_01")
    world = {PACK: {"parts": {"SM_Wep_IronSight_01": W.sight_part}}}
    ovr = W.overrides_doc(ids={aid: {"set": {"attachment_slot": "sight_front", "attachment_kind": "post"}}})
    directory, _, _, _ = W.build(tmp_path, world, overrides=ovr)
    rec = W.by_id(directory)[aid]
    assert (rec["attachment"]["slot"], rec["attachment"]["kind"]) == ("sight_front", "post")
    assert "sight_side_unsure" not in rec["review"]["reasons"]


def test_ac87_the_shipped_rules_validate_and_a_row_with_neither_set_nor_reason_is_refused():
    rules = copy.deepcopy(load_rules())
    assert validate_rules(rules) == []
    rules["attachment_rules"]["rows"].append({"name": "broken", "match": {"tokens_all": ["x"]}})
    assert validate_rules(rules)
