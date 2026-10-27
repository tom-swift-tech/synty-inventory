"""G1 S6: the magazine well reference and entry section (docs/weapon_attach_geometry.md 3.7 steps 1 and 2, 3.11; AC136 fixture, the drum case).

Meshes are the synthetic ones of ``fixtures/weapons/g1_well_meshes.py`` (a receiver block and magazines; see its docstring for the numbers).
``RULES`` is the ``fit_geometry`` block of spec 4.1 as a literal, and every expected number below is its own literal worked out by hand from the
fixture (the plane is ``0.000 - 0.002 = -0.002``; 0.06 x 0.024 is the straight magazine's section), never read from the rules file or from a
constant under test. ``fit_geometry.verdict`` (step 3, S2) is imported only by the tests: ``fit_well`` itself may not import it.

Deliberate breaks each test must fail on (run in a scratch copy, reported with the slice):

* the tapered magazine (AC136): the section cut at the magazine's own top instead of ``u_rb - 0.002``. The identical / 12 % / 40 % rows do NOT
  catch this (an identical magazine reads 0.000 at any plane), which is why the slice demands the tapered row;
* ``crossings`` through a face centre: the 1e-5 offset removed (containment left closed), so the face diagonal counts twice;
* the entry depth read from the rules: ``entry_depth_m`` hard-coded;
* the drum: an empty section returned as ``(0.0, 0.0)`` instead of ``None``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

_FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("g1_well_meshes", _FIX / "g1_well_meshes.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)

from synty_inventory.weapons import fit_geometry, fit_well  # noqa: E402
from synty_inventory.weapons.fit_types import Verdict, WellRef  # noqa: E402

# the attachment_rules.fit_geometry block of spec 4.1, as a literal
RULES = {
    "slots": ["optic", "muzzle", "underbarrel", "magazine"],
    "locator": {"grid_m": 0.0005, "sample_n": 24, "hit_min": 1.0, "merge_m": 0.002},
    "rail": {
        "window_m": 0.010,
        "bin_m": 0.0005,
        "tooth_amp_min_m": 0.0008,
        "tooth_merge_m": 0.0025,
        "pitch_min_m": 0.005,
        "pitch_max_m": 0.040,
        "pitch_cv_max": 0.25,
        "tooth_min_count": 4,
        "tooth_h_tol_m": 0.0015,
        "zone": [0.15, 0.85],
        "default_seat_len_m": 0.20,
        "sight_clear_m": 0.010,
    },
    "flat": {"band_m": 0.005, "close_m": 0.015, "min_m": 0.060},
    "clamp": {"overhang_max_m": 0.010, "ratio_min": 1.0},
    "depth": {"lo_m": -0.026, "hi_m": 0.003},
    "bore": {
        "end_slab_m": 0.010,
        "round_min": 0.8,
        "circ_min": 0.75,
        "barrel_od_max_m": 0.060,
        "od_ratio": [0.85, 2.00],
        "inner_ratio": [0.47, 1.21],
        "axis_offset_max_m": 0.005,
        "axis_tilt_max_deg": 2,
    },
    "well": {"entry_depth_m": 0.002, "tol": 0.15},
    "exceptions": [],
}

ABS = 1e-4  # stored measures are rounded to 1e-4 m


def _host():
    return M.receiver()


def _ref(mag):
    h = _host()
    return fit_well.well_reference(h[0], h[1], mag[0], mag[1], RULES)


def _verdict(ref: WellRef | None, section) -> Verdict:
    feats = {} if ref is None else {"well_ref": {"length_m": ref.length_m, "width_m": ref.width_m}}
    part = {"anchor_measured": True, "entry_section": section}
    return fit_geometry.verdict("magazine", feats, part, None, RULES)


# ---------------------------------------------------------------------------------------------------------------- crossings


def test_crossings_face_centre_diagonal_counts_once():
    # the receiver is a closed block; its top and bottom faces are two triangles whose diagonal runs through (0, 0): two crossings, not four
    v, t = _host()
    got = fit_well.crossings(v, t, 0.0, 0.0)
    assert len(got) == 2
    assert got == pytest.approx([0.0, 0.05], abs=1e-9)
    assert got == sorted(got)


@pytest.mark.parametrize("f, s", [(0.08, 0.0), (0.0, 0.03), (0.08, 0.03), (-0.08, -0.03), (0.04, 0.015)])
def test_crossings_on_an_edge_or_vertex_is_even_and_never_odd(f, s):
    # a probe on the boundary (side edge, top edge, corner, the face diagonal off-centre) may fall just in or just out, but a closed block is
    # crossed an even number of times: never one (a half-counted edge)
    v, t = _host()
    got = fit_well.crossings(v, t, f, s)
    assert len(got) in (0, 2)


def test_crossings_miss_is_empty():
    v, t = _host()
    assert fit_well.crossings(v, t, 0.2, 0.0) == []
    assert fit_well.crossings(v, t, 0.0, -0.2) == []
    assert fit_well.crossings(np.zeros((0, 3)), np.zeros((0, 3), dtype=int), 0.0, 0.0) == []


def test_crossings_stacked_blocks_sorted_whatever_the_triangle_order():
    # three disjoint blocks stacked along u: every crossing listed, ascending, from a shuffled mesh
    a = M.box(-0.01, 0.01, -0.01, 0.01, 0.00, 0.01)
    b = M.box(-0.01, 0.01, -0.01, 0.01, 0.02, 0.03)
    c = M.box(-0.01, 0.01, -0.01, 0.01, 0.05, 0.06)
    for seed in (1, 2, 3):
        v, t = M.shuffled(M.merged(c, a, b), seed)
        got = fit_well.crossings(v, t, 0.0, 0.0)
        assert got == pytest.approx([0.00, 0.01, 0.02, 0.03, 0.05, 0.06], abs=1e-9)


def test_crossings_interpolates_a_sloped_face():
    # a single triangle rising 0.02 over 0.04 in f: at f = 0.01 the height is 0.005
    v = np.array([[0.0, -0.05, 0.0], [0.04, -0.05, 0.02], [0.0, 0.05, 0.0]])
    t = np.array([[0, 1, 2]])
    got = fit_well.crossings(v, t, 0.01, 0.0)
    assert len(got) == 1
    assert got[0] == pytest.approx(0.005, abs=1e-3)  # the 1e-5 probe offset moves u by well under 1e-3


# ------------------------------------------------------------------------------------------- AC136: identical, 12 %, 40 %


def test_ref_of_a_straight_magazine():
    ref = _ref(M.mag_straight())
    assert isinstance(ref, WellRef)
    assert ref.u_rb == pytest.approx(0.0, abs=ABS)
    assert ref.length_m == pytest.approx(0.060, abs=ABS)
    assert ref.width_m == pytest.approx(0.024, abs=ABS)
    assert ref.source == "child"


def test_identical_magazine_reads_zero_and_fits():
    mag = M.mag_straight()
    ref = _ref(mag)
    sec = fit_well.entry_section(mag[0], mag[1], -0.002)  # u_rb 0.000 - 0.002
    assert sec is not None
    off_l = abs(sec[0] - ref.length_m) / ref.length_m
    off_w = abs(sec[1] - ref.width_m) / ref.width_m
    assert off_l == pytest.approx(0.0, abs=1e-9) and off_w == pytest.approx(0.0, abs=1e-9)
    assert _verdict(ref, sec) == Verdict("fit", ("well_entry",))


@pytest.mark.parametrize("k_f, k_s", [(1.12, 1.12), (1.12, 1.0), (1.0, 1.12)])
def test_twelve_percent_wider_fits(k_f, k_s):
    ref = _ref(M.mag_straight())
    cand = M.scaled_fs(M.mag_straight(), k_f, k_s)
    sec = fit_well.entry_section(cand[0], cand[1], -0.002)
    assert sec == pytest.approx((0.060 * k_f, 0.024 * k_s), abs=ABS)
    assert _verdict(ref, sec) == Verdict("fit", ("well_entry",))


@pytest.mark.parametrize("k_f, k_s", [(1.40, 1.40), (1.40, 1.0), (1.0, 1.40)])
def test_forty_percent_wider_does_not_fit(k_f, k_s):
    ref = _ref(M.mag_straight())
    cand = M.scaled_fs(M.mag_straight(), k_f, k_s)
    sec = fit_well.entry_section(cand[0], cand[1], -0.002)
    assert sec == pytest.approx((0.060 * k_f, 0.024 * k_s), abs=ABS)
    assert _verdict(ref, sec) == Verdict("no_fit", ("well_entry",))


# ---------------------------------------------------------------------------------------- AC136 break: a tapered magazine


def test_tapered_reference_is_cut_at_the_plane_not_at_its_top():
    tap = M.mag_tapered()
    ref = _ref(tap)
    # u_rb 0.000; the plane -0.002 is 20 % up the neck: half-widths 0.028 and 0.0112
    assert ref.u_rb == pytest.approx(0.0, abs=ABS)
    assert ref.length_m == pytest.approx(0.056, abs=ABS)
    assert ref.width_m == pytest.approx(0.0224, abs=ABS)
    # the magazine's own top is a clearly different section: this is what the break would read
    top = fit_well.entry_section(tap[0], tap[1], 0.01)
    assert top == pytest.approx((0.040, 0.016), abs=ABS)
    assert abs(top[1] - ref.width_m) / ref.width_m > 0.25

    # a straight candidate 0.060 x 0.024 is 7.1 % off the true reference (fit) but 50 % off a reference cut at the top (no_fit)
    cand = M.mag_straight()
    sec = fit_well.entry_section(cand[0], cand[1], ref.u_rb - 0.002)
    assert sec == pytest.approx((0.060, 0.024), abs=ABS)
    assert _verdict(ref, sec) == Verdict("fit", ("well_entry",))
    wrong = WellRef(u_rb=ref.u_rb, length_m=top[0], width_m=top[1], source="child")
    assert _verdict(wrong, sec) == Verdict("no_fit", ("well_entry",))


def test_entry_depth_is_read_from_the_rules():
    # a 0.010 depth puts the plane at -0.010, below the neck: the tapered magazine reads its full body, 0.060 x 0.024
    rules = {"well": {"entry_depth_m": 0.010, "tol": 0.15}}
    h, tap = _host(), M.mag_tapered()
    ref = fit_well.well_reference(h[0], h[1], tap[0], tap[1], rules)
    assert ref.u_rb == pytest.approx(0.0, abs=ABS)
    assert (ref.length_m, ref.width_m) == pytest.approx((0.060, 0.024), abs=ABS)


# ----------------------------------------------------------------------------------------------------- the receiver bottom


def test_receiver_bottom_is_the_lowest_host_crossing():
    # a second plate inside the receiver, above the line: the lowest crossing still decides u_rb
    plate = M.box(-0.02, 0.02, -0.02, 0.02, 0.012, 0.02)
    host = M.merged(_host(), plate)
    mag = M.mag_straight(top=0.011)
    ref = fit_well.well_reference(host[0], host[1], mag[0], mag[1], RULES)
    assert ref.u_rb == pytest.approx(0.0, abs=ABS)
    assert (ref.length_m, ref.width_m) == pytest.approx((0.060, 0.024), abs=ABS)


def test_receiver_bottom_follows_a_raised_receiver():
    host = M.shifted(_host(), du=0.03)  # bottom at 0.03
    mag = M.shifted(M.mag_tapered(), du=0.03)  # the same neck geometry relative to the bottom
    ref = fit_well.well_reference(host[0], host[1], mag[0], mag[1], RULES)
    assert ref.u_rb == pytest.approx(0.03, abs=ABS)
    assert (ref.length_m, ref.width_m) == pytest.approx((0.056, 0.0224), abs=ABS)


def test_no_host_crossing_gives_no_reference():
    h = M.shifted(_host(), df=0.5)  # the receiver is nowhere near the magazine line
    mag = M.mag_straight()
    assert fit_well.well_reference(h[0], h[1], mag[0], mag[1], RULES) is None
    empty = (np.zeros((0, 3)), np.zeros((0, 3), dtype=int))
    assert fit_well.well_reference(empty[0], empty[1], mag[0], mag[1], RULES) is None
    host = _host()
    assert fit_well.well_reference(host[0], host[1], empty[0], empty[1], RULES) is None


# ------------------------------------------------------------------------------------------------------------------- drum


def test_a_magazine_that_does_not_reach_the_plane_has_no_section_and_is_a_drum():
    drum = M.mag_drum()  # top at -0.03, the plane at -0.002
    assert fit_well.entry_section(drum[0], drum[1], -0.002) is None
    ref = _ref(M.mag_straight())
    # the candidate side as the S7 caller drives it: cut at the reference plane, and the verdict reads None as a drum
    sec = fit_well.entry_section(drum[0], drum[1], ref.u_rb - 0.002)
    assert sec is None
    assert _verdict(ref, sec) == Verdict("unverified", ("drum",))


def test_a_drum_reference_gives_no_well_reference_and_the_pair_is_not_judged():
    ref = _ref(M.mag_drum())
    assert ref is None
    assert _verdict(ref, (0.06, 0.024)) == Verdict("not_judged", ())


def test_plane_above_the_magazine_and_plane_below_it_are_empty():
    mag = M.mag_straight()  # u in [-0.12, 0.01]
    assert fit_well.entry_section(mag[0], mag[1], 0.011) is None
    assert fit_well.entry_section(mag[0], mag[1], -0.121) is None
    assert fit_well.entry_section(mag[0], mag[1], 0.0) == pytest.approx((0.060, 0.024), abs=ABS)


def test_plane_through_vertices_is_neither_lost_nor_doubled():
    # planes at exactly a ring height (-0.12, -0.005, 0.01) hit vertices; the section is still the ring's own
    tap = M.mag_tapered()
    assert fit_well.entry_section(tap[0], tap[1], -0.005) == pytest.approx((0.060, 0.024), abs=ABS)
    assert fit_well.entry_section(tap[0], tap[1], 0.01) == pytest.approx((0.040, 0.016), abs=ABS)
    # the convention is u >= plane counts as above, so a plane at the very bottom ring has the whole mesh above it: no section
    assert fit_well.entry_section(tap[0], tap[1], -0.12) is None


# ------------------------------------------------------------------------------------------------------------- determinism


def test_result_does_not_depend_on_vertex_or_triangle_order():
    expected = WellRef(u_rb=0.0, length_m=0.056, width_m=0.0224, source="child")
    assert _ref(M.mag_tapered()) == expected
    for seed in (1, 2, 3):
        h, m = M.shuffled(_host(), seed), M.shuffled(M.mag_tapered(), seed + 10)
        assert fit_well.well_reference(h[0], h[1], m[0], m[1], RULES) == expected
