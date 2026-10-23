"""W8l: the family-free slots of the same_pack_fit tier (docs/weapon_attachments.md 5.1 "A4"; AC106).

``attachment_rules.family_free_slots`` (sight_front, sight_rear, muzzle, underbarrel) names the slots whose same_pack_fit needs affinity but no
shared name token: a silencer or a foregrip names no gun. Pure ``compat.candidate`` cases first, then a built directory (pack FAKE_W8L:
a rifle and a pistol with no baked children, four ``Zulu`` parts that share no token with either). Every expected tier, score and signal
is a LITERAL worked out by hand (same pack 0.7 base, 0.1 off for a bad ring bore, no span bonus without a foot against a seat).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8h_world", FIX / "w8h_world.py")
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)

from synty_inventory.weapons import compat  # noqa: E402
from synty_inventory.weapons.rules import attachment_rules, load_rules  # noqa: E402

TABLES = attachment_rules(load_rules())
PARAMS = compat._params(TABLES)
AFFINITY = TABLES["attach_affinity"]
SAME, CROSS = "same_pack_fit", "cross_pack_fit"


def part(slot="muzzle", kind="suppressor", **kw):
    base = {"id": "P/Zulu_Part_01", "pack": "P", "slot": slot, "kind": kind, "flags": set(), "tokens": frozenset({"zulu"}),
            "foot_length_m": None, "mate_d_m": None, "setting": ("setting", "s")}
    return {**base, **kw}


def host(mounts, **kw):
    base = {"id": "P/Host_01", "pack": "P", "archetype": "rifle", "flags": set(), "mounts": mounts, "tokens": frozenset({"alpha"}),
            "setting": ("setting", "s")}
    return {**base, **kw}


def seat(**kw):
    base = {"source": "probe", "span_m": None, "span_source": None, "bore_d_m": None, "bore_source": None, "occupied_by": [], "reason": None}
    return {**base, **kw}


def none_seat(reason):
    return seat(source="none", reason=reason)


def cand(p, h, params=PARAMS):
    return compat.candidate(p, h, verdict=None, twin=False, affinity=AFFINITY, params=params)


# --- the table is the shipped literal list ---------------------------------------------------------------------------


def test_ac106_the_shipped_table_lists_the_four_slots():
    assert TABLES["family_free_slots"] == ["sight_front", "sight_rear", "muzzle", "underbarrel"]
    assert PARAMS["family_free_slots"] == {"sight_front", "sight_rear", "muzzle", "underbarrel"}


# --- the candidate tier ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("slot", "kind"), [("muzzle", "suppressor"), ("underbarrel", "foregrip")])
def test_ac106_a_muzzle_or_underbarrel_part_with_no_shared_token_is_a_same_pack_fit_when_the_seat_exists(slot, kind):
    got = cand(part(slot, kind), host({slot: seat()}))
    assert (got["tier"], got["listed"], got["score"]) == (SAME, True, 0.7)
    assert got["signals"] == ["affinity", "mount_available"]  # no family_overlap: there is no shared token


@pytest.mark.parametrize(("slot", "kind"), [("muzzle", "suppressor"), ("underbarrel", "foregrip")])
@pytest.mark.parametrize("reason", ["no_child_no_probe", "probe_unavailable"])
def test_ac106_without_a_seat_the_family_free_part_is_pending_not_compatible(slot, kind, reason):
    got = cand(part(slot, kind), host({slot: none_seat(reason)}))
    assert got == {"host": "P/Host_01", "tier": SAME, "listed": False}


@pytest.mark.parametrize(("slot", "kind"), [("muzzle", "suppressor"), ("underbarrel", "foregrip")])
def test_ac106_a_slot_disabled_host_gives_no_candidate(slot, kind):
    assert cand(part(slot, kind), host({slot: none_seat("slot_disabled")})) is None


@pytest.mark.parametrize(("slot", "kind"), [("magazine", "standard"), ("optic", "scope"), ("laser_light", "laser")])
def test_ac106_every_other_slot_still_needs_a_shared_token(slot, kind):
    assert cand(part(slot, kind), host({slot: seat()})) is None
    assert cand(part(slot, kind, tokens=frozenset({"alpha"})), host({slot: seat()}))["tier"] == SAME  # with the token it lists


@pytest.mark.parametrize("slot", ["sight_front", "sight_rear"])
def test_ac106_the_sight_slots_stay_family_free_through_the_table(slot):
    kind = "post" if slot == "sight_front" else "notch"
    got = cand(part(slot, kind), host({slot: seat()}))
    assert got["tier"] == SAME and "family_overlap" not in got["signals"]


def test_ac106_the_table_decides_not_a_hard_coded_list():
    muzzle_host = host({"muzzle": seat()})
    assert cand(part(), muzzle_host, {**PARAMS, "family_free_slots": frozenset()}) is None  # a muzzle out of the table needs a token again
    mag_host = host({"magazine": seat()})
    assert cand(part("magazine", "standard"), mag_host)  is None
    assert cand(part("magazine", "standard"), mag_host, {**PARAMS, "family_free_slots": frozenset({"magazine"})})["tier"] == SAME
    sight_host = host({"sight_front": seat()})
    assert cand(part("sight_front", "post"), sight_host, {**PARAMS, "family_free_slots": frozenset()}) is None


def test_ac106_affinity_still_applies_a_pistol_takes_no_foregrip():
    assert cand(part("underbarrel", "foregrip"), host({"underbarrel": seat()}, archetype="pistol")) is None


def test_ac106_a_cross_pack_part_is_unchanged_by_the_table():
    other = part("muzzle", "suppressor", pack="Q", mate_d_m=0.0130)
    ring = host({"muzzle": seat(bore_d_m=0.0130, bore_source="ring")})
    got = cand(other, ring)
    assert (got["tier"], got["score"]) == (CROSS, 0.5)  # the cross-pack base 0.4 plus 0.1 for a good ring bore: it needs the measured fit
    assert cand(part("muzzle", "suppressor", pack="Q"), host({"muzzle": seat()})) is None  # no bore evidence: no cross-pack candidate
    empty = {**PARAMS, "family_free_slots": frozenset()}
    assert got == cand(other, ring, empty) and cand(part("muzzle", "suppressor", pack="Q"), host({"muzzle": seat()}), empty) is None


def test_ac106_a_ring_bore_mismatch_still_marks_the_candidate_and_takes_0_1_off():
    ring = seat(bore_d_m=0.0130, bore_source="ring")
    got = cand(part(mate_d_m=0.0260), host({"muzzle": ring}))  # 0.0260 against a 0.0130 bore: 100 % off
    assert got["tier"] == SAME and got["score"] == 0.6
    assert got["signals"] == ["affinity", "bore_mismatch", "mount_available"]
    good = cand(part(mate_d_m=0.0130), host({"muzzle": ring}))
    assert good["score"] == 0.8 and "fit_bore" in good["signals"]


# --- a built directory -----------------------------------------------------------------------------------------------

PACK = "FAKE_W8L"
RIFLE, PISTOL = "SM_Wep_Rifle_Alpha_01", "SM_Wep_Pistol_Beta_01"
SILENCER, FOREGRIP, MAG, SCOPE = ("SM_Wep_Zulu_Silencer_01", "SM_Wep_Zulu_Foregrip_01", "SM_Wep_Zulu_Mag_01", "SM_Wep_Zulu_Scope_01")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    a = W.A
    world = {PACK: {
        "hosts": {RIFLE: W.host_node(RIFLE, W.box_rifle()), PISTOL: W.host_node(PISTOL, W.slide_pistol())},
        "parts": {SILENCER: a.suppressor, FOREGRIP: lambda: a.flip_y(a.optic()), MAG: lambda: a.mag_box(0.01, 0.12, 0.02), SCOPE: a.optic},
    }}
    return {w["asset_id"]: w for w in W.build(tmp_path_factory.mktemp("w8l_compat"), world)[0]["weapons"]}


def test_ac106_the_silencer_lists_both_hosts_with_no_family_overlap(built):
    hosts = built[SILENCER]["attachment"]["compatible_hosts"]
    assert [(e["host"].split("/")[1], e["tier"], e["score"], e["signals"], e["replaces"]) for e in hosts] == [
        (PISTOL, SAME, 0.7, ["affinity", "mount_available"], []), (RIFLE, SAME, 0.7, ["affinity", "mount_available"], [])]
    assert built[SILENCER]["attachment"]["pending_hosts"] == []


def test_ac106_the_foregrip_is_pending_on_the_rifle_that_has_no_underbarrel_seat_and_absent_from_the_pistol(built):
    att = built[FOREGRIP]["attachment"]
    assert att["compatible_hosts"] == [] and att["pending_hosts"] == [{"host": f"{PACK}/{RIFLE}", "tier": SAME}]
    assert built[RIFLE]["geometry"]["mounts"]["underbarrel"]["reason"] == "no_child_no_probe"


def test_ac106_the_host_with_a_pending_candidate_gets_mount_missing_and_the_other_does_not(built):
    assert "mount_missing" in built[RIFLE]["review"]["reasons"]
    assert "mount_missing" not in built[PISTOL]["review"]["reasons"]


@pytest.mark.parametrize("name", [MAG, SCOPE])
def test_ac106_a_magazine_or_an_optic_with_no_name_overlap_is_still_unlisted(built, name):
    att = built[name]["attachment"]
    assert att["compatible_hosts"] == [] and att["pending_hosts"] == []
