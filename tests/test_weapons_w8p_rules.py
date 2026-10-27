"""W8p: cross-pack magazines unverified (A8-1), the symmetric suppressor rule (A8-2) and the versions (docs/weapon_attachments.md 13.9; AC124, AC126, AC129).

Pure ``compat.candidate`` cases over hand-made part and host views (no files), then ``compat.compute`` over hand-made records for the plumbing
(reasons, ``mount_missing``). Every table a case relies on is passed as a LITERAL in ``params`` (never read from the shipped YAML), so a change of the
shipped rows cannot loosen a case; the shipped rows have their own test. Part sizes are scaled from the baked child by literal factors (1.4 = 40 % off).
"""

from __future__ import annotations

from copy import deepcopy

import pytest

import synty_inventory.weapons as pkg
from synty_inventory.weapons import compat
from synty_inventory.weapons.rules import attach_rules_digest, attachment_rules, load_rules, validate_rules, weapon_rules_digest

TABLES = attachment_rules(load_rules())
AFFINITY = TABLES["attach_affinity"]
SAME, CROSS, TWIN, OVERRIDE = "same_pack_fit", "cross_pack_fit", "twin", "override"
A7_ATTACH_DIGEST = "306a4a553e8e5060"  # attach_rules_digest(load_rules()) at 6e55ce5 (attach version 12), measured by running the function there
TOL = {"magazine": 0.35, "optic": 0.35, "underbarrel": 0.45}
CHILD = [0.02, 0.04, 0.10]  # the baked child's sorted extents


def params(unverified=None, never=None, tol=None):
    """compat params with literal A8 tables (not the shipped ones); ``None`` = the row is absent."""
    tables = dict(TABLES)
    tables["attach_compat"] = {**TABLES["attach_compat"], "cross_pack_size_tol": TOL if tol is None else tol}
    if unverified is None:
        tables["attach_compat"].pop("cross_pack_unverified_slots", None)
    else:
        tables["attach_compat"]["cross_pack_unverified_slots"] = unverified
    tables.pop("cross_pack_never", None)
    tables["suppressor_never"] = {} if never is None else never
    tables["tokenless_family_free_slots"] = []
    return compat._params(tables)


UNVERIFIED = ["magazine"]
NEVER = {"muzzle": ["shotgun"]}


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


def pending(got, tier):
    return got is not None and not got["listed"] and got["tier"] == tier


# -- AC124 A8-1: a cross-pack magazine is unverified -----------------------------------------------------------------------------------


def test_ac124_a_cross_pack_magazine_on_a_host_with_a_seat_is_pending_as_host_and_tier_only():
    h = host(children={"magazine": kid()})
    got = cand(part(extents=scaled(1.1)), h, params(UNVERIFIED))
    assert got == {"host": "Q/Host_01", "tier": CROSS, "listed": False}  # no score, signals or replaces: the pending form
    # the seat is there: with the row removed the same pair is a listed entry with all its evidence
    full = cand(part(extents=scaled(1.1)), h, params(None))
    assert listed(full, CROSS) and {"score", "signals", "replaces"} <= set(full)


def test_ac124_the_row_removed_or_empty_lists_the_cross_magazine_again():
    h = host(children={"magazine": kid()})
    assert listed(cand(part(extents=scaled(1.1)), h, params(None)), CROSS)
    assert listed(cand(part(extents=scaled(1.1)), h, params([])), CROSS)  # an empty row is no rule
    assert listed(cand(part(extents=scaled(1.1)), h, params(["optic"])), CROSS)  # a row of another slot
    assert pending(cand(part(extents=scaled(1.1)), h, params(UNVERIFIED)), CROSS)


def test_ac124_the_same_pack_the_twin_and_the_override_magazine_stay_listed():
    same_h = host(pack="Q", tokens=("zulu",), children={"magazine": kid()})
    assert listed(cand(part(pack="Q", extents=scaled(1.1)), same_h, params(UNVERIFIED)), SAME)
    cross_h = host(children={"magazine": kid()})
    assert listed(cand(part(extents=scaled(1.1)), cross_h, params(UNVERIFIED), twin=True), TWIN)
    assert listed(cand(part(extents=scaled(1.1)), cross_h, params(UNVERIFIED), verdict="add"), OVERRIDE)
    # an override and a twin on a seatless host are pending as before, and an override beats the 40 % size gate
    none = seat(source="none", occupied=(), span=None)
    assert pending(cand(part(), host(mount=none), params(UNVERIFIED), verdict="add"), OVERRIDE)
    assert listed(cand(part(extents=scaled(1.4)), cross_h, params(UNVERIFIED), verdict="add"), OVERRIDE)


@pytest.mark.parametrize(("slot", "kind", "extents_of", "span"), [
    ("optic", "scope", [0.06, 0.08, 0.20], 0.06), ("underbarrel", "foregrip", [0.02, 0.03, 0.20], 0.06), ("muzzle", "brake", None, None),
    ("laser_light", "laser", None, 0.06),
])
def test_ac124_a_cross_pack_optic_underbarrel_muzzle_and_laser_stay_listed(slot, kind, extents_of, span):
    mount = seat(span=span) if slot != "muzzle" else seat(source="probe", occupied=(), bore_d_m=0.02, bore_source="ring")
    children = {slot: kid(extents_of)} if extents_of else {}
    p = part(slot, kind, extents=extents_of, mate_d_m=0.02 if slot == "muzzle" else None, foot_length_m=None if slot == "muzzle" else 0.06)
    h = host(slot, mount=mount, children=children)
    got = cand(p, h, params(UNVERIFIED))
    assert listed(got, CROSS), slot


def test_ac124_a_cross_pack_suppressor_on_a_rifle_stays_listed():
    mount = seat(source="probe", occupied=(), bore_d_m=0.02, bore_source="ring")
    p = part("muzzle", "suppressor", mate_d_m=0.02, foot_length_m=None)
    assert listed(cand(p, host("muzzle", mount=mount), params(UNVERIFIED, NEVER)), CROSS)


def test_ac124_a_pair_r_a_drops_is_dropped_not_parked():
    # a cross magazine 40 % off the baked child it replaces: R-a drops it. If the routing came BEFORE R-a it would be a pending entry here.
    h = host(children={"magazine": kid()})
    assert cand(part(extents=scaled(1.4)), h, params(UNVERIFIED)) is None
    assert pending(cand(part(extents=scaled(1.3)), h, params(UNVERIFIED)), CROSS)  # 30 % off: kept, and parked
    assert cand(part(extents=scaled(0.6)), h, params(UNVERIFIED)) is None  # 40 % under


def test_ac124_the_other_drops_come_first_too_the_gun_class_and_the_foot_test():
    h = host(children={"magazine": kid()})
    # R-b: a pistol-named part on a rifle host
    assert cand(part(tokens=("zulu", "pistol"), extents=scaled(1.1)), h, params(UNVERIFIED)) is None
    assert pending(cand(part(tokens=("zulu", "rifle"), extents=scaled(1.1)), h, params(UNVERIFIED)), CROSS)
    # the A6 foot test: a foot of 0.05 in a 0.15 well (0.33 < 0.75)
    assert cand(part(extents=scaled(1.1), foot_length_m=0.05), h, params(UNVERIFIED)) is None
    assert pending(cand(part(extents=scaled(1.1), foot_length_m=0.12), h, params(UNVERIFIED)), CROSS)


def test_ac124_a_pending_cross_magazine_without_a_seat_is_the_same_pending_form():
    none = seat(source="none", occupied=(), span=None)
    assert cand(part(), host(mount=none), params(UNVERIFIED)) == {"host": "Q/Host_01", "tier": CROSS, "listed": False}
    assert cand(part(), host(mount=none), params(None)) == {"host": "Q/Host_01", "tier": CROSS, "listed": False}  # unchanged by the row


# -- AC124 compute: reasons, mount_missing, the lists -----------------------------------------------------------------------------------


def record(rec_id, *, role, archetype, geometry=None, attachment=None):
    pack, asset = rec_id.split("/")
    return {"id": rec_id, "pack": pack, "asset_id": asset, "role": role, "kind": "ranged" if role == "whole" else None,
            "hold_class": "long_gun" if role == "whole" else "none", "archetype": archetype, "flags": [], "attachment": attachment,
            "geometry": geometry, "review": {"confidence": 0.9, "reasons": []}}


def world_records(unverified, *, with_seatless_host=True):
    seat_mount = {"source": "child_node", "point": [0.0, 0.1, 0.0], "forward": [0, 0, 1], "up": [0, 1, 0], "span_m": 0.15, "span_source": "child_foot",
                  "bore_d_m": None, "bore_source": None, "occupied_by": ["Mag"], "child_node": "Mag", "confidence": 0.9, "reason": None}
    none = {"source": "none", "point": None, "forward": None, "up": None, "span_m": None, "span_source": None, "bore_d_m": None, "bore_source": None,
            "occupied_by": [], "child_node": None, "confidence": 0.0, "reason": "no_child_no_probe"}
    foot = {"length_m": 0.044, "width_m": 0.022, "height_m": 0.11, "foot_length_m": 0.12,  # 10 % over the baked child: not a twin, inside R-a
             "foot_width_m": 0.02, "mate_d_m": None}
    anchor = {"point": [0, 0, 0], "forward": [0, 1, 0], "up": [0, 0, 1], "foot_source": "authored_up", "forward_source": "section", "symmetric": False}
    att = {"slot": "magazine", "kind": "standard", "anchor": anchor, "footprint": foot, "compatible_hosts": [], "pending_hosts": []}
    records = [record("Q/Gun_Seated_01", role="whole", archetype="rifle", geometry={"mounts": {"magazine": seat_mount}}),
               record("P/Wep_Zulu_Mag_01", role="part", archetype="unknown", attachment=att)]
    if with_seatless_host:
        records.append(record("Q/Gun_Seatless_01", role="whole", archetype="rifle", geometry={"mounts": {"magazine": none}}))
    rules = deepcopy(load_rules())
    rules["attachment_rules"]["attach_genre_by_pack"] = {"P": "s", "Q": "s"}
    rules["attachment_rules"]["attach_compat"]["cross_pack_size_tol"] = {"magazine": 0.35}
    if unverified is None:
        rules["attachment_rules"]["attach_compat"].pop("cross_pack_unverified_slots", None)
    else:
        rules["attachment_rules"]["attach_compat"]["cross_pack_unverified_slots"] = unverified
    evidence = {"Q/Gun_Seated_01": {"magazine": {"Mag": {"extents": [0.02, 0.04, 0.10], "axes": [0.04, 0.02, 0.10], "seat": None}}}}
    return records, rules, evidence


def test_ac124_compute_parks_the_seated_cross_magazine_and_keeps_reasons_and_mount_missing():
    records, rules, evidence = world_records(["magazine"])
    got = compat.compute(records, rules, None, child_extents=evidence)
    mag = got["parts"]["P/Wep_Zulu_Mag_01"]
    assert mag["compatible"] == []
    assert mag["pending"] == [{"host": "Q/Gun_Seated_01", "tier": CROSS}, {"host": "Q/Gun_Seatless_01", "tier": CROSS}]
    assert mag["reasons"] == {"compat_cross_pack"}  # the part still says it holds a cross-pack entry
    assert got["host_slots"] == {}  # the pending cross entries never counted toward mount_missing
    # row removed: the seated pair is listed again, the seatless one stays pending; reasons and mount_missing are the same
    records, rules, evidence = world_records(None)
    base = compat.compute(records, rules, None, child_extents=evidence)
    mag = base["parts"]["P/Wep_Zulu_Mag_01"]
    assert [e["host"] for e in mag["compatible"]] == ["Q/Gun_Seated_01"] and mag["pending"] == [{"host": "Q/Gun_Seatless_01", "tier": CROSS}]
    assert mag["reasons"] == {"compat_cross_pack"} and base["host_slots"] == {}


def test_ac124_apply_compat_writes_the_pending_entry_and_the_reason_into_the_records():
    records, rules, evidence = world_records(["magazine"])
    compat.apply_compat(records, rules, None, child_extents=evidence)
    part_rec = next(r for r in records if r["id"] == "P/Wep_Zulu_Mag_01")
    assert part_rec["attachment"]["compatible_hosts"] == []
    assert [(e["host"], e["tier"]) for e in part_rec["attachment"]["pending_hosts"]] == [("Q/Gun_Seated_01", CROSS), ("Q/Gun_Seatless_01", CROSS)]
    assert part_rec["review"]["reasons"] == ["compat_cross_pack"]
    for r in records:
        if r["role"] == "whole":
            assert "mount_missing" not in r["review"]["reasons"]


# -- AC126 A8-2: a suppressor on a shotgun is no candidate at any tier ------------------------------------------------------------------


def muzzle(archetype, *, pack="P", kind="suppressor", prm=None, ring=True, twin=False, verdict=None):
    mount = seat(source="probe", occupied=(), bore_d_m=0.02, bore_source="ring") if ring else seat(source="none", occupied=(), span=None)
    p = part("muzzle", kind, pack=pack, tokens=("zulu",), mate_d_m=0.02, foot_length_m=None)
    h = host("muzzle", archetype=archetype, mount=mount, tokens=("zulu",) if pack == "Q" else ("alpha",))
    return cand(p, h, prm or params(UNVERIFIED, NEVER), twin=twin, verdict=verdict)


@pytest.mark.parametrize("ring", [True, False])
def test_ac126_a_suppressor_on_a_shotgun_is_neither_listed_nor_pending_as_same_pack_cross_and_twin(ring):
    assert muzzle("shotgun", pack="Q", ring=ring) is None  # same_pack_fit (the A7 shape let it through)
    assert muzzle("shotgun", pack="P", ring=ring) is None  # cross_pack_fit
    assert muzzle("shotgun", pack="Q", ring=ring, twin=True) is None  # twin
    assert muzzle("shotgun", pack="P", ring=ring, twin=True) is None


@pytest.mark.parametrize("ring", [True, False])
def test_ac126_an_override_naming_the_pair_still_gives_an_override_entry(ring):
    got = muzzle("shotgun", pack="P", ring=ring, verdict="add")
    assert got is not None and got["tier"] == OVERRIDE and got["listed"] is ring
    got = muzzle("shotgun", pack="Q", ring=ring, verdict="add")
    assert got is not None and got["tier"] == OVERRIDE
    assert muzzle("shotgun", pack="Q", ring=ring, verdict="remove") is None


@pytest.mark.parametrize("kind", ["brake", "compensator", "flash_hider", "muzzle_device"])
def test_ac126_another_muzzle_device_on_a_shotgun_is_untouched(kind):
    same = muzzle("shotgun", pack="Q", kind=kind)
    assert same is not None and same["tier"] == SAME and same["listed"]
    cross = muzzle("shotgun", pack="P", kind=kind)
    assert cross is not None and cross["tier"] == CROSS and cross["listed"]
    assert muzzle("shotgun", pack="Q", kind=kind, twin=True)["tier"] == TWIN


@pytest.mark.parametrize("ring", [True, False])
def test_ac126_a_suppressor_on_a_rifle_host_is_untouched(ring):
    for archetype in ("rifle", "smg", "pistol", "sniper"):
        same = muzzle(archetype, pack="Q", ring=ring)
        assert same is not None and same["tier"] == SAME and same["listed"] is ring, archetype
        cross = muzzle(archetype, pack="P", ring=ring)
        assert cross is not None and cross["tier"] == CROSS and cross["listed"] is ring, archetype


def test_ac126_with_the_row_removed_the_same_pack_suppressor_on_the_shotgun_returns():
    for prm in (params(UNVERIFIED, None), params(UNVERIFIED, {"muzzle": []})):
        got = muzzle("shotgun", pack="Q", prm=prm)
        assert got is not None and got["tier"] == SAME and got["listed"]
        assert muzzle("shotgun", pack="Q", prm=prm, twin=True)["tier"] == TWIN
    assert muzzle("shotgun", pack="P", prm=params(UNVERIFIED, None))["tier"] == CROSS


def test_ac126_the_table_decides_the_slot_and_the_archetypes():
    assert muzzle("rifle", pack="Q", prm=params(UNVERIFIED, {"muzzle": ["rifle"]})) is None  # the table decides the archetypes
    assert muzzle("shotgun", pack="Q", prm=params(UNVERIFIED, {"optic": ["shotgun"]})) is not None  # a row of another slot
    assert muzzle("shotgun", pack="Q", prm=params(UNVERIFIED, {"muzzle": ["shotgun", "rifle"]})) is None
    assert muzzle("rifle", pack="Q", prm=params(UNVERIFIED, {"muzzle": ["shotgun", "rifle"]})) is None


def test_ac126_the_old_key_is_an_unknown_key_error_and_the_new_one_is_validated():
    rules = deepcopy(load_rules())
    rules["attachment_rules"]["cross_pack_never"] = {"muzzle": ["shotgun"]}
    errors = validate_rules(rules)
    assert errors and any("cross_pack_never" in e and "unknown" in e.lower() for e in errors), errors
    for bad, needle in (({"barrel": ["shotgun"]}, "barrel"), ({"muzzle": ["blaster"]}, "blaster"), ({"muzzle": "shotgun"}, "suppressor_never.muzzle"),
                        (["shotgun"], "suppressor_never"), ({"muzzle": ["shotgun", "shotgun"]}, "distinct")):
        rules = deepcopy(load_rules())
        rules["attachment_rules"]["suppressor_never"] = bad
        errors = validate_rules(rules)
        assert errors and any(needle in e for e in errors), (bad, errors)
    rules = deepcopy(load_rules())
    rules["attachment_rules"]["suppressor_never"] = {}
    assert validate_rules(rules) == []


# -- tables, validation, digests, versions (AC124, AC126, AC129) -------------------------------------------------------------------------


def test_the_shipped_rows_are_the_specified_literals():
    assert TABLES["attach_compat"]["cross_pack_unverified_slots"] == ["magazine"]
    assert TABLES["suppressor_never"] == {"muzzle": ["shotgun"]} and "cross_pack_never" not in TABLES
    prm = compat._params(TABLES)
    assert prm["cross_pack_unverified_slots"] == frozenset({"magazine"})
    assert prm["suppressor_never"] == {"muzzle": frozenset({"shotgun"})} and "cross_pack_never" not in prm
    assert validate_rules(load_rules()) == []


def test_a_rules_dict_without_the_new_rows_is_valid_and_moves_nothing():
    rules = deepcopy(load_rules())
    t = rules["attachment_rules"]
    del t["attach_compat"]["cross_pack_unverified_slots"], t["suppressor_never"]
    assert validate_rules(rules) == []
    prm = compat._params(attachment_rules(rules))
    assert prm["cross_pack_unverified_slots"] == frozenset() and prm["suppressor_never"] == {}
    assert listed(cand(part(extents=scaled(1.1)), host(children={"magazine": kid()}), prm), CROSS)
    assert muzzle("shotgun", pack="Q", prm=prm)["tier"] == SAME


@pytest.mark.parametrize(("value", "needle"), [
    (["barrel"], "must be a list of slots"), ("magazine", "must be a list of slots"), ({"magazine": 1}, "must be a list of slots"),
    ([1], "must be a list of slots"), (["magazine", "magazine"], "distinct"),  # the texts of the new check, not the old "unknown key" error that names the key
])
def test_a_malformed_unverified_row_is_rejected(value, needle):
    rules = deepcopy(load_rules())
    rules["attachment_rules"]["attach_compat"]["cross_pack_unverified_slots"] = value
    errors = validate_rules(rules)
    assert errors and any(needle in e for e in errors), (value, errors)


def test_an_empty_unverified_row_is_valid_and_an_unknown_attach_compat_key_still_errors():
    rules = deepcopy(load_rules())
    rules["attachment_rules"]["attach_compat"]["cross_pack_unverified_slots"] = []
    assert validate_rules(rules) == []
    rules["attachment_rules"]["attach_compat"]["cross_pack_unverified"] = ["magazine"]
    errors = validate_rules(rules)
    assert errors and any("cross_pack_unverified" in e and "unknown key" in e for e in errors), errors


@pytest.mark.parametrize("edit", [
    lambda t: t["attach_compat"].update(cross_pack_unverified_slots=[]),
    lambda t: t["attach_compat"].update(cross_pack_unverified_slots=["magazine", "optic"]),
    lambda t: t["suppressor_never"].update(muzzle=["shotgun", "rifle"]),
])
def test_every_new_row_moves_the_attach_digest_and_never_the_rules_digest(edit):
    base = load_rules()
    rules = deepcopy(base)
    edit(rules["attachment_rules"])
    assert validate_rules(rules) == []
    assert weapon_rules_digest(rules) == weapon_rules_digest(base) and attach_rules_digest(rules) != attach_rules_digest(base)


def test_ac129_the_versions_and_the_digests():
    assert pkg.WEAPON_ATTACH_VERSION == 13 and pkg.WEAPON_GEOMETRY_VERSION == 6
    rules = load_rules()
    assert weapon_rules_digest(rules) == "7b9829af37328fe7"
    assert len(attach_rules_digest(rules)) == 16 and attach_rules_digest(rules) != A7_ATTACH_DIGEST
    assert attach_rules_digest(rules) == "59268363ae44fd9e"  # G1 S2: fit_geometry block (was bcd5dbd0b3d7a651); this build's value, pinned so a later edit of the shipped rows is a deliberate re-pin (A8 erratum 2026-10-26: the tool token `flare` moved it from 30827a8915c9584d)
