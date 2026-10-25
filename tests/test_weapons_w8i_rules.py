"""W8i: the two new rule tables, their digests and the cache key, and the version numbers (AC95, AC96, AC98; docs/weapon_attachments.md 7, 11, 13.2).

``attach_host_never`` and ``baked_sights`` live inside ``attachment_rules``: they move ``attach_rules_digest`` and never
``rules_digest`` (the W7 default export stays byte-identical). The constants are literals, not the code's.
"""

from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("w8i_world", Path(__file__).parent / "fixtures" / "weapons" / "w8i_world.py")
X = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(X)
W = X.W

from synty_inventory import weapons as pkg  # noqa: E402
from synty_inventory.weapons import geometry as geo  # noqa: E402
from synty_inventory.weapons.export import export_snapshot  # noqa: E402
from synty_inventory.weapons.rules import (  # noqa: E402
    ATTACH_TOP_KEYS, attach_rules_digest, load_rules, validate_rules, weapon_rules_digest,
)


def with_tables(**tables):
    rules = deepcopy(load_rules())
    rules["attachment_rules"].update(tables)
    return rules


# -- validation ---------------------------------------------------------------------------------------------------


def test_both_tables_are_whitelisted_attachment_keys():
    assert "attach_host_never" in ATTACH_TOP_KEYS and "baked_sights" in ATTACH_TOP_KEYS


def test_the_shipped_rules_validate_with_both_tables():
    rules = load_rules()
    assert rules["attachment_rules"]["attach_host_never"] and rules["attachment_rules"]["baked_sights"]
    assert validate_rules(rules) == []


@pytest.mark.parametrize("value,fragment", [
    ({"sight_front": "flare"}, "attach_host_never.sight_front"),  # a list is required
    ({"sight_front": []}, "attach_host_never.sight_front"),  # non-empty
    ({"sight_front": ["Flare"]}, "lower-case"),
    ({"sight_side": ["flare"]}, "attach_host_never.sight_side"),  # unknown slot
    (["flare"], "attach_host_never"),  # a map, not a list
])
def test_attach_host_never_is_a_map_of_known_slot_to_lower_case_tokens(value, fragment):
    errors = validate_rules(with_tables(attach_host_never=value))
    assert errors and any(fragment in e for e in errors), errors


def test_attach_host_never_may_be_absent_and_may_name_any_attachment_slot():
    rules = load_rules()
    del rules["attachment_rules"]["attach_host_never"]
    assert validate_rules(rules) == []
    assert validate_rules(with_tables(attach_host_never={"optic": ["prop"], "muzzle": ["prop"]})) == []


@pytest.mark.parametrize("value", [
    {"tokens": ["sight"], "not_tokens": ["glass"]},  # rear_tokens missing
    {"tokens": ["sight"], "not_tokens": ["glass"], "rear_tokens": ["carry"], "extra": ["x"]},
    {"tokens": ["Sight"], "not_tokens": ["glass"], "rear_tokens": ["carry"]},  # lower-case
    {"tokens": [], "not_tokens": ["glass"], "rear_tokens": ["carry"]},  # tokens may not be empty
    {"tokens": ["sight"], "not_tokens": "glass", "rear_tokens": ["carry"]},
    ["sight"],
])
def test_baked_sights_needs_its_three_lower_case_lists(value):
    errors = validate_rules(with_tables(baked_sights=value))
    assert errors and any("baked_sights" in e for e in errors), errors


# -- digests ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("table,edited", [
    ("attach_host_never", {"sight_front": ["flare", "flaregun", "prop"], "sight_rear": ["flare"]}),
    ("baked_sights", {"tokens": ["sight", "sights"], "not_tokens": ["glass"], "rear_tokens": ["carry"]}),
])
def test_editing_a_table_moves_the_attach_digest_and_never_the_rules_digest(table, edited):
    base, changed = load_rules(), with_tables(**{table: edited})
    assert attach_rules_digest(base) != attach_rules_digest(changed)
    assert weapon_rules_digest(base) == weapon_rules_digest(changed) == "7b9829af37328fe7"


# -- the cache key ------------------------------------------------------------------------------------------------

PACK = "FAKE_W8iCache"
HOST = "SM_Wep_Rifle_Cache_01"


@pytest.fixture()
def one_host(tmp_path):
    return W.write_world(tmp_path, {PACK: {"hosts": {HOST: X.rifle(HOST, [("Fake_Sights", X.sight_post(), (0.0, 0.102, X.REAR_HALF_Z))])}}})[1]


def _measure(root, cache, rules, host_id=HOST):
    return geo.measure_cached(root, f"glb/{PACK}/{HOST}.glb", None, 1.0, "rifle", "ranged", "whole", rules, cache,
                              hold_class="long_gun", genre="modern", host_id=host_id)


def test_a_second_measurement_of_the_same_host_is_a_cache_hit(one_host):
    cache: dict = {}
    assert _measure(one_host, cache, load_rules())[1] is False
    assert _measure(one_host, cache, load_rules())[1] is True


@pytest.mark.parametrize("table,edited", [
    ("baked_sights", {"tokens": ["sight"], "not_tokens": ["glass"], "rear_tokens": ["carry"]}),
    ("attach_host_never", {"sight_front": ["prop"]}),
])
def test_a_table_edit_misses_the_cache(one_host, table, edited):
    cache: dict = {}
    assert _measure(one_host, cache, load_rules())[1] is False
    assert _measure(one_host, cache, with_tables(**{table: edited}))[1] is False
    assert _measure(one_host, cache, with_tables(**{table: edited}))[1] is True


def test_the_host_id_is_part_of_the_cache_key(one_host):
    cache: dict = {}
    assert _measure(one_host, cache, load_rules())[1] is False
    assert _measure(one_host, cache, load_rules(), host_id="SM_Wep_Prop_Cache_01")[1] is False  # another name, another exclusion


def test_the_mounts_code_digest_is_part_of_the_cache_key(one_host, monkeypatch):
    cache: dict = {}
    assert _measure(one_host, cache, load_rules())[1] is False
    monkeypatch.setattr(geo, "_MOUNTS_CODE_DIGEST", "0" * 12)  # as if mounts.py (the detector) had changed
    assert _measure(one_host, cache, load_rules())[1] is False


def test_the_cached_measurement_equals_a_recompute(one_host):
    cache: dict = {}
    first, _ = _measure(one_host, cache, load_rules())
    again, hit = _measure(one_host, cache, load_rules())
    assert hit and again["mounts"] == first["mounts"]
    assert first["mounts"]["sight_rear"]["reason"] == "slot_disabled"  # the Fake_Sights child is on the rear half


# -- versions (AC96) ----------------------------------------------------------------------------------------------

WORLD = {"FAKE_W8iVer": {"hosts": {"SM_Wep_Rifle_Ver_01": W.host_node("SM_Wep_Rifle_Ver_01", W.box_rifle())},
                         "parts": {X.SIGHT_FRONT: W.sight_part, X.SIGHT_REAR: W.sight_part}}}


def snapshot(directory, *, attachments):
    return export_snapshot(
        directory, game="g", pack_ids=None, ids=None, roles={"whole", "part"} if attachments else {"whole"}, engines={"godot"},
        frame="godot", profile="private", pack_meta={}, rules_digest=weapon_rules_digest(load_rules()),
        overrides_digest="0" * 16, attachments=attachments)


def test_ac96_the_version_constants():
    assert pkg.WEAPON_ATTACH_VERSION == 12
    assert pkg.WEAPON_GEOMETRY_VERSION == 5


def test_ac96_the_directory_header_and_the_attachments_export_record_attach_version_9(tmp_path):
    directory = W.build(tmp_path, WORLD)[0]
    assert directory["attach_version"] == 12 and directory["geometry_version"] == 5
    gf = snapshot(directory, attachments=True)["generated_from"]
    assert gf["attach_version"] == 12 and gf["attach_rules_digest"] == directory["attach_rules_digest"]


def test_ac96_the_default_export_header_is_the_w7_one(tmp_path):
    gf = snapshot(W.build(tmp_path, WORLD)[0], attachments=False)["generated_from"]
    assert "attach_version" not in gf and "attach_rules_digest" not in gf
    assert gf["rules_digest"] == "7b9829af37328fe7" and gf["geometry_version"] == 5
