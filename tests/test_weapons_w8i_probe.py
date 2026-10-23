"""W8i: the sight probe mesh drops baked muzzle, underbarrel and laser children (AC97; docs/weapon_attachments.md 4.6 item 1).

Hosts are the W8h slide pistol (top y 0.075 over z -0.09..0.09) with one baked child that stands 20 mm over the slide top. The
expected seats are literals: with the child out of the mesh the receiver run is the whole slide, so the rear seat is the slide's
rear end plus 10 mm (z -0.08) and the front seat its front end minus 8 mm (z 0.082), both on y 0.075.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("w8i_world", Path(__file__).parent / "fixtures" / "weapons" / "w8i_world.py")
X = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(X)
W, A = X.W, X.A

PACK = "FAKE_ProbeMesh"
BARE, MUZ, LASER, UNDER, SCOPE = ("SM_Wep_Pistol_Bare_01", "SM_Wep_Pistol_Muz_01", "SM_Wep_Pistol_Laser_01", "SM_Wep_Pistol_Under_01",
                                  "SM_Wep_Pistol_Topper_01")
SLIDE_TOP = 0.075


def world():
    cylinder = X.block(0.010, 0.0325, 0.06)  # y 0.03..0.095 about its node: 20 mm over the slide top, 0.12 m long
    stub = X.block(0.010, 0.010, 0.02)  # y 0.075..0.095 once moved up by 0.085
    return {PACK: {"hosts": {
        BARE: X.pistol(BARE),
        MUZ: X.pistol(MUZ, [("Suppressor", cylinder, (0.0, 0.0625, 0.15))]),  # in front of the slide: z 0.09..0.21
        LASER: X.pistol(LASER, [("Laser", stub, (0.0, 0.085, 0.0))]),  # on the slide top, 20 mm proud
        UNDER: X.pistol(UNDER, [("Foregrip", stub, (0.0, 0.085, 0.0))]),
        SCOPE: X.pistol(SCOPE, [("Scope", stub, (0.0, 0.085, 0.0))]),  # the A2 rule, still true: a baked scope is out of the mesh
    }}}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return W.by_id(W.build(tmp_path_factory.mktemp("w8i_probe"), world())[0])


def seats(built, name):
    m = built[f"{PACK}/{name}"]["geometry"]["mounts"]
    return m["sight_rear"], m["sight_front"]


def test_ac97_the_bare_slide_is_seated_on_the_slide_top(built):
    rear, front = seats(built, BARE)
    assert rear["source"] == front["source"] == "probe"
    assert abs(rear["point"][1] - SLIDE_TOP) <= 0.001 and abs(front["point"][1] - SLIDE_TOP) <= 0.001
    assert abs(rear["point"][2] - (-0.09 + 0.010)) <= 0.003 and abs(front["point"][2] - (0.09 - 0.008)) <= 0.006  # the 5 mm bins put the front seat up to one bin further out


def test_ac97_a_baked_suppressor_in_front_of_the_slide_does_not_lift_the_front_seat(built):
    rear, front = seats(built, MUZ)
    m = built[f"{PACK}/{MUZ}"]["geometry"]["mounts"]
    assert m["muzzle"]["occupied_by"] == [f"{MUZ}_Suppressor"]  # the child is the muzzle slot's, so the probe drops it
    assert abs(front["point"][1] - SLIDE_TOP) <= 0.001  # on the slide top, never on the 0.095 cylinder
    assert abs(front["point"][2] - (0.09 - 0.008)) <= 0.006  # nor ahead of the slide
    assert [round(c, 4) for c in front["point"]] == [round(c, 4) for c in seats(built, BARE)[1]["point"]]


@pytest.mark.parametrize("name,slot", [(LASER, "laser_light"), (UNDER, "underbarrel"), (SCOPE, "optic")])
def test_ac97_a_baked_laser_underbarrel_or_scope_standing_proud_leaves_both_seats_unchanged(built, name, slot):
    m = built[f"{PACK}/{name}"]["geometry"]["mounts"]
    assert m[slot]["occupied_by"], slot  # the child is listed in its slot ...
    for got, want in zip(seats(built, name), seats(built, BARE)):  # ... and so is out of the probe mesh
        assert got["source"] == "probe" and got["point"] == want["point"], slot


def test_ac97_the_a2_fixture_with_a_laser_child_over_the_receiver_is_now_seated_not_refused(tmp_path):
    d = W.by_id(A.build_mount_world(tmp_path)[0])
    m = d["FAKE_Mount/SM_Wep_Pistol_Mount_01"]["geometry"]["mounts"]
    assert m["laser_light"]["source"] == "child_node"
    assert m["sight_front"]["source"] == m["sight_rear"]["source"] == "probe"
