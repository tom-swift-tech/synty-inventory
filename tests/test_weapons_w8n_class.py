"""W8n item 1: host classes (docs/weapon_attachments.md 13.7 A6-1).

``attach_host_class`` names a class by the host name tokens that put a host in it (a host may be in several), ``attach_class_never`` names the
slots a class refuses. A refused slot is a ``none`` / ``slot_disabled`` mount, exactly like an ``attach_host_never`` hit: the union of both rules
is the host's refused slots, and an id override still beats a rule. Tom's answers (2026-10-24): the launcher refuses its optic as well as the muzzle, and
flame throwers, flare guns and stun guns are tools ("nothing, like the nail gun"): their tokens sit in the ``tool`` class and there is no ``special`` class.
The last tests edit the rows to show the tables still drive the result.

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
        "launcher": ["launcher", "rpg", "rocket", "missile"], "fixed_heavy": ["minigun"],
        "tool": ["nailgun", "nail", "glue", "paint", "syringe", "welder", "water", "watergun", "waterpistol",
                 "flamethrower", "flamer", "flame", "flare", "flaregun", "stungun"],  # A8 erratum (2026-10-26): `flare` alone
    }
    assert TABLES["attach_class_never"] == {
        "launcher": ["muzzle", "optic"], "tool": ["muzzle", "optic", "underbarrel", "magazine", "laser_light", "sight_front", "sight_rear"],
        "fixed_heavy": ["muzzle", "optic", "underbarrel", "magazine", "laser_light", "sight_front", "sight_rear"]}
    assert validate_rules(load_rules()) == []


# -- the pure function ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("host", ["SM_Wep_Nailgun_01", "SM_Wep_Nail_Gun_01", "SM_Wep_Glue_Gun_01", "SM_Wep_PaintGun_01", "SM_Wep_Syringe_01",
                                  "SM_Wep_Welder_01", "SM_Wep_Water_Gun_01", "SM_Wep_Watergun_01", "SM_Wep_WaterPistol_01",
                                  "SM_Wep_Flamethrower_01", "SM_Wep_Flame_Thrower_01", "SM_Wep_Flamer_01", "SM_Wep_Flame_01", "SM_Wep_FlareGun_01",
                                  "SM_Wep_Flare_Gun_01", "SM_Wep_Stungun_01", "SM_Wep_Stun_Gun_01"])
def test_a_tool_class_token_refuses_all_seven_slots(host):
    assert M.excluded_slots(host, TABLES) == ALL


@pytest.mark.parametrize("host", ["SM_Wep_Minigun_01", "SM_Wep_Minigun_Clean_01", "SM_Wep_Mini_Gun_01", "SM_Wep_Veh_MiniGun_01"])
def test_a_minigun_refuses_all_seven_slots(host):  # Tom, 2026-10-24: "minigun doesn't take any attachments"
    assert M.excluded_slots(host, TABLES) == ALL


@pytest.mark.parametrize("host", ["SM_Wep_Launcher_01", "SM_Wep_Grenade_Launcher_01", "SM_Wep_RPG_01", "SM_Wep_Rocket_01", "SM_Wep_Missile_01"])
def test_a_launcher_class_token_refuses_the_optic_and_the_muzzle_and_nothing_else(host):
    assert M.excluded_slots(host, TABLES) == ["optic", "muzzle"]


@pytest.mark.parametrize("host", ["SM_Wep_Miniguns_01", "SM_Wep_Rifle_Nailed_01", "SM_Wep_Painted_Rifle_01", "SM_Wep_Rocketeer_01", "SM_Wep_Launching_01", "SM_Wep_Rifle_01"])
def test_a_class_token_is_a_whole_word_not_a_prefix(host):
    assert M.excluded_slots(host, TABLES) == []


def test_a_pack_prefix_in_the_id_is_ignored_like_the_other_name_rules():
    assert M.excluded_slots("POLYGON_Apocalypse/SM_Wep_Nailgun_01", TABLES) == ALL
    assert M.excluded_slots("POLYGON_Apocalypse/SM_Wep_Rocket_01", TABLES) == ["optic", "muzzle"]


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


def test_the_rocket_launcher_host_loses_the_muzzle_and_the_optic_only(built):
    m = mounts_of(built, N.ROCKET)
    assert refused(m["muzzle"]) and refused(m["optic"])  # Tom: "No optics on launchers"
    assert [(s, m[s]["source"], m[s]["reason"]) for s in ("underbarrel", "magazine", "laser_light")] == [
        ("underbarrel", "none", "no_child_no_probe"), ("magazine", "none", "no_child_no_probe"), ("laser_light", "none", "no_child_no_probe")]
    assert m["sight_front"]["source"] == "probe" and m["sight_rear"]["source"] == "probe"


@pytest.mark.parametrize("host", [N.PISTOL, N.RIFLE])
def test_a_firearm_keeps_every_slot(built, host):
    m = mounts_of(built, host)
    assert not [s for s in ALL if refused(m[s])]
    assert m["muzzle"]["source"] == "probe" and m["sight_front"]["source"] == "probe"


@pytest.mark.parametrize("host", [N.FLAME, N.STUN, N.MINIGUN])
def test_the_flame_thrower_the_stun_gun_and_the_minigun_refuse_every_slot(built, host):
    assert all(refused(m) for m in mounts_of(built, host).values())  # Tom: "Nothing, like the nail gun"; "minigun doesn't take any attachments"


def test_the_prop_host_keeps_its_existing_whole_name_refusal(built):
    assert all(refused(m) for m in mounts_of(built, N.PROP).values())


def test_no_part_lists_a_refused_slot_of_a_class_host(built):
    comp, pend = hosts_of(built, N.C_SILENCER)
    assert comp == {N.PISTOL: "same_pack_fit", N.RIFLE: "same_pack_fit"}  # not the nailgun, rocket launcher, stun gun, minigun or prop
    assert pend == {N.NAILGUN: "override"}  # the id override's `add` still lists the pair; the seat is none, so it is pending
    for part in (N.C_LASER, N.C_SIGHT):
        comp, pend = hosts_of(built, part)
        assert not {N.NAILGUN, N.ROCKET, N.PROP, N.FLAME, N.STUN, N.MINIGUN} & (set(comp) | set(pend)), part
    comp, pend = hosts_of(built, N.C_MAG)  # the one open slot of the nailgun: its id-override magazine seat, a twin of the baked child
    assert comp == {N.NAILGUN: "twin"} and pend == {N.PISTOL: "same_pack_fit", N.RIFLE: "same_pack_fit"}
    comp, pend = hosts_of(built, N.C_SCOPE)
    assert N.NAILGUN not in comp | pend and pend == {N.RIFLE: "same_pack_fit"}  # the rocket's optic is refused too
    comp, pend = hosts_of(built, N.C_FOREGRIP)
    assert N.NAILGUN not in comp | pend and pend == {N.RIFLE: "same_pack_fit", N.ROCKET: "same_pack_fit"}


# -- the tables drive the result ---------------------------------------------------------------------------------------------


def built_with(tmp_path, **never) -> dict:
    rules = W.sight_rules()
    rules["attachment_rules"]["attach_class_never"].update(never)
    assert validate_rules(rules) == []
    directory, _, _, _ = W.build(tmp_path, N.class_world(), rules=rules)
    return W.by_id(directory)


def test_a_class_row_edited_back_gives_the_launcher_its_optic_again(tmp_path):
    by = built_with(tmp_path, launcher=["muzzle"])
    m = mounts_of(by, N.ROCKET)
    assert refused(m["muzzle"]) and not refused(m["optic"]) and m["optic"]["reason"] == "no_child_no_probe"
    comp, pend = hosts_of(by, N.C_SCOPE)
    assert pend == {N.RIFLE: "same_pack_fit", N.ROCKET: "same_pack_fit"} and not comp


def test_emptying_the_tool_row_gives_the_stun_gun_its_seats_again(tmp_path):
    by = built_with(tmp_path, tool=[])
    assert not [s for s in ALL if refused(mounts_of(by, N.STUN)[s])]
    comp, pend = hosts_of(by, N.C_SILENCER)
    assert N.STUN in comp and N.NAILGUN in comp | pend


# -- a prefab-only host has no mounts to refuse, so compat reads its name ---------------------------------------------------------


def _unmeasured(name, archetype):
    return {"id": f"POLYGON_Military/{name}", "pack": "POLYGON_Military", "asset_id": name, "role": "whole", "kind": "ranged", "hold_class": "long_gun", "archetype": archetype,
            "flags": ["prefab_only", "unmeasured"], "attachment": None, "geometry": None, "review": {"confidence": 0.9, "reasons": ["no_geometry"]}}


def _part(name, slot, kind):  # pack POLYGON_Heist (the same setting as the hosts): a cross_pack_fit candidate (no family word is needed, the host has no seat to measure)
    anchor = {"point": [0.0, 0.0, 0.0], "forward": [0.0, 0.0, 1.0], "up": [0.0, 1.0, 0.0], "foot_source": "authored_up", "forward_source": "section",
              "symmetric": False}
    fp = {"length_m": 0.2, "width_m": 0.06, "height_m": 0.08, "foot_length_m": 0.06, "foot_width_m": 0.02, "mate_d_m": None}
    return {"id": f"POLYGON_Heist/{name}", "pack": "POLYGON_Heist", "asset_id": name, "role": "part", "kind": None, "hold_class": "none", "archetype": "unknown", "flags": [],
            "geometry": None, "attachment": {"slot": slot, "kind": kind, "anchor": anchor, "footprint": fp, "compatible_hosts": [], "pending_hosts": []},
            "review": {"confidence": 0.9, "reasons": []}}


def test_an_unmeasured_launcher_or_tool_host_gets_no_pending_pair_for_a_slot_its_class_refuses():
    from synty_inventory.weapons import compat
    hosts = [_unmeasured("SM_Wep_Launcher_Preset_01", "launcher"), _unmeasured("SM_Wep_Stungun_Preset_01", "utility_gun"),
             _unmeasured("SM_Wep_Minigun_Preset_01", "heavy_gun"), _unmeasured("SM_Wep_Rifle_Preset_01", "rifle")]
    got = compat.compute(hosts + [_part("SM_Wep_Scope_01", "optic", "scope"), _part("SM_Wep_Foregrip_01", "underbarrel", "foregrip")], load_rules())["parts"]
    pending = lambda part: sorted(e["host"] for e in got[f"POLYGON_Heist/{part}"]["pending"])
    assert pending("SM_Wep_Scope_01") == ["POLYGON_Military/SM_Wep_Rifle_Preset_01"]  # not the launcher (optic refused), not the stun gun or the minigun (every slot refused)
    assert pending("SM_Wep_Foregrip_01") == ["POLYGON_Military/SM_Wep_Launcher_Preset_01", "POLYGON_Military/SM_Wep_Rifle_Preset_01"]  # a launcher keeps its foregrip
