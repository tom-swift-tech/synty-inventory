"""W8c compatibility: twin detection (AC71), tiers and ordering (AC72), fit_span / fit_bore (AC73), pending hosts (AC75), INV-14.

docs/weapon_attachments.md 5 and 11. The world is FAKE_CompA / FAKE_CompB of tests/fixtures/weapons/w8c_compat.py; every expected
tier, score, signal and ordering below is a literal worked out by hand from the rules in that file's docstring (same pack 0.7 base,
cross pack 0.4, +0.1 for a fitting span, +0.1 for a good ring bore, -0.1 for a bad one, clamped to 0.6..0.9 / 0.3..0.6; twin 0.95).
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8c_compat", FIX / "w8c_compat.py")
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)

from synty_inventory.weapons import compat  # noqa: E402
from synty_inventory.weapons.directory import to_text  # noqa: E402
from synty_inventory.weapons.rules import attachment_rules, load_rules  # noqa: E402
from synty_inventory.weapons.schema import validate_directory  # noqa: E402

A_, B_, G_, E_, D_ = (W.H[n] for n in (W.ALPHA, W.BETA, W.GAMMA, W.EPSILON, W.DELTA))
TWIN, SAME, CROSS = "twin", "same_pack_fit", "cross_pack_fit"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return W.build(tmp_path_factory.mktemp("w8c_compat"))[0]


def rec(directory, part):
    return W.by_id(directory)[W.P[part]]


# part -> (compatible_hosts as (host, tier, score) in stored order, pending_hosts as (host, tier) in stored order)
EXPECTED = {
    W.SCOPE: ([(A_, TWIN, 0.95), (E_, TWIN, 0.95)], [(B_, SAME), (D_, CROSS)]),
    W.SCOPE_TIGHT: ([(A_, SAME, 0.8), (E_, SAME, 0.8)], [(B_, SAME), (D_, CROSS)]),
    W.SCOPE_WIDE: ([(A_, SAME, 0.7), (E_, SAME, 0.7)], [(B_, SAME), (D_, CROSS)]),
    W.SCOPE_GIANT: ([(A_, SAME, 0.7), (E_, SAME, 0.7)], [(B_, SAME), (D_, CROSS)]),
    # W8l (A4, spec 5.1 family_free_slots): a muzzle part needs no name overlap, so the pistol GAMMA (no "rifle" token) joins every silencer's list
    # at the same-pack base 0.7 (a square body: no ring, no bore signal) and sorts by host id beside BETA (0.7)
    W.SIL: ([(G_, SAME, 0.7), (B_, SAME, 0.7), (A_, SAME, 0.6), (E_, SAME, 0.6)], []),
    W.SIL_SLIM: ([(A_, SAME, 0.8), (E_, SAME, 0.8), (G_, SAME, 0.7), (B_, SAME, 0.7), (D_, CROSS, 0.5)], []),
    W.SIL_BRAKE: ([(E_, TWIN, 0.95), (G_, SAME, 0.7), (B_, SAME, 0.7), (A_, SAME, 0.6)], []),
    W.MAG: ([(A_, TWIN, 0.95)], [(B_, SAME), (E_, SAME), (D_, CROSS)]),
    # W8l: an underbarrel part needs no name overlap either; the three rifles have no foregrip child and no probe for the slot, so they are pending
    W.GRIP: ([(G_, TWIN, 0.95)], [(A_, SAME), (B_, SAME), (E_, SAME), (D_, CROSS)]),
    W.LASER: ([(G_, TWIN, 0.95)], [(D_, CROSS)]),
    W.ALT_SCOPE: ([(A_, TWIN, 0.95), (E_, TWIN, 0.95)], [(B_, CROSS)]),
}


# --- AC71: twin detection -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("a", "b", "twin"), [
    ((0.06, 0.08, 0.2), (0.06, 0.08, 0.2), True),  # equal
    ((0.06, 0.08, 0.2), (0.2, 0.06, 0.08), True),  # sorted per axis: the authored axis order does not matter
    ((0.06, 0.08, 0.2), (0.0618, 0.0824, 0.206), True),  # 2.9 % / 3.0 % / 2.9 % of the larger: inside 3 %
    ((0.06, 0.08, 0.2), (0.057, 0.076, 0.19), False),  # the 5 % fixture (0.95 x) is not a twin
    ((0.06, 0.08, 0.2), (0.063, 0.084, 0.21), False),  # 5 % the other way: 0.003 / 0.063 = 4.8 %
    ((0.06, 0.08, 0.2), (0.0638, 0.08, 0.2), False),  # one axis at 6 % is enough to fail
    ((0.010, 0.020, 0.030), (0.0107, 0.0207, 0.0307), True),  # tiny part: 0.7 mm is inside the 0.8 mm floor although it is 7 %
    ((0.010, 0.020, 0.030), (0.0109, 0.020, 0.030), False),  # 0.9 mm is outside the floor and outside 3 %
])
def test_ac71_is_twin_literals(a, b, twin):
    assert compat.is_twin(a, b) is twin


def test_ac71_the_five_percent_part_is_not_a_twin_and_the_equal_one_is_a_twin_of_both_hosts(built):
    scope, tight = rec(built, W.SCOPE)["attachment"], rec(built, W.SCOPE_TIGHT)["attachment"]
    assert [e["host"] for e in scope["compatible_hosts"] if e["tier"] == TWIN] == [A_, E_]
    assert all(e["tier"] != TWIN for e in tight["compatible_hosts"] + tight["pending_hosts"])
    for part in (W.SCOPE_WIDE, W.SCOPE_GIANT):  # 1.2 x and 1.8 x are not twins either
        att = rec(built, part)["attachment"]
        assert all(e["tier"] != TWIN for e in att["compatible_hosts"] + att["pending_hosts"])


def test_ac71_one_part_that_twins_several_hosts_gets_twin_multi_and_a_part_with_one_twin_does_not(built):
    assert "twin_multi" in rec(built, W.SCOPE)["review"]["reasons"]
    assert "twin_multi" in rec(built, W.ALT_SCOPE)["review"]["reasons"]
    for part in (W.MAG, W.GRIP, W.LASER, W.SIL_BRAKE, W.SCOPE_TIGHT, W.SIL):
        assert "twin_multi" not in rec(built, part)["review"]["reasons"], part


def test_ac71_a_twin_in_another_pack_is_still_a_twin(built):
    # judgment call (compat.py docstring): twin evidence is geometric, so the pack does not matter
    got = W.hosts_of(rec(built, W.ALT_SCOPE))
    assert got == [(A_, TWIN, 0.95), (E_, TWIN, 0.95)]


# --- AC72: tiers, scores and ordering ----------------------------------------------------------------------------------


@pytest.mark.parametrize("part", sorted(EXPECTED))
def test_ac72_each_part_lists_its_hosts_in_the_hand_derived_tiers_scores_and_order(built, part):
    compatible, pending = EXPECTED[part]
    att = rec(built, part)["attachment"]
    assert W.hosts_of(rec(built, part)) == compatible
    assert [(e["host"], e["tier"]) for e in att["pending_hosts"]] == pending
    assert all(set(e) == {"host", "tier"} for e in att["pending_hosts"])  # a pending host has no score, no signals


def test_ac72_the_signals_and_replaces_of_a_few_entries_are_literal(built):
    def entry(part, host):
        return next(e for e in rec(built, part)["attachment"]["compatible_hosts"] if e["host"] == host)

    assert entry(W.SCOPE, A_)["signals"] == ["affinity", "family_overlap", "fit_span", "mount_available", "twin"]
    assert entry(W.SCOPE, A_)["replaces"] == ["SM_Wep_Rifle_Alpha_01_Scope"]
    assert entry(W.SCOPE_TIGHT, A_)["signals"] == ["affinity", "family_overlap", "fit_span", "mount_available"]
    assert entry(W.SCOPE_WIDE, A_)["signals"] == ["affinity", "family_overlap", "mount_available"]  # 1.2 x: no span bonus
    assert entry(W.SIL, A_)["signals"] == ["affinity", "bore_mismatch", "family_overlap", "mount_available"]
    assert entry(W.SIL_SLIM, A_)["signals"] == ["affinity", "family_overlap", "fit_bore", "mount_available"]
    assert entry(W.SIL_SLIM, A_)["replaces"] == []  # no baked muzzle device on ALPHA
    assert entry(W.SIL_BRAKE, E_)["replaces"] == ["SM_Wep_Rifle_Epsilon_01_Brake"]
    assert entry(W.ALT_SCOPE, A_)["signals"] == ["affinity", "fit_span", "mount_available", "twin"]  # no family token
    assert entry(W.SIL_SLIM, D_)["signals"] == ["affinity", "family_overlap", "fit_bore", "mount_available"]


def test_ac72_same_pack_fit_needs_family_overlap_and_affinity_and_another_pack_only_reaches_cross_pack_fit(built):
    for part in EXPECTED:
        part_rec = rec(built, part)
        for e in part_rec["attachment"]["compatible_hosts"] + part_rec["attachment"]["pending_hosts"]:
            same_pack = e["host"].split("/")[0] == part_rec["pack"]
            if e["tier"] == SAME:
                assert same_pack
            if not same_pack and e["tier"] != TWIN:
                assert e["tier"] == CROSS and e.get("score", 0.5) <= 0.6
    assert G_ not in {e["host"] for e in rec(built, W.MAG)["attachment"]["compatible_hosts"] + rec(built, W.MAG)["attachment"]["pending_hosts"]}
    assert D_ not in {e["host"] for e in rec(built, W.ALT_SCOPE)["attachment"]["compatible_hosts"] + rec(built, W.ALT_SCOPE)["attachment"]["pending_hosts"]}


def test_ac72_the_cross_pack_candidate_is_flagged_on_the_part_and_nothing_else_is(built):
    flagged = {p for p in EXPECTED if "compat_cross_pack" in rec(built, p)["review"]["reasons"]}
    assert flagged == {W.SCOPE, W.SCOPE_TIGHT, W.SCOPE_WIDE, W.SCOPE_GIANT, W.SIL_SLIM, W.MAG, W.GRIP, W.LASER, W.ALT_SCOPE}


def test_ac72_the_order_is_rank_then_descending_score_then_host(built):
    for part in EXPECTED:
        entries = rec(built, part)["attachment"]["compatible_hosts"]
        keys = [(compat.tier_rank(e["tier"]), -e["score"], e["host"]) for e in entries]
        assert keys == sorted(keys)
    # the descending score is visible in the literals: SIL lists the two 0.7 entries (GAMMA, BETA: by host id) before the two 0.6 entries
    # although BETA sorts after ALPHA
    assert [h for h, _, _ in EXPECTED[W.SIL][0]] == [G_, B_, A_, E_]


def test_ac72_two_builds_are_identical(built, tmp_path):
    again = W.build(tmp_path)[0]
    assert to_text(again) == to_text(built)


@pytest.mark.parametrize(("family", "affine", "same_pack", "expected"), [
    (True, True, True, SAME), (True, False, True, None), (False, True, True, None), (False, False, True, None),
    (True, True, False, CROSS), (False, True, False, CROSS), (True, False, False, None),
])
def test_ac72_the_tier_rules_as_a_truth_table(family, affine, same_pack, expected):
    got = compat.candidate(part_view(pack="P" if same_pack else "Q", tokens=frozenset({"x"}) if family else frozenset({"y"})),
                           host_view(archetype="rifle" if affine else "pistol", mounts={"optic": mount()}),
                           verdict=None, twin=False, affinity=AFFINITY, params=PARAMS)
    assert (got["tier"] if got else None) == expected


def test_ac72_a_cross_pack_score_never_exceeds_0_6_and_a_same_pack_one_stays_between_0_6_and_0_9():
    cross = compat.candidate(part_view(pack="Q", foot_length_m=0.05), host_view(mounts={"optic": mount()}), verdict=None,
                             twin=False, affinity=AFFINITY, params=PARAMS)
    same = compat.candidate(part_view(foot_length_m=0.05), host_view(mounts={"optic": mount()}), verdict=None, twin=False,
                            affinity=AFFINITY, params=PARAMS)
    assert (cross["tier"], cross["score"]) == (CROSS, 0.5)
    assert (same["tier"], same["score"]) == (SAME, 0.8)
    assert compat.score_of(SAME, "fits", "good", PARAMS) == 0.9  # 0.7 + 0.1 + 0.1: the top of the band
    assert compat.score_of(SAME, None, "bad", PARAMS) == 0.6  # 0.7 - 0.1: the bottom of the band
    assert compat.score_of(CROSS, "fits", "good", PARAMS) == 0.6  # 0.4 + 0.2
    assert compat.score_of(CROSS, None, "bad", PARAMS) == 0.3


def test_ac72_a_twin_does_not_need_family_or_affinity_and_a_mech_host_is_vetoed():
    odd = compat.candidate(part_view(tokens=frozenset({"zzz"})), host_view(archetype="pistol", mounts={"optic": mount()}),
                           verdict=None, twin=True, affinity=AFFINITY, params=PARAMS)
    assert odd["tier"] == TWIN and odd["score"] == 0.95
    mech = compat.candidate(part_view(), host_view(flags={"mech_scale"}, mounts={"optic": mount()}), verdict=None, twin=True,
                            affinity=AFFINITY, params=PARAMS)
    assert mech is None  # a hand-scale part never fits a mech-scale gun, twin or not
    both = compat.candidate(part_view(flags={"mech_scale"}), host_view(flags={"mech_scale"}, mounts={"optic": mount()}),
                            verdict=None, twin=False, affinity=AFFINITY, params=PARAMS)
    assert both["tier"] == SAME


# --- AC73: fit_span and fit_bore ---------------------------------------------------------------------------------------


def test_ac73_fit_span_cuts_use_binary_exact_numbers():
    child = {"span_m": 0.5, "span_source": "child_foot"}
    assert compat.fit_span(0.5, child) == "fits"  # exactly 1.0 x
    assert compat.fit_span(0.75, child) == "neutral"  # exactly 1.5 x
    assert compat.fit_span(0.76, child) == "over"  # a child_foot span is a lower bound: above 1.5 x it still does not veto
    assert compat.fit_span(0.76, {"span_m": 0.5, "span_source": "probe"}) == "veto"
    assert compat.fit_span(0.75, {"span_m": 0.5, "span_source": "probe"}) == "neutral"
    assert compat.fit_span(None, child) is None and compat.fit_span(0.5, {"span_m": None}) is None and compat.fit_span(0.5, None) is None


def test_ac73_a_foot_1_2x_a_child_foot_span_still_fits_and_1_8x_a_probe_span_is_vetoed():
    host = host_view(mounts={"optic": mount(span_m=0.06)})
    got = compat.candidate(part_view(foot_length_m=0.072), host, verdict=None, twin=False, affinity=AFFINITY, params=PARAMS)
    assert got["tier"] == SAME and got["score"] == 0.7  # 1.2 x: neutral, no span bonus
    probe = host_view(mounts={"optic": mount(span_m=0.06, span_source="probe")})
    assert compat.candidate(part_view(foot_length_m=0.108), probe, verdict=None, twin=False, affinity=AFFINITY, params=PARAMS) is None
    assert compat.candidate(part_view(foot_length_m=0.072), probe, verdict=None, twin=False, affinity=AFFINITY, params=PARAMS)["tier"] == SAME


def test_ac73_a_foot_1_8x_a_child_foot_span_is_not_vetoed_in_the_built_directory(built):
    # Giant_01: foot 0.108 against the 0.06 child_foot span of the Scope child of ALPHA and EPSILON
    assert W.hosts_of(rec(built, W.SCOPE_GIANT)) == [(A_, SAME, 0.7), (E_, SAME, 0.7)]
    assert W.hosts_of(rec(built, W.SCOPE_WIDE)) == [(A_, SAME, 0.7), (E_, SAME, 0.7)]


def test_ac73_a_cross_pack_part_needs_a_foot_that_fits_a_measured_seat():
    over = compat.candidate(part_view(pack="Q", foot_length_m=0.108), host_view(mounts={"optic": mount(span_m=0.06)}),
                            verdict=None, twin=False, affinity=AFFINITY, params=PARAMS)
    assert over is None  # 1.8 x a child_foot span: not a veto, but also not a "measured fit" for another pack's part
    neutral = compat.candidate(part_view(pack="Q", foot_length_m=0.072), host_view(mounts={"optic": mount(span_m=0.06)}),
                               verdict=None, twin=False, affinity=AFFINITY, params=PARAMS)
    assert neutral["tier"] == CROSS and neutral["score"] == 0.4


def test_ac73_fit_bore_good_bad_and_ignored():
    ring = {"bore_d_m": 0.020, "bore_source": "ring"}
    assert compat.fit_bore(0.020, ring) == "good"
    assert compat.fit_bore(0.026, ring) == "good"  # 6 mm off a 20 mm bore: inside 35 % (7 mm)
    assert compat.fit_bore(0.028, ring) == "bad"  # 8 mm off
    assert compat.fit_bore(0.012, ring) == "bad"
    face = {"bore_d_m": 0.020, "bore_source": "face_extent"}
    assert compat.fit_bore(0.040, face) is None  # a face extent is polluted by slides and shrouds: ignored
    assert compat.fit_bore(None, ring) is None and compat.fit_bore(0.02, None) is None


def test_ac73_a_face_extent_mount_gives_no_bore_signal_in_the_built_directory(built):
    # BETA has a square barrel (face extent 0.0283): 0.026 would be a "good" bore and 0.013 a "bad" one if it counted (GAMMA, a square pistol
    # that the family-free muzzle rule of W8l lists as well, is the same case and sorts first at 0.7)
    assert W.hosts_of(rec(built, W.SIL))[:2] == [(G_, SAME, 0.7), (B_, SAME, 0.7)]
    slim_beta = next(e for e in rec(built, W.SIL_SLIM)["attachment"]["compatible_hosts"] if e["host"] == B_)
    assert slim_beta["score"] == 0.7 and "fit_bore" not in slim_beta["signals"] and "bore_mismatch" not in slim_beta["signals"]


def test_ac73_a_bad_ring_bore_blocks_a_cross_pack_candidate_and_a_good_one_admits_it(built):
    assert D_ not in {e["host"] for e in rec(built, W.SIL)["attachment"]["compatible_hosts"]}  # 0.026 against the 0.0130 ring
    assert (D_, CROSS, 0.5) in W.hosts_of(rec(built, W.SIL_SLIM))


# --- AC75: pending hosts ---------------------------------------------------------------------------------------------


def test_ac75_a_host_without_a_seat_is_pending_and_not_compatible(built):
    att = rec(built, W.SCOPE)["attachment"]
    assert B_ in {e["host"] for e in att["pending_hosts"]} and B_ not in {e["host"] for e in att["compatible_hosts"]}
    beta_optic = W.by_id(built)[B_]["geometry"]["mounts"]["optic"]
    assert beta_optic["source"] == "none"  # the reason it is pending


def test_ac75_no_host_is_in_both_lists_and_an_empty_compatible_list_is_allowed(built):
    for r in built["weapons"]:
        if r.get("attachment"):
            att = r["attachment"]
            assert not ({e["host"] for e in att["compatible_hosts"]} & {e["host"] for e in att["pending_hosts"]}), r["id"]
    assert rec(built, W.SIL)["attachment"]["pending_hosts"] == []  # every host has a muzzle seat (the probe)


def test_ac75_pending_entries_in_the_directory_keep_their_tier(built):
    assert [(e["host"], e["tier"]) for e in rec(built, W.MAG)["attachment"]["pending_hosts"]] == [(B_, SAME), (E_, SAME), (D_, CROSS)]


def test_ac75_the_default_export_view_of_pending_hosts_drops_the_cross_pack_candidate():
    pending = rec_pending([(B_, SAME), (E_, SAME), (D_, CROSS)])
    assert compat.export_pending(pending, SAME) == [B_, E_]  # ids only, the cross-pack DELTA is not a "fits" for a game
    assert compat.export_pending(pending, CROSS) == [B_, E_, D_]  # sorted by (rank, host)
    assert compat.export_pending(pending, TWIN) == []
    assert compat.export_pending([], SAME) == []


def test_ac75_the_export_view_of_compatible_hosts_filters_by_tier_too():
    entries = [{"host": "a", "tier": TWIN, "score": 0.95}, {"host": "b", "tier": SAME, "score": 0.8},
               {"host": "c", "tier": CROSS, "score": 0.5}]
    assert [e["host"] for e in compat.export_compatible(entries, SAME)] == ["a", "b"]
    assert [e["host"] for e in compat.export_compatible(entries, TWIN)] == ["a"]
    assert [e["host"] for e in compat.export_compatible(entries, CROSS)] == ["a", "b", "c"]


def test_ac75_pending_of_the_built_directory_through_the_export_filter(built):
    assert compat.export_pending(rec(built, W.MAG)["attachment"]["pending_hosts"], SAME) == [B_, E_]
    assert compat.export_pending(rec(built, W.SCOPE)["attachment"]["pending_hosts"], SAME) == [B_]
    assert compat.export_pending(rec(built, W.ALT_SCOPE)["attachment"]["pending_hosts"], SAME) == []  # only a cross-pack candidate


def test_ac75_a_host_with_a_default_tier_pending_slot_gets_mount_missing_and_others_do_not(built):
    flagged = {r["asset_id"] for r in built["weapons"] if "mount_missing" in r["review"]["reasons"]}
    # BETA: no optic and no magazine seat but candidates for both; EPSILON: no magazine seat. DELTA has only cross-pack candidates.
    # W8l: the foregrip part now lists the rifles with no name overlap (underbarrel is a family-free slot) and ALPHA has no underbarrel seat.
    assert flagged == {W.ALPHA, W.BETA, W.EPSILON}


# --- INV-14 in the schema --------------------------------------------------------------------------------------------


def test_the_built_fixture_directory_validates(built):
    assert validate_directory(built) == []


def break_(built, part, mutate):
    doc = copy.deepcopy(built)
    mutate(next(r for r in doc["weapons"] if r["id"] == W.P[part])["attachment"])
    return validate_directory(doc)


def test_inv14_a_host_listed_twice_a_wrong_replaces_and_unsorted_pending_are_schema_errors(built):
    errs = break_(built, W.SCOPE, lambda a: a["compatible_hosts"].append(copy.deepcopy(a["compatible_hosts"][0])))
    assert any("listed twice" in e for e in errs)
    errs = break_(built, W.SCOPE, lambda a: a["compatible_hosts"][0].update(replaces=["b", "a"]))
    assert any("replaces" in e and "sorted" in e for e in errs)
    errs = break_(built, W.MAG, lambda a: a["pending_hosts"].reverse())
    assert any("pending_hosts" in e and "sorted" in e for e in errs)
    errs = break_(built, W.MAG, lambda a: a["pending_hosts"].append(copy.deepcopy(a["pending_hosts"][0])))
    assert any("pending_hosts" in e for e in errs)


# --- helpers for the pure tests --------------------------------------------------------------------------------------


def rec_pending(rows):
    return [{"host": h, "tier": t} for h, t in rows]


def part_view(**kw):
    base = {"id": "P/part", "pack": "P", "slot": "optic", "kind": "scope", "flags": set(), "tokens": frozenset({"x"}),
            "foot_length_m": 0.06, "mate_d_m": None, "setting": ("setting", "s")}  # A2: one setting for P and Q
    return {**base, **kw}


def host_view(**kw):
    base = {"id": "P/host", "pack": "P", "archetype": "rifle", "flags": set(), "mounts": {}, "tokens": frozenset({"x"}),
            "setting": ("setting", "s")}
    return {**base, **kw}


def mount(**kw):
    base = {"source": "child_node", "span_m": 0.06, "span_source": "child_foot", "bore_d_m": None, "bore_source": None,
            "occupied_by": [], "reason": None}
    return {**base, **kw}


AFFINITY = {"optic": {"scope": ["rifle"], "default": ["rifle"]}}
PARAMS = compat._params(attachment_rules(load_rules()))
