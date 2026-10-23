"""W8l: the optic seat lift (AC108), the mirrored pair seat (AC109) and the foot ladder on a host child (AC107).

docs/weapon_attachments.md 4.2 "A4 on the child seat" and 3.4 step 1a. The hosts are boxes written by ``w8h_world`` into the pack
FAKE_W8L (nothing from a real pack). Every expected number is a LITERAL worked out by hand from the dimensions below:

  body      x +-0.02, y 0..0.10, z -0.25..0.35 (top face y 0.10)                      (the stepped host: z -0.25..0.05 at 0.10, 0.05..0.35 at 0.12)
  scope     box x +-0.01, y 0..0.04, z +-0.03, a child translated to (0, bottom, z): its foot centre is (0, bottom, z), foot 0.06 long
  leg       box x +-0.005, y -0.08..0, z +-0.01 (a bipod leg hanging from the underside y 0): foot centre (x, 0, 0), foot 0.02 long

The sampling grid of the probe mesh is 2.5 mm, but a flat top face is sampled at exactly its own height, so a lift lands on the face (+-0.5 mm).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8h_world", FIX / "w8h_world.py")
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)

G = W.G
PACK = "FAKE_W8L"

BODY = ((-0.02, 0.0, -0.25), (0.02, 0.10, 0.35))
WIDE = [((-0.07, 0.0, -0.25), (0.07, 0.10, 0.35))]
STEPPED = [((-0.02, 0.0, -0.25), (0.02, 0.10, 0.05)), ((-0.02, 0.0, 0.05), (0.02, 0.12, 0.35))]
SCOPE = ((-0.01, 0.0, -0.03), (0.01, 0.04, 0.03))
BIG_SCOPE = ((-0.01, 0.0, -0.03), (0.01, 0.05, 0.03))
LEG = ((-0.005, -0.08, -0.01), (0.005, 0.0, 0.01))
TALL_LEG = ((-0.005, -0.12, -0.01), (0.005, 0.0, 0.01))
CELL = ((-0.01, -0.08, -0.02), (0.01, 0.0, 0.02))


# the lipped_ridge() cloud of w8l_meshes as a real mesh: a ridge x +-0.0105, y -0.005..0, z +-0.002 over a body y -0.24..-0.005, z -0.015..0.035
RIDGE_MESH = G.merge(G.box((-0.0105, -0.005, -0.002), (0.0105, 0.0, 0.002)), G.box((-0.0105, -0.240, -0.015), (0.0105, -0.005, 0.035)))


def host(name: str, kids=(), body=(BODY,)):
    mesh = G.merge(*[G.box(*b) for b in body])
    return W.host_node(name, mesh, [W.kid(name, suffix, G.box(*box), at) for suffix, box, at in kids])


def named(n: str) -> str:
    return f"SM_Wep_Rifle_{n}_01"


HOSTS = {
    # AC108
    named("Recess"): host(named("Recess"), [("Scope", SCOPE, (0.0, 0.086, 0.0))]),      # 14 mm in the top: lifts to 0.100
    named("Cap"): host(named("Cap"), [("Scope", SCOPE, (0.0, 0.07, 0.0))]),             # 30 mm in: exactly the cap, lifts to 0.100
    named("OverCap"): host(named("OverCap"), [("Scope", SCOPE, (0.0, 0.069, 0.0))]),    # 31 mm in: a hump, not a receiver top
    named("Deep"): host(named("Deep"), [("Scope", SCOPE, (0.0, 0.06, 0.0))]),           # 40 mm in
    named("Flush"): host(named("Flush"), [("Scope", SCOPE, (0.0, 0.10, 0.0))]),         # sits on the top
    named("Raised"): host(named("Raised"), [("Scope", SCOPE, (0.0, 0.11, 0.0))]),       # 10 mm above the top
    named("Aside"): host(named("Aside"), [("Scope", SCOPE, (0.10, 0.086, 0.0))]),       # x 0.09..0.11: beyond the body (x +-0.02)
    named("Bare"): host(named("Bare")),                                                  # no scope child
    named("Step"): host(named("Step"), [("Scope_A", BIG_SCOPE, (0.0, 0.096, -0.10)), ("Scope_B", SCOPE, (0.0, 0.116, 0.20))], STEPPED),
    # AC109
    named("Twins"): host(named("Twins"), [("Bipod_L", LEG, (0.052, 0.0, 0.0)), ("Bipod_R", LEG, (-0.052, 0.0, 0.0))]),
    named("Lopsided"): host(named("Lopsided"), [("Bipod_L", LEG, (0.052, 0.0, 0.0)), ("Bipod_R", LEG, (-0.030, 0.0, 0.0))]),
    named("Skew"): host(named("Skew"), [("Bipod_L", LEG, (0.052, 0.0, 0.003)), ("Bipod_R", LEG, (-0.052, 0.0, 0.0))]),
    named("Edge"): host(named("Edge"), [("Bipod_L", LEG, (0.052, 0.0, 0.001)), ("Bipod_R", LEG, (-0.052, 0.0, 0.0))]),
    named("Close"): host(named("Close"), [("Bipod_L", LEG, (0.004, 0.0, 0.0)), ("Bipod_R", LEG, (-0.004, 0.0, 0.0))]),
    named("Unequal"): host(named("Unequal"), [("Bipod_L", LEG, (0.052, 0.0, 0.0)), ("Bipod_R", TALL_LEG, (-0.052, 0.0, 0.0))]),
    named("Three"): host(named("Three"), [("Bipod_L", LEG, (0.052, 0.0, 0.0)), ("Bipod_M", LEG, (0.020, 0.0, 0.0)),
                                          ("Bipod_R", LEG, (-0.052, 0.0, 0.0))]),
    named("Cells"): host(named("Cells"), [("Cell_A", CELL, (0.03, 0.0, 0.0)), ("Cell_B", CELL, (-0.03, 0.0, 0.0))], WIDE),
    # AC107 on a host child: a Foregrip child that is a ridge over a 50 mm body
    named("Ridge"): W.host_node(named("Ridge"), G.box(*BODY), [W.kid(named("Ridge"), "Foregrip", RIDGE_MESH, (0.0, 0.0, 0.0))]),
}


@pytest.fixture(scope="module")
def mounts(tmp_path_factory):
    directory = W.build(tmp_path_factory.mktemp("w8l_mounts"), {PACK: {"hosts": HOSTS}})[0]
    return {w["asset_id"]: w["geometry"]["mounts"] for w in directory["weapons"]}


def optic_y(mounts, name):
    return mounts[named(name)]["optic"]["point"][1]


# --- AC108: a child_node optic seat is lifted to the host surface under the baked scope --------------------------------------


def test_ac108_a_scope_nested_14_mm_in_the_receiver_top_seats_on_the_top(mounts):
    optic = mounts[named("Recess")]["optic"]
    assert optic["point"] == pytest.approx([0.0, 0.100, 0.0], abs=0.0005)
    # only the up coordinate moves: everything else is what the child gave
    assert (optic["source"], optic["span_m"], optic["span_source"], optic["forward"], optic["up"]) == (
        "child_node", 0.06, "child_foot", [0.0, 0.0, 1.0], [0.0, 1.0, 0.0])
    assert optic["occupied_by"] == [named("Recess") + "_Scope"] and optic["child_node"] == named("Recess") + "_Scope"
    assert optic["confidence"] == 0.9 and optic["reason"] is None


def test_ac108_the_cap_is_30_mm_and_a_bigger_lift_is_a_hump_the_seat_stays(mounts):
    assert optic_y(mounts, "Cap") == pytest.approx(0.100, abs=0.0005)  # exactly 0.030: inside
    assert optic_y(mounts, "OverCap") == pytest.approx(0.069, abs=0.00005)  # 0.031: the child point as it was
    assert optic_y(mounts, "Deep") == pytest.approx(0.060, abs=0.00005)  # 0.040


@pytest.mark.parametrize(("name", "y"), [("Flush", 0.10), ("Raised", 0.11), ("Aside", 0.086)])
def test_ac108_a_scope_on_the_top_above_it_or_beside_the_body_keeps_its_seat(mounts, name, y):
    assert optic_y(mounts, name) == pytest.approx(y, abs=0.00005)


def test_ac108_the_x_and_z_of_the_point_never_move(mounts):
    assert mounts[named("Recess")]["optic"]["point"][0::2] == [0.0, 0.0]
    assert mounts[named("Aside")]["optic"]["point"][0::2] == pytest.approx([0.10, 0.0], abs=0.00005)


def test_ac108_a_host_without_a_scope_child_has_no_optic_seat_to_lift(mounts):
    optic = mounts[named("Bare")]["optic"]
    assert optic["source"] == "none" and optic["point"] is None


def test_ac108_a_two_scope_mount_lifts_on_the_union_rectangle_and_each_seat_for_its_own_child(mounts):
    optic = mounts[named("Step")]["optic"]
    # the mount point is the larger scope's seat (Scope_A, bottom 0.096) lifted on the union of both rectangles: the highest top under
    # either scope is the 0.12 step (24 mm above 0.096, inside the cap); x and z stay at Scope_A's (0, -0.10)
    assert optic["point"] == pytest.approx([0.0, 0.120, -0.10], abs=0.0005)
    assert optic["occupied_by"] == [named("Step") + "_Scope_A", named("Step") + "_Scope_B"]
    seats = optic["seats"]
    assert seats[named("Step") + "_Scope_A"]["point"] == pytest.approx([0.0, 0.100, -0.10], abs=0.0005)  # its own top, 0.10
    assert seats[named("Step") + "_Scope_B"]["point"] == pytest.approx([0.0, 0.120, 0.20], abs=0.0005)  # its own top, 0.12


# --- AC109: two twin children mirrored about the centre line seat at their midpoint -------------------------------------------


def underbarrel(mounts, name):
    return mounts[named(name)]["underbarrel"]


def test_ac109_the_two_legs_of_a_bipod_seat_at_the_midpoint_on_the_lower_name(mounts):
    m = underbarrel(mounts, "Twins")
    assert m["point"] == [0.0, 0.0, 0.0]  # (0.052 + -0.052) / 2
    assert m["child_node"] == named("Twins") + "_Bipod_L"
    assert m["occupied_by"] == [named("Twins") + "_Bipod_L", named("Twins") + "_Bipod_R"]
    assert sorted(m["seats"]) == m["occupied_by"]
    assert m["seats"][named("Twins") + "_Bipod_L"]["point"] == [0.052, 0.0, 0.0]  # the seats of the single legs are kept
    assert m["seats"][named("Twins") + "_Bipod_R"]["point"] == [-0.052, 0.0, 0.0]
    assert (m["source"], m["span_m"], m["up"]) == ("child_node", 0.02, [0.0, -1.0, 0.0])


def test_ac109_a_lopsided_pair_still_seats_at_the_plain_midpoint(mounts):
    assert underbarrel(mounts, "Lopsided")["point"] == [0.011, 0.0, 0.0]  # (0.052 + -0.030) / 2


def test_ac109_a_cell_pair_is_mirrored_too_the_rule_is_not_bound_to_a_slot(mounts):
    m = mounts[named("Cells")]["magazine"]
    assert m["point"] == [0.0, 0.0, 0.0] and m["child_node"] == named("Cells") + "_Cell_A"
    assert m["occupied_by"] == [named("Cells") + "_Cell_A", named("Cells") + "_Cell_B"]


def test_ac109_a_3_mm_forward_offset_is_not_a_mirrored_pair(mounts):
    m = underbarrel(mounts, "Skew")
    assert m["point"] == [0.052, 0.0, 0.003]  # the seat of the larger-volume child (a tie goes to the first by name)
    assert m["child_node"] == named("Skew") + "_Bipod_L"


def test_ac109_a_1_mm_forward_offset_is_still_inside_the_alignment(mounts):
    assert underbarrel(mounts, "Edge")["point"] == [0.0, 0.0, 0.0005]  # (0.001 + 0) / 2


def test_ac109_two_legs_8_mm_apart_are_a_pair_more_than_5_mm_is_enough(mounts):
    assert underbarrel(mounts, "Close")["point"] == [0.0, 0.0, 0.0]


def test_ac109_children_of_unequal_size_are_not_mirrored(mounts):
    m = underbarrel(mounts, "Unequal")
    assert m["point"] == [-0.052, 0.0, 0.0] and m["child_node"] == named("Unequal") + "_Bipod_R"  # the taller leg has the larger volume


def test_ac109_three_children_are_not_mirrored(mounts):
    m = underbarrel(mounts, "Three")
    assert m["point"] == [0.052, 0.0, 0.0] and m["child_node"] == named("Three") + "_Bipod_L"
    assert len(m["occupied_by"]) == 3


# --- AC107 on a host child: the foot ladder gives the child its real foot ------------------------------------------------------


def test_ac107_a_host_child_that_is_a_ridge_over_a_body_seats_on_its_8_mm_foot(mounts):
    m = underbarrel(mounts, "Ridge")
    assert m["point"] == [0.0, 0.0, 0.01]  # the centre of the 8 mm slab (z -0.015..0.035), not of the 4 mm ridge (z 0)
    assert (m["span_m"], m["span_source"], m["source"]) == (0.05, "child_foot", "child_node")  # not the 0.004 of the ridge
