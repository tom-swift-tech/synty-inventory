"""W8j: baked optics and iron sights refuse their slots as a rule (AC99-AC101; docs/weapon_attachments.md 4.6 item 8, 7).

Hosts are the W8h box rifle (receiver top y 0.10 over z -0.2525..0.0475, +z forward; see w8i_world.py) or the W8j slab (w8j_world.py,
the fused front post cases). Children are named ``<host>_<suffix>``. Every expected value is a LITERAL worked out by hand from the
dimensions in the fixtures, never read from the code under test.

  (A) a body child (a separate optic node) keeps ``optic`` and refuses both sight slots; (B) a glass-only host refuses all three;
  (C) a baked iron sight / carry handle child or a fused front post refuses BOTH sight slots (only slots the probe seated);
  (E) host names (`toy`, `water`, `watergun`) refuse `optic` and both sight slots, whatever the source.
"""

from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

_spec = importlib.util.spec_from_file_location("w8j_world", Path(__file__).parent / "fixtures" / "weapons" / "w8j_world.py")
J = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(J)
W, X, A = J.W, J.X, J.A

from synty_inventory.weapons import mounts as M  # noqa: E402
from synty_inventory.weapons.mounts import baked_children  # noqa: E402
from synty_inventory.weapons.rules import load_rules  # noqa: E402

PACK = "FAKE_W8j"
SCOPE_AT, GLASS_AT = (0.0, 0.10, -0.05), (0.0, 0.1015, 0.0)  # a scope tube on the receiver top, a 3 mm sheet just over it
OPTIC_PART = "SM_Wep_Rifle_Scope_01"  # an optic part; it shares `rifle` with every host and is a twin of the baked Fake_Scope_01 tube
FRONT_AT, REAR_AT = (0.0, 0.054, 0.45), (0.0, 0.102, -0.20)  # a post on the barrel (top y 0.052), a post 2 mm into the receiver top (y 0.10)
SLOTS = ("optic", "sight_front", "sight_rear")
SIGHTS = ("sight_front", "sight_rear")


def rid(name):
    return f"{PACK}/{name}"


def mounts(built, name):
    return built[rid(name)]["geometry"]["mounts"]


def refused(m):
    return m["source"] == "none" and m["reason"] == "slot_disabled" and m["point"] is None and m["occupied_by"] == []


def seated(m):
    return m["source"] == "probe" and m["point"] is not None


def entries(built, part, host):
    """``(listed entry, pending entry)`` of part ``part`` on host ``host``."""
    att = built[rid(part)]["attachment"]
    return (next((e for e in att["compatible_hosts"] if e["host"] == rid(host)), None),
            next((e for e in att["pending_hosts"] if e["host"] == rid(host)), None))


def no_candidate(built, host, parts=(OPTIC_PART, X.SIGHT_FRONT, X.SIGHT_REAR)):
    return all(entries(built, p, host) == (None, None) for p in parts)


def parts():
    return {OPTIC_PART: A.optic, X.SIGHT_FRONT: W.sight_part, X.SIGHT_REAR: W.sight_part}


def rifle(name, kids=()):
    return X.rifle(name, list(kids))


# -- AC99: optic children (A, B) --------------------------------------------------------------------------------

BODY, SHEET, SCOPE_GLASS, BOTH, DOT, BARE = (f"SM_Wep_Rifle_{n}_01" for n in ("Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot"))
NO_OPTIC, KEEP_GLASS, OVR_REAR = "SM_Wep_Rifle_Golf_01", "SM_Wep_Rifle_Hotel_01", "SM_Wep_Rifle_India_01"
PRISM_GLASS = "SM_Wep_Rifle_Juliet_01"


def optic_hosts():
    return {
        BODY: rifle(BODY, [("Fake_Scope_01", A.optic(), SCOPE_AT)]),  # (i)
        SHEET: rifle(SHEET, [("Fake_Sight_Glass_01", J.sheet(), GLASS_AT)]),  # (ii)
        SCOPE_GLASS: rifle(SCOPE_GLASS, [("Fake_Scope_Glass_01", J.sheet(), GLASS_AT)]),  # (iii)
        BOTH: rifle(BOTH, [("Fake_Scope_01", A.optic(), SCOPE_AT), ("Fake_Scope_Glass_01", J.sheet(), (0.0, 0.1015, 0.1))]),  # (iv)
        DOT: rifle(DOT, [("Fake_RedDot_01", A.optic(), SCOPE_AT)]),  # (v)
        BARE: rifle(BARE),
        NO_OPTIC: rifle(NO_OPTIC, [("Fake_Scope_01", A.optic(), SCOPE_AT)]),  # (vi) override optic none
        KEEP_GLASS: rifle(KEEP_GLASS, [("Fake_Sight_Glass_01", J.sheet(), GLASS_AT)]),  # (vi) override child_node on a glass-only host
        OVR_REAR: rifle(OVR_REAR, [("Fake_Scope_01", A.optic(), SCOPE_AT)]),  # an override sight_rear on a body-child host
        PRISM_GLASS: X.prism(PRISM_GLASS, [("Fake_Sight_Glass_01", J.sheet(), (0.0, 0.2, 0.0))]),  # the probe refuses the prism
    }


def optic_overrides():
    return W.overrides_doc(ids={
        rid(NO_OPTIC): {"mounts": {"optic": {"source": "none"}}},
        rid(KEEP_GLASS): {"mounts": {"optic": {"source": "child_node", "child": f"{KEEP_GLASS}_Fake_Sight_Glass_01"}}},
        rid(OVR_REAR): {"mounts": {"sight_rear": {"source": "child_node", "child": f"{OVR_REAR}_Fake_Scope_01"}}},
    })


@pytest.fixture(scope="module")
def optics(tmp_path_factory):
    return W.by_id(W.build(tmp_path_factory.mktemp("w8j_optics"), {PACK: {"hosts": optic_hosts(), "parts": parts()}},
                           overrides=optic_overrides())[0])


@pytest.mark.parametrize("name", [BODY, BOTH, DOT])
def test_ac99_i_iv_v_a_body_child_keeps_the_optic_and_refuses_both_sight_slots(optics, name):
    # (i) Fake_Scope_01; (iv) Fake_Scope_01 with a glass sheet beside it (a body child wins); (v) Fake_RedDot_01 is a body child
    m = mounts(optics, name)
    assert m["optic"]["source"] == "child_node" and m["optic"]["occupied_by"][0] == f"{name}_{'Fake_RedDot_01' if name == DOT else 'Fake_Scope_01'}"
    assert refused(m["sight_front"]) and refused(m["sight_rear"])


def test_ac99_i_an_optic_part_is_still_a_candidate_on_a_body_child_host(optics):
    for name in (BODY, BOTH, DOT):
        listed, pending = entries(optics, OPTIC_PART, name)
        assert listed is not None and listed["tier"] == "twin" and pending is None, name


def test_ac99_i_no_sight_candidate_exists_on_a_body_child_host(optics):
    for name in (BODY, BOTH, DOT):
        assert no_candidate(optics, name, (X.SIGHT_FRONT, X.SIGHT_REAR)), name


@pytest.mark.parametrize("name", [SHEET, SCOPE_GLASS])
def test_ac99_ii_iii_a_glass_only_host_refuses_optic_and_both_sight_slots(optics, name):
    # (ii) only Fake_Sight_Glass_01 (a 3 mm sheet); (iii) only Fake_Scope_Glass_01: the optic body is fused into the host
    m = mounts(optics, name)
    assert all(refused(m[s]) for s in SLOTS), name
    assert no_candidate(optics, name), name  # no optic or sight candidate, listed or pending


def test_ac99_ii_the_glass_child_that_was_the_optics_child_node_seat_stops_being_one(optics):
    assert mounts(optics, SHEET)["optic"]["child_node"] is None


def test_ac99_a_glass_only_host_whose_sight_slots_the_probe_refused_has_them_disabled_too(optics):
    m = mounts(optics, PRISM_GLASS)
    assert refused(m["optic"])  # the optic slot is rewritten whatever its source
    for slot in SIGHTS:
        assert refused(m[slot]), slot  # W8k (item 9, AC104 ii): the pending reason is rewritten too (W8j kept probe_unavailable)


def test_ac99_a_host_with_no_optic_child_is_not_touched(optics):
    m = mounts(optics, BARE)
    # S7 (spec 3.4 step 3): the bare host's optic is the estimated flat seat on its smooth top, not a none slot
    assert seated(m["optic"]) and m["optic"]["child_node"] is None and m["optic"]["occupied_by"] == []
    assert seated(m["sight_front"]) and seated(m["sight_rear"])


def test_ac99_vi_an_optic_override_none_makes_the_optic_none(optics):
    m = mounts(optics, NO_OPTIC)
    assert refused(m["optic"])  # an override `none` is categorical, and the scope child is no seat any more (occupied_by is empty)
    # the scope child is a body child all the same, so no sight slot is a probe seat; here the tube stays in the probe mesh (it is no
    # longer in a slot) and the probe refuses the host itself: W8k (item 9) turns that pending reason into slot_disabled (A)
    assert all(refused(m[s]) for s in SIGHTS)


def test_ac99_vi_an_override_child_node_on_a_glass_only_host_keeps_that_seat(optics):
    m = mounts(optics, KEEP_GLASS)
    assert m["optic"]["source"] == "override" and m["optic"]["child_node"] == f"{KEEP_GLASS}_Fake_Sight_Glass_01"
    assert refused(m["sight_front"]) and refused(m["sight_rear"])  # the sight slots are the glass-only rule's


def test_an_override_sight_mount_is_never_touched_and_the_other_slot_still_goes(optics):
    m = mounts(optics, OVR_REAR)
    assert m["sight_rear"]["source"] == "override" and m["sight_rear"]["child_node"] == f"{OVR_REAR}_Fake_Scope_01"
    assert refused(m["sight_front"])  # (A): the probe seat goes, the override stays
    assert m["optic"]["source"] == "child_node"


# -- AC100: the iron pair (C), handles, the fused front post (D) -------------------------------------------------

POST_FRONT, POST_REAR, SIDED_FRONT, SIDED_REAR = (f"SM_Wep_Rifle_{n}_01" for n in ("Kilo", "Lima", "Mike", "November"))
HANDLE_HIGH, HANDLE_LOW, CHARGE_HIGH, CHARGE_LOW, PUMP_HIGH, PUMP_LOW = (
    f"SM_Wep_Rifle_{n}_01" for n in ("Oscar", "Papa", "Quebec", "Romeo", "Sierra", "Tango"))
CARRY = "SM_Wep_Rifle_Uniform_01"
ALREADY_NONE = "SM_Wep_Rifle_Victor_01"
HDL_AT_HIGH, HDL_AT_LOW = (0.03, 0.07, REAR_AT[2]), (0.03, 0.03, REAR_AT[2])  # centre y 0.07 is 70 % of the host height 0.10, y 0.03 is 30 %


def handle():
    return X.block(0.004, 0.010, 0.020)


def iron_hosts():
    return {
        POST_FRONT: rifle(POST_FRONT, [("Fake_Sights", X.sight_post(), FRONT_AT)]),  # (i) an unsided post on the muzzle half
        POST_REAR: rifle(POST_REAR, [("Fake_Sights", X.sight_post(), REAR_AT)]),  # (ii) one on the rear half
        SIDED_FRONT: rifle(SIDED_FRONT, [("Fake_FrontSight_01", X.sight_post(), FRONT_AT)]),  # (iv) a sided front child, no rear
        SIDED_REAR: rifle(SIDED_REAR, [("Fake_RearSight_01", X.sight_post(), REAR_AT)]),  # the mirror image
        HANDLE_HIGH: rifle(HANDLE_HIGH, [("Fake_Handle_01", handle(), HDL_AT_HIGH)]),  # (iii)
        HANDLE_LOW: rifle(HANDLE_LOW, [("Fake_Handle_01", handle(), HDL_AT_LOW)]),
        CHARGE_HIGH: rifle(CHARGE_HIGH, [("Fake_ChargeHandle_01", handle(), HDL_AT_HIGH)]),
        CHARGE_LOW: rifle(CHARGE_LOW, [("Fake_ChargeHandle_01", handle(), HDL_AT_LOW)]),
        PUMP_HIGH: rifle(PUMP_HIGH, [("Fake_PumpHandle_01", handle(), HDL_AT_HIGH)]),
        PUMP_LOW: rifle(PUMP_LOW, [("Fake_PumpHandle_01", handle(), HDL_AT_LOW)]),
        CARRY: rifle(CARRY, [("Fake_CarryHandle_01", X.block(0.010, 0.020, 0.060), (0.0, 0.12, -0.10))]),  # a `carryhandle` at any height
        ALREADY_NONE: rifle(ALREADY_NONE, [("Fake_Sights", X.sight_post(), REAR_AT)]),  # carries an override naming sight_front none
    }


def iron_overrides():
    return W.overrides_doc(ids={
        rid(ALREADY_NONE): {"mounts": {"sight_front": {"source": "none"}}},
        rid(X.SIGHT_REAR): {"compatible": {"add": [rid(POST_FRONT)]}},
    })


@pytest.fixture(scope="module")
def iron(tmp_path_factory):
    return W.by_id(W.build(tmp_path_factory.mktemp("w8j_iron"), {PACK: {"hosts": iron_hosts(), "parts": parts()}}, overrides=iron_overrides())[0])


@pytest.mark.parametrize("name", [POST_FRONT, POST_REAR, CARRY, HANDLE_HIGH])
def test_ac100_i_ii_iii_a_baked_front_post_rear_sight_or_high_handle_refuses_both_slots_never_one(iron, name):
    m = mounts(iron, name)
    assert refused(m["sight_front"]) and refused(m["sight_rear"]), name


@pytest.mark.parametrize("name", [HANDLE_LOW, CHARGE_HIGH, CHARGE_LOW, PUMP_HIGH, PUMP_LOW])
def test_ac100_iii_a_low_handle_a_charge_handle_or_a_pump_handle_at_any_height_leaves_both_seated(iron, name):
    m = mounts(iron, name)
    assert seated(m["sight_front"]) and seated(m["sight_rear"]), name


def test_ac100_iv_a_sided_child_node_front_sight_keeps_its_seat_and_the_probe_rear_goes(iron):
    m = mounts(iron, SIDED_FRONT)
    assert m["sight_front"]["source"] == "child_node" and m["sight_front"]["occupied_by"] == [f"{SIDED_FRONT}_Fake_FrontSight_01"]
    assert refused(m["sight_rear"])


def test_ac100_iv_a_sided_child_node_rear_sight_keeps_its_seat_and_the_probe_front_goes(iron):
    m = mounts(iron, SIDED_REAR)
    assert m["sight_rear"]["source"] == "child_node" and m["sight_rear"]["occupied_by"] == [f"{SIDED_REAR}_Fake_RearSight_01"]
    assert refused(m["sight_front"])


def test_ac100_vii_a_slot_that_is_already_none_keeps_its_reason_and_an_override_add_still_lists_the_pair(iron):
    m = mounts(iron, ALREADY_NONE)
    assert m["sight_front"]["source"] == "none" and m["sight_front"]["reason"] == "slot_disabled"  # the override's `none`
    assert refused(m["sight_rear"])  # and the rest of the pair goes with the post
    listed, pending = entries(iron, X.SIGHT_REAR, POST_FRONT)  # a human `add` still lands in pending_hosts (the seat is none)
    assert listed is None and pending["tier"] == "override"
    assert entries(iron, X.SIGHT_FRONT, POST_FRONT) == (None, None)


def test_ac100_no_sight_candidate_exists_for_a_refused_pair(iron):
    for name in (POST_FRONT, POST_REAR, CARRY, HANDLE_HIGH):
        if name == POST_FRONT:
            assert entries(iron, X.SIGHT_FRONT, name) == (None, None)  # the rear part has an `add` there (above)
        else:
            assert no_candidate(iron, name, (X.SIGHT_FRONT, X.SIGHT_REAR)), name


# -- AC100 (v), (vi): the fused front post -----------------------------------------------------------------------

FLAT, P80, P40, LOW80, NARROW80, BROAD80, STEP80, SUPP80 = (
    f"SM_Wep_Rifle_{n}_01" for n in ("Whiskey", "Xray", "Yankee", "Zulu", "Able", "Baker", "Charles", "Dog"))

def slab_hosts():
    wide08, wide04, narrow08, broad08 = J.POST_WIDE_08, J.POST_WIDE_04, J.POST_NARROW_08, J.POST_BROAD_08
    # a 14 mm tall, 20 mm wide block baked as a muzzle device on the slab: out of the probe mesh, so it is no fused post
    suppressor = X.block(0.020, 0.007, 0.0095)
    return {
        FLAT: J.slab_host(FLAT),  # the control: no post
        P80: J.slab_host(P80, [(*wide08, 0.014)]),  # a 20 mm wide, 14 mm tall post at 0.8: refused
        P40: J.slab_host(P40, [(*wide04, 0.014)]),  # the same at 0.4 (also (vi): a rear-half block is ignored)
        LOW80: J.slab_host(LOW80, [(*wide08, 0.006)]),  # 6 mm tall: under rise_m
        NARROW80: J.slab_host(NARROW80, [(*narrow08, 0.014)]),  # one 5 mm bin: under width_min_m
        BROAD80: J.slab_host(BROAD80, [(*broad08, 0.014)]),  # eight bins, 40 mm: over width_max_m
        STEP80: J.slab_host(STEP80, steps=[(wide08[0], 0.014)]),  # the baseline steps up by 14 mm and stays: a step, not a post
        SUPP80: J.slab_host(SUPP80, kids=[("Fake_Suppressor_01", suppressor, (0.0, J.SLAB_TOP + 0.007, 0.475))]),
    }


@pytest.fixture(scope="module")
def slabs(tmp_path_factory):
    return W.by_id(W.build(tmp_path_factory.mktemp("w8j_slabs"), {PACK: {"hosts": slab_hosts(), "parts": parts()}})[0])


def test_ac100_v_a_14_mm_post_20_mm_wide_at_0_8_is_a_fused_front_post_and_refuses_both_slots(slabs):
    m = mounts(slabs, P80)
    assert refused(m["sight_front"]) and refused(m["sight_rear"])
    assert no_candidate(slabs, P80, (X.SIGHT_FRONT, X.SIGHT_REAR))


@pytest.mark.parametrize("name", [FLAT, P40, LOW80, NARROW80, BROAD80, STEP80, SUPP80])
def test_ac100_v_vi_the_negatives_leave_both_seated(slabs, name):
    # FLAT no post; P40 the same post at 0.4 (position under 0.6; also a rear-half block of 14 mm: no effect); LOW80 6 mm tall;
    # NARROW80 4 mm wide (one bin); BROAD80 40 mm wide; STEP80 a 14 mm step of the baseline; SUPP80 the post is a baked muzzle device
    m = mounts(slabs, name)
    assert seated(m["sight_front"]) and seated(m["sight_rear"]), name


def test_ac100_v_the_negatives_are_listed_candidates_for_the_sight_parts(slabs):
    for name in (FLAT, P40, STEP80):
        for part in (X.SIGHT_FRONT, X.SIGHT_REAR):
            listed, pending = entries(slabs, part, name)
            assert listed is not None and listed["tier"] == "same_pack_fit" and pending is None, (part, name)


def test_ac100_v_the_detector_reads_the_probe_mesh_so_the_muzzle_child_is_in_its_slot(slabs):
    assert mounts(slabs, SUPP80)["muzzle"]["occupied_by"] == [f"{SUPP80}_Fake_Suppressor_01"]


def test_ac100_v_the_numbers_are_parameters_a_lower_min_pos_catches_the_post_at_0_4(tmp_path):
    rules = W.sight_rules()
    rules["attachment_rules"]["baked_sights"]["fused_post"]["min_pos"] = 0.3
    d = W.by_id(W.build(tmp_path, {PACK: {"hosts": {P40: slab_hosts()[P40]}, "parts": parts()}}, rules=rules)[0])
    assert refused(mounts(d, P40)["sight_front"]) and refused(mounts(d, P40)["sight_rear"])


# -- AC101: host names (E) ---------------------------------------------------------------------------------------

TOY, WATERGUN, WATERPISTOL, WATERFALL, PLAIN, FLARE = (
    "SM_Wep_ToyGun_Rifle_01", "SM_Wep_Watergun_01", "SM_Wep_WaterPistol_01", "SM_Wep_Waterfall_Rifle_01", "SM_Wep_Rifle_Plain_01",
    "SM_Wep_Pistol_Flare_01")
TOY_OVR = "SM_Wep_ToyGun_Rifle_02"


def name_hosts():
    scoped = lambda n: rifle(n, [("Fake_Scope_01", A.optic(), SCOPE_AT)])  # noqa: E731
    return {TOY: scoped(TOY), WATERGUN: rifle(WATERGUN), WATERPISTOL: rifle(WATERPISTOL), WATERFALL: rifle(WATERFALL), PLAIN: rifle(PLAIN),
            FLARE: scoped(FLARE), TOY_OVR: scoped(TOY_OVR)}


@pytest.fixture(scope="module")
def names(tmp_path_factory):
    ovr = W.overrides_doc(ids={
        rid(TOY_OVR): {"mounts": {"optic": {"source": "child_node", "child": f"{TOY_OVR}_Fake_Scope_01"}}},
        rid(OPTIC_PART): {"compatible": {"add": [rid(WATERGUN)]}},
    })
    return W.by_id(W.build(tmp_path_factory.mktemp("w8j_names"), {PACK: {"hosts": name_hosts(), "parts": parts()}}, overrides=ovr)[0])


@pytest.mark.parametrize("name", [TOY, WATERGUN, WATERPISTOL])
def test_ac101_a_toy_or_water_host_has_optic_and_both_sight_slots_disabled(names, name):
    m = mounts(names, name)
    assert all(refused(m[s]) for s in SLOTS), name  # the toy host's baked scope child included (occupied_by is empty)


def test_ac101_the_toy_hosts_scope_child_is_no_seat_and_the_muzzle_slot_is_untouched(names):
    m = mounts(names, TOY)
    assert m["optic"]["child_node"] is None and m["muzzle"]["source"] == "probe"


def test_ac101_no_optic_or_sight_candidate_exists_on_the_toy_and_water_hosts(names):
    for name in (TOY, WATERPISTOL):
        assert no_candidate(names, name), name


def test_ac101_a_word_that_only_starts_with_water_and_a_plain_host_are_not_excluded(names):
    for name in (WATERFALL, PLAIN):
        m = mounts(names, name)
        assert seated(m["optic"]) and m["optic"]["reason"] is None, name  # nothing disabled it (S7, spec 3.4 step 3: a flat optic seat)
        assert seated(m["sight_front"]) and seated(m["sight_rear"]), name


def test_ac101_a_flare_pistol_is_a_tool_host_and_loses_every_slot(names):
    # A8 erratum (2026-10-26): `flare` alone is a tool token, so the host's baked scope child is no seat either (the shipped outcome for the real name)
    m = mounts(names, FLARE)
    assert all(refused(m[s]) for s in (*SLOTS, "muzzle")), "flare pistol"
    assert m["optic"]["child_node"] is None


def test_ac101_the_sight_name_rule_alone_takes_the_sights_and_leaves_the_optic_child(tmp_path):
    # the mechanism of the old test (attach_host_never `flare` for the sight slots only), built with a tool row without `flare`
    rules = J.W.sight_rules()
    rules["attachment_rules"]["attach_host_class"]["tool"] = [t for t in rules["attachment_rules"]["attach_host_class"]["tool"] if t != "flare"]
    built = J.W.by_id(J.W.build(tmp_path, {PACK: {"hosts": {FLARE: rifle(FLARE, [("Fake_Scope_01", A.optic(), SCOPE_AT)])}, "parts": parts()}}, rules=rules)[0])
    m = mounts(built, FLARE)
    assert m["optic"]["source"] == "child_node" and m["optic"]["occupied_by"] == [f"{FLARE}_Fake_Scope_01"]
    assert refused(m["sight_front"]) and refused(m["sight_rear"])
    assert m["muzzle"]["source"] == "probe"


def test_ac101_an_add_override_still_lists_the_pair_on_an_excluded_host(names):
    listed, pending = entries(names, OPTIC_PART, WATERGUN)
    assert listed is None and pending["tier"] == "override"  # the seat is none, so an add lands in pending_hosts


def test_ac101_an_id_override_of_the_optic_slot_beats_the_name_rule(names):
    m = mounts(names, TOY_OVR)
    assert m["optic"]["source"] == "override" and m["optic"]["child_node"] == f"{TOY_OVR}_Fake_Scope_01"
    assert refused(m["sight_front"]) and refused(m["sight_rear"])  # the sight slots stay with the name rule


def test_ac101_excluded_slots_reads_whole_name_tokens_for_the_optic_row():
    tables = load_rules()["attachment_rules"]
    assert M.excluded_slots(TOY, tables) == ["optic", "sight_front", "sight_rear"]
    # A6 (W8n): water is a tool-class token (attach_host_class) and the tool class refuses all seven slots, on top of the optic row's tokens
    assert M.excluded_slots("SM_Wep_WaterPistol_01", tables) == ["optic", "muzzle", "underbarrel", "magazine", "laser_light", "sight_front", "sight_rear"]
    assert M.excluded_slots("SM_Wep_Pistol_Flare_01", tables) == ["optic", "muzzle", "underbarrel", "magazine", "laser_light", "sight_front", "sight_rear"]  # A8 erratum (2026-10-26): `flare` alone is a tool token
    assert M.excluded_slots("SM_Wep_Waterfall_Rifle_01", tables) == []
    assert M.excluded_slots("SM_Wep_Rifle_Toyota_01", tables) == []


# -- the classes of baked children (unit) ------------------------------------------------------------------------


def test_baked_children_classes_unit():
    tables = load_rules()["attachment_rules"]
    host = np.array([[0.0, 0.0, 0.0], [0.04, 0.10, 0.9]])  # a 0.10 tall host, forward z
    small = np.array([[0.0, 0.0, 0.0], [0.01, 0.01, 0.01]])

    def at(y):
        return small + np.array([0.0, y, 0.0])

    kids = {"X_Fake_Scope_01": at(0.09), "X_Fake_Scope_Glass_01": at(0.09), "X_Fake_RedDot_01": at(0.09), "X_Fake_Sights": at(0.09),
            "X_Fake_CarryHandle_01": at(0.01), "X_Fake_Handle_High_01": at(0.07), "X_Fake_Handle_Low_01": at(0.01),
            "X_Fake_ChargeHandle_01": at(0.09), "X_Fake_Stock_01": at(0.09)}
    got = baked_children(kids, "X_01", tables, kids.get, host, {"forward": "+z", "up": "+y"}, 1.0)
    assert got == {"glass": ["X_Fake_Scope_Glass_01"], "body": ["X_Fake_RedDot_01", "X_Fake_Scope_01"],
                   "handle": ["X_Fake_CarryHandle_01", "X_Fake_Handle_High_01"], "iron": ["X_Fake_Sights"]}


# -- tables and validation ---------------------------------------------------------------------------------------


def _rules_with(**patch):
    rules = deepcopy(load_rules())
    table = rules["attachment_rules"]["baked_sights"]
    for key, value in patch.items():
        if value is None:
            table.pop(key, None)
        else:
            table[key] = value
    return rules


def test_the_shipped_baked_sights_table_is_the_one_of_the_spec():
    table = load_rules()["attachment_rules"]["baked_sights"]
    assert table["glass_tokens"] == ["glass", "lens", "reticle"]
    assert table["body_tokens"] == ["scope", "optic", "optics", "acog", "telescope", "reddot", "reflex", "holo", "holosight"]
    assert table["handle_tokens"] == ["handle"] and table["handle_not_tokens"] == ["charge", "pump", "bolt", "cocking", "trigger"]
    assert table["handle_min_height_frac"] == 0.55
    assert table["fused_post"] == {"bin_m": 0.005, "half_bins": 8, "rise_m": 0.008, "width_min_m": 0.010, "width_max_m": 0.030, "min_pos": 0.6}
    never = load_rules()["attachment_rules"]["attach_host_never"]
    assert never["optic"] == ["water", "watergun", "toy", "prop"]  # A5 item 0: `prop` names every slot (appended here)
    assert never["sight_front"] == never["sight_rear"] == ["flare", "flaregun", "prop", "water", "watergun", "toy"]


def test_validation_accepts_the_shipped_rules_and_rejects_each_broken_table():
    from synty_inventory.weapons.rules import validate_rules

    assert validate_rules(load_rules()) == []
    good = load_rules()["attachment_rules"]["baked_sights"]["fused_post"]
    broken = [
        _rules_with(fused_post={**good, "rise_m": 0.0}),  # out of range
        _rules_with(fused_post={**good, "width_min_m": 0.05}),  # min over max
        _rules_with(fused_post={k: v for k, v in good.items() if k != "min_pos"}),  # a missing key
        _rules_with(fused_post={**good, "extra": 1}),  # an unknown key
        _rules_with(fused_post={**good, "half_bins": 8.5}),  # not an integer
        _rules_with(glass_tokens=["Glass"]),  # not lowercase
        _rules_with(body_tokens="scope"),  # not a list
        _rules_with(handle_min_height_frac=1.5),  # out of 0..1
        _rules_with(handle_min_height_frac=None),  # handle_tokens without its height fraction
        _rules_with(mystery_tokens=["x"]),  # an unknown key
    ]
    for rules in broken:
        assert validate_rules(rules), rules["attachment_rules"]["baked_sights"]


# -- versions and the cache key (AC103) --------------------------------------------------------------------------


def test_ac103_the_versions_and_digests():
    import synty_inventory.weapons as pkg
    from synty_inventory.weapons.rules import attach_rules_digest, weapon_rules_digest

    assert pkg.WEAPON_ATTACH_VERSION == 16 and pkg.WEAPON_GEOMETRY_VERSION == 6
    assert weapon_rules_digest(load_rules()) == "7b9829af37328fe7"  # the W7 digest: the attachment tables are not part of it
    base = attach_rules_digest(load_rules())
    assert attach_rules_digest(_rules_with(fused_post={**load_rules()["attachment_rules"]["baked_sights"]["fused_post"], "rise_m": 0.009})) != base
    assert attach_rules_digest(_rules_with(glass_tokens=["glass", "lens"])) != base
    never = deepcopy(load_rules())
    never["attachment_rules"]["attach_host_never"]["optic"] = ["toy"]
    assert attach_rules_digest(never) != base
    assert weapon_rules_digest(never) == "7b9829af37328fe7"


def _measure(world, cache, rules):
    from synty_inventory.weapons import geometry as geo

    return geo.measure_cached(world, f"glb/{PACK}/{FLAT}.glb", None, 1.0, "rifle", "ranged", "whole", rules, cache, hold_class="long_gun", genre="modern")


@pytest.fixture()
def one_slab(tmp_path):
    return W.write_world(tmp_path, {PACK: {"hosts": {FLAT: J.slab_host(FLAT)}}})[1]


@pytest.mark.parametrize("patch", [
    {"fused_post": {"bin_m": 0.005, "half_bins": 8, "rise_m": 0.009, "width_min_m": 0.010, "width_max_m": 0.030, "min_pos": 0.6}},
    {"fused_post": {"bin_m": 0.005, "half_bins": 8, "rise_m": 0.008, "width_min_m": 0.010, "width_max_m": 0.030, "min_pos": 0.7}},
    {"glass_tokens": ["glass", "lens"]},
    {"body_tokens": ["scope", "optic"]},
    {"handle_min_height_frac": 0.6},
    {"handle_not_tokens": ["charge"]},
])
def test_ac103_a_baked_sights_table_value_is_part_of_the_mounts_cache_key(one_slab, patch):
    cache: dict = {}
    assert _measure(one_slab, cache, W.sight_rules())[1] is False
    assert _measure(one_slab, cache, W.sight_rules())[1] is True
    rules = W.sight_rules()
    rules["attachment_rules"]["baked_sights"].update(patch)
    assert _measure(one_slab, cache, rules)[1] is False, patch  # a miss: the mounts are measured again


@pytest.mark.parametrize("digest", ["_MOUNTS_CODE_DIGEST", "_PROBE_CODE_DIGEST"])
def test_ac103_the_detector_and_rule_code_digests_are_part_of_the_mounts_cache_key(one_slab, monkeypatch, digest):
    from synty_inventory.weapons import geometry as geo

    cache: dict = {}
    assert _measure(one_slab, cache, W.sight_rules())[1] is False
    assert _measure(one_slab, cache, W.sight_rules())[1] is True
    monkeypatch.setattr(geo, digest, "0" * 16)  # as if mounts.py (the rules A, B, C) or mount_probe.py (the detector D) had changed
    assert _measure(one_slab, cache, W.sight_rules())[1] is False


def test_ac103_the_host_name_table_is_part_of_the_mounts_cache_key(one_slab):
    cache: dict = {}
    assert _measure(one_slab, cache, W.sight_rules())[1] is False
    rules = W.sight_rules()
    rules["attachment_rules"]["attach_host_never"]["optic"] = ["toy"]
    assert _measure(one_slab, cache, rules)[1] is False
