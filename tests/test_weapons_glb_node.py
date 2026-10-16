"""Weapon directory W2: glb_node scoping and node_offset (AC34). One synthetic GLB holds three nodes.

shared.glb (tests/fixtures/weapons/make_glbs.py): Bow_A at the origin; Bow_B, an empty parent at (2.0, 0.3, 0.5)
with two limb children; Quiver_B at (2.5, 0, 0.5) rotated 90 degrees about Z. The expected bounds below were worked
out by hand from those stations and are literals.

Export is not built yet (there is no module that writes an item-frame file), so the item-frame vs asset-frame
identity of AC34 is asserted at the measure_weapon level: ``node_offset`` is the node's world translation in GLB
scene space and does not depend on ``item_basis``. When export lands, its test must assert the same on the file.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from synty_inventory.weapons.geometry import measure_weapon, measure_weapon_detail
from synty_inventory.weapons.rules import load_rules

_FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("make_glbs", _FIX / "make_glbs.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)

TOL = 0.0002
BOW_B = {"min": [1.99, -0.5, 0.49], "max": [2.16, 1.1, 0.51]}
UNION = {"min": [1.99, -0.5, 0.45], "max": [2.5, 1.1, 0.55]}


@pytest.fixture(scope="module")
def rules():
    return load_rules()


@pytest.fixture(scope="module")
def shared(tmp_path_factory):
    return M.generate_all(tmp_path_factory.mktemp("glbnode"))["shared"]


def geo(path, node, rules, scale=1.0, archetype="bow", kind="ranged"):
    return measure_weapon(path, node, scale, archetype, kind, "whole", rules, genre="fantasy")


def near(got, want):
    return len(got) == len(want) and all(abs(a - b) <= TOL for a, b in zip(got, want))


def test_ac34_a_single_named_node_measures_only_itself(shared, rules):
    g = geo(shared, "Bow_B", rules)
    assert near(g["bounds"]["min"], BOW_B["min"]) and near(g["bounds"]["max"], BOW_B["max"])
    assert near(g["bounds"]["size"], [0.17, 1.6, 0.02])
    assert g["length_m"] == 1.6


def test_ac34_the_result_does_not_depend_on_the_other_nodes_in_the_file(shared, rules, tmp_path):
    only = M.write_glb(tmp_path / "only_b.glb", [r for r in M.shared_roots() if r["name"] == "Bow_B"])
    assert geo(shared, "Bow_B", rules) == geo(only, "Bow_B", rules)
    swapped = M.write_glb(tmp_path / "reordered.glb", list(reversed(M.shared_roots())))
    assert geo(swapped, "Bow_B", rules) == geo(shared, "Bow_B", rules)


def test_ac34_a_list_measures_the_union_of_its_nodes(shared, rules):
    g = geo(shared, ["Bow_B", "Quiver_B"], rules)
    assert near(g["bounds"]["min"], UNION["min"]) and near(g["bounds"]["max"], UNION["max"])
    assert g["node_offset"] is None


def test_ac34_a_null_node_on_the_multi_node_file_is_the_whole_file_aabb(shared, rules):
    g = geo(shared, None, rules)
    lo, hi = g["bounds"]["min"], g["bounds"]["max"]
    assert lo[0] < 1.0 and hi[0] >= 2.5 and hi[1] >= 1.1  # Bow_A at the origin plus the far nodes
    assert g["node_offset"] is None
    single = M.write_glb(shared.parent / "single_bow.glb", [{"name": "Bow", "mesh": M.bow()}])
    one = geo(single, None, rules)
    named = geo(single, "Bow", rules)
    assert one["bounds"] == named["bounds"]


def test_ac34_node_offset_is_the_single_nodes_world_translation(shared, rules):
    assert geo(shared, "Bow_B", rules)["node_offset"] == [2.0, 0.3, 0.5]
    assert geo(shared, "Quiver_B", rules)["node_offset"] == [2.5, 0.0, 0.5]
    assert geo(shared, "Bow_A", rules)["node_offset"] == [0.0, 0.0, 0.0]
    assert geo(shared, "Bow_B", rules, scale=2.0)["node_offset"] == [4.0, 0.6, 1.0]  # scaled like the points


def test_ac34_node_offset_is_in_asset_frame_and_never_rotated_by_item_basis(shared, rules):
    g = geo(shared, "Bow_B", rules)
    assert g["item_basis"] == [[0, 0, -1], [0, 1, 0], [1, 0, 0]]  # not the identity, so a rotation would show
    assert g["frame"] == "asset"
    assert g["node_offset"] == [2.0, 0.3, 0.5]
    rotated = [sum(g["item_basis"][r][c] * g["node_offset"][c] for c in range(3)) for r in range(3)]
    assert rotated == [-0.5, 0.3, 2.0] and g["node_offset"] != rotated
    # the same offset whatever the archetype's expected axes (it is a property of the node, not of the basis)
    assert geo(shared, "Bow_B", rules, archetype="crossbow")["node_offset"] == [2.0, 0.3, 0.5]
    # and consuming it: bounds minus node_offset is the weapon in its own node frame, independent of the basis
    local_min = [a - b for a, b in zip(g["bounds"]["min"], g["node_offset"])]
    assert near(local_min, [-0.01, -0.8, -0.01])


def test_ac34_a_rotated_node_is_flagged_for_review_and_a_plain_one_is_not(shared, rules):
    d = measure_weapon_detail(shared, "Quiver_B", 1.0, "bow", "ranged", "whole", rules, genre="fantasy")
    assert "node_transform" in d["reasons"] and d["geometry"] is not None
    d = measure_weapon_detail(shared, ["Bow_B", "Quiver_B"], 1.0, "bow", "ranged", "whole", rules, genre="fantasy")
    assert "node_transform" in d["reasons"]
    for node in ("Bow_B", "Bow_A", None):
        d = measure_weapon_detail(shared, node, 1.0, "bow", "ranged", "whole", rules, genre="fantasy")
        assert "node_transform" not in d["reasons"], node


def test_ac34_a_node_that_is_not_in_the_file_is_a_failure_with_a_warning(shared, rules):
    d = measure_weapon_detail(shared, "Bow_Z", 1.0, "bow", "ranged", "whole", rules, genre="fantasy")
    assert d["geometry"] is None and d["reasons"] == ["no_geometry"]
    assert "Bow_Z" in d["warning"]
