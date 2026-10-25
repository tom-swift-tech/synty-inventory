"""W8m: versions, the contact rules table and the pair cache (docs/weapon_attachments.md 5.4 "Cache", AC78, AC116).

The expected values are LITERALS from the spec (attach version 10, geometry version 5, rules digest 7b9829af37328fe7), never read from the constants
under test. World: ``w8m_world`` (pack FAKE_W8M).
"""

from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8m_world", FIX / "w8m_world.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)
W = M.W

import synty_inventory.weapons as pkg  # noqa: E402
from synty_inventory.weapons import directory as dirmod, geometry as geo  # noqa: E402
from synty_inventory.weapons.overrides import empty_overrides  # noqa: E402
from synty_inventory.weapons.rules import attach_rules_digest, load_rules, validate_rules, weapon_rules_digest  # noqa: E402


# --- AC116: versions ----------------------------------------------------------------------------------------------------------


def test_ac116_the_versions_and_the_digests():
    assert pkg.WEAPON_ATTACH_VERSION == 12 and pkg.WEAPON_GEOMETRY_VERSION == 5
    rules = load_rules()
    assert weapon_rules_digest(rules) == "7b9829af37328fe7"  # `contact` sits inside attachment_rules: rules_digest never moves
    assert len(attach_rules_digest(rules)) == 16
    assert "optic_seat" not in rules["attachment_rules"] and rules["attachment_rules"]["contact"]["slots"] == ["optic", "underbarrel"]


def test_ac116_the_contact_table_moves_the_attach_digest_only():
    base = load_rules()
    for mutate in (lambda t: t["contact"].update(dead_m=0.004), lambda t: t["contact"].update(slots=["optic"]),
                   lambda t: t.pop("contact")):
        rules = deepcopy(base)
        mutate(rules["attachment_rules"])
        assert weapon_rules_digest(rules) == weapon_rules_digest(base) and attach_rules_digest(rules) != attach_rules_digest(base)


def test_ac116_the_shipped_contact_table_is_the_specified_one():
    assert load_rules()["attachment_rules"]["contact"] == {
        "slots": ["optic", "underbarrel"], "slab_m": 0.004, "pitch_m": 0.0025, "dead_m": 0.003, "clamp_m": 0.06, "reach_m": 0.5,
        "cap_m": 0.03}  # A6 (W8n): the cap, 30 mm


# --- the contact table validates ---------------------------------------------------------------------------------------------


def broken(mutate):
    rules = deepcopy(load_rules())
    mutate(rules["attachment_rules"])
    return validate_rules(rules)


@pytest.mark.parametrize(("mutate", "needle"), [
    (lambda t: t["contact"].update(clamp_m=0.061), "clamp_m"),          # above the schema bound of seat_shift_m
    (lambda t: t["contact"].update(clamp_m=0.0), "clamp_m"),
    (lambda t: t["contact"].update(dead_m=0.04, clamp_m=0.03), "dead_m must be below clamp_m"),
    (lambda t: t["contact"].update(dead_m=-0.001), "dead_m"),
    (lambda t: t["contact"].update(slab_m=0.0), "slab_m"),
    (lambda t: t["contact"].update(pitch_m="fine"), "pitch_m"),
    (lambda t: t["contact"].update(reach_m=True), "reach_m"),
    (lambda t: t["contact"].pop("reach_m"), "reach_m"),
    (lambda t: t["contact"].update(slots=[]), "slots"),
    (lambda t: t["contact"].update(slots=["muzzle"]), "slots"),          # the key lives on optic and underbarrel entries only
    (lambda t: t["contact"].update(slots=["optic", "optic"]), "distinct"),
    (lambda t: t["contact"].update(surprise=1), "surprise"),
    (lambda t: t.update(contact=[1]), "contact"),
])
def test_the_contact_table_rejects_a_malformed_value(mutate, needle):
    errors = broken(mutate)
    assert errors and any(needle in e for e in errors), errors


def test_the_shipped_rules_validate_and_a_table_without_contact_is_valid():
    assert validate_rules(load_rules()) == []
    assert broken(lambda t: t.pop("contact")) == []


# --- the pair cache ----------------------------------------------------------------------------------------------------------


@pytest.fixture()
def tree(tmp_path):
    cat, root = W.write_world(tmp_path, M.world())
    return cat, root


def run(tree, cache, rules=None, with_root=True, base=None):
    cat, root = tree
    return dirmod.build_directory_report(
        cat, overrides=empty_overrides(), pack_settings=W.pack_settings(M.world()), rules=rules or W.sight_rules(),
        threejs_v2_dir=root if with_root else None, geometry_cache=cache, base=base)


def keys(directory) -> dict:
    out = {}
    for w in directory["weapons"]:
        for e in (w.get("attachment") or {}).get("compatible_hosts") or []:
            out[(w["id"], e["host"])] = e.get("seat_shift_m")
    return out


def test_ac78_a_second_build_reads_every_pair_from_the_cache_and_equals_the_first(tree, monkeypatch):
    cache: dict = {}
    d1, _, r1 = run(tree, cache)
    n = r1["contact_stats"]["computed"]
    assert n >= 14 and r1["contact_stats"] == {"computed": n, "cached": 0, "kept": 0}  # 13 hosts' scope pairs, the tab, the grips: all settled
    assert {k for k, v in cache.items() if k.startswith("pair|")} and all(
        e["version"].startswith("5+") for k, e in cache.items() if k.startswith("pair|"))

    def refuse(*a, **k):
        raise AssertionError("a mesh was decoded on a build whose inputs did not change")

    monkeypatch.setattr(geo, "load_triangles", refuse)
    d2, _, r2 = run(tree, cache)
    assert r2["contact_stats"] == {"computed": 0, "cached": n, "kept": 0} and r2["geometry_stats"]["decoded"] == 0
    assert d2 == d1 and keys(d2) == keys(d1)  # a cache hit equals a recompute (the keyed pairs, the none pairs and the rest)
    monkeypatch.undo()
    d3, _, r3 = run(tree, {})
    assert d3 == d1 and r3["contact_stats"]["computed"] == n


def test_a_pair_with_no_key_is_cached_as_no_key(tree):
    cache: dict = {}
    run(tree, cache)
    entry = cache[f"pair|glb/{M.PACK}/{M.SCOPE_PART}.glb|glb/{M.PACK}/{M.host_id('Near')}.glb"]
    assert [v for v in entry["by_inputs"].values()] == [{"shift": None}]
    hover = cache[f"pair|glb/{M.PACK}/{M.SCOPE_PART}.glb|glb/{M.PACK}/{M.host_id('Hover')}.glb"]
    assert [v for v in hover["by_inputs"].values()] == [{"shift": -0.011}]


def test_a_changed_host_or_part_file_misses_and_remeasures(tree):
    cat, root = tree
    cache: dict = {}
    run(tree, cache)
    hover = root / "glb" / M.PACK / f"{M.host_id('Hover')}.glb"
    hover.write_bytes(hover.read_bytes() + b"\0" * 4)  # size and mtime move; glTF ignores trailing bytes? the loader must still decode it
    d, _, r = run(tree, cache)
    assert r["contact_stats"]["computed"] >= 1 and r["contact_stats"]["cached"] >= 13


def test_the_contact_table_the_attach_version_and_the_code_digests_are_in_the_fingerprint(tree, monkeypatch):
    cache: dict = {}
    _, _, r1 = run(tree, cache)
    n = r1["contact_stats"]["computed"]
    rules = W.sight_rules()
    rules["attachment_rules"]["contact"]["dead_m"] = 0.0035  # inside the table: every pair is a new question
    _, _, r2 = run(tree, cache, rules)
    assert r2["contact_stats"]["computed"] == n and r2["contact_stats"]["cached"] == 0
    _, _, r3 = run(tree, cache, rules)
    assert r3["contact_stats"]["cached"] == n
    for name in ("_ATTACH_CODE_DIGEST", "_PROBE_CODE_DIGEST"):
        monkeypatch.setattr(geo, name, "0" * 16)
        _, _, r = run(tree, cache, rules)
        assert r["contact_stats"]["computed"] == n and r["contact_stats"]["cached"] == 0, name
        monkeypatch.undo()
    monkeypatch.setattr(pkg, "WEAPON_ATTACH_VERSION", 13)
    _, _, r = run(tree, cache, rules)
    assert r["contact_stats"]["computed"] == n, "WEAPON_ATTACH_VERSION is in the pair fingerprint"


def test_a_moved_mount_frame_or_hide_list_is_another_question(tree):
    cat, root = tree
    d, _, _ = run(tree, {})
    by = W.by_id(d)
    part, host = by[M.pid(M.SCOPE_PART)], by[M.hid("Hover")]
    cache: dict = {}
    mount = host["geometry"]["mounts"]["optic"]
    args = (root, part["files"], host["files"], part["attachment"]["anchor"], mount)
    p = load_rules()["attachment_rules"]["contact"]
    hide = [M.host_id("Hover") + "_Scope"]  # the baked scope is the slot's occupant: the build hides it
    assert geo.settle_cached(*args, hide, "optic", p, cache) == (-0.011, "computed")
    assert geo.settle_cached(*args, hide, "optic", p, cache) == (-0.011, "cached")
    moved = dict(mount, point=[mount["point"][0], mount["point"][1] - 0.011, mount["point"][2]])  # the part now rests on the body
    assert geo.settle_cached(root, part["files"], host["files"], part["attachment"]["anchor"], moved, hide, "optic", p, cache) == (None, "computed")
    assert geo.settle_cached(*args, [], "optic", p, cache)[1] == "computed"  # another hide list (the scope child counted as surface)
    assert geo.settle_cached(*args, hide, "optic", p, cache) == (-0.011, "cached")  # the first answer is still there


def test_a_missing_or_undecodable_glb_is_unavailable_and_stores_no_answer(tree):
    cat, root = tree
    d, _, _ = run(tree, {})
    by = W.by_id(d)
    part, host = by[M.pid(M.SCOPE_PART)], by[M.hid("Hover")]
    p = load_rules()["attachment_rules"]["contact"]
    args = (part["attachment"]["anchor"], host["geometry"]["mounts"]["optic"], [], "optic", p)
    cache: dict = {}
    assert geo.settle_cached(root, part["files"], dict(host["files"], glb="glb/nowhere/missing.glb"), *args, cache) == (None, "unavailable")
    assert not cache
    garbage = root / "glb" / M.PACK / "garbage.glb"
    garbage.write_bytes(b"this is not a glb")
    assert geo.settle_cached(root, part["files"], dict(host["files"], glb=f"glb/{M.PACK}/garbage.glb"), *args, cache) == (None, "unavailable")
    assert all(not e["by_inputs"] for e in cache.values())  # no answer (not even "no key") is stored for a mesh that could not be read


def test_a_pair_whose_meshes_cannot_be_read_keeps_the_stored_key(tree):
    d1, _, _ = run(tree, {})
    records = deepcopy(d1["weapons"])
    stored = dirmod._stored_shifts(records)
    assert stored[(M.pid(M.SCOPE_PART), M.hid("Hover"))] == -0.011 and (M.pid(M.SCOPE_PART), M.hid("Near")) not in stored
    for r in records:
        for e in (r.get("attachment") or {}).get("compatible_hosts") or []:
            e.pop("seat_shift_m", None)
    stats = {"computed": 0, "cached": 0, "kept": 0}
    dirmod._apply_contact(records, W.sight_rules(), None, {}, stats, stored)  # no threejs root: nothing can be measured
    assert stats["computed"] == 0 and stats["cached"] == 0 and stats["kept"] >= 14
    now = dirmod._stored_shifts(records)
    assert now == stored  # exactly the keys the records carried, no more and no less


def test_a_rules_file_without_a_contact_table_writes_no_key(tree):
    rules = W.sight_rules()
    del rules["attachment_rules"]["contact"]
    d, _, r = run(tree, {}, rules)
    assert all(v is None for v in keys(d).values()) and r["contact_stats"] == {"computed": 0, "cached": 0, "kept": 0}


def test_a_table_naming_only_underbarrel_keys_no_optic(tree):
    rules = W.sight_rules()
    rules["attachment_rules"]["contact"]["slots"] = ["underbarrel"]
    d, _, _ = run(tree, {}, rules)
    got = keys(d)
    assert got[(M.pid(M.GRIP_PART), M.hid("UbGap"))] == -0.012 and got[(M.pid(M.SCOPE_PART), M.hid("Hover"))] is None
