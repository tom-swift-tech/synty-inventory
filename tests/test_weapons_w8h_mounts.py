"""W8h-A/B: sight mounts from baked children, the probe fallback and the cache key (AC89, AC92 wiring, AC93 cache; spec 4.2, 4.6).

Hosts are the W8a body (z -0.25..0.65, +z forward, +y up) with children that are the W8a optic (foot centre (0.005, 0, 0.05) in its
own frame, so a child at node translation T seats at T + (0.005, 0, 0.05)). Expected seats are literals.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("w8h_world", Path(__file__).parent / "fixtures" / "weapons" / "w8h_world.py")
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)
A = W.A

from synty_inventory.weapons import geometry as geo  # noqa: E402
from synty_inventory.weapons import mounts as M  # noqa: E402
from synty_inventory.weapons.rules import load_rules  # noqa: E402

PACK = "FAKE_SightMount"
SLOTS = ["optic", "muzzle", "underbarrel", "magazine", "laser_light", "sight_front", "sight_rear"]
FRONT_AT, REAR_AT, GLASS_AT = (0.0, 0.10, 0.30), (0.0, 0.10, -0.20), (0.0, 0.10, 0.10)
FOOT = A.FOOT_CENTRE  # (0.005, 0.0, 0.05): the foot centre of A.optic() in its own frame


def seat(at):
    return [at[i] + FOOT[i] for i in range(3)]


def body():
    return A.host_body("square")


def hosts() -> dict:
    def node(name, kids):
        return W.host_node(name, body(), [W.kid(name, s, A.optic(), at) for s, at in kids])

    sided, unsided, sibs, over = ("SM_Wep_Rifle_Sided_01", "SM_Wep_Rifle_Unsided_01", "SM_Wep_Rifle_Sibs_01", "SM_Wep_Rifle_Over_01")
    return {
        sided: node(sided, [("FrontSight_01", FRONT_AT), ("RearSight_01", REAR_AT), ("Sight_Glass_01", GLASS_AT)]),
        unsided: node(unsided, [("Sights_01", (0.0, 0.10, 0.0))]),
        sibs: node(sibs, [("Sight_01", (0.0, 0.10, 0.0)), ("Sight_02", (0.0, 0.10, 0.2))]),
        over: node(over, [("Sights_01", (0.0, 0.10, 0.0))]),
        "SM_Wep_Rifle_Bare_01": W.host_node("SM_Wep_Rifle_Bare_01", body()),
    }


def rid(name):
    return f"{PACK}/{name}"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    over = rid("SM_Wep_Rifle_Over_01")
    ovr = W.overrides_doc(ids={over: {"mounts": {"sight_rear": {"source": "child_node", "child": "SM_Wep_Rifle_Over_01_Sights_01"}}}})
    return W.by_id(W.build(tmp_path_factory.mktemp("w8h_mounts"), {PACK: {"hosts": hosts()}}, overrides=ovr)[0])


def mounts(built, name):
    return built[rid(name)]["geometry"]["mounts"]


def close(got, want, tol=1e-3):
    assert len(got) == len(want) and all(abs(g - w) <= tol for g, w in zip(got, want)), (got, want)


def test_ac89_the_slot_list_has_seven_entries():
    assert SLOTS == list(M.ATTACH_SLOTS)


def test_ac89_a_host_with_sided_children_gets_child_node_seats(built):
    m = mounts(built, "SM_Wep_Rifle_Sided_01")
    front, rear = m["sight_front"], m["sight_rear"]
    assert front["source"] == rear["source"] == "child_node"
    close(front["point"], seat(FRONT_AT))
    close(rear["point"], seat(REAR_AT))
    assert front["occupied_by"] == ["SM_Wep_Rifle_Sided_01_FrontSight_01"] and front["child_node"] == front["occupied_by"][0]
    assert rear["occupied_by"] == ["SM_Wep_Rifle_Sided_01_RearSight_01"] and rear["child_node"] == rear["occupied_by"][0]


def test_ac89_a_sight_glass_child_still_fills_optic_and_neither_sight_slot(built):
    m = mounts(built, "SM_Wep_Rifle_Sided_01")
    assert m["optic"]["source"] == "child_node" and m["optic"]["occupied_by"] == ["SM_Wep_Rifle_Sided_01_Sight_Glass_01"]
    assert "SM_Wep_Rifle_Sided_01_Sight_Glass_01" not in m["sight_front"]["occupied_by"] + m["sight_rear"]["occupied_by"]


def test_ac89_an_unsided_sights_child_fills_nothing(built):
    m = mounts(built, "SM_Wep_Rifle_Unsided_01")
    child = "SM_Wep_Rifle_Unsided_01_Sights_01"
    assert all(child not in m[s]["occupied_by"] for s in SLOTS)
    assert m["optic"]["source"] == "none"


def test_ac89_two_sibling_sight_children_stay_in_optic(built):
    m = mounts(built, "SM_Wep_Rifle_Sibs_01")
    assert sorted(m["optic"]["occupied_by"]) == ["SM_Wep_Rifle_Sibs_01_Sight_01", "SM_Wep_Rifle_Sibs_01_Sight_02"]
    assert m["sight_front"]["occupied_by"] == [] and m["sight_rear"]["occupied_by"] == []


def test_ac89_every_eligible_host_has_the_seven_mount_keys(built):
    for rec in built.values():
        assert sorted(rec["geometry"]["mounts"]) == sorted(SLOTS)


def test_ac89_a_host_override_names_a_child_for_sight_rear(built):
    m = mounts(built, "SM_Wep_Rifle_Over_01")
    rear = m["sight_rear"]
    assert rear["source"] == "override" and rear["child_node"] == "SM_Wep_Rifle_Over_01_Sights_01"
    close(rear["point"], seat((0.0, 0.10, 0.0)))
    assert m["sight_front"]["source"] == "probe"  # the other sight slot still falls through to the probe


def test_ac89_a_child_seat_is_never_replaced_by_a_probe_seat_and_a_bare_host_gets_the_probe(built):
    assert mounts(built, "SM_Wep_Rifle_Sided_01")["sight_rear"]["source"] == "child_node"
    bare = mounts(built, "SM_Wep_Rifle_Bare_01")
    assert {bare["sight_front"]["source"], bare["sight_rear"]["source"]} <= {"probe", "none"}


# -- the cache key (AC93 / AC78 for the probe) ------------------------------------------------------------------------


def _measure(world, cache, rules):
    host = "SM_Wep_Rifle_Bare_01"
    return geo.measure_cached(world, f"glb/{PACK}/{host}.glb", None, 1.0, "rifle", "ranged", "whole", rules, cache,
                              hold_class="long_gun", genre="modern")


@pytest.fixture()
def one_host(tmp_path):
    _, root = W.write_world(tmp_path, {PACK: {"hosts": {"SM_Wep_Rifle_Bare_01": W.host_node("SM_Wep_Rifle_Bare_01", W.box_rifle())}}})
    return root


def test_ac93_the_probe_code_digest_is_part_of_the_mounts_cache_key(one_host, monkeypatch):
    cache: dict = {}
    rules = W.sight_rules()
    assert _measure(one_host, cache, rules)[1] is False
    assert _measure(one_host, cache, rules)[1] is True
    monkeypatch.setattr(geo, "_PROBE_CODE_DIGEST", "0" * 16)  # as if mount_probe.py had changed
    assert _measure(one_host, cache, rules)[1] is False


def test_ac93_a_probe_parameter_is_part_of_the_mounts_cache_key(one_host):
    cache: dict = {}
    assert _measure(one_host, cache, W.sight_rules())[1] is False
    assert _measure(one_host, cache, W.sight_rules(rear_inset_m=0.02))[1] is False
    assert _measure(one_host, cache, W.sight_rules(rear_inset_m=0.02))[1] is True


def test_ac89_matching_slots_removes_optic_only_for_a_node_that_hits_a_sight_slot():
    tables = load_rules()["attachment_rules"]
    assert M.matching_slots("X_Front_Sight", tables) == ["sight_front"]  # the join `frontsight` is sided; the bare `sight` is dropped
    assert M.matching_slots("X_FrontSight_01", tables) == ["sight_front"]
    assert M.matching_slots("X_Sight_Glass_01", tables) == ["optic"]
    assert M.matching_slots("X_Sights_01", tables) == []
    assert M.matching_slots("X_RearSight_Scope_01", tables) == ["optic", "sight_rear"]  # an optic token other than `sight` keeps optic
