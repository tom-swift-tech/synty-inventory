"""gauntlet.run_gauntlet's mech_slots gate — skip cleanly when POLYGON_Mech
isn't on disk, and (when present) assert body assets carry skeleton+slots+
variants, standalone attachments carry part.slot+attach_bone, and the
pinned 2026-08-19 ground-truth conventions hold. All against tmp_path
fixtures (no D:/ dependence)."""

import json
from pathlib import Path

from synty_inventory.gauntlet import run_gauntlet
from synty_inventory.schema import CATALOG_VERSION, empty_files, empty_module, empty_part, empty_paths, empty_placement


def _asset(aid: str, *, atype: str = "vehicle/part", mech: dict | None = None, part: dict | None = None) -> dict:
    p = empty_part()
    if part:
        p.update(part)
    a = {
        "id": aid,
        "name": aid,
        "kind": "mesh",
        "placeable": True,
        "type": atype,
        "category": [],
        "tags": [],
        "description": "d" * 90,
        "semantic_role": "vehicle_part",
        "semantic_detail": "",
        "placement": empty_placement(),
        "bounds": None,
        "dimensions": {"approx": None, "units": "meters", "source": "none"},
        "module": empty_module(),
        "part": p,
        "files": empty_files(),
        "paths": empty_paths(),
        "thumbnail": None,
        "ai_notes": "n" * 50,
    }
    if mech is not None:
        a["mech"] = mech
    return a


def _write_catalog(catalogs_dir: Path, pack_id: str, assets: list[dict]) -> None:
    doc = {
        "pack_id": pack_id,
        "engine": "Unity",
        "origin": "Synty",
        "style": "lowpoly_mech",
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


def _gate(result: dict, name: str) -> dict:
    return next(g for g in result["gates"] if g["gate"] == name)


_MECH_VARIANTS = {f"SM_Veh_Mech_{i:02d}": [f"geo_x_{n:03d}" for n in range(64)] for i in range(1, 7)}


def _pinned_slots() -> list[dict]:
    return [
        {"region": "chest", "side": "r", "bone": "Spine_01", "geo_nodes": ["geo_r_chest_attach_weapon_01"]},
        {"region": "cockpit", "side": "c", "bone": "CockpitDoor", "geo_nodes": ["geo_c_cockpit_door_01"]},
    ]


def test_mech_slots_skipped_when_pack_not_on_disk(tmp_path: Path):
    catalogs_dir = tmp_path / "catalogs"
    _write_catalog(catalogs_dir, "POLYGON_City", [_asset("SM_Veh_Part_Body_01")])
    result = run_gauntlet(catalogs_dir)
    gate = _gate(result, "mech_slots")
    assert gate["ok"] is True
    assert "not on disk" in gate["detail"]


def test_mech_slots_passes_with_full_body_and_attachments(tmp_path: Path):
    catalogs_dir = tmp_path / "catalogs"
    body = _asset(
        "SM_Veh_Mech_01",
        atype="vehicle",
        mech={"skeleton": ["Spine_01", "CockpitDoor"], "slots": _pinned_slots(), "variants": _MECH_VARIANTS},
    )
    attach = _asset(
        "SM_Mech_Leg_01_Armor_Kneepad_03",
        part={"slot": {"region": "lowerleg", "side": "l"}, "attach_bone": "LowerLeg_L"},
    )
    _write_catalog(catalogs_dir, "POLYGON_Mech", [body, attach])
    result = run_gauntlet(catalogs_dir)
    gate = _gate(result, "mech_slots")
    assert gate["ok"] is True, gate["detail"]
    assert "1/1" in gate["detail"]


def test_mech_slots_fails_when_body_missing_slots(tmp_path: Path):
    catalogs_dir = tmp_path / "catalogs"
    body = _asset("SM_Veh_Mech_01", atype="vehicle", mech={"skeleton": [], "slots": [], "variants": {}})
    attach = _asset(
        "SM_Mech_Leg_01_Armor_Kneepad_03",
        part={"slot": {"region": "lowerleg", "side": "l"}, "attach_bone": "LowerLeg_L"},
    )
    _write_catalog(catalogs_dir, "POLYGON_Mech", [body, attach])
    result = run_gauntlet(catalogs_dir)
    gate = _gate(result, "mech_slots")
    assert gate["ok"] is False


def test_mech_slots_fails_below_attachment_coverage_floor(tmp_path: Path):
    catalogs_dir = tmp_path / "catalogs"
    body = _asset(
        "SM_Veh_Mech_01",
        atype="vehicle",
        mech={"skeleton": ["Spine_01", "CockpitDoor"], "slots": _pinned_slots(), "variants": _MECH_VARIANTS},
    )
    resolved = _asset(
        "SM_Mech_Leg_01_Armor_Kneepad_03",
        part={"slot": {"region": "lowerleg", "side": "l"}, "attach_bone": "LowerLeg_L"},
    )
    unresolved = [_asset(f"SM_Mech_Unknown_01_Widget_{i:02d}") for i in range(1, 20)]  # 19 unresolved, 1 resolved
    _write_catalog(catalogs_dir, "POLYGON_Mech", [body, resolved, *unresolved])
    result = run_gauntlet(catalogs_dir)
    gate = _gate(result, "mech_slots")
    assert gate["ok"] is False
    assert "1/20" in gate["detail"]


def test_mech_slots_fails_when_pinned_conventions_do_not_hold(tmp_path: Path):
    catalogs_dir = tmp_path / "catalogs"
    body = _asset(
        "SM_Veh_Mech_01",
        atype="vehicle",
        # neither the chest-attach-weapon nor the cockpit pin is present
        mech={"skeleton": ["Spine_01"], "slots": [{"region": "hips", "side": "c", "bone": "Hips", "geo_nodes": ["geo_c_hips_01"]}], "variants": _MECH_VARIANTS},
    )
    attach = _asset(
        "SM_Mech_Leg_01_Armor_Kneepad_03",
        part={"slot": {"region": "lowerleg", "side": "l"}, "attach_bone": "LowerLeg_L"},
    )
    _write_catalog(catalogs_dir, "POLYGON_Mech", [body, attach])
    result = run_gauntlet(catalogs_dir)
    gate = _gate(result, "mech_slots")
    assert gate["ok"] is False
    assert "chest_attach_weapon_01->Spine_01=False" in gate["detail"]
    assert "cockpit->CockpitDoor=False" in gate["detail"]
