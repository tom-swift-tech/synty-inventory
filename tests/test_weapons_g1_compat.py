"""G1 S8: the geometry verdict in ``compat`` (docs/weapon_attach_geometry.md 3.1, 3.5 to 3.8, 3.9, 4.4; INV-22, INV-23, INV-25; AC133, AC138 to AC140,
AC143, AC148, AC149).

Two layers. Pure ``compat.candidate`` cases over hand-made part and host views (no files; the tables are LITERAL dicts in this file, never the shipped
YAML) prove the rules of 3.1: the tier is the pack relation and nothing else, A8-1 acts after the tier, the score is the tier base alone, the signals are
the 3.1 vocabulary, the four verdicts map to the two lists, and policy comes before geometry. Then built directories of the FAKE_G1 world
(``fixtures/weapons/g1_world.py``) and of small worlds of this file prove the same on real meshes: the twins, the negative controls, the standing
refusals, the cross-pack magazines, the well pass cache, the retired keys of the shipped table and the determinism of the digests.

Every expected number is a LITERAL worked out by hand from the dimensions written in the fixtures (a 0.04 x 0.02 well, a 0.20 x 0.02 toothed run, a 0.02
barrel end); no bound is read from the rules file or from a constant under test, except where a test says it checks the shipped file itself.
Located preset magazine (E2): no test here exercises it. ``PRESET_MAG`` is built by the FAKE_G1 world, and its magazine mount is none, so the pair is
``not_judged``; the located path of ``fit_geometry`` is not touched.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, FIX / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GW = _load("g1_world")
J = _load("w8j_world")
W, A = GW.W, GW.A

from synty_inventory.weapons import compat  # noqa: E402
from synty_inventory.weapons import directory as dirmod  # noqa: E402
from synty_inventory.weapons import overrides as overrides_mod  # noqa: E402
from synty_inventory.weapons.overrides import empty_overrides, load_overrides  # noqa: E402
from synty_inventory.weapons.rules import attachment_rules, load_rules, validate_rules  # noqa: E402

SAME, CROSS, TWIN, OVERRIDE = "same_pack_fit", "cross_pack_fit", "twin", "override"
FOUR = ("optic", "muzzle", "underbarrel", "magazine")

# -- literal tables ----------------------------------------------------------------------------------------------------------------
FIT_RULES = {"slots": list(FOUR), "clamp": {"overhang_max_m": 0.010, "ratio_min": 1.0},
             "bore": {"od_ratio": [0.85, 2.0], "inner_ratio": [0.47, 1.21]}, "well": {"tol": 0.15}}
# a pretend `attach_affinity` for the label-era slots: the four geometry slots would read it if the retirement leaked
AFFINITY = {"muzzle": {"suppressor": ["pistol"], "default": ["pistol"]}, "optic": {"default": ["pistol"]},
            "underbarrel": {"default": ["pistol"]}, "magazine": {"default": ["pistol"]}, "laser_light": {"default": ["rifle"]}}


def params(*, unverified=("magazine",), bonus=0.0, never=None):
    """compat params from literal tables; ``bonus`` is put on every label-era score term to prove the geometry slots read none of them."""
    tables = {"attach_compat": {"tier_score": {"override": 1.0, "twin": 0.95}, "base": {"same_pack_fit": 0.7, "cross_pack_fit": 0.4},
                                "fit_span_bonus": bonus, "fit_bore_bonus": bonus, "fit_bore_penalty": bonus, "generic_tokens": [],
                                "cross_pack_size_tol": {"laser_light": 0.35}, "cross_pack_unverified_slots": list(unverified)},
              "suppressor_never": {"muzzle": ["shotgun"]} if never is None else never,
              "family_free_slots": ["sight_front", "sight_rear"], "tokenless_family_free_slots": [], "fit_geometry": FIT_RULES}
    return compat._params(tables)


RUN = {"length_m": 0.20, "width_m": 0.02}  # a toothed run: foot 0.06 x 0.02 sits on it (0.06 <= 0.20 + 0.010, 0.02 >= 1.0 * 0.02)
RING = {"od_m": 0.02, "evidence": "ring"}
ROUND = {"od_m": 0.02, "evidence": "round_section"}
WELL = {"length_m": 0.04, "width_m": 0.02}
HOST_ID = "Q/Host_01"

# case -> (slot, host slot features, part overrides, verdict, signals). The part is measured (anchor, 0.06 x 0.02 foot, mate 0.02) unless it says not.
CASES = {
    "rail_teeth_fit": ("optic", {"toothed_run": RUN}, {}, "fit", ["rail_teeth"]),
    "rail_teeth_no_fit": ("optic", {"toothed_run": RUN}, {"foot_length_m": 0.25}, "no_fit", ["rail_teeth"]),  # 0.25 > 0.20 + 0.010
    "rail_teeth_unverified": ("optic", {"toothed_run": RUN}, {"anchor_measured": False}, "unverified", ["rail_teeth"]),
    "seat_ref_fit": ("optic", {"ref": {"flat_run_m": 0.12, "child_foot_length_m": None}}, {}, "fit", ["seat_ref"]),  # 0.06 <= 0.12
    "rail_flat": ("optic", {"flat_seat": True}, {}, "unverified", ["rail_flat"]),
    "optic_not_judged": ("optic", {}, {}, "not_judged", []),
    "underbarrel_fit": ("underbarrel", {"toothed_run": RUN}, {}, "fit", ["rail_teeth"]),
    "underbarrel_flat_not_judged": ("underbarrel", {"flat_seat": True}, {}, "not_judged", []),  # a flat seat is an optic-only evidence
    "barrel_ring_fit": ("muzzle", {"barrel_end": RING}, {}, "fit", ["barrel_ring"]),
    "barrel_round_fit": ("muzzle", {"barrel_end": ROUND}, {}, "fit", ["barrel_round"]),
    "barrel_od_no_fit": ("muzzle", {"barrel_end": RING}, {"mate_d_m": 0.05}, "no_fit", ["barrel_ring"]),  # 0.05 / 0.02 = 2.5 > 2.0
    "no_barrel_end": ("muzzle", {"barrel_end": None}, {}, "no_fit", []),
    "muzzle_unmeasured": ("muzzle", {"barrel_end": RING}, {"anchor_measured": False}, "unverified", ["barrel_ring"]),
    "well_fit": ("magazine", {"well_ref": WELL}, {"section": [0.044, 0.022]}, "fit", ["well_entry"]),  # 10 % over both: inside 0.15
    "well_no_fit": ("magazine", {"well_ref": WELL}, {"section": [0.06, 0.03]}, "no_fit", ["well_entry"]),  # 50 % over
    "drum": ("magazine", {"well_ref": WELL}, {"section": None}, "unverified", ["drum"]),  # an empty section: the part does not reach the plane
    "no_well": ("magazine", {}, {"section": [0.04, 0.02]}, "not_judged", []),
}
KIND = {"optic": "scope", "muzzle": "suppressor", "underbarrel": "foregrip", "magazine": "standard", "laser_light": "laser"}


def part(slot, *, pack="P", tokens=("zulu",), kind=None, **kw):
    section = kw.pop("section", False)
    base = {"id": f"{pack}/Zulu_Part_01", "pack": pack, "slot": slot, "kind": kind or KIND[slot], "flags": set(), "tokens": frozenset(tokens),
            "foot_length_m": 0.06, "foot_width_m": 0.02, "mate_d_m": 0.02, "setting": ("setting", "s"), "anchor_measured": True,
            "device_inner_d": None, "sections": {}, "extents": None}
    if section is not False:
        base["sections"] = {HOST_ID: {"": section}}
    return {**base, **kw}


def seat(*, source="probe", occupied=()):
    return {"source": source, "span_m": None, "span_source": None, "bore_d_m": None, "bore_source": None, "occupied_by": list(occupied),
            "reason": None if source != "none" else "no_child_no_probe"}


def host(slot, feats, *, pack="Q", archetype="rifle", mount=None, tokens=("alpha",), **kw):
    base = {"id": f"{pack}/Host_01", "pack": pack, "archetype": archetype, "flags": set(), "mounts": {slot: seat() if mount is None else mount},
            "tokens": frozenset(tokens), "setting": ("setting", "s"), "children": {}, "refused": frozenset(),
            "feats": None if feats is None else {"slots": {slot: feats}}}
    return {**base, **kw}


def cand(p, h, *, prm=None, twin=False, verdict=None, affinity=AFFINITY, twin_replaces=None):
    return compat.candidate(p, h, verdict=verdict, twin=twin, affinity=affinity, params=prm or params(), twin_replaces=twin_replaces)


def case(name, *, part_pack="Q", host_pack="Q", **kw):
    slot, feats, over, _value, _signals = CASES[name]
    return part(slot, pack=part_pack, **over), host(slot, feats, pack=host_pack, **kw)


# -- 3.1 step 4: the tier is the pack relation and nothing else ---------------------------------------------------------------------


@pytest.mark.parametrize("name", ["rail_teeth_fit", "underbarrel_fit", "barrel_ring_fit", "barrel_round_fit"])
def test_the_tier_is_the_pack_relation_for_the_rail_and_muzzle_slots(name):
    same_part, same_host = case(name)
    cross_part, cross_host = case(name, part_pack="P")
    assert cand(same_part, same_host)["tier"] == SAME
    assert cand(cross_part, cross_host)["tier"] == CROSS


@pytest.mark.parametrize("tokens", [("zulu",), ("alpha",), ("alpha", "zulu"), ()])
@pytest.mark.parametrize("kind", ["scope", "brake", "other"])
@pytest.mark.parametrize("archetype", ["pistol", "rifle", "shotgun", "lmg"])
def test_inv23_names_kinds_and_archetypes_decide_no_tier_and_no_verdict(tokens, kind, archetype):
    # G1 3.8: family_overlap, attach_affinity and the gun class are retired for the four slots. The part shares no token with the host in one case and all of
    # them in another, has any kind, sits on any archetype (AFFINITY above allows only a pistol): the entry is the same
    for slot in ("optic", "underbarrel", "magazine"):
        name = {"optic": "rail_teeth_fit", "underbarrel": "underbarrel_fit", "magazine": "well_fit"}[slot]
        base_part, base_host = case(name)
        want = cand(base_part, base_host)
        moved_part = {**base_part, "tokens": frozenset(tokens), "kind": kind}
        moved_host = {**base_host, "archetype": archetype}
        assert cand(moved_part, moved_host) == want, (slot, tokens, kind, archetype)
        assert cand(moved_part, moved_host, affinity={}) == want  # a blank table changes nothing either (AC149)
    muz_part, muz_host = case("barrel_ring_fit")
    muz_part = {**muz_part, "tokens": frozenset(tokens), "kind": "brake" if kind == "other" else kind}  # a suppressor-only veto is policy, tested below
    assert cand(muz_part, {**muz_host, "archetype": archetype}) == cand(muz_part, muz_host, affinity={}) == cand(*case("barrel_ring_fit"))


def test_the_label_slot_still_reads_the_family_test_and_the_affinity_table():
    # AC149, the other side: a leak of the geometry rules into laser_light would show here. The same pair gives a candidate only through its labels
    laser_host = host("laser_light", None, mount={**seat(source="child_node", occupied=("Kid",)), "span_m": 0.06})
    laser = part("laser_light", tokens=("zulu",), pack="Q")
    assert cand(laser, laser_host) is None  # no shared token with the host
    assert cand({**laser, "tokens": frozenset({"alpha"})}, laser_host)["tier"] == SAME
    assert cand({**laser, "tokens": frozenset({"alpha"})}, laser_host, affinity={}) is None  # the affinity row is what lets a rifle host through


# -- 3.1 step 4 and 5: A8-1 after the tier, the score from the tier base, the signals -------------------------------------------------


def test_a8_1_acts_after_the_tier_a_cross_pack_magazine_fit_is_pending_and_a_same_pack_one_listed():
    cross_part, cross_host = case("well_fit", part_pack="P")
    got = cand(cross_part, cross_host)
    # the pending form carries the evidence of the fit it parks; `fit_parked` is the transient marker `compute` counts for AC140
    assert got == {"host": HOST_ID, "tier": CROSS, "listed": False, "signals": ["well_entry"], "fit_parked": True}
    same_part, same_host = case("well_fit")
    got = cand(same_part, same_host)
    assert got["listed"] is True and got["tier"] == SAME and got["signals"] == ["well_entry"] and "fit_parked" not in got
    # the other cross-pack slots are not parked by the magazine row, and the row decides by slot: empty, it parks nothing
    assert cand(*case("rail_teeth_fit", part_pack="P"))["listed"] is True
    assert cand(cross_part, cross_host, prm=params(unverified=()))["listed"] is True
    assert cand(*case("rail_teeth_fit", part_pack="P"), prm=params(unverified=("optic",)))["listed"] is False


def test_a8_1_parks_only_what_the_verdict_listed_and_never_a_twin_or_an_override():
    # a cross-pack magazine the verdict refuses is on neither list (parking before the verdict would make it pending)
    assert cand(*case("well_no_fit", part_pack="P")) is None
    # an unverified or not_judged cross-pack magazine is pending as it was, and carries no `fit_parked` marker
    assert cand(*case("drum", part_pack="P")) == {"host": HOST_ID, "tier": CROSS, "listed": False, "signals": ["drum"]}
    assert cand(*case("no_well", part_pack="P")) == {"host": HOST_ID, "tier": CROSS, "listed": False}
    cross_part, cross_host = case("well_fit", part_pack="P")
    assert cand(cross_part, cross_host, twin=True)["tier"] == TWIN and cand(cross_part, cross_host, twin=True)["listed"] is True
    assert cand(cross_part, cross_host, verdict="add")["tier"] == OVERRIDE and cand(cross_part, cross_host, verdict="add")["listed"] is True


@pytest.mark.parametrize("bonus", [0.0, 0.5])
def test_the_score_is_the_tier_base_alone(bonus):
    # the span, bore and penalty terms of the label era are retired for the four slots: whatever they are set to, a same-pack fit scores the base 0.7 and a
    # cross-pack one 0.4, a twin 0.95 and an override 1.0
    prm = params(bonus=bonus)
    assert cand(*case("rail_teeth_fit"), prm=prm)["score"] == 0.7
    assert cand(*case("barrel_ring_fit"), prm=prm)["score"] == 0.7
    assert cand(*case("barrel_ring_fit", part_pack="P"), prm=prm)["score"] == 0.4
    assert cand(*case("rail_teeth_fit"), prm=prm, twin=True)["score"] == 0.95
    assert cand(*case("rail_teeth_fit"), prm=prm, verdict="add")["score"] == 1.0


# the `bore_mismatch` of the label era (a ring 100 % off) is no signal and no penalty any more: the muzzle is judged by its OD ratio (3.6)
def test_a_part_mate_far_from_the_bore_is_no_label_signal():
    p, h = case("barrel_ring_fit")
    got = cand({**p, "mate_d_m": 0.034}, h, prm=params(bonus=0.5))  # 1.7 x the barrel OD: inside [0.85, 2.0]
    assert got["signals"] == ["barrel_ring"] and got["score"] == 0.7


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_four_verdicts_map_to_the_two_lists(name):
    slot, _feats, _over, value, signals = CASES[name]
    p, h = case(name)
    got = cand(p, h)
    if value == "no_fit":
        assert got is None  # the mating feature is measured and the part does not match: neither listed nor pending
    elif value == "fit":
        assert got["listed"] is True and got["signals"] == signals and got["replaces"] == [] and got["score"] == 0.7
    elif value == "unverified":
        assert got == {"host": HOST_ID, "tier": SAME, "listed": False, "signals": signals}  # pending, with what was measured
    else:
        assert got == {"host": HOST_ID, "tier": SAME, "listed": False}  # not_judged: a bare pending entry


@pytest.mark.parametrize("name", [n for n in sorted(CASES) if CASES[n][3] == "fit"])
def test_a_fit_on_a_host_with_no_seat_is_pending_with_its_signals(name):
    # the verdict says fit, the mount says there is nowhere to place it: pending (as before), the evidence kept. A magazine with no seat has nothing to place
    # the part at (3.7 step 1, errata E2.4), so it is not_judged and its pending entry is bare
    slot, _feats, _over, _value, signals = CASES[name]
    p, h = case(name)
    got = cand(p, {**h, "mounts": {slot: seat(source="none")}})
    assert got == {"host": HOST_ID, "tier": SAME, "listed": False, **({} if slot == "magazine" else {"signals": signals})}


def test_inv22_a_listed_geometry_entry_is_a_fit_with_a_geometry_signal_and_never_rail_flat_alone():
    geometry_signals = {"rail_teeth", "seat_ref", "barrel_ring", "barrel_round", "well_entry"}
    for name, (_slot, _feats, _over, value, _signals) in CASES.items():
        for part_pack in ("Q", "P"):
            got = cand(*case(name, part_pack=part_pack))
            if got is not None and got["listed"]:
                assert value == "fit" and geometry_signals & set(got["signals"]), (name, got)
                assert set(got["signals"]) != {"rail_flat"}
    flat = cand(*case("rail_flat"))
    assert flat["listed"] is False and flat["signals"] == ["rail_flat"]  # AC148: a flat seat lists nothing


def test_frame_body_is_appended_to_every_verdict_of_a_host_with_the_flag():
    for name, (slot, feats, over, value, signals) in CASES.items():
        if value == "not_judged" or (value == "no_fit" and not signals):
            continue
        p = part(slot, pack="Q", **over)
        h = host(slot, {**feats, "frame_body": True})
        got = cand(p, h)
        if value == "no_fit":
            assert got is None
        else:
            assert got["signals"] == sorted([*signals, "frame_body"]), name


def test_the_twin_listing_is_unchanged_whatever_the_verdict():
    # AC133: a twin is listed as before, its verdict is calibration. A `fit` names its evidence beside `twin`; an unverified (drum), a no_fit (the slide-face
    # silencer: the barrel od is far off) and a not_judged twin keep the bare `twin` signal and the same score
    for name, signals in (("well_fit", ["twin", "well_entry"]), ("drum", ["twin"]), ("barrel_od_no_fit", ["twin"]), ("no_well", ["twin"]),
                          ("rail_teeth_fit", ["twin", "rail_teeth"]), ("rail_flat", ["twin"])):
        slot = CASES[name][0]
        p, h = case(name)
        got = cand(p, {**h, "mounts": {slot: seat(source="child_node", occupied=("Kid",))}}, twin=True, twin_replaces=["Kid"])
        assert got["tier"] == TWIN and got["listed"] is True and got["score"] == 0.95, name
        assert got["signals"] == sorted(signals) and got["replaces"] == ["Kid"], name


# -- policy comes before geometry (3.8) ---------------------------------------------------------------------------------------------


def test_the_setting_gate_slot_disabled_and_mech_scale_refuse_a_fit_pair():
    p, h = case("rail_teeth_fit")
    assert cand(p, {**h, "setting": ("setting", "other")}) is None
    assert cand(p, {**h, "mounts": {"optic": {**seat(source="none"), "reason": "slot_disabled"}}}) is None
    assert cand(p, {**h, "refused": frozenset({"optic"})}) is None
    assert cand(p, {**h, "flags": {"mech_scale"}}) is None
    assert cand({**p, "flags": {"mech_scale"}}, {**h, "flags": {"mech_scale"}})["listed"] is True
    # an override add outranks all four except the remove; the setting gate is the one policy `add` also outranks
    assert cand(p, {**h, "flags": {"mech_scale"}}, verdict="add")["tier"] == OVERRIDE
    assert cand(p, {**h, "setting": ("setting", "other")}, verdict="add")["tier"] == OVERRIDE
    assert cand(p, h, verdict="remove") is None


def test_the_suppressor_rule_vetoes_before_the_verdict_and_an_add_outranks_it():
    p, h = case("barrel_ring_fit")
    shotgun = {**h, "archetype": "shotgun"}
    assert cand(p, shotgun) is None and cand(p, shotgun, twin=True) is None  # a fit suppressor, refused at any tier
    assert cand({**p, "kind": "brake"}, shotgun)["listed"] is True  # another muzzle device is untouched
    assert cand(p, shotgun, verdict="add")["tier"] == OVERRIDE
    assert cand(p, shotgun, prm=params(never={}))["listed"] is True  # the table decides, not the archetype name


def test_an_override_does_not_consult_the_geometry_and_lists_a_no_fit_pair():
    p, h = case("well_no_fit")
    got = cand(p, h, verdict="add")
    assert got["tier"] == OVERRIDE and got["signals"] == ["override"] and got["score"] == 1.0 and got["listed"] is True
    no_barrel = cand(*case("no_barrel_end"), verdict="add")
    assert no_barrel["tier"] == OVERRIDE and no_barrel["listed"] is True


def test_a_geometry_pair_with_host_features_needs_the_fit_rules():
    # a design call of S8: a host that was measured but rules with no fit_geometry block cannot be judged. Silent not_judged would hide a broken rules dict
    p, h = case("rail_teeth_fit")
    prm = dict(params(), fit_rules=None)
    with pytest.raises(ValueError, match="fit_geometry"):
        cand(p, h, prm=prm)
    assert cand(p, {**h, "feats": None}, prm=prm) == {"host": HOST_ID, "tier": SAME, "listed": False}  # an unmeasured host needs none


def test_a_magazine_pair_whose_section_the_pass_did_not_measure_is_unverified_never_fit():
    p, h = case("well_fit")
    no_sections = {**p, "sections": {}}
    assert cand(no_sections, h) == {"host": HOST_ID, "tier": SAME, "listed": False, "signals": ["well_entry"]}


# -- the validator and the shipped table (3.8) ----------------------------------------------------------------------------------------


def _bad(edit):
    rules = deepcopy(load_rules())
    edit(rules["attachment_rules"])
    return validate_rules(rules)


@pytest.mark.parametrize(("edit", "needle"), [
    (lambda t: t["attach_compat"].update(fit_span_min=0.75), "fit_span_min"),
    *[(lambda t, s=s: t["attach_compat"].update(cross_pack_size_tol={s: 0.35}), f"cross_pack_size_tol.{s}") for s in FOUR],
    *[(lambda t, s=s: t.update(family_free_slots=[*t["family_free_slots"], s]), "family_free_slots") for s in FOUR],
    *[(lambda t, s=s: t.update(tokenless_family_free_slots=[s]), "tokenless_family_free_slots") for s in FOUR],
    *[(lambda t, s=s: t["attach_affinity"].update({s: {"default": ["rifle"]}}), f"attach_affinity.{s}") for s in FOUR],
])
def test_g1_3_8_a_retired_key_naming_a_geometry_slot_is_rejected(edit, needle):
    errors = _bad(edit)
    assert errors and any(needle in e and "retired" in e or needle in e and "geometry slot" in e for e in errors), (needle, errors)


def test_g1_3_8_the_label_slots_keep_their_rows():
    # laser_light and the sights keep every label-era mechanism, so the validator accepts rows for them
    assert _bad(lambda t: t["attach_compat"].update(cross_pack_size_tol={"laser_light": 0.35, "sight_front": 0.45})) == []
    assert _bad(lambda t: t.update(family_free_slots=["sight_front", "sight_rear", "laser_light"])) == []
    assert _bad(lambda t: t.update(tokenless_family_free_slots=["sight_front"])) == []
    assert _bad(lambda t: t["attach_affinity"].update({"laser_light": {"default": ["rifle"]}})) == []


def test_g1_3_8_the_shipped_table_carries_no_retired_key():
    # reads the shipped file on purpose: a retired key left in weapon_rules.yaml fails here
    rules = load_rules()
    tables = attachment_rules(rules)
    assert validate_rules(rules) == []
    assert "fit_span_min" not in tables["attach_compat"]
    assert not set(tables["attach_compat"].get("cross_pack_size_tol") or {}) & set(FOUR)
    assert tables["family_free_slots"] == ["sight_front", "sight_rear"]
    assert not set(tables.get("tokenless_family_free_slots") or ()) & set(FOUR)
    assert not set(tables["attach_affinity"]) & set(FOUR)
    assert tables["attach_compat"]["cross_pack_unverified_slots"] == ["magazine"]  # A8-1 stays
    assert tables["suppressor_never"] == {"muzzle": ["shotgun"]}  # A8-2 stays


# -- built directories ---------------------------------------------------------------------------------------------------------------


def build(tmp, world, *, rules=None, overrides=None, cache=None, **kw):
    cat, root = W.write_world(tmp, world)
    return dirmod.build_directory_report(
        cat, overrides=overrides if overrides is not None else empty_overrides(), pack_settings=W.pack_settings(world),
        rules=rules if rules is not None else GW.cross_rules(), threejs_v2_dir=root, geometry_cache={} if cache is None else cache, **kw)


@pytest.fixture(scope="module")
def g1(tmp_path_factory):
    d, _ex, report = build(tmp_path_factory.mktemp("g1_compat"), GW.cross_world())
    return SimpleNamespace(directory=d, report=report, by_id=W.by_id(d))


def att(b, name, pack=GW.PACK):
    return b.by_id[GW.pid(name, pack)]["attachment"]


def listed(b, name, pack=GW.PACK):
    return {e["host"].split("/", 1)[1]: (e["tier"], e["score"], tuple(e["signals"])) for e in att(b, name, pack)["compatible_hosts"]}


def pending(b, name, pack=GW.PACK):
    return {e["host"].split("/", 1)[1]: (e["tier"], tuple(e.get("signals", ()))) for e in att(b, name, pack)["pending_hosts"]}


def test_ac148_a_toothed_rail_lists_and_a_flat_seat_stays_pending(g1):
    # the carbine (Notched) has the 8-tooth rail: the scope fits it (same pack 0.7, cross pack 0.4); every other flat top is `rail_flat`, pending, listing nothing
    assert listed(g1, GW.SCOPE)[GW.CARBINE] == (SAME, 0.7, ("rail_teeth",))
    assert listed(g1, GW.TWIN_SCOPE, GW.OTHER)[GW.CARBINE] == (CROSS, 0.4, ("rail_teeth",))
    for scope, pack in ((GW.SCOPE, GW.PACK), (GW.TWIN_SCOPE, GW.OTHER)):
        flat = {h for h, (_t, sig) in pending(g1, scope, pack).items() if sig == ("rail_flat",)}
        assert flat == {GW.FLAT, GW.FLATTOP, GW.LOWRAIL, GW.PRESET_MAG, GW.SHOTGUN}, pack
        assert not [h for h, e in listed(g1, scope, pack).items() if e[2] == ("rail_flat",)]


def test_ac148_an_untoothed_host_with_an_authored_optic_child_lists_through_seat_ref(g1):
    # SCOPED and STEPPED bake a scope child; both pairs are twins whose verdict is fit through the authored reference
    for pack in (GW.PACK, GW.OTHER):
        got = listed(g1, GW.SCOPE if pack == GW.PACK else GW.TWIN_SCOPE, pack)
        assert got[GW.SCOPED] == (TWIN, 0.95, ("seat_ref", "twin")) and got[GW.STEPPED] == (TWIN, 0.95, ("seat_ref", "twin"))


def test_inv22_no_listed_geometry_entry_of_the_world_lacks_a_verdict_signal(g1):
    geometry = {"rail_teeth", "seat_ref", "barrel_ring", "barrel_round", "well_entry"}
    seen = 0
    for rec in g1.directory["weapons"]:
        a = rec.get("attachment")
        if not a or a["slot"] not in FOUR:
            continue
        for e in a["compatible_hosts"]:
            if e["tier"] in (SAME, CROSS):
                seen += 1
                assert geometry & set(e["signals"]) and set(e["signals"]) != {"rail_flat"}, (rec["id"], e)
    # by hand: magazines 3 (Alfa) + 2 (Mag_Rifle: Plain, Uzi) = 5, scope on the carbine 1 + 1, silencers 8 + 5 + 3 in FAKE_G1 and 8 cross-pack = 24
    assert seen == 31


def test_ac133_the_twins_of_the_world_list_with_their_evidence(g1):
    twins = {(rec["id"].split("/", 1)[1], e["host"].split("/", 1)[1], tuple(e["signals"]))
             for rec in g1.directory["weapons"] if rec.get("attachment") for e in rec["attachment"]["compatible_hosts"] if e["tier"] == TWIN}
    assert twins == {  # a twin pair: the magazine in Preset's well (a cross-family well, 0.15 tolerance), the scopes on the two authored optic seats
        (GW.MAG_RIFLE, GW.PRESET, ("twin", "well_entry")), (GW.SCOPE, GW.SCOPED, ("seat_ref", "twin")), (GW.SCOPE, GW.STEPPED, ("seat_ref", "twin"))}
    twin_entries = sum(1 for rec in g1.directory["weapons"] if rec.get("attachment") for e in rec["attachment"]["compatible_hosts"] if e["tier"] == TWIN)
    assert twin_entries == 6  # the three above in FAKE_G1 and the same three of the OTHER-pack copies (a cross-pack twin lists as a twin)


def test_ac140_no_cross_pack_magazine_is_listed_and_the_fit_count_is_the_two_wells_the_part_matches(g1, capsys):
    for rec in g1.directory["weapons"]:
        a = rec.get("attachment")
        if a and a["slot"] == "magazine":
            assert not [e for e in a["compatible_hosts"] if e["tier"] == CROSS], rec["id"]
    got = pending(g1, GW.MAG_RIFLE, GW.OTHER)
    assert got[GW.RIFLE_PLAIN] == (CROSS, ("well_entry",)) and got[GW.UZI] == (CROSS, ("frame_body", "well_entry"))
    count = g1.report["cross_pack_magazine_fit"]
    print(f"AC140: cross-pack magazine pairs judged fit and parked by A8-1 (Q-G1): {count}")
    assert count == 2  # the OTHER-pack Mag_Rifle fits the wells of Plain and Uzi (the Alfa and drum cross-pack parts: the drum is no_fit, not a fit)
    assert "AC140" in capsys.readouterr().out


def test_ac133_a_drum_is_not_a_fit_in_the_world(g1):
    # the drum (0.06 x 0.065 section) is no_fit against the 0.04 x 0.02 wells: listed nowhere, and pending only on hosts with no well to judge it
    got = pending(g1, GW.MAG_DRUM)
    assert not listed(g1, GW.MAG_DRUM) and all(sig == () for _t, sig in got.values())
    assert {GW.RIFLE_PLAIN, GW.UZI, GW.PRESET} & set(got) == set()


def test_ac138_negative_controls_the_launcher_tool_and_minigun_take_no_optic(g1):
    for name in (GW.ROCKET, GW.NAILGUN, GW.MINIGUN):
        for scope, pack in ((GW.SCOPE, GW.PACK), (GW.TWIN_SCOPE, GW.OTHER)):
            assert name not in listed(g1, scope, pack) and name not in pending(g1, scope, pack), (name, pack)


def test_ac138_negative_controls_a_magazine_is_never_listed_on_a_host_with_no_well_reference(g1):
    no_well = {GW.FLAT, GW.FLATTOP, GW.LOWRAIL, GW.SCOPED, GW.STEPPED, GW.PRESET_MAG, GW.SHOTGUN, GW.ROCKET}
    for name, pack in ((GW.MAG_RIFLE, GW.PACK), (GW.MAG_PISTOL, GW.PACK), (GW.MAG_DRUM, GW.PACK), (GW.MAG_RIFLE, GW.OTHER), (GW.MAG_DRUM, GW.OTHER)):
        assert not no_well & set(listed(g1, name, pack)), (name, pack)


def neg_world():
    """Hosts the controls need and FAKE_G1 does not have: a box-barrel rifle (no barrel end) and a melee record. The parts are the FAKE_G1 ones."""
    pack = "FAKE_G1_NEG"
    return {pack: {"hosts": {"SM_Wep_Rifle_Box_01": W.host_node("SM_Wep_Rifle_Box_01", W.box_rifle()),
                             "SM_Wep_Sword_Long_01": W.host_node("SM_Wep_Sword_Long_01", W.box_rifle())},
                   "parts": {GW.SCOPE: A.optic, GW.SILENCER: A.suppressor, GW.MAG_RIFLE: lambda: A.mag_box(0.01, 0.12, 0.02),
                             "SM_Wep_Zulu_Foregrip_01": lambda: A.flip_y(A.optic())}}}


def test_ac138_negative_controls_a_muzzle_needs_a_barrel_end_and_a_melee_record_takes_nothing(tmp_path):
    d, _ex, _report = build(tmp_path, neg_world(), rules=W.sight_rules({"FAKE_G1_NEG": "modern"}))
    by = W.by_id(d)
    for part_name in (GW.SCOPE, GW.SILENCER, GW.MAG_RIFLE, "SM_Wep_Zulu_Foregrip_01"):
        a = by[f"FAKE_G1_NEG/{part_name}"]["attachment"]
        assert not [e for e in a["compatible_hosts"] if e["host"].endswith("SM_Wep_Sword_Long_01")], part_name
        assert not [e for e in a["pending_hosts"] if e["host"].endswith("SM_Wep_Sword_Long_01")], part_name
    sil = by[f"FAKE_G1_NEG/{GW.SILENCER}"]["attachment"]
    assert sil["compatible_hosts"] == [] and sil["pending_hosts"] == []  # the box rifle's barrel is a box: no ring and no round section, so no_fit
    assert by["FAKE_G1_NEG/SM_Wep_Sword_Long_01"].get("geometry", {}).get("mounts") in (None, {})


# -- AC139: the standing refusals --------------------------------------------------------------------------------------------------------


def test_ac139_1_a_preset_refuses_its_filled_slots_and_keeps_the_magazine_open(g1):
    # FAKE_G1 Preset_Rifle has a scope and a silencer fused into the mesh (located, Q-G11) and bakes a Mag child: no optic or muzzle part is a candidate on it,
    # and its magazine slot stays open (the baked Mag is a twin of the rifle magazine, and the pistol-family one fits the same well)
    for name in (GW.SCOPE, GW.SILENCER, GW.RING_DEVICE, GW.PLAIN_DEVICE):
        assert GW.PRESET not in listed(g1, name) and GW.PRESET not in pending(g1, name), name
    assert listed(g1, GW.MAG_RIFLE)[GW.PRESET][0] == TWIN and listed(g1, GW.MAG_PISTOL)[GW.PRESET][0] == SAME
    # Preset_Carbine fuses a magazine only (a located well, no seat): its optic and muzzle slots are open, as the fill list says
    assert GW.PRESET_MAG in listed(g1, GW.SILENCER)


@pytest.fixture(scope="module")
def sights(tmp_path_factory):
    """The W8j hosts of the sight refusals (a baked post, a body child, a glass-only host) with the three sight-side parts."""
    pack = "FAKE_G1_SIGHTS"
    hosts = {"SM_Wep_Rifle_Alpha_01": J.X.rifle("SM_Wep_Rifle_Alpha_01", [("Fake_Sights", J.X.sight_post(), (0.0, 0.054, 0.45))]),
             "SM_Wep_Rifle_Bravo_01": J.X.rifle("SM_Wep_Rifle_Bravo_01", [("Fake_Sight_Glass_01", J.sheet(), (0.0, 0.1015, 0.0))]),
             "SM_Wep_Rifle_Charlie_01": J.X.rifle("SM_Wep_Rifle_Charlie_01", [("Fake_Scope_01", A.optic(), (0.0, 0.10, -0.05))])}
    parts = {"SM_Wep_Rifle_Scope_01": A.optic, J.X.SIGHT_FRONT: W.sight_part, J.X.SIGHT_REAR: W.sight_part}
    d, _ex, _rep = build(tmp_path_factory.mktemp("g1_sights"), {pack: {"hosts": hosts, "parts": parts}}, rules=W.sight_rules({pack: "modern"}))
    return W.by_id(d), pack


def sight_entries(sights, part_name, host_name):
    by, pack = sights
    a = by[f"{pack}/{part_name}"]["attachment"]
    return [e for e in a["compatible_hosts"] + a["pending_hosts"] if e["host"] == f"{pack}/{host_name}"]


def test_ac139_2_a_baked_iron_sight_refuses_both_sight_slots(sights):
    for part_name in (J.X.SIGHT_FRONT, J.X.SIGHT_REAR):
        assert sight_entries(sights, part_name, "SM_Wep_Rifle_Alpha_01") == [], part_name


def test_ac139_3_a_glass_only_host_refuses_the_optic(sights):
    assert sight_entries(sights, "SM_Wep_Rifle_Scope_01", "SM_Wep_Rifle_Bravo_01") == []
    for part_name in (J.X.SIGHT_FRONT, J.X.SIGHT_REAR):
        assert sight_entries(sights, part_name, "SM_Wep_Rifle_Bravo_01") == []


def test_ac139_4_a_baked_optic_body_on_a_non_preset_host_stays_replaceable_not_refused(sights):
    got = sight_entries(sights, "SM_Wep_Rifle_Scope_01", "SM_Wep_Rifle_Charlie_01")
    assert len(got) == 1 and got[0]["tier"] == TWIN and got[0]["replaces"] == ["SM_Wep_Rifle_Charlie_01_Fake_Scope_01"]  # hidden through occupied_by on mount


def test_ac139_5_no_silencer_on_a_shotgun_or_launcher_and_no_optic_on_a_launcher_tool_or_minigun(g1):
    for name in (GW.SHOTGUN, GW.ROCKET):
        for sil, pack in ((GW.SILENCER, GW.PACK), (GW.SILENCER, GW.OTHER)):
            assert name not in listed(g1, sil, pack) and name not in pending(g1, sil, pack), (name, pack)
    for name in (GW.ROCKET, GW.NAILGUN, GW.MINIGUN):
        assert name not in listed(g1, GW.SCOPE) and name not in pending(g1, GW.SCOPE), name


def test_ac139_5_the_sniper_heavy_muzzle_ruling_and_the_preset_a_fill_list_come_from_the_shipped_overrides(tmp_path):
    br, mil = "POLYGON_BattleRoyale", "POLYGON_Military"
    rod = GW.rod_rifle
    world = {br: {"hosts": {"SM_Wep_Sniper_Heavy_01": W.host_node("SM_Wep_Sniper_Heavy_01", rod())}, "parts": {"SM_Wep_Attachment_Silencer_01": A.suppressor}},
             mil: {"hosts": {"SM_Wep_Preset_A_Sniper_01": W.host_node("SM_Wep_Preset_A_Sniper_01", rod())},
                   "parts": {"SM_Wep_Mod_Silencer_01": A.suppressor, "SM_Wep_Mod_Scope_01": A.optic,
                             "SM_Wep_Mod_Mag_01": lambda: A.mag_box(0.01, 0.12, 0.02)}}}
    # the committed file by path: the suite's autouse fixture points the default path at an empty file
    shipped = Path(overrides_mod.__file__).resolve().parent.parent / "data" / "weapon_overrides.json"
    d, _ex, _rep = build(tmp_path, world, rules=W.sight_rules({br: "modern", mil: "modern"}), overrides=load_overrides(shipped))
    by = W.by_id(d)
    for part_id, host_id in ((f"{br}/SM_Wep_Attachment_Silencer_01", f"{br}/SM_Wep_Sniper_Heavy_01"), (f"{mil}/SM_Wep_Mod_Silencer_01", f"{mil}/SM_Wep_Preset_A_Sniper_01"),
                             (f"{mil}/SM_Wep_Mod_Scope_01", f"{mil}/SM_Wep_Preset_A_Sniper_01")):
        a = by[part_id]["attachment"]
        assert host_id not in [e["host"] for e in a["compatible_hosts"] + a["pending_hosts"]], (part_id, host_id)  # Heavy refuses muzzle; Preset_A fills muzzle and optic
    mounts = by[f"{mil}/SM_Wep_Preset_A_Sniper_01"]["geometry"]["mounts"]
    assert mounts["magazine"]["source"] == "none" and mounts["magazine"]["reason"] != "slot_disabled"  # the magazine slot is left open (no seat to place at, not refused)


def test_ac139_5_a_cross_setting_pair_is_never_a_candidate(tmp_path):
    d, _ex, _rep = build(tmp_path, GW.cross_world(), rules=W.sight_rules())  # no shared setting: each pack is a setting of its own
    by = W.by_id(d)
    for name in (GW.SCOPE, GW.SILENCER, GW.MAG_RIFLE, GW.MAG_DRUM):
        a = by[GW.pid(name, GW.OTHER)]["attachment"]
        assert a["compatible_hosts"] == [] and a["pending_hosts"] == [], name


def test_ac139_the_refused_slot_host_set_of_the_world_is_the_literal_set(g1):
    refused = {(rec["id"].split("/", 1)[1], slot) for rec in g1.directory["weapons"] for slot, m in ((rec.get("geometry") or {}).get("mounts") or {}).items()
               if m["source"] == "none" and m["reason"] == "slot_disabled"}
    assert {(GW.PRESET, "optic"), (GW.PRESET, "muzzle")} <= refused and not {(GW.PRESET_MAG, "optic"), (GW.PRESET_MAG, "muzzle")} & refused
    assert {(GW.ROCKET, "optic"), (GW.NAILGUN, "optic"), (GW.MINIGUN, "optic")} <= refused  # the shotgun's muzzle is not a mount refusal: A8-2 vetoes the suppressor


# -- the well pass: cached per pair, the same as a recompute ------------------------------------------------------------------------------


def test_the_well_pass_caches_each_pair_and_a_hit_equals_a_recompute(tmp_path):
    world = GW.cross_world()
    cat, root = W.write_world(tmp_path, world)
    cache: dict = {}

    def run():
        return dirmod.build_directory_report(cat, overrides=empty_overrides(), pack_settings=W.pack_settings(world), rules=GW.cross_rules(),
                                             threejs_v2_dir=root, geometry_cache=cache)

    d1, _ex, r1 = run()
    wells = sorted(k for k in cache if k.startswith("well|"))
    parts = sorted(k for k in cache if k.startswith("fitpart|"))
    assert wells and parts
    assert all(k.count("|") == 2 for k in wells) and all(k.count("|") == 1 for k in parts)  # well|<part id>|<host id>, fitpart|<part id>
    assert (r1["fit_stats"]["computed"], r1["fit_stats"]["cached"]) == (len(wells) + len(parts), 0)
    # a second build over the same files and the same cache reads no mesh for the pass, and gives the same directory
    d2, _ex, r2 = run()
    assert (r2["fit_stats"]["computed"], r2["fit_stats"]["cached"]) == (0, len(wells) + len(parts))
    assert json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True)
    # touching one part's file (its mtime is part of the key) recomputes that part's pairs and no other
    victim = next(r for r in d1["weapons"] if r["id"] == GW.pid(GW.MAG_RIFLE))
    path = root / victim["files"]["glb"]
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    mine = len([k for k in wells if k.startswith(f"well|{victim['id']}|")])
    assert mine >= 1
    d3, _ex, r3 = run()
    assert (r3["fit_stats"]["computed"], r3["fit_stats"]["cached"]) == (mine, len(wells) + len(parts) - mine)
    assert json.dumps(d3, sort_keys=True) == json.dumps(d1, sort_keys=True)


# -- AC143, INV-25: determinism -----------------------------------------------------------------------------------------------------------

PROBE = """
import sys, json, hashlib
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import importlib.util
spec = importlib.util.spec_from_file_location("g1_world", Path(sys.argv[2]) / "g1_world.py")
GW = importlib.util.module_from_spec(spec); spec.loader.exec_module(GW)
W = GW.W
from synty_inventory.weapons import directory as dirmod
from synty_inventory.weapons.overrides import empty_overrides
world = GW.world()
cat, root = W.write_world(Path(sys.argv[3]), world)
d, _ex, _rep = dirmod.build_directory_report(cat, overrides=empty_overrides(), pack_settings=W.pack_settings(world), rules=W.sight_rules(),
                                              threejs_v2_dir=root, geometry_cache={})
blob = json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
print(d["fit_digest"], hashlib.sha256(blob.encode()).hexdigest())
"""


def _run_probe(tmp_path, seed):
    src = str(Path(__file__).resolve().parent.parent / "src")
    env = {**os.environ, "PYTHONHASHSEED": str(seed)}
    out = subprocess.run([sys.executable, "-c", PROBE, src, str(FIX), str(tmp_path / f"seed{seed}")], env=env, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    return out.stdout.split()


def test_ac143_two_builds_under_different_hash_seeds_give_identical_bytes_and_the_literal_fit_digest(tmp_path):
    (tmp_path / "seed0").mkdir()
    (tmp_path / "seed1").mkdir()
    fit0, sha0 = _run_probe(tmp_path, 0)
    fit1, sha1 = _run_probe(tmp_path, 1)
    assert (fit0, sha0) == (fit1, sha1)
    # the FAKE_G1 world's digest; a change of a measure, a rule or a detector moves it (INV-25). E2 re-pin (E2-Q2, E2-Q3), from 5ad9a64f66683826 at S8:
    # four rod-rifle hosts' barrel_end evidence ring -> round_section, and the fused-magazine preset's located well_ref is gone: nothing else moved
    assert fit0 == "9e88713e0a47d5d0"
    print(f"AC143: fit_digest {fit0}, directory sha256 {sha0[:16]}")
