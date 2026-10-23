"""W8b: host mounts from the baked child meshes (AC66, AC68; docs/weapon_attachments.md 4.1, 4.2, D-3, D-8, D-9).

The FAKE_Mount hosts of ``fixtures/weapons/w8a_attach.py`` carry children at known translations; every expected seat in
that module is a literal worked out by hand from the child's own mesh plus the node translation, never read from the code
under test. The slot list, the sources and the reasons below are literals too.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("w8a_attach", Path(__file__).parent / "fixtures" / "weapons" / "w8a_attach.py")
A = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A)

from synty_inventory.weapons import mounts as M  # noqa: E402
from synty_inventory.weapons.geometry import measure_weapon_detail  # noqa: E402
from synty_inventory.weapons.rules import load_rules  # noqa: E402

SLOTS = ["optic", "muzzle", "underbarrel", "magazine", "laser_light", "sight_front", "sight_rear"]
P = A.MOUNT_PACK
MOUNT, DOUBLE, PLAIN = (f"{P}/SM_Wep_Rifle_{n}_01" for n in ("Mount", "Double", "Plain"))
PISTOL, GRENADE, HULL = f"{P}/SM_Wep_Pistol_Mount_01", f"{P}/SM_Wep_Grenade_Mount_01", f"{P}/SM_Wep_Rifle_Hull_01"
TILT, SHARED = f"{P}/SM_Wep_Rifle_Tilt_01", f"{P}/SM_Wep_Rifle_Shared_01"


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    directory, _, _, root = A.build_mount_world(tmp_path_factory.mktemp("w8b_mounts"))
    return directory, root


def rec(world, rid):
    return next(w for w in world[0]["weapons"] if w["id"] == rid)


def mounts(world, rid):
    return rec(world, rid)["geometry"]["mounts"]


def close(got, want, tol=1e-3):
    assert len(got) == len(want) and all(abs(g - w) <= tol for g, w in zip(got, want)), (got, want)


def detail_of(world, host, overrides=None, rules=None):
    """The uncached measurement of one host with an explicit categorical mount-override mapping."""
    root = world[1]
    asset = host.split("/", 1)[1]
    glb = root / ("glb/FAKE_Mount/shared.glb" if asset == "SM_Wep_Rifle_Shared_01" else f"glb/FAKE_Mount/{asset}.glb")
    node = "Rifle_Shared" if asset == "SM_Wep_Rifle_Shared_01" else None
    return measure_weapon_detail(glb, node, 1.0, "rifle", "ranged", "whole", rules or load_rules(), hold_class="long_gun",
                                 genre="modern", mount_overrides=overrides, with_mounts=True)


# --- AC66: seats from the child nodes --------------------------------------------------------------------------------


def test_ac66_every_eligible_host_carries_all_seven_slots_and_the_others_carry_null(world):
    for rid, hold in [(MOUNT, "long_gun"), (DOUBLE, "long_gun"), (PLAIN, "long_gun"), (PISTOL, "one_hand"), (HULL, "long_gun")]:
        r = rec(world, rid)
        assert (r["role"], r["kind"], r["hold_class"]) == ("whole", "ranged", hold)
        assert sorted(r["geometry"]["mounts"]) == sorted(SLOTS)
    g = rec(world, GRENADE)
    assert (g["kind"], g["hold_class"]) == ("thrown", "thrown")
    assert g["geometry"]["mounts"] is None  # D-9, whatever its children are called


def test_ac66_optic_and_magazine_seat_on_the_child_foot_with_the_child_foot_length_as_span(world):
    m = mounts(world, MOUNT)
    optic, mag = m["optic"], m["magazine"]
    assert optic["source"] == "child_node" and mag["source"] == "child_node"
    close(optic["point"], A.SCOPE_SEAT)
    close(mag["point"], A.MAG_SEAT)
    assert optic["occupied_by"] == [f"{MOUNT.split('/')[1]}_Scope"] and optic["child_node"] == optic["occupied_by"][0]
    assert mag["occupied_by"] == [f"{MOUNT.split('/')[1]}_Mag"] and mag["child_node"] == mag["occupied_by"][0]
    assert abs(optic["span_m"] - 0.06) <= 1e-3 and abs(mag["span_m"] - 0.04) <= 1e-3
    assert optic["span_source"] == mag["span_source"] == "child_foot"
    # the frame (3.1): optic up is the host up, magazine up is down, forward is the host forward
    assert optic["up"] == [0.0, 1.0, 0.0] and mag["up"] == [0.0, -1.0, 0.0]
    assert optic["forward"] == mag["forward"] == [0.0, 0.0, 1.0]
    assert optic["bore_d_m"] is None and optic["bore_source"] is None and optic["reason"] is None
    assert optic["confidence"] == 0.9


def test_ac66_underbarrel_and_laser_children_hang_below_the_host_up(world):
    m = mounts(world, PISTOL)
    assert (m["underbarrel"]["source"], m["laser_light"]["source"]) == ("child_node", "child_node")
    close(m["underbarrel"]["point"], A.FOREGRIP_SEAT)
    close(m["laser_light"]["point"], A.LASER_SEAT)
    assert m["underbarrel"]["up"] == m["laser_light"]["up"] == [0.0, -1.0, 0.0]
    assert abs(m["underbarrel"]["span_m"] - 0.06) <= 1e-3 and abs(m["laser_light"]["span_m"] - 0.06) <= 1e-3


def test_ac66_a_trigger_child_is_never_a_mount_in_any_slot(world):
    m = mounts(world, MOUNT)
    assert all("Trigger" not in n for slot in SLOTS for n in m[slot]["occupied_by"] + [m[slot]["child_node"] or ""])
    assert m["underbarrel"]["source"] == m["laser_light"]["source"] == "none"


def test_ac66_two_magazines_are_both_listed_sorted_and_the_seat_comes_from_the_larger(world):
    mag = mounts(world, DOUBLE)["magazine"]
    small, large = "SM_Wep_Rifle_Double_01_Mag_A_Small", "SM_Wep_Rifle_Double_01_Mag_B_Large"
    assert mag["occupied_by"] == [small, large]  # sorted raw names, both of them
    assert mag["child_node"] == large and mag["source"] == "child_node"
    close(mag["point"], A.BIG_MAG_SEAT)
    assert abs(mag["span_m"] - 0.06) <= 1e-3 and mag["span_source"] == "child_foot"
    assert "mount_ambiguous" in rec(world, DOUBLE)["review"]["reasons"]
    assert "mount_ambiguous" not in rec(world, MOUNT)["review"]["reasons"]
    assert mag["confidence"] == 0.6


def test_ac66_a_shared_glb_host_sees_only_the_children_below_its_selected_node(world):
    m = mounts(world, SHARED)
    assert m["optic"]["occupied_by"] == ["Rifle_Shared_Scope"]
    close(m["optic"]["point"], (1.0 + 0.005, 0.10, 0.15))  # scene space, the selected node sits 1 m along x
    assert m["magazine"]["source"] == "none" and m["magazine"]["occupied_by"] == []  # Other_Rifle_Mag is another gun's


def test_ac66_a_child_in_a_collision_hull_node_is_dropped(world):
    r = rec(world, HULL)
    assert r["geometry"]["mounts"]["optic"]["source"] == "none" and r["geometry"]["mounts"]["optic"]["occupied_by"] == []
    assert r["geometry"]["bounds"]["max"][1] < 0.11  # the hull (scope at y 0.10..0.18) is not part of the measured mesh either


def test_ac66_a_rotated_child_node_keeps_its_seat_but_is_capped_at_confidence_04(world):
    optic = mounts(world, TILT)["optic"]
    close(optic["point"], A.YAWED_SCOPE_SEAT)
    assert abs(optic["span_m"] - 0.06) <= 1e-3
    assert optic["confidence"] == 0.4


def test_ac66_the_body_of_the_gun_is_not_a_child_of_itself(world):
    # a host whose own node name carries a slot token must not occupy that slot (it would empty the muzzle probe)
    flat = A.mount_roots("SM_Wep_Rifle_Plain_01")
    flat[0]["name"] = "SM_Wep_Rifle_Plain_01_Scope"
    body = [{"name": "Root", "children": flat}]
    import tempfile
    d, _, _, _ = A.build_mount_world(Path(tempfile.mkdtemp()), roots={"SM_Wep_Rifle_Plain_01": body})
    m = next(w for w in d["weapons"] if w["id"] == PLAIN)["geometry"]["mounts"]
    assert m["optic"]["source"] == "none"  # the 'Scope' node is the whole gun: the body, not a baked child
    assert m["muzzle"]["source"] == "probe"


# --- AC66: precedence override > child_node > probe > none ------------------------------------------------------------


def test_ac66_resolve_slot_takes_the_first_rung_that_exists():
    o, c, p = {"source": "override"}, {"source": "child_node"}, {"source": "probe"}
    assert M.resolve_slot(o, c, p) is o
    assert M.resolve_slot(None, c, p) is c
    assert M.resolve_slot(None, None, p) is p
    last = M.resolve_slot(None, None, None)
    assert last["source"] == "none" and last["reason"] == "no_child_no_probe"


def test_ac66_four_fixtures_one_per_rung(world):
    small = "SM_Wep_Rifle_Double_01_Mag_A_Small"
    # override: the named child beats the larger child the plain rule would take
    ov = detail_of(world, DOUBLE, {"magazine": {"source": "child_node", "child": small}})["mounts"]["magazine"]
    assert ov["source"] == "override" and ov["child_node"] == small
    close(ov["point"], A.SMALL_MAG_SEAT)
    assert abs(ov["span_m"] - 0.04) <= 1e-3 and ov["confidence"] == 1.0
    assert ov["occupied_by"] == [small, "SM_Wep_Rifle_Double_01_Mag_B_Large"]  # the game hides both baked magazines
    # child_node
    assert mounts(world, MOUNT)["optic"]["source"] == "child_node"
    # probe: the muzzle has no child to take and falls to the probe
    assert mounts(world, MOUNT)["muzzle"]["source"] == "probe"
    # none: nothing to take
    assert mounts(world, PLAIN)["optic"]["source"] == "none"


def test_ac66_an_override_can_disable_a_slot_that_has_a_child(world):
    got = detail_of(world, MOUNT, {"optic": {"source": "none"}})["mounts"]["optic"]
    assert got["source"] == "none" and got["reason"] == "slot_disabled" and got["occupied_by"] == [] and got["point"] is None
    assert detail_of(world, MOUNT, {"muzzle": {"source": "none"}})["mounts"]["muzzle"]["reason"] == "slot_disabled"


def test_ac66_an_override_naming_a_missing_node_is_reported_and_the_ladder_goes_on(world):
    got = detail_of(world, MOUNT, {"optic": {"source": "child_node", "child": "Nope_Node"}})
    assert got["mount_problems"] == ["child_not_found: optic: Nope_Node"]
    assert got["mounts"]["optic"]["source"] == "child_node"  # fell through to the child the tokens found
    assert detail_of(world, MOUNT)["mount_problems"] == []


def test_ac66_an_override_can_seat_a_slot_on_a_node_the_tokens_do_not_match(world):
    trigger = "SM_Wep_Rifle_Mount_01_Trigger"
    got = detail_of(world, MOUNT, {"underbarrel": {"source": "child_node", "child": trigger}})["mounts"]["underbarrel"]
    assert got["source"] == "override" and got["child_node"] == trigger and got["occupied_by"] == [trigger]


def test_ac66_ignoring_the_child_would_leave_the_optic_without_a_mount(world):
    # the property the mutation 'always probe' breaks: a host with a scope child has an optic mount, one without has none
    assert mounts(world, MOUNT)["optic"]["point"] is not None and mounts(world, PLAIN)["optic"]["point"] is None


# --- AC68: none behaviour --------------------------------------------------------------------------------------------


def test_ac68_the_childless_host_has_none_slots_with_null_coordinates_and_the_reason(world):
    m = mounts(world, PLAIN)
    for slot in ("optic", "underbarrel", "magazine", "laser_light"):
        got = m[slot]
        assert got["source"] == "none" and got["reason"] == "no_child_no_probe"
        assert got["point"] is None and got["forward"] is None and got["up"] is None and got["span_m"] is None
        assert got["span_source"] is None and got["child_node"] is None and got["occupied_by"] == []


def test_ac68_no_slot_is_ever_defaulted_to_a_bounds_guess(world):
    # every none slot, on every host, has no coordinate at all; the bounds of the host would have supplied one
    for w in world[0]["weapons"]:
        mm = w["geometry"]["mounts"]
        for slot, got in (mm or {}).items():
            if got["source"] == "none":
                assert got["point"] is None and got["span_m"] is None, (w["id"], slot)
    assert rec(world, PLAIN)["geometry"]["bounds"]["size"][2] > 0.8  # a bounds default would have had plenty to work with


def test_ac68_mount_missing_needs_a_compatible_attachment_for_that_slot(world):
    m = mounts(world, PLAIN)
    est = {"mount_estimated"}  # A2: both sight slots of these hosts are probe seats
    assert M.mount_reasons(m) == est  # compatibility inference is W8c: the build passes nothing
    assert M.mount_reasons(m, {"optic"}) == est | {"mount_missing"}
    assert M.mount_reasons(m, {"muzzle"}) == est  # the muzzle slot is a probe, not none
    assert M.mount_reasons(mounts(world, MOUNT), {"optic"}) == est  # the optic has a child
    assert M.mount_reasons(mounts(world, MOUNT), {"underbarrel", "laser_light"}) == est | {"mount_missing"}
    assert M.mount_reasons(None, {"optic"}) == set()
    assert "mount_missing" not in rec(world, PLAIN)["review"]["reasons"]


def test_ac68_a_build_has_no_mount_missing_and_estimates_only_the_sight_seats(world):
    for w in world[0]["weapons"]:
        assert "mount_missing" not in w["review"]["reasons"]
        mm = w["geometry"]["mounts"]
        probed = {s for s, m in (mm or {}).items() if m["source"] == "probe" and s.startswith("sight_")}
        assert ("mount_estimated" in w["review"]["reasons"]) == bool(probed), w["id"]  # A2: only a sight probe seat is an estimate


def test_ac68_only_whole_ranged_one_hand_and_long_gun_records_get_a_block(world):
    assert M.eligible("whole", "ranged", "long_gun") and M.eligible("whole", "ranged", "one_hand")
    for combo in [("whole", "thrown", "thrown"), ("whole", "melee", "melee_one"), ("whole", "shield", "shield"),
                  ("whole", "ranged", "bow"), ("whole", "ranged", "crossbow"), ("emplaced", "ranged", "none"),
                  ("part", None, "none"), ("whole", "ranged", "none")]:
        assert not M.eligible(*combo), combo


def test_ac68_the_w8a_world_gives_null_to_swords_grenades_and_parts(tmp_path):
    d, _, _, _ = A.build(tmp_path)
    by = {w["id"]: w for w in d["weapons"]}
    for rid in (f"{A.PACK}/SM_Wep_Sword_Long_01", f"{A.PACK}/SM_Wep_Grenade_Frag_01", f"{A.PACK}/SM_Wep_Rifle_Scope_01"):
        assert by[rid]["geometry"]["mounts"] is None, rid
    for rid in (f"{A.PACK}/SM_Wep_Rifle_Assault_01", f"{A.PACK}/SM_Wep_Pistol_01"):
        assert sorted(by[rid]["geometry"]["mounts"]) == sorted(SLOTS)


def test_a_bare_measurement_does_not_carry_the_mount_keys(world):
    # W8b is opt-in at the measurement level: the W7 detail dict (and its hashes) is what it was
    root = world[1]
    bare = measure_weapon_detail(root / "glb/FAKE_Mount/SM_Wep_Rifle_Mount_01.glb", None, 1.0, "rifle", "ranged", "whole",
                                 load_rules(), hold_class="long_gun", genre="modern")
    assert "mounts" not in bare and "mount_problems" not in bare and "mounts" not in bare["geometry"]
