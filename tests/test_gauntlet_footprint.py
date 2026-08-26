"""T6: gauntlet gates for the footprint sweep (spec AC5)."""

from __future__ import annotations

import copy
import json

import pytest

from synty_inventory.gauntlet import run_gauntlet

GOOD = {
    "polygon_m": [[0.0, 0.0], [5.0, 0.0], [5.0, 5.0], [0.0, 5.0]],
    "components": 1,
    "area_m2": 25.0,
    "grade_area_m2": 25.0,
    "overhang_ratio": 0.0,
    "fill_ratio": 1.0,
    "class": "compact",
    "radius_m": None,
    "tile_cells": [1, 1],
    "snap_m": 0.25,
    "grade_band_m": [0.0, 0.5],
    "source": "measured",
    "version": 1,
}

BOUNDS = {
    "min": [0.0, 0.0, 0.0],
    "max": [5.0, 3.0, 5.0],
    "size": [5.0, 3.0, 5.0],
    "pivot": "corner",
    "source": "measured",
}


def _asset(aid, footprint="good"):
    a = {
        "id": aid,
        "name": aid,
        "kind": "prefab",
        "placeable": True,
        "type": "building/shell",
        "category": [],
        "tags": [],
        "description": "",
        "semantic_role": "building_shell",
        "semantic_detail": "",
        "placement": {
            "mount": "ground",
            "height": "grade",
            "orientation": "upright",
            "attachment": "base_to_ground",
            "preferred_floors": [1],
            "constraints": [],
            "preferred_contexts": [],
            "contact": None,
        },
        "bounds": copy.deepcopy(BOUNDS),
        "dimensions": {"approx": [5.0, 3.0, 5.0], "units": "meters", "source": "measured"},
        "files": {
            "unity_prefab": None,
            "unity_mesh": None,
            "unity_materials": [],
            "glb": f"PACK/models/{aid}.glb",
            "unreal_uasset": None,
            "godot_scene": None,
        },
        "paths": {"prefab": None, "mesh": None, "materials": []},
        "thumbnail": None,
        "ai_notes": "",
    }
    if footprint == "good":
        a["footprint"] = copy.deepcopy(GOOD)
    elif footprint == "null":
        a["footprint"] = None
    elif footprint == "escaping":
        bad = copy.deepcopy(GOOD)
        bad["polygon_m"] = [[0.0, 0.0], [90.0, 0.0], [90.0, 90.0], [0.0, 90.0]]
        a["footprint"] = bad
    elif footprint == "badclass":
        bad = copy.deepcopy(GOOD)
        bad["class"] = "blob"
        a["footprint"] = bad
    elif footprint == "absent":
        pass
    return a


def _write(catalogs, *assets):
    doc = {
        "pack_id": "PACK",
        "engine": "Unity",
        "origin": "Synty",
        "style": "test",
        "units": "meters",
        "version": 2,
        "scanned_at": "2026-08-26T00:00:00+00:00",
        "grid": {"snap": 0.25, "module": 2.5, "tile": 5.0, "story": 3.0},
        "conventions": {"street_axis": "+z", "rotate_deg": 90, "scale": 1, "up_axis": "+y"},
        "asset_count": len(assets),
        "assets": list(assets),
    }
    (catalogs / "PACK.json").write_text(json.dumps(doc), encoding="utf-8")
    return catalogs


def _gate(result, name):
    for g in result["gates"]:
        if g["gate"] == name:
            return g
    return None


def test_clean_footprints_pass(tmp_path):
    _write(tmp_path, _asset("SM_A_01"), _asset("SM_B_01", "null"))
    res = run_gauntlet(tmp_path)
    g = _gate(res, "footprint_invariants")
    assert g is not None and g["ok"], g
    assert "1 footprints, 1 null" in g["detail"]


def test_escaping_polygon_trips_the_gate(tmp_path):
    """AC5: a polygon outside its own bounding box must fail loudly. A POI
    solver reading these catalogs has no other check."""
    _write(tmp_path, _asset("SM_A_01"), _asset("SM_B_01", "escaping"))
    res = run_gauntlet(tmp_path)
    g = _gate(res, "footprint_invariants")
    assert g is not None and not g["ok"]
    assert "escapes bounds" in g["detail"]
    assert res["ok"] is False


def test_unknown_class_trips_the_gate(tmp_path):
    _write(tmp_path, _asset("SM_A_01", "badclass"))
    res = run_gauntlet(tmp_path)
    assert not _gate(res, "footprint_invariants")["ok"]


def test_class_histogram_is_reported(tmp_path):
    _write(tmp_path, _asset("SM_A_01"), _asset("SM_B_01"))
    res = run_gauntlet(tmp_path)
    g = _gate(res, "footprint_classes")
    assert g is not None and g["ok"]
    assert "compact" in g["detail"]


def test_gates_absent_when_nothing_analysed(tmp_path):
    """Catalogs from before the pass must not fail a gate for a field they
    have never carried."""
    _write(tmp_path, _asset("SM_A_01", "absent"))
    res = run_gauntlet(tmp_path)
    assert _gate(res, "footprint_invariants") is None
    assert _gate(res, "footprint_classes") is None


def test_null_only_still_gates(tmp_path):
    """Analysed-and-failed counts as analysed: the gate reports, and passes."""
    _write(tmp_path, _asset("SM_A_01", "null"))
    res = run_gauntlet(tmp_path)
    g = _gate(res, "footprint_invariants")
    assert g is not None and g["ok"]
    assert "0 footprints, 1 null" in g["detail"]


def test_token_budget_unmoved_by_footprints(tmp_path):
    """INV-7 end-to-end: adding footprints to every record must not change
    the canonical POI query set by a single byte."""
    without = run_gauntlet(_write(tmp_path, _asset("SM_A_01", "absent")))
    with_fp = run_gauntlet(_write(tmp_path, _asset("SM_A_01")))
    assert _gate(with_fp, "token_budget")["detail"] == _gate(without, "token_budget")["detail"]


@pytest.mark.parametrize("field,value", [("area_m2", 0.0), ("fill_ratio", 1.9), ("overhang_ratio", 1.0)])
def test_numeric_invariants_trip(tmp_path, field, value):
    bad = _asset("SM_B_01")
    bad["footprint"][field] = value
    _write(tmp_path, _asset("SM_A_01"), bad)
    assert not _gate(run_gauntlet(tmp_path), "footprint_invariants")["ok"]
