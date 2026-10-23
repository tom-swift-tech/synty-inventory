"""W8l: the free-end forward and the foot lip ladder (docs/weapon_attachments.md 3.4 steps 1a and 3b; A4 items 1 and 3; AC105, AC107).

The meshes are the vertex clouds of ``fixtures/weapons/w8l_meshes.py`` (hand-derived numbers in its docstring). Every expected value is a
LITERAL worked out from those dimensions, never read from the module under test.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("w8l_meshes", Path(__file__).parent / "fixtures" / "weapons" / "w8l_meshes.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)

from synty_inventory.weapons import ANCHOR_FORWARD_SOURCES  # noqa: E402
from synty_inventory.weapons.attach import measure_anchor  # noqa: E402

PLUS_Z, MINUS_Z = [0.0, 0.0, 1.0], [0.0, 0.0, -1.0]


def forward_of(v, slot, kind=None, override=None):
    got = measure_anchor(v, slot, override, kind=kind)
    return got["anchor"]["forward"], got["anchor"]["forward_source"], got["anchor"]["symmetric"], got["reasons"]


# --- AC105: the free end decides the forward of a standard magazine and a bipod ---------------------------------------


def test_ac105_a_free_end_leaning_30_mm_forward_beats_the_section_prior_for_a_standard_magazine():
    # the section prior reads -z (the back plate is the larger end); the lower quarter leans 30 mm toward +z
    assert forward_of(M.banana(0.030), "magazine")[:3] == (MINUS_Z, "section", False)  # no kind: the old result
    fwd, source, symmetric, reasons = forward_of(M.banana(0.030), "magazine", "standard")
    assert (fwd, source, symmetric, reasons) == (PLUS_Z, "free_end", False, [])


def test_ac105_the_mirror_image_leans_to_minus_z():
    fwd, source, symmetric, reasons = forward_of(M.flip_z(M.banana(0.030)), "magazine", "standard")
    assert (fwd, source, symmetric, reasons) == (MINUS_Z, "free_end", False, [])


def test_ac105_a_9_mm_lean_keeps_the_section_result_byte_for_byte_and_an_11_mm_lean_takes_the_free_end():
    old = measure_anchor(M.banana(0.009), "magazine")
    assert old["anchor"]["forward"] == MINUS_Z and old["anchor"]["forward_source"] == "section"
    assert measure_anchor(M.banana(0.009), "magazine", kind="standard") == old
    new = forward_of(M.banana(0.011), "magazine", "standard")
    assert new == (PLUS_Z, "free_end", False, [])


def test_ac105_a_bipod_whose_legs_lean_80_mm_toward_minus_z_points_to_minus_z():
    # the plate sits at +z, so the section prior reads +z; the legs lean -80 mm
    v = M.flip_z(M.banana(0.080))
    assert forward_of(v, "underbarrel")[:2] == (PLUS_Z, "section")
    assert forward_of(v, "underbarrel", "bipod") == (MINUS_Z, "free_end", False, [])


@pytest.mark.parametrize("slot, kind, foot_at_bottom", [
    ("magazine", "drum", False), ("magazine", "extended", False), ("magazine", "cell", False),
    ("underbarrel", "foregrip", False), ("optic", "scope", True), ("optic", "reflex", True),
    ("laser_light", "laser", True), ("laser_light", "light", True), ("sight_front", "post", True),
])
def test_ac105_the_rule_is_not_applied_to_any_other_slot_or_kind(slot, kind, foot_at_bottom):
    v = M.flip_y(M.banana(0.030)) if foot_at_bottom else M.banana(0.030)
    assert forward_of(v, slot, kind) == (MINUS_Z, "section", False, [])


def test_ac105_a_standard_magazine_on_the_bottom_foot_side_is_not_special_either_way_round():
    # the pair table names slot AND kind: a `standard` kind in another slot, and a `bipod` kind outside underbarrel, take nothing
    assert forward_of(M.flip_y(M.banana(0.030)), "optic", "standard")[:2] == (MINUS_Z, "section")
    assert forward_of(M.banana(0.030), "underbarrel", "standard")[:2] == (MINUS_Z, "section")
    assert forward_of(M.banana(0.030), "magazine", "bipod")[:2] == (MINUS_Z, "section")


def test_ac105_an_explicit_forward_override_wins_over_the_free_end():
    for want, vec in (("-z", MINUS_Z), ("+z", PLUS_Z)):
        fwd, source, symmetric, _ = forward_of(M.banana(0.030), "magazine", "standard", override=want)
        assert (fwd, source, symmetric) == (vec, "override", False)


def test_ac105_free_end_is_a_member_of_the_forward_source_enum():
    assert "free_end" in ANCHOR_FORWARD_SOURCES


def test_ac105_the_threshold_and_the_pair_table_come_from_the_parameters_not_the_code():
    base = {"foot_depths_m": [0.004, 0.008, 0.016], "lip_min_m": 0.001, "lip_max_m": 0.0045, "lip_growth": 2.0,
            "free_end": {"min_displacement_m": 0.010, "kinds": {"magazine": ["standard"], "underbarrel": ["bipod"]}}}
    loose = {**base, "free_end": {**base["free_end"], "min_displacement_m": 0.005}}
    assert measure_anchor(M.banana(0.009), "magazine", None, kind="standard", params=base)["anchor"]["forward_source"] == "section"
    assert measure_anchor(M.banana(0.009), "magazine", None, kind="standard", params=loose)["anchor"]["forward_source"] == "free_end"
    no_kinds = {**base, "free_end": {**base["free_end"], "kinds": {}}}
    assert measure_anchor(M.banana(0.030), "magazine", None, kind="standard", params=no_kinds)["anchor"]["forward_source"] == "section"


def test_ac105_only_the_forward_changes_the_footprint_and_point_do_not():
    old = measure_anchor(M.banana(0.030), "magazine")
    new = measure_anchor(M.banana(0.030), "magazine", kind="standard")
    assert new["anchor"]["point"] == old["anchor"]["point"] == [0.0, 0.0, 0.0]
    assert new["anchor"]["up"] == old["anchor"]["up"] == [0.0, -1.0, 0.0]
    assert new["footprint"] == old["footprint"]


# --- AC107: a foot that the 4 mm slab cuts as a lip is measured one rung deeper ----------------------------------------


def foot_of(v, slot):
    got = measure_anchor(v, slot)
    return got["anchor"]["point"], got["footprint"]


def test_ac107_a_ridge_over_a_body_reads_the_8_mm_rung():
    point, fp = foot_of(M.lipped_ridge(), "underbarrel")
    assert fp["foot_length_m"] == 0.05 and fp["foot_width_m"] == 0.021
    assert point == [0.0, 0.0, 0.01]  # the centre of the 8 mm slab (z -0.015..0.035), still at the top extreme y 0
    assert (fp["length_m"], fp["width_m"], fp["height_m"]) == (0.05, 0.021, 0.24)  # the whole-mesh extents never move


def test_ac107_a_2_5_mm_stub_over_a_body_reads_the_8_mm_rung():
    point, fp = foot_of(M.stub_over_body(), "underbarrel")
    assert (fp["foot_length_m"], fp["foot_width_m"]) == (0.04, 0.02)
    assert point == [0.0, 0.0, 0.0]


def test_ac107_a_post_that_stays_4_3_mm_deep_is_a_foot_and_is_not_stepped():
    point, fp = foot_of(M.post_on_base(), "sight_front")
    assert (fp["foot_length_m"], fp["foot_width_m"]) == (0.0043, 0.012)  # not the 40 mm of the base at the 16 mm rung
    assert point == [0.0, 0.0, 0.0]


def test_ac107_a_line_contact_foot_stays_a_line():
    point, fp = foot_of(M.line_contact(), "optic")
    assert (fp["foot_length_m"], fp["foot_width_m"]) == (0.0, 0.04)
    assert point == [0.0, 0.0, 0.0]


def test_ac107_a_flat_foot_is_untouched():
    v = M.cloud(M.box((-0.01, -0.004, -0.03), (0.01, 0.0, 0.03)), M.box((-0.01, -0.1, -0.03), (0.01, -0.004, 0.03)))
    point, fp = foot_of(v, "underbarrel")
    assert (fp["foot_length_m"], fp["foot_width_m"]) == (0.06, 0.02) and point == [0.0, 0.0, 0.0]


def test_ac107_a_ridge_over_a_ridge_takes_two_steps_and_stops_at_the_16_mm_rung():
    point, fp = foot_of(M.ridge_over_ridge(), "underbarrel")
    assert (fp["foot_length_m"], fp["foot_width_m"]) == (0.05, 0.021)
    assert point == [0.0, 0.0, 0.0]


def test_ac107_the_ladder_works_on_a_foot_at_the_bottom_too():
    point, fp = foot_of(M.flip_y(M.lipped_ridge()), "optic")
    assert (fp["foot_length_m"], fp["foot_width_m"]) == (0.05, 0.021)
    assert point == [0.0, 0.0, 0.01]


def test_ac107_the_rungs_and_the_lip_limits_come_from_the_parameters():
    base = {"foot_depths_m": [0.004, 0.008, 0.016], "lip_min_m": 0.001, "lip_max_m": 0.0045, "lip_growth": 2.0,
            "free_end": {"min_displacement_m": 0.010, "kinds": {}}}
    v = M.lipped_ridge()
    only_4 = {**base, "foot_depths_m": [0.004]}
    assert measure_anchor(v, "underbarrel", None, params=only_4)["footprint"]["foot_length_m"] == 0.004
    flat = {**base, "lip_growth": 1.0}  # a rung that merely repeats the thin extent now counts as growth
    assert measure_anchor(M.post_on_base(), "sight_front", None, params=flat)["footprint"]["foot_length_m"] == 0.04
    narrow = {**base, "lip_max_m": 0.003}  # 4 mm is no longer a lip
    assert measure_anchor(v, "underbarrel", None, params=narrow)["footprint"]["foot_length_m"] == 0.004


def test_ac107_the_ladder_does_not_touch_a_muzzle_device():
    # muzzle devices measure a mating face, not a foot slab
    tube = M.cloud(M.box((-0.01, -0.01, -0.1), (0.01, 0.01, 0.1)))
    got = measure_anchor(tube, "muzzle")
    assert got["footprint"]["mate_d_m"] is not None and got["anchor"]["forward_source"] in ("authored", "override")


def test_the_shipped_defaults_are_the_literals_of_the_spec():
    from synty_inventory.weapons.attach import DEFAULT_ANCHOR_PARAMS
    from synty_inventory.weapons.rules import attachment_rules, load_rules

    anchor = attachment_rules(load_rules())["anchor"]
    assert anchor["foot_depths_m"] == [0.004, 0.008, 0.016]
    assert (anchor["lip_min_m"], anchor["lip_max_m"], anchor["lip_growth"]) == (0.001, 0.0045, 2.0)
    assert anchor["free_end"] == {"min_displacement_m": 0.010, "kinds": {"magazine": ["standard"], "underbarrel": ["bipod"]}}
    # the built-in defaults of attach.py (used when the rules carry no table) are the shipped table, number for number
    assert DEFAULT_ANCHOR_PARAMS == anchor
