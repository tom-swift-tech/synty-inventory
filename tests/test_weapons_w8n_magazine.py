"""W8n item 2: magazines (docs/weapon_attachments.md 13.7 A6-3).

(i) A magazine whose smaller body side (``min(length_m, width_m)``) reaches ``attach_compat.drum_min_m`` (0.11 m) reads the ``drum`` row of
``attach_affinity`` (smg, rifle, shotgun, lmg), whatever its name or its classified kind; the record's ``kind`` is untouched.
(ii) A non-twin, non-override magazine whose ``foot_length_m / span_m`` is under ``attach_compat.fit_span_min`` (0.75) is not listed; a part or a
seat without the number is not judged.

Pure ``compat.candidate`` cases first (the boundaries), then a built directory (``w8n_world.mag_world``: three hosts with a 0.15 m well, four
magazines). Every expected value is a LITERAL.
"""

from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8n_world", FIX / "w8n_world.py")
N = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(N)
W = N.W

from synty_inventory.weapons import compat  # noqa: E402
from synty_inventory.weapons.rules import attachment_rules, load_rules, validate_rules  # noqa: E402

TABLES = attachment_rules(load_rules())
PARAMS = compat._params(TABLES)
AFFINITY = TABLES["attach_affinity"]
SAME, CROSS = "same_pack_fit", "cross_pack_fit"


def part(foot=0.12, body_min=0.02, pack="P", **kw):
    base = {"id": f"{pack}/Zulu_Mag_01", "pack": pack, "slot": "magazine", "kind": "standard", "flags": set(), "tokens": frozenset({"zulu"}),
            "foot_length_m": foot, "mate_d_m": None, "setting": ("setting", "s"), "body_min_m": body_min}
    return {**base, **kw}


def host(span=0.15, archetype="rifle", pack="P", **kw):
    seat = {"source": "child_node", "span_m": span, "span_source": "child_foot", "bore_d_m": None, "bore_source": None, "occupied_by": ["Mag"],
            "reason": None}
    base = {"id": f"{pack}/Zulu_Host_01", "pack": pack, "archetype": archetype, "flags": set(), "mounts": {"magazine": seat},
            "tokens": frozenset({"zulu"}), "setting": ("setting", "s")}
    return {**base, **kw}


def cand(p, h, *, verdict=None, twin=False):
    return compat.candidate(p, h, verdict=verdict, twin=twin, affinity=AFFINITY, params=PARAMS)


def test_the_shipped_numbers_are_the_specified_literals():
    assert TABLES["attach_compat"]["drum_min_m"] == 0.11 and TABLES["attach_compat"]["fit_span_min"] == 0.75
    assert PARAMS["drum_min_m"] == 0.11 and PARAMS["fit_span_min"] == 0.75
    assert validate_rules(load_rules()) == []


# -- (ii) the lower bound, pure ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("foot", "span", "listed"), [
    (0.09, 0.15, False),      # 0.60
    (0.10, 0.15, False),      # 0.667
    (0.1124, 0.15, False),    # 0.7493
    (0.12, 0.15, True),       # 0.80
    (0.15, 0.15, True),       # 1.0
    (0.375, 0.50, True),      # exactly 0.75: the bound is a floor (the ratio must be under it to be vetoed)
])
def test_a_same_pack_magazine_under_three_quarters_of_the_well_is_not_listed(foot, span, listed):
    got = cand(part(foot=foot), host(span=span))
    assert (got is not None and got["listed"] and got["tier"] == SAME) is listed, (foot, span)
    assert (got is None) is (not listed)  # not pending either: the pair is gone


def test_a_cross_pack_magazine_is_judged_by_the_same_bound():
    assert cand(part(foot=0.09, pack="Q"), host(span=0.15)) is None
    got = cand(part(foot=0.12, pack="Q"), host(span=0.15))
    assert got["tier"] == CROSS and got["listed"]


def test_a_twin_and_an_override_are_never_vetoed_by_the_bound():
    assert cand(part(foot=0.045), host(span=0.15), twin=True)["tier"] == "twin"   # 0.30
    assert cand(part(foot=0.045), host(span=0.15), verdict="add")["tier"] == "override"
    assert cand(part(foot=0.045, pack="Q"), host(span=0.15), verdict="add")["tier"] == "override"


def test_a_pair_without_a_foot_or_a_span_is_not_judged():
    assert cand(part(foot=None), host(span=0.15))["tier"] == SAME
    assert cand(part(foot=0.045), host(span=None))["tier"] == SAME
    no_seat = host(span=None)
    no_seat["mounts"]["magazine"] = {"source": "none", "reason": "no_child_no_probe", "span_m": None}
    assert cand(part(foot=0.045), no_seat) == {"host": "P/Zulu_Host_01", "tier": SAME, "listed": False}  # pending as before


def test_the_bound_is_for_the_magazine_slot_only():
    underbarrel = part(foot=0.03, kind="foregrip", slot="underbarrel")
    h = host(span=0.15)
    h["mounts"] = {"underbarrel": h["mounts"]["magazine"]}
    assert cand(underbarrel, h)["listed"]  # 0.20, listed all the same


def test_the_bound_is_a_parameter():
    params = dict(PARAMS, fit_span_min=0.5)
    assert compat.candidate(part(foot=0.09), host(span=0.15), verdict=None, twin=False, affinity=AFFINITY, params=params)["tier"] == SAME   # 0.60
    params = dict(PARAMS, fit_span_min=0.9)
    assert compat.candidate(part(foot=0.12), host(span=0.15), verdict=None, twin=False, affinity=AFFINITY, params=params) is None   # 0.80


# -- (i) the drum by shape, pure ---------------------------------------------------------------------------------------------


def test_a_magazine_thick_on_both_sides_reads_the_drum_row():
    # a pistol is in the standard row, not in the drum row (smg, rifle, shotgun, lmg)
    assert cand(part(foot=0.15, body_min=0.10), host(archetype="pistol"))["tier"] == SAME
    assert cand(part(foot=0.15, body_min=0.12), host(archetype="pistol")) is None
    assert cand(part(foot=0.15, body_min=0.12), host(archetype="rifle"))["tier"] == SAME
    assert cand(part(foot=0.15, body_min=0.12), host(archetype="sniper")) is None


def test_the_drum_threshold_is_inclusive_at_0_11():
    assert cand(part(foot=0.15, body_min=0.11), host(archetype="pistol")) is None
    assert cand(part(foot=0.15, body_min=0.1099), host(archetype="pistol"))["tier"] == SAME


def test_a_part_without_a_body_size_and_other_slots_are_not_drums():
    assert cand(part(foot=0.15, body_min=None), host(archetype="pistol"))["tier"] == SAME
    scope = part(foot=0.15, body_min=0.12, kind="scope", slot="optic")
    h = host(archetype="pistol")
    h["mounts"] = {"optic": h["mounts"]["magazine"]}
    assert cand(scope, h) == cand(dict(scope, body_min_m=0.02), h)  # a body size changes nothing outside the magazine slot


def test_the_drum_number_is_a_parameter():
    params = dict(PARAMS, drum_min_m=0.2)
    assert compat.candidate(part(foot=0.15, body_min=0.12), host(archetype="pistol"), verdict=None, twin=False, affinity=AFFINITY,
                            params=params)["tier"] == SAME


# -- a built directory ------------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    directory, _, _, _ = W.build(tmp_path_factory.mktemp("w8n_mag"), N.mag_world())
    return W.by_id(directory)


def listed(by, name) -> dict:
    att = by[N.pid(name)]["attachment"]
    return {"compatible": {e["host"].split("/", 1)[1]: (e["tier"], e["score"]) for e in att["compatible_hosts"]},
            "pending": [e["host"].split("/", 1)[1] for e in att["pending_hosts"]]}


def test_the_fixture_is_what_the_comments_say(built):
    for host_name, archetype in ((N.MAG_RIFLE, "rifle"), (N.MAG_PISTOL, "pistol"), (N.MAG_SNIPER, "sniper")):
        m = built[N.pid(host_name)]["geometry"]["mounts"]["magazine"]
        assert built[N.pid(host_name)]["archetype"] == archetype
        assert m["source"] == "child_node" and m["span_m"] == pytest.approx(0.15, abs=0.001) and m["span_source"] == "child_foot"
    for name, foot, body_min in ((N.MAG_DRUM, 0.13, 0.12), (N.MAG_SLIM, 0.13, 0.02), (N.MAG_BOARD, 0.09, 0.02), (N.MAG_FAIR, 0.12, 0.02)):
        fp = built[N.pid(name)]["attachment"]["footprint"]
        assert fp["foot_length_m"] == pytest.approx(foot, abs=0.0006) and min(fp["length_m"], fp["width_m"]) == pytest.approx(body_min, abs=0.0006)


def test_the_drum_shaped_magazine_lists_on_the_drum_row_only_and_keeps_its_kind(built):
    assert built[N.pid(N.MAG_DRUM)]["attachment"]["kind"] == "standard"  # the record is unchanged
    assert listed(built, N.MAG_DRUM) == {"compatible": {N.MAG_RIFLE: ("same_pack_fit", 0.8)}, "pending": []}  # not the pistol, not the sniper


def test_the_slim_magazine_lists_on_the_standard_row(built):
    assert listed(built, N.MAG_SLIM) == {
        "compatible": {N.MAG_PISTOL: ("same_pack_fit", 0.8), N.MAG_RIFLE: ("same_pack_fit", 0.8), N.MAG_SNIPER: ("same_pack_fit", 0.8)},
        "pending": []}


def test_a_magazine_at_60_percent_of_the_well_lists_nowhere_and_one_at_80_percent_does(built):
    assert listed(built, N.MAG_BOARD) == {"compatible": {}, "pending": []}   # 0.09 / 0.15
    assert sorted(listed(built, N.MAG_FAIR)["compatible"]) == [N.MAG_PISTOL, N.MAG_RIFLE, N.MAG_SNIPER]   # 0.12 / 0.15


def test_the_bound_off_lists_the_board_magazine_again(tmp_path):
    rules = W.sight_rules()
    rules["attachment_rules"]["attach_compat"]["fit_span_min"] = 0.0
    assert validate_rules(rules) == []
    by = W.by_id(W.build(tmp_path, N.mag_world(), rules=rules)[0])
    assert sorted(listed(by, N.MAG_BOARD)["compatible"]) == [N.MAG_PISTOL, N.MAG_RIFLE, N.MAG_SNIPER]


def test_an_override_still_lists_the_board_magazine_on_a_host(tmp_path):
    ovr = W.overrides_doc(ids={N.pid(N.MAG_BOARD): {"compatible": {"add": [N.pid(N.MAG_PISTOL)]}}})
    by = W.by_id(W.build(tmp_path, N.mag_world(), overrides=ovr)[0])
    assert listed(by, N.MAG_BOARD)["compatible"] == {N.MAG_PISTOL: ("override", 1.0)}


def test_the_rules_validation_rejects_a_malformed_magazine_number():
    for key, bad in (("drum_min_m", 0.0), ("drum_min_m", 1.5), ("drum_min_m", "big"), ("fit_span_min", -0.1), ("fit_span_min", 1.5),
                     ("fit_span_min", True)):
        rules = deepcopy(load_rules())
        rules["attachment_rules"]["attach_compat"][key] = bad
        errors = validate_rules(rules)
        assert errors and any(key in e for e in errors), (key, bad, errors)
