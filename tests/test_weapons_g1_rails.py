"""G1 S4: the rail detector (docs/weapon_attach_geometry.md 3.4; AC134 fixture, AC148 detector part).

Synthetic hosts only (``tests/fixtures/weapons/g1_rail_meshes.py``). Every bound below is a literal of this file: the rules dict is a copy of
the spec 4.1 values, never read from ``weapon_rules.yaml`` or the module (AC137). Deliberate breaks, run on a scratch copy by editing the
RULES literal: ``tooth_min_count`` 6 turns ``test_a_five_tooth_rail_is_found`` red; ``pitch_max_m`` 0.016 turns
``test_a_six_tooth_rail_at_23_5_mm_pitch_is_found_with_its_measures`` and ``test_pitch_window_edges`` red.
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import numpy as np
import pytest

_FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("g1_rail_meshes", _FIX / "g1_rail_meshes.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)

from synty_inventory.weapons.fit_rails import clip_run, flat_seat, rail_runs, seat_point  # noqa: E402
from synty_inventory.weapons.fit_types import RailRun  # noqa: E402

RULES = {
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
}


def rules_with(**rail):
    r = copy.deepcopy(RULES)
    r["rail"].update(rail)
    return r


def runs(mesh, side="top", s0=0.0, rules=RULES):
    return rail_runs(mesh[0], mesh[1], side, s0, rules)


def flat(mesh, s0=0.0, rules=RULES):
    return flat_seat(mesh[0], mesh[1], s0, rules)


# ---------------------------------------------------------------- AC134: the toothed rail


def test_a_six_tooth_rail_at_23_5_mm_pitch_is_found_with_its_measures():
    found = runs(M.toothed_host(n=6, pitch=0.0235, start_f=0.12, amp=0.004, rail_w=0.017))
    assert len(found) == 1
    r = found[0]
    assert r.toothed is True
    assert r.teeth == 6
    assert r.pitch_m == pytest.approx(0.0235, abs=0.0005)  # one bin
    assert r.amp_m == pytest.approx(0.004, abs=0.0001)
    assert r.width_m == pytest.approx(0.017, abs=0.0002)
    assert r.top_u == pytest.approx(0.005, abs=0.0001)  # floor 1 mm over the body top, crest 4 mm over the floor
    assert r.f0 == pytest.approx(0.12, abs=0.0006)  # whole pitch cells: the rail covers 0.12 .. 0.261
    assert r.f1 == pytest.approx(0.261, abs=0.0006)


def test_the_bottom_rail_is_the_mirror_of_the_top_rail():
    top = runs(M.toothed_host())[0]
    flipped = M.mirror_u(M.toothed_host())
    bottom = runs(flipped, side="bottom")
    assert len(bottom) == 1
    b = bottom[0]
    assert (b.f0, b.f1, b.pitch_m, b.amp_m, b.teeth, b.width_m, b.toothed) == (top.f0, top.f1, top.pitch_m, top.amp_m, top.teeth, top.width_m, True)
    assert b.top_u == pytest.approx(-0.005, abs=0.0001)  # the lowest u of the teeth, a signed host coordinate
    # and the sides do not mix: the upside-down host has no toothed top, the upright host no toothed bottom
    assert runs(flipped, side="top") == []
    assert runs(M.toothed_host(), side="bottom") == []


@pytest.mark.parametrize(
    "start_f, found",
    [
        (0.005, False),  # 0.005 .. 0.146: wholly behind the zone [0.15, 0.85] of a 1 m host
        (0.050, True),  # 0.050 .. 0.191 straddles the rear edge
        (0.300, True),
        (0.800, True),  # 0.800 .. 0.941 straddles the front edge
        (0.860, False),  # wholly in front of the zone
    ],
)
def test_a_run_outside_the_zone_is_not_found(start_f, found):
    # the 1 m body fixes the f extent at 0 .. 1 m whichever way the 141 mm rail sits
    mesh = M.toothed_host(n=6, start_f=start_f, length=1.0)
    assert bool(runs(mesh)) is found


def test_the_zone_is_a_fraction_of_the_f_extent_of_the_arrays_given():
    # the same rail, f 0.10 .. 0.241: it overlaps the zone [0.15, 0.85] of a 1 m host, but not the zone [0.30, 1.70] of a 2 m host
    assert runs(M.toothed_host(n=6, start_f=0.10, length=1.0)) != []
    assert runs(M.toothed_host(n=6, start_f=0.10, length=2.0)) == []


def test_uneven_tooth_tops_beyond_1_5_mm_break_the_run():
    base = [0.004] * 6
    # one middle tooth 3 mm proud: 3 mm beyond the median top, and either side of it holds fewer than 4 teeth
    proud = list(base)
    proud[2] = 0.007
    assert runs(M.toothed_host(amps=proud)) == []
    # 1.6 mm proud breaks it, 1.4 mm proud does not (the edge is 1.5 mm from the median top)
    for lift, expect in ((0.0016, False), (0.0014, True)):
        amps = list(base)
        amps[2] = 0.004 + lift
        assert bool(runs(M.toothed_host(amps=amps))) is expect, lift


def test_a_proud_end_tooth_leaves_the_five_teeth_that_agree():
    amps = [0.007, 0.004, 0.004, 0.004, 0.004, 0.004]
    found = runs(M.toothed_host(amps=amps))
    assert len(found) == 1 and found[0].teeth == 5
    assert found[0].f0 == pytest.approx(0.12 + 0.0235, abs=0.0006)


def test_a_five_tooth_rail_is_found():
    found = runs(M.toothed_host(n=5))
    assert len(found) == 1 and found[0].teeth == 5
    # Break (AC134): tooth_min_count 6 drops it
    assert runs(M.toothed_host(n=5), rules=rules_with(tooth_min_count=6)) == []
    # and a 6-tooth rail survives that same break
    assert len(runs(M.toothed_host(n=6), rules=rules_with(tooth_min_count=6))) == 1


def test_the_tooth_count_edges():
    assert len(runs(M.toothed_host(n=4))) == 1
    assert runs(M.toothed_host(n=3)) == []


def test_pitch_window_edges():
    assert len(runs(M.toothed_host(pitch=0.0235))) == 1
    # Break (AC134): pitch_max_m 0.016 drops the 23.5 mm rail
    assert runs(M.toothed_host(pitch=0.0235), rules=rules_with(pitch_max_m=0.016)) == []
    # the literal window [0.005, 0.040]: 39 mm in, 42 mm out; 6 mm in, 4.5 mm out
    assert len(runs(M.toothed_host(pitch=0.039, crest_w=0.010, start_f=0.12))) == 1
    assert runs(M.toothed_host(pitch=0.042, crest_w=0.010, start_f=0.12)) == []
    assert len(runs(M.toothed_host(pitch=0.006, crest_w=0.003, rail_w=0.017, start_f=0.3, n=8))) == 1
    assert runs(M.toothed_host(pitch=0.0045, crest_w=0.002, start_f=0.3, n=8)) == []


def test_the_pitch_cv_limit():
    even = M.toothed_host_at(list(np.cumsum([0.12, 0.020, 0.026, 0.020, 0.026, 0.020])))  # CV 0.13
    found = runs(even)
    assert len(found) == 1 and found[0].teeth == 6
    uneven = M.toothed_host_at(list(np.cumsum([0.12, 0.015, 0.030, 0.015, 0.030, 0.015])))  # CV 0.36; every 4-tooth stretch is 0.33
    assert runs(uneven) == []


def test_the_tooth_amplitude_floor():
    assert len(runs(M.toothed_host(amp=0.0010))) == 1
    assert runs(M.toothed_host(amp=0.0006)) == []
    assert runs(M.toothed_host(amp=0.0010))[0].amp_m == pytest.approx(0.0010, abs=0.0001)


def test_two_rails_on_one_host_are_both_listed_rear_to_front():
    body = M.box(0.0, 1.0, -0.02, 0.02, -0.05, 0.0)
    rear = M.prism(M.tooth_profile(0.20, 4, 0.0235, 0.010, 0.001, 0.004), -0.0085, 0.0085, 0.0)
    front = M.prism(M.tooth_profile(0.50, 6, 0.0300, 0.012, 0.001, 0.005), -0.0085, 0.0085, 0.0)
    found = runs(M.concat(body, front, rear))  # given front first: the order of the result does not follow the input
    assert [r.teeth for r in found] == [4, 6]
    assert found[0].f1 < found[1].f0
    assert found[1].pitch_m == pytest.approx(0.030, abs=0.0005)
    assert found[1].amp_m == pytest.approx(0.005, abs=0.0001)


def test_the_centreline_window_is_10_mm_either_side_of_s0():
    mesh = M.toothed_host(s_centre=0.030)
    assert runs(mesh, s0=0.0) == []  # the rail top (s 0.0215 .. 0.0385) lies outside the window around s 0
    found = runs(mesh, s0=0.030)
    assert len(found) == 1 and found[0].teeth == 6
    assert found[0].width_m == pytest.approx(0.017, abs=0.0002)
    # an off-centre rail is still seen by the window around a centreline 8 mm away from its middle
    assert len(runs(M.toothed_host(s_centre=0.008), s0=0.0)) == 1


def test_vertex_and_triangle_order_do_not_change_the_result():
    v, t = M.toothed_host()
    rng = np.random.default_rng(7)
    perm = rng.permutation(len(v))
    inv = np.empty_like(perm)
    inv[perm] = np.arange(len(v))
    shuffled = (v[perm], inv[t][rng.permutation(len(t))])
    assert runs(shuffled) == runs((v, t))
    assert flat(shuffled) == flat((v, t))


def test_the_inputs_are_not_modified():
    v, t = M.toothed_host()
    v0, t0 = v.copy(), t.copy()
    runs((v, t), side="bottom")
    flat((v, t))
    assert np.array_equal(v, v0) and np.array_equal(t, t0)


def test_an_empty_host_and_a_bad_side():
    empty = (np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64))
    assert runs(empty) == [] and flat(empty) is None
    with pytest.raises(ValueError):
        runs(M.toothed_host(), side="left")


def test_measures_are_rounded_to_a_tenth_of_a_millimetre():
    r = runs(M.toothed_host())[0]
    for x in (r.f0, r.f1, r.top_u, r.pitch_m, r.amp_m, r.width_m):
        assert x == round(x, 4)


# ---------------------------------------------------------------- AC148: the flat seat


def test_a_smooth_80_mm_top_gives_a_flat_seat_that_is_not_toothed():
    mesh = M.staircase_host(f_plateau=0.42, plateau_len=0.080)
    assert runs(mesh) == []  # nothing toothed on it
    seat = flat(mesh)
    assert seat is not None
    assert seat.toothed is False
    assert (seat.teeth, seat.pitch_m, seat.amp_m) == (0, 0.0, 0.0)
    assert seat.f0 == pytest.approx(0.42, abs=0.0006)
    assert seat.f1 == pytest.approx(0.50, abs=0.0006)
    assert seat.top_u == pytest.approx(0.0, abs=0.0001)
    assert seat.width_m == pytest.approx(0.040, abs=0.0002)


def test_a_toothed_host_gives_no_flat_seat():
    mesh = M.toothed_host()
    assert len(runs(mesh)) == 1
    assert flat(mesh) is None
    # the same body without the rail is flat along its whole zone, so the fallback does exist there
    body = M.box(0.0, 1.0, -0.02, 0.02, -0.05, 0.0)
    assert flat(body) is not None


def test_the_flat_run_is_at_least_60_mm_long_inside_the_zone():
    assert flat(M.staircase_host(plateau_len=0.050)) is None
    assert flat(M.staircase_host(plateau_len=0.070)) is not None
    # a plateau over the rear edge of the zone [0.15, 0.85]: only the part inside counts, and the run is cut at the edge
    assert flat(M.staircase_host(f_plateau=0.10, plateau_len=0.080)) is None  # 30 mm inside
    seat = flat(M.staircase_host(f_plateau=0.10, plateau_len=0.140))  # 90 mm inside
    assert seat is not None
    assert seat.f0 == pytest.approx(0.15, abs=0.0006)
    assert seat.f1 == pytest.approx(0.24, abs=0.0006)
    # wholly behind the zone
    assert flat(M.staircase_host(f_plateau=0.01, plateau_len=0.120)) is None


def test_a_gap_of_15_mm_is_bridged_and_a_wider_one_is_not():
    bridged = flat(M.staircase_host(f_plateau=0.42, plateau_len=0.160, notch=0.012))
    assert bridged is not None and bridged.f1 - bridged.f0 == pytest.approx(0.160, abs=0.0006)
    split = flat(M.staircase_host(f_plateau=0.42, plateau_len=0.160, notch=0.020))
    assert split is not None and split.f1 - split.f0 == pytest.approx(0.070, abs=0.0006)  # one 70 mm half, not 160
    # and a split whose halves are shorter than 60 mm leaves nothing
    assert flat(M.staircase_host(f_plateau=0.42, plateau_len=0.100, notch=0.020)) is None  # 40 mm halves


def test_a_step_inside_the_flat_band_is_one_run_and_one_outside_it_is_not():
    assert flat(M.staircase_host(plateau_len=0.080, step_after=0.004)).f1 - 0.42 == pytest.approx(0.080, abs=0.0006)  # 4 mm: within 5 mm
    assert flat(M.staircase_host(plateau_len=0.080, step_after=0.006)) is None  # 6 mm: two 40 mm halves


# ---------------------------------------------------------------- step 4 helpers


def test_clip_run_ends_the_run_10_mm_behind_a_front_sight():
    run = runs(M.toothed_host())[0]  # f 0.12 .. 0.261
    clipped = clip_run(run, 0.255, 0.010)
    assert clipped is not None
    assert clipped.f1 == pytest.approx(0.245, abs=0.0001)
    assert clipped.f0 == run.f0
    assert (clipped.top_u, clipped.pitch_m, clipped.amp_m, clipped.teeth, clipped.width_m, clipped.toothed) == (
        run.top_u,
        run.pitch_m,
        run.amp_m,
        run.teeth,
        run.width_m,
        True,
    )
    assert run.f1 == pytest.approx(0.261, abs=0.0006)  # the input is a frozen dataclass and untouched


def test_clip_run_edges():
    run = RailRun(f0=0.100, f1=0.300, top_u=0.02, pitch_m=0.0235, amp_m=0.004, teeth=8, width_m=0.017, toothed=True)
    assert clip_run(run, 0.400, 0.010) is run  # the sight is far ahead: unchanged
    assert clip_run(run, 0.310, 0.010) is run  # exactly 10 mm ahead of the end: nothing to cut
    assert clip_run(run, 0.309, 0.010).f1 == pytest.approx(0.299, abs=1e-9)
    assert clip_run(run, 0.110, 0.010) is None  # clip lands on the run's start: nothing left
    assert clip_run(run, 0.050, 0.010) is None  # the run lies wholly ahead of the sight
    assert clip_run(run, 0.120, 0.010).f1 == pytest.approx(0.110, abs=1e-9)


def test_seat_point_is_the_centre_of_the_rearmost_200_mm_at_the_top():
    short = RailRun(f0=0.120, f1=0.261, top_u=0.005, pitch_m=0.0235, amp_m=0.004, teeth=6, width_m=0.017, toothed=True)
    assert seat_point(short, 0.20) == (pytest.approx(0.1905, abs=1e-9), 0.005)  # the whole 141 mm run
    long = RailRun(f0=0.120, f1=0.520, top_u=0.031, pitch_m=0.0235, amp_m=0.004, teeth=17, width_m=0.017, toothed=True)
    assert seat_point(long, 0.20) == (pytest.approx(0.220, abs=1e-9), 0.031)  # rear 200 mm: 0.12 .. 0.32
    below = RailRun(f0=0.120, f1=0.520, top_u=-0.031, pitch_m=0.0235, amp_m=0.004, teeth=17, width_m=0.017, toothed=True)
    assert seat_point(below, 0.20)[1] == -0.031  # a bottom run keeps its signed u


def test_the_detector_and_the_helpers_compose_on_a_railed_host_with_a_front_sight():
    run = runs(M.toothed_host(n=12, start_f=0.10))[0]  # f 0.10 .. 0.382
    clipped = clip_run(run, 0.300, 0.010)  # a front sight at f 0.30: the run ends at 0.29
    assert clipped.f1 == pytest.approx(0.29, abs=0.0006)
    f, u = seat_point(clipped, 0.20)  # 190 mm long: the whole of it
    assert f == pytest.approx((0.10 + 0.29) / 2, abs=0.0006)
    assert u == pytest.approx(0.005, abs=0.0001)
