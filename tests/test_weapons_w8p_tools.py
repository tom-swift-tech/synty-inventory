"""W8p A8 erratum (2026-10-26): `SM_Wep_Pistol_Flare_01` is a tool host, refused every slot like the flare gun (tool class, `flare` token).

Tom's standing rule (2026-10-24): flame throwers, flare guns and stun guns get "Nothing, like the nail gun". The class tokens are whole words of the host
id plus the joins of 2-3 neighbours, so `Flare_Gun` reached `flaregun` but `Pistol_Flare` (a BattleRoyale host) had only `pistol` and `flare` and was
refused the sight slots only, so a muzzle still seated on it. The fix is the one data token `flare` in ``attach_host_class.tool``.

Every expected value is a LITERAL (the seven slot names in ATTACH_SLOTS order, the host ids); ids are synthetic, the world is built from fixtures.
The sweep of the tool host names and the controls pass on the old yaml too (the guard rail around the one token); the Pistol_Flare / Flare_Pistol
cases and the end-to-end cases fail on it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8h_world", _FIX / "w8h_world.py")
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)

from synty_inventory.weapons import mounts as M  # noqa: E402
from synty_inventory.weapons.rules import attachment_rules, load_rules  # noqa: E402

TABLES = attachment_rules(load_rules())
ALL = ["optic", "muzzle", "underbarrel", "magazine", "laser_light", "sight_front", "sight_rear"]  # ATTACH_SLOTS order


# -- the pure function: the flare hosts in either word order --------------------------------------------------------------------------


@pytest.mark.parametrize("host", ["SM_Wep_Pistol_Flare_01", "SM_Wep_Flare_Pistol_01", "SM_Wep_Flare_Gun_01", "POLYGON_BattleRoyale/SM_Wep_Pistol_Flare_01"])
def test_a_flare_host_in_any_word_order_is_refused_all_seven_slots(host):
    assert M.excluded_slots(host, TABLES) == ALL


def test_the_flare_token_is_in_the_tool_row_and_the_flaregun_join_is_kept():
    assert "flare" in TABLES["attach_host_class"]["tool"] and "flaregun" in TABLES["attach_host_class"]["tool"]


# -- the guard rail: the tool hosts of the audit were refused before and are still (these pass on the old yaml) --------------------------

TOOLS = ["FlareGun_01", "Nailgun_01", "Nailgun_Clean_01", "Nail_Gun_01", "Stungun_01", "Stungun_02", "Welder_01", "Syringe_Gun_01", "Paint_Gun_01",
         "Glue_Gun_01", "SM_Prop_Staple_Gun_01", "SM_Prop_Spray_Gun_01", "Watergun_01", "WaterPistol_01", "FlameThrower_01", "Flame_Thrower_01",
         "Flamethrower_Bottle_Separate_01"]


@pytest.mark.parametrize("name", TOOLS)
def test_the_audited_tool_host_names_are_refused_all_seven_slots(name):
    host = name if name.startswith("SM_") else f"SM_Wep_{name}"
    assert M.excluded_slots(host, TABLES) == ALL, host


# -- the controls stay as they were --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("host,slots", [
    ("SM_Wep_Pistol_01", []),
    ("SM_Wep_Rifle_Properly_01", []),  # a token, not a substring
    ("SM_Wep_Rifle_Flared_01", []),  # `flared` is not `flare`
    ("SM_Wep_ToyGun_Rifle_01", ["optic", "sight_front", "sight_rear"]),
    ("SM_Wep_RPG_01", ["optic", "muzzle"]),
])
def test_the_controls_keep_their_slots(host, slots):
    assert M.excluded_slots(host, TABLES) == slots


# -- end to end: no suppressor lists the flare pistol, listed or pending --------------------------------------------------------------------

PA, PB = "FAKE_W8P_A", "FAKE_W8P_B"
FLARE, PLAIN = "SM_Wep_Zulu_Pistol_Flare_01", "SM_Wep_Zulu_Pistol_Plain_01"
SAME, CROSS = "SM_Wep_Zulu_Silencer_01", "SM_Wep_Zulu_Silencer_02"


def rid(pack, name):
    return f"{pack}/{name}"


def listing(by, part_id, host_id):
    att = by[part_id]["attachment"]
    return [e for key in ("compatible_hosts", "pending_hosts") for e in att[key] if e["host"] == host_id]


SLIM_H = 0.0046  # 2 * 0.0046 * sqrt(2) = 0.01301 m mating diameter, the bore ring diameter (tube r_in 0.0065)
SETTING = {PA: "s1", PB: "s1"}  # one setting, so the other pack passes the setting gate and the tier rules decide


def ring_barrel_host(name):
    return W.host_node(name, W.A.host_body("round"))  # a round barrel with a bore ring: the measured bore a cross-pack suppressor is fitted against


def slim_suppressor():
    return W.A.G.loft(2, [(-0.1, SLIM_H, SLIM_H), (0.1, W.A.MUZZLE_WIDE_H, W.A.MUZZLE_WIDE_H)])  # a narrow end matching the 13 mm bore


def world():
    a = W.A
    return {
        PA: {"hosts": {n: ring_barrel_host(n) for n in (FLARE, PLAIN)}, "parts": {SAME: slim_suppressor}},
        PB: {"parts": {CROSS: slim_suppressor}},
    }


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    ovr = W.overrides_doc(ids={rid(PB, CROSS): {"compatible": {"add": [rid(PA, FLARE)]}}})
    return W.by_id(W.build(tmp_path_factory.mktemp("w8p_tools"), world(), rules=W.sight_rules(SETTING), overrides=ovr)[0])


def test_the_flare_pistol_has_none_slot_disabled_on_all_seven_slots(built):
    m = built[rid(PA, FLARE)]["geometry"]["mounts"]
    assert sorted(m) == sorted(ALL)
    for slot in ALL:
        assert m[slot]["source"] == "none" and m[slot]["reason"] == "slot_disabled", slot


def test_the_same_pack_suppressor_lists_the_plain_pistol_and_not_the_flare_pistol(built):
    part = rid(PA, SAME)
    assert [e["tier"] for e in listing(built, part, rid(PA, PLAIN))] == ["same_pack_fit"]  # the control: the part fits a pistol
    assert listing(built, part, rid(PA, FLARE)) == []


def test_the_cross_pack_suppressor_lists_the_plain_pistol_as_a_cross_pack_fit(built):
    assert [e["tier"] for e in listing(built, rid(PB, CROSS), rid(PA, PLAIN))] == ["cross_pack_fit"]


def test_an_add_override_still_lists_the_flare_pistol_as_an_override_pending(built):
    att = built[rid(PB, CROSS)]["attachment"]
    assert [e["host"] for e in att["compatible_hosts"] if e["host"] == rid(PA, FLARE)] == []  # the seat is none, so it lands in pending_hosts
    assert [e["tier"] for e in att["pending_hosts"] if e["host"] == rid(PA, FLARE)] == ["override"]
    assert [e["host"] for e in built[rid(PA, SAME)]["attachment"]["pending_hosts"] if e["host"] == rid(PA, FLARE)] == []  # the same-pack part had no add


@pytest.mark.parametrize("part", [rid(PA, SAME), rid(PB, CROSS)], ids=["same_pack", "cross_pack"])
def test_without_the_add_neither_suppressor_lists_the_flare_pistol(tmp_path, part):
    by = W.by_id(W.build(tmp_path, world(), rules=W.sight_rules(SETTING))[0])
    assert listing(by, part, rid(PA, FLARE)) == []
    assert listing(by, part, rid(PA, PLAIN)) != []  # the control: the same part is a candidate on the plain pistol
