"""G1 S3: the locator and strip (docs/weapon_attach_geometry.md 3.2, 3.11, 4.1; AC131 and AC132, fixture side).

The meshes are the synthetic ones of ``fixtures/weapons/g1_locate_meshes.py`` (a 12-vertex asymmetric part, translated copies of it). Every rule
value, translation and expected number below is a LITERAL written out here, never read from the code under test or from ``weapon_rules.yaml``:
the rules dict is a copy of the spec 4.1 ``locator`` values, the whole-cell translations are 4-decimal metres (T_HALF adds 0.25 mm), the 1 mm and 0.25 mm offsets are written out.

Deliberate breaks (run in a scratch copy, never in the worktree), and the tests that fail on each:

* ``hit_min`` lowered to 0.9 (AC131; the rules dict of the test): ``test_a_part_with_one_vertex_moved_1_mm_is_not_located`` (the moved part
  IS located then) and ``test_a_part_with_one_vertex_moved_1_cm_is_not_located`` (11 of its 12 vertices are still in the host);
* the 27-neighbour tolerance dropped (AC131; the neighbour offsets reduced to ``(0, 0, 0)``): ``test_a_placement_on_a_half_grid_offset_is_located``,
  ``test_a_vertex_moved_0_4_mm_is_still_located``, ``test_strip_keeps_a_base_triangle_that_shares_one_vertex_with_a_fused_part``;
* strip skipped (AC132; ``strip`` returns the host unchanged): ``test_strip_returns_the_base_mesh_triangle_for_triangle``,
  ``test_no_triangle_remaining_after_strip_has_all_three_vertices_on_a_located_part`` and three more ``test_strip_*``.
"""

from __future__ import annotations

import dataclasses
import importlib.util
from pathlib import Path

import numpy as np
import pytest

_FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("g1_locate_meshes", _FIX / "g1_locate_meshes.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)

from synty_inventory.weapons.fit_locate import locate_by_translation, strip  # noqa: E402
from synty_inventory.weapons.fit_types import Placement  # noqa: E402

# spec 4.1 `locator`, written out (the test never reads the rules file)
RULES = {"locator": {"grid_m": 0.0005, "sample_n": 24, "hit_min": 1.0, "merge_m": 0.002}}
RULES_09 = {"locator": {"grid_m": 0.0005, "sample_n": 24, "hit_min": 0.9, "merge_m": 0.002}}

# the base mesh: a box x 0..0.04, y 0..0.03, z 0..0.02, 8 vertices and 12 triangles
BASE_VERTS = [
    (0.0, 0.0, 0.0), (0.04, 0.0, 0.0), (0.04, 0.03, 0.0), (0.0, 0.03, 0.0),
    (0.0, 0.0, 0.02), (0.04, 0.0, 0.02), (0.04, 0.03, 0.02), (0.0, 0.03, 0.02),
]  # fmt: skip
BASE_TRIS = [
    (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
    (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
]  # fmt: skip
T_A = (0.1000, 0.0600, 0.0200)
T_B = (0.1500, -0.0400, 0.0300)
T_C = (-0.0800, 0.0900, -0.0500)
T_HALF = (0.20025, 0.07025, -0.06475)  # a whole number of 0.5 mm cells plus 0.25 mm on each axis

PART_V, PART_T = M.asymmetric_part()


def host(translations, part_verts=None):
    return M.host_from(BASE_VERTS, BASE_TRIS, PART_V if part_verts is None else part_verts, PART_T, translations)


def ts(placements):
    return [p.t for p in placements]


def coord_tris(verts, tris):
    """The triangles as coordinate triples (vertex order kept), sorted: the comparison is blind to triangle order and to vertex indices."""
    v = np.asarray(verts)
    return sorted(tuple(tuple(round(float(c), 9) for c in v[i]) for i in tri) for tri in np.asarray(tris))


EXPECTED_BASE = coord_tris(BASE_VERTS, BASE_TRIS)


def test_the_fixture_is_the_size_the_tests_assume():
    v, t = host([T_A, T_B, T_C])
    assert v.shape == (8 + 3 * 12, 3) and t.shape == (12 + 3 * 12, 3)


# ---- AC131: locate_by_translation ------------------------------------------------------------------------------------------------------

def test_a_host_built_from_three_translated_parts_returns_exactly_those_three_translations():
    hv, _ = host([T_C, T_A, T_B])
    got = locate_by_translation(hv, PART_V, RULES)
    assert [p.t for p in got] == [pytest.approx(t, abs=1e-9) for t in sorted([T_A, T_B, T_C])]
    assert [p.hit for p in got] == [1.0, 1.0, 1.0]
    assert len(got) == 3


def test_a_placement_has_no_part_label_the_caller_sets_it():
    hv, _ = host([T_A])
    (p,) = locate_by_translation(hv, PART_V, RULES)
    assert isinstance(p, Placement) and p.part == ""
    assert dataclasses.replace(p, part="Scope_01").part == "Scope_01"


def test_the_result_does_not_depend_on_the_order_of_the_host_vertices():
    hv, _ = host([T_A, T_B, T_C])
    ref = locate_by_translation(hv, PART_V, RULES)
    for seed in (1, 2, 3):
        order = np.random.default_rng(seed).permutation(len(hv))
        assert locate_by_translation(hv[order], PART_V, RULES) == ref
    assert locate_by_translation(hv, PART_V[::-1].copy(), RULES) == ref  # nor on the order of the part's vertices


def test_a_part_with_one_vertex_moved_1_cm_is_not_located():
    hv, _ = host([T_A])
    assert locate_by_translation(hv, M.moved(PART_V, 3, (0.01, 0.0, 0.0)), RULES) == []


def test_a_part_with_one_vertex_moved_1_mm_is_not_located():
    hv, _ = host([T_A, T_B, T_C])
    moved = M.moved(PART_V, 5, (0.001, 0.0, 0.0))  # not the smallest vertex, so the candidate translations are unchanged
    assert locate_by_translation(hv, moved, RULES) == []


def test_that_part_is_located_at_hit_min_0_9_with_its_hit_fraction():
    hv, _ = host([T_A, T_B, T_C])
    moved = M.moved(PART_V, 5, (0.001, 0.0, 0.0))
    got = locate_by_translation(hv, moved, RULES_09)
    assert [p.t for p in got] == [pytest.approx(t, abs=1e-9) for t in sorted([T_A, T_B, T_C])]
    assert [p.hit for p in got] == [pytest.approx(11 / 12, abs=1e-4)] * 3  # 11 of 12 vertices land


def test_a_vertex_moved_0_4_mm_is_still_located():
    # 0.4 mm is under one cell: the vertex lands in this cell or the next, and the 27-neighbour tolerance accepts both
    hv, _ = host([T_A])
    moved = M.moved(PART_V, 5, (0.0002, 0.0, 0.0))
    assert [p.hit for p in locate_by_translation(hv, moved, RULES)] == [1.0]


def test_a_placement_on_a_half_grid_offset_is_located():
    hv, _ = host([T_A, T_HALF])
    got = locate_by_translation(hv, PART_V, RULES)
    assert len(got) == 2
    assert got[0].t == pytest.approx(T_A, abs=1e-9)
    assert got[1].t == pytest.approx(T_HALF, abs=1e-4)  # reported to 1e-4 m
    assert [p.hit for p in got] == [1.0, 1.0]


def test_placements_within_2_mm_merge_to_one_and_farther_ones_stay_two():
    near = (T_A[0] + 0.0015, T_A[1], T_A[2])
    far = (T_A[0] + 0.0030, T_A[1], T_A[2])
    hv, _ = host([T_A, near])
    assert [p.t for p in locate_by_translation(hv, PART_V, RULES)] == [pytest.approx(T_A, abs=1e-9)]  # the smaller t represents the pair
    hv, _ = host([T_A, far])
    assert len(locate_by_translation(hv, PART_V, RULES)) == 2


def test_the_prefilter_samples_at_most_sample_n_vertices_and_still_finds_a_big_part():
    # a part of 60 vertices (more than the 24 sampled): 5 translated copies of the 12-vertex part along x, each 0.1 m apart
    big = np.vstack([PART_V + np.array([0.1 * k, 0.0, 0.0]) for k in range(5)])
    hv = np.vstack([np.array(BASE_VERTS), big + np.array([0.0, 0.5, 0.0])])
    got = locate_by_translation(hv, big, RULES)
    assert [p.t for p in got] == [pytest.approx((0.0, 0.5, 0.0), abs=1e-9)]


def test_an_empty_part_or_host_gives_no_placement():
    hv, _ = host([T_A])
    assert locate_by_translation(hv, np.zeros((0, 3)), RULES) == []
    assert locate_by_translation(np.zeros((0, 3)), PART_V, RULES) == []


# ---- AC132: strip ----------------------------------------------------------------------------------------------------------------------

def located(translations, names=("Scope_01", "Grip_02", "Mag_03")):
    hv, ht = host(translations)
    pls = [dataclasses.replace(p, part=name) for p, name in zip(locate_by_translation(hv, PART_V, RULES), names)]
    return hv, ht, pls


def test_strip_returns_the_base_mesh_triangle_for_triangle():
    hv, ht, pls = located([T_A, T_B, T_C])
    assert len(pls) == 3
    sv, st = strip(hv, ht, pls, {p.part: PART_V for p in pls})
    assert sv.shape == (8, 3) and st.shape == (12, 3)  # the located parts' vertices are gone with their triangles
    assert coord_tris(sv, st) == EXPECTED_BASE
    assert [tuple(v) for v in sv] == BASE_VERTS


def test_the_located_host_holds_the_part_triangles_that_strip_must_remove():
    # the premise of the AC132 break: before strip the host holds 36 more triangles than the base
    _, ht, _ = located([T_A, T_B, T_C])
    assert len(ht) == 12 + 36


def test_no_triangle_remaining_after_strip_has_all_three_vertices_on_a_located_part():
    hv, ht, pls = located([T_A, T_B, T_C])
    sv, st = strip(hv, ht, pls, {p.part: PART_V for p in pls})
    for tr in (T_A, T_B, T_C):
        on_part = {tuple(round(float(c), 9) for c in v) for v in PART_V + np.array(tr)}
        for tri in st:
            assert not all(tuple(round(float(c), 9) for c in sv[i]) in on_part for i in tri)


def test_strip_keeps_a_base_triangle_that_shares_one_vertex_with_a_fused_part():
    # the copy's vertex 0 sits exactly on the base corner (0.04, 0.03, 0.02): that corner is on the part, but its base triangles are not
    fused = (0.04 - 0.000125, 0.03 - 0.000125, 0.02 - 0.000125)
    hv, ht, pls = located([fused, T_B], names=("Scope_01", "Grip_02"))
    assert len(pls) == 2
    sv, st = strip(hv, ht, pls, {p.part: PART_V for p in pls})
    assert sv.shape == (8, 3)
    assert coord_tris(sv, st) == EXPECTED_BASE


def test_strip_accepts_a_part_mesh_given_as_verts_and_tris():
    hv, ht, pls = located([T_A])
    sv, st = strip(hv, ht, pls, {pls[0].part: (PART_V, PART_T)})
    assert coord_tris(sv, st) == EXPECTED_BASE


def test_strip_with_no_placement_returns_the_host_unchanged():
    hv, ht = host([T_A])
    sv, st = strip(hv, ht, [], {})
    assert np.array_equal(sv, hv) and np.array_equal(st, ht)


def test_strip_does_not_modify_its_inputs():
    hv, ht, pls = located([T_A, T_B, T_C])
    hv0, ht0 = hv.copy(), ht.copy()
    strip(hv, ht, pls, {p.part: PART_V for p in pls})
    assert np.array_equal(hv, hv0) and np.array_equal(ht, ht0)


def test_strip_names_the_missing_part_mesh():
    hv, ht, pls = located([T_A], names=("Scope_01",))
    with pytest.raises(KeyError, match="Scope_01"):
        strip(hv, ht, pls, {})
