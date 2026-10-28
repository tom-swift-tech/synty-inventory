"""E3.4: guard tests for the frame-derived fields of the feature frame (docs/weapon_attach_geometry.md 3.3 "Scope of the feature frame", AC146, AC147;
errata E3.4). Test-only: the code needs no change, the spec's list of fields a frame vote may move was short.

The synthetic hosts are in ``fixtures/weapons/e3_frame_fields_world.py``: two SMG-shaped hosts whose magazine is longer than the body (so the
bounding box says y, the body z, and a 15 mm ring at the +z end confirms the vote), one of them with a pre-vote ``forward_by_fallback``, and a plain
rifle with no frame change. The "old frame" side of each pair is the same world built with ``frame_axis`` set to the build axis, which keeps the
build frame (the version 5 record); the "new frame" side has no override. The default export (``export`` defaults: private profile, item frame, no
``--attachments``) of the two is diffed field by field.

Every list and number below is a LITERAL, written out here: the old list is the section 3.3 text of commit 41ca096 (before E3.4), the amended list is
the text of f723f5c. None is read from the code under test.

Deliberate breaks, and the tests that fail on each:

* the old list used for the same assertion (the negative control): ``test_the_old_list_fails_the_same_assertion`` names what falls outside it;
* a list without ``geometry.bounds``: ``test_an_amended_list_without_bounds_fails_the_diff``;
* a vote that changes a field outside the list: ``test_a_vote_that_changes_a_non_listed_field_fails_the_guard``.
"""

from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

_FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("e3_frame_fields_world", _FIX / "e3_frame_fields_world.py")
E = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(E)

from synty_inventory.weapons import export as export_mod  # noqa: E402
from synty_inventory.weapons import geometry  # noqa: E402
from synty_inventory.weapons.rules import load_rules  # noqa: E402

W = E.W

# the fields a frame vote may move, one entry per field of the spec's list (a changed leaf collapses to its entry: geometry.bounds.size -> geometry.bounds)
OLD_LIST = frozenset({  # section 3.3 before E3.4 (41ca096): axes, item_basis, "length_m, tip, butt, grip and pivot points, and geometry.muzzle", review reasons
    "geometry.axes", "geometry.item_basis", "geometry.length_m", "geometry.tip", "geometry.butt", "geometry.grip", "geometry.pivot_frac",
    "geometry.muzzle", "review.reasons"})
E3_4_ADDED = frozenset({"geometry.bounds", "geometry.support", "geometry.support_r_m", "hints.size_class", "flags"})
AMENDED_LIST = OLD_LIST | E3_4_ADDED  # section 3.3 after E3.4 (f723f5c)

CHANGED_HOSTS = (E.ALPHA, E.BRAVO)
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


def test_the_old_side_equals_the_version_5_measure_apart_from_the_support_point(pair):
    """The frame_axis emulation is the version 5 path: the same GLB measured as a record that is not an eligible host (hold class none, no vote)
    has the same geometry in every key but the support block, which only a long gun carries."""
    rules = load_rules()
    for host, scale in ((E.ALPHA, 1.0), (E.BRAVO, 1.0)):
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
    """The diff is a subset of the list, not equal to it: a host moves only the fields its geometry moves (ALPHA keeps its flags and its pivot
    fraction at 0.5 on BRAVO, neither has a tip or a grip that moves). Between them the two hosts show every field E3.4 adds."""
    for host in CHANGED_HOSTS:
        assert {"geometry.bounds", "geometry.support", "geometry.support_r_m", "hints.size_class"} <= changed(pair, host), host
    assert "flags" in changed(pair, E.BRAVO) and "flags" not in changed(pair, E.ALPHA)
    assert E3_4_ADDED <= changed(pair, E.ALPHA) | changed(pair, E.BRAVO)
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
])
def test_the_old_list_fails_the_same_assertion(pair, host, left):
    """The negative control: section 3.3 as it stood. The same assertion, with the old list as its literal, names the fields the amendment adds."""
    assert outside(changed(pair, host), OLD_LIST) == left
    with pytest.raises(AssertionError, match="fields outside the list"):
        assert_only_listed(host, changed(pair, host), OLD_LIST)


def test_an_amended_list_without_bounds_fails_the_diff(pair):
    short = AMENDED_LIST - {"geometry.bounds"}
    for host in CHANGED_HOSTS:
        assert outside(changed(pair, host), short) == {"geometry.bounds"}, host
        with pytest.raises(AssertionError, match=r"\['geometry.bounds'\]"):
            assert_only_listed(host, changed(pair, host), short)


@pytest.mark.parametrize("path, value", [
    (("hints", "inventory_cells"), [9, 9]),
    (("hints", "weight_class"), "large"),
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


@pytest.mark.parametrize("host", [E.ALPHA, E.BRAVO, E.CHARLIE])
def test_inventory_cells_and_weight_class_do_not_move(pair, host):
    """By construction of the fixtures (the spec's "do not move" was measured on the live hosts, it is not a rule of the code): the length moves
    from 0.55 / 0.60 m to 0.40 m, which crosses a size-class cut (0.45 m) but not a cell step (one cell per 0.30 m, rounded up: 2 cells either side)."""
    old, new = record(pair, "old", host)["hints"], record(pair, "new", host)["hints"]
    assert old["inventory_cells"] == new["inventory_cells"] == ([3, 2] if host == E.CHARLIE else [2, 2])
    assert old["weight_class"] == new["weight_class"] == "medium"
    assert "hints.inventory_cells" not in changed(pair, host) and "hints.weight_class" not in changed(pair, host)
