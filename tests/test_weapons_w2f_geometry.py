"""Weapon directory W2f: the melee grip butt inset and the head-forward sign of a mid-origin melee item.

Everything is synthetic (tests/fixtures/weapons/w2f/make_w2f.py). Bounds are literals: the 0.045 m inset, the 25 % window
and the 15 % margin are not imported from the code under test.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from synty_inventory.weapons.geometry import measure_weapon_detail
from synty_inventory.weapons.rules import load_rules

_W2F = Path(__file__).parent / "fixtures" / "weapons" / "w2f"
_spec = importlib.util.spec_from_file_location("make_w2f", _W2F / "make_w2f.py")
F = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(F)
M = F.M


@pytest.fixture(scope="module")
def rules():
    return load_rules()


def measure(tmp_path, rules, mesh, archetype, origin_y, kind="melee", name="m"):
    """Measure ``mesh`` (butt at y 0) with its origin ``origin_y`` metres from the butt along +y."""
    path = M.write_glb(tmp_path / f"{name}.glb", [{"name": name, "mesh": M.shifted(mesh, (0.0, -origin_y, 0.0))}])
    return measure_weapon_detail(path, None, 1.0, archetype, kind, "whole", rules, genre="fantasy")


# --- item 2: the larger end head is forward when the origin says nothing ------------------------------------------------


def test_an_ornate_headed_staff_with_its_origin_mid_length_points_at_the_head(tmp_path, rules):
    d = measure(tmp_path, rules, F.ornate_staff(), "staff", 1.0)
    axes = d["geometry"]["axes"]
    assert axes["forward_source"] == "section" and "forward_by_fallback" in d["flags"]
    assert axes["forward"] == "+y"  # the 12 cm head is at +y; the end-section rule alone said -y


def test_the_same_staff_mirrored_points_the_other_way(tmp_path, rules):
    """The head at the -y end: the sign follows the head, not a fixed side."""
    v, t = F.ornate_staff()
    v = v.copy()
    v[:, 1] = 2.0 - v[:, 1]
    d = measure(tmp_path, rules, (v, t[:, ::-1]), "staff", 1.0)
    assert d["geometry"]["axes"]["forward"] == "-y"


def test_a_plain_spear_with_a_wider_butt_cap_keeps_the_tip_forward(tmp_path, rules):
    """Spears are not calibrated for the head rule (the leaf head and the butt are a wash in the pivot data): the thin end
    stays the tip. A 'larger end is forward' rule would turn this one around (butt extent 0.05 > head 0.04)."""
    d = measure(tmp_path, rules, F.capped_spear(), "spear", 1.0)
    assert d["geometry"]["axes"]["forward"] == "+y" and d["geometry"]["axes"]["forward_source"] == "section"


def test_a_pointed_archetype_keeps_the_blade_forward_against_a_heavy_guard(tmp_path, rules):
    d = measure(tmp_path, rules, F.guarded_sword(), "sword", 0.45)
    assert d["geometry"]["axes"]["forward"] == "+y"


def test_ends_within_the_margin_fall_back_to_the_end_section_rule(tmp_path, rules):
    """6.0 vs 6.2 cm heads (3 % apart): the head rule is silent, the end-section rule decides (the thinner butt end is the
    tip: -y). Without the margin the 6.2 cm end would win: +y."""
    d = measure(tmp_path, rules, F.twin_head_staff(), "staff", 1.0)
    assert d["geometry"]["axes"]["forward"] == "-y"
    assert d["geometry"]["axes"]["forward_source"] == "section" and "forward_by_fallback" in d["flags"]


def test_a_pivot_decided_sign_is_never_touched_by_the_head_rule(tmp_path, rules):
    """With the origin at the head end the designer's origin says forward is -y (away from the origin), although the head is
    at +y: the head rule must not override a pivot-given sign."""
    d = measure(tmp_path, rules, F.ornate_staff(), "staff", 2.0)
    assert d["geometry"]["axes"]["forward"] == "-y" and d["geometry"]["axes"]["forward_source"] == "pivot"
    assert "forward_by_fallback" not in d["flags"]


# --- item 1: the grip is kept a hand-half off the butt ------------------------------------------------------------------


def test_a_pivot_grip_at_the_butt_is_pushed_out_to_4_5_cm_along_the_forward_axis_only(tmp_path, rules):
    """sparse_haft (a club, origin at the butt): the grip stays at the origin but is held 0.045 m off the end. The mesh is
    shifted 1 cm in x, so the lateral coordinate (the run's surface mean, about 0.01) shows the move was along y only."""
    mesh = M.shifted(M.sparse_haft(), (0.01, 0.0, 0.0))
    g = measure(tmp_path, rules, mesh, "club", 0.0)["geometry"]
    assert g["grip_source"] == "handle"
    assert abs(g["grip"][1] - 0.045) <= 0.0005
    assert abs(g["grip"][0] - 0.01) <= 0.005 and abs(g["grip"][2]) <= 0.005


def test_a_grip_already_further_in_is_not_moved(tmp_path, rules):
    g = measure(tmp_path, rules, M.sparse_haft(), "club", 0.201)["geometry"]  # origin 20.1 cm in, inside the thin run
    assert g["grip_source"] == "handle" and abs(g["grip"][1]) <= 0.0005  # the grip stays AT the origin (AC40 case a)


def test_the_inset_is_capped_at_half_the_length_of_a_very_short_item(tmp_path, rules):
    g = measure(tmp_path, rules, F.tiny_item(), "knife", 0.0)["geometry"]
    assert abs(g["grip"][1] - 0.03) <= 0.0005  # the origin is the butt, so grip y is its distance from it: half of 0.06


def test_a_ranged_grip_at_the_butt_is_not_moved(tmp_path, rules):
    """Only the melee grip is held off the butt: a pistol grip is the origin."""
    mesh = M.box((-0.02, -0.05, 0.0), (0.02, 0.05, 0.2))
    path = M.write_glb(tmp_path / "p.glb", [{"name": "p", "mesh": mesh}])
    g = measure_weapon_detail(path, None, 1.0, "pistol", "ranged", "whole", rules, genre="modern")["geometry"]
    assert g["grip"] == [0.0, 0.0, 0.0] and g["grip_source"] == "pivot"
