"""W8a: the geometry cache and the attachment anchor (AC78, parts half; docs/weapon_attachments.md 3.5).

An anchor is cached with the rest of a part's measurement, keyed by the part's slot and the attachment version, so a bump of
``WEAPON_ATTACH_VERSION`` re-measures exactly the attachment parts and a bump of ``WEAPON_GEOMETRY_VERSION`` re-measures all.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("w8a_attach", Path(__file__).parent / "fixtures" / "weapons" / "w8a_attach.py")
A = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A)

from synty_inventory import weapons as pkg  # noqa: E402
from synty_inventory.weapons.directory import build_directory_report  # noqa: E402
from synty_inventory.weapons.geometry import measure_cached  # noqa: E402
from synty_inventory.weapons.overrides import empty_overrides  # noqa: E402
from synty_inventory.weapons.rules import load_rules  # noqa: E402

N_ATTACHMENTS = 24  # the fixture parts whose expected slot/kind is not None (w8a_attach.PARTS); counted again below


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    cat, root = A.write_world(tmp_path_factory.mktemp("w8a_cache"))
    return cat, root


def run(world, cache):
    cat, root = world
    d, e, report = build_directory_report(cat, overrides=empty_overrides(), pack_settings=A.PACK_SETTINGS,
                                          threejs_v2_dir=root, geometry_cache=cache)
    return d, e, report["geometry_stats"]


def attachments(directory):
    return [w for w in directory["weapons"] if w.get("attachment")]


def dump(directory) -> str:
    return json.dumps(directory, sort_keys=True)


def test_the_fixture_has_the_attachment_count_the_tests_assume(world):
    d, _, _ = run(world, {})
    assert len(attachments(d)) == N_ATTACHMENTS == len([1 for _, exp in A.PARTS.values() if exp is not None])


def test_ac78_two_builds_are_identical_and_the_second_decodes_nothing(world):
    cache: dict = {}
    d1, _, s1 = run(world, cache)
    d2, _, s2 = run(world, cache)
    assert dump(d1) == dump(d2)
    assert s1["decoded"] > 0 and s1["cached"] == 0
    assert s2 == {"decoded": 0, "cached": s1["decoded"]}


def test_ac78_a_cache_hit_gives_the_same_directory_as_a_fresh_recompute_and_survives_a_json_round_trip(world):
    cache: dict = {}
    fresh, _, _ = run(world, cache)
    reloaded = json.loads(json.dumps(cache))  # what a cache file on disk does to it
    hit, _, stats = run(world, reloaded)
    assert stats["decoded"] == 0
    assert dump(hit) == dump(fresh)
    assert len(attachments(hit)) == N_ATTACHMENTS


def test_ac78_an_attach_version_bump_remeasures_exactly_the_attachment_parts(world, monkeypatch):
    cache: dict = {}
    d1, _, s1 = run(world, cache)
    monkeypatch.setattr(pkg, "WEAPON_ATTACH_VERSION", pkg.WEAPON_ATTACH_VERSION + 1)
    d2, _, s2 = run(world, cache)
    assert s2["decoded"] == N_ATTACHMENTS  # every part with a slot, and no host, no other part
    assert s2["cached"] == s1["decoded"] - N_ATTACHMENTS
    # the anchors themselves are unchanged by the bump; only the header version moves
    assert [w.get("attachment") for w in d2["weapons"]] == [w.get("attachment") for w in d1["weapons"]]
    assert d2["attach_version"] == d1["attach_version"] + 1


def test_ac78_a_geometry_version_bump_remeasures_everything(world, monkeypatch):
    cache: dict = {}
    _, _, s1 = run(world, cache)
    monkeypatch.setattr(pkg, "WEAPON_GEOMETRY_VERSION", pkg.WEAPON_GEOMETRY_VERSION + 1)
    _, _, s2 = run(world, cache)
    assert s2["decoded"] == s1["decoded"] and s2["cached"] == 0


def test_ac78_the_slot_is_part_of_the_cache_key(world):
    cat, root = world
    rules = load_rules()
    cache: dict = {}
    rel = f"glb/{A.PACK}/SM_Wep_Rifle_Scope_01.glb"
    first, hit1 = measure_cached(root, rel, None, 1.0, "unknown", None, "part", rules, cache, attach_slot="optic")
    again, hit2 = measure_cached(root, rel, None, 1.0, "unknown", None, "part", rules, cache, attach_slot="optic")
    other, hit3 = measure_cached(root, rel, None, 1.0, "unknown", None, "part", rules, cache, attach_slot="underbarrel")
    plain, hit4 = measure_cached(root, rel, None, 1.0, "unknown", None, "part", rules, cache)
    assert (hit1, hit2, hit3, hit4) == (False, True, False, False)
    # the bottom-foot mesh suits an optic slot; asked as an underbarrel it finds no foot at the top and falls back
    assert first["attach"]["anchor"]["foot_source"] == "authored_up" and other["attach"]["anchor"]["foot_source"] == "measured"
    assert copy.deepcopy(again["attach"]) == first["attach"]
    assert "attach" not in plain  # a record without a slot has no anchor and shares no entry with one that has


def test_ac78_a_non_attachment_record_cache_key_is_what_w7_computed(world):
    from synty_inventory.weapons.geometry import _inputs_fingerprint

    rules = load_rules()
    plain = _inputs_fingerprint("pistol", "ranged", "whole", "one_hand", "modern", rules)
    assert _inputs_fingerprint("pistol", "ranged", "whole", "one_hand", "modern", rules, attach_slot=None) == plain
    assert _inputs_fingerprint("unknown", None, "part", "none", None, rules, attach_slot="optic") != \
        _inputs_fingerprint("unknown", None, "part", "none", None, rules)
