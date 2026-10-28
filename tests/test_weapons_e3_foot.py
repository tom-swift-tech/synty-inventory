"""E3.7: the foot rung must hold the part's mid-line, on rail slots (docs/weapon_attachments.md 3.4 step 1b; AC107, AC134; errata E3.7).

The meshes are the vertex clouds of ``fixtures/weapons/e3_foot_meshes.py`` (hand-derived numbers in its docstring). Every expected value is a
LITERAL worked out from those dimensions, never read from the module under test, and the 16.4 mm run below is the test's own number.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("e3_foot_meshes", Path(__file__).parent / "fixtures" / "weapons" / "e3_foot_meshes.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)

from synty_inventory.weapons.attach import measure_anchor  # noqa: E402

RUN_WIDTH_M = 0.0164  # the host's toothed run, centred at x 0 (errata E3.7's worked example)
MM = 0.001

# the slots the rule applies to (errata E3-Q7) and the slots that keep today's footprint; `hung` parts hang from a +Y foot (flip_y)
RAIL_SLOTS = [("optic", False), ("underbarrel", True)]
NON_RAIL_SLOTS = [("laser_light", False), ("sight_front", False), ("sight_rear", False), ("magazine", True)]


def measure(v, slot, hung):
    got = measure_anchor(M.flip_y(v) if hung else v, slot)
    return got["footprint"], got["anchor"]["point"]


def assert_foot(v, slot, hung, width, length, x, z):
    fp, point = measure(v, slot, hung)
    assert fp["foot_width_m"] == pytest.approx(width, abs=2e-4), fp
    assert fp["foot_length_m"] == pytest.approx(length, abs=2e-4), fp
    assert point[0] == pytest.approx(x, abs=2e-4), point
    assert point[1] == 0.0 and point[2] == pytest.approx(z, abs=2e-4), point


# --- the rule: a side hook is not the foot --------------------------------------------------------------------------------


@pytest.mark.parametrize("slot, hung", RAIL_SLOTS)
def test_side_hook_rung_is_skipped(slot, hung):
    # the 4 and 8 mm rungs cut the 6.2 mm hook, 13.45 mm off the mid-line (x 0.00265); the 16 mm rung is the base, 33.3 mm across
    fp, point = measure(M.side_hook_part(), slot, hung)
    assert fp["foot_width_m"] == pytest.approx(0.0333, abs=2e-4), fp  # 0.0062 without the rule
    assert fp["foot_length_m"] == pytest.approx(0.1162, abs=2e-4), fp  # the hook is the long part of the slab: unchanged
    assert 2.0 <= fp["foot_width_m"] / RUN_WIDTH_M <= 2.1, fp  # 2.03; 0.378 without the rule
    assert abs(point[0] - 0.00265) < 1 * MM, point  # the anchor within 1 mm of the mid-line (0.0161 without the rule)


# --- guards: they pass without the rule, and must still pass with it ---------------------------------------------------------


@pytest.mark.parametrize("slot, hung", RAIL_SLOTS)
def test_pad_rung_on_the_mid_line_is_unchanged(slot, hung):
    # a 9.5 mm pad on the mid-line: narrower than any run, but it holds the mid-line and is not a lip, so rung 0 stays
    assert_foot(M.narrow_pad_on_mid_line(), slot, hung, width=0.0095, length=0.060, x=0.0, z=0.0)


@pytest.mark.parametrize("slot, hung", RAIL_SLOTS)
def test_true_narrow_lip_on_the_mid_line_keeps_ladder_behaviour(slot, hung):
    # the ridge holds the mid-line and is a lip (1a): one rung deeper, as today; a rule that skipped every rung narrower than the run fails here
    assert_foot(M.lip_on_mid_line(), slot, hung, width=0.021, length=0.050, x=0.0, z=0.010)


@pytest.mark.parametrize("slot, hung", RAIL_SLOTS)
def test_no_rung_holds_the_mid_line_falls_back(slot, hung):
    # all three slabs lie on one side of the mid-line: today's ladder (rung 0, 6 mm), not the deepest rung (14 mm)
    assert_foot(M.no_rung_holds_the_mid_line(), slot, hung, width=0.006, length=0.060, x=0.025, z=0.0)


# --- the scope (errata E3-Q7): other slots keep today's footprint ----------------------------------------------------------


@pytest.mark.parametrize("slot, hung", NON_RAIL_SLOTS)
def test_non_rail_slot_part_keeps_its_footprint(slot, hung):
    # the same side-hook mesh: the 6.2 mm hook, centred x 0.0161, 116.2 mm long, exactly as the 1a ladder reads it
    assert_foot(M.side_hook_part(), slot, hung, width=0.0062, length=0.1162, x=0.0161, z=0.0)
