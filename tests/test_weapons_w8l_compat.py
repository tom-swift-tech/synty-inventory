"""W8l: the family-free slots of the same_pack_fit tier (docs/weapon_attachments.md 5.1 "A4"; AC106), as G1 leaves them (S8).

``attachment_rules.family_free_slots`` now names the two label-era sight slots only (G1 3.8, AC148): the four geometry slots (optic, muzzle,
underbarrel, magazine) take their tier from the pack relation and their listing from the geometry verdict (3.1), so a silencer or a foregrip needs no
shared name token and no affinity any more, and neither does a scope or a magazine. Pure ``compat.candidate`` cases first (a host with no recorded
features is ``not_judged``: a pending same-pack entry, whatever its name), then a built directory (pack FAKE_W8L: a rifle and a pistol with no baked
children, four ``Zulu`` parts that share no token with either). Every expected tier and signal is a LITERAL worked out by hand.
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
PENDING_SAME = {"host": "P/Host_01", "tier": SAME, "listed": False}


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


def test_ac106_the_shipped_table_lists_the_two_sight_slots_only():
    # G1 3.8 (S8): muzzle and underbarrel leave the table with the family test they were exempt from
    assert TABLES["family_free_slots"] == ["sight_front", "sight_rear"]
    assert PARAMS["family_free_slots"] == {"sight_front", "sight_rear"}


# --- the candidate tier ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("slot", "kind"), [("muzzle", "suppressor"), ("underbarrel", "foregrip")])
def test_ac106_a_muzzle_or_underbarrel_part_with_no_shared_token_is_a_pending_same_pack_entry_while_the_host_has_no_features(slot, kind):
    # G1 3.1: the tier is the pack relation (no token, no affinity), the listing is the verdict; a host never measured is not_judged: pending, bare
    assert cand(part(slot, kind), host({slot: seat()})) == PENDING_SAME


@pytest.mark.parametrize(("slot", "kind"), [("muzzle", "suppressor"), ("underbarrel", "foregrip")])
@pytest.mark.parametrize("reason", ["no_child_no_probe", "probe_unavailable"])
def test_ac106_without_a_seat_the_part_is_pending_too(slot, kind, reason):
    assert cand(part(slot, kind), host({slot: none_seat(reason)})) == PENDING_SAME


@pytest.mark.parametrize(("slot", "kind"), [("muzzle", "suppressor"), ("underbarrel", "foregrip")])
def test_ac106_a_slot_disabled_host_gives_no_candidate(slot, kind):
    assert cand(part(slot, kind), host({slot: none_seat("slot_disabled")})) is None


@pytest.mark.parametrize(("slot", "kind"), [("magazine", "standard"), ("optic", "scope")])
def test_ac106_the_other_geometry_slots_need_no_shared_token_either(slot, kind):
    assert cand(part(slot, kind), host({slot: seat()})) == PENDING_SAME  # G1 3.8: the family test is retired for all four geometry slots
    assert cand(part(slot, kind, tokens=frozenset({"alpha"})), host({slot: seat()})) == PENDING_SAME  # and a shared token changes nothing


def test_ac106_a_label_slot_outside_the_table_still_needs_a_shared_token():
    laser = host({"laser_light": seat()})
    assert cand(part("laser_light", "laser"), laser) is None
    assert cand(part("laser_light", "laser", tokens=frozenset({"alpha"})), laser)["tier"] == SAME  # with the token it lists


@pytest.mark.parametrize("slot", ["sight_front", "sight_rear"])
def test_ac106_the_sight_slots_stay_family_free_through_the_table(slot):
    kind = "post" if slot == "sight_front" else "notch"
    got = cand(part(slot, kind), host({slot: seat()}))
    assert got["tier"] == SAME and "family_overlap" not in got["signals"]


def test_ac106_the_table_decides_for_the_label_slots_and_the_geometry_slots_ignore_it():
    sight_host = host({"sight_front": seat()})
    assert cand(part("sight_front", "post"), sight_host, {**PARAMS, "family_free_slots": frozenset()}) is None  # out of the table: a token again
    muzzle_host = host({"muzzle": seat()})
    assert cand(part(), muzzle_host, {**PARAMS, "family_free_slots": frozenset()}) == PENDING_SAME  # a geometry slot reads no table
    mag_host = host({"magazine": seat()})
    assert cand(part("magazine", "standard"), mag_host, {**PARAMS, "family_free_slots": frozenset({"magazine"})}) == PENDING_SAME


def test_ac106_affinity_is_retired_for_the_geometry_slots_a_pistol_foregrip_is_a_pending_entry():
    assert cand(part("underbarrel", "foregrip"), host({"underbarrel": seat()}, archetype="pistol")) == PENDING_SAME  # G1 3.8: no attach_affinity row decides it


def test_ac106_a_cross_pack_part_is_a_pending_cross_entry_whatever_the_bore():
    other = part("muzzle", "suppressor", pack="Q", mate_d_m=0.0130)
    ring = host({"muzzle": seat(bore_d_m=0.0130, bore_source="ring")})
    want = {"host": "P/Host_01", "tier": CROSS, "listed": False}
    assert cand(other, ring) == want  # G1 3.1: the tier is the pack relation; the old bore evidence is not read (cross_pack_size_tol, fit_bore: retired)
    assert cand(part("muzzle", "suppressor", pack="Q"), host({"muzzle": seat()})) == want  # nor does a missing bore drop it


def test_ac106_a_ring_bore_mismatch_no_longer_marks_the_candidate_or_scores_it():
    ring = seat(bore_d_m=0.0130, bore_source="ring")
    got = cand(part(mate_d_m=0.0260), host({"muzzle": ring}))  # 0.0260 against a 0.0130 bore: the label-era `bore_mismatch` of 100 % off
    assert got == PENDING_SAME  # G1 3.1 step 5: the score is the tier base alone and the pending form carries no fit_bore or bore_mismatch signal


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


def pending_of(built, name):
    att = built[name]["attachment"]
    return att["compatible_hosts"], sorted((e["host"].split("/")[1], e["tier"], tuple(e.get("signals", ()))) for e in att["pending_hosts"])


def test_ac106_the_silencer_lists_neither_host_the_box_barrels_have_no_end_to_judge(built):
    # G1 3.6: the fixture barrels are boxes (no ring and no round section), so the muzzle verdict is no_fit: on neither list, with or without a name
    assert pending_of(built, SILENCER) == ([], [])


def test_ac106_the_foregrip_is_a_bare_pending_entry_on_both_hosts(built):
    # no underbarrel seat on either host: not_judged, so pending with no signals; the pistol is no longer cut by affinity (G1 3.8)
    assert pending_of(built, FOREGRIP) == ([], [(PISTOL, SAME, ()), (RIFLE, SAME, ())])
    assert built[RIFLE]["geometry"]["mounts"]["underbarrel"]["reason"] == "no_child_no_probe"


def test_ac106_both_hosts_with_a_pending_candidate_get_mount_missing(built):
    assert "mount_missing" in built[RIFLE]["review"]["reasons"]
    assert "mount_missing" in built[PISTOL]["review"]["reasons"]  # the pistol held no candidate before: affinity cut the foregrip


def test_ac106_a_magazine_and_an_optic_with_no_name_overlap_are_pending_now(built):
    # G1 3.1/3.5/3.8: no family test any more; the flat optic seats are unverified (rail_flat), the magazine mount is none: not_judged
    assert pending_of(built, MAG) == ([], [(PISTOL, SAME, ()), (RIFLE, SAME, ())])
    assert pending_of(built, SCOPE) == ([], [(PISTOL, SAME, ("rail_flat",)), (RIFLE, SAME, ("rail_flat",))])
