"""E3 coverage (S11 findings 7 and 13): three gaps left open after E3, test-only, no code under test changes.

* (a) A§4.6 gate 6(c) on a LONG run. The only proof so far is tests/test_weapons_g1_seats.py on a 0.188 m run (the seat point is the centre of the whole
  run there). On a run of 0.20 m or more the seat point is the centre of the REARMOST 0.20 m (spec 3.4 step 4), not of the run, so the span, centred on
  that point, no longer lines up with the run; the sight clip (``fit_geometry.rail_slot.clipped``, spec 3.4 step 4) is what has to keep it off a front
  sight. The gate is the test's own twin of ``test_weapons_w8h_probe.gate_violations`` (as tests/test_weapons_g1_seats.py:89 keeps one), adapted from
  the mount point to the seat ``f``.
* (b) The covered branch of ``fit_geometry._ref`` (spec 3.5): ``flat_run_m`` is the flat run's length when the run contains the reference contact's
  ``f`` (within 1e-9), else None; ``child_foot_length_m`` is the reference child's own span, carried as given (rounded to 1e-4).
* (c) ``clamp.ratio_min`` (errata E3.8, 1.0 to 0.69): a toothed seat whose foot is narrower than 0.69 of the run width fails the clamp under the
  SHIPPED rules, at ratios strictly between 0.30 and 0.69. tests/test_weapons_e3_clamp.py alone does not catch ``ratio_min`` lowered to 0.30 (its
  positives are 0.80, 1.5 and 3.0); S11 finding 13.

No world, GLB or pack: every host is a synthetic numpy mesh from ``fixtures/weapons/g1_rail_meshes.py`` (a made-up 23.5 mm pitch, 4 mm tooth, 17 mm rail
top), driven through ``fit_geometry.host_features`` with hand-built mounts. The hosts are in their own (f, s, u) frame (axes forward +x, up +z, so
asset x = f). Every bound is this file's own literal, worked out by hand next to it; the rail/flat detector rules are a literal copy of the spec 4.1
block (``RULES``, as tests/test_weapons_g1_bore.py), not read from ``weapon_rules.yaml``. Only the (c) cases read the shipped block, as their input.

Deliberate breaks, each on a scratch copy of the base (the full output is in the slice report):

* the sight clip removed (``clipped`` returns ``run`` for a top rail, fit_geometry.py:416): the two long-run cases of
  ``test_gate_6c_holds_on_a_long_run_only_through_the_sight_clip`` go red;
* ``covered`` forced False in ``_ref``: the inside, f0, f1 and f1-plus-slack cases go red (the beyond-f1 and no-flat cases stay green, by design);
* ``clamp.ratio_min`` 0.30 in the scratch ``weapon_rules.yaml``: the (c) cases of this file go red (and the BLOCK and digest pins, not
  ``test_weapons_e3_clamp.py``: S11 finding 13).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "weapons"))
import g1_rail_meshes as M  # noqa: E402

from synty_inventory.weapons import calibrate as FC  # noqa: E402
from synty_inventory.weapons import fit_geometry as FG  # noqa: E402
from synty_inventory.weapons.fit_rails import RailRun  # noqa: E402
from synty_inventory.weapons.mounts import none_mount  # noqa: E402
from synty_inventory.weapons.rules import attachment_rules, load_rules  # noqa: E402

# the spec 4.1 block, written out (the rail and flat detector rules below are the ones that matter here; the clamp rows are not read by (a) and (b))
RULES = {
    "slots": ["optic", "muzzle", "underbarrel", "magazine"],
    "locator": {"grid_m": 0.0005, "sample_n": 24, "hit_min": 1.0, "merge_m": 0.002},
    "rail": {
        "window_m": 0.010, "bin_m": 0.0005, "tooth_amp_min_m": 0.0008, "tooth_merge_m": 0.0025, "pitch_min_m": 0.005, "pitch_max_m": 0.040,
        "pitch_cv_max": 0.25, "tooth_min_count": 4, "tooth_h_tol_m": 0.0015, "zone": [0.15, 0.85], "default_seat_len_m": 0.20, "sight_clear_m": 0.010,
    },
    "flat": {"band_m": 0.005, "close_m": 0.015, "min_m": 0.060},
    "clamp": {"overhang_max_m": 0.010, "ratio_min": 0.69},
    "depth": {"lo_m": -0.026, "hi_m": 0.003},
    "bore": {
        "end_slab_m": 0.010, "round_min": 0.8, "circ_min": 0.75, "barrel_od_max_m": 0.060, "od_ratio": [0.85, 2.00], "inner_ratio": [0.47, 1.21],
        "axis_offset_max_m": 0.005, "axis_tilt_max_deg": 2,
    },
    "well": {"entry_depth_m": 0.002, "tol": 0.15},
    "exceptions": [],
}
AXES = {"forward": "+x", "up": "+z"}  # the meshes are in (f, s, u): asset x is f, asset y is s, asset z is u


def plain_mounts():
    """The four mounts ``host_features`` reads for a hand-built host: every slot empty, so the muzzle gives no barrel end and ``s0`` is the host's centre."""
    return {slot: none_mount("no_child_no_probe") for slot in ("muzzle", "optic", "underbarrel", "magazine")}


def features(mesh, mounts):
    return FG.host_features(RULES, axes=AXES, mounts=mounts, mesh=lambda drop: mesh, child_mesh=lambda name: None)


# -- (a) gate 6(c) on a long run -----------------------------------------------------------------------------------

# The host: 14 teeth, pitch 23.5 mm, from f 0.12. The toothed run is f0 0.12 .. f1 0.12 + 14 * 0.0235 = 0.449, so 0.329 m long (over 0.20 m). The seat point is the centre of the rearmost min(0.329, 0.20) = 0.20 m: f = 0.12 + 0.10 = 0.22, whatever the clip does.
LONG_RUN = (0.12, 0.449)
LONG_RUN_M = 0.329
LONG_HOST = M.toothed_host(n=14, pitch=0.0235, start_f=0.12)
SEAT_F = 0.22


def sight_mounts(sight_f):
    mounts = plain_mounts()
    mounts["sight_front"] = {**none_mount("x"), "source": "probe", "point": [sight_f, 0.0, 0.0], "reason": None}
    return mounts


def gate_6c(seat, sight_f):
    """The test's own twin of gate 6(c) of A§4.6 (``test_weapons_w8h_probe.gate_violations``; tests/test_weapons_g1_seats.py:89 keeps one for the mount
    point): the optic span, centred on the seat, covers the front sight. ``seat`` is the ``feats["seats"]["optic"]`` entry (``f`` and ``span_m``)."""
    return abs(sight_f - seat["f"]) <= seat["span_m"] / 2


def test_the_long_host_is_what_the_cases_say_it_is():
    # no sight at all: the whole run is the seat's span, centred (for the point) on the rearmost 0.20 m
    seat = features(LONG_HOST, plain_mounts())["seats"]["optic"]
    assert seat["feature"] == "rail_teeth" and seat["f"] == pytest.approx(SEAT_F, abs=1e-4)
    assert seat["span_m"] == pytest.approx(LONG_RUN_M, abs=1e-4) and LONG_RUN_M >= 0.20
    assert LONG_RUN[1] - LONG_RUN[0] == pytest.approx(LONG_RUN_M, abs=1e-9)


# (sight f, the span the clip leaves). The clip ends the span 0.010 m behind the sight: span = sight - 0.010 - 0.12 (0.22 and 0.25, both still over 0.20).
# The twin covers a sight within span / 2 of the seat's f 0.22. Unclipped (span 0.329) that reaches f 0.3845 and covers both sights; clipped it reaches
# 0.22 + 0.22 / 2 = 0.33 (sight 0.35) and 0.22 + 0.25 / 2 = 0.345 (sight 0.38), short of each. The sight at 0.38 sits 4.5 mm inside the unclipped reach:
# near the sight, so the clip alone keeps the span off it.
CLIPPED = [(0.35, 0.22), (0.38, 0.25)]


@pytest.mark.parametrize("sight_f, span", CLIPPED)
def test_gate_6c_holds_on_a_long_run_only_through_the_sight_clip(sight_f, span):
    seat = features(LONG_HOST, sight_mounts(sight_f))["seats"]["optic"]
    assert seat["feature"] == "rail_teeth" and seat["f"] == pytest.approx(SEAT_F, abs=1e-4)
    assert seat["span_m"] == pytest.approx(span, abs=2e-3) and seat["span_m"] >= 0.20  # still a long run after the clip
    assert not gate_6c(seat, sight_f)
    # and the span ends 10 mm behind the sight, measured from the run's rear (f0 0.12): 0.12 + span = sight - 0.010
    assert LONG_RUN[0] + seat["span_m"] == pytest.approx(sight_f - 0.010, abs=2e-3)
    # the control that makes the twin mean something: the unclipped span of this run WOULD cover the sight
    unclipped = {"f": SEAT_F, "span_m": LONG_RUN_M}
    assert gate_6c(unclipped, sight_f)


def test_a_sight_beyond_the_long_run_leaves_the_whole_run():
    # the sight (f 0.52) is 71 mm ahead of the run's front (0.449): the clip would end the span at 0.51, so nothing is cut
    seat = features(LONG_HOST, sight_mounts(0.52))["seats"]["optic"]
    assert seat["span_m"] == pytest.approx(LONG_RUN_M, abs=1e-4)
    assert not gate_6c(seat, 0.52)


# -- (b) the covered branch of fit_geometry._ref -----------------------------------------------------------------------

# A flat-top host: a 0.50 m box, top flat. With no toothed run the flat seat is the longest flat run of the detector zone (15 % to 85 % of the
# 0.50 m body): f 0.075 .. 0.425, 0.35 m long. An authored optic seat (a child node with a point and a foot span) takes its reference from it.
FLAT_HOST = M.box(0.0, 0.50, -0.020, 0.020, -0.050, 0.0)
FLAT = (0.075, 0.425)
FLAT_RUN_M = 0.35
SPAN = 0.0625  # the reference child's own foot length, as the mount carries it


def authored_mounts(contact_f, span=SPAN):
    mounts = plain_mounts()
    mounts["optic"] = {**none_mount("x"), "source": "child_node", "point": [contact_f, 0.0, 0.0], "child_node": "n", "reason": None, "span_m": span}
    return mounts


def ref_of(mesh, mounts):
    return features(mesh, mounts)["slots"]["optic"]["ref"]


# Through the public path (host_features on a synthetic host): the contact inside the run, at its rear end, at its front end
@pytest.mark.parametrize("contact_f", [0.20, 0.075, 0.425])
def test_ref_flat_run_is_the_runs_length_when_the_contact_is_inside_or_on_its_ends(contact_f):
    assert ref_of(FLAT_HOST, authored_mounts(contact_f)) == {"flat_run_m": FLAT_RUN_M, "child_foot_length_m": SPAN}


@pytest.mark.parametrize("contact_f", [0.07, 0.43])
def test_ref_flat_run_is_none_when_the_contact_is_5_mm_outside_the_run(contact_f):
    # public path: 5 mm behind f0 and 5 mm past f1, far outside the slack
    assert ref_of(FLAT_HOST, authored_mounts(contact_f)) == {"flat_run_m": None, "child_foot_length_m": SPAN}


def test_ref_without_a_flat_run_has_none_and_carries_the_child_foot_length():
    # public path: a toothed top has a toothed run, so flat_seat gives None (it takes the untoothed hosts only)
    assert ref_of(LONG_HOST, authored_mounts(0.20)) == {"flat_run_m": None, "child_foot_length_m": SPAN}


def test_ref_child_foot_length_is_none_when_the_mount_has_no_span():
    # public path: the flat run still covers the contact, the child's foot length is not known
    assert ref_of(FLAT_HOST, authored_mounts(0.20, span=None)) == {"flat_run_m": FLAT_RUN_M, "child_foot_length_m": None}


# The edge of the slack (1e-9, written out here) is not reachable through a rounded mount, so these call ``_ref`` directly with a RailRun.
def flat_run(f0=FLAT[0], f1=FLAT[1]):
    return RailRun(f0=f0, f1=f1, top_u=0.0, pitch_m=0.0, amp_m=0.0, teeth=0, width_m=0.04, toothed=False)


@pytest.mark.parametrize("contact_f", [FLAT[1] + 5e-10, FLAT[0] - 5e-10])
def test_ref_direct_a_contact_within_the_slack_of_an_end_is_covered(contact_f):
    assert FG._ref(flat_run(), contact_f, SPAN) == {"flat_run_m": FLAT_RUN_M, "child_foot_length_m": SPAN}


@pytest.mark.parametrize("contact_f", [FLAT[1] + 2e-9, FLAT[0] - 2e-9])
def test_ref_direct_a_contact_beyond_the_slack_of_an_end_is_not_covered(contact_f):
    assert FG._ref(flat_run(), contact_f, SPAN) == {"flat_run_m": None, "child_foot_length_m": SPAN}


@pytest.mark.parametrize("span, want", [(SPAN, SPAN), (0.06, 0.06), (0.06004, 0.06), (None, None)])
def test_ref_direct_no_flat_run_is_none_and_the_foot_length_is_carried(span, want):
    assert FG._ref(None, 0.2, span) == {"flat_run_m": None, "child_foot_length_m": want}


# -- (c) clamp.ratio_min, the shipped literal 0.69 ------------------------------------------------------------------------

# A toothed seat: 6 teeth on a 17 mm rail (the run's width_m is 0.017). The foot widths are chosen for the ratios foot / run width written beside them:
#   0.0085  / 0.017 = 0.50   strictly between 0.30 and 0.69: no_fit under the shipped 0.69, fit under 0.30
#   0.01156 / 0.017 = 0.68   just under 0.69: no_fit
#   0.01190 / 0.017 = 0.70   just over: fit
RUN_WIDTH = 0.017
FOOT_L = 0.06  # shorter than the run (6 * 0.0235 = 0.141 m), so only the width decides
SHIPPED = attachment_rules(load_rules())["fit_geometry"]


def toothed_feats():
    feats = features(M.toothed_host(n=6, pitch=0.0235, start_f=0.12), plain_mounts())["slots"]["optic"]
    assert feats["toothed_run"]["width_m"] == pytest.approx(RUN_WIDTH, abs=1e-4)
    return feats


def optic_part(foot_w):
    return {"anchor_measured": True, "foot_length_m": FOOT_L, "foot_width_m": foot_w}


@pytest.mark.parametrize("foot_w", [0.0085, 0.01156])
def test_clamp_a_foot_narrower_than_the_shipped_ratio_is_no_fit(foot_w):
    # ratio 0.50 and 0.68, both under 0.69: the clamp fails (no_fit on the rail_teeth evidence). With ratio_min at 0.30 the first reads fit.
    v = FG.verdict("optic", toothed_feats(), optic_part(foot_w), None, SHIPPED)
    assert (v.value, v.signals) == ("no_fit", ("rail_teeth",))


def test_clamp_a_foot_over_the_shipped_ratio_is_fit():
    v = FG.verdict("optic", toothed_feats(), optic_part(0.0119), None, SHIPPED)  # ratio 0.70
    assert (v.value, v.signals) == ("fit", ("rail_teeth",))


def ratio_obs(value):
    return {"key": "ratio", "value": value, "cls": "baked", "slot": "optic", "host": "host_a", "part": "part_a", "tags": ["optic:baked"], "seat_node": "node_a"}


def ratio_row(values):
    got = FC.calibrate([ratio_obs(v) for v in values], SHIPPED, frame_bore_max_m=0.025)  # 0.025 is geometry._FRAME_BORE_MAX_M, written out
    return got, next(r for r in got["rows"] if r["literal"] == "clamp.ratio_min")


def test_calibrate_a_toothed_positive_at_ratio_0_50_exceeds_the_shipped_literal():
    # the same shape as test_weapons_e3_clamp (the clamp row of attach-calibrate), with the positive e3_clamp lacks: 0.50, between 0.30 and 0.69
    got, row = ratio_row([0.50])
    assert (row["n"], row["observed"], row["ok"], row["covered"]) == (1, 0.5, False, True)
    assert {"literal": "clamp.ratio_min", "reason": "exceeded"} in got["failed"]


def test_calibrate_positives_at_ratio_0_75_and_up_clear_the_shipped_literal():
    got, row = ratio_row([0.75, 1.5])
    assert (row["n"], row["observed"], row["ok"]) == (2, 0.75, True)
    assert all(f["literal"] != "clamp.ratio_min" for f in got["failed"])
