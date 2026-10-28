"""E3.4: guard tests for the frame-derived fields of the feature frame (docs/weapon_attach_geometry.md 3.3 "Scope of the feature frame", AC146, AC147;
errata E3.4). Test-only: the code needs no change, the spec's list of fields a frame vote may move was short.

The synthetic hosts are in ``fixtures/weapons/e3_frame_fields_world.py``: SMG-shaped hosts whose magazine is longer than the body (so the
bounding box says y, the body z, and a 15 mm ring at the +z end confirms the vote), one of them with a pre-vote ``forward_by_fallback``, the
Uzi-shaped host of AC147 (the vote moves its inventory cells), a short one (the vote moves its size class, cells and weight class), and a plain
rifle with no frame change. The "old frame" side of each pair is the same world built with ``frame_axis`` set to the build axis, which keeps the
build frame (the version 5 record); the "new frame" side has no override. The default export (``export`` defaults: private profile, item frame, no
``--attachments``) of the two is diffed field by field.

Every list and number below is a LITERAL, written out here: the old list is the section 3.3 text of commit 41ca096 (before E3.4), the five-field list
is the first E3.4 text (f723f5c, committed in the first version of these tests), the amended list is the list with ``hints.inventory_cells`` and
``hints.weight_class`` added: both are derived from ``length_m`` (``inventory_cells`` from the length and the lateral extent, ``weight_class`` from
the size class) and move when the length crosses a step. None is read from the code under test.

Deliberate breaks, and the tests that fail on each:

* the old list used for the same assertion (the negative control): ``test_the_old_list_fails_the_same_assertion`` names what falls outside it;
* the five-field list (without the cells and the weight class): ``test_the_five_field_list_fails_on_the_hosts_that_move_cells_or_weight``;
* a list without ``geometry.bounds``: ``test_an_amended_list_without_bounds_fails_the_diff``;
* a vote that changes a field outside the list: ``test_a_vote_that_changes_a_non_listed_field_fails_the_guard``.

One live test (``-m live``, skipped without the licensed library) counts the live hosts whose cells or weight class move with the vote.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import shutil
from copy import deepcopy
from pathlib import Path

import pytest

_FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("e3_frame_fields_world", _FIX / "e3_frame_fields_world.py")
E = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(E)

from synty_inventory.paths import ConfigError, load_config  # noqa: E402
from synty_inventory.weapons import export as export_mod  # noqa: E402
from synty_inventory.weapons import geometry  # noqa: E402
from synty_inventory.weapons.directory import build_directory_report  # noqa: E402
from synty_inventory.weapons.overrides import load_overrides  # noqa: E402
from synty_inventory.weapons.rules import load_rules  # noqa: E402

W = E.W

# the fields a frame vote may move, one entry per field of the spec's list (a changed leaf collapses to its entry: geometry.bounds.size -> geometry.bounds)
OLD_LIST = frozenset({  # section 3.3 before E3.4 (41ca096): axes, item_basis, "length_m, tip, butt, grip and pivot points, and geometry.muzzle", review reasons
    "geometry.axes", "geometry.item_basis", "geometry.length_m", "geometry.tip", "geometry.butt", "geometry.grip", "geometry.pivot_frac",
    "geometry.muzzle", "review.reasons"})
E3_4_ADDED = frozenset({"geometry.bounds", "geometry.support", "geometry.support_r_m", "hints.size_class", "flags"})
FIVE_FIELD_LIST = OLD_LIST | E3_4_ADDED  # section 3.3 with the first E3.4 text: the cells and the weight class are held fixed
LENGTH_DERIVED = frozenset({"hints.inventory_cells", "hints.weight_class"})  # derived from length_m: they move when it crosses a step
AMENDED_LIST = FIVE_FIELD_LIST | LENGTH_DERIVED  # section 3.3 as amended

CHANGED_HOSTS = (E.ALPHA, E.BRAVO, E.DELTA, E.ECHO)
NESTED = ("geometry", "hints", "review")  # top-level records whose children are listed one by one


def collapse(path: tuple[str, ...]) -> str:
    return ".".join(path[:2] if path[0] in NESTED else path[:1])


def changed_fields(old, new, path=()):
    """The collapsed names of every field that differs between two records (a key present on one side only counts as a difference)."""
    if isinstance(old, dict) and isinstance(new, dict):
        out = set()
        for key in sorted(set(old) | set(new)):
            if key not in old or key not in new:
                out.add(collapse((*path, key)))
            else:
                out |= changed_fields(old[key], new[key], (*path, key))
        return out
    return {collapse(path)} if old != new else set()


def outside(changed: set[str], listed) -> set[str]:
    return set(changed) - set(listed)


def assert_only_listed(host: str, changed: set[str], listed) -> None:
    left = outside(changed, listed)
    assert not left, f"{host}: fields outside the list: {sorted(left)}"


@pytest.fixture(scope="module")
def pair(tmp_path_factory):
    """``{old, new}``: the world built in the build frame (frame_axis on every host) and in the voted frame (no override), each with its directory,
    its default-export records by id and its default-export header."""
    out = {}
    for name, overrides in (("old", E.old_frame_overrides()), ("new", E.overrides())):
        directory, _excluded, _cat, root = W.build(tmp_path_factory.mktemp(f"e3_frame_{name}"), E.frame_world(), overrides=overrides)
        snap = export_mod.export_snapshot(
            directory, game="ref", pack_ids=None, ids=None, roles={"whole"}, engines={"godot"}, frame="item", profile="private",
            pack_meta={p["pack"]: p for p in directory["packs"]}, rules_digest=directory["rules_digest"],
            overrides_digest=directory["overrides_digest"], attachments=False)
        out[name] = {"directory": directory, "root": root, "header": snap["generated_from"], "by_id": {w["id"]: w for w in snap["weapons"]}}
    return out


def record(pair, side: str, host: str) -> dict:
    return pair[side]["by_id"][E.pid(host)]


def changed(pair, host: str) -> set[str]:
    return changed_fields(record(pair, "old", host), record(pair, "new", host))


# --- the old side is the build frame ----------------------------------------------------------------------------------------------------


def test_the_old_side_is_the_build_frame_and_the_new_side_the_voted_frame(pair):
    old_a, new_a = record(pair, "old", E.ALPHA), record(pair, "new", E.ALPHA)
    assert old_a["geometry"]["axes"] == {"forward": "-y", "up": "+z", "forward_source": "pivot", "up_source": "fixed"}
    assert (old_a["geometry"]["length_m"], old_a["hints"]["size_class"]) == (0.55, "medium")
    assert new_a["geometry"]["axes"] == {"forward": "+z", "up": "+y", "forward_source": "body", "up_source": "fixed"}
    assert (new_a["geometry"]["length_m"], new_a["hints"]["size_class"]) == (0.4, "small")
    old_b, new_b = record(pair, "old", E.BRAVO), record(pair, "new", E.BRAVO)
    assert old_b["geometry"]["axes"]["forward"] == "-y" and old_b["geometry"]["axes"]["forward_source"] == "section"
    assert (old_b["geometry"]["length_m"], old_b["hints"]["size_class"]) == (0.6, "medium")
    assert new_b["geometry"]["axes"] == {"forward": "+z", "up": "+y", "forward_source": "body", "up_source": "fixed"}
    assert (new_b["geometry"]["length_m"], new_b["hints"]["size_class"]) == (0.4, "small")
    old_d, new_d = record(pair, "old", E.DELTA), record(pair, "new", E.DELTA)
    assert old_d["geometry"]["axes"]["forward"] == "-y" and old_d["geometry"]["axes"]["forward_source"] == "pivot"
    assert (old_d["geometry"]["length_m"], new_d["geometry"]["length_m"]) == (0.38, 0.3) and new_d["geometry"]["axes"]["forward_source"] == "body"
    old_e, new_e = record(pair, "old", E.ECHO), record(pair, "new", E.ECHO)
    assert old_e["geometry"]["axes"]["forward"] == "-y" and old_e["geometry"]["axes"]["forward_source"] == "pivot"
    assert (old_e["geometry"]["length_m"], new_e["geometry"]["length_m"]) == (0.4, 0.18) and new_e["geometry"]["axes"]["forward_source"] == "body"


def test_the_old_side_equals_the_version_5_measure_apart_from_the_support_point(pair):
    """The frame_axis emulation is the version 5 path: the same GLB measured as a record that is not an eligible host (hold class none, no vote)
    has the same geometry in every key but the support block, which only a long gun carries."""
    rules = load_rules()
    for host, scale in ((E.ALPHA, 1.0), (E.BRAVO, 1.0), (E.DELTA, 1.0), (E.ECHO, 1.0)):
        glb = pair["old"]["root"] / "glb" / E.PACK / f"{host}.glb"
        v5 = geometry.measure_weapon_detail(glb, None, scale, "smg", "ranged", "whole", rules, hold_class="none", genre="modern", with_mounts=False,
                                            host_id=host, host_pack=E.PACK)["geometry"]
        old = next(w for w in pair["old"]["directory"]["weapons"] if w["id"] == E.pid(host))["geometry"]
        skip = {"support", "support_r_m", "support_source", "mounts"}
        assert {k: v for k, v in old.items() if k not in skip} == {k: v for k, v in v5.items() if k not in skip}, host


# --- the diff of a frame-changed host ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("host", CHANGED_HOSTS)
def test_frame_changed_host_differs_only_in_the_amended_list(pair, host):
    assert_only_listed(host, changed(pair, host), AMENDED_LIST)


def test_the_amended_additions_are_each_seen_on_a_frame_changed_host(pair):
    """The diff is a subset of the list, not equal to it: a host moves only the fields its geometry moves (ALPHA has no flags to clear, BRAVO's
    pivot fraction stays 0.5, no host has a tip or a grip that moves). Between them the hosts show every field E3.4 adds."""
    for host in CHANGED_HOSTS:
        assert {"geometry.bounds", "geometry.support"} <= changed(pair, host), host
    for host in (E.ALPHA, E.BRAVO):
        assert {"geometry.support_r_m", "hints.size_class"} <= changed(pair, host), host
    assert "flags" in changed(pair, E.BRAVO) and "flags" not in changed(pair, E.ALPHA)
    assert E3_4_ADDED <= changed(pair, E.ALPHA) | changed(pair, E.BRAVO)
    assert LENGTH_DERIVED <= changed(pair, E.ECHO)
    for host in CHANGED_HOSTS:  # and the fields of the old list that follow the frame
        assert {"geometry.axes", "geometry.item_basis", "geometry.length_m", "geometry.butt", "geometry.muzzle", "review.reasons"} <= changed(pair, host), host
    assert "geometry.pivot_frac" in changed(pair, E.ALPHA)


def test_a_changed_field_is_a_changed_value_not_a_changed_key(pair):
    """The two sides carry the same keys everywhere: the vote moves values, it adds and drops no field."""
    for host in CHANGED_HOSTS:
        old, new = record(pair, "old", host), record(pair, "new", host)
        assert set(old) == set(new) and set(old["geometry"]) == set(new["geometry"]) and set(old["hints"]) == set(new["hints"]), host


@pytest.mark.parametrize("host, left", [
    (E.ALPHA, {"geometry.bounds", "geometry.support", "geometry.support_r_m", "hints.size_class"}),
    (E.BRAVO, {"geometry.bounds", "geometry.support", "geometry.support_r_m", "hints.size_class", "flags"}),
    (E.DELTA, {"geometry.bounds", "geometry.support", "hints.inventory_cells"}),
    (E.ECHO, {"geometry.bounds", "geometry.support", "hints.size_class", "hints.inventory_cells", "hints.weight_class"}),
])
def test_the_old_list_fails_the_same_assertion(pair, host, left):
    """The negative control: section 3.3 as it stood. The same assertion, with the old list as its literal, names the fields the amendment adds."""
    assert outside(changed(pair, host), OLD_LIST) == left
    with pytest.raises(AssertionError, match="fields outside the list"):
        assert_only_listed(host, changed(pair, host), OLD_LIST)


@pytest.mark.parametrize("host, left", [
    (E.ALPHA, set()),
    (E.BRAVO, set()),
    (E.DELTA, {"hints.inventory_cells"}),
    (E.ECHO, {"hints.inventory_cells", "hints.weight_class"}),
])
def test_the_five_field_list_fails_on_the_hosts_that_move_cells_or_weight(pair, host, left):
    """The negative control of the cells and the weight class: the list with only the five fields of the first E3.4 text holds for the hosts whose
    length stays inside a cell step and a weight step (ALPHA, BRAVO) and fails for the Uzi-shaped host (cells) and the short one (cells and weight)."""
    assert outside(changed(pair, host), FIVE_FIELD_LIST) == left
    if left:
        with pytest.raises(AssertionError, match="fields outside the list"):
            assert_only_listed(host, changed(pair, host), FIVE_FIELD_LIST)
    else:
        assert_only_listed(host, changed(pair, host), FIVE_FIELD_LIST)


def test_an_amended_list_without_bounds_fails_the_diff(pair):
    short = AMENDED_LIST - {"geometry.bounds"}
    for host in CHANGED_HOSTS:
        assert outside(changed(pair, host), short) == {"geometry.bounds"}, host
        with pytest.raises(AssertionError, match=r"\['geometry.bounds'\]"):
            assert_only_listed(host, changed(pair, host), short)


@pytest.mark.parametrize("path, value", [
    (("hints", "quality_tier"), 9),
    (("hints", "ammo_family"), "other"),
    (("hints", "size_basis"), "raw"),
    (("geometry", "long_axis"), "z"),
    (("geometry", "grip_source"), "handle"),
    (("geometry", "triangles"), 1),
    (("asset_id",), "other"),
])
def test_a_vote_that_changes_a_non_listed_field_fails_the_guard(pair, path, value):
    """Break: a vote that moves a field outside the list. The voted record is edited in a copy (the code needs no change, and none is made)."""
    host = E.ALPHA
    voted = deepcopy(record(pair, "new", host))
    node = voted
    for key in path[:-1]:
        node = node[key]
    assert node[path[-1]] != value
    node[path[-1]] = value
    seen = changed_fields(record(pair, "old", host), voted)
    assert outside(seen, AMENDED_LIST) == {".".join(path[:2] if path[0] in NESTED else path[:1])}
    with pytest.raises(AssertionError, match="fields outside the list"):
        assert_only_listed(host, seen, AMENDED_LIST)


# --- forward_by_fallback ----------------------------------------------------------------------------------------------------------------


def test_pre_vote_forward_by_fallback_clears_when_a_ring_confirms_the_sign(pair):
    old, new = record(pair, "old", E.BRAVO), record(pair, "new", E.BRAVO)
    # the origin sits mid-range on y: no pivot, a section guess for the sign, flagged for review
    assert old["flags"] == ["forward_by_fallback"] and old["geometry"]["axes"]["forward_source"] == "section"
    # the ring at +z gives the sign: measured, not a guess
    assert new["flags"] == [] and new["geometry"]["axes"]["forward_source"] == "body"
    assert changed(pair, E.BRAVO) >= {"flags"}


def test_a_host_with_no_pre_vote_flag_has_none_after_the_vote(pair):
    assert record(pair, "old", E.ALPHA)["flags"] == [] and record(pair, "new", E.ALPHA)["flags"] == []


# --- a host with no frame change --------------------------------------------------------------------------------------------------------


def test_host_without_a_frame_change_differs_in_no_field(pair):
    old, new = record(pair, "old", E.CHARLIE), record(pair, "new", E.CHARLIE)
    assert changed(pair, E.CHARLIE) == set() and old == new
    assert new["geometry"]["axes"]["forward_source"] == "pivot"  # the build frame on both sides
    assert pair["old"]["by_id"].keys() == pair["new"]["by_id"].keys()


def test_the_two_builds_differ_in_the_overrides_digest_alone(pair):
    """The old side is the new side plus a frame_axis entry: the header of the default export carries that entry's digest and nothing else moves."""
    differing = {k for k in pair["new"]["header"] if pair["old"]["header"][k] != pair["new"]["header"][k]}
    assert differing == {"overrides_digest"}


# --- inventory cells and weight class ---------------------------------------------------------------------------------------------------

# host -> (length_m before the vote, length_m after, size class before, after): worked out by hand from the fixture dimensions
LENGTHS = {
    E.ALPHA: (0.55, 0.4, "medium", "small"),
    E.BRAVO: (0.6, 0.4, "medium", "small"),
    E.DELTA: (0.38, 0.3, "small", "small"),
    E.ECHO: (0.4, 0.18, "small", "tiny"),
    E.CHARLIE: (0.85, 0.85, "medium", "medium"),
}
LATERAL_CELLS = 2  # every host is 0.12 m or more across its second axis: two cells high
WEIGHTS = ["light", "medium", "heavy"]  # the weight class of an SMG or a rifle is "medium"; a tiny size is one step lighter, a huge one heavier


def cells_of(length_m: float) -> int:
    """One cell of length per 0.30 m, rounded up, at least one (the rule, written out in tenths of a millimetre)."""
    return max(-(-round(length_m * 10000) // 3000), 1)


def weight_of(size_class: str) -> str:
    return WEIGHTS[1 + {"tiny": -1, "huge": 1}.get(size_class, 0)]


@pytest.mark.parametrize("host", list(LENGTHS))
def test_cells_and_weight_class_follow_the_length_and_move_only_when_it_crosses_a_step(pair, host):
    """``inventory_cells`` and ``weight_class`` are derived from ``length_m`` (the weight class through the size class): they move with the vote when
    the length crosses a cell step (0.30 m) or a size-class cut into or out of tiny or huge, and only then. DELTA crosses a cell step and no cut,
    ALPHA and BRAVO cross a cut (medium to small) and no step that matters, ECHO crosses a cell step and the cut to tiny, CHARLIE crosses nothing."""
    old_len, new_len, old_size, new_size = LENGTHS[host]
    old, new = record(pair, "old", host), record(pair, "new", host)
    assert (old["geometry"]["length_m"], new["geometry"]["length_m"]) == (old_len, new_len)
    assert (old["hints"]["size_class"], new["hints"]["size_class"]) == (old_size, new_size)
    for rec, length, size in ((old, old_len, old_size), (new, new_len, new_size)):
        assert rec["hints"]["inventory_cells"] == [cells_of(length), LATERAL_CELLS], (host, length)
        assert rec["hints"]["weight_class"] == weight_of(size), (host, size)
    moved = changed(pair, host)
    assert ("hints.inventory_cells" in moved) == (cells_of(old_len) != cells_of(new_len)), host
    assert ("hints.weight_class" in moved) == (weight_of(old_size) != weight_of(new_size)), host


def test_the_cells_and_weight_moves_of_the_fixture_world_are_these_and_no_others(pair):
    moved = {host: sorted(changed(pair, host) & LENGTH_DERIVED) for host in LENGTHS}
    assert moved == {
        E.ALPHA: [], E.BRAVO: [], E.CHARLIE: [],
        E.DELTA: ["hints.inventory_cells"],  # [2, 2] to [1, 2]: the AC147 Uzi-shaped host (0.38 m to 0.30 m)
        E.ECHO: ["hints.inventory_cells", "hints.weight_class"],  # [2, 2] to [1, 2], medium to light
    }
    assert record(pair, "old", E.DELTA)["hints"]["inventory_cells"] == [2, 2] and record(pair, "new", E.DELTA)["hints"]["inventory_cells"] == [1, 2]
    assert record(pair, "old", E.ECHO)["hints"]["weight_class"] == "medium" and record(pair, "new", E.ECHO)["hints"]["weight_class"] == "light"


# --- the pre-vote side without an override: the vote switched off -------------------------------------------------------------------------


def vote_off(real_vote):
    """A ``frame_vote`` that reads the build frame as usual and never changes it: the pre-vote record of ANY eligible host, with no per-host override.
    The live count needs it, because the live library's hosts cannot all be given a ``frame_axis`` before the build says what their axis is."""
    def off(verts, body_verts, build_forward, frame_axis=None):
        return dataclasses.replace(real_vote(verts, body_verts, build_forward, None), changed=False, conflict=False)
    return off


def test_a_switched_off_vote_gives_the_same_records_as_frame_axis_on_the_build_axis(tmp_path, pair, monkeypatch):
    """The two ways to a pre-vote side agree on the synthetic world, so the live count (which can only use the switched-off vote) measures the same
    old frame as the fixtures above."""
    monkeypatch.setattr(geometry, "frame_vote", vote_off(geometry.frame_vote))
    off, _excluded, _cat, _root = W.build(tmp_path, E.frame_world(), overrides=E.overrides())
    monkeypatch.undo()
    assert off["weapons"] == pair["old"]["directory"]["weapons"]
    assert off["weapons"] != pair["new"]["directory"]["weapons"]


@pytest.mark.live
def test_no_live_host_moves_its_inventory_cells_or_weight_class_with_the_vote(tmp_path, monkeypatch):
    """The live library, built twice on a COPY of the catalogs with empty caches (never the shared ones, never their caches): once with the vote
    switched off (the pre-vote frame), once as shipped. The frame-changed hosts are the 3 of spec 3.3; none of them moves its cells or its weight class."""
    try:
        cfg = load_config(require=False)
    except ConfigError:
        pytest.skip("no config on this machine")
    catalogs, glbs = cfg.get("catalogs"), cfg.get("threejs_v2")
    if catalogs is None or not catalogs.is_dir() or glbs is None or not glbs.is_dir():
        pytest.skip("no real catalogs or glb tree configured on this machine")
    copy = tmp_path / "catalogs"
    copy.mkdir()
    for path in catalogs.glob("*.json"):  # the pack catalogs only: the weapons caches stay behind, so every build starts empty
        shutil.copyfile(path, copy / path.name)
    committed = Path(geometry.__file__).resolve().parent.parent / "data" / "weapon_overrides.json"  # by path: conftest points the default at an empty file
    rules, overrides = load_rules(), load_overrides(committed)

    def build():
        directory, _excluded, _report = build_directory_report(
            copy, rules=rules, overrides=overrides, measure=True, threejs_v2_dir=glbs, geometry_cache={}, fit_cache={},
            extracted_root=cfg.get("extracted_root"))
        return {w["id"]: w for w in directory["weapons"]}

    real_vote = geometry.frame_vote
    monkeypatch.setattr(geometry, "frame_vote", vote_off(real_vote))
    pre = build()
    monkeypatch.setattr(geometry, "frame_vote", real_vote)
    post = build()
    assert pre.keys() == post.keys() and len(post) > 100
    frame_changed = [i for i, w in post.items() if (w["geometry"] or {}).get("axes") != (pre[i]["geometry"] or {}).get("axes")]
    assert len(frame_changed) == 3, frame_changed  # the switched-off vote really is the old frame, and 3 hosts differ
    moved = [i for i, w in post.items()
             if (w["hints"]["inventory_cells"], w["hints"]["weight_class"]) != (pre[i]["hints"]["inventory_cells"], pre[i]["hints"]["weight_class"])]
    assert len(moved) == 0, moved
