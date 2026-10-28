"""W8m: settle to contact (docs/weapon_attachments.md 5.4; AC112 (i) to (xii)).

The hosts are the boxes of ``w8m_world`` (pack FAKE_W8M, nothing from a real pack). Each host seats its baked scope (or grip) child at a
hand-chosen height, the part's anchor lands on that seat, and the gap or the sunk depth against the host body is the literal in the
comment of its row. Every expected number below is worked out from those dimensions, never read from the code under test.
"""

from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8m_world", FIX / "w8m_world.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)
W = M.W

from synty_inventory.weapons import attach, directory as dirmod  # noqa: E402


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    directory, _, _, root = W.build(tmp_path_factory.mktemp("w8m_contact"), M.world(), rules=M.uncapped_rules())
    return SimpleNamespace(directory=directory, by_id=W.by_id(directory), root=root)


def entry(built, part: str, case: str) -> dict:
    att = built.by_id[M.pid(part)]["attachment"]
    return next(e for e in att["compatible_hosts"] if e["host"] == M.hid(case))


def shift(built, part: str, case: str):
    return entry(built, part, case).get("seat_shift_m")


# --- the fixture is what the comments say ------------------------------------------------------------------------------------


def test_the_pairs_are_natural_same_pack_pairs_on_child_node_seats(built):
    for case in ("Hover", "Sunk", "Tube", "Tall", "Collide", "Shoulder", "Wing"):
        host = built.by_id[M.hid(case)]
        mount = host["geometry"]["mounts"]["optic"]
        assert mount["source"] == "child_node" and mount["up"] == [0.0, 1.0, 0.0], case
        assert entry(built, M.SCOPE_PART, case)["tier"] == "same_pack_fit", case
    grip = built.by_id[M.hid("UbGap")]["geometry"]["mounts"]["underbarrel"]
    assert grip["source"] == "child_node" and grip["up"] == [0.0, -1.0, 0.0] and grip["point"] == [0.0, -0.012, 0.0]
    assert built.by_id[M.pid(M.SCOPE_PART)]["attachment"]["anchor"]["point"] == [0.0, 0.0, 0.0]  # the part's foot centre


# --- (i) to (v): the signed distance and the clamp ----------------------------------------------------------------------------


def test_ac112_i_an_optic_11_mm_above_the_receiver_moves_down_11_mm(built):
    assert shift(built, M.SCOPE_PART, "Hover") == pytest.approx(-0.0110, abs=0.0005)  # child foot 0.111, body top 0.100


def test_ac112_ii_an_optic_sunk_8_mm_moves_up_8_mm(built):
    assert shift(built, M.SCOPE_PART, "Sunk") == pytest.approx(+0.0080, abs=0.0005)  # child foot 0.092


def test_ac112_iii_a_gap_of_2_9_mm_has_no_key_and_3_1_mm_has_one(built):
    assert "seat_shift_m" not in entry(built, M.SCOPE_PART, "Near")  # child foot 0.1029
    assert shift(built, M.SCOPE_PART, "Far") == pytest.approx(-0.0031, abs=0.00005)  # child foot 0.1031


def test_ac112_iv_an_underbarrel_part_12_mm_below_a_rail_and_one_sunk_37_7_mm(built):
    assert shift(built, M.GRIP_PART, "UbGap") == pytest.approx(-0.0120, abs=0.0005)  # grip foot 12 mm under the body bottom (y 0)
    assert shift(built, M.GRIP_PART, "UbSunk") == pytest.approx(+0.0377, abs=0.0005)  # grip foot 37.7 mm inside the body


def test_ac112_v_the_clamp_is_60_mm(built):
    assert shift(built, M.SCOPE_PART, "Far90") == pytest.approx(-0.0600, abs=1e-6)  # a 90 mm gap
    assert shift(built, M.SCOPE_PART, "Far59") == pytest.approx(-0.0590, abs=1e-6)  # a 59 mm gap: inside the clamp


# --- (vi) to (x): which surface counts ----------------------------------------------------------------------------------------


def test_ac112_vi_the_outer_top_decides_not_the_nearest_surface(built):
    # the cavity floor is 1.5 mm under the part (y 0.085 against the foot at 0.0865) and the outer top 13.5 mm over it (0.100)
    assert shift(built, M.SCOPE_PART, "Tube") == pytest.approx(+0.0135, abs=0.0005)


def test_ac112_vii_a_hidden_child_and_a_collision_node_are_not_host_surface(built):
    hidden = built.by_id[M.hid("Tall")]["geometry"]["mounts"]["optic"]
    assert hidden["occupied_by"] == [M.host_id("Tall") + "_Scope"]  # the child whose box reaches 0.12, 20 mm over the body top
    assert shift(built, M.SCOPE_PART, "Tall") == pytest.approx(+0.0200, abs=0.0005)  # foot 0.08: sunk 20 mm into the body (0.100)
    collide = built.by_id[M.hid("Collide")]["geometry"]["mounts"]["optic"]
    assert collide["occupied_by"] == [M.host_id("Collide") + "_Scope"]  # the Collision box (top 0.12) is no child at all
    assert shift(built, M.SCOPE_PART, "Collide") == pytest.approx(+0.0100, abs=0.0005)  # foot 0.09: sunk 10 mm


def test_ac112_viii_the_contact_face_is_the_slab_at_the_extreme_not_the_whole_part(built):
    # the tab bottom is the part's extreme: its foot is 0.107, 7 mm over the body top. The canopy 5.3 cm higher sits over rails that reach 0.16,
    # so a sample taken from it would read s = 0.150 - 0.160 = -0.010 and win the minimum; only the 4 mm slab keeps the tab as the decider.
    assert shift(built, M.TAB_PART, "Wing") == pytest.approx(-0.0070, abs=0.0005)
    assert shift(built, M.SCOPE_PART, "Wing") == pytest.approx(-0.0070, abs=0.0005)


def test_ac112_ix_a_face_with_no_host_under_it_has_no_key(built):
    # G1 3.5 (S8): the Aside seat child (foot 0.06) is shorter than the scope's foot (0.08) and has no flat run under it, so the verdict is no_fit and the
    # pair is not listed any more. The settle pass is run on a listed entry put there by hand: the seat at x 0.10 is beside the body (x +-0.02)
    assert not [e for e in built.by_id[M.pid(M.SCOPE_PART)]["attachment"]["compatible_hosts"] if e["host"] == M.hid("Aside")]

    def list_aside(by):
        att = by[M.pid(M.SCOPE_PART)]["attachment"]["compatible_hosts"]
        att.append({**next(e for e in att if e["host"] == M.hid("Hover")), "host": M.hid("Aside")})

    records, _ = run_post_pass(built, list_aside)
    aside = next(e for e in records[M.pid(M.SCOPE_PART)]["attachment"]["compatible_hosts"] if e["host"] == M.hid("Aside"))
    assert aside["tier"] == "same_pack_fit" and "seat_shift_m" not in aside


def test_ac112_x_the_minimum_is_the_sample_that_touches_first(built):
    # half the face rests on the left block (top 0.100 = the foot), the other half is 20 mm up over the right block (top 0.080)
    assert "seat_shift_m" not in entry(built, M.SCOPE_PART, "Shoulder")


# --- (xi): only the optic and underbarrel slots -------------------------------------------------------------------------------


def test_ac112_xi_a_muzzle_magazine_laser_or_sight_part_never_has_a_key(built):
    assert shift(built, M.SCOPE_PART, "Hover") is not None  # not vacuous: the rule is on in this very directory
    # G1 3.1/3.6/3.7 (S8): the magazine is a pending entry (no well on these hosts) and the silencer a no_fit (box barrels), so neither is listed; the
    # laser and the front sight still are. The settle pass is run with a listed magazine and silencer entry on Misc put there by hand, so all four slots
    # are exercised: the rule would fire on the magazine (15 mm gap) and the silencer if the slot were not excluded
    def list_all(by):
        for part in (M.MAG_PART, M.SILENCER_PART):
            by[M.pid(part)]["attachment"]["compatible_hosts"].append(
                {"host": M.hid("Misc"), "tier": "same_pack_fit", "score": 0.7, "signals": [], "replaces": []})

    records, _ = run_post_pass(built, list_all)
    for part in M.OTHER_PARTS:
        entries = records[M.pid(part)]["attachment"]["compatible_hosts"]
        assert entries, part
        assert not [e for e in entries if "seat_shift_m" in e], part
    assert [e["host"] for e in built.by_id[M.pid(M.MAG_PART)]["attachment"]["compatible_hosts"]] == []
    assert [e["host"] for e in built.by_id[M.pid(M.SILENCER_PART)]["attachment"]["compatible_hosts"]] == []
    # the magazine and the laser really are 15 mm off their seats' neighbours on Misc: the rule would have fired on them
    misc = built.by_id[M.hid("Misc")]["geometry"]["mounts"]
    assert misc["magazine"]["point"] == [0.0, -0.015, 0.1] and misc["laser_light"]["point"] == [0.0, 0.115, -0.1]


# --- (xii): the up of the mount must be a coordinate axis ----------------------------------------------------------------------


def run_post_pass(built, mutate=None):
    records = deepcopy(built.directory["weapons"])
    for r in records:
        for e in (r.get("attachment") or {}).get("compatible_hosts") or []:
            e.pop("seat_shift_m", None)
    if mutate:
        mutate({r["id"]: r for r in records})
    stats = {"computed": 0, "cached": 0, "kept": 0}
    dirmod._apply_contact(records, W.sight_rules(), built.root, {}, stats, {})
    return {r["id"]: r for r in records}, stats


def test_ac112_xii_a_mount_up_30_degrees_off_every_axis_has_no_key(built):
    def tilt(by):
        by[M.hid("Hover")]["geometry"]["mounts"]["optic"]["up"] = [0.0, 0.866, 0.5]  # 30 degrees off +y, 60 off +z

    records, _ = run_post_pass(built, tilt)
    att = records[M.pid(M.SCOPE_PART)]["attachment"]["compatible_hosts"]
    assert "seat_shift_m" not in next(e for e in att if e["host"] == M.hid("Hover"))
    assert next(e for e in att if e["host"] == M.hid("Sunk"))["seat_shift_m"] == pytest.approx(0.008, abs=0.0005)  # the others are untouched


def test_the_axis_alignment_is_one_degree():
    def up(deg):
        return [0.0, float(np.cos(np.radians(deg))), float(np.sin(np.radians(deg)))]

    assert attach.up_axis(up(0.0)) == (1, 1) and attach.up_axis(up(0.9)) == (1, 1)
    assert attach.up_axis(up(1.1)) is None and attach.up_axis(up(30.0)) is None
    assert attach.up_axis([0.0, -1.0, 0.0]) == (1, -1) and attach.up_axis([0.0, 0.0, 1.0]) == (2, 1)
    assert attach.up_axis(None) is None and attach.up_axis([0.0, 0.0, 0.0]) is None


# --- the pair filter (5.4 "Which pairs") ----------------------------------------------------------------------------------------


PARAMS = {"slots": ["optic", "underbarrel"], "slab_m": 0.004, "pitch_m": 0.0025, "dead_m": 0.003, "clamp_m": 0.06, "reach_m": 0.5}  # the spec table, literal
CHILD_SEAT = {"source": "child_node", "point": [0.0, 0.1, 0.0], "up": [0.0, 1.0, 0.0]}
ANCHOR = {"point": [0.0, 0.0, 0.0]}


@pytest.mark.parametrize(("slot", "mount", "tier", "anchor", "want"), [
    ("optic", CHILD_SEAT, "same_pack_fit", ANCHOR, True),
    ("underbarrel", {**CHILD_SEAT, "up": [0.0, -1.0, 0.0]}, "cross_pack_fit", ANCHOR, True),
    ("optic", {**CHILD_SEAT, "source": "probe"}, "same_pack_fit", ANCHOR, True),
    ("magazine", CHILD_SEAT, "same_pack_fit", ANCHOR, False),             # (xi) a slot the table does not name
    ("muzzle", CHILD_SEAT, "same_pack_fit", ANCHOR, False),
    ("optic", None, "same_pack_fit", ANCHOR, False),                      # (a) no mount
    ("optic", {**CHILD_SEAT, "source": "none", "point": None}, "same_pack_fit", ANCHOR, False),
    ("optic", {**CHILD_SEAT, "source": "override"}, "same_pack_fit", ANCHOR, False),   # (b)
    ("optic", CHILD_SEAT, "twin", ANCHOR, False),                         # (c)
    ("optic", CHILD_SEAT, "override", ANCHOR, False),
    ("optic", CHILD_SEAT, "same_pack_fit", None, False),                  # (d)
    ("optic", {**CHILD_SEAT, "up": [0.5, 0.866, 0.0]}, "same_pack_fit", ANCHOR, False),  # (e)
])
def test_which_pairs_are_settled(slot, mount, tier, anchor, want):
    assert attach.settle_applies(slot, mount, tier, anchor, PARAMS) is want


# --- the rule itself, on hand-built numbers ------------------------------------------------------------------------------------


def box_mesh(lo, hi):
    v = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])], dtype=float)
    t = []
    for axis in range(3):  # two triangles for each of the six faces
        a, b = [i for i in range(3) if i != axis]
        for side in (0, 1):
            idx = [i for i, p in enumerate(v) if p[axis] == (lo, hi)[side][axis]]
            c = sorted(idx, key=lambda i: (v[i][a], v[i][b]))  # (lo,lo) (lo,hi) (hi,lo) (hi,hi) over the two other axes
            t += [[c[0], c[1], c[2]], [c[1], c[3], c[2]]]
    return v, np.array(t)


def face_at(y, half=0.01, n=5):
    grid = np.linspace(-half, half, n)
    return np.array([[x, y, z] for x in grid for z in grid])


HOST = box_mesh((-0.05, 0.0, -0.05), (0.05, 0.10, 0.05))  # top face y 0.100


@pytest.mark.parametrize(("y", "d", "want"), [
    (0.111, 0.011, -0.0110), (0.092, -0.008, 0.0080), (0.1029, 0.0029, None), (0.1031, 0.0031, -0.0031),
    (0.159, 0.059, -0.0590), (0.190, 0.090, -0.0600), (0.100, 0.0, None),
])
def test_settle_pair_on_a_box_host(y, d, want):
    got_d, got = attach.settle_pair(face_at(y), *HOST, [0.0, 1.0, 0.0], PARAMS)
    assert got_d == pytest.approx(d, abs=1e-9)
    assert got == want


def test_settle_pair_underbarrel_lies_along_minus_up():
    # the same body seen from below: a face 12 mm under the bottom (y 0) with the mount's up pointing down
    got_d, got = attach.settle_pair(face_at(-0.012), *HOST, [0.0, -1.0, 0.0], PARAMS)
    assert got_d == pytest.approx(0.012, abs=1e-9) and got == -0.0120
    got_d, got = attach.settle_pair(face_at(0.0377), *HOST, [0.0, -1.0, 0.0], PARAMS)
    assert got_d == pytest.approx(-0.0377, abs=1e-9) and got == 0.0377


def test_settle_pair_ignores_a_host_further_than_reach_and_a_face_off_the_mesh():
    assert attach.settle_pair(face_at(0.10 + 0.6), *HOST, [0.0, 1.0, 0.0], PARAMS) == (None, None)  # 0.6 m over: beyond reach_m 0.5
    off = face_at(0.111) + np.array([0.20, 0.0, 0.0])  # beside the box
    assert attach.settle_pair(off, *HOST, [0.0, 1.0, 0.0], PARAMS) == (None, None)


def test_settle_pair_takes_the_slab_at_the_extreme_and_the_minimum_over_it():
    # a flat face at 0.111 with one corner sample dipping 2 mm: the dip is inside the 4 mm slab, so it is the minimum (gap 9 mm)
    face = np.vstack([face_at(0.111), [[0.0, 0.109, 0.0]]])
    d, got = attach.settle_pair(face, *HOST, [0.0, 1.0, 0.0], PARAMS)
    assert d == pytest.approx(0.009, abs=1e-9) and got == -0.0090
    # a sample 6 mm above the extreme is outside the slab and cannot matter even if it sat over a taller host
    face = np.vstack([face_at(0.111), [[0.0, 0.117, 0.0]]])
    assert attach.settle_pair(face, *HOST, [0.0, 1.0, 0.0], PARAMS)[0] == pytest.approx(0.011, abs=1e-9)
