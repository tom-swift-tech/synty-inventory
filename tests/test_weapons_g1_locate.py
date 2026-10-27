"""G1 S3 and errata E1.2: the locator and strip (docs/weapon_attach_geometry.md 3.2, 3.11, 4.1; AC131 and AC132, fixture side; INV-29).

The meshes are the synthetic ones of ``fixtures/weapons/g1_locate_meshes.py`` (a 12-vertex asymmetric part, translated copies of it). Every rule
value, translation and expected number below is a LITERAL written out here, never read from the code under test or from ``weapon_rules.yaml``:
the rules dict is a copy of the spec 4.1 ``locator`` values, the whole-cell translations are 4-decimal metres (T_HALF adds 0.25 mm), the 1 mm and 0.25 mm offsets are written out.

Deliberate breaks (run in a scratch copy, never in the worktree), and the tests that fail on each:

* ``hit_min`` lowered to 0.9 (AC131; the rules dict of the test): ``test_a_part_with_one_vertex_moved_1_mm_is_not_located`` (the moved part
  IS located then) and ``test_a_part_with_one_vertex_moved_1_cm_is_not_located`` (11 of its 12 vertices are still in the host);
* the 27-neighbour tolerance dropped (AC131; the neighbour offsets reduced to ``(0, 0, 0)``): ``test_a_placement_on_a_half_grid_offset_is_located``,
  ``test_a_vertex_moved_0_4_mm_is_still_located``, ``test_strip_keeps_a_base_triangle_that_shares_one_vertex_with_a_fused_part``;
* strip skipped (AC132; ``strip`` returns the host unchanged): ``test_strip_returns_the_base_mesh_triangle_for_triangle``,
  ``test_no_triangle_remaining_after_strip_has_all_three_vertices_on_a_located_part`` and three more ``test_strip_*``;
* E1.2: the landing test run on whole-cell shifts instead of on the stored ``t`` (the old locator):
  ``test_a_copy_off_the_cell_grid_with_a_vertex_0_1_mm_off_is_located`` and its strip twin;
* E1.2: strip on its own finer grid (1e-4 m, the old ``_STRIP_CELL_M``; INV-29): ``test_a_fused_copy_0_1_mm_off_the_part_is_stripped_to_the_base``
  and ``test_the_off_grid_copy_is_stripped_to_the_base``;
* E1.3: strip on every placement is the caller's scope (``fit_geometry``), tested in ``test_weapons_g1_seats.py``.
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
    # 0.4 mm is under one cell: the vertex lands in this cell or the next, and the 27-neighbour tolerance accepts both (E1.2 guarantee)
    hv, _ = host([T_A])
    moved = M.moved(PART_V, 5, (0.0004, 0.0, 0.0))  # E1.2: 0.4 mm (it was 0.2 mm); within grid_m on every axis, so it lands
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


# ---- E1.2: one landing test, on the stored translation (AC131, AC132, INV-29) -----------------------------------------------------------

OFF_V, OFF_T = M.offgrid_part()
OFF_PART = M.moved(OFF_V, 1, M.OFFGRID_MOVE)  # the part as passed: row 1 is 0.1 mm lower on x than the copy fused into the host


def jittered_host():
    return M.host_from(BASE_VERTS, BASE_TRIS, M.jittered(PART_V), PART_T, [T_A])


def test_the_jittered_copy_is_the_size_the_tests_assume():
    v, t = jittered_host()
    assert v.shape == (8 + 12, 3) and t.shape == (12 + 12, 3)
    assert np.allclose(v[8] - (PART_V[0] + T_A), 0.0001, atol=1e-12) and np.allclose(v[9] - (PART_V[1] + T_A), -0.0001, atol=1e-12)


def test_a_fused_copy_0_1_mm_off_the_part_is_located_at_hit_1():
    hv, _ = jittered_host()
    (p,) = locate_by_translation(hv, PART_V, RULES)
    assert p.hit == 1.0
    assert p.t == pytest.approx((T_A[0] + 0.0001, T_A[1] + 0.0001, T_A[2] + 0.0001), abs=1e-9)  # the smallest vertex's host copy gives the t


def test_a_fused_copy_0_1_mm_off_the_part_is_stripped_to_the_base():
    # AC132 and INV-29: the locator places it at hit 1.0, so strip leaves no triangle of the copy (today 24 triangles remain, the base's 12 and
    # the copy's, because strip matched on a finer grid than the locator)
    hv, ht = jittered_host()
    (p,) = locate_by_translation(hv, PART_V, RULES)
    sv, st = strip(hv, ht, [dataclasses.replace(p, part="Scope_01")], {"Scope_01": PART_V}, RULES)
    assert st.shape == (12, 3) and sv.shape == (8, 3)
    assert coord_tris(sv, st) == EXPECTED_BASE


def test_the_jitter_is_also_stripped_at_0_15_and_0_2_mm():
    # the errata's evidence: the same happens at 0.15 and 0.2 mm (the vertices stay within the 0.5 mm tolerance of the stored t)
    for amount in (0.00015, 0.0002):
        hv, ht = M.host_from(BASE_VERTS, BASE_TRIS, M.jittered(PART_V, amount), PART_T, [T_A])
        (p,) = locate_by_translation(hv, PART_V, RULES)
        assert p.hit == 1.0
        sv, st = strip(hv, ht, [dataclasses.replace(p, part="Scope_01")], {"Scope_01": PART_V}, RULES)
        assert coord_tris(sv, st) == EXPECTED_BASE, amount


def offgrid_host():
    return M.host_from(BASE_VERTS, BASE_TRIS, OFF_V, OFF_T, [M.OFFGRID_T])


def test_the_off_grid_fixture_is_the_size_and_shape_the_tests_assume():
    hv, ht = offgrid_host()
    assert hv.shape == (8 + 4, 3) and ht.shape == (12 + 4, 3)
    assert OFF_PART.shape == (4, 3) and not np.array_equal(OFF_PART, OFF_V)
    # the premises of the case, in cells of 0.5 mm: row 0 is the smallest vertex, the translation is 0.88 of a cell on x past whole cells
    assert OFF_V[0, 0] == OFF_V[:, 0].min() and OFF_V[0, 0] / 0.0005 == pytest.approx(10.05)
    assert M.OFFGRID_T[0] / 0.0005 == pytest.approx(200.88)


def test_a_copy_off_the_cell_grid_with_a_vertex_0_1_mm_off_is_located():
    # AC131: a translation that is not a whole number of cells and one vertex 0.1 mm off. The old test shifted whole cells from the smallest vertex
    # and tested the others there: this vertex ends two cells from where that shift puts it, so the copy was lost
    hv, _ = offgrid_host()
    got = locate_by_translation(hv, OFF_PART, RULES)
    assert len(got) == 1 and got[0].hit == 1.0
    assert got[0].t == pytest.approx(M.OFFGRID_T, abs=1e-4)  # reported to 1e-4 m


def test_the_off_grid_copy_is_stripped_to_the_base():
    # INV-29 on the second E1.2 fixture
    hv, ht = offgrid_host()
    (p,) = locate_by_translation(hv, OFF_PART, RULES)
    sv, st = strip(hv, ht, [dataclasses.replace(p, part="Tetra")], {"Tetra": OFF_PART}, RULES)
    assert st.shape == (12, 3) and sv.shape == (8, 3)
    assert coord_tris(sv, st) == EXPECTED_BASE


def test_the_off_grid_part_moved_1_mm_is_not_located():
    # the guarantee's other side: 1 mm is 2 x grid_m, the vertex never lands
    hv, _ = offgrid_host()
    assert locate_by_translation(hv, M.moved(OFF_V, 1, (-0.001, 0.0, 0.0)), RULES) == []


def test_strip_reads_its_grid_from_the_rules_so_it_cannot_drift_from_the_locator():
    # the same copy and the same stored t: a 0.5 mm grid strips it, a 0.1 mm grid (the old strip cell) leaves its triangles
    hv, ht = jittered_host()
    (p,) = locate_by_translation(hv, PART_V, RULES)
    placed, meshes = [dataclasses.replace(p, part="Scope_01")], {"Scope_01": PART_V}
    assert strip(hv, ht, placed, meshes, RULES)[1].shape == (12, 3)
    fine = {"locator": {**RULES["locator"], "grid_m": 0.0001}}
    assert strip(hv, ht, placed, meshes, fine)[1].shape == (24, 3)


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
    sv, st = strip(hv, ht, pls, {p.part: PART_V for p in pls}, RULES)
    assert sv.shape == (8, 3) and st.shape == (12, 3)  # the located parts' vertices are gone with their triangles
    assert coord_tris(sv, st) == EXPECTED_BASE
    assert [tuple(v) for v in sv] == BASE_VERTS


def test_the_located_host_holds_the_part_triangles_that_strip_must_remove():
    # the premise of the AC132 break: before strip the host holds 36 more triangles than the base
    _, ht, _ = located([T_A, T_B, T_C])
    assert len(ht) == 12 + 36


def test_no_triangle_remaining_after_strip_has_all_three_vertices_on_a_located_part():
    hv, ht, pls = located([T_A, T_B, T_C])
    sv, st = strip(hv, ht, pls, {p.part: PART_V for p in pls}, RULES)
    for tr in (T_A, T_B, T_C):
        on_part = {tuple(round(float(c), 9) for c in v) for v in PART_V + np.array(tr)}
        for tri in st:
            assert not all(tuple(round(float(c), 9) for c in sv[i]) in on_part for i in tri)


def test_strip_keeps_a_base_triangle_that_shares_one_vertex_with_a_fused_part():
    # the copy's vertex 0 sits exactly on the base corner (0.04, 0.03, 0.02): that corner is on the part, but its base triangles are not
    fused = (0.04 - 0.000125, 0.03 - 0.000125, 0.02 - 0.000125)
    hv, ht, pls = located([fused, T_B], names=("Scope_01", "Grip_02"))
    assert len(pls) == 2
    sv, st = strip(hv, ht, pls, {p.part: PART_V for p in pls}, RULES)
    assert sv.shape == (8, 3)
    assert coord_tris(sv, st) == EXPECTED_BASE


def test_strip_accepts_a_part_mesh_given_as_verts_and_tris():
    hv, ht, pls = located([T_A])
    sv, st = strip(hv, ht, pls, {pls[0].part: (PART_V, PART_T)}, RULES)
    assert coord_tris(sv, st) == EXPECTED_BASE


def test_strip_with_no_placement_returns_the_host_unchanged():
    hv, ht = host([T_A])
    sv, st = strip(hv, ht, [], {}, RULES)
    assert np.array_equal(sv, hv) and np.array_equal(st, ht)


def test_strip_does_not_modify_its_inputs():
    hv, ht, pls = located([T_A, T_B, T_C])
    hv0, ht0 = hv.copy(), ht.copy()
    strip(hv, ht, pls, {p.part: PART_V for p in pls}, RULES)
    assert np.array_equal(hv, hv0) and np.array_equal(ht, ht0)


def test_strip_names_the_missing_part_mesh():
    hv, ht, pls = located([T_A], names=("Scope_01",))
    with pytest.raises(KeyError, match="Scope_01"):
        strip(hv, ht, pls, {}, RULES)
