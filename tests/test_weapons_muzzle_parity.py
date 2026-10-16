"""AC12: the Python ``muzzle_point`` matches sit_weapons' ``SitGunHold.muzzle_local`` on the shared golden.

``tests/fixtures/weapons/muzzle_golden.json`` (schema ``sit_muzzle_golden/1``) is copied byte for byte from
sit-capabilities (``tools/probes/muzzle_golden.json``); the Godot probe produced it. This test FAILS, it does not
skip, when the file or any of the five named cases is missing: a skip would not satisfy AC12. Tolerances and the
expected values are literals here, not the constants of the code under test.
"""

from __future__ import annotations

import json
from pathlib import Path

from synty_inventory.weapons.geometry import muzzle_point

GOLDEN = Path(__file__).parent / "fixtures" / "weapons" / "muzzle_golden.json"
CASES = ("plain", "inflated_bounds", "edge2_widened", "edge3_face", "cone_apex")
# the spec's expected values (section 6, AC12), independent of the golden file's own numbers
EXPECTED = {
    "plain": ([0.0, 0.05, 0.5], False),
    "inflated_bounds": ([0.0, 0.05, 0.5], False),
    "edge2_widened": ([0.001333, 0.05, 0.503], False),
    "edge3_face": ([0.0, 0.053333, 0.503], False),
    "cone_apex": ([0.0, 0.01, 0.2], True),
}
TOL = 0.0005


def _golden() -> dict[str, dict]:
    assert GOLDEN.is_file(), f"muzzle golden not present: {GOLDEN}"
    doc = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert doc["schema"] == "sit_muzzle_golden/1"
    by_name = {c["name"]: c for c in doc["cases"]}
    missing = [n for n in CASES if n not in by_name]
    assert not missing, f"muzzle golden lacks cases: {missing}"
    return by_name


def test_ac12_golden_is_present_with_all_five_cases():
    assert set(_golden()) >= set(CASES)


def test_ac12_muzzle_point_matches_the_godot_golden_on_every_case():
    cases = _golden()
    for name in CASES:
        case = cases[name]
        point, source = muzzle_point(case["vertices"], "+z", "+y")
        for axis in range(3):
            assert abs(point[axis] - case["muzzle"][axis]) <= TOL, (name, axis, point, case["muzzle"])
        assert (source == "bounds_fallback") == bool(case["fallback"]), name
        # and against the spec's own numbers, so a wrong golden copy cannot hide a wrong port
        want, fallback = EXPECTED[name]
        for axis in range(3):
            assert abs(point[axis] - want[axis]) <= TOL, (name, axis, point, want)
        assert (source == "bounds_fallback") == fallback, name


def test_ac12_inflated_bounds_differs_from_the_bounds_centre_rule_by_at_least_two_cm():
    case = _golden()["inflated_bounds"]
    point, source = muzzle_point(case["vertices"], "+z", "+y")
    assert source == "face"
    ys = [v[1] for v in case["vertices"]]
    bounds_centre_y = (min(ys) + max(ys)) / 2
    assert abs(point[1] - bounds_centre_y) >= 0.02


def test_ac12_edge2_is_widened_to_a_face_not_a_fallback():
    case = _golden()["edge2_widened"]
    point, source = muzzle_point(case["vertices"], "+z", "+y")
    assert source == "face"
    assert abs(point[0] - 0.001333) <= TOL


def test_ac12_the_port_follows_a_signed_forward_axis():
    # the same plain gun rotated so the barrel points along -x: the muzzle rotates with it
    case = _golden()["plain"]
    rotated = [[-v[2], v[1], v[0]] for v in case["vertices"]]  # (x, y, z) -> (-z, y, x): +z maps onto -x
    point, source = muzzle_point(rotated, "-x", "+y")
    assert source == "face"
    assert abs(point[0] - (-0.5)) <= TOL and abs(point[1] - 0.05) <= TOL and abs(point[2] - 0.0) <= TOL


# --- the tolerance windows: the shared golden never decides at 0.002 ---------------------------------------------------
#
# Why the previous mutation (drop 0.002 from the window tuple) failed no test: in muzzle_golden.json the point count of
# every case jumps over the 0.002 window. plain, inflated_bounds and edge3_face already hold 3-4 points at 0.001;
# edge2_widened has 2 points at 0.001 AND 0.002 and 6 at 0.005; cone_apex has 1 point in every window. So the 0.002
# step is never the first window with >= 3 points, and removing it moves no result. w2c/muzzle_windows.json is a
# hand-worked golden (spec 3.5.4, not the Godot probe) with one case decided by each window; the expected values are
# literals below.

WINDOWS = Path(__file__).parent / "fixtures" / "weapons" / "w2c" / "muzzle_windows.json"
WINDOW_EXPECTED = {
    # the decisive window's lateral mean (x, y) and the max forward coordinate
    "window_0001_three_points": [0.003333, 0.066667, 0.5],
    "window_0002_exactly_three": [0.003333, 0.066667, 0.5],
    "window_0005_three_points": [0.003333, 0.066667, 0.5],
    "window_0010_three_points": [0.003333, 0.066667, 0.5],
}
# what the next window would give: the decoy vertices pull the mean far from the right answer
WINDOW_WRONG_IF_SKIPPED = {
    "window_0001_three_points": [0.015, 0.05, 0.5],  # the 0.002 window: 4 points
    "window_0002_exactly_three": [0.016, 0.04, 0.5],  # the 0.005 window: 5 points
    "window_0005_three_points": [0.016, 0.04, 0.5],  # the 0.010 window: 5 points
}


def _window_cases() -> dict[str, dict]:
    assert WINDOWS.is_file(), f"muzzle window golden not present: {WINDOWS}"
    doc = json.loads(WINDOWS.read_text(encoding="utf-8"))
    return {c["name"]: c for c in doc["cases"]}


def test_each_tolerance_window_decides_one_case_with_the_hand_worked_mean():
    cases = _window_cases()
    assert set(cases) == set(WINDOW_EXPECTED)
    for name, want in WINDOW_EXPECTED.items():
        point, source = muzzle_point(cases[name]["vertices"], "+z", "+y")
        assert source == "face", name
        for axis in range(3):
            assert abs(point[axis] - want[axis]) <= TOL, (name, axis, point, want)


def test_the_window_cases_are_set_apart_by_more_than_the_tolerance():
    """Guards the fixture: skipping the deciding window would give a point further than 20 tolerances away, so a
    mutation of the window tuple cannot hide inside the tolerance."""
    cases = _window_cases()
    for name, wrong in WINDOW_WRONG_IF_SKIPPED.items():
        want = WINDOW_EXPECTED[name]
        assert max(abs(wrong[a] - want[a]) for a in range(3)) >= 20 * TOL, name
    # the 0.010 case has no wrong 'next window': skipping it leaves < 3 points everywhere -> the bounds fallback
    verts = cases["window_0010_three_points"]["vertices"]
    assert sum(1 for v in verts if v[2] >= 0.5 - 0.005) == 2


def test_the_muzzle_is_the_max_forward_coordinate_not_a_window_mean():
    # the forward coordinate of a face point is the bounds maximum, even when the deciding window starts below it
    cases = _window_cases()
    for name in WINDOW_EXPECTED:
        point, _ = muzzle_point(cases[name]["vertices"], "+z", "+y")
        assert abs(point[2] - 0.5) <= 1e-9, name
