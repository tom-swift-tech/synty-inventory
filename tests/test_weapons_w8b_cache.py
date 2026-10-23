"""W8b: determinism and the geometry cache with host mounts (AC78, geometry half; docs/weapon_attachments.md 3.5).

An eligible host's mounts are cached with the rest of its measurement. Its fingerprint carries ``WEAPON_ATTACH_VERSION``
(read at call time), so an attach bump re-measures the hosts as well as the parts; ``WEAPON_GEOMETRY_VERSION`` stays 5 and
bumping it re-measures everything. A host that is not eligible has the fingerprint W7 computed, so an attach bump leaves it
cached.
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
from synty_inventory.weapons.geometry import _inputs_fingerprint, measure_cached  # noqa: E402
from synty_inventory.weapons.overrides import empty_overrides  # noqa: E402
from synty_inventory.weapons.rules import load_rules  # noqa: E402

N_ELIGIBLE = 9  # FAKE_Mount hosts that are whole + ranged + one_hand/long_gun (the grenade host is the tenth asset)
N_ASSETS = 10
N_ATTACH_PARTS, N_ATTACH_HOSTS = 24, 2  # the W8a fixture: 24 parts with a slot, plus the assault rifle and the pistol


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    return A.write_mount_world(tmp_path_factory.mktemp("w8b_cache"))


def run(world, cache):
    cat, root = world
    d, _, report = build_directory_report(cat, overrides=empty_overrides(), pack_settings=A.MOUNT_SETTINGS,
                                          threejs_v2_dir=root, geometry_cache=cache)
    return d, report["geometry_stats"]


def dump(directory) -> str:
    return json.dumps(directory, sort_keys=True)


def test_the_geometry_version_is_still_5_and_the_attach_version_is_a_positive_integer():
    assert pkg.WEAPON_GEOMETRY_VERSION == 5  # W8b does not bump it (brief, AC77)
    assert isinstance(pkg.WEAPON_ATTACH_VERSION, int) and pkg.WEAPON_ATTACH_VERSION >= 1


def test_ac78_two_builds_are_identical_and_the_second_decodes_nothing(world):
    cache: dict = {}
    d1, s1 = run(world, cache)
    d2, s2 = run(world, cache)
    assert dump(d1) == dump(d2)
    assert s1 == {"decoded": N_ASSETS, "cached": 0}
    assert s2 == {"decoded": 0, "cached": N_ASSETS}


def test_ac78_a_cache_hit_equals_a_fresh_recompute_and_survives_a_json_round_trip(world):
    cache: dict = {}
    fresh, _ = run(world, cache)
    hit, stats = run(world, json.loads(json.dumps(cache)))
    assert stats["decoded"] == 0 and dump(hit) == dump(fresh)
    mounted = [w for w in hit["weapons"] if w["geometry"]["mounts"] is not None]
    assert len(mounted) == N_ELIGIBLE  # the hit still carries every mounts block


def test_ac78_an_attach_version_bump_remeasures_exactly_the_eligible_hosts(world, monkeypatch):
    cache: dict = {}
    d1, s1 = run(world, cache)
    monkeypatch.setattr(pkg, "WEAPON_ATTACH_VERSION", pkg.WEAPON_ATTACH_VERSION + 1)
    d2, s2 = run(world, cache)
    assert s2 == {"decoded": N_ELIGIBLE, "cached": N_ASSETS - N_ELIGIBLE}  # not the grenade host
    assert [w["geometry"] for w in d2["weapons"]] == [w["geometry"] for w in d1["weapons"]]  # the bump moves no number
    assert d2["attach_version"] == d1["attach_version"] + 1


def test_ac78_the_w8a_world_bump_remeasures_the_parts_and_its_two_hosts(tmp_path, monkeypatch):
    cat, root = A.write_world(tmp_path)

    def go(cache):
        _, _, rep = build_directory_report(cat, overrides=empty_overrides(), pack_settings=A.PACK_SETTINGS,
                                           threejs_v2_dir=root, geometry_cache=cache)
        return rep["geometry_stats"]

    cache: dict = {}
    s1 = go(cache)
    monkeypatch.setattr(pkg, "WEAPON_ATTACH_VERSION", pkg.WEAPON_ATTACH_VERSION + 1)
    s2 = go(cache)
    assert s2["decoded"] == N_ATTACH_PARTS + N_ATTACH_HOSTS and s2["cached"] == s1["decoded"] - s2["decoded"]


def test_ac78_a_geometry_version_bump_remeasures_everything(world, monkeypatch):
    cache: dict = {}
    _, s1 = run(world, cache)
    monkeypatch.setattr(pkg, "WEAPON_GEOMETRY_VERSION", pkg.WEAPON_GEOMETRY_VERSION + 1)
    _, s2 = run(world, cache)
    assert s2 == {"decoded": N_ASSETS, "cached": 0}


def test_ac78_an_eligible_fingerprint_carries_the_attach_version_and_the_others_do_not(monkeypatch):
    rules = load_rules()
    eligible = [("rifle", "ranged", "whole", "long_gun", "modern"), ("pistol", "ranged", "whole", "one_hand", "modern")]
    others = [("grenade", "thrown", "whole", "thrown", "modern"), ("sword", "melee", "whole", "melee_one", "modern"),
              ("unknown", None, "part", "none", "modern"), ("rifle", "ranged", "emplaced", "none", "modern")]
    before = {a: _inputs_fingerprint(*a[:4], a[4], rules) for a in eligible + others}
    monkeypatch.setattr(pkg, "WEAPON_ATTACH_VERSION", pkg.WEAPON_ATTACH_VERSION + 7)
    for a in eligible:
        assert _inputs_fingerprint(*a[:4], a[4], rules) != before[a], a
    for a in others:
        assert _inputs_fingerprint(*a[:4], a[4], rules) == before[a], a


def test_ac78_an_edit_to_the_child_tokens_or_an_override_changes_an_eligible_key_only():
    rules = load_rules()
    base = _inputs_fingerprint("rifle", "ranged", "whole", "long_gun", "modern", rules)
    edited = copy.deepcopy(rules)
    edited["attachment_rules"]["child_tokens"]["optic"] = list(edited["attachment_rules"]["child_tokens"]["optic"]) + ["zzscope"]
    assert _inputs_fingerprint("rifle", "ranged", "whole", "long_gun", "modern", edited) != base
    ov = {"optic": {"source": "none"}}
    assert _inputs_fingerprint("rifle", "ranged", "whole", "long_gun", "modern", rules, mount_overrides=ov) != base
    sword = _inputs_fingerprint("sword", "melee", "whole", "melee_one", "modern", rules)
    assert _inputs_fingerprint("sword", "melee", "whole", "melee_one", "modern", edited) == sword
    assert _inputs_fingerprint("sword", "melee", "whole", "melee_one", "modern", rules, mount_overrides=ov) == sword


def test_ac78_measure_cached_returns_a_private_copy_with_the_mounts(world):
    cat, root = world
    rules = load_rules()
    cache: dict = {}
    rel = f"glb/{A.MOUNT_PACK}/SM_Wep_Rifle_Mount_01.glb"
    first, hit1 = measure_cached(root, rel, None, 1.0, "rifle", "ranged", "whole", rules, cache, hold_class="long_gun", genre="modern")
    first["mounts"]["optic"]["point"][0] = 99.0
    again, hit2 = measure_cached(root, rel, None, 1.0, "rifle", "ranged", "whole", rules, cache, hold_class="long_gun", genre="modern")
    assert (hit1, hit2) == (False, True)
    assert abs(again["mounts"]["optic"]["point"][0] - 0.005) <= 1e-3  # the stored entry was not touched through the copy
