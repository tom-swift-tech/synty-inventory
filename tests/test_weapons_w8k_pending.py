"""W8k: a baked host has no pending sights (AC104; docs/weapon_attachments.md 4.6 item 9, lead 2026-10-23, addendum 3b).

Hosts are the W8h prism (a tent the sight probe refuses: both sight slots start ``none`` / ``probe_unavailable``) with baked children, or the
W8k spike slab (w8k_world.py: a fused front post on a mesh whose receiver run is too short to seat). Children are named ``<host>_<suffix>``.
Every expected value is a LITERAL worked out by hand from the fixtures, never read from the code under test.

  Before item 9 the rules of item 8 (A body child, B glass-only, C iron sight / carry handle / fused front post) rewrote only a sight slot the
  probe had SEATED, so a baked host the probe refused kept ``probe_unavailable`` and compat listed pending sight entries for it. Now the two
  pending reasons ``probe_unavailable`` and ``no_child_no_probe`` are rewritten to ``slot_disabled`` as well; ``slot_disabled``, ``child_node``
  and ``override`` slots are never touched, and the fused post detector runs whenever the probe mesh has a profile.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("w8k_world", Path(__file__).parent / "fixtures" / "weapons" / "w8k_world.py")
K = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(K)
J, X, W, A = K.J, K.X, K.W, K.A

PACK = "FAKE_W8k"
OPTIC_PART = "SM_Wep_Rifle_Scope_01"  # an optic part (twin of the baked Fake_Scope_01 tube)
SLOTS = ("optic", "sight_front", "sight_rear")
SIGHTS = ("sight_front", "sight_rear")
APEX = (0.0, 0.2, 0.0)  # a child standing on the prism apex (y 0.2)
INSIDE_FRONT = (0.0, 0.05, 0.05)  # a post inside the tent on its muzzle half (the tent surface there is y 0.1), out of the profile
HIGH, LOW = (0.0, 0.15, 0.0), (0.0, 0.05, 0.0)  # centre y 0.15 is 75 % of the host height 0.2, y 0.05 is 25 %


def rid(name):
    return f"{PACK}/{name}"


def mounts(built, name):
    return built[rid(name)]["geometry"]["mounts"]


def refused(m):
    return m["source"] == "none" and m["reason"] == "slot_disabled" and m["point"] is None and m["occupied_by"] == []


def pending_reason(m):
    return m["source"] == "none" and m["reason"] == "probe_unavailable"


def entries(built, part, host):
    """``(listed entry, pending entry)`` of part ``part`` on host ``host``."""
    att = built[rid(part)]["attachment"]
    return (next((e for e in att["compatible_hosts"] if e["host"] == rid(host)), None),
            next((e for e in att["pending_hosts"] if e["host"] == rid(host)), None))


def no_candidate(built, host, parts=(OPTIC_PART, X.SIGHT_FRONT, X.SIGHT_REAR)):
    return all(entries(built, p, host) == (None, None) for p in parts)


def parts():
    return {OPTIC_PART: A.optic, X.SIGHT_FRONT: W.sight_part, X.SIGHT_REAR: W.sight_part}


def tent(name, kids=()):
    return X.prism(name, list(kids))


def handle():
    return X.block(0.004, 0.010, 0.020)


H = {n: f"SM_Wep_Rifle_{n}_01" for n in (
    "Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel", "India", "Juliet", "Kilo", "Lima", "Mike", "November", "Oscar",
    "Papa", "Quebec", "Romeo", "Sierra")}
SCOPE, GLASS, POST, HANDLE, FUSED = H["Alpha"], H["Bravo"], H["Charlie"], H["Delta"], H["Echo"]
BARE_TENT, BARE_SPIKE, LOW_HANDLE, CHARGE = H["Foxtrot"], H["Golf"], H["Hotel"], H["India"]
SIDED, NONE_OVR, OVR_REAR, ADDED, SHORT, LOW_POST = H["Juliet"], H["Kilo"], H["Lima"], H["Mike"], H["November"], H["Oscar"]
GLASS_SCOPE_NONE = H["Papa"]


def hosts():
    return {
        # (i) a body child (a scope tube); (ii) glass only (a 3 mm sheet); (iii) a baked front post; (iv) a carry handle above 55 %
        SCOPE: tent(SCOPE, [("Fake_Scope_01", A.optic(), APEX)]),
        GLASS: tent(GLASS, [("Fake_Sight_Glass_01", J.sheet(), APEX)]),
        POST: tent(POST, [("Fake_Sight_01", X.sight_post(), INSIDE_FRONT)]),
        HANDLE: tent(HANDLE, [("Fake_Handle_01", handle(), HIGH)]),
        # (v) a 20 mm wide, 14 mm tall block at 0.8 of the length of a mesh whose receiver run is 2 bins
        FUSED: K.spike_host(FUSED, [(*J.POST_WIDE_08, 0.014)]),
        # (vi) the controls: no baked child, post or handle; a handle at 25 %; a charge handle at 75 %; a post at 0.4 and a 6 mm one at 0.8
        BARE_TENT: tent(BARE_TENT),
        BARE_SPIKE: K.spike_host(BARE_SPIKE),
        LOW_HANDLE: tent(LOW_HANDLE, [("Fake_Handle_01", handle(), LOW)]),
        CHARGE: tent(CHARGE, [("Fake_ChargeHandle_01", handle(), HIGH)]),
        LOW_POST: K.spike_host(LOW_POST, [(*J.POST_WIDE_08, 0.006)]),
        # (vii) a sided child_node front sight on a refused host; an override rear on a body-child host; an override `none` on one; an add
        SIDED: tent(SIDED, [("Fake_FrontSight_01", X.sight_post(), INSIDE_FRONT)]),
        OVR_REAR: tent(OVR_REAR, [("Fake_Scope_01", A.optic(), APEX)]),
        NONE_OVR: tent(NONE_OVR, [("Fake_Scope_01", A.optic(), APEX)]),
        ADDED: tent(ADDED, [("Fake_Scope_01", A.optic(), APEX)]),
        # a mesh under the 12 populated bins the detector needs: no profile to judge, so the post at 0.8 is not found
        SHORT: K.spike_host(SHORT, [(0.0055, 0.0245, 0.014)], z0=-0.025, z1=0.025),
        # glass-only host with an optic override `none`: only the sight slots are the rule's
        GLASS_SCOPE_NONE: tent(GLASS_SCOPE_NONE, [("Fake_Sight_Glass_01", J.sheet(), APEX)]),
    }


def overrides():
    return W.overrides_doc(ids={
        rid(NONE_OVR): {"mounts": {"sight_front": {"source": "none"}}},
        rid(OVR_REAR): {"mounts": {"sight_rear": {"source": "child_node", "child": f"{OVR_REAR}_Fake_Scope_01"}}},
        rid(X.SIGHT_REAR): {"compatible": {"add": [rid(ADDED)]}},
        rid(GLASS_SCOPE_NONE): {"mounts": {"optic": {"source": "none"}}},
    })


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return W.by_id(W.build(tmp_path_factory.mktemp("w8k_pending"), {PACK: {"hosts": hosts(), "parts": parts()}}, overrides=overrides())[0])


# -- the fixtures are what the cases need ----------------------------------------------------------------------------


@pytest.mark.parametrize("name", [BARE_TENT, BARE_SPIKE, LOW_HANDLE, CHARGE, LOW_POST, SHORT])
def test_ac104_the_fixture_hosts_the_probe_cannot_seat_start_probe_unavailable(built, name):
    # (vi) the controls: nothing baked, so the rules have nothing to say and both slots keep the probe's reason
    m = mounts(built, name)
    assert pending_reason(m["sight_front"]) and pending_reason(m["sight_rear"]), name


# -- (i) to (v): the rules reach a slot the probe could not seat -------------------------------------------------------


def test_ac104_i_a_scope_child_refuses_both_pending_sight_slots_and_keeps_the_optic(built):
    m = mounts(built, SCOPE)
    assert refused(m["sight_front"]) and refused(m["sight_rear"])
    assert m["optic"]["source"] == "child_node" and m["optic"]["occupied_by"] == [f"{SCOPE}_Fake_Scope_01"]  # (A): optic unchanged
    assert no_candidate(built, SCOPE, (X.SIGHT_FRONT, X.SIGHT_REAR))  # neither listed nor pending
    listed, pending = entries(built, OPTIC_PART, SCOPE)
    assert listed is not None and listed["tier"] == "twin" and pending is None  # the optic part is still a candidate


def test_ac104_ii_a_glass_only_host_refuses_both_pending_sight_slots_and_the_optic(built):
    m = mounts(built, GLASS)
    assert all(refused(m[s]) for s in SLOTS)  # (B)
    assert no_candidate(built, GLASS)


def test_ac104_iii_a_baked_front_post_child_refuses_both_pending_sight_slots(built):
    m = mounts(built, POST)
    assert refused(m["sight_front"]) and refused(m["sight_rear"])  # (C) iron child; the optic has no child and no probe
    assert no_candidate(built, POST, (X.SIGHT_FRONT, X.SIGHT_REAR))


def test_ac104_iv_a_carry_handle_child_above_55_percent_refuses_both_pending_sight_slots(built):
    m = mounts(built, HANDLE)
    assert refused(m["sight_front"]) and refused(m["sight_rear"])  # (C) handle at 75 % of the host height
    assert no_candidate(built, HANDLE, (X.SIGHT_FRONT, X.SIGHT_REAR))


def test_ac104_v_a_fused_front_post_on_a_host_the_probe_could_not_seat_refuses_both_slots(built):
    m = mounts(built, FUSED)
    assert refused(m["sight_front"]) and refused(m["sight_rear"])  # (C) fused: the detector ran on the mesh of a refused host
    assert no_candidate(built, FUSED, (X.SIGHT_FRONT, X.SIGHT_REAR))


# -- (vi): the same host without anything baked keeps its reason and its pending entries ---------------------------------


@pytest.mark.parametrize("name", [BARE_TENT, BARE_SPIKE])
def test_ac104_vi_a_host_with_nothing_baked_keeps_probe_unavailable_and_its_pending_entries(built, name):
    m = mounts(built, name)
    assert pending_reason(m["sight_front"]) and pending_reason(m["sight_rear"])
    for part in (X.SIGHT_FRONT, X.SIGHT_REAR):
        listed, pending = entries(built, part, name)
        assert listed is None and pending is not None and pending["tier"] == "same_pack_fit", (part, name)


@pytest.mark.parametrize("name", [LOW_HANDLE, CHARGE, LOW_POST, SHORT])
def test_ac104_vi_the_near_misses_are_no_baked_sight(built, name):
    # a handle at 25 % of the height, a charge handle at 75 %, a 6 mm post at 0.8, a 14 mm post on a mesh under 12 bins: nothing to refuse
    for part in (X.SIGHT_FRONT, X.SIGHT_REAR):
        listed, pending = entries(built, part, name)
        assert listed is None and pending is not None, (part, name)


# -- (vii): what the rules never touch -------------------------------------------------------------------------------


def test_ac104_vii_a_slot_that_is_already_slot_disabled_keeps_its_reason_and_the_other_one_goes(built):
    m = mounts(built, NONE_OVR)  # the override `none` of sight_front; the scope child is a body child (A)
    assert m["sight_front"]["source"] == "none" and m["sight_front"]["reason"] == "slot_disabled"
    assert refused(m["sight_rear"])


def test_ac104_vii_a_sided_child_node_sight_keeps_its_seat_and_the_pending_rear_goes(built):
    m = mounts(built, SIDED)
    assert m["sight_front"]["source"] == "child_node" and m["sight_front"]["occupied_by"] == [f"{SIDED}_Fake_FrontSight_01"]
    assert m["sight_front"]["point"] is not None
    assert refused(m["sight_rear"])  # (C): half a pair is never offered


def test_ac104_vii_an_override_mount_is_never_touched_and_the_pending_front_goes(built):
    m = mounts(built, OVR_REAR)
    assert m["sight_rear"]["source"] == "override" and m["sight_rear"]["child_node"] == f"{OVR_REAR}_Fake_Scope_01"
    assert refused(m["sight_front"])  # (A)


def test_ac104_vii_an_override_add_still_lists_the_pair_as_pending(built):
    m = mounts(built, ADDED)
    assert refused(m["sight_front"]) and refused(m["sight_rear"])
    listed, pending = entries(built, X.SIGHT_REAR, ADDED)
    assert listed is None and pending is not None and pending["tier"] == "override"
    assert entries(built, X.SIGHT_FRONT, ADDED) == (None, None)  # only the rear part has the `add`


def test_ac104_vii_an_optic_override_none_is_not_the_rules_to_overwrite_and_the_sights_go(built):
    m = mounts(built, GLASS_SCOPE_NONE)
    assert refused(m["optic"]) and refused(m["sight_front"]) and refused(m["sight_rear"])


# -- rules without a sight_probe table: the reason is no_child_no_probe, the rewrite is the same --------------------------


def test_ac104_a_rule_set_without_a_probe_table_rewrites_no_child_no_probe_on_a_baked_host_only(tmp_path):
    rules = W.sight_rules()
    del rules["attachment_rules"]["sight_probe"]  # no probe: every free sight slot is no_child_no_probe, and no profile exists to judge
    d = W.by_id(W.build(tmp_path, {PACK: {"hosts": {SCOPE: hosts()[SCOPE], BARE_TENT: hosts()[BARE_TENT], FUSED: hosts()[FUSED]},
                                         "parts": parts()}}, rules=rules)[0])
    scoped, bare, fused = mounts(d, SCOPE), mounts(d, BARE_TENT), mounts(d, FUSED)
    assert refused(scoped["sight_front"]) and refused(scoped["sight_rear"])
    for slot in SIGHTS:
        assert bare[slot]["source"] == "none" and bare[slot]["reason"] == "no_child_no_probe", slot
        assert fused[slot]["source"] == "none" and fused[slot]["reason"] == "no_child_no_probe", slot  # no table, no profile, no detection


# -- the pure rule -----------------------------------------------------------------------------------------------------


def _mount(source, reason=None):
    return {"source": source, "reason": reason, "point": [0.0, 0.0, 0.0] if source != "none" else None, "occupied_by": []}


FOUND_NONE = {"glass": [], "body": [], "handle": [], "iron": []}


@pytest.mark.parametrize("reason,after", [("probe_unavailable", "slot_disabled"), ("no_child_no_probe", "slot_disabled"),
                                          ("slot_disabled", "slot_disabled")])
def test_ac104_refuse_baked_rewrites_exactly_the_two_pending_reasons(reason, after):
    from synty_inventory.weapons.mounts import refuse_baked

    m = {"optic": _mount("none", "no_child_no_probe"), "sight_front": _mount("none", reason), "sight_rear": _mount("override")}
    refuse_baked(m, {**FOUND_NONE, "body": ["X_Fake_Scope_01"]}, False)
    assert m["sight_front"]["reason"] == after and m["sight_front"]["source"] == "none"
    assert m["sight_rear"]["source"] == "override"
    assert m["optic"]["reason"] == "no_child_no_probe"  # (A) leaves optic alone


def test_ac104_refuse_baked_leaves_a_host_with_nothing_found_alone():
    from synty_inventory.weapons.mounts import refuse_baked

    m = {"optic": _mount("none", "no_child_no_probe"), "sight_front": _mount("none", "probe_unavailable"),
         "sight_rear": _mount("none", "no_child_no_probe")}
    refuse_baked(m, FOUND_NONE, False)
    assert (m["sight_front"]["reason"], m["sight_rear"]["reason"]) == ("probe_unavailable", "no_child_no_probe")
    refuse_baked(m, FOUND_NONE, True)  # a fused front post alone is enough (C)
    assert m["sight_front"]["reason"] == m["sight_rear"]["reason"] == "slot_disabled"


# -- versions and the cache key (AC104, AC103) -------------------------------------------------------------------------


def test_ac104_the_versions_and_the_digest():
    import synty_inventory.weapons as pkg
    from synty_inventory.weapons.rules import load_rules, weapon_rules_digest

    assert pkg.WEAPON_ATTACH_VERSION == 14 and pkg.WEAPON_GEOMETRY_VERSION == 6
    assert weapon_rules_digest(load_rules()) == "7b9829af37328fe7"  # the W7 digest: item 9 touches no rule table


def test_ac104_the_mounts_cache_key_follows_the_rule_code_and_the_attach_version(tmp_path, monkeypatch):
    # the rewrite lives in mounts.py, whose source digest is part of the geometry mounts cache key; so is WEAPON_ATTACH_VERSION
    import synty_inventory.weapons as pkg
    from synty_inventory.weapons import geometry as geo

    world = W.write_world(tmp_path, {PACK: {"hosts": {BARE_TENT: hosts()[BARE_TENT]}}})[1]

    def measure(cache):
        return geo.measure_cached(world, f"glb/{PACK}/{BARE_TENT}.glb", None, 1.0, "rifle", "ranged", "whole", W.sight_rules(), cache,
                                  hold_class="long_gun", genre="modern")[1]

    cache: dict = {}
    assert measure(cache) is False and measure(cache) is True
    monkeypatch.setattr(geo, "_MOUNTS_CODE_DIGEST", "0" * 16)  # as if mounts.py had changed
    assert measure(cache) is False
    monkeypatch.undo()
    assert measure(cache) is True
    monkeypatch.setattr(pkg, "WEAPON_ATTACH_VERSION", pkg.WEAPON_ATTACH_VERSION + 1)
    assert measure(cache) is False
