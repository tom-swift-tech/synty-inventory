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
