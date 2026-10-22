"""Weapon directory W7 slice 1: the head sign decides over a pivot-decided sign (R-H1) and for head-lead tools (R-H2)
(docs/weapon_directory.md 3.5.2 PATCH W7; AC43, AC54, AC55).

Everything is synthetic. Bounds are literals: the 15 % margin and the archetype lists are not imported from the code under
test, and every rule has a mutation proof that stays in the suite (the rule is switched off in the test and the headed
case must change).

Shape: a y-long staff, 2.0 m, a 10 cm square butt cap y 0..0.2, a 3 cm shaft, and a head y 1.8..2.0 of the given width.
The outer 25 % windows (0.5 m) therefore compare 0.10 (butt) with the head width. ``origin_y`` is where the origin sits
along +y from the butt: 2.0 = at the head (the pivot rule says forward is -y, away from the origin), 0.0 = at the butt
(forward +y, toward the head, the pivot and the head agree).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_FIX = Path(__file__).parent / "fixtures" / "weapons"


def _load(name: str, sub: str = ""):
    spec = importlib.util.spec_from_file_location(name, _FIX / sub / f"{name}.py" if sub else _FIX / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load("make_glbs")
wfx = _load("wfx")

import synty_inventory.weapons as pkg  # noqa: E402
from synty_inventory.weapons import geometry as G  # noqa: E402
from synty_inventory.weapons.directory import build_directory_report  # noqa: E402
from synty_inventory.weapons.geometry import measure_cached, measure_weapon_detail  # noqa: E402
from synty_inventory.weapons.rules import load_rules  # noqa: E402

HEADED = ("axe", "mace", "hammer", "polearm", "staff")
NOT_HEADED = ("club", "sword", "knife", "spear")


def head_staff(head_half=0.06):
    """Butt cap half width 0.05 (extent 0.10); head half width ``head_half`` (extent 2 * head_half)."""
    return M.merge(M.bar(0.0, 0.2, 0.05, 0.05), M.bar(0.2, 1.8, 0.015, 0.015), M.bar(1.8, 2.0, head_half, head_half))


def mirrored(mesh):
    v, t = mesh
    v = v.copy()
    v[:, 1] = 2.0 - v[:, 1]
    return v, t[:, ::-1]


@pytest.fixture(scope="module")
def rules():
    return load_rules()


def measure(tmp_path, rules, mesh, archetype, origin_y, kind="melee", **kw):
    path = M.write_glb(tmp_path / "m.glb", [{"name": "m", "mesh": M.shifted(mesh, (0.0, -origin_y, 0.0))}])
    return measure_weapon_detail(path, None, 1.0, archetype, kind, "whole", rules, genre="fantasy", **kw)


def axes(d):
    return d["geometry"]["axes"]["forward"], d["geometry"]["axes"]["forward_source"]


# --- AC43 ---------------------------------------------------------------------------------------------------------------


def test_ac43_the_geometry_version_is_the_plain_integer_5():
    assert pkg.WEAPON_GEOMETRY_VERSION == 5 and isinstance(pkg.WEAPON_GEOMETRY_VERSION, int)


# --- AC54: R-H1 ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("archetype", HEADED)
def test_ac54_a_headed_archetype_with_its_origin_at_the_head_points_at_the_head(tmp_path, rules, archetype):
    d = measure(tmp_path, rules, head_staff(), archetype, 2.0)
    assert axes(d) == ("+y", "head")
    assert "forward_by_fallback" not in d["flags"]  # a measured rule, not a guess
    g = d["geometry"]
    assert g["item_basis"][2] == [0, 1, 0]  # every sign-derived value follows the head sign
    assert g["tip"] == [0.0, 0.0, 0.0] and g["butt"] == [0.0, -2.0, 0.0]  # the head end is the tip, the origin sits on it


@pytest.mark.parametrize("archetype", HEADED)
def test_ac54_the_sign_follows_the_head_not_a_fixed_side(tmp_path, rules, archetype):
    """The mirror image: the head at the -y end and the origin on it. The pivot says +y (away from the origin)."""
    d = measure(tmp_path, rules, mirrored(head_staff()), archetype, 0.0)
    assert axes(d) == ("-y", "head")
    assert "forward_by_fallback" not in d["flags"]


@pytest.mark.parametrize("archetype", HEADED)
def test_ac54_when_the_pivot_and_the_head_agree_the_source_stays_pivot(tmp_path, rules, archetype):
    d = measure(tmp_path, rules, head_staff(), archetype, 0.0)
    assert axes(d) == ("+y", "pivot")
    assert "forward_by_fallback" not in d["flags"]


@pytest.mark.parametrize("archetype", HEADED)
def test_ac54_below_the_15_percent_margin_the_pivot_sign_and_source_stay(tmp_path, rules, archetype):
    d = measure(tmp_path, rules, head_staff(0.0565), archetype, 2.0)  # 11.3 cm head vs 10.0 cm butt: ratio 1.13
    assert axes(d) == ("-y", "pivot")
    assert "forward_by_fallback" not in d["flags"]


def test_ac54_above_the_15_percent_margin_the_head_decides(tmp_path, rules):
    d = measure(tmp_path, rules, head_staff(0.0585), "axe", 2.0)  # 11.7 cm head vs 10.0 cm butt: ratio 1.17
    assert axes(d) == ("+y", "head")


@pytest.mark.parametrize("archetype", NOT_HEADED)
def test_ac54_club_sword_knife_spear_keep_the_pivot_sign(tmp_path, rules, archetype):
    d = measure(tmp_path, rules, head_staff(), archetype, 2.0)
    assert axes(d) == ("-y", "pivot")


def test_ac54_a_tool_without_a_head_lead_token_keeps_the_pivot_sign(tmp_path, rules):
    assert axes(measure(tmp_path, rules, head_staff(), "tool", 2.0)) == ("-y", "pivot")
    assert axes(measure(tmp_path, rules, head_staff(), "tool", 2.0, head_lead=False)) == ("-y", "pivot")


def test_ac54_head_over_pivot_applies_to_melee_only(tmp_path, rules):
    """A ranged item is never reached by the head rule, whatever its archetype name says."""
    d = measure(tmp_path, rules, head_staff(), "axe", 2.0, kind="ranged")
    assert axes(d)[1] != "head"


@pytest.mark.parametrize("override,expected", [("-y", "-y"), ("+y", "+y")])
def test_ac54_a_forward_override_still_wins(tmp_path, rules, override, expected):
    d = measure(tmp_path, rules, head_staff(), "staff", 2.0, forward_override=override)
    assert axes(d) == (expected, "override")
    assert "forward_by_fallback" not in d["flags"]


@pytest.mark.parametrize("archetype", HEADED)
def test_ac54_mutation_without_the_archetype_in_the_table_the_headed_case_changes(tmp_path, rules, monkeypatch, archetype):
    assert axes(measure(tmp_path, rules, head_staff(), archetype, 2.0)) == ("+y", "head")
    monkeypatch.setattr(G, "_HEAD_PIVOT", tuple(a for a in G._HEAD_PIVOT if a != archetype))
    assert axes(measure(tmp_path, rules, head_staff(), archetype, 2.0)) == ("-y", "pivot")


def test_ac54_mutation_with_the_rule_removed_no_headed_case_survives(tmp_path, rules, monkeypatch):
    monkeypatch.setattr(G, "_HEAD_PIVOT", ())
    for archetype in HEADED:
        assert axes(measure(tmp_path, rules, head_staff(), archetype, 2.0)) == ("-y", "pivot")


# --- AC55: R-H2 ---------------------------------------------------------------------------------------------------------


def test_ac55_a_head_lead_tool_follows_its_head(tmp_path, rules):
    d = measure(tmp_path, rules, head_staff(), "tool", 2.0, head_lead=True)
    assert axes(d) == ("+y", "head") and "forward_by_fallback" not in d["flags"]


def test_ac55_a_head_lead_tool_whose_pivot_agrees_stays_pivot(tmp_path, rules):
    assert axes(measure(tmp_path, rules, head_staff(), "tool", 0.0, head_lead=True)) == ("+y", "pivot")


def test_ac55_a_head_lead_tool_below_the_margin_keeps_the_pivot(tmp_path, rules):
    assert axes(measure(tmp_path, rules, head_staff(0.0565), "tool", 2.0, head_lead=True)) == ("-y", "pivot")


def test_ac55_the_flag_alone_does_not_extend_to_other_pointed_archetypes(tmp_path, rules):
    for archetype in NOT_HEADED:
        assert axes(measure(tmp_path, rules, head_staff(), archetype, 2.0, head_lead=True)) == ("-y", "pivot")


def test_ac55_the_fingerprint_of_an_unrelated_record_is_unchanged_and_head_lead_adds_to_it(rules):
    args = ("sword", "melee", "whole", "melee_one", "fantasy", rules)
    assert G._inputs_fingerprint(*args) == "02018a9e0640406c"  # the value before W7: pinned
    assert G._inputs_fingerprint(*args, head_lead=False) == "02018a9e0640406c"
    assert G._inputs_fingerprint(*args, head_lead=True) != "02018a9e0640406c"
    assert G._inputs_fingerprint(*args, "+y") == "503a811f21093e35"  # an override keeps its own key


def test_ac55_a_cached_result_is_never_served_across_head_lead(tmp_path, rules):
    M.write_glb(tmp_path / "spade.glb", [{"name": "s", "mesh": M.shifted(head_staff(), (0.0, -2.0, 0.0))}])
    args = (tmp_path, "spade.glb", None, 1.0, "tool", "melee", "whole", rules)
    cache: dict = {}
    plain, was = measure_cached(*args, cache, genre="fantasy")
    assert was is False and axes(plain) == ("-y", "pivot")
    led, was = measure_cached(*args, cache, genre="fantasy", head_lead=True)
    assert was is False and axes(led) == ("+y", "head")  # not the plain entry
    assert len(cache["spade.glb"]["by_inputs"]) == 2
    again, was = measure_cached(*args, cache, genre="fantasy", head_lead=True)
    assert was is True and axes(again) == ("+y", "head")
    back, was = measure_cached(*args, cache, genre="fantasy", head_lead=False)
    assert was is True and axes(back) == ("-y", "pivot")  # and the other way round


# --- AC55 end to end: directory.py derives head_lead from the id's tokens and the rules table --------------------------

TOOLS = {  # catalog asset id -> expected forward when the table holds the token (head) / does not (pivot)
    "SM_Wep_Spade_01": "spade", "SM_Wep_Shovel_01": "shovel", "SM_Wep_Pitchfork_01": "pitchfork",
    "SM_Wep_Wrench_01": None, "SM_Wep_Chainsaw_01": None, "SM_Wep_Pickaxe_01": None,
}


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("w7geo")
    cat = tmp / "catalogs"
    cat.mkdir()
    template = json.loads((wfx.CATALOGS / "FAKE_Modern.json").read_text(encoding="utf-8"))
    base = next(a for a in template["assets"] if a["id"] == "SM_Wep_Pistol_01")
    root = tmp / "threejs"
    assets = []
    for aid in [*TOOLS, "SM_Wep_Axe_01", "SM_Wep_Club_01"]:
        a = json.loads(json.dumps(base))
        a["id"], a["name"] = aid, aid.replace("_", " ")
        a["files"]["glb"] = f"glb/FAKE_Modern/{aid}.glb"
        a["files"]["unity_prefab"], a["files"]["unity_mesh"] = f"Prefabs/{aid}.prefab", f"Meshes/{aid}.fbx"
        a["paths"] = {"materials": [], "mesh": a["files"]["unity_mesh"], "prefab": a["files"]["unity_prefab"]}
        assets.append(a)
        M.write_glb(root / a["files"]["glb"], [{"name": aid, "mesh": M.shifted(head_staff(), (0.0, -2.0, 0.0))}])
    doc = {**template, "assets": assets, "asset_count": len(assets)}
    (cat / "FAKE_Modern.json").write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
    return {"cat": cat, "root": root}


def build(world, rules, cache=None):
    return build_directory_report(world["cat"], rules=rules, overrides=wfx.overrides_doc(), measure=True,
                                  pack_settings=wfx.pack_settings(), threejs_v2_dir=world["root"],
                                  geometry_cache={} if cache is None else cache)


def forwards(directory):
    return {r["id"].split("/", 1)[1]: (r["archetype"], r["geometry"]["axes"]["forward"],
                                       r["geometry"]["axes"]["forward_source"]) for r in directory["weapons"]}


def test_ac54_ac55_end_to_end_only_the_listed_tools_and_the_headed_archetypes_follow_the_head(world, rules):
    directory, _, _ = build(world, rules)
    got = forwards(directory)
    for aid, token in TOOLS.items():
        assert got[aid] == ("tool", "+y" if token else "-y", "head" if token else "pivot"), aid
    assert got["SM_Wep_Axe_01"] == ("axe", "+y", "head")
    assert got["SM_Wep_Club_01"] == ("club", "-y", "pivot")
    assert all("forward_by_fallback" not in r["flags"] for r in directory["weapons"])


@pytest.mark.parametrize("token", ["spade", "shovel", "pitchfork"])
def test_ac55_mutation_removing_one_token_flips_exactly_its_tool_and_the_stale_result_is_not_served(world, rules, token):
    cache: dict = {}
    full, _, _rep_full = build(world, rules, cache)
    cut = json.loads(json.dumps(rules))
    cut["head_lead_tokens"].remove(token)
    after, _, rep_cut = build(world, cut, cache)  # the SAME cache: the fingerprint must tell the two apart
    a, b = forwards(full), forwards(after)
    changed = sorted(k for k in a if a[k] != b[k])
    assert changed == [f"SM_Wep_{token.capitalize()}_01"]
    assert b[changed[0]] == ("tool", "-y", "pivot") and a[changed[0]] == ("tool", "+y", "head")
    # only the record whose head_lead changed was measured again; every other entry was served from the shared cache
    assert rep_cut["geometry_stats"]["decoded"] == 1 and rep_cut["geometry_stats"]["cached"] >= 7


def test_ac55_mutation_with_the_table_removed_the_spade_case_fails(world, rules):
    gone = json.loads(json.dumps(rules))
    gone["head_lead_tokens"] = []
    directory, _, _ = build(world, gone)
    got = forwards(directory)
    assert got["SM_Wep_Spade_01"] == ("tool", "-y", "pivot")
    assert got["SM_Wep_Axe_01"] == ("axe", "+y", "head")  # R-H1 does not depend on the table
