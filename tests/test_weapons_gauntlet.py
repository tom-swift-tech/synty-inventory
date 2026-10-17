"""Weapon directory W5: the ``weapons_directory`` gauntlet gate (AC30) and its additivity (AC29).

The world is the committed fixture catalogs with a GLB only for the six measurable weapons (every other record has
``files.glb`` removed, so the 97 % geometry floor is meaningful on a small library) and a directory built from them.
Each check gets one case that breaks exactly it, edited into a copy of the written directory, plus the clean world
that passes every check. Expected counts and thresholds are literals.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

_FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("wfx", _FIX / "wfx.py")
wfx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wfx)
_spec = importlib.util.spec_from_file_location("make_glbs", _FIX / "make_glbs.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)

from synty_inventory import gauntlet  # noqa: E402
from synty_inventory.gauntlet import run_gauntlet  # noqa: E402
from synty_inventory.weapons import gate as G  # noqa: E402
from synty_inventory.weapons import overrides as O  # noqa: E402
from synty_inventory.weapons import to_text  # noqa: E402
from synty_inventory.weapons.directory import (  # noqa: E402
    DIRECTORY_NAME,
    EXCLUDED_NAME,
    build_directory_report,
    write_directory,
)

SIX = {  # record -> named fixture GLB (the same stand-ins the icon tests use)
    "FAKE_Modern/SM_Wep_Rifle_Assault_01": "gun",
    "FAKE_Fantasy/SM_Wep_Claymore_06": "sword",
    "FAKE_Fantasy/SM_Wep_Spear_01": "spear",
    "FAKE_Fantasy/SM_Wep_Axe_01": "axe",
    "FAKE_Fantasy/SM_Wep_Bow_03": "bow",
    "FAKE_Fantasy/SM_Wep_Shield_01": "shield",
}
RIFLE = "FAKE_Modern/SM_Wep_Rifle_Assault_01"
AXE = "FAKE_Fantasy/SM_Wep_Axe_01"
CHECKS = ["directory_current", "schema", "coverage", "ids_unique", "geometry", "muzzle", "overrides_current", "gold"]
GHOST = "FAKE_Fantasy/SM_Wep_Ghost_99"  # an id no catalog has


def make_world(tmp: Path, overrides: dict | None = None) -> dict:
    cat = wfx.make_catalogs_dir(tmp)
    root = tmp / "threejs"
    named = M.generate_all(tmp / "named")
    for path in sorted(cat.glob("FAKE_*.json")):
        if path.name.count(".") > 1:
            continue  # a sidecar such as FAKE_Modern.scene_grammar.json
        doc = json.loads(path.read_text(encoding="utf-8"))
        for asset in doc["assets"]:
            files = asset.setdefault("files", {})
            if f"{doc['pack_id']}/{asset['id']}" in SIX:
                dest = root / files["glb"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(named[SIX[f"{doc['pack_id']}/{asset['id']}"]].read_bytes())
            else:
                files["glb"] = None
        path.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    ov = overrides if overrides is not None else O.empty_overrides()
    directory, excluded, _ = build_directory_report(
        cat, overrides=ov, pack_settings=wfx.pack_settings(), threejs_v2_dir=root, geometry_cache={})
    write_directory(cat, directory, excluded)
    return {"cat": cat, "root": root, "overrides": ov, "dir": directory, "excl": excluded,
            "dpath": cat / "weapons" / DIRECTORY_NAME, "epath": cat / "weapons" / EXCLUDED_NAME}


@pytest.fixture(scope="module")
def pristine(tmp_path_factory):
    return make_world(tmp_path_factory.mktemp("gate"))


@pytest.fixture
def world(pristine, tmp_path):
    """A private copy of the pristine world per test, so one case's edits never leak into another."""
    cat = tmp_path / "catalogs"
    shutil.copytree(pristine["cat"], cat)
    return {**pristine, "cat": cat, "dpath": cat / "weapons" / DIRECTORY_NAME, "epath": cat / "weapons" / EXCLUDED_NAME,
            "dir": copy.deepcopy(pristine["dir"]), "excl": copy.deepcopy(pristine["excl"])}


def save(w: dict, directory: dict | None = None, excluded: dict | None = None) -> None:
    w["dpath"].write_bytes(to_text(directory if directory is not None else w["dir"]).encode("utf-8"))
    w["epath"].write_bytes(to_text(excluded if excluded is not None else w["excl"]).encode("utf-8"))


def gate(w: dict, **kw) -> dict:
    kw.setdefault("overrides", w["overrides"])
    return G.check_weapons_directory(w["cat"], **kw)


def by_check(result: dict) -> dict[str, dict]:
    return {c["check"]: c for c in result["checks"]}


def failing(result: dict) -> list[str]:
    return [c["check"] for c in result["checks"] if not c["ok"]]


def tree_hash(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def rec(directory: dict, rid: str) -> dict:
    return next(r for r in directory["weapons"] if r["id"] == rid)


# --- the clean world -------------------------------------------------------------------------------------------------


def test_the_world_is_the_shape_the_checks_need(world):
    assert len(world["dir"]["weapons"]) == 147 and len(world["excl"]["excluded"]) == 22
    measured = [r["id"] for r in world["dir"]["weapons"] if r["geometry"] is not None]
    assert sorted(measured) == sorted(SIX)
    assert [r["id"] for r in world["dir"]["weapons"] if r["files"].get("glb")] == sorted(SIX)  # the 97 % denominator
    assert rec(world["dir"], RIFLE)["geometry"]["muzzle"] is not None


def test_a_clean_directory_passes_every_check(world):
    r = gate(world)
    assert r["ok"] is True and r["skipped"] is False
    assert [c["check"] for c in r["checks"]] == CHECKS and failing(r) == []
    assert "6/6 records with a GLB are measured" in by_check(r)["geometry"]["detail"]
    assert "0 gold ids" in by_check(r)["gold"]["detail"]


def test_no_directory_skips_the_gate(tmp_path):
    cat = wfx.make_catalogs_dir(tmp_path)
    r = G.check_weapons_directory(cat)
    assert (r["ok"], r["skipped"], r["checks"]) == (True, True, []) and "skipped" in r["detail"]
    assert not (cat / "weapons").exists()  # looking never creates the sidecar folder


def test_the_gate_writes_nothing(world):
    before = tree_hash(world["cat"])
    gate(world)
    gate(world, strict=True)
    assert tree_hash(world["cat"]) == before


# --- one failing case per check --------------------------------------------------------------------------------------


def test_a_directory_built_with_other_inputs_is_not_current(world):
    world["dir"]["rules_digest"] = "0" * 16
    save(world)
    r = gate(world)
    assert r["ok"] is False and "directory_current" in failing(r)
    assert "run `weapons build`" in by_check(r)["directory_current"]["detail"]
    assert [c["check"] for c in r["checks"]][-1] == "schema"  # nothing is audited against inputs it was not built with


def test_a_bumped_weapon_version_makes_the_directory_stale(world, monkeypatch):
    from synty_inventory import weapons as pkg

    monkeypatch.setattr(pkg, "WEAPON_VERSION", pkg.WEAPON_VERSION + 1)
    r = gate(world)
    assert r["ok"] is False and failing(r) == ["directory_current"]


def test_an_invalid_enum_fails_the_schema_check(world):
    rec(world["dir"], AXE)["archetype"] = "banana"
    save(world)
    r = gate(world)
    assert r["ok"] is False and "schema" in failing(r)
    assert "archetype" in by_check(r)["schema"]["detail"]


def test_a_record_dropped_from_the_directory_fails_coverage_even_with_the_stored_counts_fixed(world):
    victim = "FAKE_Fantasy/SM_Wep_Mace_01"
    d = world["dir"]
    assert victim in {r["id"] for r in d["weapons"]}
    d["weapons"] = [r for r in d["weapons"] if r["id"] != victim]
    row = next(p for p in d["packs"] if p["pack"] == "FAKE_Fantasy")
    row["records"] -= 1
    row["candidates"] -= 1  # the stored row now agrees with the rows, so only the catalogs can tell
    save(world)
    r = gate(world)
    assert "coverage" in failing(r)
    assert "1 candidate(s) without a row" in by_check(r)["coverage"]["detail"] and victim in by_check(r)["coverage"]["detail"]


def test_a_stored_count_that_disagrees_with_the_rows_fails_coverage(world):
    next(p for p in world["dir"]["packs"] if p["pack"] == "FAKE_Fantasy")["candidates"] += 1
    save(world)
    r = gate(world)
    assert "coverage" in failing(r) and "FAKE_Fantasy: pack row says" in by_check(r)["coverage"]["detail"]


def test_a_row_that_no_candidate_explains_fails_coverage(world):
    world["excl"]["excluded"].append({"id": GHOST, "reason": "name_pattern", "matched": "x", "source": "catalog"})
    world["excl"]["excluded"].sort(key=lambda e: e["id"])
    row = next(p for p in world["dir"]["packs"] if p["pack"] == "FAKE_Fantasy")
    row["excluded"] += 1
    row["candidates"] += 1
    save(world)
    r = gate(world)
    assert "coverage" in failing(r) and "not candidates" in by_check(r)["coverage"]["detail"]


def test_a_duplicated_id_fails_ids_unique(world):
    world["dir"]["weapons"].append(copy.deepcopy(rec(world["dir"], AXE)))
    save(world)
    r = gate(world)
    assert "ids_unique" in failing(r) and AXE in by_check(r)["ids_unique"]["detail"]


def test_an_id_in_both_files_fails_ids_unique(world):
    victim = world["excl"]["excluded"][0]["id"]
    clone = copy.deepcopy(rec(world["dir"], AXE))
    clone["id"] = victim
    world["dir"]["weapons"].append(clone)
    save(world)
    r = gate(world)
    assert "ids_unique" in failing(r) and "in both" in by_check(r)["ids_unique"]["detail"]


def test_geometry_below_97_percent_of_glb_records_fails(world):
    # 5 of 6 measured is 83 %: below the 97 % floor. One record keeps its GLB path but loses its measurement.
    r5 = rec(world["dir"], AXE)
    r5["geometry"] = None
    r5["flags"] = sorted(set(r5["flags"]) | {"unmeasured"})
    r5["hints"].update(size_class=None, inventory_cells=None, size_basis=None)
    save(world)
    r = gate(world)
    assert "geometry" in failing(r)
    assert "5/6 records with a GLB are measured (83.3%, floor 97%)" in by_check(r)["geometry"]["detail"]


def test_a_ranged_record_without_a_muzzle_fails_muzzle(world):
    geo = rec(world["dir"], RIFLE)["geometry"]
    geo["muzzle"] = None
    geo["muzzle_source"] = None
    save(world)
    r = gate(world)
    assert "muzzle" in failing(r) and RIFLE in by_check(r)["muzzle"]["detail"]
    # a bow has no muzzle and must not be flagged
    assert rec(world["dir"], "FAKE_Fantasy/SM_Wep_Bow_03")["geometry"]["muzzle"] is None
    assert "SM_Wep_Bow_03" not in by_check(r)["muzzle"]["detail"]


def test_a_malformed_document_fails_instead_of_raising(world):
    del world["dir"]["weapons"][0]["geometry"]
    del world["dir"]["packs"]
    save(world)
    r = gate(world)
    assert r["ok"] is False and "schema" in failing(r)


# --- stale overrides: listed always, fail only with strict --------------------------------------------------------------


STALE = {"schema": "weapon-overrides/1", "ids": {GHOST: {"set": {"archetype": "sword"}}},
         "globs": {"FAKE_Nowhere/*": {"confirm": True}}}


@pytest.fixture
def stale_world(tmp_path):
    return make_world(tmp_path, overrides=STALE)


def test_a_stale_override_is_listed_and_passes_without_strict(stale_world):
    r = gate(stale_world)
    assert r["ok"] is True and failing(r) == []
    assert [s["key"] for s in r["stale_overrides"]] == [GHOST, "FAKE_Nowhere/*"]
    assert GHOST in r["detail"] and "listed only" in by_check(r)["overrides_current"]["detail"]


def test_a_stale_override_fails_with_strict(stale_world):
    r = gate(stale_world, strict=True)
    assert r["ok"] is False and failing(r) == ["overrides_current"] and r["strict"] is True
    assert "2 stale override(s)" in by_check(r)["overrides_current"]["detail"] and "(fails: strict)" in r["detail"]


def test_a_stale_id_is_not_a_gold_case(stale_world):
    assert "0 gold id(s)" in by_check(gate(stale_world))["gold"]["detail"]


# --- the gold regression -----------------------------------------------------------------------------------------------


GOLD = {"schema": "weapon-overrides/1",
        "ids": {AXE: {"set": {"archetype": "mace", "genre": "scifi"}}, "FAKE_Fantasy/SM_Wep_Mace_01": {"exclude": True}},
        "globs": {}}


def test_gold_ids_classify_to_their_overridden_values_after_a_clean_rebuild(tmp_path):
    w = make_world(tmp_path, overrides=GOLD)
    assert rec(w["dir"], AXE)["archetype"] == "mace" and rec(w["dir"], AXE)["genre"] == "scifi"
    r = gate(w)
    assert r["ok"] is True, r["detail"]
    assert "2 gold id(s) classify to their overridden values" in by_check(r)["gold"]["detail"]


def test_a_classifier_that_ignores_an_override_fails_the_gold_check(tmp_path, monkeypatch):
    w = make_world(tmp_path, overrides=GOLD)
    real = G.build_directory_report

    def regressed(*a, **kw):  # a classifier that stopped honouring the override
        d, e, rep = real(*a, **kw)
        rec(d, AXE)["archetype"] = "axe"
        return d, e, rep

    monkeypatch.setattr(G, "build_directory_report", regressed)
    r = gate(w)
    assert r["ok"] is False and failing(r) == ["gold"]
    assert f"{AXE}: archetype is 'axe', the override says 'mace'" in by_check(r)["gold"]["detail"]
    assert "1 of 2 gold id(s) differ" in by_check(r)["gold"]["detail"]


def test_an_exclude_that_the_rebuild_does_not_honour_fails_the_gold_check(tmp_path, monkeypatch):
    w = make_world(tmp_path, overrides=GOLD)
    real = G.build_directory_report

    def regressed(*a, **kw):
        d, e, rep = real(*a, **kw)
        e["excluded"] = [x for x in e["excluded"] if x["id"] != "FAKE_Fantasy/SM_Wep_Mace_01"]
        return d, e, rep

    monkeypatch.setattr(G, "build_directory_report", regressed)
    r = gate(w)
    assert "gold" in failing(r) and "exclude did not give an excluded row" in by_check(r)["gold"]["detail"]


# --- W2e: a forward override is a gold case on the audited directory -------------------------------------------------------


FWD = {"schema": "weapon-overrides/1", "ids": {RIFLE: {"forward": "-z"}}, "globs": {}}


def test_a_forward_override_the_directory_honours_passes_and_counts_as_one_gold_id(tmp_path):
    w = make_world(tmp_path, overrides=FWD)
    axes = rec(w["dir"], RIFLE)["geometry"]["axes"]
    assert axes["forward"] == "-z" and axes["forward_source"] == "override"  # the fixture gun is +z natively
    r = gate(w)
    assert r["ok"] is True, r["detail"]
    assert "1 gold id(s) classify to their overridden values" in by_check(r)["gold"]["detail"]


def test_a_forward_override_and_a_set_on_one_id_count_once(tmp_path):
    ov = {"schema": "weapon-overrides/1", "ids": {RIFLE: {"forward": "-z", "set": {"genre": "scifi"}}}, "globs": {}}
    w = make_world(tmp_path, overrides=ov)
    r = gate(w)
    assert r["ok"] is True and "1 gold id(s)" in by_check(r)["gold"]["detail"], r["detail"]


def test_a_directory_that_disagrees_with_a_forward_override_fails_the_gold_check_naming_the_id(tmp_path):
    w = make_world(tmp_path, overrides=FWD)
    axes = rec(w["dir"], RIFLE)["geometry"]["axes"]
    axes["forward"], axes["forward_source"] = "+z", "pivot"  # the natural measurement, as if the override were lost
    save(w)
    r = gate(w)
    assert r["ok"] is False and failing(r) == ["gold"]
    assert f"{RIFLE}: forward is '+z' (pivot), the override says '-z'" in by_check(r)["gold"]["detail"]
    assert "1 of 1 gold id(s) differ" in by_check(r)["gold"]["detail"]


def test_a_forward_override_whose_sign_is_right_but_source_is_not_override_fails(tmp_path):
    w = make_world(tmp_path, overrides=FWD)
    rec(w["dir"], RIFLE)["geometry"]["axes"]["forward_source"] = "section"
    save(w)
    r = gate(w)
    assert failing(r) == ["gold"] and f"{RIFLE}: forward is '-z' (section)" in by_check(r)["gold"]["detail"]


def test_a_forward_override_on_a_record_without_geometry_fails(tmp_path):
    w = make_world(tmp_path, overrides=FWD)
    rec(w["dir"], RIFLE)["geometry"] = None
    save(w)
    r = gate(w)
    assert "gold" in failing(r)
    assert f"{RIFLE}: forward override '-z' but the record has no geometry" in by_check(r)["gold"]["detail"]


def test_a_forward_override_on_the_wrong_axis_is_not_applied_and_the_gate_says_so(tmp_path):
    ov = {"schema": "weapon-overrides/1", "ids": {RIFLE: {"forward": "+x"}}, "globs": {}}
    w = make_world(tmp_path, overrides=ov)  # the gun is z-long: +x is not its forward axis
    assert rec(w["dir"], RIFLE)["geometry"]["axes"]["forward_source"] == "pivot"
    r = gate(w)
    assert failing(r) == ["gold"] and f"{RIFLE}: forward is '+z' (pivot), the override says '+x'" in r["detail"]


def test_a_forward_override_on_an_excluded_record_is_skipped(tmp_path):
    w0 = make_world(tmp_path / "probe")
    gone = next(e["id"] for e in w0["excl"]["excluded"] if e["reason"] != "override")
    ov = {"schema": "weapon-overrides/1", "ids": {gone: {"forward": "+z"}}, "globs": {}}
    w = make_world(tmp_path / "real", overrides=ov)
    r = gate(w)
    assert r["ok"] is True, r["detail"]
    assert "0 gold id(s)" in by_check(r)["gold"]["detail"]


# --- run_gauntlet: strict, the added gate, and AC29 additivity ------------------------------------------------------------


def gate_row(result: dict) -> dict:
    return next(g for g in result["gates"] if g["gate"] == "weapons_directory")


def test_run_gauntlet_adds_exactly_one_gate_and_reports_it(world):
    result = run_gauntlet(world["cat"])
    names = [g["gate"] for g in result["gates"]]
    assert names.count("weapons_directory") == 1 and names[-1] == "weapons_directory"
    assert gate_row(result)["ok"] is True and "coverage ok" in gate_row(result)["detail"]


@pytest.fixture
def stale_cat(stale_world, tmp_path, monkeypatch):
    path = tmp_path / "weapon_overrides.json"
    path.write_text(json.dumps(STALE), encoding="utf-8")
    monkeypatch.setattr(O, "default_overrides_path", lambda: path)
    return stale_world["cat"]


def test_run_gauntlet_stale_override_passes_non_strict_and_fails_strict(stale_cat):
    loose = gate_row(run_gauntlet(stale_cat))
    assert loose["ok"] is True and GHOST in loose["detail"]
    assert gate_row(run_gauntlet(stale_cat, strict=False))["ok"] is True
    tight = gate_row(run_gauntlet(stale_cat, strict=True))
    assert tight["ok"] is False and "overrides_current" in tight["detail"] and "(fails: strict)" in tight["detail"]


def test_run_gauntlet_strict_defaults_to_false_and_is_keyword_compatible(stale_cat):
    import inspect

    param = inspect.signature(run_gauntlet).parameters["strict"]
    assert param.default is False
    # the three existing positional parameters keep their order, so no existing caller changes
    assert list(inspect.signature(run_gauntlet).parameters)[:3] == ["catalogs_dir", "threejs_v2", "godot_root"]


def test_ac29_every_existing_gate_is_unchanged_by_the_directory_and_nothing_is_written(world):
    before = tree_hash(world["cat"])
    with_dir = run_gauntlet(world["cat"])
    assert tree_hash(world["cat"]) == before  # the gate (and every other gate) wrote nothing
    bare = world["cat"].parent / "bare"
    shutil.copytree(world["cat"], bare)
    shutil.rmtree(bare / "weapons")
    without_dir = run_gauntlet(bare)
    old = [g for g in with_dir["gates"] if g["gate"] != "weapons_directory"]
    assert old == [g for g in without_dir["gates"] if g["gate"] != "weapons_directory"]
    assert gate_row(without_dir)["ok"] is True and "skipped" in gate_row(without_dir)["detail"]
    assert gauntlet.run_gauntlet.__module__ == "synty_inventory.gauntlet"
