"""W8h-A: sight pairs (AC88; docs/weapon_attachments.md 3.5, INV-20).

Pack A holds the parts and the hosts (the hosts carry the family token `iron`, so the sights reach them as same_pack_fit: a probe
seat has no span, so an iron sight never reaches a host as cross_pack_fit, spec 5.1); pack B holds a front and a rear sight that
must never pair with pack A's. Every expected pair is a literal read off the ids.
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("w8h_world", Path(__file__).parent / "fixtures" / "weapons" / "w8h_world.py")
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)

from synty_inventory.weapons import SchemaError  # noqa: E402
from synty_inventory.weapons.overrides import validate_overrides  # noqa: E402
from synty_inventory.weapons.pairs import set_candidates  # noqa: E402
from synty_inventory.weapons.schema import pair_symmetry_errors, validate_directory  # noqa: E402

A_, B_ = "FAKE_SightA", "FAKE_SightB"
GENRES = {A_: "x", B_: "x"}
PARTS_A = ["SM_Wep_IronSight_Front_01", "SM_Wep_IronSight_Rear_01", "SM_Wep_IronSight_Front_Canted_01",
           "SM_Wep_IronSight_Rear_Canted_01", "SM_Wep_IronSight_Rear_02", "SM_Wep_Iron_Post_Sight_01"]
FRONT, REAR, FRONT_C, REAR_C, REAR_2, POST = (f"{A_}/{a}" for a in PARTS_A)
B_FRONT, B_REAR3 = f"{B_}/SM_Wep_IronSight_Front_01", f"{B_}/SM_Wep_IronSight_Rear_03"
BOX, HALF = f"{A_}/SM_Wep_Iron_Rifle_Box_01", f"{A_}/SM_Wep_Iron_Rifle_Half_01"


def world(extra_a=()):
    parts_a = {a: W.sight_part for a in (*PARTS_A, *extra_a)}
    hosts = {n: W.host_node(n, W.box_rifle()) for n in ("SM_Wep_Iron_Rifle_Box_01", "SM_Wep_Iron_Rifle_Half_01")}
    return {
        A_: {"parts": parts_a, "hosts": hosts},
        B_: {"parts": {"SM_Wep_IronSight_Front_01": W.sight_part, "SM_Wep_IronSight_Rear_03": W.sight_part}},
    }


def build(tmp_path, *, overrides=None, extra_a=(), w=None):
    return W.build(tmp_path, w or world(extra_a), rules=W.sight_rules(GENRES), overrides=overrides)[0]


def pairs_of(directory) -> dict:
    return {w["id"]: w["attachment"]["pair"] for w in directory["weapons"] if w.get("attachment")}


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    return build(tmp_path_factory.mktemp("w8h_pairs"))


def test_ac88_exactly_two_pairs_are_found_and_stored_on_both_members(base):
    got = pairs_of(base)
    assert {k: v for k, v in got.items() if v is not None} == {
        FRONT: REAR, REAR: FRONT, FRONT_C: REAR_C, REAR_C: FRONT_C}
    assert got[REAR_2] is None and got[POST] is None  # a lone rear (no Front_02) and a lone post (variant `post`)
    assert got[B_FRONT] is None and got[B_REAR3] is None  # another pack never pairs with pack A's Rear_01


def test_ac88_every_attachment_record_has_the_pair_key_and_it_is_null_outside_the_sight_slots(base):
    for rec in base["weapons"]:
        if rec.get("attachment") is not None:
            assert "pair" in rec["attachment"]
            if rec["attachment"]["slot"] not in ("sight_front", "sight_rear"):
                assert rec["attachment"]["pair"] is None


def test_ac88_the_symmetry_rule_is_checked_by_the_schema(base):
    by_id = {w["id"]: w for w in base["weapons"]}
    assert pair_symmetry_errors(by_id, "weapons") == []
    assert validate_directory(base) == []
    broken = copy.deepcopy(base)
    next(w for w in broken["weapons"] if w["id"] == REAR)["attachment"]["pair"] = None  # stored on one side only
    assert any("does not name it back" in e for e in validate_directory(broken))
    broken = copy.deepcopy(base)
    next(w for w in broken["weapons"] if w["id"] == FRONT)["attachment"]["pair"] = B_REAR3  # another pack, not named back
    assert validate_directory(broken)
    broken = copy.deepcopy(base)
    next(w for w in broken["weapons"] if w["id"] == POST)["attachment"]["pair"] = FRONT_C  # a front paired with a front
    assert validate_directory(broken)


def test_ac88_a_second_part_with_the_same_key_makes_both_of_that_side_pair_nothing(tmp_path):
    got = pairs_of(build(tmp_path, extra_a=("SM_Wep_IronSight_Front_A_01",)))  # `a` is noise: same pack, variant and number as Front_01
    assert got[FRONT] is None and got[REAR] is None and got[f"{A_}/SM_Wep_IronSight_Front_A_01"] is None
    assert got[FRONT_C] == REAR_C and got[REAR_C] == FRONT_C  # the other pair is untouched


def test_ac88_a_part_in_another_pack_never_pairs(tmp_path):
    w = {A_: {"parts": {"SM_Wep_IronSight_Rear_01": W.sight_part}}, B_: {"parts": {"SM_Wep_IronSight_Front_01": W.sight_part}}}
    assert set(pairs_of(build(tmp_path, w=w)).values()) == {None}


def test_ac88_the_pair_override_pairs_symmetrically_from_either_side(tmp_path):
    got = pairs_of(build(tmp_path, overrides=W.overrides_doc(ids={POST: {"pair": REAR_2}})))
    assert got[POST] == REAR_2 and got[REAR_2] == POST
    assert got[FRONT] == REAR and got[FRONT_C] == REAR_C  # the name pairs stay
    got = pairs_of(build(tmp_path / "other", overrides=W.overrides_doc(ids={REAR_2: {"pair": POST}})))
    assert got[POST] == REAR_2 and got[REAR_2] == POST


def test_ac88_a_null_pair_override_unpairs_both_members(tmp_path):
    got = pairs_of(build(tmp_path, overrides=W.overrides_doc(ids={FRONT: {"pair": None}})))
    assert got[FRONT] is None and got[REAR] is None and got[FRONT_C] == REAR_C


def test_ac88_an_override_that_repairs_a_member_frees_its_former_partner(tmp_path):
    got = pairs_of(build(tmp_path, overrides=W.overrides_doc(ids={FRONT: {"pair": REAR_2}})))
    assert got[FRONT] == REAR_2 and got[REAR_2] == FRONT and got[REAR] is None


@pytest.mark.parametrize("name, ids", [
    ("two fronts", {FRONT: {"pair": POST}}),
    ("two rears", {REAR: {"pair": REAR_2}}),
    ("two packs", {FRONT: {"pair": B_REAR3}}),
    ("an unknown id", {FRONT: {"pair": "FAKE_SightA/SM_Wep_IronSight_Rear_99"}}),
    ("not a sight", {FRONT: {"pair": BOX}}),
    ("disagreeing overrides", {FRONT: {"pair": REAR_2}, POST: {"pair": REAR_2}}),
])
def test_ac88_a_bad_pair_override_is_a_schema_error(tmp_path, name, ids):
    with pytest.raises(SchemaError):
        build(tmp_path, overrides=W.overrides_doc(ids=ids))


def test_ac88_the_pair_override_is_an_id_entry_key_with_a_string_or_null_value():
    assert validate_overrides(W.overrides_doc(ids={FRONT: {"pair": REAR}})) == []
    assert validate_overrides(W.overrides_doc(ids={FRONT: {"pair": None}})) == []
    assert validate_overrides(W.overrides_doc(ids={FRONT: {"pair": 5}}))
    assert validate_overrides(W.overrides_doc(globs={f"{A_}/*": {"pair": REAR}}))  # id-only, like `mounts`


def test_ac88_a_host_listed_by_both_members_has_a_set_candidate_and_one_listed_by_one_keeps_that_member_alone(tmp_path):
    ovr = W.overrides_doc(ids={HALF: {"mounts": {"sight_rear": {"source": "none"}}}})
    d = build(tmp_path, overrides=ovr)
    by = {w["id"]: w for w in d["weapons"]}
    listed = lambda pid: {e["host"]: e["tier"] for e in by[pid]["attachment"]["compatible_hosts"]}  # noqa: E731
    assert listed(FRONT).get(BOX) == "same_pack_fit" and listed(REAR).get(BOX) == "same_pack_fit"
    assert HALF in listed(FRONT) and HALF not in listed(REAR)  # the rear seat of HALF is switched off
    sets = [(c["front"], c["rear"], c["host"], c["tier"]) for c in set_candidates(d["weapons"])]
    assert (FRONT, REAR, BOX, "same_pack_fit") in sets and (FRONT_C, REAR_C, BOX, "same_pack_fit") in sets
    assert not [s for s in sets if s[2] == HALF]  # only one member lists HALF: that member mounts alone


def test_ac88_a_set_candidate_takes_the_lower_tier_of_its_two_members(tmp_path):
    ovr = W.overrides_doc(ids={REAR: {"compatible": {"add": [BOX]}}})
    d = build(tmp_path, overrides=ovr)
    by = {w["id"]: w for w in d["weapons"]}
    tiers = lambda pid: {e["host"]: e["tier"] for e in by[pid]["attachment"]["compatible_hosts"]}  # noqa: E731
    assert tiers(REAR)[BOX] == "override" and tiers(FRONT)[BOX] == "same_pack_fit"
    [cand] = [c for c in set_candidates(d["weapons"]) if (c["front"], c["host"]) == (FRONT, BOX)]
    assert cand["tier"] == "same_pack_fit"  # the front member's tier, the lower of override and same_pack_fit
