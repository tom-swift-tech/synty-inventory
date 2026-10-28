"""W8h-A: the optic over the rear sight (AC90, spec 4.3) and the setting gate (AC91, spec 5.1, INV-21).

The numbers are literals worked out by hand from the meshes of ``fixtures/weapons/w8a_attach.py`` (the optic: foot centre
(0.005, 0, 0.05), z -0.1..0.1 in its own frame, objective flare toward +z) and the node translations below.
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("w8h_world", Path(__file__).parent / "fixtures" / "weapons" / "w8h_world.py")
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)
A = W.A
G = W.G

from synty_inventory.weapons import preview  # noqa: E402
from synty_inventory.weapons.compat import hides_slots  # noqa: E402
from synty_inventory.weapons.rules import attach_rules_digest, weapon_rules_digest  # noqa: E402
from synty_inventory.weapons.schema import validate_directory  # noqa: E402

# -- AC90 ----------------------------------------------------------------------------------------------------

HIDE = "FAKE_SightHide"
HOST_HIDE, HOST_NOREAR = "SM_Wep_Iron_Rifle_Hide_01", "SM_Wep_Iron_Rifle_NoRear_01"
SCOPE, SHORT, FRONT = "SM_Wep_Rifle_Scope_01", "SM_Wep_Rifle_Scope_Short_01", "SM_Wep_IronSight_Front_01"
SCOPE_AT, REAR_AT, FRONT_AT = (0.0, 0.10, 0.10), (0.0, 0.10, 0.04), (0.0, 0.10, 0.30)


def short_optic():
    """A 0.06 m optic: foot z +-0.03 at y 0..0.01 under a body of the same length (extent -0.03..+0.03 about the foot centre)."""
    return G.merge(G.box((-0.01, 0.0, -0.03), (0.01, 0.01, 0.03)), G.box((-0.015, 0.01, -0.03), (0.015, 0.04, 0.03)))


def hide_world():
    def host(name, rear):
        kids = [W.kid(name, "Scope", A.optic(), SCOPE_AT), W.kid(name, "FrontSight_01", A.optic(), FRONT_AT)]
        if rear:
            kids.append(W.kid(name, "RearSight_01", A.optic(), REAR_AT))
        return W.host_node(name, A.host_body("square"), kids)

    return {HIDE: {"hosts": {HOST_HIDE: host(HOST_HIDE, True), HOST_NOREAR: host(HOST_NOREAR, False)},
                   "parts": {SCOPE: A.optic, SHORT: short_optic, FRONT: A.optic}}}


def uncapped_rules() -> dict:
    """A6 (W8n): the short optic below is seated 60 mm off the host (the clamp) by the contact pass, which the 30 mm settle cap now removes from
    ``compatible_hosts``. These AC90 cases are about hides_slots, so they build with the cap raised to the clamp (the cap is tested in test_weapons_w8n_cap.py)."""
    rules = W.sight_rules()
    rules["attachment_rules"]["contact"]["cap_m"] = rules["attachment_rules"]["contact"]["clamp_m"]
    return rules


@pytest.fixture(scope="module")
def hide_dir(tmp_path_factory):
    directory, _, _, root = W.build(tmp_path_factory.mktemp("w8h_hide"), hide_world(), rules=uncapped_rules())
    return directory, root


def entry(directory, part, host):
    rec = W.by_id(directory)[f"{HIDE}/{part}"]
    return next((e for e in rec["attachment"]["compatible_hosts"] if e["host"] == f"{HIDE}/{host}"), None)


def test_ac90_both_mounts_are_measured_on_the_fixture_host(hide_dir):
    m = W.by_id(hide_dir[0])[f"{HIDE}/{HOST_HIDE}"]["geometry"]["mounts"]
    assert m["optic"]["source"] == "child_node" and m["sight_rear"]["source"] == "child_node"
    nr = W.by_id(hide_dir[0])[f"{HIDE}/{HOST_NOREAR}"]["geometry"]["mounts"]
    assert nr["sight_rear"]["source"] in ("probe", "none")  # no rear child: the probe, or nothing


def test_ac90_an_optic_that_covers_the_rear_seat_hides_the_rear_sight(hide_dir):
    # optic seat z 0.15 (SCOPE_AT 0.10 + foot 0.05); the part spans -0.15..+0.05 about its foot: 0.0..0.20; the rear seat is z 0.09
    got = entry(hide_dir[0], SCOPE, HOST_HIDE)
    assert got["tier"] == "twin" and got["hides_slots"] == ["sight_rear"]


def test_ac90_a_short_optic_seated_forward_of_the_rear_seat_has_no_hides_slots_key(hide_dir):
    # 0.06 m optic on the same seat: 0.12..0.18 plus the 10 mm margin is 0.11..0.19, the rear seat z 0.09 is outside it
    got = entry(hide_dir[0], SHORT, HOST_HIDE)
    assert got is not None and "hides_slots" not in got


def test_ac90_an_optic_on_a_host_whose_rear_sight_is_not_measured_has_none(tmp_path):
    ovr = W.overrides_doc(ids={f"{HIDE}/{HOST_HIDE}": {"mounts": {"sight_rear": {"source": "none"}}}})
    d = W.build(tmp_path, hide_world(), overrides=ovr)[0]
    got = entry(d, SCOPE, HOST_HIDE)
    assert got is not None and "hides_slots" not in got


def test_ac90_a_front_sight_part_never_has_hides_slots(hide_dir):
    rec = W.by_id(hide_dir[0])[f"{HIDE}/{FRONT}"]
    assert rec["attachment"]["slot"] == "sight_front"
    assert rec["attachment"]["compatible_hosts"] and not any("hides_slots" in e for e in rec["attachment"]["compatible_hosts"])


def test_ac90_the_pure_rule_has_a_10_mm_margin_each_way():
    seat = {"point": [0.0, 0.1, 0.0], "forward": [0.0, 0.0, 1.0]}
    rear = lambda z: {"point": [0.0, 0.1, z], "forward": [0.0, 0.0, 1.0]}  # noqa: E731
    ext = (-0.10, 0.05)
    assert hides_slots(ext, seat, rear(-0.109)) == ["sight_rear"] and hides_slots(ext, seat, rear(-0.111)) == []
    assert hides_slots(ext, seat, rear(0.059)) == ["sight_rear"] and hides_slots(ext, seat, rear(0.061)) == []
    assert hides_slots(None, seat, rear(0.0)) == [] and hides_slots(ext, seat, None) == []
    assert hides_slots(ext, seat, {"point": None, "forward": None}) == []


def test_ac90_the_schema_accepts_the_key_on_an_optic_entry_only_and_never_empty(hide_dir):
    d = hide_dir[0]
    assert validate_directory(d) == []
    bad = copy.deepcopy(d)
    next(e for e in W.by_id(bad)[f"{HIDE}/{SCOPE}"]["attachment"]["compatible_hosts"] if "hides_slots" in e)["hides_slots"] = []
    assert validate_directory(bad)
    bad = copy.deepcopy(d)
    W.by_id(bad)[f"{HIDE}/{FRONT}"]["attachment"]["compatible_hosts"][0]["hides_slots"] = ["sight_rear"]
    assert validate_directory(bad)


def test_ac90_the_preview_hides_the_rear_sight_nodes_with_the_covering_optic(hide_dir):
    directory, root = hide_dir
    by = W.by_id(directory)
    host = by[f"{HIDE}/{HOST_HIDE}"]

    def hidden(part):
        pair = {"part": f"{HIDE}/{part}", "host": host["id"], "slot": "optic", "tier": "x", "score": 0.5, "twin": False}
        return preview.build_job(pair, by[pair["part"]], host, root)["hide"]

    assert hidden(SCOPE) == [f"{HOST_HIDE}_RearSight_01", f"{HOST_HIDE}_Scope"]  # the covering optic hides the rear sight too
    assert hidden(SHORT) == [f"{HOST_HIDE}_Scope"]  # the short one only the optic it replaces


# -- AC91 ----------------------------------------------------------------------------------------------------

P1, P2, P3, P4 = "FAKE_GateA", "FAKE_GateB", "FAKE_GateC", "FAKE_GateD"
SETTING = {P1: "s1", P2: "s1", P3: "s2"}  # P4 is unlisted
PART = "SM_Wep_Rifle_Scope_01"


def gate_world():
    def host(name, k):
        kids = [W.kid(name, "Scope", W.sight_scaled(k), SCOPE_AT)] if k else []
        return W.host_node(name, A.host_body("square"), kids)

    return {
        P1: {"parts": {PART: A.optic}, "hosts": {"SM_Wep_Rifle_Alpha_01": host("SM_Wep_Rifle_Alpha_01", 1.1),
                                                  "SM_Wep_Rifle_Plain_01": host("SM_Wep_Rifle_Plain_01", 0)}},
        P2: {"hosts": {"SM_Wep_Rifle_Beta_01": host("SM_Wep_Rifle_Beta_01", 1.1)}},
        P3: {"hosts": {"SM_Wep_Rifle_Gamma_01": host("SM_Wep_Rifle_Gamma_01", 1.0),  # a child the part twins exactly
                       "SM_Wep_Rifle_Gamma_Plain_01": host("SM_Wep_Rifle_Gamma_Plain_01", 0)}},
        P4: {"parts": {PART: A.optic}, "hosts": {"SM_Wep_Rifle_Delta_01": host("SM_Wep_Rifle_Delta_01", 1.0)}},
    }


def hosts_of(directory, pack, key="compatible_hosts"):
    return {e["host"]: e["tier"] for e in W.by_id(directory)[f"{pack}/{PART}"]["attachment"][key]}


@pytest.fixture(scope="module")
def gated(tmp_path_factory):
    return W.build(tmp_path_factory.mktemp("w8h_gate"), gate_world(), rules=W.sight_rules(SETTING))[0]


def test_ac91_hosts_of_the_same_pack_and_of_the_same_setting_are_candidates(gated):
    # S7 (spec 3.4 step 3): Plain has no scope child but a smooth top, so its optic is a flat seat. G1 3.5/AC148 (S8): a flat seat is `unverified`, so
    # Plain is a pending same-pack entry, not a listed one
    assert hosts_of(gated, P1) == {f"{P1}/SM_Wep_Rifle_Alpha_01": "same_pack_fit", f"{P2}/SM_Wep_Rifle_Beta_01": "cross_pack_fit"}
    assert hosts_of(gated, P1, "pending_hosts") == {f"{P1}/SM_Wep_Rifle_Plain_01": "same_pack_fit"}


def test_ac91_no_host_of_another_setting_or_an_unlisted_pack_is_listed_even_one_with_an_exact_twin_child(gated):
    everything = {**hosts_of(gated, P1), **hosts_of(gated, P1, "pending_hosts")}
    assert not [h for h in everything if h.startswith((P3, P4))]  # Gamma has an exact twin child and Delta too


def test_ac91_an_unlisted_pack_matches_only_itself(gated):
    assert hosts_of(gated, P4) == {f"{P4}/SM_Wep_Rifle_Delta_01": "twin"}
    assert hosts_of(gated, P4, "pending_hosts") == {}


def test_ac91_an_add_override_crosses_the_gate_with_tier_override(tmp_path):
    ovr = W.overrides_doc(ids={f"{P1}/{PART}": {"compatible": {"add": [f"{P3}/SM_Wep_Rifle_Gamma_01"]}}})
    d = W.build(tmp_path, gate_world(), rules=W.sight_rules(SETTING), overrides=ovr)[0]
    assert hosts_of(d, P1)[f"{P3}/SM_Wep_Rifle_Gamma_01"] == "override"
    assert f"{P3}/SM_Wep_Rifle_Gamma_Plain_01" not in {**hosts_of(d, P1), **hosts_of(d, P1, "pending_hosts")}  # only the named host


def test_ac91_every_non_override_entry_has_a_host_of_the_parts_setting(tmp_path):
    ovr = W.overrides_doc(ids={f"{P1}/{PART}": {"compatible": {"add": [f"{P3}/SM_Wep_Rifle_Gamma_01"]}}})
    d = W.build(tmp_path, gate_world(), rules=W.sight_rules(SETTING), overrides=ovr)[0]
    setting = lambda pack: SETTING.get(pack, f"pack:{pack}")  # noqa: E731
    seen = 0
    for rec in d["weapons"]:
        att = rec.get("attachment")
        for entry_ in ((att or {}).get("compatible_hosts") or []) + ((att or {}).get("pending_hosts") or []):
            seen += 1
            if entry_["tier"] != "override":
                assert setting(entry_["host"].split("/")[0]) == setting(rec["pack"]), (rec["id"], entry_)
    assert seen == 5  # Alpha, Beta, Plain, the overridden Gamma, and the unlisted pack's own twin Delta


def test_ac91_without_a_table_every_pack_is_its_own_setting(tmp_path):
    d = W.build(tmp_path, gate_world(), rules=W.sight_rules({}))[0]
    # S7 (spec 3.4 step 3): Plain's flat optic seat makes it a same-pack entry too; G1 3.5/AC148 (S8): a pending one
    assert hosts_of(d, P1) == {f"{P1}/SM_Wep_Rifle_Alpha_01": "same_pack_fit"}
    assert hosts_of(d, P1, "pending_hosts") == {f"{P1}/SM_Wep_Rifle_Plain_01": "same_pack_fit"}


def test_ac91_editing_the_table_moves_the_attach_digest_and_not_the_rules_digest():
    a, b = W.sight_rules(SETTING), W.sight_rules({**SETTING, P4: "s1"})
    assert attach_rules_digest(a) != attach_rules_digest(b)
    assert weapon_rules_digest(a) == weapon_rules_digest(b)
    assert weapon_rules_digest(a) == "7b9829af37328fe7"
