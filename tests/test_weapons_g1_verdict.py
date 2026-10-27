"""G1 S2: the fit interface, the verdict tables and the digest (docs/weapon_attach_geometry.md 3.1 step 4 and 5, 3.5, 3.6, 3.7 step 3, 3.11, 4.3; AC143 digest part).

``fit_geometry.verdict`` is a pure function over host feature dicts, so nothing here needs a mesh. ``RULES`` below is the ``fit_geometry`` block of
spec 4.1 written out as a literal, and every bound a test uses is its own literal worked out by hand (the 0.010 overhang, the [0.85, 2.00] band, the
0.15 well tolerance), never read from the rules file or from a constant under test. A test that wants a different tolerance builds its own dict, which
also proves the function reads its tolerances from the ``rules`` argument.

One test per row of the tables. The deliberate break each row must fail on (run in a scratch copy, reported with the slice):

* an unmeasured anchor gives ``unverified``: the anchor test dropped, so a part with no anchor is judged;
* ``seat_ref`` uses the flat run, or the child's own foot length: the child's foot length used even where a flat run covers the contact (or the
  flat run used on a stepped seat);
* width is not checked on ``seat_ref``: ``clamp.ratio_min`` applied on a reference seat;
* no barrel end gives ``no_fit``: a missing barrel end passed on;
* a null ``mate_d_m`` gives ``unverified``: a null read as 0 (``no_fit``);
* the inner-ring band applies only when a ring exists: a missing ring read as 0 (``no_fit``);
* an empty section gives ``unverified`` with signal ``drum``: the empty section judged ``no_fit``;
* no seat and no feature gives ``not_judged``: the empty host judged ``no_fit``;
* the clamp overhang read from the wrong key, or dropped: the overhang edge rows.
"""

from __future__ import annotations

import inspect
import json
import os
import random
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from synty_inventory.weapons import fit_bore, fit_geometry, fit_locate, fit_rails, fit_types, fit_well
from synty_inventory.weapons.fit_geometry import fit_digest, verdict

SRC = str(Path(__file__).resolve().parent.parent / "src")

# the attachment_rules.fit_geometry block of spec 4.1, as a literal
RULES = {
    "slots": ["optic", "muzzle", "underbarrel", "magazine"],
    "locator": {"grid_m": 0.0005, "sample_n": 24, "hit_min": 1.0, "merge_m": 0.002},
    "rail": {
        "window_m": 0.010, "bin_m": 0.0005, "tooth_amp_min_m": 0.0008, "tooth_merge_m": 0.0025, "pitch_min_m": 0.005, "pitch_max_m": 0.040,
        "pitch_cv_max": 0.25, "tooth_min_count": 4, "tooth_h_tol_m": 0.0015, "zone": [0.15, 0.85], "default_seat_len_m": 0.20, "sight_clear_m": 0.010,
    },
    "flat": {"band_m": 0.005, "close_m": 0.015, "min_m": 0.060},
    "clamp": {"overhang_max_m": 0.010, "ratio_min": 1.0},
    "depth": {"lo_m": -0.026, "hi_m": 0.003},
    "bore": {
        "end_slab_m": 0.010, "round_min": 0.8, "barrel_od_max_m": 0.060, "od_ratio": [0.85, 2.00], "inner_ratio": [0.47, 1.21],
        "axis_offset_max_m": 0.005, "axis_tilt_max_deg": 2,
    },
    "well": {"entry_depth_m": 0.002, "tol": 0.15},
    "exceptions": [],
}


def rail_part(length=0.100, width=0.030, measured=True):
    return {"anchor_measured": measured, "foot_length_m": length, "foot_width_m": width}


def muzzle_part(mate=0.020, inner=None, measured=True):
    return {"anchor_measured": measured, "mate_d_m": mate, "device_inner_d": inner}


def mag_part(section=(0.040, 0.020), measured=True):
    return {"anchor_measured": measured, "entry_section": section}


RUN = {"length_m": 0.200, "width_m": 0.016}  # a toothed run 200 mm long with a 16 mm wide top
END = {"od_m": 0.020, "evidence": "ring"}  # a barrel end 20 mm across
WELL = {"length_m": 0.040, "width_m": 0.020}  # the reference magazine's entry section


def v(slot, feats, part, pair_seat=None, rules=RULES):
    out = verdict(slot, feats, part, pair_seat, rules)
    return out.value, out.signals


# -- vocabulary and types -----------------------------------------------------------------------------------------------------------------

def test_the_verdict_values_the_signal_vocabulary_and_the_slots_are_the_specs():
    assert fit_types.VERDICT_VALUES == ("fit", "unverified", "no_fit", "not_judged")
    assert fit_types.SIGNALS == ("rail_teeth", "seat_ref", "rail_flat", "barrel_ring", "barrel_round", "well_entry", "drum", "frame_body")
    assert fit_types.FIT_SLOTS == ("optic", "muzzle", "underbarrel", "magazine")


def test_the_verdict_type_refuses_a_value_or_a_signal_outside_the_vocabulary():
    assert fit_types.Verdict("fit", ("rail_teeth",)).signals == ("rail_teeth",)
    with pytest.raises(ValueError):
        fit_types.Verdict("maybe", ())
    with pytest.raises(ValueError):
        fit_types.Verdict("fit", ("rail",))


def test_the_types_are_the_spec_3_11_dataclasses_and_frame_vote_is_not_among_them():
    for name, fields in {
        "RailRun": ["f0", "f1", "top_u", "pitch_m", "amp_m", "teeth", "width_m", "toothed"],
        "BarrelEnd": ["centre_su", "face_f", "od_m", "evidence"],
        "WellRef": ["u_rb", "length_m", "width_m", "source"],
        "Placement": ["part", "t", "hit"],
        "Verdict": ["value", "signals"],
    }.items():
        cls = getattr(fit_types, name)
        assert list(cls.__dataclass_fields__) == fields, name
        assert cls.__dataclass_params__.frozen, name
        assert getattr(fit_geometry, name) is cls  # re-exported
    assert not hasattr(fit_types, "FrameVote") and not hasattr(fit_geometry, "FrameVote")


@pytest.mark.parametrize("module, name, params", [
    (fit_locate, "locate_by_translation", ["host_verts", "part_verts", "rules"]),
    (fit_locate, "strip", ["host_verts", "host_tris", "placements", "part_meshes"]),
    (fit_rails, "rail_runs", ["verts_fsu", "tris", "side", "s0", "rules"]),
    (fit_rails, "flat_seat", ["verts_fsu", "tris", "s0", "rules"]),
    (fit_bore, "barrel_end", ["verts_fsu", "tris", "mount", "rules"]),
    (fit_bore, "device_inner_d", ["part_verts_fsu", "anchor", "rules"]),
    (fit_well, "well_reference", ["host_verts_fsu", "host_tris", "mag_verts_fsu", "mag_tris", "rules"]),
    (fit_well, "entry_section", ["mag_verts_fsu", "mag_tris", "u_plane"]),
])
def test_each_detector_has_the_spec_signature_that_the_facade_re_exports(module, name, params):
    # G1 P1 (S3 to S6) replaced the stubs, so the S2 "still raises NotImplementedError" leg is retired; the signature, the spec citation and
    # the facade re-export stay pinned
    fn = getattr(module, name)
    assert list(inspect.signature(fn).parameters) == params
    assert "Spec 3." in (fn.__doc__ or "")
    assert getattr(fit_geometry, name) is fn


def test_verdict_and_fit_digest_have_the_spec_signatures():
    assert list(inspect.signature(verdict).parameters) == ["slot", "host_feats", "part", "pair_seat", "rules"]
    assert list(inspect.signature(fit_digest).parameters) == ["measure_records"]


# -- optic and underbarrel (3.5) ----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("slot", ["optic", "underbarrel"])
def test_a_part_inside_the_toothed_run_and_as_wide_as_its_top_fits(slot):
    assert v(slot, {"toothed_run": RUN}, rail_part(0.120, 0.030)) == ("fit", ("rail_teeth",))


def test_an_unmeasured_anchor_gives_unverified_on_a_toothed_run():
    assert v("optic", {"toothed_run": RUN}, rail_part(0.120, 0.030, measured=False)) == ("unverified", ("rail_teeth",))


def test_an_unmeasured_anchor_gives_unverified_on_a_reference_seat():
    feats = {"ref": {"flat_run_m": 0.090, "child_foot_length_m": 0.050}}
    assert v("optic", feats, rail_part(0.050, 0.030, measured=False)) == ("unverified", ("seat_ref",))


def test_a_foot_length_that_is_none_gives_unverified_even_with_the_anchor_flag_set():
    assert v("optic", {"toothed_run": RUN}, {"anchor_measured": True, "foot_length_m": None, "foot_width_m": 0.03}) == ("unverified", ("rail_teeth",))


def test_the_overhang_bound_is_inclusive_at_10_mm_and_no_fit_beyond_it():
    # the run is 0.200 m: a foot of 0.210 m is exactly 10 mm over
    assert v("optic", {"toothed_run": RUN}, rail_part(0.210, 0.030))[0] == "fit"
    assert v("optic", {"toothed_run": RUN}, rail_part(0.2105, 0.030)) == ("no_fit", ("rail_teeth",))


def test_the_overhang_is_read_from_the_rules_argument():
    wide = deepcopy(RULES)
    wide["clamp"]["overhang_max_m"] = 0.020
    assert v("optic", {"toothed_run": RUN}, rail_part(0.215, 0.030), rules=wide)[0] == "fit"
    assert v("optic", {"toothed_run": RUN}, rail_part(0.215, 0.030))[0] == "no_fit"
    tight = deepcopy(RULES)
    tight["clamp"]["overhang_max_m"] = 0.0
    assert v("optic", {"toothed_run": RUN}, rail_part(0.205, 0.030), rules=tight)[0] == "no_fit"


def test_the_clamp_ratio_bound_is_inclusive_and_a_narrower_clamp_is_no_fit():
    # the rail top is 16 mm wide and ratio_min is 1.0: a clamp underside of exactly 16 mm grips it, 15.9 mm cannot
    assert v("optic", {"toothed_run": RUN}, rail_part(0.100, 0.016))[0] == "fit"
    assert v("optic", {"toothed_run": RUN}, rail_part(0.100, 0.0159)) == ("no_fit", ("rail_teeth",))


def test_the_clamp_ratio_is_read_from_the_rules_argument():
    strict = deepcopy(RULES)
    strict["clamp"]["ratio_min"] = 1.5
    assert v("optic", {"toothed_run": RUN}, rail_part(0.100, 0.020), rules=strict)[0] == "no_fit"  # 20 mm is under 1.5 x 16 mm
    assert v("optic", {"toothed_run": RUN}, rail_part(0.100, 0.024), rules=strict)[0] == "fit"  # 24 mm is exactly 1.5 x 16 mm


def test_a_toothed_run_wins_over_an_authored_reference_seat():
    feats = {"toothed_run": RUN, "ref": {"flat_run_m": 0.500, "child_foot_length_m": 0.500}}
    assert v("optic", feats, rail_part(0.300, 0.030)) == ("no_fit", ("rail_teeth",))


def test_seat_ref_uses_the_flat_run_when_one_covers_the_reference_contact():
    # a flat run of 90 mm, the child's own foot is 50 mm: the run decides, not the child
    feats = {"ref": {"flat_run_m": 0.090, "child_foot_length_m": 0.050}}
    assert v("optic", feats, rail_part(0.099, 0.030)) == ("fit", ("seat_ref",))
    assert v("optic", feats, rail_part(0.101, 0.030)) == ("no_fit", ("seat_ref",))


def test_seat_ref_uses_the_childs_own_foot_length_on_a_stepped_seat():
    # no flat run covers the contact (flat_run_m None): the reference child's own foot of 60 mm decides
    feats = {"ref": {"flat_run_m": None, "child_foot_length_m": 0.060}}
    assert v("optic", feats, rail_part(0.070, 0.030)) == ("fit", ("seat_ref",))
    assert v("optic", feats, rail_part(0.0705, 0.030)) == ("no_fit", ("seat_ref",))


def test_width_is_not_checked_on_seat_ref():
    feats = {"ref": {"flat_run_m": 0.090, "child_foot_length_m": 0.050}}
    assert v("optic", feats, rail_part(0.080, 0.001)) == ("fit", ("seat_ref",))  # a 1 mm clamp, no calibration exists for an untoothed one
    assert v("optic", feats, {"anchor_measured": True, "foot_length_m": 0.080, "foot_width_m": None}) == ("fit", ("seat_ref",))
    assert v("optic", {"toothed_run": RUN}, rail_part(0.080, 0.001))[0] == "no_fit"  # the same part IS width-checked on a toothed run


def test_pair_seat_ref_replaces_the_hosts_reference_seat():
    host = {"ref": {"flat_run_m": 0.050, "child_foot_length_m": 0.050}}
    seat = {"ref": {"flat_run_m": 0.200, "child_foot_length_m": 0.050}}
    assert v("optic", host, rail_part(0.150, 0.030))[0] == "no_fit"
    assert v("optic", host, rail_part(0.150, 0.030), pair_seat=seat)[0] == "fit"


def test_a_flat_seat_only_gives_unverified_with_rail_flat_for_every_part():
    assert v("optic", {"flat_seat": True}, rail_part(0.100, 0.030)) == ("unverified", ("rail_flat",))
    assert v("optic", {"flat_seat": True}, rail_part(0.900, 0.001)) == ("unverified", ("rail_flat",))  # whatever its size
    assert v("optic", {"flat_seat": True}, rail_part(0.100, 0.030, measured=False)) == ("unverified", ("rail_flat",))


def test_a_flat_seat_belongs_to_the_optic_slot_only():
    assert v("underbarrel", {"flat_seat": True}, rail_part()) == ("not_judged", ())


def test_no_seat_and_no_feature_gives_not_judged():
    assert v("optic", {}, rail_part()) == ("not_judged", ())
    assert v("underbarrel", {"flat_seat": False, "toothed_run": None, "ref": None}, rail_part()) == ("not_judged", ())
    assert v("optic", {}, rail_part(measured=False)) == ("not_judged", ())  # the host decides first


def test_the_underbarrel_slot_uses_the_same_run_and_reference_tables():
    assert v("underbarrel", {"toothed_run": RUN}, rail_part(0.2105, 0.030))[0] == "no_fit"
    assert v("underbarrel", {"ref": {"flat_run_m": None, "child_foot_length_m": 0.060}}, rail_part(0.070, 0.01)) == ("fit", ("seat_ref",))


# -- muzzle (3.6) -------------------------------------------------------------------------------------------------------------------------

def test_no_barrel_end_gives_no_fit_whatever_the_part():
    assert v("muzzle", {}, muzzle_part(0.020)) == ("no_fit", ())
    assert v("muzzle", {"barrel_end": None}, muzzle_part(0.020)) == ("no_fit", ())
    assert v("muzzle", {}, muzzle_part(None, measured=False)) == ("no_fit", ())


@pytest.mark.parametrize("evidence, signal", [("ring", "barrel_ring"), ("face_ring", "barrel_ring"), ("round_section", "barrel_round")])
def test_the_signal_follows_the_evidence_of_the_barrel_end(evidence, signal):
    assert v("muzzle", {"barrel_end": {"od_m": 0.020, "evidence": evidence}}, muzzle_part(0.020)) == ("fit", (signal,))


def test_a_barrel_end_with_an_unknown_evidence_is_an_error():
    with pytest.raises(ValueError):
        verdict("muzzle", {"barrel_end": {"od_m": 0.020, "evidence": "magic"}}, muzzle_part(0.020), None, RULES)


def test_a_null_mate_d_m_gives_unverified():
    assert v("muzzle", {"barrel_end": END}, muzzle_part(None)) == ("unverified", ("barrel_ring",))


def test_an_unmeasured_anchor_gives_unverified_on_a_barrel_end():
    assert v("muzzle", {"barrel_end": END}, muzzle_part(0.020, measured=False)) == ("unverified", ("barrel_ring",))


def test_the_od_ratio_band_is_0_85_to_2_00_inclusive():
    feats = {"barrel_end": END}  # 20 mm
    assert v("muzzle", feats, muzzle_part(0.017))[0] == "fit"  # 0.85
    assert v("muzzle", feats, muzzle_part(0.0169)) == ("no_fit", ("barrel_ring",))
    assert v("muzzle", feats, muzzle_part(0.040))[0] == "fit"  # 2.00
    assert v("muzzle", feats, muzzle_part(0.0401)) == ("no_fit", ("barrel_ring",))


def test_the_od_ratio_band_is_read_from_the_rules_argument():
    narrow = deepcopy(RULES)
    narrow["bore"]["od_ratio"] = [0.95, 1.10]
    assert v("muzzle", {"barrel_end": END}, muzzle_part(0.030), rules=narrow)[0] == "no_fit"
    assert v("muzzle", {"barrel_end": END}, muzzle_part(0.021), rules=narrow)[0] == "fit"


def test_the_inner_ring_band_applies_only_when_a_ring_exists():
    feats = {"barrel_end": END}
    # a device with no inner ring is judged on the outer ratio alone
    assert v("muzzle", feats, muzzle_part(0.020, inner=None)) == ("fit", ("barrel_ring",))
    # a device with a ring must put it in [0.47, 1.21] x 20 mm = [9.4 mm, 24.2 mm]
    assert v("muzzle", feats, muzzle_part(0.020, inner=0.0094))[0] == "fit"
    assert v("muzzle", feats, muzzle_part(0.020, inner=0.0093)) == ("no_fit", ("barrel_ring",))
    assert v("muzzle", feats, muzzle_part(0.020, inner=0.0242))[0] == "fit"
    assert v("muzzle", feats, muzzle_part(0.020, inner=0.0243)) == ("no_fit", ("barrel_ring",))


def test_a_good_inner_ring_does_not_save_a_bad_outer_ratio():
    assert v("muzzle", {"barrel_end": END}, muzzle_part(0.0100, inner=0.012))[0] == "no_fit"


# -- magazine (3.7 step 3) -----------------------------------------------------------------------------------------------------------------

def test_an_identical_section_fits_with_the_well_entry_signal():
    assert v("magazine", {"well_ref": WELL}, mag_part((0.040, 0.020))) == ("fit", ("well_entry",))


def test_the_well_tolerance_is_0_15_inclusive_on_both_sides_of_both_extents():
    feats = {"well_ref": WELL}  # 40 mm x 20 mm
    for section in [(0.046, 0.020), (0.034, 0.020), (0.040, 0.023), (0.040, 0.017)]:
        assert v("magazine", feats, mag_part(section))[0] == "fit", section
    for section in [(0.0461, 0.020), (0.0339, 0.020), (0.040, 0.0231), (0.040, 0.0169)]:
        assert v("magazine", feats, mag_part(section)) == ("no_fit", ("well_entry",)), section


def test_the_well_tolerance_is_read_from_the_rules_argument():
    tight = deepcopy(RULES)
    tight["well"]["tol"] = 0.09
    assert v("magazine", {"well_ref": WELL}, mag_part((0.044, 0.020)), rules=tight)[0] == "no_fit"  # 10% in length: over 0.09
    assert v("magazine", {"well_ref": WELL}, mag_part((0.044, 0.020)))[0] == "fit"  # and under 0.15


def test_an_empty_section_gives_unverified_with_signal_drum():
    assert v("magazine", {"well_ref": WELL}, mag_part(None)) == ("unverified", ("drum",))


def test_an_unmeasured_anchor_gives_unverified_on_a_magazine():
    assert v("magazine", {"well_ref": WELL}, mag_part((0.040, 0.020), measured=False)) == ("unverified", ("well_entry",))


def test_no_well_reference_gives_not_judged():
    assert v("magazine", {}, mag_part()) == ("not_judged", ())
    assert v("magazine", {"well_ref": None}, mag_part(None)) == ("not_judged", ())
    assert v("magazine", {"well_ref": {"length_m": 0.0, "width_m": 0.02}}, mag_part()) == ("not_judged", ())


def test_pair_seat_well_ref_replaces_the_hosts_reference():
    other = {"well_ref": {"length_m": 0.080, "width_m": 0.020}}
    assert v("magazine", {"well_ref": WELL}, mag_part((0.080, 0.020)))[0] == "no_fit"
    assert v("magazine", {"well_ref": WELL}, mag_part((0.080, 0.020)), pair_seat=other)[0] == "fit"


# -- all slots ---------------------------------------------------------------------------------------------------------------------------

def test_a_frame_conflict_host_is_not_judged_in_all_four_slots_even_with_fitting_features():
    feats = {"frame_conflict": True, "toothed_run": RUN, "barrel_end": END, "well_ref": WELL}
    parts = {"optic": rail_part(0.1, 0.03), "underbarrel": rail_part(0.1, 0.03), "muzzle": muzzle_part(0.02), "magazine": mag_part()}
    for slot, part in parts.items():
        assert v(slot, feats, part) == ("not_judged", ()), slot


def test_the_frame_body_signal_follows_the_geometry_signal_and_never_a_not_judged_verdict():
    assert v("optic", {"toothed_run": RUN, "frame_body": True}, rail_part(0.1, 0.03)) == ("fit", ("rail_teeth", "frame_body"))
    assert v("muzzle", {"barrel_end": END, "frame_body": True}, muzzle_part(0.04)) == ("fit", ("barrel_ring", "frame_body"))
    assert v("muzzle", {"barrel_end": END, "frame_body": True}, muzzle_part(0.5)) == ("no_fit", ("barrel_ring", "frame_body"))
    assert v("magazine", {"well_ref": WELL, "frame_body": True}, mag_part(None)) == ("unverified", ("drum", "frame_body"))
    assert v("optic", {"frame_body": True}, rail_part()) == ("not_judged", ())
    assert v("optic", {"toothed_run": RUN, "frame_body": False}, rail_part(0.1, 0.03)) == ("fit", ("rail_teeth",))


def test_a_slot_outside_the_four_or_outside_the_rules_slots_is_an_error():
    with pytest.raises(ValueError):
        verdict("laser_light", {}, {}, None, RULES)
    only_optic = deepcopy(RULES)
    only_optic["slots"] = ["optic"]
    with pytest.raises(ValueError):
        verdict("muzzle", {"barrel_end": END}, muzzle_part(), None, only_optic)


def test_every_verdict_is_from_the_vocabulary_over_a_grid_of_inputs():
    values = {"fit", "unverified", "no_fit", "not_judged"}
    signals = {"rail_teeth", "seat_ref", "rail_flat", "barrel_ring", "barrel_round", "well_entry", "drum", "frame_body"}
    for slot in RULES["slots"]:
        for conflict in (False, True):
            for body in (False, True):
                for feats_extra in ({}, {"toothed_run": RUN}, {"ref": {"flat_run_m": None, "child_foot_length_m": 0.06}}, {"flat_seat": True},
                                    {"barrel_end": END}, {"barrel_end": {"od_m": 0.02, "evidence": "round_section"}}, {"well_ref": WELL}):
                    for part in (rail_part(), rail_part(measured=False), muzzle_part(), muzzle_part(None), muzzle_part(0.02, inner=0.001),
                                 mag_part(), mag_part(None), {}):
                        feats = {"frame_conflict": conflict, "frame_body": body, **feats_extra}
                        out = verdict(slot, feats, part, None, RULES)
                        assert out.value in values and set(out.signals) <= signals
                        assert out.value != "not_judged" or out.signals == ()


# -- fit_digest (4.3, AC143 digest part) ---------------------------------------------------------------------------------------------------

RECORDS = [
    {"part": "p_b", "anchor_measured": True, "foot_length_m": 0.12344999, "foot_width_m": 0.0301, "mate_d_m": None},
    {"host": "h2", "slot": "optic", "toothed_run": {"length_m": 0.1987651, "width_m": 0.0171}, "flat_seat": False, "teeth": 6},
    {"host": "h1", "slot": "muzzle", "barrel_end": {"od_m": 0.02, "evidence": "ring"}},
    {"host": "h1", "slot": "magazine", "well_ref": {"length_m": 0.04014, "width_m": 0.02}},
    {"part": "p_a", "mate_d_m": 0.02149, "device_inner_d": None, "entry_section": [0.0401, -0.0]},
]
# worked out by hand: the canonical JSON (sorted keys, no spaces, floats rounded to 1e-4, hosts by (host, slot) then parts by part)
#   [{"host":"h1","slot":"magazine","well_ref":{"length_m":0.0401,"width_m":0.02}},
#    {"barrel_end":{"evidence":"ring","od_m":0.02},"host":"h1","slot":"muzzle"},
#    {"flat_seat":false,"host":"h2","slot":"optic","teeth":6,"toothed_run":{"length_m":0.1988,"width_m":0.0171}},
#    {"device_inner_d":null,"entry_section":[0.0401,0.0],"mate_d_m":0.0215,"part":"p_a"},
#    {"anchor_measured":true,"foot_length_m":0.1234,"foot_width_m":0.0301,"mate_d_m":null,"part":"p_b"}]
# and its sha256, first 16 hex characters:
RECORDS_DIGEST = "2258ea634fd3d152"


def test_the_digest_of_a_synthetic_record_list_is_a_literal():
    assert fit_digest(RECORDS) == RECORDS_DIGEST


def test_the_digest_does_not_depend_on_the_order_of_the_records_or_of_their_keys():
    for seed in range(5):
        shuffled = [dict(sorted(r.items(), reverse=bool(seed % 2))) for r in RECORDS]
        random.Random(seed).shuffle(shuffled)
        assert fit_digest(shuffled) == RECORDS_DIGEST


def test_measures_are_rounded_to_1e_4_so_a_tenth_of_a_unit_does_not_move_the_digest_but_a_unit_does():
    nudged = deepcopy(RECORDS)
    nudged[1]["toothed_run"]["length_m"] = 0.19879  # still 0.1988 at 1e-4
    assert fit_digest(nudged) == RECORDS_DIGEST
    nudged[1]["toothed_run"]["length_m"] = 0.1989
    assert fit_digest(nudged) != RECORDS_DIGEST


def test_a_negative_zero_hashes_as_zero_and_a_non_finite_measure_is_refused():
    flipped = deepcopy(RECORDS)
    flipped[4]["entry_section"] = [0.0401, 0.0]
    assert fit_digest(flipped) == RECORDS_DIGEST
    flipped[4]["entry_section"] = [0.0401, float("nan")]
    with pytest.raises(ValueError):
        fit_digest(flipped)


def test_a_record_must_be_a_host_record_or_a_part_record():
    with pytest.raises(ValueError):
        fit_digest([{"host": "h", "part": "p", "slot": "optic"}])
    with pytest.raises(ValueError):
        fit_digest([{"slot": "optic"}])


def test_the_digest_is_16_hex_characters_and_an_empty_list_has_one():
    out = fit_digest([])
    assert len(out) == 16 and set(out) <= set("0123456789abcdef")


_CHILD = """
import json, sys
sys.path.insert(0, sys.argv[1])
from synty_inventory.weapons.fit_geometry import fit_digest
print(fit_digest(json.loads(sys.argv[2])))
"""


@pytest.mark.parametrize("seed", ["0", "1"])
def test_the_digest_is_the_same_literal_under_pythonhashseed_0_and_1(seed):
    env = {**os.environ, "PYTHONHASHSEED": seed}
    out = subprocess.run([sys.executable, "-c", _CHILD, SRC, json.dumps(RECORDS)], capture_output=True, text=True, env=env, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == RECORDS_DIGEST
