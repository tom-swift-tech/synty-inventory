"""W8i: a host that already carries a baked iron sight or carry handle child refuses that sight slot (AC98; docs/weapon_attachments.md 4.6 item 7).

All hosts but one are the W8h box rifle (axial extent z -0.2525..0.65, middle z 0.19875, +z forward). A child centred at
z 0.45 is on the muzzle half, at z -0.20 (or -0.10) on the rear half. The case numbers (i) to (vi) are those of AC98.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("w8i_world", Path(__file__).parent / "fixtures" / "weapons" / "w8i_world.py")
X = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(X)
W, A = X.W, X.A

from synty_inventory.weapons.rules import validate_rules  # noqa: E402

PACK = "FAKE_Baked"
FRONT_AT, REAR_AT, MID_REAR_AT = (0.0, 0.102, 0.45), (0.0, 0.102, -0.20), (0.0, 0.12, -0.10)


def post():
    return X.sight_post()


def carry():
    return X.block(0.010, 0.020, 0.060)  # 40 mm tall, 0.12 m long, standing on the receiver top (y 0.10) at y 0.12


HOSTS = {
    "SM_Wep_Rifle_Twin_01": [("Fake_Sight_01", post(), FRONT_AT), ("Fake_Sight_02", post(), REAR_AT)],  # (i) the Rifle_Assault_01 shape
    "SM_Wep_Rifle_Single_01": [("Fake_Sights", post(), REAR_AT)],  # (ii) one unsided child, rear half
    "SM_Wep_Rifle_Carry_01": [("Fake_CarryHandle_01", carry(), MID_REAR_AT)],  # (iii)
    "SM_Wep_Rifle_CarryFront_01": [("Fake_CarryHandle_01", carry(), (0.0, 0.12, 0.45))],  # a carry handle is rear whatever its position
    "SM_Wep_Rifle_Charge_01": [("Fake_ChargeHandle_01", X.block(0.004, 0.010, 0.020), (0.03, 0.06, REAR_AT[2]))],  # (iv)
    "SM_Wep_Rifle_Hdl_01": [("Fake_Handle_01", X.block(0.004, 0.010, 0.020), (0.03, 0.03, REAR_AT[2]))],  # a bare Handle low on the gun is a grip, no carry handle (W8j: y 0.03 is under 0.55 of the host height 0.10; at 0.06 it would be one)
    "SM_Wep_Rifle_Glass_01": [("Fake_Sight_Glass_01", post(), (0.0, 0.102, 0.10))],
    "SM_Wep_Rifle_Scoped_01": [("Fake_Scope_01", post(), (0.0, 0.102, 0.10))],
    "SM_Wep_Rifle_Named_01": [("Fake_RearSight_01", post(), REAR_AT), ("Fake_Sights", post(), (0.0, 0.102, 0.0))],  # a sided child beside an unsided one
    "SM_Wep_Rifle_Forced_01": [("Fake_Sights", post(), REAR_AT)],  # carries a host override naming that child for sight_rear
    "SM_Wep_Rifle_Bare_01": [],  # (vi) no baked child; the override below disables its front slot
}


def hosts():
    out = {name: X.rifle(name, kids) for name, kids in HOSTS.items()}
    out["SM_Wep_Rifle_Prism_01"] = X.prism("SM_Wep_Rifle_Prism_01", [("Fake_Sight_01", post(), (0.0, 0.1, 0.06))])  # (v) the probe refuses it
    return out


def world():
    return {PACK: {"hosts": hosts(), "parts": {X.SIGHT_FRONT: W.sight_part, X.SIGHT_REAR: W.sight_part}}}


def overrides():
    forced = f"{PACK}/SM_Wep_Rifle_Forced_01"
    return W.overrides_doc(ids={
        forced: {"mounts": {"sight_rear": {"source": "child_node", "child": "SM_Wep_Rifle_Forced_01_Fake_Sights"}}},
        f"{PACK}/SM_Wep_Rifle_Bare_01": {"mounts": {"sight_front": {"source": "none"}}},
        f"{PACK}/{X.SIGHT_REAR}": {"compatible": {"add": [f"{PACK}/SM_Wep_Rifle_Twin_01"]}},
    })


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return W.by_id(W.build(tmp_path_factory.mktemp("w8i_baked"), world(), overrides=overrides())[0])


def mounts(built, name):
    return built[f"{PACK}/{name}"]["geometry"]["mounts"]


def candidates(built, part, name):
    """``(listed entry, pending entry)`` of sight part ``part`` on host ``name``."""
    att = built[f"{PACK}/{part}"]["attachment"]
    host = f"{PACK}/{name}"
    return (next((e for e in att["compatible_hosts"] if e["host"] == host), None),
            next((e for e in att["pending_hosts"] if e["host"] == host), None))


def refused(m):
    return m["source"] == "none" and m["reason"] == "slot_disabled" and m["point"] is None


# -- (i) --------------------------------------------------------------------------------------------------------


def test_ac98_i_a_pair_of_unsided_sight_children_on_the_two_halves_refuses_both_slots(built):
    m = mounts(built, "SM_Wep_Rifle_Twin_01")
    assert refused(m["sight_front"]) and refused(m["sight_rear"])


def test_ac98_i_the_optic_mount_of_that_host_is_unchanged(built):
    opt = mounts(built, "SM_Wep_Rifle_Twin_01")["optic"]
    assert opt["source"] == "child_node"
    assert opt["occupied_by"] == ["SM_Wep_Rifle_Twin_01_Fake_Sight_01", "SM_Wep_Rifle_Twin_01_Fake_Sight_02"]


def test_ac98_i_no_sight_candidate_listed_or_pending_exists_for_it(built):
    # the rear part has an `add` override for this host (case vi); the front part has none and must have no entry at all
    assert candidates(built, X.SIGHT_FRONT, "SM_Wep_Rifle_Twin_01") == (None, None)


# -- (ii) -------------------------------------------------------------------------------------------------------


def test_ac98_ii_one_unsided_sights_child_on_the_rear_half_refuses_both_slots_since_w8j(built):
    # A3 addendum 3 (W8j, item 8 C): half a pair is never offered, so the front slot, which the probe would have seated and which W8i left
    # alone, is refused with the rear one (the W8i expectation was: rear refused, front a probe seat listed same_pack_fit)
    m = mounts(built, "SM_Wep_Rifle_Single_01")
    assert refused(m["sight_rear"]) and refused(m["sight_front"])
    assert candidates(built, X.SIGHT_REAR, "SM_Wep_Rifle_Single_01") == (None, None)
    assert candidates(built, X.SIGHT_FRONT, "SM_Wep_Rifle_Single_01") == (None, None)


# -- (iii) ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["SM_Wep_Rifle_Carry_01", "SM_Wep_Rifle_CarryFront_01"])
def test_ac98_iii_a_carry_handle_child_refuses_both_slots_wherever_it_stands(built, name):
    m = mounts(built, name)
    assert refused(m["sight_rear"])
    assert refused(m["sight_front"])  # W8j (item 8 C): the pair goes with it (W8i left the front slot a probe seat)


def test_ac98_iii_the_carry_handle_does_not_become_an_optic_child(built):
    # `handle` is in child_never: the optic has no child (S7, spec 3.4 step 3: its seat is the estimated flat one, not none)
    optic = mounts(built, "SM_Wep_Rifle_Carry_01")["optic"]
    assert optic["source"] == "probe" and optic["child_node"] is None and optic["occupied_by"] == []


# -- (iv) -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["SM_Wep_Rifle_Charge_01", "SM_Wep_Rifle_Hdl_01"])
def test_ac98_iv_a_charge_handle_or_a_low_bare_handle_is_no_baked_sight(built, name):
    m = mounts(built, name)
    assert m["sight_front"]["source"] == m["sight_rear"]["source"] == "probe", name


@pytest.mark.parametrize("name", ["SM_Wep_Rifle_Glass_01", "SM_Wep_Rifle_Scoped_01"])
def test_ac98_iv_a_sight_glass_or_a_scope_is_no_baked_iron_sight_but_since_w8j_it_refuses_the_pair_as_an_optic(built, name):
    # W8i: neither is an iron sight child, the seats stayed probe seats. W8j (item 8 A, B): a glass-only host and a body-child host
    # refuse both sight slots as optics (and the glass-only host its optic slot too; see w8j_baked for the full cases)
    m = mounts(built, name)
    assert refused(m["sight_front"]) and refused(m["sight_rear"]), name


# -- (v) --------------------------------------------------------------------------------------------------------


def test_ac98_v_a_slot_the_probe_refused_is_slot_disabled_on_a_baked_host(built):
    # W8k (item 9, AC104): the host carries a baked Fake_Sight_01, so the slots the probe could not seat are refused and not pending any more
    # (W8i left them probe_unavailable). A bare refused host keeps probe_unavailable: see test_weapons_w8k_pending.py.
    m = mounts(built, "SM_Wep_Rifle_Prism_01")
    for slot in ("sight_front", "sight_rear"):
        assert m[slot]["source"] == "none" and m[slot]["reason"] == "slot_disabled", slot


def test_ac98_v_a_slot_that_was_never_probed_keeps_its_reason_unless_the_host_is_baked(tmp_path):
    rules = W.sight_rules()
    del rules["attachment_rules"]["sight_probe"]  # no probe: every free sight slot is no_child_no_probe
    bare = "SM_Wep_Rifle_Bare_01"
    d = W.by_id(W.build(tmp_path, {PACK: {"hosts": {bare: X.rifle(bare), "SM_Wep_Rifle_Twin_01": hosts()["SM_Wep_Rifle_Twin_01"]}}}, rules=rules)[0])
    m = d[f"{PACK}/{bare}"]["geometry"]["mounts"]  # nothing baked: the reason stays
    assert m["sight_front"]["reason"] == m["sight_rear"]["reason"] == "no_child_no_probe"
    twin = d[f"{PACK}/SM_Wep_Rifle_Twin_01"]["geometry"]["mounts"]  # W8k (item 9, AC104): the baked Twin_01 refuses the pending slots
    assert twin["sight_front"]["reason"] == twin["sight_rear"]["reason"] == "slot_disabled"


def test_ac98_v_a_sided_child_and_an_override_are_not_touched(built):
    named = mounts(built, "SM_Wep_Rifle_Named_01")
    assert named["sight_rear"]["source"] == "child_node" and named["sight_rear"]["occupied_by"] == ["SM_Wep_Rifle_Named_01_Fake_RearSight_01"]
    assert refused(named["sight_front"])  # W8j (item 8 C): the unsided Fake_Sights child refuses the slot the probe would have seated
    forced = mounts(built, "SM_Wep_Rifle_Forced_01")["sight_rear"]
    assert forced["source"] == "override" and forced["child_node"] == "SM_Wep_Rifle_Forced_01_Fake_Sights"


# -- (vi) -------------------------------------------------------------------------------------------------------


def test_ac98_vi_an_add_override_still_lists_the_pair_as_override(built):
    listed, pending = candidates(built, X.SIGHT_REAR, "SM_Wep_Rifle_Twin_01")
    assert listed is None and pending["tier"] == "override"  # the seat is none: an add lands in pending_hosts


def test_ac98_vi_a_host_override_refuses_the_front_slot_of_a_host_with_no_baked_child(built):
    m = mounts(built, "SM_Wep_Rifle_Bare_01")
    assert refused(m["sight_front"]) and m["sight_rear"]["source"] == "probe"
    assert candidates(built, X.SIGHT_FRONT, "SM_Wep_Rifle_Bare_01") == (None, None)


# -- the table --------------------------------------------------------------------------------------------------


def test_ac98_the_shipped_table_is_the_one_of_the_spec():
    table = W.sight_rules()["attachment_rules"]["baked_sights"]
    assert table == {"tokens": ["sight", "sights", "ironsight", "ironsights"],
                     "not_tokens": ["glass", "scope", "lens", "reticle", "laser", "red", "dot"],
                     "rear_tokens": ["carryhandle", "carry"],
                     # A3 addendum 3 (W8j, item 8)
                     "glass_tokens": ["glass", "lens", "reticle"],
                     "body_tokens": ["scope", "optic", "optics", "acog", "telescope", "reddot", "reflex", "holo", "holosight"],
                     "handle_tokens": ["handle"],
                     "handle_not_tokens": ["charge", "pump", "bolt", "cocking", "trigger"],
                     "handle_min_height_frac": 0.55,
                     "fused_post": {"bin_m": 0.005, "half_bins": 8, "rise_m": 0.008, "width_min_m": 0.010, "width_max_m": 0.030, "min_pos": 0.6}}
    assert validate_rules(W.sight_rules()) == []
