"""W8c compatibility tables in weapon_rules.yaml: validation, the rules_digest pin (D-10), the default export (INV-19),
partial builds and cached builds.

docs/weapon_attachments.md 5.1 (the tables are parameters, not contract), 3.6 and D-10.
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

from synty_inventory.weapons.directory import build_directory_report, to_text  # noqa: E402
from synty_inventory.weapons.export import export_snapshot  # noqa: E402
from synty_inventory.weapons.overrides import empty_overrides  # noqa: E402
from synty_inventory.weapons.rules import (  # noqa: E402
    attach_rules_digest,
    attachment_rules,
    load_rules,
    validate_rules,
    weapon_rules_digest,
)

W7_RULES_DIGEST = "7b9829af37328fe7"  # a literal: what W7 computed for the rule sections it hashed


# --- the digest pin ----------------------------------------------------------------------------------------------------


def test_the_compatibility_tables_leave_rules_digest_at_the_w7_value():
    rules = load_rules()
    assert weapon_rules_digest(rules) == W7_RULES_DIGEST


def test_the_compatibility_tables_live_inside_attachment_rules_and_not_beside_it():
    rules = load_rules()
    assert "attach_affinity" not in rules and "attach_compat" not in rules
    tables = attachment_rules(rules)
    assert set(tables["attach_affinity"]) == {"optic", "muzzle", "underbarrel", "laser_light", "magazine", "sight_front", "sight_rear"}
    assert tables["attach_compat"]["base"] == {"same_pack_fit": 0.7, "cross_pack_fit": 0.4}
    assert tables["attach_compat"]["tier_score"] == {"override": 1.0, "twin": 0.95}


def test_editing_a_compatibility_table_moves_the_attach_digest_and_not_rules_digest():
    rules = load_rules()
    for key, mutate in (("attach_affinity", lambda t: t["optic"].update(scope=["pistol"])),
                        ("attach_compat", lambda t: t.update(fit_span_bonus=0.05))):
        edited = copy.deepcopy(rules)
        mutate(edited["attachment_rules"][key])
        assert weapon_rules_digest(edited) == W7_RULES_DIGEST
        assert attach_rules_digest(edited) != attach_rules_digest(rules)
        assert validate_rules(edited) == []


def test_the_shipped_rules_validate():
    assert validate_rules(load_rules()) == []


# --- validation of the tables ---------------------------------------------------------------------------------------------


def broken(mutate) -> list[str]:
    rules = copy.deepcopy(load_rules())
    mutate(rules["attachment_rules"])
    return validate_rules(rules)


@pytest.mark.parametrize(("mutate", "message"), [
    (lambda t: t["attach_affinity"].update(scope={"x": ["rifle"]}), "slot not in"),
    (lambda t: t["attach_affinity"]["optic"].update(drum=["rifle"]), "not a kind of the slot"),
    (lambda t: t["attach_affinity"]["optic"].update(scope=["rifel"]), "unknown archetype"),
    (lambda t: t["attach_affinity"]["optic"].update(scope="rifle"), "must be a list"),
    (lambda t: t["attach_affinity"].update(muzzle={}), "non-empty"),
    (lambda t: t["attach_compat"].update(speed=1), "unknown key"),
    (lambda t: t["attach_compat"].update(fit_span_bonus=0.9), "from 0 to 0.5"),
    (lambda t: t["attach_compat"]["base"].update(same_pack_fit=0.85), "outside the band"),  # 0.85 + 0.1 + 0.1 > 0.9
    (lambda t: t["attach_compat"]["base"].update(cross_pack_fit=0.35), "outside the band"),  # 0.35 - 0.1 < 0.3 is fine, +0.2 > 0.6
    (lambda t: t["attach_compat"]["base"].update(twin=0.9), "must map"),
    (lambda t: t["attach_compat"]["tier_score"].update(same_pack_fit=0.7), "must map"),
    (lambda t: t["attach_compat"].update(generic_tokens="wep"), "generic_tokens"),
])
def test_a_bad_compatibility_table_is_a_rules_error(mutate, message):
    errors = broken(mutate)
    assert any(message in e for e in errors), errors


# --- the default export is untouched (INV-19) ---------------------------------------------------------------------------------


def test_the_default_export_of_the_built_world_carries_nothing_of_the_compatibility_pass(tmp_path):
    directory = W.build(tmp_path)[0]
    snap = export_snapshot(directory, game="g", pack_ids=None, ids=None, roles={"whole", "part"}, engines={"all"}, frame="item",
                           profile="private", pack_meta={}, overrides_digest=directory["overrides_digest"],
                           rules_digest=directory["rules_digest"])
    text = to_text(snap)
    for forbidden in ("attachment", "compatible_hosts", "pending_hosts", "twin_multi", "compat_cross_pack", "mount_missing", "mounts"):
        assert forbidden not in text, forbidden
    assert snap["generated_from"]["rules_digest"] == W7_RULES_DIGEST


# --- partial builds and cached builds --------------------------------------------------------------------------------------


def test_a_partial_build_of_one_pack_keeps_the_twins_of_the_carried_hosts(tmp_path):
    full, full_ex, _, _ = W.build(tmp_path / "full")
    cat, root = W.write_world(tmp_path / "part")
    part, part_ex, _ = build_directory_report(
        cat, packs=[W.PACK_B], base=(full, full_ex), overrides=empty_overrides(), pack_settings=W.PACK_SETTINGS,
        rules=W.compat_rules(), threejs_v2_dir=root, geometry_cache={})
    alt = W.by_id(part)[W.P[W.ALT_SCOPE]]
    # the hosts of FAKE_CompA are carried over (no child extents in this run): the twin relations come from the stored lists
    # (S7, spec 3.4 step 3: BETA's flat optic seat makes it a cross_pack_fit entry of the Alt scope, carried over too)
    assert W.hosts_of(alt) == [(W.H[W.ALPHA], "twin", 0.95), (W.H[W.EPSILON], "twin", 0.95), (W.H[W.BETA], "cross_pack_fit", 0.5)]
    assert "twin_multi" in alt["review"]["reasons"]
    assert to_text(part) == to_text(full)


def test_a_cache_hit_gives_the_same_compatibility_as_a_recompute(tmp_path):
    cache: dict = {}
    cold, *_ = W.build(tmp_path, cache=cache)
    assert cache  # the second build is served from it
    warm, *_ = W.build(tmp_path, cache=cache)
    assert to_text(warm) == to_text(cold)
    assert W.hosts_of(W.by_id(warm)[W.P[W.SCOPE]]) == W.hosts_of(W.by_id(cold)[W.P[W.SCOPE]])
    assert W.hosts_of(W.by_id(warm)[W.P[W.SCOPE]])[0][1] == "twin"  # child extents survive the cache


def test_ac72_an_unmeasured_build_lists_no_compatible_host_only_name_based_candidates(tmp_path):
    cat, _ = W.write_world(tmp_path)
    directory, _ = W.WFX.build(cat, pack_settings=W.PACK_SETTINGS, measure=False)
    scope = W.by_id(directory)[W.P[W.SCOPE]]
    # nothing was measured, so no host is a verified fit: the name-based candidates wait in pending_hosts
    assert scope["attachment"]["compatible_hosts"] == []
    pending = scope["attachment"]["pending_hosts"]
    assert pending and {p["tier"] for p in pending} <= {"same_pack_fit", "cross_pack_fit"}
    assert "no_geometry" in scope["review"]["reasons"]
