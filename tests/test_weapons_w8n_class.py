"""W8n item 1: host classes (docs/weapon_attachments.md 13.7 A6-1).

``attach_host_class`` names a class by the host name tokens that put a host in it (a host may be in several), ``attach_class_never`` names the
slots a class refuses. A refused slot is a ``none`` / ``slot_disabled`` mount, exactly like an ``attach_host_never`` hit: the union of both rules
is the host's refused slots, and an id override still beats a rule. The ``special`` row and the launcher's optic are Tom's open question, so they
ship switched off (an empty list); the last tests flip them to show the rows work when he answers.

Every expected value is a LITERAL. Fixtures: ``w8n_world.class_world`` (pack FAKE_W8N, one family word ``Zulu`` on every name).
"""

from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8n_world", FIX / "w8n_world.py")
N = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(N)
W = N.W

from synty_inventory.weapons import mounts as M  # noqa: E402
from synty_inventory.weapons.rules import attachment_rules, load_rules, validate_rules  # noqa: E402

TABLES = attachment_rules(load_rules())
ALL = ["optic", "muzzle", "underbarrel", "magazine", "laser_light", "sight_front", "sight_rear"]  # ATTACH_SLOTS order


# -- the shipped rows -------------------------------------------------------------------------------------------------------


def test_the_shipped_class_rows_are_the_specified_literals():
    assert TABLES["attach_host_class"] == {
        "launcher": ["launcher", "rpg", "rocket", "missile"],
        "tool": ["nailgun", "nail", "glue", "paint", "syringe", "welder", "water", "watergun", "waterpistol"],
        "special": ["flamethrower", "flamer", "flame", "flaregun", "stungun"],
    }
    assert TABLES["attach_class_never"] == {
        "launcher": ["muzzle"], "tool": ["muzzle", "optic", "underbarrel", "magazine", "laser_light", "sight_front", "sight_rear"],
        "special": []}  # special: Tom's answer pending, switched off
    assert validate_rules(load_rules()) == []


# -- the pure function ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("host", ["SM_Wep_Nailgun_01", "SM_Wep_Nail_Gun_01", "SM_Wep_Glue_Gun_01", "SM_Wep_PaintGun_01", "SM_Wep_Syringe_01",
                                  "SM_Wep_Welder_01", "SM_Wep_Water_Gun_01", "SM_Wep_Watergun_01", "SM_Wep_WaterPistol_01"])
def test_a_tool_class_token_refuses_all_seven_slots(host):
    assert M.excluded_slots(host, TABLES) == ALL


@pytest.mark.parametrize("host", ["SM_Wep_Launcher_01", "SM_Wep_Grenade_Launcher_01", "SM_Wep_RPG_01", "SM_Wep_Rocket_01", "SM_Wep_Missile_01"])
def test_a_launcher_class_token_refuses_only_the_muzzle(host):
    assert M.excluded_slots(host, TABLES) == ["muzzle"]


@pytest.mark.parametrize("host", ["SM_Wep_Flamethrower_01", "SM_Wep_Flamer_01", "SM_Wep_Flame_01", "SM_Wep_Stungun_01"])
def test_a_special_class_token_refuses_nothing_while_the_row_is_switched_off(host):
    assert M.excluded_slots(host, TABLES) == []


def test_the_flare_gun_keeps_only_its_older_token_rule():
    assert M.excluded_slots("SM_Wep_FlareGun_01", TABLES) == ["sight_front", "sight_rear"]  # `flare` is an attach_host_never token; `flaregun` adds nothing yet


@pytest.mark.parametrize("host", ["SM_Wep_Rifle_Nailed_01", "SM_Wep_Painted_Rifle_01", "SM_Wep_Rocketeer_01", "SM_Wep_Launching_01", "SM_Wep_Rifle_01"])
def test_a_class_token_is_a_whole_word_not_a_prefix(host):
    assert M.excluded_slots(host, TABLES) == []


def test_a_pack_prefix_in_the_id_is_ignored_like_the_other_name_rules():
    assert M.excluded_slots("POLYGON_Apocalypse/SM_Wep_Nailgun_01", TABLES) == ALL
    assert M.excluded_slots("POLYGON_Apocalypse/SM_Wep_Rocket_01", TABLES) == ["muzzle"]


def tables_with(**edit) -> dict:
    t = deepcopy(TABLES)
    t["attach_host_class"] = {"alpha": ["zed"], "beta": ["yak"]}
    t["attach_class_never"] = {"alpha": ["muzzle"], "beta": ["magazine", "optic"]}
    t.update(edit)
    return t


def test_a_host_in_several_classes_gets_the_union_in_attach_slots_order():
    assert M.excluded_slots("SM_Wep_Zed_01", tables_with()) == ["muzzle"]
    assert M.excluded_slots("SM_Wep_Yak_01", tables_with()) == ["optic", "magazine"]
    assert M.excluded_slots("SM_Wep_Zed_Yak_01", tables_with()) == ["optic", "muzzle", "magazine"]


def test_the_class_slots_and_the_attach_host_never_tokens_union():
    t = tables_with()
    t["attach_host_never"] = {**t["attach_host_never"], "underbarrel": ["zed"], "magazine": []}
    assert M.excluded_slots("SM_Wep_Zed_01", t) == ["muzzle", "underbarrel"]  # the class row (muzzle) and the token row (underbarrel)
    assert M.excluded_slots("SM_Wep_Zed_Yak_01", t) == ["optic", "muzzle", "underbarrel", "magazine"]


def test_a_class_with_an_empty_slot_list_refuses_nothing():
    assert M.excluded_slots("SM_Wep_Zed_01", tables_with(attach_class_never={"alpha": [], "beta": []})) == []


def test_a_table_without_the_class_rows_behaves_as_before():
    t = deepcopy(TABLES)
    del t["attach_host_class"], t["attach_class_never"]
    assert M.excluded_slots("SM_Wep_Nailgun_01", t) == [] and M.excluded_slots("SM_Wep_Watergun_01", t) == ["optic", "sight_front", "sight_rear"]


# -- a built directory ------------------------------------------------------------------------------------------------------


def hosts_of(by, part):
    att = by[N.pid(part)]["attachment"]
    return ({e["host"].split("/", 1)[1]: e["tier"] for e in att["compatible_hosts"]},
            {e["host"].split("/", 1)[1]: e["tier"] for e in att["pending_hosts"]})


def mounts_of(by, host):
    return by[N.pid(host)]["geometry"]["mounts"]


def refused(m) -> bool:
    return m["source"] == "none" and m["reason"] == "slot_disabled"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    ovr = W.overrides_doc(ids={
        N.pid(N.C_SILENCER): {"compatible": {"add": [N.pid(N.NAILGUN)]}},
        N.pid(N.NAILGUN): {"mounts": {"magazine": {"source": "child_node", "child": f"{N.NAILGUN}_Mag"}}},
    })
    directory, _, _, _ = W.build(tmp_path_factory.mktemp("w8n_class"), N.class_world(), overrides=ovr)
    return W.by_id(directory)


def test_the_nailgun_host_is_slot_disabled_on_all_slots_but_the_one_an_id_override_names(built):
    m = mounts_of(built, N.NAILGUN)
    assert [s for s in ALL if refused(m[s])] == ["optic", "muzzle", "underbarrel", "laser_light", "sight_front", "sight_rear"]
    assert m["magazine"]["source"] == "override" and m["magazine"]["child_node"] == f"{N.NAILGUN}_Mag"  # an id override beats a class rule


def test_the_rocket_launcher_host_loses_only_the_muzzle(built):
    m = mounts_of(built, N.ROCKET)
    assert refused(m["muzzle"])
    assert [(s, m[s]["source"], m[s]["reason"]) for s in ("optic", "underbarrel", "magazine", "laser_light")] == [
        ("optic", "none", "no_child_no_probe"), ("underbarrel", "none", "no_child_no_probe"), ("magazine", "none", "no_child_no_probe"),
        ("laser_light", "none", "no_child_no_probe")]  # the launcher's optic is Tom's open question: switched off
    assert m["sight_front"]["source"] == "probe" and m["sight_rear"]["source"] == "probe"


@pytest.mark.parametrize("host", [N.PISTOL, N.RIFLE, N.FLAME, N.STUN])
def test_a_firearm_and_the_switched_off_special_hosts_keep_every_slot(built, host):
    m = mounts_of(built, host)
    assert not [s for s in ALL if refused(m[s])]
    assert m["muzzle"]["source"] == "probe" and m["sight_front"]["source"] == "probe"


def test_the_prop_host_keeps_its_existing_whole_name_refusal(built):
    assert all(refused(m) for m in mounts_of(built, N.PROP).values())


def test_no_part_lists_a_refused_slot_of_a_class_host(built):
    comp, pend = hosts_of(built, N.C_SILENCER)
    assert comp == {N.PISTOL: "same_pack_fit", N.RIFLE: "same_pack_fit", N.STUN: "same_pack_fit"}  # not the nailgun, rocket launcher or prop
    assert pend == {N.NAILGUN: "override"}  # the id override's `add` still lists the pair; the seat is none, so it is pending
    for part in (N.C_LASER, N.C_SIGHT):
        comp, pend = hosts_of(built, part)
        assert not {N.NAILGUN, N.ROCKET, N.PROP} & (set(comp) | set(pend)), part
    comp, pend = hosts_of(built, N.C_MAG)  # the one open slot of the nailgun: its id-override magazine seat, a twin of the baked child
    assert comp == {N.NAILGUN: "twin"} and pend == {N.PISTOL: "same_pack_fit", N.RIFLE: "same_pack_fit", N.STUN: "same_pack_fit"}
    comp, pend = hosts_of(built, N.C_SCOPE)
    assert N.NAILGUN not in comp | pend and pend == {N.RIFLE: "same_pack_fit", N.ROCKET: "same_pack_fit"}  # the rocket's optic is not refused (yet)
    comp, pend = hosts_of(built, N.C_FOREGRIP)
    assert N.NAILGUN not in comp | pend and pend == {N.RIFLE: "same_pack_fit", N.ROCKET: "same_pack_fit"}


# -- the switched off rows, switched on -------------------------------------------------------------------------------------


def built_with(tmp_path, **never) -> dict:
    rules = W.sight_rules()
    rules["attachment_rules"]["attach_class_never"].update(never)
    assert validate_rules(rules) == []
    directory, _, _, _ = W.build(tmp_path, N.class_world(), rules=rules)
    return W.by_id(directory)


def test_switching_the_special_row_on_refuses_those_slots_on_the_special_hosts(tmp_path):
    by = built_with(tmp_path, special=["muzzle", "magazine"])
    for host in (N.FLAME, N.STUN):
        m = mounts_of(by, host)
        assert refused(m["muzzle"]) and refused(m["magazine"]) and m["optic"]["reason"] == "no_child_no_probe", host
    comp, pend = hosts_of(by, N.C_SILENCER)
    assert comp == {N.PISTOL: "same_pack_fit", N.RIFLE: "same_pack_fit"}  # the stun gun is gone
    assert not refused(mounts_of(by, N.PISTOL)["muzzle"])


def test_switching_the_launcher_optic_on_removes_the_scope_candidate_of_the_launcher(tmp_path):
    by = built_with(tmp_path, launcher=["muzzle", "optic"])
    m = mounts_of(by, N.ROCKET)
    assert refused(m["muzzle"]) and refused(m["optic"]) and not refused(m["underbarrel"])
    comp, pend = hosts_of(by, N.C_SCOPE)
    assert pend == {N.RIFLE: "same_pack_fit"} and not comp
