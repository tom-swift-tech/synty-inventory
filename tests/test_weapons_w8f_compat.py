"""W8f: the pure rules of the twin evidence in ``compat`` (docs/weapon_attachments.md 3.4 step 3a, 4.3, 5.1, amendment A1).

Hand-made records and ``child_extents`` (no files, no GLBs): which child a twin matches, what a carried part keeps, and the exact
conditions under which the forward correction applies or stays out. Every number is a literal.
"""

from __future__ import annotations

import copy

import pytest

from synty_inventory.weapons import compat
from synty_inventory.weapons.rules import load_rules

FWD, BACK, RIGHT, UP, DOWN = [0.0, 0.0, 1.0], [0.0, 0.0, -1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, -1.0, 0.0]
SCOPE_EXT = [0.06, 0.08, 0.2]  # sorted extents of the scope used throughout


def mount(forward=FWD, occupied=("Scope",), **kw):
    base = {"source": "child_node", "point": [0.0, 0.1, 0.0], "forward": forward, "up": UP, "span_m": 0.06,
            "span_source": "child_foot", "bore_d_m": None, "bore_source": None, "occupied_by": sorted(occupied),
            "child_node": sorted(occupied)[0] if occupied else None, "confidence": 0.9, "reason": None}
    return {**base, **kw}


def host(name, mounts, *, pack="P"):
    return {"id": f"{pack}/{name}", "pack": pack, "asset_id": name, "role": "whole", "kind": "ranged", "hold_class": "long_gun",
            "archetype": "rifle", "flags": [], "attachment": None, "geometry": {"mounts": mounts},
            "review": {"confidence": 0.9, "reasons": []}}


def part(name="Scope_01", *, slot="optic", forward=BACK, up=UP, length=0.2, width=0.06, height=0.08, foot_length=0.06, foot_width=0.02,
         source="section", symmetric=False, pack="P"):
    anchor = {"point": [0.005, 0.0, -0.05], "forward": forward, "up": up, "foot_source": "authored_up", "forward_source": source,
              "symmetric": symmetric}
    footprint = {"length_m": length, "width_m": width, "height_m": height, "foot_length_m": foot_length, "foot_width_m": foot_width,
                 "mate_d_m": None}
    return {"id": f"{pack}/{name}", "pack": pack, "asset_id": name, "role": "part", "kind": None, "hold_class": "none",
            "archetype": "unknown", "flags": [], "geometry": None,
            "attachment": {"slot": slot, "kind": "scope", "anchor": anchor, "footprint": footprint, "compatible_hosts": [],
                           "pending_hosts": []},
            "review": {"confidence": 0.9, "reasons": ["colourway_unknown"]}}


def child(extents=SCOPE_EXT, axes=(0.06, 0.08, 0.2), seat=None):
    return {"extents": list(extents), "axes": list(axes), "seat": seat}


def evidence(host_rec, slot="optic", **nodes):
    return {host_rec["id"]: {slot: nodes}}


# --- matched_child: the closest sorted extents, the lower name on a tie -------------------------------------------------


def test_the_closest_sorted_extents_win_even_when_a_lower_named_child_also_matches():
    rows = {"A_Scope": child([0.0615, 0.0805, 0.2005]), "Z_Scope": child(SCOPE_EXT)}  # both within max(3 %, 0.8 mm)
    assert compat.matched_child(SCOPE_EXT, rows) == "Z_Scope"


def test_the_lower_node_name_breaks_a_tie_and_a_child_out_of_tolerance_is_no_match():
    rows = {"B_Scope": child(), "A_Scope": child(), "C_Scope": child([0.07, 0.08, 0.2])}
    assert compat.matched_child(SCOPE_EXT, rows) == "A_Scope"
    assert compat.matched_child(SCOPE_EXT, {"C_Scope": child([0.07, 0.08, 0.2])}) is None  # 0.07 is 15 % off
    assert compat.matched_child(SCOPE_EXT, {}) is None


# --- compute: `replaces` of a twin entry -------------------------------------------------------------------------------


def entries(records, **kw):
    got = compat.compute(records, load_rules(), None, **kw)
    return got["parts"]["P/Scope_01"]["compatible"]


def test_a_twin_entry_names_the_closest_matching_child_and_a_tie_the_lower_name():
    h = host("Gun_01", {"optic": mount(occupied=("A_Scope", "Z_Scope"))})
    p = part(forward=FWD)
    rows = {"A_Scope": child([0.0615, 0.0805, 0.2005]), "Z_Scope": child(SCOPE_EXT)}
    [e] = entries([h, p], child_extents=evidence(h, **rows))
    assert (e["tier"], e["replaces"]) == ("twin", ["Z_Scope"])
    [e] = entries([h, p], child_extents=evidence(h, B_Scope=child(), A_Scope=child()))
    assert e["replaces"] == ["A_Scope"]


def test_a_twin_of_a_one_child_slot_replaces_that_child():
    h = host("Gun_01", {"optic": mount(occupied=("Scope",))})
    [e] = entries([h, part()], child_extents=evidence(h, Scope=child()))
    assert (e["tier"], e["replaces"]) == ("twin", ["Scope"])


def test_a_carried_twin_keeps_the_previous_single_name_else_the_copy_of_occupied_by():
    h = host("Gun_01", {"optic": mount(occupied=("A_Scope", "B_Scope"))})
    p = part()
    [e] = entries([h, p], prev_twins={("P/Scope_01", "P/Gun_01"): ["B_Scope"]})  # no evidence for the host: the stored name stays
    assert (e["tier"], e["replaces"]) == ("twin", ["B_Scope"])
    for previous in (["A_Scope", "B_Scope"], []):
        [e] = entries([h, p], prev_twins={("P/Scope_01", "P/Gun_01"): previous})
        assert (e["tier"], e["replaces"]) == ("twin", ["A_Scope", "B_Scope"])


def test_a_part_that_is_not_a_twin_replaces_the_whole_slot_as_before():
    h = host("Gun_01", {"optic": mount(occupied=("A_Scope", "B_Scope"))})
    p = part("Scope_01", length=0.3)  # sorted extents 0.06 / 0.08 / 0.3: not a twin of either child
    added = {"schema": "weapon-overrides/1", "globs": {}, "ids": {"P/Scope_01": {"compatible": {"add": ["P/Gun_01"]}}}}
    got = compat.compute([h, p], load_rules(), added, child_extents=evidence(h, A_Scope=child(), B_Scope=child()))["parts"]["P/Scope_01"]
    [e] = got["compatible"]
    assert (e["tier"], e["replaces"]) == ("override", ["A_Scope", "B_Scope"])  # only a `twin` entry names its one child


# --- twin_forward: when the correction applies -------------------------------------------------------------------------


def corrected(records, ext):
    ids = compat.twin_forward(records, ext)
    return ids


def test_a_reversed_part_gets_its_hosts_forward_and_nothing_else_changes():
    h, p = host("Gun_01", {"optic": mount()}), part()
    before = copy.deepcopy(p)
    assert corrected([h, p], evidence(h, Scope=child())) == ["P/Scope_01"]
    a = p["attachment"]["anchor"]
    assert (a["forward"], a["forward_source"], a["symmetric"]) == (FWD, "twin", False)
    assert {k: a[k] for k in ("point", "up", "foot_source")} == {k: before["attachment"]["anchor"][k] for k in ("point", "up", "foot_source")}
    assert p["attachment"]["footprint"] == before["attachment"]["footprint"]  # a sign flip changes no number
    assert p["review"] == before["review"]  # confidence and reasons are never touched


def test_a_change_of_axis_swaps_length_with_width_and_foot_length_with_foot_width():
    # a drum measured along x (0.14 long, 0.11 wide) on a host that points along z; magazine up is -y
    h = host("Gun_01", {"magazine": mount(up=DOWN, occupied=("Drum",))})
    p = part("Drum_01", slot="magazine", forward=RIGHT, up=DOWN, length=0.14, width=0.11, height=0.09, foot_length=0.14,
             foot_width=0.11, source="authored", symmetric=True)
    ext = evidence(h, "magazine", Drum=child([0.09, 0.11, 0.14], axes=(0.14, 0.09, 0.11)))
    assert corrected([h, p], ext) == ["P/Drum_01"]
    a, f = p["attachment"]["anchor"], p["attachment"]["footprint"]
    assert (a["forward"], a["forward_source"], a["symmetric"], a["up"]) == (FWD, "twin", False, DOWN)
    assert (f["length_m"], f["width_m"], f["height_m"], f["foot_length_m"], f["foot_width_m"]) == (0.11, 0.14, 0.09, 0.11, 0.14)
    assert p["review"]["confidence"] == 0.9 and p["review"]["reasons"] == ["colourway_unknown"]


def test_applying_the_correction_twice_changes_nothing_more():
    h, p = host("Gun_01", {"optic": mount()}), part()
    ext = evidence(h, Scope=child())
    corrected([h, p], ext)
    once = copy.deepcopy(p)
    assert corrected([h, p], ext) == [] and p == once


@pytest.mark.parametrize("tweak", ["override", "muzzle", "no_footprint", "unmeasured"])
def test_the_correction_stays_out_for_an_override_a_muzzle_device_and_an_unmeasured_part(tweak):
    h, p = host("Gun_01", {"optic": mount(), "muzzle": mount(occupied=("Scope",), source="probe", child_node=None)}), part()
    ext = evidence(h, Scope=child())
    if tweak == "override":
        p["attachment"]["anchor"]["forward_source"] = "override"
    elif tweak == "muzzle":
        p["attachment"]["slot"] = "muzzle"
        ext = evidence(h, "muzzle", Scope=child())
    elif tweak == "no_footprint":
        p["attachment"]["anchor"] = None
        p["attachment"]["footprint"] = None
    else:
        p["attachment"] = None
    before = copy.deepcopy(p)
    assert corrected([h, p], ext) == [] and p == before


def test_two_hosts_that_disagree_leave_the_part_alone_and_two_that_agree_still_correct_it():
    a = host("Gun_01", {"optic": mount(FWD)})
    b = host("Gun_02", {"optic": mount(RIGHT)})
    c = host("Gun_03", {"optic": mount(FWD)})
    p = part()
    before = copy.deepcopy(p)
    assert corrected([a, b, p], {**evidence(a, Scope=child()), **evidence(b, Scope=child())}) == [] and p == before
    assert corrected([a, c, p], {**evidence(a, Scope=child()), **evidence(c, Scope=child())}) == ["P/Scope_01"]
    assert p["attachment"]["anchor"]["forward"] == FWD


def test_a_child_that_matches_only_when_turned_a_host_without_a_seat_and_a_vertical_forward_give_no_evidence():
    p = part()
    before = copy.deepcopy(p)
    h = host("Gun_01", {"optic": mount()})
    # sorted extents equal, per-axis extents not: the child is yawed 90 degrees against the part
    assert corrected([h, p], evidence(h, Scope=child(axes=(0.2, 0.08, 0.06)))) == [] and p == before
    # the slot has no seat on this host
    none = host("Gun_02", {"optic": {**mount(), "source": "none", "point": None, "forward": None, "up": None, "span_m": None,
                                     "span_source": None, "occupied_by": [], "child_node": None, "reason": "no_child_no_probe"}})
    assert corrected([none, p], evidence(none, Scope=child())) == [] and p == before
    # a host whose forward is the part's own up axis would make an invalid frame: never applied
    tall = host("Gun_03", {"optic": mount(UP)})
    assert corrected([tall, p], evidence(tall, Scope=child())) == [] and p == before
    # the child is not the part's size at all
    assert corrected([h, p], evidence(h, Scope=child([0.1, 0.1, 0.3], axes=(0.1, 0.1, 0.3)))) == [] and p == before


def test_a_part_that_already_has_the_hosts_forward_is_not_touched():
    h, p = host("Gun_01", {"optic": mount()}), part(forward=FWD)
    before = copy.deepcopy(p)
    assert corrected([h, p], evidence(h, Scope=child())) == [] and p == before  # the source stays `section`
