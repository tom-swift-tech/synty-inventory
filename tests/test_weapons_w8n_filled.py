"""W8n: a preset refuses the slots its built-in parts already fill (Tom, 2026-10-24: "presets only refuse the slots their built-in parts already fill;
other slots stay open").

``attachment_rules.attach_filled_hosts`` names the host tokens (``preset``) of hosts that arrive with their parts on. Such a host refuses (mount ``none`` /
``slot_disabled``) each slot one of its OWN measured baked children fills, whatever the child is; a slot no child fills stays open, and an id override
still wins. The rule reads the children, so no preset is named by hand. The world is synthetic (``w8n_world.preset_world``, pack FAKE_W8N).
Every expected value is a LITERAL.
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

from synty_inventory.weapons.rules import attachment_rules, load_rules, validate_rules  # noqa: E402

ALL = ["optic", "muzzle", "underbarrel", "magazine", "laser_light", "sight_front", "sight_rear"]
FULL, MAG, BARE, CONTROL = N.PRE_FULL, N.PRE_MAG, N.PRE_BARE, N.PRE_CONTROL


def mounts_of(by, host):
    return by[N.pid(host)]["geometry"]["mounts"]


def refused(m) -> bool:
    return m["source"] == "none" and m["reason"] == "slot_disabled"


def refused_slots(by, host) -> list[str]:
    m = mounts_of(by, host)
    return [s for s in ALL if refused(m[s])]


def listed(by, part) -> dict[str, str]:
    att = by[N.pid(part)]["attachment"]
    return {e["host"].split("/", 1)[1]: e["tier"] for e in att["compatible_hosts"] + att["pending_hosts"]}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    directory, _, _, _ = W.build(tmp_path_factory.mktemp("w8n_filled"), N.preset_world())
    return W.by_id(directory)


def test_the_shipped_row_is_the_preset_token_and_the_rules_validate():
    assert attachment_rules(load_rules())["attach_filled_hosts"] == ["preset"]
    assert validate_rules(load_rules()) == []


def test_a_preset_refuses_each_slot_a_baked_child_fills(built):
    # a magazine, a suppressor, a foregrip and a scope are baked on: magazine, muzzle, underbarrel and optic go; the scope child also takes both iron
    # sights (the baked-sight rules of addendum 3, unchanged); the laser light is filled by nothing and stays open
    assert refused_slots(built, FULL) == ["optic", "muzzle", "underbarrel", "magazine", "sight_front", "sight_rear"]
    assert mounts_of(built, FULL)["laser_light"]["reason"] == "no_child_no_probe"


def test_a_preset_with_only_a_magazine_refuses_only_the_magazine(built):
    assert refused_slots(built, MAG) == ["magazine"]
    m = mounts_of(built, MAG)
    assert m["muzzle"]["source"] == "probe" and m["sight_front"]["source"] == "probe"  # the other slots keep their seats


def test_a_preset_with_no_baked_part_keeps_every_slot(built):
    assert refused_slots(built, BARE) == []


def test_the_same_children_on_a_host_that_is_not_a_preset_refuse_nothing_more(built):
    assert refused_slots(built, CONTROL) == ["sight_front", "sight_rear"]  # only the baked-scope sight rule; magazine, muzzle, grip and optic stay seats
    m = mounts_of(built, CONTROL)
    assert (m["magazine"]["source"], m["underbarrel"]["source"], m["optic"]["source"]) == ("child_node", "child_node", "child_node")


def test_no_part_lists_a_slot_a_preset_has_filled_and_every_open_slot_still_lists(built):
    assert set(listed(built, N.C_MAG)) == {BARE, CONTROL}  # not FULL or MAG: each has its own magazine (the authored twin of it is gone with the seat)
    assert set(listed(built, N.C_SILENCER)) == {MAG, BARE, CONTROL}  # not FULL: its muzzle is filled by its own suppressor
    assert set(listed(built, N.C_FOREGRIP)) == {MAG, BARE, CONTROL}
    assert set(listed(built, N.C_SCOPE)) == {MAG, BARE, CONTROL}
    assert set(listed(built, N.C_LASER)) == {FULL, MAG, BARE, CONTROL}  # the laser slot is open on every one of them


def test_an_id_override_still_beats_the_filled_slot_rule(tmp_path):
    ovr = W.overrides_doc(ids={N.pid(FULL): {"mounts": {"magazine": {"source": "child_node", "child": f"{FULL}_Mag"}}}})
    directory, _, _, _ = W.build(tmp_path, N.preset_world(), overrides=ovr)
    by = W.by_id(directory)
    assert mounts_of(by, FULL)["magazine"]["source"] == "override"
    assert "magazine" not in refused_slots(by, FULL)


def test_the_rule_is_driven_by_the_table_and_switching_it_off_restores_the_seats(tmp_path):
    rules = deepcopy(load_rules())
    rules["attachment_rules"]["attach_filled_hosts"] = []
    directory, _, _, _ = W.build(tmp_path, N.preset_world(), rules=rules)
    assert refused_slots(W.by_id(directory), FULL) == ["sight_front", "sight_rear"]  # only the baked-scope sight rule is left
