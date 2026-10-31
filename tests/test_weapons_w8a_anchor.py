"""W8a: attachment anchors and the placement math (AC63, AC64, AC65; docs/weapon_attachments.md 3.1, 3.4).

Every expected number is a literal worked out by hand in tests/fixtures/weapons/w8a_attach.py, never read from the code.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np
import pytest

_spec = importlib.util.spec_from_file_location("w8a_attach", Path(__file__).parent / "fixtures" / "weapons" / "w8a_attach.py")
A = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A)

from synty_inventory.weapons.attach import frame_matrix, measure_anchor, place  # noqa: E402

POINT_TOL_M = 0.001  # AC63: the point within 1 mm
ANGLE_TOL_DEG = 0.5  # AC63: the up within 0.5 degrees
BOTTOM_SLOTS = ("optic", "laser_light")  # foot at -Y
TOP_SLOTS = ("underbarrel", "magazine")  # foot at +Y
# E3.23: step 3 takes the authored z as the along-rail axis of every foot slot (it no longer picks the longer horizontal extent). The AC63 yaw sweep
# used to turn the optic by every quarter turn and expect the anchor to follow the part's own long axis (forward and point yawed with it). A quarter
# turn (1 or 3) leaves the part long in x, outside the prior the rule documents (attach._foot_anchor): the rule reads z in the part's own frame, so
# forward stays +-z and the foot is read across the short side, which is the very reading E3.23 ends (AC153, test_weapons_e323_axis). That
# scenario does not exist under z, so there is no yawed expectation to re-express; the half turns, which keep the part long in z and only flip its
# sign, are the yaw cases that still exist and keep their literals unchanged. (Measured on the build: turn 1 and 3 give forward [0, 0, 1], point
# [-0.01, 0, 0] / [0.01, 0, 0], source `authored`, symmetric: not the yawed frame, by design.)
HALF_TURNS = (0, 2)
SPEC_ID = "FAKE_Attach/SM_Wep_Rifle_Scope_01"


def angle_deg(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    cos = float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def assert_frame(frame, point, up, forward=None):
    assert np.allclose(frame["point"], point, atol=POINT_TOL_M), (frame["point"], point)
    assert angle_deg(frame["up"], up) < ANGLE_TOL_DEG, (frame["up"], up)
    if forward is not None:
        assert angle_deg(frame["forward"], forward) < ANGLE_TOL_DEG, (frame["forward"], forward)


# --- AC63: the point is the contact patch, the up is the side the foot is on ---------------------------------------


@pytest.mark.parametrize("quarter_turns", HALF_TURNS)
@pytest.mark.parametrize("slot", BOTTOM_SLOTS)
def test_ac63_a_bottom_foot_part_anchors_at_the_offset_foot_not_the_aabb_centre(slot, quarter_turns):
    v, _ = A.yaw(A.optic(), quarter_turns)
    got = measure_anchor(v, slot)
    assert_frame(got["anchor"], A.yaw_vec((0.005, 0.0, 0.05), quarter_turns), (0.0, 1.0, 0.0),
                 A.yaw_vec((0.0, 0.0, 1.0), quarter_turns))
    assert got["anchor"]["foot_source"] == "authored_up" and got["anchor"]["forward_source"] == "section"
    assert got["reasons"] == []


@pytest.mark.parametrize("quarter_turns", HALF_TURNS)
@pytest.mark.parametrize("slot", TOP_SLOTS)
def test_ac63_a_top_foot_part_points_its_up_down_into_the_host(slot, quarter_turns):
    v, _ = A.yaw(A.flip_y(A.optic()), quarter_turns)
    got = measure_anchor(v, slot)
    assert_frame(got["anchor"], A.yaw_vec((0.005, 0.0, 0.05), quarter_turns), (0.0, -1.0, 0.0),
                 A.yaw_vec((0.0, 0.0, 1.0), quarter_turns))
    assert got["anchor"]["foot_source"] == "authored_up"


def test_ac63_the_footprint_is_the_part_box_and_the_foot_patch_in_the_anchor_axes():
    for quarter_turns in HALF_TURNS:  # E3.23: the quarter turns put the part long in x, outside the forced-z prior (see HALF_TURNS)
        v, _ = A.yaw(A.optic(), quarter_turns)
        fp = measure_anchor(v, "optic")["footprint"]
        assert fp["length_m"] == pytest.approx(0.2, abs=0.001) and fp["width_m"] == pytest.approx(0.06, abs=0.001)
        assert fp["height_m"] == pytest.approx(0.08, abs=0.001)
        assert fp["foot_length_m"] == pytest.approx(0.06, abs=0.001) and fp["foot_width_m"] == pytest.approx(0.02, abs=0.001)
        assert fp["mate_d_m"] is None


def test_ac63_a_foot_on_the_wrong_end_is_found_at_the_other_end_and_says_measured():
    v, _ = A.upside_down_optic()
    got = measure_anchor(v, "optic")  # authored for a -Y foot, but the bottom is an apex (one point)
    assert got["anchor"]["foot_source"] == "measured"
    assert_frame(got["anchor"], (0.0, 0.03, 0.0), (0.0, -1.0, 0.0))


def test_ac63_a_part_with_no_foot_at_either_end_has_no_anchor_and_says_so():
    v, _ = A.footless()
    got = measure_anchor(v, "optic")
    assert got["anchor"] is None and got["footprint"] is None
    assert got["reasons"] == ["anchor_unmeasured"]
    assert measure_anchor(np.zeros((0, 3)), "optic")["reasons"] == ["anchor_unmeasured"]


def test_ac63_the_directory_record_carries_the_anchor_of_each_fixture_part(tmp_path):
    directory, *_ = A.build(tmp_path)
    recs = {w["asset_id"]: w for w in directory["weapons"]}
    bottom = recs["SM_Wep_Rifle_Scope_01"]["attachment"]
    assert_frame(bottom["anchor"], A.FOOT_CENTRE, (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    assert bottom["footprint"] == {"length_m": 0.2, "width_m": 0.06, "height_m": 0.08, "foot_length_m": 0.06,
                                   "foot_width_m": 0.02, "mate_d_m": None}
    top = recs["SM_Wep_Rifle_Mag_01"]["attachment"]
    assert_frame(top["anchor"], A.FOOT_CENTRE, (0.0, -1.0, 0.0), (0.0, 0.0, 1.0))
    assert recs["SM_Wep_Footless_Scope_01"]["attachment"]["anchor"] is None
    assert "anchor_unmeasured" in recs["SM_Wep_Footless_Scope_01"]["review"]["reasons"]
    assert recs["SM_Wep_Footless_Scope_01"]["review"]["confidence"] == 0.81  # 0.9 * 0.9


# --- AC64: the forward sign from the end section, and the coin flip ------------------------------------------------


def test_ac64_the_objective_flare_sets_forward_from_the_geometry():
    got = measure_anchor(A.optic()[0], "optic")["anchor"]
    assert got["forward"] == [0.0, 0.0, 1.0] and got["forward_source"] == "section" and got["symmetric"] is False
    mirrored = measure_anchor(A.flip_z(A.optic())[0], "optic")["anchor"]
    assert mirrored["forward"] == [0.0, 0.0, -1.0] and mirrored["forward_source"] == "section"
    assert_frame(mirrored, (0.005, 0.0, -0.05), (0.0, 1.0, 0.0))


def test_ac64_identical_ends_are_symmetric_authored_and_flagged():
    got = measure_anchor(A.symmetric_box()[0], "optic")
    assert got["anchor"]["symmetric"] is True and got["anchor"]["forward_source"] == "authored"
    assert got["anchor"]["forward"] == [0.0, 0.0, 1.0]  # the authored +Z
    assert got["reasons"] == ["anchor_forward_unsure"]


def test_ac64_a_forward_override_on_the_rail_axis_decides_the_sign():
    v = A.optic()[0]
    flipped = measure_anchor(v, "optic", forward_override="-z")["anchor"]
    assert flipped["forward"] == [0.0, 0.0, -1.0] and flipped["forward_source"] == "override"
    sym = measure_anchor(A.symmetric_box()[0], "optic", forward_override="-z")
    assert sym["anchor"]["forward"] == [0.0, 0.0, -1.0] and sym["anchor"]["forward_source"] == "override"
    assert sym["anchor"]["symmetric"] is False and sym["reasons"] == []


def test_ac64_a_forward_override_on_another_axis_is_ignored():
    sym = measure_anchor(A.symmetric_box()[0], "optic", forward_override="+x")
    assert sym["anchor"]["symmetric"] is True and sym["anchor"]["forward_source"] == "authored"
    assert measure_anchor(A.optic()[0], "optic", forward_override="+y")["anchor"]["forward_source"] == "section"
    assert measure_anchor(A.optic()[0], "optic", forward_override="sideways")["anchor"]["forward_source"] == "section"


def test_ac64_the_directory_caps_a_symmetric_record_below_the_review_line(tmp_path):
    directory, *_ = A.build(tmp_path)
    rec = {w["asset_id"]: w for w in directory["weapons"]}["SM_Wep_Symmetric_Scope_01"]
    assert rec["attachment"]["anchor"]["symmetric"] is True
    assert rec["review"]["confidence"] == 0.59
    assert {"anchor_forward_unsure", "low_confidence"} <= set(rec["review"]["reasons"])
    sure = {w["asset_id"]: w for w in directory["weapons"]}["SM_Wep_Rifle_Scope_01"]
    assert sure["review"]["confidence"] == 0.9 and "anchor_forward_unsure" not in sure["review"]["reasons"]


def test_ac64_an_id_override_sets_the_forward_and_clears_the_flag_in_the_directory(tmp_path):
    ids = {"FAKE_Attach/SM_Wep_Symmetric_Scope_01": {"forward": "-z"}, SPEC_ID: {"forward": "-z"}}
    directory, *_ = A.build(tmp_path, overrides=A.WFX.overrides_doc(ids=ids))
    recs = {w["asset_id"]: w for w in directory["weapons"]}
    sym = recs["SM_Wep_Symmetric_Scope_01"]
    assert sym["attachment"]["anchor"]["forward"] == [0.0, 0.0, -1.0]
    assert sym["attachment"]["anchor"]["forward_source"] == "override" and sym["attachment"]["anchor"]["symmetric"] is False
    assert sym["review"]["confidence"] == 0.9 and "anchor_forward_unsure" not in sym["review"]["reasons"]
    assert recs["SM_Wep_Rifle_Scope_01"]["attachment"]["anchor"]["forward"] == [0.0, 0.0, -1.0]


# --- AC65: a muzzle device mates with its narrow end ---------------------------------------------------------------


@pytest.mark.parametrize("quarter_turns", range(4))
@pytest.mark.parametrize("flipped", (False, True))
def test_ac65_the_narrow_end_mates_and_up_points_to_the_wide_end(flipped, quarter_turns):
    mesh = A.flip_z(A.suppressor()) if flipped else A.suppressor()
    v, _ = A.yaw(mesh, quarter_turns)
    got = measure_anchor(v, "muzzle")
    point = (0.0, 0.0, 0.1) if flipped else A.MUZZLE_POINT
    up = (0.0, 0.0, -1.0) if flipped else (0.0, 0.0, 1.0)
    assert_frame(got["anchor"], A.yaw_vec(point, quarter_turns), A.yaw_vec(up, quarter_turns))
    assert got["anchor"]["foot_source"] == "measured" and got["anchor"]["forward_source"] == "authored"
    assert got["anchor"]["symmetric"] is False
    assert got["anchor"]["forward"] == [0.0, 1.0, 0.0]  # the authored +Y, perpendicular to every yawed bore
    assert got["footprint"]["mate_d_m"] == pytest.approx(0.026, abs=0.001)
    assert got["footprint"]["height_m"] == pytest.approx(0.2, abs=0.001)


def test_ac65_the_directory_records_the_muzzle_mate_diameter(tmp_path):
    directory, *_ = A.build(tmp_path)
    rec = {w["asset_id"]: w for w in directory["weapons"]}["SM_Wep_Silencer_01"]
    assert_frame(rec["attachment"]["anchor"], A.MUZZLE_POINT, (0.0, 0.0, 1.0), (0.0, 1.0, 0.0))
    assert rec["attachment"]["footprint"]["mate_d_m"] == pytest.approx(0.026, abs=0.001)


def test_ac65_a_bore_along_y_takes_its_roll_from_the_authored_z():
    v = np.stack([A.suppressor()[0][:, 0], A.suppressor()[0][:, 2], A.suppressor()[0][:, 1]], axis=1)  # bore on Y
    got = measure_anchor(v, "muzzle")["anchor"]
    assert got["up"] == [0.0, 1.0, 0.0] and got["forward"] == [0.0, 0.0, 1.0]


# --- placement: part_T = T(mount) * T(anchor)^-1 --------------------------------------------------------------------

# A rotation of order 3 (x -> y -> z -> x): it is not its own inverse, so the transpose is a different matrix.
THREE_CYCLE_MOUNT = {"point": [0.1, 0.2, 0.3], "forward": [1.0, 0.0, 0.0], "up": [0.0, 0.0, 1.0]}  # right = up x forward = +y
IDENTITY_ANCHOR = {"point": [0.0, 0.0, 0.0], "forward": [0.0, 0.0, 1.0], "up": [0.0, 1.0, 0.0]}  # right = up x forward = +x


def test_place_with_the_identity_anchor_is_the_mount_transform_and_not_its_inverse():
    m = place(IDENTITY_ANCHOR, THREE_CYCLE_MOUNT)
    # the part's local x, y, z axes land on the mount's right (+y), up (+z) and forward (+x)
    assert np.allclose(m[:3, :3] @ [1, 0, 0], [0, 1, 0])
    assert np.allclose(m[:3, :3] @ [0, 1, 0], [0, 0, 1])
    assert np.allclose(m[:3, :3] @ [0, 0, 1], [1, 0, 0])
    assert np.allclose(m[:3, 3], [0.1, 0.2, 0.3])
    assert np.allclose(m[:3, :3] @ m[:3, :3].T, np.eye(3)) and np.linalg.det(m[:3, :3]) == pytest.approx(1.0)
    # the 3-cycle applied three times is the identity; its transpose is not the same matrix
    assert not np.allclose(m[:3, :3], m[:3, :3].T)
    assert np.allclose(np.linalg.matrix_power(m[:3, :3], 3), np.eye(3))


def test_place_puts_the_anchor_point_on_the_mount_point_and_the_axes_on_the_mount_axes():
    anchor = {"point": [0.005, 0.0, 0.05], "forward": [0.0, 0.0, 1.0], "up": [0.0, 1.0, 0.0]}
    m = place(anchor, THREE_CYCLE_MOUNT)
    assert np.allclose(m @ [0.005, 0.0, 0.05, 1.0], [0.1, 0.2, 0.3, 1.0])
    assert np.allclose(m[:3, :3] @ anchor["up"], THREE_CYCLE_MOUNT["up"])
    assert np.allclose(m[:3, :3] @ anchor["forward"], THREE_CYCLE_MOUNT["forward"])
    # a point 0.1 m up the part sits 0.1 m up the mount
    assert np.allclose(m @ [0.005, 0.1, 0.05, 1.0], [0.1, 0.2, 0.4, 1.0])
    # and one 0.1 m forward is 0.1 m along the mount's forward (+x)
    assert np.allclose(m @ [0.005, 0.0, 0.15, 1.0], [0.2, 0.2, 0.3, 1.0])


def test_frame_matrix_columns_are_right_up_forward():
    m = frame_matrix(THREE_CYCLE_MOUNT)
    assert np.allclose(m[:3, 0], [0, 1, 0]) and np.allclose(m[:3, 1], [0, 0, 1]) and np.allclose(m[:3, 2], [1, 0, 0])
    assert np.allclose(m[:3, 3], THREE_CYCLE_MOUNT["point"])
