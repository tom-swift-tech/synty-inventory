"""W8l A5 item 0: the `prop` host token refuses every attach slot (docs/weapon_attachments.md 7, A3 addendum 5).

``SM_Prop_Briefcase_Flaregun_01`` is a briefcase, not a gun, yet the directory listed fourteen attachments on it (silencers, a flashlight,
six magazines): ``attach_host_never`` named `prop` for the two sight slots only. A host with the token now gets `none` / `slot_disabled` on
all seven slots, the mechanism the sights already use, so the slot veto of compat.py removes every candidate that is not an override.

Every expected value is a LITERAL (the seven slot names, the real id), never read from the code under test. The world is synthetic.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8h_world", _FIX / "w8h_world.py")
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)
_spec = importlib.util.spec_from_file_location("g1_world", _FIX / "g1_world.py")
GW = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(GW)

from synty_inventory.weapons import mounts as M  # noqa: E402
from synty_inventory.weapons.rules import load_rules  # noqa: E402

ALL_SLOTS = ["optic", "muzzle", "underbarrel", "magazine", "laser_light", "sight_front", "sight_rear"]  # excluded_slots answers in ATTACH_SLOTS order

PACK = "FAKE_W8L_PROP"
# `Zulu` is the family word the hosts and the magazine and flashlight share (those two slots need a family overlap)
PROP, PLAIN, FLARE = "SM_Wep_Zulu_Rifle_Prop_01", "SM_Wep_Zulu_Rifle_Alpha_01", "SM_Wep_Zulu_Pistol_Flare_01"
SILENCER, MAG, LASER = "SM_Wep_Zulu_Silencer_01", "SM_Wep_Zulu_Mag_01", "SM_Wep_Zulu_Flashlight_01"


def rid(name):
    return f"{PACK}/{name}"


def refused(m):
    return m["source"] == "none" and m["reason"] == "slot_disabled" and m["point"] is None and m["occupied_by"] == []


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    a = W.A
    world = {PACK: {
        # G1 3.6 (S8): the hosts are the rod rifle (the box rifle with a round rod barrel), so the silencer has a barrel end to fit: on the box rifle's
        # square barrel it is no_fit on every host and the muzzle refusal below would pass with the refusal removed
        "hosts": {n: W.host_node(n, GW.rod_rifle()) for n in (PROP, PLAIN, FLARE)},
        "parts": {SILENCER: a.suppressor, MAG: lambda: a.mag_box(0.01, 0.12, 0.02), LASER: lambda: a.flip_y(a.optic())},
    }}
    return {w["id"]: w for w in W.build(tmp_path_factory.mktemp("w8l_prop"), world)[0]["weapons"]}


def listing(built, part, host):
    att = built[rid(part)]["attachment"]
    return [e for key in ("compatible_hosts", "pending_hosts") for e in att[key] if e["host"] == rid(host)]


# --- the real id, a pure function ------------------------------------------------------------------------------------


@pytest.mark.parametrize("asset_id", ["POLYGON_Apocalypse/SM_Prop_Briefcase_Flaregun_01", "SM_Prop_Briefcase_Flaregun_01"])
def test_the_briefcase_flaregun_prop_is_refused_on_all_seven_slots(asset_id):
    assert M.excluded_slots(asset_id, load_rules()["attachment_rules"]) == ALL_SLOTS


def test_a_name_that_only_contains_prop_and_a_plain_gun_are_not_refused():
    tables = load_rules()["attachment_rules"]
    assert M.excluded_slots("SM_Wep_Rifle_Properly_01", tables) == []
    assert M.excluded_slots("SM_Wep_Rifle_Assault_01", tables) == []


def test_the_other_tokens_keep_their_slots():
    tables = load_rules()["attachment_rules"]
    assert M.excluded_slots("SM_Wep_Pistol_Flare_01", tables) == ALL_SLOTS  # A8 erratum (2026-10-26): `flare` alone is a tool token (was the two sights)
    assert M.excluded_slots("SM_Wep_ToyGun_Rifle_01", tables) == ["optic", "sight_front", "sight_rear"]
    assert M.excluded_slots("SM_Wep_Watergun_01", tables) == ALL_SLOTS  # A6 (W8n): water is a tool-class token, and the tool class refuses all seven


# --- a built directory -----------------------------------------------------------------------------------------------


def test_a_prop_host_has_none_slot_disabled_on_all_seven_slots(built):
    mounts = built[rid(PROP)]["geometry"]["mounts"]
    assert sorted(mounts) == sorted(ALL_SLOTS)
    for slot in ALL_SLOTS:
        assert refused(mounts[slot]), slot


def test_the_control_hosts_list_the_muzzle_magazine_and_laser_parts(built):
    # without this the next test could pass because the parts never fit anything
    for part in (SILENCER, MAG, LASER):
        assert listing(built, part, PLAIN), part
    # `listing` counts both lists, and a pending entry would let the muzzle part stand in vacuously: the silencer is a fit (compatible), not a pending row
    att = built[rid(SILENCER)]["attachment"]
    assert rid(PLAIN) in [e["host"] for e in att["compatible_hosts"]]
    assert rid(PLAIN) not in [e["host"] for e in att["pending_hosts"]]


@pytest.mark.parametrize("part", [SILENCER, MAG, LASER])
def test_no_attachment_part_lists_the_prop_host_neither_compatible_nor_pending(built, part):
    assert listing(built, part, PROP) == []


def test_a_plain_host_keeps_its_muzzle_seat(built):
    assert not refused(built[rid(PLAIN)]["geometry"]["mounts"]["muzzle"])
