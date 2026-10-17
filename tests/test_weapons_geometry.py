"""Weapon directory W2: geometry measurement (AC11, AC13-AC16), the geometry cache, pass-2 classification and the
end-to-end build with generated GLBs.

Everything is synthetic (tests/fixtures/weapons/make_glbs.py writes the GLBs into a tmp dir). Numeric bounds are
literals: the hand-worked expectations live in make_glbs.LABELS and in this file, never in the code under test.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

_FIX = Path(__file__).parent / "fixtures" / "weapons"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _FIX / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wfx = _load("wfx")
M = _load("make_glbs")

from synty_inventory.weapons import geometry as G  # noqa: E402
from synty_inventory.weapons import to_text  # noqa: E402
from synty_inventory.weapons.classify import classify  # noqa: E402
from synty_inventory.weapons.directory import build_directory_report  # noqa: E402
from synty_inventory.weapons.geometry import measure_cached, measure_weapon, measure_weapon_detail  # noqa: E402
from synty_inventory.weapons.overrides import empty_overrides  # noqa: E402
from synty_inventory.weapons.rules import load_rules  # noqa: E402
from synty_inventory.weapons.schema import validate_directory  # noqa: E402


@pytest.fixture(scope="module")
def rules():
    return load_rules()


@pytest.fixture(scope="module")
def glbs(tmp_path_factory):
    return M.generate_all(tmp_path_factory.mktemp("glbs"))


def meas(glbs, rules, name, archetype, kind, role="whole", hold=None, genre="fantasy", node=None, scale=1.0):
    return measure_weapon_detail(glbs[name], node, scale, archetype, kind, role, rules, hold_class=hold, genre=genre)


def close(a, b, tol=0.0002):
    return all(abs(x - y) <= tol for x, y in zip(a, b)) and len(a) == len(b)


# --- AC11: axes ----------------------------------------------------------------------------------------------

AC11_CASES = [
    ("gun", "rifle", "ranged", "long_gun", "modern"),
    ("sword", "sword", "melee", None, "fantasy"),
    ("spear", "spear", "melee", None, "fantasy"),
    ("axe", "axe", "melee", None, "fantasy"),
    ("bow", "bow", "ranged", None, "fantasy"),
    ("shield", "shield", "shield", None, "fantasy"),
    ("zlong_melee", "sword", "melee", None, "fantasy"),
]


@pytest.mark.parametrize("name,arch,kind,hold,genre", AC11_CASES)
def test_ac11_axes_match_the_labels(glbs, rules, name, arch, kind, hold, genre):
    want = M.LABELS[name]
    d = meas(glbs, rules, name, arch, kind, hold=hold, genre=genre)
    geo = d["geometry"]
    assert geo["axes"]["forward"] == want["forward"]
    assert geo["axes"]["up"] == want["up"]
    assert geo["long_axis"] == want["long_axis"]
    assert geo["axes"]["forward_source"] == want["forward_source"]
    assert abs(geo["length_m"] - want["length"]) <= 0.001


@pytest.mark.parametrize("name,arch,kind", [("spear", "spear", "melee"), ("axe", "axe", "melee")])
def test_ac11_spear_and_axe_use_the_section_fallback_and_flag_it(glbs, rules, name, arch, kind):
    d = meas(glbs, rules, name, arch, kind)
    assert d["geometry"]["axes"]["forward_source"] == "section"
    assert "forward_by_fallback" in d["flags"]
    # origin mid-length is what sends them to the fallback
    assert abs(d["geometry"]["pivot_frac"] - 0.5) <= 0.01


def test_ac11_bow_rule_is_flagged_only_when_the_belly_is_unreadable_and_the_pivot_rule_is_not(glbs, rules):
    bow = meas(glbs, rules, "bow", "bow", "ranged")
    assert bow["geometry"]["axes"]["up_source"] == "long_axis"
    assert bow["geometry"]["axes"]["forward_source"] == "bow_rule"
    assert "forward_by_fallback" not in bow["flags"]  # a measured belly is not a fallback (spec 3.5.2 item 3, PATCH W2c)
    for name, arch, kind in (("sword", "sword", "melee"), ("shield", "shield", "shield")):
        assert "forward_by_fallback" not in meas(glbs, rules, name, arch, kind)["flags"]


# --- bow forward: the belly side (spec 3.5.2 item 3) ---------------------------------------------------------------
#
# bow(): riser at z +0.15 and limb tips at z 0 (the string is on the tip side, toward the archer), so forward = +z.
# The "origin" fixtures put the origin past the belly, where the old "away from the origin" sign pointed at the archer.

BOW_FORWARD = {
    "bow": "+z",  # origin on the tip side: old and new rules agree
    "bow_origin_past_belly_pz": "+z",  # old rule said -z
    "bow_origin_past_belly_nz": "-z",  # old rule said +z
}


@pytest.mark.parametrize("name", sorted(BOW_FORWARD))
def test_bow_forward_is_the_belly_side_whatever_side_the_origin_is_on(glbs, rules, name):
    d = meas(glbs, rules, name, "bow", "ranged")
    axes = d["geometry"]["axes"]
    assert axes["forward"] == BOW_FORWARD[name] and axes["forward_source"] == "bow_rule"
    assert axes["up"] == "+y" and d["geometry"]["long_axis"] == "y"
    assert "forward_by_fallback" not in d["flags"]


def test_bow_origin_side_fixtures_really_put_the_origin_on_the_other_side(glbs, rules):
    """Guards the fixtures: the old rule (forward away from the origin, along z) would give the opposite sign."""
    for name, old in (("bow_origin_past_belly_pz", "-z"), ("bow_origin_past_belly_nz", "+z")):
        b = meas(glbs, rules, name, "bow", "ranged")["geometry"]["bounds"]
        lo, hi = b["min"][2], b["max"][2]
        frac = (0.0 - lo) / (hi - lo)
        assert ("+z" if frac < 0.5 else "-z") == old, name


def test_bow_with_a_barely_readable_belly_keeps_the_origin_sign_and_the_flag(glbs, rules, tmp_path):
    """bow_with_belly(b): belly = b / (|b| + 0.02) of the depth. 0.003 -> 0.130 (under the 0.15 threshold: the origin,
    far below the stave at z 0.1, says +z although the belly points -z) and 0.0045 -> 0.184 (over it: the belly)."""
    def at(belly_z, dz, name):
        path = M.write_glb(tmp_path / f"{name}.glb", [{"name": name, "mesh": M.shifted(M.bow_with_belly(belly_z), (0, 0, dz))}])
        return measure_weapon_detail(path, None, 1.0, "bow", "ranged", "whole", rules, genre="fantasy")

    weak = at(-0.003, 0.1, "weak")
    assert weak["geometry"]["axes"]["forward"] == "+z" and "forward_by_fallback" in weak["flags"]
    assert weak["geometry"]["axes"]["forward_source"] == "bow_rule"
    strong = at(-0.0045, 0.1, "strong")
    assert strong["geometry"]["axes"]["forward"] == "-z" and "forward_by_fallback" not in strong["flags"]
    strong_pos = at(0.0045, -0.1, "strong_pos")  # origin above the stave: old sign -z; belly +z
    assert strong_pos["geometry"]["axes"]["forward"] == "+z" and "forward_by_fallback" not in strong_pos["flags"]
    weak_pos = at(0.003, -0.1, "weak_pos")
    assert weak_pos["geometry"]["axes"]["forward"] == "-z" and "forward_by_fallback" in weak_pos["flags"]


def test_a_crossbow_stays_under_the_firearm_rule_not_the_bow_rule(glbs, rules):
    d = meas(glbs, rules, "gun", "crossbow", "ranged", hold="crossbow")
    assert d["geometry"]["axes"]["forward_source"] == "pivot"  # not "bow_rule"


# --- ranged non-bow forward when the origin is silent (spec 3.5.2 step 2) -----------------------------------------
# Guns whose origin sits mid-length are decided by the end cross-sections, which cannot tell a muzzle from a stock;
# the pack convention (axes_expected, ranged +z) breaks that tie. Signs are literals worked out from the stations.

# name, archetype, hold, genre -> forward the section rule alone would give, and the forward reported
MID_ORIGIN_GUNS = [
    ("rifle_mid_origin", "rifle", "long_gun", "+z", "+z"),  # section already says +z
    ("smg_fat_handguard", "smg", "long_gun", "-z", "+z"),  # slim stock, fat handguard: section says -z
    ("pistol_mid_origin", "pistol", "one_hand", "-z", "+z"),  # bulky light at the muzzle: section says -z
]


@pytest.mark.parametrize("name,arch,hold,section_says,want", MID_ORIGIN_GUNS)
def test_mid_origin_ranged_guns_take_the_convention_sign_and_stay_flagged(glbs, rules, name, arch, hold, section_says, want):
    d = meas(glbs, rules, name, arch, "ranged", hold=hold, genre="modern")
    axes = d["geometry"]["axes"]
    assert abs(d["geometry"]["pivot_frac"] - 0.5) <= 0.001  # the pivot rule has no say
    assert axes["forward"] == want and axes["forward_source"] == "section"
    assert "forward_by_fallback" in d["flags"]
    assert "axes_unexpected" not in d["reasons"]


@pytest.mark.parametrize("name,arch,hold,section_says,want", MID_ORIGIN_GUNS)
def test_without_a_genre_the_end_section_sign_stands(glbs, rules, name, arch, hold, section_says, want):
    d = meas(glbs, rules, name, arch, "ranged", hold=hold, genre=None)
    assert d["geometry"]["axes"]["forward"] == section_says
    assert d["geometry"]["axes"]["forward_source"] == "section"


def test_a_convention_on_another_axis_does_not_decide_the_sign(glbs, rules):
    odd = copy.deepcopy(rules)
    odd["axes_expected"]["modern"]["ranged"] = "-x"
    d = meas(glbs, odd, "smg_fat_handguard", "smg", "ranged", hold="long_gun", genre="modern")
    assert d["geometry"]["axes"]["forward"] == "-z"  # the end sections, as without a convention
    assert "axes_unexpected" in d["reasons"]


def test_the_convention_flips_a_minus_z_section_sign_to_the_convention_sign_and_the_opposite_one_too(glbs, rules):
    neg = copy.deepcopy(rules)
    neg["axes_expected"]["modern"]["ranged"] = "-z"
    d = meas(glbs, neg, "rifle_mid_origin", "rifle", "ranged", hold="long_gun", genre="modern")
    assert d["geometry"]["axes"]["forward"] == "-z"


def test_an_emplaced_ranged_record_keeps_the_end_section_sign(glbs, rules):
    d = meas(glbs, rules, "smg_fat_handguard", "cannon", "ranged", role="emplaced", genre="modern")
    assert d["geometry"]["axes"]["forward"] == "-z" and d["geometry"]["axes"]["forward_source"] == "section"


def test_a_shoulder_launcher_whose_origin_is_past_60_percent_keeps_the_pivot_sign_and_says_so(glbs, rules):
    d = meas(glbs, rules, "shoulder_launcher", "launcher", "ranged", hold="long_gun", genre="modern")
    axes = d["geometry"]["axes"]
    assert d["geometry"]["pivot_frac"] == pytest.approx(0.63, abs=0.001)
    # an origin that decides is never overridden by the convention: the mismatch is reported, not corrected
    assert axes["forward"] == "-z" and axes["forward_source"] == "pivot"
    assert "axes_unexpected" in d["reasons"] and "forward_by_fallback" not in d["flags"]


def test_a_pivot_decided_gun_is_unchanged_by_the_convention_rule(glbs, rules):
    d = meas(glbs, rules, "gun", "rifle", "ranged", hold="long_gun", genre="modern")
    assert d["geometry"]["axes"]["forward"] == "+z" and d["geometry"]["axes"]["forward_source"] == "pivot"


@pytest.mark.parametrize("name,arch,kind,hold", [(c[0], c[1], c[2], c[3]) for c in AC11_CASES])
def test_item_basis_takes_forward_to_plus_z_and_up_to_plus_y_right_handed(glbs, rules, name, arch, kind, hold):
    geo = meas(glbs, rules, name, arch, kind, hold=hold)["geometry"]
    basis = np.array(geo["item_basis"])
    assert basis.shape == (3, 3) and basis.dtype.kind == "i"

    def vec(sig):
        v = np.zeros(3, dtype=int)
        v["xyz".index(sig[1])] = 1 if sig[0] == "+" else -1
        return v

    assert (basis @ vec(geo["axes"]["forward"])).tolist() == [0, 0, 1]
    assert (basis @ vec(geo["axes"]["up"])).tolist() == [0, 1, 0]
    assert round(np.linalg.det(basis)) == 1


def test_item_basis_for_a_y_long_sword_is_the_hand_worked_permutation(glbs, rules):
    # forward +y -> +z, up +x -> +y, so right = up x forward = x cross y... the third row is [0,1,0]
    assert meas(glbs, rules, "sword", "sword", "melee")["geometry"]["item_basis"] == [[0, 0, 1], [1, 0, 0], [0, 1, 0]]


def test_axes_unexpected_is_a_reason_not_a_correction(glbs, rules):
    odd = meas(glbs, rules, "zlong_melee", "sword", "melee", genre="fantasy")
    assert "axes_unexpected" in odd["reasons"]
    assert odd["geometry"]["axes"]["forward"] == "+z"  # reported as found, never silently flipped
    assert "axes_unexpected" not in meas(glbs, rules, "sword", "sword", "melee")["reasons"]
    assert "axes_unexpected" not in meas(glbs, rules, "zlong_melee", "sword", "melee", genre=None)["reasons"]
    assert "axes_unexpected" not in meas(glbs, rules, "bow", "bow", "ranged")["reasons"]  # bows are forward_by_fallback


# --- length, tip, butt, bounds --------------------------------------------------------------------------------

def test_sword_length_tip_butt_pivot_and_bounds_are_the_hand_worked_values(glbs, rules):
    geo = meas(glbs, rules, "sword", "sword", "melee")["geometry"]
    assert geo["length_m"] == 1.0 and geo["pivot_frac"] == 0.15
    assert close(geo["tip"], [0.0, 0.85, 0.0]) and close(geo["butt"], [0.0, -0.15, 0.0])
    assert close(geo["bounds"]["min"], [-0.1, -0.15, -0.025]) and close(geo["bounds"]["max"], [0.1, 0.85, 0.025])
    assert close(geo["bounds"]["size"], [0.2, 1.0, 0.05])
    assert geo["frame"] == "asset" and geo["node_offset"] is None
    assert geo["muzzle"] is None and geo["muzzle_source"] is None and geo["support"] is None


def test_ranged_records_have_no_tip_but_a_butt(glbs, rules):
    geo = meas(glbs, rules, "gun", "rifle", "ranged", hold="long_gun", genre="modern")["geometry"]
    assert geo["tip"] is None
    assert close(geo["butt"], [0.0, 0.05, -0.25])


def test_collision_hull_nodes_do_not_count(glbs, rules):
    geo = meas(glbs, rules, "gun", "rifle", "ranged", hold="long_gun", genre="modern")["geometry"]
    assert geo["bounds"]["max"][2] == 0.65  # the 2 m *_Collision box would give 1.0
    assert geo["bounds"]["min"][0] == -0.02


def test_glb_scale_multiplies_every_point(glbs, rules):
    one = meas(glbs, rules, "sword", "sword", "melee")["geometry"]
    two = meas(glbs, rules, "sword", "sword", "melee", scale=2.0)["geometry"]
    assert two["length_m"] == 2.0 and close(two["tip"], [0.0, 1.7, 0.0]) and close(two["grip"], [0.0, -0.02, 0.0])
    assert one["pivot_frac"] == two["pivot_frac"] == 0.15
    assert two["grip_r_m"] == 0.03


# --- muzzle in the pipeline (AC12 itself is in test_weapons_muzzle_parity) -------------------------------------

def test_inflated_gun_muzzle_is_the_barrel_face_not_the_bounds_centre(glbs, rules):
    geo = meas(glbs, rules, "gun_inflated", "rifle", "ranged", hold="long_gun", genre="modern")["geometry"]
    assert geo["muzzle_source"] == "face" and close(geo["muzzle"], [0.0, 0.055, 0.65])
    bounds_centre_y = (-0.30 + 0.20) / 2
    assert abs(geo["muzzle"][1] - bounds_centre_y) >= 0.02


def test_cone_front_falls_back_to_the_bounds_rule_with_a_reason(glbs, rules):
    d = meas(glbs, rules, "gun_cone", "rifle", "ranged", hold="long_gun", genre="modern")
    geo = d["geometry"]
    assert geo["muzzle_source"] == "bounds_fallback" and "muzzle_fallback" in d["reasons"]
    assert close(geo["muzzle"], [0.0, 0.075, 0.65])  # min_up 0 + 0.75 * 0.10; never null on a measured ranged weapon


def test_stepped_muzzle_is_decided_by_the_0002_window(glbs, rules):
    """The barrel ends in an apex (z 0.65), a ring at 0.6485 and an off-centre ring at 0.646: the 0.001 window holds 1
    point, the 0.002 window exactly 5 (lateral y mean 0.055) and the 0.005 window 9 (y mean 0.0639). The AC12 golden
    never decides at 0.002, so this is the pipeline-level pin for that step."""
    geo = meas(glbs, rules, "gun_stepped_muzzle", "rifle", "ranged", hold="long_gun", genre="modern")["geometry"]
    assert geo["muzzle_source"] == "face"
    assert close(geo["muzzle"], [0.0, 0.055, 0.65], tol=0.0005)


def test_a_bow_has_no_muzzle_and_a_crossbow_does(glbs, rules):
    assert meas(glbs, rules, "bow", "bow", "ranged")["geometry"]["muzzle"] is None
    assert meas(glbs, rules, "gun", "crossbow", "ranged", hold="crossbow")["geometry"]["muzzle"] is not None


# --- AC13: grip ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name,arch,centre,radius", [
    ("sword", "sword", -0.02, 0.015),  # handle y -0.12..0.08
    ("knife", "knife", -0.04, 0.01),  # handle y -0.10..0.02
])
def test_ac13_handle_detection_finds_the_known_handle(glbs, rules, name, arch, centre, radius):
    geo = meas(glbs, rules, name, arch, "melee")["geometry"]
    assert geo["grip_source"] == "handle"
    assert abs(geo["grip"][1] - centre) <= 0.02
    assert abs(geo["grip_r_m"] - radius) <= 0.005
    assert abs(geo["grip"][0]) <= 0.005 and abs(geo["grip"][2]) <= 0.005  # lateral = mean of the run's vertices


def test_ac13_axe_handle_is_in_the_butt_side_shaft(glbs, rules):
    geo = meas(glbs, rules, "axe", "axe", "melee")["geometry"]
    assert geo["grip_source"] == "handle"
    assert -0.45 <= geo["grip"][1] <= 0.09  # butt-side 60 % of 0.9 m
    assert abs(geo["grip_r_m"] - 0.015) <= 0.005


def test_ac13_a_mesh_with_no_qualifying_run_grips_at_the_pivot(glbs, rules):
    # banded: 60 % thin bins in the window, but only in runs of 3 (< 6 cm), by the vertex AND the surface profile; origin at
    # the butt (zigzag, the previous fixture here, now has a surface run holding its origin: see test_w2d_zigzag_*)
    geo = meas(glbs, rules, "banded", "club", "melee")["geometry"]
    assert geo["grip_source"] == "pivot" and geo["grip_r_m"] is None
    # W2f: the pivot grip at the butt is kept a hand-half (0.045 m) off the end, along the forward axis only
    assert close(geo["grip"], [0.0, 0.045, 0.0])


def test_w2d_zigzag_is_one_thin_run_because_the_edges_fill_the_bins(glbs, rules):
    """The rings alternate 0.02 / 0.10 wide (the base rule finds no handle), but the edges between them cross every bin:
    the surface profile is 0.092 / 0.100, within 30 % of its p20, so the 30-bin window is one counting run and the origin
    (y 0, bin 15) lies inside it: handle, the grip stays at the origin (W2d step 3)."""
    geo = meas(glbs, rules, "zigzag", "club", "melee")["geometry"]
    assert geo["grip_source"] == "handle" and abs(geo["grip_r_m"] - 0.048) <= 0.001
    assert abs(geo["grip"][1] - 0.0) <= 0.001


def test_guns_grip_at_the_origin_and_shields_and_bows_at_the_centre(glbs, rules):
    gun = meas(glbs, rules, "gun", "rifle", "ranged", hold="long_gun", genre="modern")["geometry"]
    assert gun["grip_source"] == "pivot" and gun["grip"] == [0.0, 0.0, 0.0] and gun["grip_r_m"] is None
    shield = meas(glbs, rules, "shield", "shield", "shield")["geometry"]
    assert shield["grip_source"] == "centre" and close(shield["grip"], [0.0, 0.0, 0.0])  # centre of the z=0 back face
    bow = meas(glbs, rules, "bow", "bow", "ranged")["geometry"]
    assert bow["grip_source"] == "centre" and close(bow["grip"], [0.0, 0.0, 0.075])  # bounds centre of z -0.01..0.16


# --- AC14: support -------------------------------------------------------------------------------------------

def test_ac14_long_gun_support_sits_at_62_percent_with_a_measured_radius(glbs, rules):
    geo = meas(glbs, rules, "gun", "rifle", "ranged", hold="long_gun", genre="modern")["geometry"]
    frac = (geo["support"][2] - (-0.25)) / 0.9
    assert abs(frac - 0.62) <= 0.01
    assert abs(geo["support_r_m"] - 0.02) <= 0.002  # half the smaller lateral extent (x 0.04 vs y 0.10)
    assert geo["support_source"] == "proportion"
    assert abs(geo["support"][0]) <= 0.001 and abs(geo["support"][1] - 0.05) <= 0.001  # slice centroid


def test_ac14_radius_is_unclamped_a_14_cm_slice_gives_7_cm(glbs, rules):
    geo = meas(glbs, rules, "gun_wide", "shotgun", "ranged", hold="long_gun", genre="modern")["geometry"]
    assert abs(geo["support_r_m"] - 0.07) <= 0.002
    assert geo["support_r_m"] > 0.06


def test_ac14_one_hand_and_melee_have_no_support(glbs, rules):
    assert meas(glbs, rules, "pistol", "pistol", "ranged", hold="one_hand", genre="modern")["geometry"]["support"] is None
    d = meas(glbs, rules, "sword", "sword", "melee", hold="melee_one")["geometry"]
    assert d["support"] is None and d["support_r_m"] is None and d["support_source"] is None


def test_ac14_an_empty_slice_keeps_the_point_and_nulls_the_radius(glbs, rules, tmp_path):
    path = M.write_glb(tmp_path / "box.glb", [{"name": "box", "mesh": M.box_part((0.04, 0.04, 0.6))}])
    d = measure_weapon_detail(path, None, 1.0, "rifle", "ranged", "whole", rules, hold_class="long_gun", genre="modern")
    geo = d["geometry"]
    assert geo["support"] is not None and geo["support_r_m"] is None
    assert abs(geo["support"][2] - (-0.3 + 0.62 * 0.6)) <= 0.001


# --- AC15: failure to measure ------------------------------------------------------------------------------------

def test_ac15_missing_garbage_and_zero_triangle_files_measure_to_none(glbs, rules, tmp_path):
    for name in ("garbage", "zero_tri"):
        d = meas(glbs, rules, name, "rifle", "ranged", hold="long_gun")
        assert d["geometry"] is None and d["reasons"] == ["no_geometry"] and d["flags"] == []
        assert measure_weapon(glbs[name], None, 1.0, "rifle", "ranged", "whole", rules) is None
    assert measure_weapon(tmp_path / "missing.glb", None, 1.0, "rifle", "ranged", "whole", rules) is None


def test_ac15_a_zero_extent_mesh_is_degenerate(glbs, rules):
    d = meas(glbs, rules, "degenerate", "rifle", "ranged")
    assert d["geometry"] is None and set(d["reasons"]) == {"degenerate", "no_geometry"}


# --- AC40: melee grip anchored on the pivot (W2d, revised) -----------------------------------------------------

# The rule (spec 3.5.5): (1) the BASE rule (vertex profile, longest run, p10) runs first and wins unchanged; (2) otherwise a
# surface profile makes the counting runs; (3) a pivot inside a counting run keeps the grip AT the pivot ("handle", with
# the run's measured radius); (4) a pivot at least 30 % of the length from the butt and within 10 % of the length of a
# counting run snaps onto the run, min_run / 2 inside its end; (5) otherwise the pivot fallback. Every expectation below is
# a literal worked out by hand from the fixture docstrings in make_glbs.py (bins are 1 cm from the butt).
#
# The labelled set is make_glbs.W2D_SET (ten meshes), measured with the origin at the butt, at 20 % of the length and at the
# middle of the length. At the middle the pivot rule is silent, so the forward sign comes from the end-section rule: every
# set member has a tip clearly smaller than its butt (pointed archetypes) or a head clearly larger (axe / hammer / club), and
# must still resolve to +y. Nine members are built from ``bar`` sections, whose vertex profile is a clean step function: the
# BASE rule decides them (step 1), so their grip is the run centre whatever the origin. Only ``sparse_haft`` (a vertex-sparse
# haft: at most one vertex per bin) defeats the base rule and takes step 3.


BUTT_INSET = 0.045  # W2f: a melee grip is kept this far (m) from the butt end, along the forward axis (half the 0.09 m hand)
BASE_LONGEST_RUN_LIMIT = ("tang", "wire")  # AC40's named shapes do not include them; see make_glbs.W2D_SET


@pytest.fixture(scope="module")
def w2d(tmp_path_factory):
    root = tmp_path_factory.mktemp("w2d")
    out = {}
    for name, (build, _arch, length, *_rest) in M.W2D_SET.items():
        for origin, (frac, _src) in M.W2D_ORIGINS.items():
            mesh = M.shifted(build(), (0.0, -frac * length, 0.0))
            out[(name, origin)] = M.write_glb(root / f"{name}_{origin}.glb", [{"name": name, "mesh": mesh}])
    return out


def w2d_measure(w2d, rules, name, origin):
    arch = M.W2D_SET[name][1]
    return measure_weapon_detail(w2d[(name, origin)], None, 1.0, arch, "melee", "whole", rules, genre="fantasy")["geometry"]


def grip_of(tmp_path, rules, mesh, archetype, length, frac, forward_override=None, name="m"):
    """Measure ``mesh`` (butt at y 0, forward +y) with the origin ``frac`` of its length from the butt. Returns the geometry
    block and the grip's y measured from the butt (the frame the hand-worked literals use)."""
    path = M.write_glb(tmp_path / f"{name}.glb", [{"name": name, "mesh": M.shifted(mesh, (0.0, -frac * length, 0.0))}])
    geo = measure_weapon_detail(path, None, 1.0, archetype, "melee", "whole", rules, genre="fantasy",
                                forward_override=forward_override)["geometry"]
    return geo, geo["grip"][1] + frac * length


def test_ac40_the_set_has_at_least_twelve_labelled_meshes_and_covers_the_named_shapes():
    assert len(M.W2D_SET) * len(M.W2D_ORIGINS) >= 12
    assert {"sword", "axe", "hammer", "bat", "crowbar", "knife", "spear", "sparse_haft"} <= set(M.W2D_SET)
    assert set(M.W2D_ORIGINS) == {"butt", "fifth", "mid"}


@pytest.mark.parametrize("name", sorted(M.W2D_SET))
@pytest.mark.parametrize("origin", sorted(M.W2D_ORIGINS))
def test_ac40_the_grip_lies_in_the_labelled_handle_with_the_labelled_radius(w2d, rules, name, origin):
    _build, _arch, length, (lo, hi), radius, grip_y = M.W2D_SET[name]
    frac, forward_source = M.W2D_ORIGINS[origin]
    geo = w2d_measure(w2d, rules, name, origin)
    assert geo["axes"]["forward"] == "+y" and geo["axes"]["forward_source"] == forward_source
    assert geo["grip_source"] == "handle"
    y = geo["grip"][1] + frac * length  # back to the butt-at-zero frame the labels use
    if name in BASE_LONGEST_RUN_LIMIT:
        # the unchanged base rule keeps the LONGEST thin run: the tang (not the hilt), the filament (not the grip wire). The
        # grip is outside the hand-held span; pinned, so that a change to the base rule shows up here
        assert not (lo <= y <= hi)
    else:
        assert lo <= y <= hi
    # step 1 (base rule): the hand-worked run centre, whatever the origin; step 3 ("origin"): the pivot itself
    # (W2f: a grip nearer the butt than BUTT_INSET is pushed out to it)
    assert abs(y - max(frac * length if grip_y == "origin" else grip_y, BUTT_INSET)) <= 0.0005
    assert abs(geo["grip_r_m"] - radius) <= 0.005
    assert abs(geo["grip"][0]) <= 0.005 and abs(geo["grip"][2]) <= 0.005  # lateral: the mean of a symmetric surface


def test_ac40_a_mesh_the_base_rule_decides_never_reaches_the_surface_step(w2d, rules, monkeypatch):
    """Step 1 wins when it finds a handle, so every live record that already said 'handle' keeps its bytes: for the nine
    bar-built members the surface step is not even called (a call would raise)."""
    def boom(*args, **kwargs):
        raise AssertionError("the base rule found a handle; the surface step must not run")

    monkeypatch.setattr(G, "_pivot_handle", boom)
    for name in sorted(M.W2D_SET):
        if name != "sparse_haft":
            for origin in M.W2D_ORIGINS:
                assert w2d_measure(w2d, rules, name, origin)["grip_source"] == "handle"


@pytest.mark.parametrize("name,mesh", [
    ("sparse_haft", M.sparse_haft), ("sparse_pole", M.sparse_pole), ("sparse_machete", M.sparse_machete),
    ("sparse_paddle_4", lambda: M.sparse_paddle(4, 0.455)), ("sparse_paddle_3", lambda: M.sparse_paddle(3, 0.355)),
    ("zigzag", M.zigzag),
])
def test_ac40_the_vertex_sparse_fixtures_really_defeat_the_base_rule(name, mesh):
    """The premise of these fixtures: the vertex-profile rule (step 1) finds NO handle, which is what broke the old rule on
    the live low-poly hafts. Without it the cases below would test the base rule, not the surface step."""
    v, _ = mesh()
    fmin = float(v[:, 1].min())
    assert G._find_handle(v, 1, v[:, 1], fmin, float(v[:, 1].max()) - fmin) is None


def test_ac40_the_sparse_haft_really_has_at_most_one_vertex_per_bin():
    """Every 1 cm bin of the window holds at most one vertex (the shaft part; the head is outside the window)."""
    v, _ = M.sparse_haft()
    window = v[v[:, 1] < 0.6]
    bins = np.floor((window[:, 1] - v[:, 1].min()) / 0.01 + 1e-6).astype(int)
    assert np.bincount(bins).max() == 1 and len(window) >= 20


@pytest.mark.parametrize("frac,want_y", [(0.0, 0.045), (0.2, 0.201), (0.5, 0.5025)])  # 0.0 -> 0.045: W2f butt inset
def test_ac40_a_the_sparse_haft_gets_handle_at_the_origin_with_a_measured_radius(tmp_path, rules, frac, want_y):
    """Case (a), the one that broke the old rule: step 3. The surface profile is one thin run of 61 bins (bins 0-60, every
    shaft bin is <= 0.03), the origin lies inside it, so the grip is the origin (y = frac * 1.005) and the radius is the run's
    mean(e') / 2: 0.03 in 59 of the 61 bins, the first two partial -> 0.0148 (labelled 0.015, within 5 mm)."""
    geo, y = grip_of(tmp_path, rules, M.sparse_haft(), "club", 1.005, frac)
    assert geo["grip_source"] == "handle"
    assert abs(y - want_y) <= 0.0005
    assert geo["grip_r_m"] is not None and abs(geo["grip_r_m"] - 0.015) <= 0.005
    assert abs(geo["grip"][0]) <= 0.005 and abs(geo["grip"][2]) <= 0.005


@pytest.mark.parametrize("frac,want_y", [(0.2, 0.401), (0.5, 1.0025)])
def test_ac40_b_a_two_metre_pole_keeps_the_grip_at_the_origin(tmp_path, rules, frac, want_y):
    """Case (b): a 2.005 m vertex-sparse pole, window 121 bins, one thin run of 121. The origin (mid-shaft, y 1.0025, or at
    20 %, y 0.401) lies in it: the grip stays THERE. The rejected nearest-the-butt rule gripped it 15 cm from the butt."""
    geo, y = grip_of(tmp_path, rules, M.sparse_pole(), "club", 2.005, frac)
    assert geo["grip_source"] == "handle" and abs(y - want_y) <= 0.0005
    assert abs(y - 0.15) > 0.2
    assert abs(geo["grip_r_m"] - 0.015) <= 0.005


@pytest.mark.parametrize("frac", [0.0, 0.1, 0.2])
def test_ac40_c_a_machete_origin_in_the_hilt_stays_pivot_and_is_never_moved(tmp_path, rules, frac):
    """Case (c): hilt + knuckle guard 0.08 wide (bins 0-14), flat blade 0.05 wide (bins 15-42): by the surface profile the
    hilt is WIDER than the blade, p20 = 0.05, threshold 0.065, and the only counting run is the blade [15, 43), starting
    9 mm above the 20 % origin (y 0.141, bin 14) and well inside 10 % of the length (7 cm). The origin is in the butt-side
    30 % (< 0.2115), so it is never moved: pivot, grip at the origin, no radius. The rejected rule gripped the blade."""
    geo, y = grip_of(tmp_path, rules, M.sparse_machete(), "machete", 0.705, frac)
    assert geo["grip_source"] == "pivot" and geo["grip_r_m"] is None
    assert abs(y - max(frac * 0.705, BUTT_INSET)) <= 0.0005  # W2f: an origin at the butt is held 0.045 m off the end
    assert y < 0.15  # not on the blade


def test_ac40_c_the_machete_blade_does_count_when_the_origin_is_on_it(tmp_path, rules):
    """The control of case (c): with the origin on the blade (25 % = y 0.17625, bin 17, inside [15, 43)) the blade IS a
    counting run, so step 3 holds the grip at the origin with the blade's radius (mean e' ~ 0.048 -> 0.024)."""
    geo, y = grip_of(tmp_path, rules, M.sparse_machete(), "machete", 0.705, 0.25)
    assert geo["grip_source"] == "handle" and abs(y - 0.17625) <= 0.0005
    assert abs(geo["grip_r_m"] - 0.025) <= 0.005


def test_ac40_d_a_mid_origin_on_a_wide_head_snaps_onto_the_shaft_end(tmp_path, rules):
    """Case (d): sparse_paddle(4, 0.455): a thin shaft, then a 0.20 wide paddle from y 0.455 (bin 45) to the tip at 1.005.
    The one counting run is [0, 45) (hi = 0.45); the origin at 50 % (y 0.5025, bin 50, on the paddle) is 0.0525 from it,
    inside 10 % of the length (0.1005) and past 30 % of the length, so it snaps onto the run end kept min_run / 2 inside:
    min_run = max(2, min(6, 0.2 * 100.5 cm)) = 6 cm, so the grip is at 0.45 - 0.03 = 0.42. Source 'handle'."""
    geo, y = grip_of(tmp_path, rules, M.sparse_paddle(4, 0.455), "club", 1.005, 0.5)
    assert geo["axes"]["forward"] == "+y" and geo["axes"]["forward_source"] == "section"
    assert geo["grip_source"] == "handle" and abs(y - 0.42) <= 0.0005
    assert abs(geo["grip_r_m"] - 0.015) <= 0.005
    assert abs(geo["grip"][0]) <= 0.005 and abs(geo["grip"][2]) <= 0.005


def test_ac40_e_a_shaft_farther_than_ten_percent_stays_pivot(tmp_path, rules):
    """Case (e): the same mesh with the paddle from y 0.355 (bin 35): the run is [0, 35) (hi = 0.35), 0.1525 from the origin,
    farther than 10 % of the length (0.1005): step 5, pivot at the origin (y 0.5025), no radius."""
    geo, y = grip_of(tmp_path, rules, M.sparse_paddle(3, 0.355), "club", 1.005, 0.5)
    assert geo["grip_source"] == "pivot" and geo["grip_r_m"] is None
    assert abs(y - 0.5025) <= 0.0005


def test_ac40_f_an_origin_in_the_far_forty_percent_takes_step_4_or_5(tmp_path, rules):
    """Case (f). The window is the butt-side 60 %, so an origin in the far 40 % is outside every run and falls through to
    step 4 or 5. Under the natural forward rule the origin is always within 40 % of the butt (forward points away from it),
    so the case needs a forward override: the sparse haft with the origin 65 % and 75 % along +y, forward forced to +y.
    The shaft is one run [0, 61) (hi = 0.61). 65 %: y 0.65325, 0.04325 from the run end (inside 10 %, 0.1005): STEP 4, snaps
    to 0.61 - 0.03 = 0.58. 75 %: y 0.75375, 0.14375 away: STEP 5, pivot at the origin."""
    geo, y = grip_of(tmp_path, rules, M.sparse_haft(), "club", 1.005, 0.65, forward_override="+y")
    assert geo["axes"]["forward"] == "+y" and geo["axes"]["forward_source"] == "override"
    assert geo["grip_source"] == "handle" and abs(y - 0.58) <= 0.0005
    assert abs(geo["grip_r_m"] - 0.015) <= 0.005
    geo, y = grip_of(tmp_path, rules, M.sparse_haft(), "club", 1.005, 0.75, forward_override="+y")
    assert geo["grip_source"] == "pivot" and geo["grip_r_m"] is None and abs(y - 0.75375) <= 0.0005


def test_ac40_an_origin_outside_the_bounds_is_never_the_anchor(tmp_path, rules):
    """The origin of a mesh pushed 0.5 m off in x is outside the AABB: the pivot rule is not used (spec 3.5.5), so the
    surface step is skipped even though the origin's position on the long axis (y 0) lies inside a counting run."""
    path = M.write_glb(tmp_path / "far_haft.glb", [{"name": "h", "mesh": M.shifted(M.sparse_haft(), (0.5, 0, 0))}])
    d = measure_weapon_detail(path, None, 1.0, "club", "melee", "whole", rules, genre="fantasy")
    assert "origin_outside_bounds" in d["flags"]
    assert d["geometry"]["grip"] is None and d["geometry"]["grip_source"] is None and d["geometry"]["grip_r_m"] is None


def test_w2d_zigzag_grip_stays_at_the_pivot_inside_its_one_run(tmp_path, rules):
    """zigzag's surface profile makes its whole 30-bin window one thin run [0, 30) (the vertex profile alternates, so the
    base rule finds nothing). Shifted so its butt is at y 0 and measured with the origin at 20 % (0.10 m from the butt, bin
    10, inside the run): the run centre is 0.15, the origin 0.10, and the grip must follow the ORIGIN."""
    geo, y = grip_of(tmp_path, rules, M.shifted(M.zigzag(), (0.0, 0.15, 0.0)), "club", 0.5, 0.2)
    assert geo["grip_source"] == "handle" and abs(y - 0.10) <= 0.0005
    assert abs(geo["grip_r_m"] - 0.048) <= 0.001


@pytest.mark.parametrize("length,handle_bins,source,grip_y,radius", [
    (0.28, 12, "handle", 0.06, 0.01),  # step 1: the base rule's 12-bin run, centre 6 cm
    (0.28, 6, "handle", 0.045, 0.01),  # step 1: exactly the base rule's 6-bin minimum, centre 3 cm (W2f: pushed out to 4.5 cm)
    (0.28, 5, "pivot", 0.045, None),  # 5 bins: below the base minimum (6) and below the surface step's 5.6 cm -> 6 bins (W2f: grip 0 -> 4.5 cm)
    (0.18, 5, "handle", 0.045, 0.01),  # step 3: max(2, min(6, 3.6)) = 3.6 cm -> 4 bins <= 5; the origin (the butt) is inside (W2f: 0 -> 4.5 cm)
    (0.18, 4, "handle", 0.045, 0.01),  # step 3: exactly 4 bins (W2f: 0 -> 4.5 cm)
    (0.18, 3, "pivot", 0.045, None),  # 3 bins < 4 (W2f: 0 -> 4.5 cm)
])
def test_ac40_the_surface_minimum_run_scales_with_a_short_blade(tmp_path, rules, length, handle_bins, source, grip_y, radius):
    geo, y = grip_of(tmp_path, rules, M.short_blade(length, handle_bins), "knife", length, 0.0)
    assert geo["grip_source"] == source and abs(y - grip_y) <= 0.0005
    if radius is None:
        assert geo["grip_r_m"] is None
    else:
        assert abs(geo["grip_r_m"] - radius) <= 0.005


def test_ac40_the_3_mm_floor_keeps_a_hair_thin_window_from_collapsing_the_threshold(tmp_path, rules, monkeypatch):
    """The whip (make_glbs.w2d_wire) with the base rule out of the way, to isolate the surface step: a 1 mm filament fills
    24 of the 37 window bins, so p20 = 0.001 and the threshold would be 0.0013, which the 3.5 mm grip wire (bins 0-9, y
    0..0.095) exceeds. The 3 mm floor on w_ref keeps the threshold at 0.0039, the wire is thin, the origin at y 0.05 lies in
    its run: handle at the origin, r = 0.0035 / 2. (Without the floor the origin is in no run, in the butt-side 30 %: pivot.)"""
    monkeypatch.setattr(G, "_find_handle", lambda *args, **kwargs: None)
    geo, y = grip_of(tmp_path, rules, M.w2d_wire(), "whip", 0.605, 0.05 / 0.605)
    assert geo["grip_source"] == "handle" and abs(y - 0.05) <= 0.0005
    assert abs(geo["grip_r_m"] - 0.00175) <= 0.0005


def test_ac40_measurements_are_byte_identical_across_runs(w2d, rules, tmp_path):
    for name in sorted(M.W2D_SET):
        a = json.dumps(w2d_measure(w2d, rules, name, "mid"), sort_keys=True)
        b = json.dumps(w2d_measure(w2d, rules, name, "mid"), sort_keys=True)
        assert a == b
    for build, arch, length, frac in [(M.sparse_pole, "club", 2.005, 0.5), (M.sparse_machete, "machete", 0.705, 0.25)]:
        a = json.dumps(grip_of(tmp_path, rules, build(), arch, length, frac)[0], sort_keys=True)
        assert a == json.dumps(grip_of(tmp_path, rules, build(), arch, length, frac)[0], sort_keys=True)


def test_ac40_the_chunked_surface_sampling_gives_the_same_profile(rules, tmp_path, monkeypatch):
    """A 7-point sample chunk walks the chunked path edge by edge: the per-bin counts, minima and maxima are exactly those
    of the single chunk, the sums agree to rounding, and so do the measured grips."""
    meshes = [("sparse_haft", M.sparse_haft(), "club", 1.005, 0.5), ("sparse_machete", M.sparse_machete(), "machete", 0.705, 0.25),
              ("zigzag", M.zigzag(), "club", 0.5, 0.3)]
    whole = G._SURFACE_CHUNK
    stats, grips = {}, {}
    for chunk in (whole, 7):
        monkeypatch.setattr(G, "_SURFACE_CHUNK", chunk)
        for name, (v, t), arch, length, frac in meshes:
            fmin = float(v[:, 1].min())
            nb = int(np.ceil((float(v[:, 1].max()) - fmin) / 0.01 - 1e-6))
            stats[(name, chunk)] = G._surface_stats(v, t, 1, v[:, 1], fmin, nb, int(np.ceil(0.6 * nb)))
            grips[(name, chunk)] = json.dumps(grip_of(tmp_path, rules, (v, t), arch, length, frac, name=name)[0], sort_keys=True)
    for name, *_ in meshes:
        one, many = stats[(name, whole)], stats[(name, 7)]
        assert one.count.sum() > 0
        assert np.array_equal(one.count, many.count) and np.array_equal(one.lo, many.lo) and np.array_equal(one.hi, many.hi)
        assert np.allclose(one.total, many.total, rtol=0, atol=1e-12)
        assert grips[(name, whole)] == grips[(name, 7)]


# --- AC16: origin outside the AABB ---------------------------------------------------------------------------------

def test_ac16_origin_outside_bounds_is_flagged_and_never_grips_at_the_pivot(glbs, rules):
    d = meas(glbs, rules, "origin_outside", "rifle", "ranged", hold="long_gun", genre="modern")
    assert "origin_outside_bounds" in d["flags"] and "origin_outside_bounds" in d["reasons"]
    geo = d["geometry"]
    assert geo["grip_source"] != "pivot"
    assert geo["grip_source"] == "proportion"  # the rules table has an entry for rifle: [0.30, 0.45]
    assert close(geo["grip"], [0.0, 0.545, 0.92])
    # an archetype with no proportion entry gets no grip at all rather than a made-up one
    smg = meas(glbs, rules, "origin_outside", "smg", "ranged", hold="long_gun", genre="modern")["geometry"]
    assert smg["grip"] is None and smg["grip_source"] is None


def test_ac16_a_melee_with_the_origin_outside_falls_to_the_handle_or_null(glbs, rules, tmp_path):
    # zigzag has a surface run holding its origin's long-axis position: only the outside-the-AABB guard stops step 3
    path = M.write_glb(tmp_path / "far_zigzag.glb", [{"name": "z", "mesh": M.shifted(M.zigzag(), (0.5, 0, 0))}])
    d = measure_weapon_detail(path, None, 1.0, "club", "melee", "whole", rules, genre="fantasy")
    assert "origin_outside_bounds" in d["flags"]
    assert d["geometry"]["grip"] is None and d["geometry"]["grip_source"] is None
    # a real handle is still found without the pivot
    path = M.write_glb(tmp_path / "far_sword.glb", [{"name": "s", "mesh": M.shifted(M.sword(), (0.5, 0, 0))}])
    geo = measure_weapon_detail(path, None, 1.0, "sword", "melee", "whole", rules, genre="fantasy")["geometry"]
    assert geo["grip_source"] == "handle" and abs(geo["grip"][0] - 0.5) <= 0.005


# --- determinism and the cache ----------------------------------------------------------------------------------------

def test_measurement_is_deterministic_and_rounded_to_a_tenth_of_a_millimetre(glbs, rules):
    a = meas(glbs, rules, "sword", "sword", "melee")
    b = meas(glbs, rules, "sword", "sword", "melee")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def walk(x):
        if isinstance(x, float):
            assert x == round(x, 4) and str(x) != "-0.0"
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(a["geometry"])


def _count_decodes(monkeypatch):
    calls = []
    real = G.load_triangles

    def counting(*a, **k):
        calls.append(a[0])
        return real(*a, **k)

    monkeypatch.setattr(G, "load_triangles", counting)
    G._DECODE_MEMO.clear()
    return calls


def test_cached_equals_uncached_and_the_second_call_does_not_decode(glbs, rules, monkeypatch, tmp_path):
    calls = _count_decodes(monkeypatch)
    root = glbs["sword"].parent
    args = (root, "sword.glb", None, 1.0, "sword", "melee", "whole", rules)
    cache: dict = {}
    first, was = measure_cached(*args, cache, genre="fantasy")
    assert was is False and len(calls) == 1
    G._DECODE_MEMO.clear()
    second, was = measure_cached(*args, cache, genre="fantasy")
    assert was is True and len(calls) == 1  # served from the cache, the file was not decoded again
    uncached = measure_weapon_detail(glbs["sword"], None, 1.0, "sword", "melee", "whole", rules, genre="fantasy")
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True) == json.dumps(uncached, sort_keys=True)
    # through the file as well: save, load, hit
    path = tmp_path / "w" / G.CACHE_NAME
    G.save_cache(path, cache)
    third, was = measure_cached(*args, G.load_cache(path), genre="fantasy")
    assert was is True and json.dumps(third, sort_keys=True) == json.dumps(uncached, sort_keys=True)
    raw = path.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    G.save_cache(tmp_path / "w2" / G.CACHE_NAME, cache)
    assert (tmp_path / "w2" / G.CACHE_NAME).read_bytes() == raw


def test_cache_entry_is_keyed_on_file_version_and_classification_context(glbs, rules, monkeypatch, tmp_path):
    import synty_inventory.weapons as pkg

    calls = _count_decodes(monkeypatch)
    root = glbs["sword"].parent
    cache: dict = {}
    base = (root, "sword.glb", None, 1.0)
    measure_cached(*base, "sword", "melee", "whole", rules, cache, genre="fantasy")
    assert len(calls) == 1
    # another archetype is another context: measured again, and both results are then kept
    G._DECODE_MEMO.clear()  # the decode memo would otherwise hide the second read from the call counter
    spear, was = measure_cached(*base, "polearm", "melee", "whole", rules, cache, genre="fantasy")
    assert was is False and len(calls) == 2
    assert measure_cached(*base, "sword", "melee", "whole", rules, cache, genre="fantasy")[1] is True
    assert measure_cached(*base, "polearm", "melee", "whole", rules, cache, genre="fantasy")[1] is True
    assert spear == measure_weapon_detail(glbs["sword"], None, 1.0, "polearm", "melee", "whole", rules, genre="fantasy")
    # a different scale is another entry id
    G._DECODE_MEMO.clear()
    measure_cached(root, "sword.glb", None, 2.0, "sword", "melee", "whole", rules, cache, genre="fantasy")
    assert {k for k in cache} == {"sword.glb", "sword.glb#s2"}
    # a geometry version bump invalidates the entry
    monkeypatch.setattr(pkg, "WEAPON_GEOMETRY_VERSION", pkg.WEAPON_GEOMETRY_VERSION + 1)
    assert measure_cached(*base, "sword", "melee", "whole", rules, cache, genre="fantasy")[1] is False
    # so does rewriting the file (size changes the key)
    copy_path = tmp_path / "t.glb"
    copy_path.write_bytes(glbs["sword"].read_bytes())
    c2: dict = {}
    measure_cached(tmp_path, "t.glb", None, 1.0, "sword", "melee", "whole", rules, c2)
    copy_path.write_bytes(glbs["knife"].read_bytes())
    again, was = measure_cached(tmp_path, "t.glb", None, 1.0, "sword", "melee", "whole", rules, c2)
    assert was is False and again["geometry"]["length_m"] == 0.29


def test_a_version_3_cache_entry_is_not_served_under_geometry_version_4(glbs, rules, monkeypatch):
    """The v4 algorithm (W2f: melee grip kept off the butt, forward sign by the larger end head) changes stored geometry, so
    an entry written by v3 must be re-measured. The v3 entry is poisoned: serving it would be visible in the length. (Since
    W2f an entry's version is "<int>+<code digest>", see tests/test_weapons_w2f_cache.py.)"""
    import synty_inventory.weapons as pkg

    assert pkg.WEAPON_GEOMETRY_VERSION == 4  # a literal: the bump itself is under test
    root = glbs["sword"].parent
    args = (root, "sword.glb", None, 1.0, "sword", "melee", "whole", rules)
    cache: dict = {}
    monkeypatch.setattr(pkg, "WEAPON_GEOMETRY_VERSION", 3)
    old, was = measure_cached(*args, cache, genre="fantasy")
    assert was is False and cache["sword.glb"]["version"].startswith("3+")
    cache["sword.glb"]["by_inputs"][next(iter(cache["sword.glb"]["by_inputs"]))]["geometry"]["length_m"] = 999.0
    assert measure_cached(*args, cache, genre="fantasy")[1] is True  # still served under v3 ...
    monkeypatch.undo()  # ... and the real constant (4) must not take it
    fresh, was = measure_cached(*args, cache, genre="fantasy")
    assert was is False and fresh["geometry"]["length_m"] == 1.0
    assert cache["sword.glb"]["version"].startswith("4+")


def test_a_missing_file_is_not_cached_and_a_failure_is(glbs, rules, tmp_path):
    cache: dict = {}
    d, was = measure_cached(tmp_path, "absent.glb", None, 1.0, "sword", "melee", "whole", rules, cache)
    assert d["geometry"] is None and was is False and cache == {}
    root = glbs["garbage"].parent
    d, was = measure_cached(root, "garbage.glb", None, 1.0, "sword", "melee", "whole", rules, cache)
    assert d["geometry"] is None and was is False and len(cache) == 1
    assert measure_cached(root, "garbage.glb", None, 1.0, "sword", "melee", "whole", rules, cache)[1] is True


# --- pass 2: classification with a measured length ------------------------------------------------------------------------

def _asset(aid, **kw):
    return wfx_asset(aid, **kw)


def wfx_asset(aid, two=None):
    a = copy.deepcopy(next(iter(wfx.catalog_assets().values()))[1])
    a["id"] = aid
    a["gear"]["twoHanded"] = two
    a["gear"]["kind"] = "weapon"
    a["files"]["glb_node"] = None
    return a


MEASURED = {"length_m": 0.9, "forward_by_fallback": False, "axes_unexpected": False}


def _cls(rules, asset, measured=None, overrides=None, pack="FAKE_Pack"):
    return classify(asset, pack, rules, overrides or empty_overrides(), None, measured=measured)


def test_pass2_long_m_rule_fills_an_unknown_archetype_at_confidence_at_most_04(rules):
    r = copy.deepcopy(rules)
    r["rules"].append({"name": "len_rifle", "match": {"long_m": [0.7, 1.4]}, "set": {"role": "whole", "archetype": "rifle"},
                       "confidence": 0.8})
    asset = wfx_asset("SM_Wep_Gun_Mystery_01")
    before = _cls(r, asset)
    assert before["archetype"] == "unknown" and before["matched_rule"] == "generic_gun"
    after = _cls(r, asset, MEASURED)
    assert after["archetype"] == "rifle" and after["kind"] == "ranged" and after["hold_class"] == "long_gun"
    assert after["confidence"] <= 0.4 and after["matched_rule"] == "len_rifle"
    assert after["provenance"]["archetype"] == "measured"
    # a length outside the rule's range fills nothing
    assert _cls(r, asset, {**MEASURED, "length_m": 0.3})["archetype"] == "unknown"
    # an already-known archetype is never re-decided by length
    pistol = _cls(r, wfx_asset("SM_Wep_Pistol_09"), MEASURED)
    assert pistol["archetype"] == "pistol" and pistol["matched_rule"] != "len_rifle"


def test_pass2_without_measurement_nothing_length_dependent_fires(rules):
    r = copy.deepcopy(rules)
    r["rules"].append({"name": "len_rifle", "match": {"long_m": [0.7, 1.4]}, "set": {"role": "whole", "archetype": "rifle"},
                       "confidence": 0.8})
    assert _cls(r, wfx_asset("SM_Wep_Gun_Mystery_01"))["archetype"] == "unknown"
    assert _cls(r, wfx_asset("SM_Wep_Sword_09"))["hold_class"] == "melee_one"


def test_pass2_plausibility_and_forward_penalties_are_the_spec_amounts(rules):
    asset = wfx_asset("SM_Wep_Pistol_09")
    ok = _cls(rules, asset, {"length_m": 0.2, "forward_by_fallback": False, "axes_unexpected": False})["confidence"]
    assert round(ok - _cls(rules, asset, {"length_m": 1.5, "forward_by_fallback": False,
                                          "axes_unexpected": False})["confidence"], 2) == 0.25
    assert round(ok - _cls(rules, asset, {"length_m": 0.2, "forward_by_fallback": True,
                                          "axes_unexpected": False})["confidence"], 2) == 0.15
    assert round(ok - _cls(rules, asset, {"length_m": 0.2, "forward_by_fallback": False,
                                          "axes_unexpected": True})["confidence"], 2) == 0.15
    bare = _cls(rules, asset)["confidence"]
    assert bare == ok  # a plausible, unflagged measurement changes nothing
    both = _cls(rules, asset, {"length_m": 1.5, "forward_by_fallback": True, "axes_unexpected": True})["confidence"]
    assert round(ok - both, 2) == 0.55  # the three penalties stack: 0.25 + 0.15 + 0.15


def test_pass2_overrides_still_win_with_confidence_one(rules):
    asset = wfx_asset("SM_Wep_Pistol_09")
    ov = {"schema": "weapon-overrides/1", "ids": {"FAKE_Pack/SM_Wep_Pistol_09": {"set": {"archetype": "club"}}}, "globs": {}}
    out = _cls(rules, asset, {"length_m": 9.0, "forward_by_fallback": True, "axes_unexpected": True}, overrides=ov)
    assert out["confidence"] == 1.0 and out["archetype"] == "club"


@pytest.mark.parametrize("arch,length,two,want", [
    ("sword", 1.2, None, "melee_two"),  # long_blade_two_handed: >= 1.1 m
    ("sword", 1.1, None, "melee_two"),
    ("sword", 1.0, None, "melee_one"),
    ("axe", 1.3, None, "melee_two"),
    ("hammer", 1.2, None, "melee_two"),  # beats the hammer -> melee_bat default
    ("hammer", 0.8, None, "melee_bat"),
    ("knife", 1.5, None, "melee_one"),  # the exception names sword/axe/mace/hammer only
    ("sword", 0.5, True, "melee_two"),  # gear.twoHanded still works without a length
])
def test_pass2_long_blade_exception_needs_the_measured_length(rules, arch, length, two, want):
    asset = wfx_asset(f"SM_Wep_{arch.capitalize()}_09", two=two)
    got = _cls(rules, asset, {"length_m": length, "forward_by_fallback": False, "axes_unexpected": False})
    assert got["archetype"] == arch and got["hold_class"] == want
    if two is None:  # pass 1 (no length) takes the table default
        assert _cls(rules, asset)["hold_class"] == {"sword": "melee_one", "axe": "melee_one", "hammer": "melee_bat",
                                                    "knife": "melee_one"}[arch]


# --- end to end: build with generated GLBs ---------------------------------------------------------------------------

def _make_threejs(tmp_path, cat, *, garbage=(), absent=(), empty=()):
    """Generate a stand-in GLB for every fixture record from a no-geometry pass; returns the threejs_v2 root."""
    root = tmp_path / "threejs"
    base, _ = wfx.build(cat, measure=False)
    for rec in base["weapons"]:
        rel = rec["files"].get("glb")
        if not rel:
            continue
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if rec["id"] in absent:
            continue
        if rec["id"] in garbage:
            dest.write_bytes(b"not a glb")
        elif rec["id"] in empty:
            M.write_glb(dest, [{"name": "Empty"}])
        else:
            mesh = M.mesh_for(rec["archetype"], rec["kind"], rec["role"])
            roots = [{"name": rec["asset_id"], "mesh": mesh}]
            if rec["kind"] == "ranged":
                roots.append({"name": "SM_Fixture_Collision", "mesh": M.box((-1, -1, -1), (1, 1, 1))})
            M.write_glb(dest, roots)
    return root


@pytest.fixture(scope="module")
def e2e(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e")
    cat = wfx.make_catalogs_dir(tmp)
    victims = {
        "garbage": {"FAKE_Modern/SM_Wep_Rifle_Assault_01"},
        "absent": {"FAKE_Modern/SM_Wep_Carbine_01"},
        "empty": {"FAKE_Fantasy/SM_Wep_Sword_02"},
    }
    root = _make_threejs(tmp, cat, **{k: v for k, v in victims.items()})
    cache: dict = {}
    directory, excluded, report = build_directory_report(
        cat, overrides=empty_overrides(), pack_settings=wfx.pack_settings(), threejs_v2_dir=root, geometry_cache=cache,
    )
    return {"cat": cat, "root": root, "dir": directory, "excl": excluded, "report": report, "cache": cache,
            "victims": victims}


def test_e2e_the_strict_schema_accepts_the_measured_directory(e2e):
    assert validate_directory(e2e["dir"], e2e["excl"]) == []


def test_e2e_every_record_with_a_decodable_glb_is_measured(e2e):
    victims = set().union(*e2e["victims"].values())
    for rec in e2e["dir"]["weapons"]:
        if rec["files"].get("glb") and rec["id"] not in victims:
            assert rec["geometry"] is not None, rec["id"]
            assert "unmeasured" not in rec["flags"] and "no_geometry" not in rec["review"]["reasons"], rec["id"]
            assert rec["provenance"]["geometry"] == "measured"
        else:
            assert rec["geometry"] is None and "unmeasured" in rec["flags"], rec["id"]
        assert rec["provenance"]["hints"] == "rules"


def test_e2e_ac15_failures_are_null_flagged_and_do_not_touch_siblings(e2e):
    by_id = wfx.records_by_id(e2e["dir"])
    for rid in set().union(*e2e["victims"].values()):
        rec = by_id[rid]
        assert rec["geometry"] is None and "unmeasured" in rec["flags"]
        assert "no_geometry" in rec["review"]["reasons"]
        assert rec["hints"]["size_class"] is None and rec["hints"]["inventory_cells"] is None
    # the garbage-file rifle has a numbered sibling in the same family: it keeps its own measurement (INV-6)
    sibling = by_id["FAKE_Modern/SM_Wep_Rifle_Assault_02"]
    assert by_id["FAKE_Modern/SM_Wep_Rifle_Assault_01"]["family"] == sibling["family"]
    assert sibling["geometry"] is not None and sibling["geometry"]["length_m"] == 0.9
    # a whole weapon with a known archetype keeps its tier even without geometry (AC35)
    assert by_id["FAKE_Modern/SM_Wep_Carbine_01"]["hints"]["quality_tier"] in (1, 2, 3, 4, 5)


def test_e2e_report_carries_the_real_geometry_coverage(e2e):
    rep = e2e["report"]
    with_glb = [r for r in e2e["dir"]["weapons"] if r["files"].get("glb")]
    measured = [r for r in with_glb if r["geometry"] is not None]
    assert len(with_glb) - len(measured) == 3
    assert rep["geometry_coverage"] == round(len(measured) / len(with_glb), 4)
    assert 0.9 < rep["geometry_coverage"] < 1.0
    assert rep["geometry_stats"]["decoded"] >= len(measured) and rep["geometry_stats"]["cached"] == 0


def test_e2e_reasons_flags_and_hints_reflect_the_measurement(e2e):
    by_id = wfx.records_by_id(e2e["dir"])
    rifle = by_id["FAKE_Modern/SM_Wep_Rifle_Assault_02"]
    g = rifle["geometry"]
    assert rifle["hold_class"] == "long_gun" and g["support"] is not None and g["muzzle"] is not None
    assert g["bounds"]["max"][2] == 0.65  # the generated collision box is ignored
    # 0.90 m sits exactly on a size cut and takes the upper class
    assert rifle["hints"]["size_class"] == "large" and rifle["hints"]["inventory_cells"] == [3, 1]
    assert rifle["hints"]["size_basis"] == "measured" and rifle["hints"]["ammo_family"] == "rifle"
    # a mech-scale record keeps its measurement but is sized from the raw length
    mech = by_id["FAKE_Mech/SM_Wep_Rifle_Mech_01"]
    assert "mech_scale" in mech["flags"] and mech["hints"]["size_basis"] == "raw"
    # plasma/laser ids on a rifle are energy weapons, and a plasma token is a tier-up token
    assert by_id["FAKE_SciFi/SM_Wep_Plasma_Rifle_02"]["hints"]["ammo_family"] == "energy"
    assert by_id["FAKE_SciFi/SM_Wep_Plasma_Rifle_02"]["hints"]["quality_tier"] == 4
    # the stand-in bows (make_glbs.bow) have a readable belly: measured by the bow rule, so not a fallback
    bows = [r for r in e2e["dir"]["weapons"] if r["archetype"] == "bow" and r["geometry"] is not None]
    assert bows and all(
        r["geometry"]["axes"]["forward_source"] == "bow_rule" and "forward_by_fallback" not in r["flags"] for r in bows
    )


def test_e2e_determinism_and_cache_equals_uncached(e2e, tmp_path):
    cat, root = e2e["cat"], e2e["root"]
    kw = dict(overrides=empty_overrides(), pack_settings=wfx.pack_settings(), threejs_v2_dir=root)
    uncached, _, _ = build_directory_report(cat, **kw)
    assert to_text(uncached) == to_text(e2e["dir"])  # a throwaway cache gives the same bytes as the filled one
    path = tmp_path / "w" / G.CACHE_NAME
    G.save_cache(path, e2e["cache"])
    G._DECODE_MEMO.clear()
    warm, _, report = build_directory_report(cat, geometry_cache=G.load_cache(path), **kw)
    # the warm cache serves every file that exists (failures included); only the absent file is retried
    assert report["geometry_stats"]["decoded"] == 1
    assert report["geometry_stats"]["cached"] > 0
    assert to_text(warm) == to_text(e2e["dir"]) == to_text(uncached)


def test_e2e_measure_false_and_a_missing_root_keep_the_unmeasured_stub(e2e):
    kw = dict(overrides=empty_overrides(), pack_settings=wfx.pack_settings())
    off, _, rep = build_directory_report(e2e["cat"], measure=False, threejs_v2_dir=e2e["root"], **kw)
    assert all(r["geometry"] is None and "unmeasured" in r["flags"] for r in off["weapons"])
    assert validate_directory(off, e2e["excl"]) == []  # hints are still derived, so the strict schema holds
    no_root, _, rep2 = build_directory_report(e2e["cat"], **kw)
    assert all(r["geometry"] is None for r in no_root["weapons"])
    assert any("threejs_v2" in w for w in rep2["warnings"])


def test_e2e_glb_scale_in_the_catalog_reaches_the_measurement(tmp_path):
    cat = wfx.make_catalogs_dir(tmp_path)
    root = _make_threejs(tmp_path, cat)
    path = next(cat.glob("FAKE_Modern.json"))
    doc = json.loads(path.read_text(encoding="utf-8"))
    for a in doc["assets"]:
        if a["id"] == "SM_Wep_Rifle_Assault_02":
            a["files"]["glb_scale"] = 2.0
    path.write_text(json.dumps(doc), encoding="utf-8")
    directory, _, _ = build_directory_report(cat, overrides=empty_overrides(), pack_settings=wfx.pack_settings(),
                                             threejs_v2_dir=root)
    rec = wfx.records_by_id(directory)["FAKE_Modern/SM_Wep_Rifle_Assault_02"]
    assert rec["geometry"]["length_m"] == 1.8


# --- the CLI ---------------------------------------------------------------------------------------------------------

def test_cli_build_measures_writes_the_cache_and_reuses_it(tmp_path, monkeypatch, capsys):
    from synty_inventory.cli import main

    for key in ("SYNTI_CONFIG", "SYNTI_UNITY_ROOT", "SYNTI_EXTRACTED_ROOT", "SYNTI_THREEJS_V2", "SYNTI_VIEWER_DATA",
                "SYNTI_CATALOGS", "SYNTI_GODOT_ROOT", "SYNTI_UNREAL_ROOT", "SYNTI_SYNTY_GLB_ROOT"):
        monkeypatch.delenv(key, raising=False)
    cat = wfx.make_catalogs_dir(tmp_path)
    root = _make_threejs(tmp_path, cat)
    cfg = tmp_path / "config.yaml"
    cfg.write_text("\n".join([
        f'unity_root: "{tmp_path.as_posix()}/unity"', f'extracted_root: "{tmp_path.as_posix()}/extracted"',
        f'threejs_v2: "{root.as_posix()}"', f'catalogs: "{cat.as_posix()}"']) + "\n", encoding="utf-8")
    import synty_inventory.packs.profile as profile

    monkeypatch.setattr(profile, "load_settings_table", lambda *a, **k: wfx.pack_settings())

    def run(*argv):
        capsys.readouterr()
        code = main(["--config", str(cfg), *argv])
        return code, json.loads(capsys.readouterr().out)

    code, out = run("weapons", "build")
    assert code == 0, out
    rep = out["report"]
    assert rep["geometry"] == "measured" and rep["geometry_coverage"] == 1.0 and rep["geometry_stats"]["decoded"] > 0
    wdir = cat / "weapons"
    assert sorted(p.name for p in wdir.iterdir()) == ["_geometry_cache.json", "directory.json", "excluded.json"]
    first = (wdir / "directory.json").read_bytes()
    cache_bytes = (wdir / "_geometry_cache.json").read_bytes()
    assert validate_directory(json.loads(first), json.loads((wdir / "excluded.json").read_bytes())) == []

    G._DECODE_MEMO.clear()
    code, out = run("weapons", "build")
    assert code == 0 and out["report"]["geometry_stats"]["decoded"] == 0 and out["report"]["geometry_stats"]["cached"] > 0
    assert (wdir / "directory.json").read_bytes() == first
    assert (wdir / "_geometry_cache.json").read_bytes() == cache_bytes

    code, out = run("weapons", "build", "--rebuild")
    assert code == 0 and out["report"]["geometry_stats"]["cached"] == 0
    assert (wdir / "directory.json").read_bytes() == first  # cached == uncached, byte for byte

    code, out = run("weapons", "build", "--no-geometry")
    assert out["report"]["geometry"] == "skipped (--no-geometry)" and out["report"]["geometry_coverage"] == 0.0
