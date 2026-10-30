"""E3 slice D3: the build report carries the AC139 fill list and the AC147 frame counts (S11 finding 8).

AC139 and AC147 (docs/weapon_attach_geometry.md) say the build reports the preset fill list, the frame-conflict count and the frame-changed hosts
with their class. ``build_directory_report`` returns them in three new keys, over the packs built (as ``feature_counts``):

* ``frame_counts``: ``{"changed": n, "conflict": n}``, the hosts whose frame vote changed / conflicted;
* ``frame_changed_hosts``: ``[{"host", "class"}]`` sorted by host id (``class`` is the record's archetype);
* ``fill_list``: ``[{"host", "class", "slot"}]`` sorted by (host, slot): exactly the slots ``mounts.refuse_filled`` refused where its located-part
  disjunct (``slot in filled``) is true (the part the locator found on a preset fills the slot, alone or with the baked-glass disjunct). A slot only
  the glass / ``occupied_by`` disjuncts refused is not in it, nor is one ``refuse_filled`` skipped.

``refuse_filled`` returns that slot list, ``build_mounts`` hands it on as ``refused_by_located``, and ``geometry.measure_weapon_detail`` copies it into
the measurement detail beside ``child_extents``, so it rides the geometry cache with the rest of the detail.

World: ``fixtures/weapons/g1_world.py`` (``FAKE_G1``; its docstring says what each host is for). Every expected value below is a LITERAL worked out
by hand from that docstring: UZI is the one frame-changed host (an SMG), BOTH the one frame-conflict host, PRESET the rod rifle with a scope and a
silencer fused in (optic and muzzle refused by the located parts), PRESET_MAG a preset with a magazine fused in (a located magazine adds nothing:
it stays open). The keys are never part of the directory.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from synty_inventory.paths import load_config

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("g1_world", FIX / "g1_world.py")
GW = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(GW)
W = GW.W

from synty_inventory import weapons as pkg  # noqa: E402
from synty_inventory.weapons import directory as dirmod  # noqa: E402
from synty_inventory.weapons import mounts as mountmod  # noqa: E402
from synty_inventory.weapons.overrides import empty_overrides  # noqa: E402

REPORT_KEYS = ("frame_counts", "frame_changed_hosts", "fill_list")
# two more presets, in the test only (see ``glass_world``)
GLASS_PRESET = "SM_Wep_Preset_Rifle_02"  # a baked glass child no part of the pack matches: the glass disjunct alone
BOTH_PRESET = "SM_Wep_Preset_Rifle_03"  # a baked scope child that IS the pack's scope part: the locator finds it too (glass and located together)


def glass_world() -> dict:
    """``GW.world()`` plus two presets built from the world's own helpers (``W.host_node``, ``W.kid``, ``GW.rod_rifle``, ``GW.scope_kid``), because the
    fake world has no preset with a baked glass child:

    * ``GLASS_PRESET``: the rod rifle with a child named ``Scope`` (glass by name) whose mesh is a small box that matches no pack part. Its optic is
      refused by the baked-glass disjunct of ``refuse_filled`` and the locator finds nothing on it: the located disjunct is true for no slot.
    * ``BOTH_PRESET``: the rod rifle with the world's baked scope child (``GW.scope_kid``, the SCOPE part's own mesh). The locator finds that child's
      vertices as the SCOPE part, so its optic is refused by the glass and the located disjunct together (the shape of the live sniper preset)."""
    world = GW.world()
    hosts = world[GW.PACK]["hosts"]
    small_box = GW.G.box((-0.01, 0.0, -0.03), (0.01, 0.02, 0.03))
    hosts[GLASS_PRESET] = W.host_node(GLASS_PRESET, GW.rod_rifle(), [W.kid(GLASS_PRESET, "Scope", small_box, GW.SCOPE_AT)])
    hosts[BOTH_PRESET] = W.host_node(BOTH_PRESET, GW.rod_rifle(), [GW.scope_kid(BOTH_PRESET)])
    return world


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    world = GW.world()
    cat, root = W.write_world(tmp_path_factory.mktemp("e3_report"), world)
    return SimpleNamespace(cat=cat, root=root, settings=W.pack_settings(world))


@pytest.fixture(scope="module")
def glass_tree(tmp_path_factory):
    world = glass_world()
    cat, root = W.write_world(tmp_path_factory.mktemp("e3_report_glass"), world)
    return SimpleNamespace(cat=cat, root=root, settings=W.pack_settings(world))


def build(tree, *, measure=True, geometry_cache=None):
    """``(directory, excluded, report)`` of the world; ``measure=False`` is the unmeasured build (no geometry, so no vote and no mounts)."""
    return dirmod.build_directory_report(
        tree.cat, overrides=empty_overrides(), pack_settings=tree.settings, rules=W.sight_rules(), measure=measure,
        threejs_v2_dir=tree.root, geometry_cache={} if geometry_cache is None else geometry_cache)


@pytest.fixture(scope="module")
def built(tree):
    d, _ex, report = build(tree)
    return SimpleNamespace(directory=d, report=report, by_id=W.by_id(d))


def keys_of(report) -> dict:
    return {k: report[k] for k in REPORT_KEYS}


# --- frame_counts and frame_changed_hosts ----------------------------------------------------------------------------------


def test_the_frame_counts_and_the_frame_changed_hosts_on_fake_g1(built):
    # by hand (g1_world): UZI votes a new forward (the body axis is z, the bounding box says y): changed. BOTH has a bore ring at both ends: a conflict
    # (and keeps the build's frame, so it is not changed). Every other eligible host votes the build's frame. One of each.
    assert built.report["frame_counts"] == {"changed": 1, "conflict": 1}
    assert built.report["frame_changed_hosts"] == [{"host": GW.pid(GW.UZI), "class": "smg"}]
    assert built.by_id[GW.pid(GW.UZI)]["archetype"] == "smg"  # the class is the record's archetype


# --- fill_list -----------------------------------------------------------------------------------------------------------------


def test_the_fill_list_is_the_presets_fused_optic_and_muzzle(built):
    # PRESET has a scope and a silencer fused into its mesh: the located parts fill its optic and muzzle (sorted: muzzle, optic). Its baked magazine child
    # fills a slot that stays open (attach_filled_open), so no magazine row. PRESET_MAG has only a fused magazine: it adds nothing.
    want = [{"host": GW.pid(GW.PRESET), "class": "rifle", "slot": "muzzle"},
            {"host": GW.pid(GW.PRESET), "class": "rifle", "slot": "optic"}]
    assert built.report["fill_list"] == want
    assert built.by_id[GW.pid(GW.PRESET)]["archetype"] == "rifle"
    # the mounts the list stands for are refused
    m = built.by_id[GW.pid(GW.PRESET)]["geometry"]["mounts"]
    assert [(s, m[s]["source"], m[s]["reason"]) for s in ("muzzle", "optic")] == [("muzzle", "none", "slot_disabled"), ("optic", "none", "slot_disabled")]
    assert built.by_id[GW.pid(GW.PRESET_MAG)]["geometry"]["mounts"]["magazine"]["reason"] != "slot_disabled"  # the located magazine refuses nothing
    # hosts with a baked scope (SCOPED, ROCKET) are not presets: their filled slots are not additions
    assert {row["host"] for row in built.report["fill_list"]} == {GW.pid(GW.PRESET)}


def test_a_slot_only_the_baked_glass_refuses_is_not_in_the_fill_list(glass_tree):
    # GLASS_PRESET: a preset with a baked glass child and nothing the locator finds. Its optic is refused (the glass disjunct) but by no located part,
    # so no row names it. BOTH_PRESET's optic is refused by the glass AND the located scope: that one is a row (co-cause), as the live sniper preset.
    d, _ex, report = build(glass_tree)
    by_id = W.by_id(d)
    m = by_id[GW.pid(GLASS_PRESET)]["geometry"]["mounts"]
    assert (m["optic"]["source"], m["optic"]["reason"]) == ("none", "slot_disabled")  # refused ...
    assert [row for row in report["fill_list"] if row["host"] == GW.pid(GLASS_PRESET)] == []  # ... but not by a located part
    m = by_id[GW.pid(BOTH_PRESET)]["geometry"]["mounts"]
    assert (m["optic"]["source"], m["optic"]["reason"]) == ("none", "slot_disabled")
    assert report["fill_list"] == [
        {"host": GW.pid(GW.PRESET), "class": "rifle", "slot": "muzzle"}, {"host": GW.pid(GW.PRESET), "class": "rifle", "slot": "optic"},
        {"host": GW.pid(BOTH_PRESET), "class": "rifle", "slot": "optic"}]


# --- the unmeasured build ------------------------------------------------------------------------------------------------------


def test_an_unmeasured_build_has_the_three_keys_empty(tree):
    # measure=False: no record is measured, so there is no vote and no located part. The keys exist (no KeyError) and say nothing.
    _d, _ex, report = build(tree, measure=False)
    assert report["frame_counts"] == {"changed": 0, "conflict": 0}
    assert report["frame_changed_hosts"] == []
    assert report["fill_list"] == []


# --- the directory is unchanged ------------------------------------------------------------------------------------------------


def test_the_report_keys_never_enter_the_directory(built):
    # the header keys are the literal set (no report key among them) and no record or geometry block carries a report key or the carried slot list ...
    assert sorted(built.directory) == sorted([
        "schema", "weapon_version", "geometry_version", "rules_digest", "overrides_digest", "attach_version", "attach_rules_digest", "fit_digest",
        "packs", "counts", "weapons"])
    own = set(REPORT_KEYS) | {"refused_by_located"}
    assert all(not own & set(rec) and not own & set(rec["geometry"] or {}) for rec in built.directory["weapons"])
    # ... and the bytes are the ones the base (bc3657f) wrote for this world: the sha256 of the sorted compact JSON, taken from the unmodified code
    blob = json.dumps(built.directory, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert hashlib.sha256(blob.encode()).hexdigest() == "2d026cbce542d8858217161f93306404d8ad708f1350a07eee793d34784ae14f"
    assert built.directory["fit_digest"] == "9e88713e0a47d5d0"


# --- the cache path ------------------------------------------------------------------------------------------------------------


def test_a_warm_build_gives_the_same_three_keys_and_the_cached_detail_carries_the_slot_list(tree):
    # the slot list lives in the measurement detail, which the geometry cache stores whole: a second build over the same cache decodes nothing and
    # reports the same three keys; the cached entry of PRESET holds the list the cold build computed.
    cache: dict = {}
    _d1, _e1, cold = build(tree, geometry_cache=cache)
    _d2, _e2, warm = build(tree, geometry_cache=cache)
    assert cold["geometry_stats"]["decoded"] > 0
    assert warm["geometry_stats"]["decoded"] == 0 and warm["geometry_stats"]["cached"] == cold["geometry_stats"]["decoded"] + cold["geometry_stats"]["cached"]
    assert keys_of(warm) == keys_of(cold)
    assert keys_of(cold)["fill_list"] != []  # not vacuous
    held = [detail["refused_by_located"] for entry in cache.values() for detail in entry["by_inputs"].values() if "refused_by_located" in detail]
    assert held and all(isinstance(slots, list) for slots in held)  # every eligible host's cached detail has it
    assert {tuple(slots) for slots in held} == {(), ("optic", "muzzle")}  # PRESET's list (ATTACH_SLOTS order), an empty one for every other host


# --- refuse_filled's return value ----------------------------------------------------------------------------------------------

TABLES = {"attach_filled_hosts": ["preset"], "attach_filled_open": ["magazine"]}
PRESET_ID = "pack/SM_Wep_Preset_Unit_01"


def _mounts(**sources) -> dict:
    """A mount block: every slot ``none`` / ``no_child_no_probe`` unless ``sources`` says ``slot=(source, occupied_by)``."""
    block = {slot: mountmod.none_mount("no_child_no_probe") for slot in pkg.ATTACH_SLOTS}
    for slot, (source, occupied_by) in sources.items():
        block[slot] = {**mountmod.none_mount("x"), "source": source, "reason": None, "occupied_by": list(occupied_by)}
    return block


def _refuse(block, host=PRESET_ID, glass=(), body=(), located=None):
    found = {"glass": list(glass), "body": list(body), "iron": [], "handle": []}
    return mountmod.refuse_filled(block, found, host, TABLES, located)


def _refused(block) -> set:
    return {slot for slot, m in block.items() if m["reason"] == "slot_disabled"}


def test_refuse_filled_returns_the_slots_its_located_disjunct_refused():
    block = _mounts(optic=("probe", []), muzzle=("probe", []), underbarrel=("probe", []))
    got = _refuse(block, located=[{"part": "a", "slot": "optic"}, {"part": "b", "slot": "muzzle"}])
    assert sorted(got) == ["muzzle", "optic"]
    assert _refused(block) == {"muzzle", "optic"}  # the refusal itself is as before; underbarrel stays open


def test_refuse_filled_returns_a_slot_the_located_part_and_the_glass_both_refuse():
    block = _mounts(optic=("probe", []))
    assert _refuse(block, glass=["Scope"], located=[{"part": "a", "slot": "optic"}]) == ["optic"]  # co-cause counts
    assert _refused(block) == {"optic"}


def test_refuse_filled_does_not_return_a_slot_only_the_glass_or_occupied_by_refused():
    block = _mounts(optic=("probe", []), underbarrel=("child_node", ["Grip"]))
    assert _refuse(block, glass=["Scope"]) == []  # glass alone ...
    assert _refused(block) == {"optic", "underbarrel"}  # ... still refuses, occupied_by too
    block = _mounts(optic=("probe", []))
    assert _refuse(block, body=["Receiver"], located=[]) == []


def test_refuse_filled_does_not_return_a_slot_it_skipped():
    located = [{"part": "a", "slot": "optic"}, {"part": "b", "slot": "muzzle"}, {"part": "c", "slot": "magazine"}, {"part": "d", "slot": None}]
    block = _mounts(optic=("override", []), muzzle=("none", []), magazine=("probe", []))
    assert _refuse(block, located=located) == []  # override kept, source none skipped, magazine is attach_filled_open, no slot fills nothing
    assert _refused(block) == set() and block["optic"]["source"] == "override"


def test_refuse_filled_returns_nothing_for_a_host_that_is_not_a_preset():
    block = _mounts(optic=("probe", []))
    assert _refuse(block, host="pack/SM_Wep_Rifle_Unit_01", located=[{"part": "a", "slot": "optic"}]) == []
    assert _refused(block) == set()


# --- live guard ----------------------------------------------------------------------------------------------------------------


@pytest.mark.live
def test_live_the_fill_list_is_two_slots():
    """The live pin: the real build's ``fill_list`` has exactly 2 rows (AC139, errata E3.5; trace T-fill, 2026-10-28).

    The two slots are the rifle preset's muzzle (the located part is the sole cause) and the sniper preset's optic (the located part and the baked
    glass both refuse it). Where the located disjunct is the sole cause there is 1 slot (data from the trace, not asserted here). The directory is
    built in memory from the configured catalogs: nothing is written and the caches are throwaway dicts."""
    from synty_inventory.paths import ConfigError
    from synty_inventory.weapons.overrides import load_overrides
    from synty_inventory.weapons.rules import load_rules

    try:
        cfg = load_config(require=False)
    except ConfigError:
        pytest.skip("the library is not on this machine")
    if not all(cfg.get(k) is not None and Path(cfg[k]).is_dir() for k in ("catalogs", "threejs_v2", "extracted_root")):
        pytest.skip("the library is not on this machine")
    from synty_inventory.weapons import overrides as overrides_mod
    committed = Path(overrides_mod.__file__).resolve().parent.parent / "data" / "weapon_overrides.json"  # by path: the suite points the default at an empty file
    _d, _excluded, report = dirmod.build_directory_report(
        Path(cfg["catalogs"]), packs=None, rules=load_rules(), overrides=load_overrides(committed), measure=True, base=None,
        threejs_v2_dir=Path(cfg["threejs_v2"]), geometry_cache={}, extracted_root=Path(cfg["extracted_root"]), fit_cache={})
    assert len(report["fill_list"]) == 2


# --- frame_sight_gain (AC149, errata E3.5a) ------------------------------------------------------------------------------------

_SPEC = importlib.util.spec_from_file_location("e3_sight_world", FIX / "e3_sight_world.py")
S = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(S)


def _sight_tree(tmp_path_factory, name, *, with_plain):
    """The sight-clause world written to disk: ``(catalogs dir, GLB root, pack settings)``."""
    world = S.sight_world(with_plain=with_plain)
    cat, root = S.W.write_world(tmp_path_factory.mktemp(name), world)
    return cat, root, S.W.pack_settings(world)


def _sight_build(tree, geometry_cache=None):
    """``(directory, report)`` of a sight-clause tree in the voted frame (no ``frame_axis`` override), measured, over ``geometry_cache``."""
    cat, root, settings = tree
    d, _ex, report = dirmod.build_directory_report(
        cat, overrides=S.voted_overrides(), pack_settings=settings, rules=S.W.sight_rules(), measure=True,
        threejs_v2_dir=root, geometry_cache={} if geometry_cache is None else geometry_cache)
    return d, report


def test_frame_sight_gain_counts_the_frame_changed_host_that_gains_sight_seats(tmp_path_factory):
    """AC149 / E3.5a: no single build holds the build-frame sight state, so a frame-changed host is probed once more in the build frame and the report
    counts the hosts whose sight slot reads ``probe_unavailable`` there and is seated by the probe in the voted frame. By hand (e3_sight_world): PLAIN is
    the Uzi with no post, no seat in the build frame (forward -y) and both seats in the voted frame (forward +z): one host. POST has the same two frames
    but a fused post, so the voted frame reads ``slot_disabled`` (a refusal, not a seat): not counted. RIFLE and BOTH are not frame-changed."""
    plain = _sight_tree(tmp_path_factory, "e3_gain_plain", with_plain=True)
    d, report = _sight_build(plain)
    by_id = S.W.by_id(d)
    assert by_id[S.pid(S.PLAIN)]["archetype"] == "smg"  # the literal class below is the record's archetype
    assert report["frame_sight_gain"] == {"count": 1, "hosts": [{"host": "FAKE_G1/SM_Wep_SMG_Uzi_01", "class": "smg"}]}
    assert S.pid(S.PLAIN) == "FAKE_G1/SM_Wep_SMG_Uzi_01"
    # the mechanism it counts, in the voted directory: PLAIN seats both sights by the probe, POST has them refused by its post
    assert [by_id[S.pid(S.PLAIN)]["geometry"]["mounts"][s]["source"] for s in ("sight_front", "sight_rear")] == ["probe", "probe"]
    assert [by_id[S.pid(S.POST)]["geometry"]["mounts"][s]["reason"] for s in ("sight_front", "sight_rear")] == ["slot_disabled", "slot_disabled"]
    assert {h["host"] for h in report["frame_changed_hosts"]} == {"FAKE_G1/SM_Wep_SMG_Uzi_01", "FAKE_G1/SM_Wep_SMG_Post_01"}  # both are frame-changed
    # a warm rebuild over the same geometry cache reports the same key: the flag rides the cached measurement detail
    cache: dict = {}
    _d, cold = _sight_build(plain, cache)
    _d, warm = _sight_build(plain, cache)
    assert cold["geometry_stats"]["decoded"] > 0 and warm["geometry_stats"]["decoded"] == 0
    assert warm["frame_sight_gain"] == cold["frame_sight_gain"] == report["frame_sight_gain"]
    # the world without PLAIN: POST is the one frame-changed host, its sight slots are probe_unavailable in the build frame, and its fused post refuses
    # them in the voted frame: not a gain
    d0, report0 = _sight_build(_sight_tree(tmp_path_factory, "e3_gain_post_only", with_plain=False))
    assert [h["host"] for h in report0["frame_changed_hosts"]] == ["FAKE_G1/SM_Wep_SMG_Post_01"]  # not vacuous: a frame-changed host is there
    assert report0["frame_sight_gain"] == {"count": 0, "hosts": []}
    assert "frame_sight_gain" not in d0 and all("frame_sight_gain" not in r for r in d0["weapons"])  # never part of the directory
