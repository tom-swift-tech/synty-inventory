"""W8i: pack-generic same-pack sights (AC94) and the excluded flare and prop hosts (AC95); docs/weapon_attachments.md 5.1 (A3) and 7.

Fixture hosts and parts are in ``fixtures/weapons/w8i_world.py``. Expected scores and signals are literals: the tier base of
``same_pack_fit`` is 0.7 and a span-less probe seat adds nothing (no ``fit_span``), so a sight's score is exactly 0.7.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("w8i_world", Path(__file__).parent / "fixtures" / "weapons" / "w8i_world.py")
X = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(X)
W, A = X.W, X.A

from synty_inventory.weapons import mounts as M  # noqa: E402
from synty_inventory.weapons.rules import load_rules  # noqa: E402

# -- AC94 ----------------------------------------------------------------------------------------------------

P1, P2 = "FAKE_GenSight", "FAKE_GenOther"
RIFLE, PISTOL, SHOTGUN, SWORD, OTHER = ("SM_Wep_Rifle_Gen_01", "SM_Wep_Pistol_Gen_01", "SM_Wep_Shotgun_Gen_01", "SM_Wep_Sword_Gen_01",
                                       "SM_Wep_Rifle_Other_01")
SCOPE = "SM_Wep_Sniper_Scope_01"  # an optic that shares no name token with any host
SETTING = {P1: "s1", P2: "s1"}  # one setting, so the other-pack host passes the setting gate and only the tier rules decide


def gen_world():
    return {
        P1: {"parts": {X.SIGHT_FRONT: W.sight_part, SCOPE: A.optic},
             "hosts": {RIFLE: X.rifle(RIFLE), PISTOL: X.rifle(PISTOL), SHOTGUN: X.prism(SHOTGUN),
                       SWORD: W.host_node(SWORD, A.G.box((-0.02, 0.0, -0.5), (0.02, 0.04, 0.5)))}},
        P2: {"hosts": {OTHER: X.rifle(OTHER)}},
    }


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    return W.by_id(W.build(tmp_path_factory.mktemp("w8i_gen"), gen_world(), rules=W.sight_rules(SETTING))[0])


def test_ac94_the_fixture_hosts_are_what_the_case_needs(gen):
    for host in (RIFLE, PISTOL):
        assert X.seat(gen[f"{P1}/{host}"], "sight_front")["source"] == "probe"  # a probe seat, so mount_available holds
    shotgun = X.seat(gen[f"{P1}/{SHOTGUN}"], "sight_front")
    assert shotgun["source"] == "none" and shotgun["reason"] == "probe_unavailable"
    assert gen[f"{P1}/{SWORD}"]["geometry"]["mounts"] is None  # a melee record is no host
    assert X.seat(gen[f"{P2}/{OTHER}"], "sight_front")["source"] == "probe"


def test_ac94_a_same_pack_sight_needs_no_name_overlap_and_scores_the_tier_base(gen):
    got = X.entries(gen[f"{P1}/{X.SIGHT_FRONT}"])
    assert sorted(got) == [f"{P1}/{PISTOL}", f"{P1}/{RIFLE}"]
    for e in got.values():
        assert e["tier"] == "same_pack_fit" and e["score"] == 0.7
        assert e["signals"] == ["affinity", "mount_available"]  # no family_overlap, no fit_span: the probe seat has no span


def test_ac94_a_same_pack_host_without_a_seat_is_pending_not_listed(gen):
    rec = gen[f"{P1}/{X.SIGHT_FRONT}"]
    assert {h: e["tier"] for h, e in X.entries(rec, "pending_hosts").items()} == {f"{P1}/{SHOTGUN}": "same_pack_fit"}
    assert f"{P1}/{SHOTGUN}" not in X.entries(rec)


def test_ac94_a_melee_record_and_an_other_pack_host_get_nothing(gen):
    rec = gen[f"{P1}/{X.SIGHT_FRONT}"]
    everything = {**X.entries(rec), **X.entries(rec, "pending_hosts")}
    assert f"{P1}/{SWORD}" not in everything  # not an eligible host
    assert f"{P2}/{OTHER}" not in everything  # same setting, but a cross-pack sight still needs a measured fit and the probe seat has none


def test_ac94_the_relaxation_is_for_the_sight_slots_only(gen):
    rec = gen[f"{P1}/{SCOPE}"]
    assert rec["attachment"]["slot"] == "optic"
    for key in ("compatible_hosts", "pending_hosts"):
        assert not [e for e in rec["attachment"][key] if e["tier"] == "same_pack_fit"], key  # the rifle shares no token with the scope


def test_ac94_a_sight_that_shares_a_name_token_keeps_family_overlap_in_its_signals(tmp_path):
    host = "SM_Wep_Rifle_Iron_01"  # shares `iron` with the part
    d = W.build(tmp_path, {P1: {"parts": {X.SIGHT_FRONT: W.sight_part}, "hosts": {host: X.rifle(host)}}}, rules=W.sight_rules(SETTING))[0]
    got = X.entries(W.by_id(d)[f"{P1}/{X.SIGHT_FRONT}"])[f"{P1}/{host}"]
    assert got["tier"] == "same_pack_fit" and got["signals"] == ["affinity", "family_overlap", "mount_available"]


# -- AC95 ----------------------------------------------------------------------------------------------------

PX = "FAKE_Excl"
FLARE, BRIEFCASE, PROP, PLAIN = ("SM_Wep_Pistol_Flare_01", "SM_Wep_Prop_Briefcase_Flaregun_01", "SM_Wep_Rifle_Prop_01", "SM_Wep_Rifle_Plain_01")
SCOPED = "SM_Wep_Rifle_Scoped_01"  # W8j: the reference for the optic mount of the excluded hosts (a baked scope; PLAIN no longer has one)
EXCLUDED = (FLARE, BRIEFCASE, PROP)
SCOPE_AT = (0.0, 0.10, -0.05)


def excl_world():
    def host(name):
        return X.rifle(name, [("Scope", A.optic(), SCOPE_AT)])  # a baked scope, so the optic mount is a child_node that must not move

    # W8j (item 8 A): a baked Scope is a body child and refuses both sight slots of its host, so PLAIN, the one host whose sight slots must
    # stay probe seats, is a bare rifle and SCOPED carries the reference optic mount
    hosts = {h: host(h) for h in (*EXCLUDED, SCOPED)}
    hosts[PLAIN] = X.rifle(PLAIN)
    return {PX: {"parts": {X.SIGHT_FRONT: W.sight_part, X.SIGHT_REAR: W.sight_part}, "hosts": hosts}}


@pytest.fixture(scope="module")
def excl(tmp_path_factory):
    return W.by_id(W.build(tmp_path_factory.mktemp("w8i_excl"), excl_world())[0])


@pytest.fixture(scope="module")
def excl_sights_only(tmp_path_factory):
    # A8 erratum (2026-10-26): the shipped tool class now names `flare`, so the FLARE host loses every slot. The sight-slot NAME RULE alone (attach_host_never
    # lists `flare` for the two sight slots; the other slots untouched) is the mechanism this test exercises, so it is built with a tool row without `flare`.
    rules = W.sight_rules()
    rules["attachment_rules"]["attach_host_class"]["tool"] = [t for t in rules["attachment_rules"]["attach_host_class"]["tool"] if t != "flare"]
    return W.by_id(W.build(tmp_path_factory.mktemp("w8i_excl_sights"), excl_world(), rules=rules)[0])


def test_ac95_a_flare_gun_a_briefcase_flaregun_and_a_prop_have_both_sight_seats_disabled(excl):
    for host in EXCLUDED:
        m = excl[f"{PX}/{host}"]["geometry"]["mounts"]
        for slot in ("sight_front", "sight_rear"):
            assert m[slot]["source"] == "none" and m[slot]["reason"] == "slot_disabled", (host, slot)
            assert m[slot]["point"] is None and m[slot]["occupied_by"] == []


def test_ac95_their_optic_mount_is_unchanged_and_the_plain_host_is_seated_by_the_probe(excl):
    plain = excl[f"{PX}/{SCOPED}"]["geometry"]["mounts"]  # the optic reference (see excl_world)
    assert plain["optic"]["source"] == "child_node"
    bare = excl[f"{PX}/{PLAIN}"]["geometry"]["mounts"]
    assert bare["sight_front"]["source"] == bare["sight_rear"]["source"] == "probe"
    # A5 item 0: a prop host loses every slot. A8 erratum (2026-10-26): so does the flare pistol, a tool host now (the shipped outcome for the real name)
    for host in (FLARE, BRIEFCASE, PROP):
        m = excl[f"{PX}/{host}"]["geometry"]["mounts"]
        assert m["optic"]["source"] == m["muzzle"]["source"] == "none" and m["optic"]["reason"] == m["muzzle"]["reason"] == "slot_disabled", host


def test_ac95_the_sight_name_rule_alone_leaves_the_optic_and_the_other_slots_of_the_host(excl_sights_only):
    # the mechanism (shipped tool row minus `flare`): attach_host_never `flare` takes the two sight slots and no other
    plain = excl_sights_only[f"{PX}/{SCOPED}"]["geometry"]["mounts"]
    m = excl_sights_only[f"{PX}/{FLARE}"]["geometry"]["mounts"]
    for slot in ("sight_front", "sight_rear"):
        assert m[slot]["source"] == "none" and m[slot]["reason"] == "slot_disabled", slot
    assert m["optic"]["source"] == "child_node" and m["optic"]["occupied_by"] == [f"{FLARE}_Scope"]
    assert m["optic"]["point"] == plain["optic"]["point"] and m["optic"]["span_m"] == plain["optic"]["span_m"]
    assert m["muzzle"]["source"] == "probe"  # no other slot is touched


def test_ac95_no_sight_candidate_lists_an_excluded_host_listed_or_pending(excl):
    for part in (X.SIGHT_FRONT, X.SIGHT_REAR):
        att = excl[f"{PX}/{part}"]["attachment"]
        got = {e["host"] for key in ("compatible_hosts", "pending_hosts") for e in att[key]}
        assert got == {f"{PX}/{PLAIN}"}, part  # the one host whose name has none of the excluded tokens


def test_ac95_an_add_override_still_lists_the_pair_as_override(tmp_path):
    ovr = W.overrides_doc(ids={f"{PX}/{X.SIGHT_FRONT}": {"compatible": {"add": [f"{PX}/{FLARE}"]}}})
    d = W.by_id(W.build(tmp_path, excl_world(), overrides=ovr)[0])
    att = d[f"{PX}/{X.SIGHT_FRONT}"]["attachment"]
    assert {e["tier"] for e in att["pending_hosts"] if e["host"] == f"{PX}/{FLARE}"} == {"override"}  # the seat is none: pending
    assert f"{PX}/{FLARE}" not in {e["host"] for e in d[f"{PX}/{X.SIGHT_REAR}"]["attachment"]["pending_hosts"]}  # the rear part had no add


def test_ac95_the_shipped_table_lists_flare_flaregun_and_prop_for_both_sight_slots():
    table = load_rules()["attachment_rules"]["attach_host_never"]
    # W8j (item 8 E): the sight slots also list the water, watergun and toy names, and the optic slot those three
    # A5 item 0: `prop` also names optic (last) and the four other slots
    assert table == {"optic": ["water", "watergun", "toy", "prop"],
                     "sight_front": ["flare", "flaregun", "prop", "water", "watergun", "toy"],
                     "sight_rear": ["flare", "flaregun", "prop", "water", "watergun", "toy"],
                     "muzzle": ["prop"], "underbarrel": ["prop"], "magazine": ["prop"], "laser_light": ["prop"]}


@pytest.mark.parametrize("asset_id,slots", [
    ("SM_Wep_Pistol_Flare_01", ["optic", "muzzle", "underbarrel", "magazine", "laser_light", "sight_front", "sight_rear"]),  # A8 erratum (2026-10-26): `flare` alone is a tool token
    ("SM_Prop_Briefcase_Flaregun_01", ["optic", "muzzle", "underbarrel", "magazine", "laser_light", "sight_front", "sight_rear"]),  # A5 item 0
    ("SM_Wep_Rifle_Prop_01", ["optic", "muzzle", "underbarrel", "magazine", "laser_light", "sight_front", "sight_rear"]),  # A5 item 0
    ("SM_Wep_Flare_Gun_01", ["optic", "muzzle", "underbarrel", "magazine", "laser_light", "sight_front", "sight_rear"]),  # A6 (W8n): `flaregun` is a tool token; the join of `flare` and `gun`
    ("SM_Wep_Rifle_Properly_01", []),  # a token, not a substring
    ("SM_Wep_Rifle_Assault_01", []),
])
def test_ac95_excluded_slots_match_whole_name_tokens(asset_id, slots):
    assert M.excluded_slots(asset_id, load_rules()["attachment_rules"]) == slots


def test_ac95_the_joined_form_of_neighbouring_tokens_matches_too():
    tables = {"attach_host_never": {"sight_front": ["flaregun"]}}
    assert M.excluded_slots("SM_Wep_Flare_Gun_01", tables) == ["sight_front"]  # Flare + Gun join to `flaregun`
    assert M.excluded_slots("SM_Wep_Flare_Rifle_01", tables) == []
    assert M.excluded_slots("SM_Wep_Flare_Gun_01", {}) == []  # no table, nothing excluded
