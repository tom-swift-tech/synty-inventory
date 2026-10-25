"""W8o: the three cross-pack precision rules, the tokenless family waiver and the versions (docs/weapon_attachments.md 13.8 A7-2, A7-4; AC118, AC119, AC121, AC123).

Pure ``compat.candidate`` cases (hand-made part and host views, no files), then ``compat.compute`` over hand-made records for the plumbing of the host's
baked-child extents into the candidate. Every tolerance a case relies on is passed as a LITERAL in ``params`` (``rules(...)``), never read from the
shipped table, so a change of the shipped numbers cannot loosen a case; the shipped numbers have their own test. Part sizes are scaled from the baked
child by literal factors (1.3 = 30 % off).
"""

from __future__ import annotations

from copy import deepcopy

import pytest

import synty_inventory.weapons as pkg
from synty_inventory.weapons import compat
from synty_inventory.weapons.rules import attach_rules_digest, attachment_rules, load_rules, validate_rules, weapon_rules_digest

TABLES = attachment_rules(load_rules())
AFFINITY = TABLES["attach_affinity"]
SAME, CROSS = "same_pack_fit", "cross_pack_fit"
BASE_ATTACH_DIGEST = "2f23e707292a96c3"  # attach_rules_digest(load_rules()) at base 201e2d8 (attach version 11)


def params(tol=None, never=None, tokenless=None):
    """compat params with literal A7 tables (not the shipped ones); ``None`` = the table row is absent."""
    tables = dict(TABLES)
    tables["attach_compat"] = {**TABLES["attach_compat"], "cross_pack_size_tol": {} if tol is None else tol}
    tables["cross_pack_never"] = {} if never is None else never
    tables["tokenless_family_free_slots"] = [] if tokenless is None else tokenless
    return compat._params(tables)


TOL = {"magazine": 0.35, "optic": 0.35, "underbarrel": 0.45}
NEVER = {"muzzle": ["shotgun"]}
CHILD = [0.02, 0.04, 0.10]  # the baked child's sorted extents, used by every size case


def scaled(factor, base=CHILD):
    return [round(x * factor, 6) for x in base]


def part(slot="magazine", kind="standard", *, pack="P", tokens=("zulu",), extents=None, **kw):
    base = {"id": f"{pack}/Zulu_Part_01", "pack": pack, "slot": slot, "kind": kind, "flags": set(), "tokens": frozenset(tokens),
            "foot_length_m": 0.12 if slot == "magazine" else 0.06, "mate_d_m": None, "setting": ("setting", "s"), "body_min_m": 0.02,
            "extents": extents}
    return {**base, **kw}


def seat(*, source="child_node", occupied=("Kid",), span=None, **kw):
    base = {"source": source, "span_m": span, "span_source": "child_foot" if span else None, "bore_d_m": None, "bore_source": None,
            "occupied_by": list(occupied), "reason": None if source != "none" else "no_child_no_probe"}
    return {**base, **kw}


def host(slot="magazine", *, archetype="rifle", pack="Q", mount=None, children=None, tokens=("alpha",), **kw):
    if mount is None:
        mount = seat(span=0.15 if slot == "magazine" else 0.06)
    base = {"id": f"{pack}/Host_01", "pack": pack, "archetype": archetype, "flags": set(), "mounts": {slot: mount}, "tokens": frozenset(tokens),
            "setting": ("setting", "s"), "children": {} if children is None else children}
    return {**base, **kw}


def kid(extents=CHILD, name="Kid"):
    return {name: {"extents": list(extents), "axes": list(extents), "seat": None}}


def cand(p, h, prm, *, twin=False, verdict=None):
    return compat.candidate(p, h, verdict=verdict, twin=twin, affinity=AFFINITY, params=prm)


def listed(got, tier):
    return got is not None and got["listed"] and got["tier"] == tier


# -- AC118 R-a: the size gate --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("factor", "kept"), [(1.30, True), (1.40, False), (1.80, False), (0.70, True), (0.60, False)])
def test_ac118_a_cross_pack_magazine_is_kept_30_dropped_40_and_80_percent_off_its_baked_child(factor, kept):
    got = cand(part(extents=scaled(factor)), host(children={"magazine": kid()}), params(TOL))
    assert (got is not None) is kept, factor
    if kept:
        assert listed(got, CROSS)


@pytest.mark.parametrize(("factor", "kept"), [(1.40, True), (1.50, False)])
def test_ac118_an_underbarrel_is_kept_40_and_dropped_50_percent_off(factor, kept):
    child = [0.02, 0.03, 0.20]
    p = part("underbarrel", "foregrip", extents=scaled(factor, child))
    h = host("underbarrel", children={"underbarrel": kid(child)}, mount=seat(span=0.06))
    assert (cand(p, h, params(TOL)) is not None) is kept, factor


def test_ac118_the_deviation_is_the_worst_axis_not_the_mean():
    # two axes exact, the third 40 % off
    got = cand(part(extents=[0.02, 0.04, 0.14]), host(children={"magazine": kid()}), params(TOL))
    assert got is None
    assert listed(cand(part(extents=[0.02, 0.04, 0.13]), host(children={"magazine": kid()}), params(TOL)), CROSS)


def test_ac118_an_optic_40_percent_off_is_untouched_as_a_twin_and_as_a_same_pack_fit_and_dropped_as_a_cross_pack_fit():
    child, mount = [0.06, 0.08, 0.20], seat(span=0.06)
    ext = scaled(1.4, child)
    p_same, h_same = part("optic", "scope", pack="Q", extents=ext), host("optic", children={"optic": kid(child)}, mount=mount, tokens=("zulu",))
    assert listed(cand(p_same, h_same, params(TOL)), SAME)
    assert listed(cand(p_same, h_same, params(TOL), twin=True), "twin")
    p_cross, h_cross = part("optic", "scope", pack="P", extents=ext), host("optic", children={"optic": kid(child)}, mount=mount)
    assert cand(p_cross, h_cross, params(TOL)) is None
    assert listed(cand(p_cross, h_cross, params(TOL), twin=True), "twin")  # a twin entry is never size-gated
    assert listed(cand(p_cross, h_cross, params(TOL), verdict="add"), "override")


def test_ac118_a_host_with_no_recorded_child_is_not_checked():
    far = scaled(3.0)
    assert listed(cand(part(extents=far), host(children={}), params(TOL)), CROSS)  # no children at all
    assert listed(cand(part(extents=far), host(children={"magazine": kid(name="Other")}), params(TOL)), CROSS)  # a child the seat does not name
    assert listed(cand(part(extents=far), host(mount=seat(source="probe", occupied=(), span=0.15), children={"magazine": kid()}), params(TOL)), CROSS)
    assert listed(cand(part(extents=None), host(children={"magazine": kid()}), params(TOL)), CROSS)  # a part without a footprint
    # a child with a zero extent is skipped, so it does not decide either
    assert listed(cand(part(extents=far), host(children={"magazine": kid([0.0, 0.04, 0.10])}), params(TOL)), CROSS)


def test_ac118_the_smallest_deviation_over_the_children_the_seat_names_decides():
    h = host(mount=seat(span=0.15, occupied=("A", "B")), children={"magazine": {**kid(scaled(3.0), "A"), **kid(CHILD, "B")}})
    assert listed(cand(part(extents=scaled(1.1)), h, params(TOL)), CROSS)  # B is 10 % off, A is 63 % off
    h = host(mount=seat(span=0.15, occupied=("A", "B")), children={"magazine": {**kid(scaled(3.0), "A"), **kid(scaled(2.0), "B")}})
    assert cand(part(extents=scaled(1.0)), h, params(TOL)) is None  # both far


def test_ac118_a_pending_pair_has_no_seat_and_is_not_size_checked():
    none = seat(source="none", occupied=(), span=None)
    got = cand(part(extents=scaled(3.0)), host(mount=none, children={"magazine": kid()}), params(TOL))
    assert got == {"host": "Q/Host_01", "tier": CROSS, "listed": False}


def test_ac118_a_slot_with_no_tolerance_and_a_missing_table_check_nothing():
    h = host(children={"magazine": kid()})
    assert listed(cand(part(extents=scaled(1.8)), h, params({"optic": 0.35})), CROSS)  # magazine is not a key
    assert listed(cand(part(extents=scaled(1.8)), h, params(None)), CROSS)  # the table row removed: nothing is dropped
    assert cand(part(extents=scaled(1.8)), h, params({"magazine": 0.35})) is None  # the same part with the row: dropped


def test_ac118_the_deviation_helper_has_the_specified_numbers():
    mount = seat(occupied=("A", "B", "Missing"))
    rows = {**kid([0.1, 0.2, 0.4], "A"), **kid([0.1, 0.2, 0.3], "B")}
    assert compat.child_deviation([0.11, 0.2, 0.4], mount, rows) == pytest.approx(0.1)  # A: 0.1; B: 0.33
    assert compat.child_deviation([0.1, 0.2, 0.4], mount, {}) is None
    assert compat.child_deviation(None, mount, rows) is None
    assert compat.child_deviation([0.1, 0.2, 0.4], seat(occupied=("Missing",)), rows) is None
    assert compat.child_deviation([0.1, 0.2, 0.4], None, rows) is None


def record(rec_id, *, role, archetype, geometry=None, attachment=None):
    pack, asset = rec_id.split("/")
    return {"id": rec_id, "pack": pack, "asset_id": asset, "role": role, "kind": "ranged" if role == "whole" else None,
            "hold_class": "long_gun" if role == "whole" else "none", "archetype": archetype, "flags": [], "attachment": attachment,
            "geometry": geometry, "review": {"confidence": 0.9, "reasons": []}}


def test_ac118_compute_hands_the_hosts_child_extents_and_the_parts_footprint_to_the_rule():
    mount = {"source": "child_node", "point": [0.0, 0.1, 0.0], "forward": [0, 0, 1], "up": [0, 1, 0], "span_m": 0.15, "span_source": "child_foot",
             "bore_d_m": None, "bore_source": None, "occupied_by": ["Mag"], "child_node": "Mag", "confidence": 0.9, "reason": None}
    host_rec = record("Q/Gun_Alpha_01", role="whole", archetype="rifle", geometry={"mounts": {"magazine": mount}})

    def mag(name, scale):
        foot = {"length_m": 0.04 * scale, "width_m": 0.02 * scale, "height_m": 0.10 * scale, "foot_length_m": 0.12, "foot_width_m": 0.02, "mate_d_m": None}
        anchor = {"point": [0, 0, 0], "forward": [0, 1, 0], "up": [0, 0, 1], "foot_source": "authored_up", "forward_source": "section", "symmetric": False}
        att = {"slot": "magazine", "kind": "standard", "anchor": anchor, "footprint": foot, "compatible_hosts": [], "pending_hosts": []}
        return record(f"P/{name}", role="part", archetype="unknown", attachment=att)

    rules = deepcopy(load_rules())
    rules["attachment_rules"]["attach_genre_by_pack"] = {"P": "s", "Q": "s"}
    rules["attachment_rules"]["attach_compat"]["cross_pack_size_tol"] = {"magazine": 0.35}
    evidence = {"Q/Gun_Alpha_01": {"magazine": {"Mag": {"extents": [0.02, 0.04, 0.10], "axes": [0.04, 0.02, 0.10], "seat": None}}}}
    parts = [mag("Wep_Zulu_Mag_Near", 1.3), mag("Wep_Zulu_Mag_Far", 1.4)]
    got = compat.compute([host_rec, *parts], rules, None, child_extents=evidence)["parts"]
    assert [e["tier"] for e in got["P/Wep_Zulu_Mag_Near"]["compatible"]] == [CROSS]
    assert got["P/Wep_Zulu_Mag_Far"]["compatible"] == [] and got["P/Wep_Zulu_Mag_Far"]["pending"] == []
    # no evidence for the host (a carried host without it): nothing to compare, both stay
    got = compat.compute([host_rec, *parts], rules, None, child_extents={})["parts"]
    assert [e["tier"] for e in got["P/Wep_Zulu_Mag_Far"]["compatible"]] == [CROSS]


def test_ac117_the_mount_missing_loop_counts_the_old_default_tiers_only():
    # a host whose only entry is a pending cross-pack pair must not gain `mount_missing`: DEFAULT_TIERS grew, the loop kept the old set
    assert compat.DEFAULT_PENDING_TIERS == ("override", "twin", "same_pack_fit")
    assert compat.DEFAULT_TIERS == ("override", "twin", "same_pack_fit", "cross_pack_fit")
    none = seat(source="none", occupied=(), span=None)
    host_rec = record("Q/Gun_Alpha_01", role="whole", archetype="rifle", geometry={"mounts": {"magazine": {**none, "point": None, "forward": None}}})
    foot = {"length_m": 0.04, "width_m": 0.02, "height_m": 0.10, "foot_length_m": 0.12, "foot_width_m": 0.02, "mate_d_m": None}
    anchor = {"point": [0, 0, 0], "forward": [0, 1, 0], "up": [0, 0, 1], "foot_source": "authored_up", "forward_source": "section", "symmetric": False}
    att = {"slot": "magazine", "kind": "standard", "anchor": anchor, "footprint": foot, "compatible_hosts": [], "pending_hosts": []}
    rules = deepcopy(load_rules())
    rules["attachment_rules"]["attach_genre_by_pack"] = {"P": "s", "Q": "s"}
    got = compat.compute([host_rec, record("P/Wep_Zulu_Mag_01", role="part", archetype="unknown", attachment=att)], rules)
    assert [e["tier"] for e in got["parts"]["P/Wep_Zulu_Mag_01"]["pending"]] == [CROSS]
    assert got["host_slots"] == {}  # DEFAULT_TIERS in the loop would have said {"Q/Gun_Alpha_01": {"magazine"}}


# -- AC119 R-b: the gun class ---------------------------------------------------------------------------------------------------


def mag_on(archetype, tokens, *, pack="P", seat_kind="seat", prm=None):
    mount = seat(span=0.15) if seat_kind == "seat" else seat(source="none", occupied=(), span=None)
    return cand(part(tokens=tokens, pack=pack), host(archetype=archetype, mount=mount), prm or params(TOL, NEVER))


@pytest.mark.parametrize("seat_kind", ["seat", "pending"])
def test_ac119_a_handgun_named_part_on_a_long_gun_and_the_reverse_are_not_cross_candidates(seat_kind):
    for archetype in ("rifle", "shotgun", "sniper", "lmg"):
        assert mag_on(archetype, ("zulu", "pistol"), seat_kind=seat_kind) is None, archetype
        assert mag_on(archetype, ("zulu", "revolver"), seat_kind=seat_kind) is None, archetype
    for archetype in ("pistol", "revolver"):
        for word in ("rifle", "shotgun", "sniper", "lmg", "smg"):
            assert mag_on(archetype, ("zulu", word), seat_kind=seat_kind) is None, (archetype, word)
    # the same words on a host of their own group stay candidates
    assert mag_on("pistol", ("zulu", "pistol"), seat_kind=seat_kind) is not None
    assert mag_on("pistol", ("zulu", "revolver"), seat_kind=seat_kind) is not None
    assert mag_on("rifle", ("zulu", "sniper"), seat_kind=seat_kind) is not None
    assert mag_on("lmg", ("zulu", "rifle"), seat_kind=seat_kind) is not None
    assert mag_on("smg", ("zulu", "rifle"), seat_kind=seat_kind) is not None


@pytest.mark.parametrize("seat_kind", ["seat", "pending"])
def test_ac119_a_pistol_named_part_on_an_smg_host_is_a_cross_candidate(seat_kind):
    for word in ("pistol", "revolver"):
        got = mag_on("smg", ("zulu", word), seat_kind=seat_kind)
        assert got is not None and got["tier"] == CROSS and got["listed"] is (seat_kind == "seat"), word


def test_ac119_the_class_rule_is_for_the_cross_pack_tier_only():
    # same pack with a shared family token, a twin and an override: the name of the gun class does not veto them
    p = part(tokens=("zulu", "pistol"), pack="Q")
    h = host(archetype="rifle", tokens=("zulu",))
    assert listed(cand(p, h, params(TOL, NEVER)), SAME)
    assert listed(cand(part(tokens=("zulu", "pistol")), h, params(TOL, NEVER), twin=True), "twin")
    assert listed(cand(part(tokens=("zulu", "pistol")), h, params(TOL, NEVER), verdict="add"), "override")


def test_ac119_a_part_with_no_class_word_is_not_judged():
    assert mag_on("pistol", ("zulu", "gamma")) is not None and mag_on("rifle", ("zulu", "gamma")) is not None


# -- AC119 R-c: a suppressor on a shotgun ----------------------------------------------------------------------------------------


def muzzle(archetype, *, pack="P", kind="suppressor", prm=None, ring=True, tokens=("zulu",)):
    mount = seat(source="probe", occupied=(), bore_d_m=0.02, bore_source="ring") if ring else seat(source="none", occupied=(), span=None)
    p = part("muzzle", kind, pack=pack, tokens=tokens, mate_d_m=0.02, foot_length_m=None)
    return cand(p, host("muzzle", archetype=archetype, mount=mount, tokens=("zulu",) if pack == "Q" else ("alpha",)), prm or params(TOL, NEVER))


@pytest.mark.parametrize("ring", [True, False])
def test_ac119_a_cross_pack_suppressor_on_a_shotgun_is_vetoed_listed_and_pending(ring):
    assert muzzle("shotgun", ring=ring) is None
    for archetype in ("rifle", "smg", "pistol", "sniper"):
        got = muzzle(archetype, ring=ring)
        assert got is not None and got["tier"] == CROSS and got["listed"] is ring, archetype


@pytest.mark.parametrize("ring", [True, False])
def test_ac119_the_same_pack_suppressor_on_a_shotgun_still_is_a_candidate(ring):
    got = muzzle("shotgun", pack="Q", ring=ring)
    assert got is not None and got["tier"] == SAME and got["listed"] is ring


def test_ac119_with_the_table_row_removed_the_shotgun_suppressor_is_a_cross_candidate_again():
    got = muzzle("shotgun", prm=params(TOL, None))
    assert got is not None and got["tier"] == CROSS and got["listed"]
    assert muzzle("shotgun", prm=params(TOL, {"muzzle": []})) is not None  # an empty row is no rule


def test_ac119_the_rule_is_for_the_suppressor_kind_and_the_listed_archetypes_only():
    assert muzzle("shotgun", kind="compensator") is not None  # not a suppressor
    assert muzzle("rifle", prm=params(TOL, {"muzzle": ["rifle"]})) is None  # the table decides the archetypes
    assert muzzle("shotgun", prm=params(TOL, {"optic": ["shotgun"]})) is not None  # a row of another slot


# -- AC121 A7-4: the tokenless family waiver -----------------------------------------------------------------------------------------


OPTIC_CHILD = [0.06, 0.08, 0.20]


def tokenless(factor=1.0, *, slot="optic", kind="scope", tokens=(), mount=None, children="default", archetype="rifle", prm=None):
    ext = scaled(factor, OPTIC_CHILD)
    p = part(slot, kind, pack="Q", tokens=tokens, extents=ext)
    kids = {slot: kid(OPTIC_CHILD)} if children == "default" else children
    h = host(slot, archetype=archetype, mount=mount if mount is not None else seat(span=0.06), children=kids)
    return cand(p, h, prm or params(TOL, NEVER, ["optic"]))


def test_ac121_a_tokenless_optic_on_a_child_seat_within_the_tolerance_is_a_listed_same_pack_fit():
    for factor in (1.0, 1.30, 0.70):
        got = tokenless(factor)
        assert got is not None and got["tier"] == SAME and got["listed"] and "family_overlap" not in got["signals"], factor


def test_ac121_a_tokenless_optic_beyond_the_tolerance_is_absent():
    for factor in (1.5, 1.8, 0.4):
        assert tokenless(factor) is None, factor


def test_ac121_without_a_seat_it_is_absent_and_not_pending():
    assert tokenless(mount=seat(source="none", occupied=(), span=None)) is None
    assert tokenless(mount=seat(source="probe", occupied=(), span=0.06)) is None  # a probe seat is no child seat
    assert tokenless(children={}) is None  # a child seat with no recorded child
    assert tokenless(children={"optic": kid(OPTIC_CHILD, "Other")}) is None


def test_ac121_a_tokenless_magazine_and_laser_light_are_absent():
    assert tokenless(slot="magazine", kind="standard", mount=seat(span=0.15)) is None
    assert tokenless(slot="laser_light", kind="laser", mount=seat(span=0.06)) is None


def test_ac121_a_named_optic_that_fails_the_family_test_is_absent_and_a_named_one_that_passes_is_unchanged():
    assert tokenless(tokens=("zulu",)) is None  # the host's tokens are {alpha}
    p = part("optic", "scope", pack="Q", tokens=("alpha",), extents=scaled(1.8, OPTIC_CHILD))
    h = host("optic", mount=seat(span=0.06), children={"optic": kid(OPTIC_CHILD)})
    assert listed(cand(p, h, params(TOL, NEVER, ["optic"])), SAME)  # family_overlap holds: no size gate on a named same-pack part


def test_ac121_the_waiver_needs_its_table_row_and_the_slots_tolerance_and_keeps_affinity():
    assert tokenless(prm=params(TOL, NEVER, None)) is None  # row removed
    assert tokenless(prm=params(TOL, NEVER, ["magazine"])) is None  # the slot is not in the row
    assert tokenless(prm=params(None, NEVER, ["optic"])) is None  # no tolerance for the slot: no waiver
    assert tokenless(prm=params({"magazine": 0.35}, NEVER, ["optic"])) is None
    assert tokenless(kind="sniper_scope", archetype="pistol") is None  # affinity still decides
    assert tokenless(1.3, prm=params({"optic": 0.5}, NEVER, ["optic"])) is not None
    assert tokenless(1.4, prm=params({"optic": 0.3}, NEVER, ["optic"])) is None


def test_ac121_a_tokenless_part_on_another_pack_is_still_a_cross_pack_candidate_under_the_size_gate():
    ext = scaled(1.3, OPTIC_CHILD)
    p, h = part("optic", "scope", pack="P", tokens=(), extents=ext), host("optic", mount=seat(span=0.06), children={"optic": kid(OPTIC_CHILD)})
    assert listed(cand(p, h, params(TOL, NEVER, ["optic"])), CROSS)


# -- the tables: shipped literals, validation, digests (AC123) -------------------------------------------------------------------------


def test_ac118_the_shipped_tables_are_the_specified_literals():
    assert TABLES["attach_compat"]["cross_pack_size_tol"] == {"magazine": 0.35, "optic": 0.35, "underbarrel": 0.45}
    assert TABLES["cross_pack_never"] == {"muzzle": ["shotgun"]}
    assert TABLES["tokenless_family_free_slots"] == ["optic"]
    prm = compat._params(TABLES)
    assert prm["cross_pack_size_tol"] == {"magazine": 0.35, "optic": 0.35, "underbarrel": 0.45}
    assert prm["cross_pack_never"] == {"muzzle": frozenset({"shotgun"})} and prm["tokenless_family_free_slots"] == frozenset({"optic"})
    assert compat.GUN_CLASS_WORDS == {"pistol", "revolver", "smg", "rifle", "shotgun", "sniper", "lmg"}
    assert compat.HANDGUN_CLASSES == {"pistol", "revolver"}
    assert validate_rules(load_rules()) == []


def test_a_rules_dict_without_the_new_tables_is_valid_and_drops_nothing():
    rules = deepcopy(load_rules())
    t = rules["attachment_rules"]
    del t["attach_compat"]["cross_pack_size_tol"], t["cross_pack_never"], t["tokenless_family_free_slots"]
    assert validate_rules(rules) == []
    prm = compat._params(attachment_rules(rules))
    assert prm["cross_pack_size_tol"] == {} and prm["cross_pack_never"] == {} and prm["tokenless_family_free_slots"] == frozenset()
    assert listed(cand(part(extents=scaled(3.0)), host(children={"magazine": kid()}), prm), CROSS)


@pytest.mark.parametrize(("edit", "needle"), [
    (lambda t: t["attach_compat"].update(cross_pack_size_tol={"barrel": 0.3}), "cross_pack_size_tol"),
    (lambda t: t["attach_compat"].update(cross_pack_size_tol={"optic": 0}), "cross_pack_size_tol"),
    (lambda t: t["attach_compat"].update(cross_pack_size_tol={"optic": -0.1}), "cross_pack_size_tol"),
    (lambda t: t["attach_compat"].update(cross_pack_size_tol={"optic": "0.3"}), "cross_pack_size_tol"),
    (lambda t: t["attach_compat"].update(cross_pack_size_tol=[0.3]), "cross_pack_size_tol"),
    (lambda t: t.update(cross_pack_never={"barrel": ["shotgun"]}), "barrel"),
    (lambda t: t.update(cross_pack_never={"muzzle": ["blaster"]}), "blaster"),
    (lambda t: t.update(cross_pack_never={"muzzle": "shotgun"}), "cross_pack_never.muzzle"),
    (lambda t: t.update(cross_pack_never=["shotgun"]), "cross_pack_never"),
    (lambda t: t.update(tokenless_family_free_slots=["barrel"]), "tokenless_family_free_slots"),
    (lambda t: t.update(tokenless_family_free_slots=["optic", "optic"]), "distinct"),
    (lambda t: t.update(tokenless_family_free_slots="optic"), "tokenless_family_free_slots"),
])
def test_a_malformed_new_table_is_rejected(edit, needle):
    rules = deepcopy(load_rules())
    edit(rules["attachment_rules"])
    errors = validate_rules(rules)
    assert errors and any(needle in e for e in errors), (needle, errors)


def test_empty_new_tables_are_valid():
    rules = deepcopy(load_rules())
    t = rules["attachment_rules"]
    t["attach_compat"]["cross_pack_size_tol"], t["cross_pack_never"], t["tokenless_family_free_slots"] = {}, {}, []
    assert validate_rules(rules) == []


@pytest.mark.parametrize("edit", [
    lambda t: t["attach_compat"]["cross_pack_size_tol"].update(optic=0.3),
    lambda t: t["cross_pack_never"].update(muzzle=["shotgun", "rifle"]),
    lambda t: t.update(tokenless_family_free_slots=[]),
])
def test_every_new_table_moves_the_attach_digest_and_never_the_rules_digest(edit):
    base = load_rules()
    rules = deepcopy(base)
    edit(rules["attachment_rules"])
    assert validate_rules(rules) == []
    assert weapon_rules_digest(rules) == weapon_rules_digest(base) and attach_rules_digest(rules) != attach_rules_digest(base)


def test_ac123_the_versions_and_the_digests():
    assert pkg.WEAPON_ATTACH_VERSION == 12 and pkg.WEAPON_GEOMETRY_VERSION == 5
    rules = load_rules()
    assert weapon_rules_digest(rules) == "7b9829af37328fe7"
    assert len(attach_rules_digest(rules)) == 16 and attach_rules_digest(rules) != BASE_ATTACH_DIGEST
