"""W8h-B: the sight seat probe (AC92; docs/weapon_attachments.md 4.6) and its numeric gates (4.6 item 6).

Fixture hosts are in ``fixtures/weapons/w8h_world.py`` (box rifle, slide pistol, prism). The expected seats are literals worked
out by hand from the box dimensions; the gate checker below is the test-level twin of the live checker and is shown to fail
on perturbed records (one per gate).
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import numpy as np
import pytest

_spec = importlib.util.spec_from_file_location("w8h_world", Path(__file__).parent / "fixtures" / "weapons" / "w8h_world.py")
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)
A = W.A

from synty_inventory.sources.glb_geometry import load_triangles  # noqa: E402
from synty_inventory.weapons.mount_probe import sight_seats  # noqa: E402
from synty_inventory.weapons.rules import load_rules  # noqa: E402

PACK = "FAKE_SightProbe"
BOX, KIDDED, SLIDE, PRISM = "SM_Wep_Rifle_Box_01", "SM_Wep_Rifle_BoxKid_01", "SM_Wep_Pistol_Slide_01", "SM_Wep_Rifle_Prism_01"
SCOPE_AT = (0.0, 0.10, -0.05)  # an optic child over the receiver (foot centre z 0.0, its mesh spans z -0.1..0.1 about the foot)


def hosts():
    return {
        BOX: W.host_node(BOX, W.box_rifle()),
        KIDDED: W.host_node(KIDDED, W.box_rifle(), [W.kid(KIDDED, "Scope", A.optic(), SCOPE_AT)]),
        SLIDE: W.host_node(SLIDE, W.slide_pistol()),
        PRISM: W.host_node(PRISM, W.prism()),
    }


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    directory, _, _, root = W.build(tmp_path_factory.mktemp("w8h_probe"), {PACK: {"hosts": hosts()}})
    return W.by_id(directory), root


def mounts(built, name):
    return built[0][f"{PACK}/{name}"]["geometry"]["mounts"]


def test_ac92_i_box_rifle_rear_seat_is_the_receiver_rear_end_plus_10_mm_on_the_receiver_top(built):
    rear = mounts(built, BOX)["sight_rear"]
    assert rear["source"] == "probe" and rear["confidence"] == 0.5 and rear["span_m"] is None
    assert abs(rear["point"][2] - (-0.2525 + 0.010)) <= 0.003  # along forward
    assert abs(rear["point"][1] - 0.10) <= 0.001  # receiver top


def test_ac92_i_box_rifle_front_seat_is_the_handguard_front_end_minus_8_mm_on_the_handguard_top(built):
    front = mounts(built, BOX)["sight_front"]
    assert front["source"] == "probe"
    assert abs(front["point"][2] - (0.4012 - 0.008)) <= 0.003
    assert abs(front["point"][1] - 0.075) <= 0.001  # the handguard is 25 mm lower than the receiver, not the barrel


def test_ac92_ii_a_baked_scope_child_on_the_receiver_keeps_the_optic_and_since_w8j_refuses_both_sight_seats(built):
    # A3 addendum 3 (W8j, item 8 A): the Scope child is a BODY child (a separate optic node), so the optic keeps its child_node seat and
    # both sight slots, which the probe would have seated where the bare box rifle's are, are slot_disabled. (Until W8i the seats were
    # equal to the bare host's; that "the baked child is out of the probe mesh" property is still pinned by the laser and underbarrel
    # cases of w8i_probe and by w8j_baked.)
    kidded = mounts(built, KIDDED)
    assert kidded["optic"]["source"] == "child_node"
    for slot in ("sight_rear", "sight_front"):
        assert (kidded[slot]["source"], kidded[slot]["reason"]) == ("none", "slot_disabled"), slot
        assert kidded[slot]["point"] is None and kidded[slot]["occupied_by"] == []


def test_ac92_iii_a_slide_only_pistol_gets_both_seats_or_none_and_never_the_front_behind_the_rear(built):
    m = mounts(built, SLIDE)
    rear, front = m["sight_rear"], m["sight_front"]
    assert rear["source"] == front["source"]
    if rear["source"] == "probe":
        assert front["point"][2] - rear["point"][2] >= 0.060


def test_ac92_iv_a_host_whose_top_run_is_under_three_bins_gets_neither_seat(built):
    m = mounts(built, PRISM)
    assert m["sight_rear"]["source"] == m["sight_front"]["source"] == "none"
    assert m["sight_rear"]["reason"] == m["sight_front"]["reason"] == "probe_unavailable"


def test_ac92_the_pure_probe_refuses_the_prism_and_seats_the_box():
    params = load_rules()["attachment_rules"]["sight_probe"]
    axes = {"forward": "+z", "up": "+y"}
    v, t = W.prism()
    assert sight_seats(v, t, axes, params) is None
    v, t = W.box_rifle()
    seats = sight_seats(v, t, axes, params)
    assert seats is not None and abs(seats["sight_rear"][1] - 0.10) <= 0.001 and seats["sight_front"][2] > seats["sight_rear"][2] + 0.060


def test_ac92_the_two_refusals_of_step_5_are_each_honoured_on_a_host_the_probe_would_otherwise_seat():
    # the box rifle's receiver run is 60 bins (0.30 m / 5 mm) and its seats are 0.63 m apart: raise each bound past those
    axes = {"forward": "+z", "up": "+y"}
    v, t = W.box_rifle()
    base = dict(load_rules()["attachment_rules"]["sight_probe"])
    assert sight_seats(v, t, axes, base) is not None
    assert sight_seats(v, t, axes, {**base, "min_receiver_bins": 80}) is None  # fewer bins than the run needs
    assert sight_seats(v, t, axes, {**base, "min_separation_m": 0.9}) is None  # front seat not far enough ahead of the rear


# -- the numeric gates of 4.6 item 6, as a checker over a built directory -------------------------------------------


def _ray_top(v, t, origin, up_i):
    """Highest surface hit of a ray from ``origin`` straight down (-up_i), or None."""
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    d = np.zeros(3)
    d[up_i] = -1.0
    e1, e2 = b - a, c - a
    p = np.cross(d, e2)
    det = np.einsum("ij,ij->i", e1, p)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    tv = origin - a
    u = np.einsum("ij,ij->i", tv, p) * inv
    q = np.cross(tv, e1)
    w = (q @ d) * inv
    s = np.einsum("ij,ij->i", e2, q) * inv
    hit = ok & (u >= -1e-9) & (w >= -1e-9) & (u + w <= 1 + 1e-9) & (s > 0)
    return float((origin + s[hit][:, None] * d)[:, up_i].max()) if hit.any() else None


def gate_violations(rec, root, optic_entries=()):
    """Gates (a), (b), (c) for one host record whose probe set both seats (the fixture hosts are +z forward, +y up)."""
    m = rec["geometry"]["mounts"]
    rear, front = m["sight_rear"], m["sight_front"]
    out = []
    drop = {n for s in ("optic", "sight_front", "sight_rear") for n in m[s]["occupied_by"]}
    v, t = load_triangles(root / "glb" / rec["pack"] / f"{rec['asset_id']}.glb", None, exclude=lambda n: n in drop, scale=1.0)
    v, t = np.asarray(v, float), np.asarray(t)
    for name, seat in (("sight_rear", rear), ("sight_front", front)):
        p = np.array(seat["point"], float)
        heights = []
        for df in (-0.003, 0.0, 0.003):
            o = p.copy()
            o[2] += df
            o[1] += 1.0
            h = _ray_top(v, t, o, 1)
            if h is not None:
                heights.append(h)
        if not heights or abs(float(np.median(heights)) - p[1]) > 0.003:
            out.append(("a", name))
    if front["point"][2] - rear["point"][2] < 0.060:
        out.append(("b", None))
    opt = m["optic"]
    if opt["source"] != "none" and opt.get("span_m") and opt.get("point"):
        half = opt["span_m"] / 2
        for name, seat in (("sight_front", front), ("sight_rear", rear)):
            if abs(seat["point"][2] - opt["point"][2]) <= half:
                covered = name == "sight_rear" and optic_entries and all(e.get("hides_slots") == ["sight_rear"] for e in optic_entries)
                if not covered:
                    out.append(("c", name))
    return out


def test_ac92_gates_pass_on_every_fixture_host_where_the_probe_seated_both(built):
    seated = [r for r in built[0].values() if r["geometry"]["mounts"]["sight_rear"]["source"] == "probe"
              and r["geometry"]["mounts"]["sight_front"]["source"] == "probe"]
    assert {r["asset_id"] for r in seated} == {BOX, SLIDE}  # W8j: the scope-kidded box is a body-child host, its seats are refused
    for rec in seated:
        assert gate_violations(rec, built[1]) == [], rec["id"]


def test_ac92_gate_a_fails_when_a_seat_floats_above_the_top_surface(built):
    rec = copy.deepcopy(built[0][f"{PACK}/{BOX}"])
    rec["geometry"]["mounts"]["sight_rear"]["point"][1] += 0.005
    assert gate_violations(rec, built[1]) == [("a", "sight_rear")]


def test_ac92_gate_b_fails_when_the_front_seat_is_not_60_mm_ahead(built):
    rec = copy.deepcopy(built[0][f"{PACK}/{BOX}"])
    rec["geometry"]["mounts"]["sight_front"]["point"][2] = rec["geometry"]["mounts"]["sight_rear"]["point"][2] + 0.040
    assert ("b", None) in gate_violations(rec, built[1])


def test_ac92_gate_c_fails_when_a_seat_is_inside_the_optic_span_unless_hides_slots_covers_the_rear(built):
    rec = copy.deepcopy(built[0][f"{PACK}/{BOX}"])  # a seated host (W8j: the scope-kidded box is refused) given the scope child's optic mount
    opt = rec["geometry"]["mounts"]["optic"] = copy.deepcopy(mounts(built, KIDDED)["optic"])
    assert opt["span_m"]
    opt["point"][2] = rec["geometry"]["mounts"]["sight_rear"]["point"][2]  # as if the scope sat over the rear seat
    assert gate_violations(rec, built[1]) == [("c", "sight_rear")]
    assert gate_violations(rec, built[1], [{"hides_slots": ["sight_rear"]}]) == []  # covered by hides_slots
    opt["point"][2] = rec["geometry"]["mounts"]["sight_front"]["point"][2]
    assert gate_violations(rec, built[1], [{"hides_slots": ["sight_rear"]}]) == [("c", "sight_front")]  # the front is never covered
