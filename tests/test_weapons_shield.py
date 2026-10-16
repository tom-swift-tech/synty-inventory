"""Weapon geometry: the shield front face (spec 3.5.2 item 4).

The origin is a weak guide to which side of a shield is the front (it points the wrong way for roughly a third of the
real ones), so the rule measures the mesh: arm straps stand off the BACK, and a shield is convex toward the FRONT; the
origin is only the last fallback. Everything here is synthetic (tests/fixtures/weapons/make_glbs.py writes the GLBs);
every expectation is a literal worked out from the fixture docstrings, never read back from the code under test.
In every named fixture the origin sits on the FRONT side of the body, so the old "away from the origin" rule picks
the back.
"""

from __future__ import annotations

import hashlib
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


M = _load("make_glbs")

from synty_inventory.weapons import geometry as G  # noqa: E402
from synty_inventory.weapons.geometry import measure_cached, measure_weapon_detail  # noqa: E402
from synty_inventory.weapons.rules import load_rules  # noqa: E402


@pytest.fixture(scope="module")
def rules():
    return load_rules()


@pytest.fixture(scope="module")
def glbs(tmp_path_factory):
    return M.generate_all(tmp_path_factory.mktemp("shield_glbs"))


def shield(path, rules):
    return measure_weapon_detail(path, None, 1.0, "shield", "shield", "whole", rules, genre="fantasy")


# fixture -> (forward, item_basis, signal): hand-worked from the make_glbs docstrings
FRONTS = {
    "shield_strap_pz": ("+z", [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "shield_front"),
    "shield_strap_nz": ("-z", [[-1, 0, 0], [0, 1, 0], [0, 0, -1]], "shield_front"),
    "shield_strap_px": ("+x", [[0, 0, -1], [0, 1, 0], [1, 0, 0]], "shield_front"),
    "shield_dish_pz": ("+z", [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "shield_front"),
    "shield_dish_nz": ("-z", [[-1, 0, 0], [0, 1, 0], [0, 0, -1]], "shield_front"),
    "shield_strap_over_dish": ("+z", [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "shield_front"),
}


@pytest.mark.parametrize("name", sorted(FRONTS))
def test_forward_points_to_the_front_and_up_stays_the_longer_face_axis(glbs, rules, name):
    want_forward, want_basis, want_source = FRONTS[name]
    geo = shield(glbs[name], rules)["geometry"]
    assert geo["axes"]["forward"] == want_forward
    assert geo["axes"]["forward_source"] == want_source
    assert geo["axes"]["up"] == "+y"  # the face is 0.6 x 0.8: y is the longer remaining axis, whatever the normal
    assert geo["axes"]["up_source"] == "shield_rule"
    assert geo["item_basis"] == want_basis
    assert geo["long_axis"] == "y" and abs(geo["length_m"] - 0.8) <= 0.001


@pytest.mark.parametrize("name", sorted(FRONTS))
def test_the_fixture_origin_is_on_the_front_so_the_old_pivot_rule_would_be_wrong(glbs, rules, name):
    """Guards the fixtures themselves: the origin lies on the forward side of the bounds (past the half), so a rule
    that points away from the origin would choose the back."""
    forward = FRONTS[name][0]  # the literal, not the measurement: this guards the fixture, not the rule
    axis, sign = "xyz".index(forward[1]), (1 if forward[0] == "+" else -1)
    bounds = shield(glbs[name], rules)["geometry"]["bounds"]
    lo, hi = bounds["min"][axis], bounds["max"][axis]
    origin_toward_front = (0.0 - lo) / (hi - lo) if sign > 0 else (hi - 0.0) / (hi - lo)
    assert origin_toward_front >= 0.99


def test_the_origin_does_not_move_a_decided_front(glbs, rules, tmp_path):
    base = M.shield_strapped()
    for dz in (-0.12, -0.04, 0.0, 0.5, -3.0):  # origin behind, inside and far from the body
        path = M.write_glb(tmp_path / f"s{dz}.glb", [{"name": "s", "mesh": M.shifted(base, (0.0, 0.0, dz))}])
        axes = shield(path, rules)["geometry"]["axes"]
        assert axes["forward"] == "+z" and axes["forward_source"] == "shield_front"


def test_a_shield_with_no_straps_and_no_dish_falls_back_to_the_origin_rule(glbs, rules, tmp_path):
    # the original fixture: flat plate plus a compact round boss; no strap-like piece, no dish
    plain = shield(glbs["shield"], rules)["geometry"]["axes"]
    assert (plain["forward"], plain["forward_source"]) == ("+z", "shield_rule")  # origin on the z = 0 arm face
    for dz, want in ((-0.08, "-z"), (0.0, "+z"), (0.1, "+z")):
        path = M.write_glb(tmp_path / f"p{dz}.glb", [{"name": "p", "mesh": M.shifted(M.shield(), (0.0, 0.0, dz))}])
        axes = shield(path, rules)["geometry"]["axes"]
        assert (axes["forward"], axes["forward_source"]) == (want, "shield_rule")  # z 0.08 ends at the origin: -z


def test_an_origin_in_the_middle_band_of_the_thickness_resolves_to_plus(glbs, rules, tmp_path):
    # z -0.04..0.04 puts the origin at 0.50 of the thickness; 0.55 and 0.45 are inside the +-0.10 band as well,
    # 0.606 is outside it (the origin side decides again: -z) and 0.39 is outside on the other side (+z)
    for dz, want in ((-0.04, "+z"), (-0.044, "+z"), (-0.036, "+z"), (-0.0485, "-z"), (-0.0315, "+z")):
        path = M.write_glb(tmp_path / f"m{dz}.glb", [{"name": "m", "mesh": M.shifted(M.shield(), (0.0, 0.0, dz))}])
        axes = shield(path, rules)["geometry"]["axes"]
        assert axes["forward"] == want and axes["forward_source"] == "shield_rule"


def test_measurement_is_deterministic_and_independent_of_triangle_order(glbs, rules, tmp_path):
    first = shield(glbs["shield_strap_nz"], rules)
    G._DECODE_MEMO.clear()
    assert shield(glbs["shield_strap_nz"], rules) == first
    v, t = M.shifted(M._reorient(M.shield_strapped(), flip_z=True), (0.0, 0.0, 0.04))
    shuffled = t[np.random.default_rng(7).permutation(len(t))]
    path = M.write_glb(tmp_path / "shuffled.glb", [{"name": "s", "mesh": (v, shuffled)}])
    assert shield(path, rules)["geometry"]["axes"] == first["geometry"]["axes"]


def test_vertices_split_at_seams_still_form_one_plate_and_two_straps(glbs, rules, tmp_path):
    """glTF exports duplicate vertices along UV and normal seams; the components are welded by position, so a fully
    unindexed mesh (every triangle owns its three vertices) decides the same way."""
    v, t = M.shifted(M.shield_strapped(), (0.0, 0.0, -0.04))
    split_v = v[t].reshape(-1, 3)
    split_t = np.arange(len(split_v)).reshape(-1, 3)
    path = M.write_glb(tmp_path / "split.glb", [{"name": "s", "mesh": (split_v, split_t)}])
    axes = shield(path, rules)["geometry"]["axes"]
    assert axes["forward"] == "+z" and axes["forward_source"] == "shield_front"


def test_a_boss_on_the_front_is_not_mistaken_for_a_strap(glbs, rules, tmp_path):
    """A round boss stands off the plate but has no elongation, and a long band lying on the face is not deep: neither
    counts as a strap, so a plain plate with them decides by the origin only."""
    plate = M.box((-0.3, -0.4, 0.0), (0.3, 0.4, 0.04))
    boss = M.box((-0.05, -0.05, 0.04), (0.05, 0.05, 0.12))  # round-ish, 0.08 deep
    band = M.box((-0.25, -0.02, 0.04), (0.25, 0.02, 0.05))  # 12:1 but only 0.01 deep
    path = M.write_glb(tmp_path / "boss.glb", [{"name": "b", "mesh": M.merge(plate, boss, band)}])
    axes = shield(path, rules)["geometry"]["axes"]
    assert (axes["forward"], axes["forward_source"]) == ("+z", "shield_rule")  # origin on the z = 0 back face


# --- nothing but shields changes ---------------------------------------------------------------------------

# sha256[:16] of the compact, key-sorted JSON of measure_weapon_detail, computed from the code BEFORE the shield
# change (same archetype / kind / hold / genre as the AC11 cases); the plain shield fixture is included because it
# decides by the origin and must be byte-identical too
SNAPSHOT = {
    "gun": ("rifle", "ranged", "long_gun", "modern", "745b043b4a2219c5"),
    "gun_wide": ("rifle", "ranged", "long_gun", "modern", "3d07d219fc2505ff"),
    "gun_inflated": ("rifle", "ranged", "long_gun", "modern", "9dffa52dab0c2810"),
    "gun_cone": ("rifle", "ranged", "long_gun", "modern", "cc20f99fc126c861"),
    "pistol": ("pistol", "ranged", None, "modern", "1deae6a1ea70911f"),
    "sword": ("sword", "melee", None, "fantasy", "d5bc71055d327a9d"),
    "knife": ("knife", "melee", None, "fantasy", "3753d5d0be08aeee"),
    "axe": ("axe", "melee", None, "fantasy", "0f6198fd9cf0c0f2"),
    "spear": ("spear", "melee", None, "fantasy", "e559abe79e1c646a"),
    "bow": ("bow", "ranged", None, "fantasy", "ab24c784a4a8d7c0"),
    "zlong_melee": ("sword", "melee", None, "fantasy", "675787f7d019805a"),
    "zigzag": ("club", "melee", None, "fantasy", "485b46971169cb6e"),
    "origin_outside": ("rifle", "ranged", "long_gun", "modern", "7609781a37aa579a"),
    "degenerate": ("sword", "melee", None, "fantasy", "405fc4cad17fe547"),
    "shield": ("shield", "shield", None, "fantasy", "0a78d19cf11c3f43"),
}


@pytest.mark.parametrize("name", sorted(SNAPSHOT))
def test_non_shield_fixtures_and_the_undecided_shield_are_byte_identical_to_before(glbs, rules, name):
    archetype, kind, hold, genre, want = SNAPSHOT[name]
    detail = measure_weapon_detail(glbs[name], None, 1.0, archetype, kind, "whole", rules, hold_class=hold, genre=genre)
    blob = json.dumps(detail, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16] == want


def test_the_cache_round_trip_keeps_the_new_front(glbs, rules, tmp_path):
    cache: dict = {}
    first, hit1 = measure_cached(glbs["shield_strap_nz"].parent, "shield_strap_nz.glb", None, 1.0, "shield", "shield",
                                 "whole", rules, cache, genre="fantasy")
    G._DECODE_MEMO.clear()
    second, hit2 = measure_cached(glbs["shield_strap_nz"].parent, "shield_strap_nz.glb", None, 1.0, "shield", "shield",
                                  "whole", rules, json.loads(json.dumps(cache)), genre="fantasy")
    assert (hit1, hit2) == (False, True)
    assert first == second and second["geometry"]["axes"]["forward"] == "-z"
