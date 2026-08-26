"""gauntlet.run_gauntlet's godot_paths gate — mapped-pack resolution,
on-disk existence of every non-null files.godot_scene, and geometry-bearing
resolution coverage — all against tmp_path fixtures (no D:/ dependence)."""

import json
from pathlib import Path

from synty_inventory.gauntlet import GODOT_COVERAGE_FLOOR, run_gauntlet
from synty_inventory.schema import CATALOG_VERSION
from synty_inventory.sources.godot import SLUG_PACK_OVERRIDES


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")


def _asset(aid: str, *, godot_scene: str | None, kind: str = "prefab") -> dict:
    return {
        "id": aid,
        "name": aid,
        "kind": kind,
        "placeable": True,
        "type": "prop",
        "category": [],
        "tags": [],
        "description": "d" * 90,
        "semantic_role": "exterior_prop",
        "semantic_detail": "",
        "placement": {
            "mount": "ground",
            "height": "grade",
            "orientation": "upright",
            "attachment": "base_to_ground",
            "preferred_floors": [1],
            "constraints": [],
            "preferred_contexts": [],
        },
        "bounds": None,
        "dimensions": {"approx": None, "units": "meters", "source": "none"},
        "files": {
            "unity_prefab": None,
            "unity_mesh": None,
            "unity_materials": [],
            "glb": None,
            "unreal_uasset": None,
            "godot_scene": godot_scene,
        },
        "paths": {"prefab": None, "mesh": None, "materials": []},
        "thumbnail": None,
        "ai_notes": "n" * 50,
    }


def _write_catalog(catalogs_dir: Path, pack_id: str, assets: list[dict]) -> None:
    doc = {
        "pack_id": pack_id,
        "engine": "Unity",
        "origin": "Synty",
        "style": "toon",
        "units": "meters",
        "version": CATALOG_VERSION,
        "scanned_at": "2026-01-01T00:00:00+00:00",
        "grid": {"snap": 0.25, "module": 2.5, "tile": 5.0, "story": 3.0},
        "conventions": {"street_axis": "+z", "rotate_deg": 90, "scale": 1, "up_axis": "+y"},
        "asset_count": len(assets),
        "assets": assets,
    }
    catalogs_dir.mkdir(parents=True, exist_ok=True)
    (catalogs_dir / f"{pack_id}.json").write_text(json.dumps(doc), encoding="utf-8")


def _mapped_godot_root(tmp_path: Path) -> Path:
    root = tmp_path / "godot"
    for slug in SLUG_PACK_OVERRIDES:
        (root / slug).mkdir(parents=True)
    return root


def _gate(result: dict, name: str) -> dict:
    return next(g for g in result["gates"] if g["gate"] == name)


def test_godot_paths_skipped_when_root_not_configured(tmp_path: Path):
    catalogs_dir = tmp_path / "catalogs"
    _write_catalog(catalogs_dir, "POLYGON_City", [_asset("SM_Bld_Door_01", godot_scene=None)])
    result = run_gauntlet(catalogs_dir)
    gate = _gate(result, "godot_paths")
    assert gate["ok"] is True
    assert "not configured" in gate["detail"]


def test_godot_paths_fails_when_a_mapped_pack_dir_is_missing(tmp_path: Path):
    godot_root = tmp_path / "godot"
    (godot_root / "polygon-city-01").mkdir(parents=True)  # missing starter + particle-fx
    catalogs_dir = tmp_path / "catalogs"
    _write_catalog(catalogs_dir, "POLYGON_City", [_asset("SM_Bld_Door_01", godot_scene=None)])
    result = run_gauntlet(catalogs_dir, godot_root=godot_root)
    gate = _gate(result, "godot_paths")
    assert gate["ok"] is False
    assert "missing=" in gate["detail"]


def test_godot_paths_fails_on_dangling_godot_scene_reference(tmp_path: Path):
    godot_root = _mapped_godot_root(tmp_path)
    catalogs_dir = tmp_path / "catalogs"
    assets = [_asset(f"SM_Bld_Door_{i:02d}", godot_scene=None) for i in range(20)]
    assets[0]["files"]["godot_scene"] = "polygon-city-01/no_such_file.tscn"
    _write_catalog(catalogs_dir, "POLYGON_City", assets)
    result = run_gauntlet(catalogs_dir, godot_root=godot_root)
    gate = _gate(result, "godot_paths")
    assert gate["ok"] is False
    assert "SM_Bld_Door_00" in gate["detail"]


def test_godot_paths_passes_with_full_resolution_and_covers_the_pin(tmp_path: Path):
    godot_root = _mapped_godot_root(tmp_path)
    for i in range(20):
        _touch(godot_root / "polygon-city-01" / f"SM_Bld_Door_{i:02d}.tscn")
    catalogs_dir = tmp_path / "catalogs"
    assets = [
        _asset(f"SM_Bld_Door_{i:02d}", godot_scene=f"polygon-city-01/SM_Bld_Door_{i:02d}.tscn")
        for i in range(20)
    ]
    _write_catalog(catalogs_dir, "POLYGON_City", assets)
    result = run_gauntlet(catalogs_dir, godot_root=godot_root)
    gate = _gate(result, "godot_paths")
    assert gate["ok"] is True
    assert "20/20" in gate["detail"] or "100.0%" in gate["detail"]


def test_godot_paths_fails_below_coverage_floor(tmp_path: Path):
    godot_root = _mapped_godot_root(tmp_path)
    _touch(godot_root / "polygon-city-01" / "SM_Bld_Door_00.tscn")
    catalogs_dir = tmp_path / "catalogs"
    # 20 geometry-bearing assets, only 1 resolves -> 5% coverage, well under
    # GODOT_COVERAGE_FLOOR.
    assets = [_asset("SM_Bld_Door_00", godot_scene="polygon-city-01/SM_Bld_Door_00.tscn")]
    assets += [_asset(f"SM_Bld_Door_{i:02d}", godot_scene=None) for i in range(1, 20)]
    for a in assets[1:]:
        a["files"]["unity_prefab"] = f"Assets/Synty/{a['id']}.prefab"
    _write_catalog(catalogs_dir, "POLYGON_City", assets)
    result = run_gauntlet(catalogs_dir, godot_root=godot_root)
    gate = _gate(result, "godot_paths")
    assert gate["ok"] is False
    assert (1 / 20) < GODOT_COVERAGE_FLOOR


def test_godot_paths_ignores_glb_only_stems_in_coverage_denominator(tmp_path: Path):
    godot_root = _mapped_godot_root(tmp_path)
    for i in range(20):
        _touch(godot_root / "polygon-city-01" / f"SM_Bld_Door_{i:02d}.tscn")
    catalogs_dir = tmp_path / "catalogs"
    assets = [
        _asset(f"SM_Bld_Door_{i:02d}", godot_scene=f"polygon-city-01/SM_Bld_Door_{i:02d}.tscn")
        for i in range(20)
    ]
    extras = [_asset(f"SM_GlbOnly_{i:02d}", godot_scene=None, kind="mesh") for i in range(50)]
    _write_catalog(catalogs_dir, "POLYGON_City", assets + extras)
    result = run_gauntlet(catalogs_dir, godot_root=godot_root)
    gate = _gate(result, "godot_paths")
    assert gate["ok"] is True
    assert "20/20" in gate["detail"] or "100.0%" in gate["detail"]
