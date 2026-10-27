"""W8p (A8 erratum E2): two hosts with an integral can at the muzzle refuse the muzzle slot (lead ruling 2026-10-26; Tom's rule "built-in parts fill their slot").

* ``POLYGON_Police_Station/SM_Wep_Sniper_01``: the last 21 cm of barrel is a hollow can (radius 0.027-0.029 m against a 0.0139 m barrel); Tom labelled four
  silencers on it "no" (e33, e49, f20, f26) and five ``cross_pack_fit`` silencers were listed on it;
* ``POLYGON_SciFi_Worlds/SM_Wep_Sniper_03``: a slotted can-like section ends at the muzzle (radius 0.043 m over 0.19 m against a 0.023 m barrel); no
  silencer was listed on it, the refusal is a guard.

``POLYGON_SciFi_Worlds/SM_Wep_Pistol_05`` (a ported brake; a silencer covers a built-in brake) and a plain Police_Station sniper are the controls. The
mechanism is the per-id override file, read from the SHIPPED ``weapon_overrides.json`` (not from a test doc). The worlds are synthetic (packs named like
the real ones so the shipped ids hit): round-barrel hosts, so a slim suppressor from another pack measures a good bore and reaches ``cross_pack_fit``.
Every expected value is a LITERAL.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, FIX / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


W = _load("w8h_world")
A = W.A

from synty_inventory.weapons.overrides import empty_overrides, load_overrides  # noqa: E402
from synty_inventory.weapons.rules import load_rules  # noqa: E402

PS, MIL, SFW, SFC = "POLYGON_Police_Station", "POLYGON_Military", "POLYGON_SciFi_Worlds", "POLYGON_SciFi_City"
SNIPER_PS, SNIPER_PS_CONTROL = "SM_Wep_Sniper_01", "SM_Wep_Sniper_02"
SNIPER_SF, PISTOL_SF = "SM_Wep_Sniper_03", "SM_Wep_Pistol_05"
SIL, BRAKE, CROSS_SIL = "SM_Wep_Silencer_01", "SM_Wep_Silencer_Brake_01", "SM_Wep_Mod_Silencer_01"
OTHER_SLOTS = ["optic", "underbarrel", "magazine", "laser_light", "sight_front", "sight_rear"]
# S7 (spec 3.4 step 3): the round-barrel hosts have a smooth top, so their optic is an estimated flat seat (a probe seat)
OTHER_SLOTS_SEATS = {"optic": ("probe", None), "underbarrel": ("none", "no_child_no_probe"), "magazine": ("none", "no_child_no_probe"),
                     "laser_light": ("none", "no_child_no_probe"), "sight_front": ("probe", None), "sight_rear": ("probe", None)}


def slim():
    """A suppressor whose narrow end measures a mating diameter of 0.0130 m, the bore ring of the round-barrel host: a good bore, so another pack reaches cross_pack_fit."""
    return W.G.loft(2, [(-0.1, 0.0046, 0.0046), (0.1, 0.02, 0.02)])


def host(name: str):
    return W.host_node(name, A.host_body("round"))


def world() -> dict:
    return {
        PS: {"hosts": {SNIPER_PS: host(SNIPER_PS), SNIPER_PS_CONTROL: host(SNIPER_PS_CONTROL)}, "parts": {SIL: slim, BRAKE: slim}},
        MIL: {"parts": {CROSS_SIL: slim}},
        SFW: {"hosts": {SNIPER_SF: host(SNIPER_SF), PISTOL_SF: host(PISTOL_SF)}, "parts": {SIL: slim, BRAKE: slim}},
        SFC: {"parts": {CROSS_SIL: slim}},
    }


def with_brakes(overrides: dict) -> dict:
    """The given overrides plus a classification of the two ``Silencer_Brake_01`` parts as a ``brake`` (a muzzle part that is no suppressor)."""
    out = copy.deepcopy(overrides)
    for pack in (PS, SFW):
        out["ids"][f"{pack}/{BRAKE}"] = {"note": "test: a muzzle brake", "set": {"attachment_slot": "muzzle", "attachment_kind": "brake"}}
    return out


def build(tmp_path, overrides):
    directory, _, _, _ = W.build(tmp_path, world(), rules=load_rules(), overrides=with_brakes(overrides))
    return W.by_id(directory)


@pytest.fixture(scope="module")
def shipped(tmp_path_factory):
    return build(tmp_path_factory.mktemp("w8p_cans_shipped"), load_overrides())


@pytest.fixture(scope="module")
def bare(tmp_path_factory):
    return build(tmp_path_factory.mktemp("w8p_cans_bare"), empty_overrides())


def mounts(by, pack, host_id) -> dict:
    return by[f"{pack}/{host_id}"]["geometry"]["mounts"]


def listed(by, pack, part) -> dict:
    """``{host asset id: tier}`` over compatible_hosts and pending_hosts of the part."""
    att = by[f"{pack}/{part}"]["attachment"]
    return {e["host"].split("/", 1)[1]: e["tier"] for e in att["compatible_hosts"] + att["pending_hosts"]}


# (pack, host, pack of a cross-pack suppressor)
CANS = [pytest.param(PS, SNIPER_PS, MIL, id="police_station_sniper_01"), pytest.param(SFW, SNIPER_SF, SFC, id="scifi_worlds_sniper_03")]


@pytest.mark.parametrize("pack,host_id,cross_pack", CANS)
def test_the_muzzle_is_refused_and_no_suppressor_is_listed_or_pending(shipped, bare, pack, host_id, cross_pack):
    seated = mounts(bare, pack, host_id)["muzzle"]
    assert (seated["source"], seated["reason"]) == ("probe", None)  # the build alone seats it
    muzzle = mounts(shipped, pack, host_id)["muzzle"]
    assert (muzzle["source"], muzzle["reason"], muzzle["point"], muzzle["occupied_by"]) == ("none", "slot_disabled", None, [])
    # the same-pack and the cross-pack suppressor are listed without the override; with it neither is, in compatible_hosts or in pending_hosts
    assert listed(bare, pack, SIL)[host_id] == "same_pack_fit"
    assert listed(bare, cross_pack, CROSS_SIL)[host_id] == "cross_pack_fit"
    assert host_id not in listed(shipped, pack, SIL)
    assert host_id not in listed(shipped, cross_pack, CROSS_SIL)


@pytest.mark.parametrize("pack,host_id,cross_pack", CANS)
def test_a_muzzle_part_that_is_no_suppressor_is_refused_too(shipped, bare, pack, host_id, cross_pack):
    assert shipped[f"{pack}/{BRAKE}"]["attachment"]["kind"] == "brake"
    assert listed(bare, pack, BRAKE)[host_id] == "same_pack_fit"
    assert host_id not in listed(shipped, pack, BRAKE)  # the slot is filled, whatever the kind of the part


@pytest.mark.parametrize("pack,host_id,control_id", [pytest.param(PS, SNIPER_PS, SNIPER_PS_CONTROL, id="police_station_sniper_01"),
                                                     pytest.param(SFW, SNIPER_SF, PISTOL_SF, id="scifi_worlds_sniper_03")])
def test_no_other_slot_moves(shipped, bare, pack, host_id, control_id):
    got = mounts(shipped, pack, host_id)
    assert got["muzzle"]["source"] == "none"  # the one slot that moves
    assert {s: (got[s]["source"], got[s]["reason"]) for s in OTHER_SLOTS} == OTHER_SLOTS_SEATS
    assert {s: got[s] for s in OTHER_SLOTS} == {s: mounts(bare, pack, host_id)[s] for s in OTHER_SLOTS}  # as the build alone made them
    assert {s: got[s] for s in OTHER_SLOTS} == {s: mounts(shipped, pack, control_id)[s] for s in OTHER_SLOTS}  # and as a control host built the same way has them


@pytest.mark.parametrize("pack,control_id,cross_pack", [pytest.param(PS, SNIPER_PS_CONTROL, MIL, id="police_station_sniper_02"),
                                                        pytest.param(SFW, PISTOL_SF, SFC, id="scifi_worlds_pistol_05")])
def test_the_control_hosts_keep_the_muzzle_seat_and_take_both_suppressors(shipped, pack, control_id, cross_pack):
    muzzle = mounts(shipped, pack, control_id)["muzzle"]
    assert (muzzle["source"], muzzle["reason"]) == ("probe", None)
    assert listed(shipped, pack, SIL)[control_id] == "same_pack_fit"
    assert listed(shipped, cross_pack, CROSS_SIL)[control_id] == "cross_pack_fit"
    assert listed(shipped, pack, BRAKE)[control_id] == "same_pack_fit"


def test_the_shipped_override_file_carries_exactly_the_muzzle_refusal_and_a_note_for_the_two_hosts():
    path = Path(__file__).resolve().parents[1] / "src" / "synty_inventory" / "data" / "weapon_overrides.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    for host_id in (f"{PS}/{SNIPER_PS}", f"{SFW}/{SNIPER_SF}"):
        entry = doc["ids"][host_id]
        assert sorted(entry) == ["mounts", "note"], host_id
        assert entry["mounts"] == {"muzzle": {"source": "none"}}, host_id
        assert isinstance(entry["note"], str) and entry["note"].strip(), host_id
    assert f"{SFW}/{PISTOL_SF}" not in doc["ids"]  # the ported brake: a silencer covers it
