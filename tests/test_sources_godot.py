from pathlib import Path

from synty_inventory.sources.godot import (
    SLUG_PACK_OVERRIDES,
    _normalize_slug,
    apply_godot_overlay,
    discover_pack_dirs,
    scene_index,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[gd_scene]\n", encoding="utf-8")


def test_discover_pack_dirs_uses_override_map(tmp_path: Path):
    for slug in SLUG_PACK_OVERRIDES:
        (tmp_path / slug).mkdir()
    mapped = discover_pack_dirs(tmp_path)
    assert mapped == {pack_id: tmp_path / slug for slug, pack_id in SLUG_PACK_OVERRIDES.items()}


def test_discover_pack_dirs_falls_back_to_normalized_slug(tmp_path: Path):
    (tmp_path / "polygon-scifi-city-02").mkdir()
    mapped = discover_pack_dirs(tmp_path)
    assert mapped == {"Polygon_Scifi_City": tmp_path / "polygon-scifi-city-02"}


def test_discover_pack_dirs_missing_root_returns_empty():
    assert discover_pack_dirs(None) == {}
    assert discover_pack_dirs(Path("Z:/does/not/exist")) == {}


def test_normalize_slug_strips_drop_revision_and_title_cases():
    assert _normalize_slug("polygon-city-01") == "Polygon_City"
    assert _normalize_slug("particle-fx") == "Particle_Fx"
    assert _normalize_slug("weird slug!!") == "Weird_Slug"


def test_scene_index_exact_and_case_insensitive_match(tmp_path: Path):
    pack_root = tmp_path / "polygon-city-01"
    _touch(pack_root / "Assets/Synty/PolygonCity/Prefabs/Buildings/SM_Bld_Apartment_01.tscn")
    _touch(pack_root / "Assets/Synty/PolygonCity/Prefabs/Props/SM_Prop_Sign_Police_01.tscn")
    exact, ci = scene_index(tmp_path, "POLYGON_City")
    assert exact["SM_Bld_Apartment_01"] == "polygon-city-01/Assets/Synty/PolygonCity/Prefabs/Buildings/SM_Bld_Apartment_01.tscn"
    assert ci["sm_prop_sign_police_01"] == exact["SM_Prop_Sign_Police_01"]
    assert exact.get("sm_bld_apartment_01") is None


def test_scene_index_excludes_demo_and_overview_scenes(tmp_path: Path):
    pack_root = tmp_path / "polygon-starter"
    _touch(pack_root / "Assets/Synty/PolygonStarter/Scenes/Demo.tscn")
    _touch(pack_root / "Assets/Synty/PolygonStarter/Scenes/Overview.tscn")
    _touch(pack_root / "Assets/Synty/PolygonStarter/Prefabs/SM_Bld_Door_01.tscn")
    exact, _ = scene_index(tmp_path, "POLYGON_Starter")
    assert "Demo" not in exact and "Overview" not in exact
    assert "SM_Bld_Door_01" in exact


def test_scene_index_unmapped_pack_or_missing_root_returns_empty(tmp_path: Path):
    assert scene_index(tmp_path, "POLYGON_City") == ({}, {})
    assert scene_index(None, "POLYGON_City") == ({}, {})


def test_apply_godot_overlay_sets_files_field_with_no_provenance():
    asset = {"id": "SM_Bld_Door_01", "files": {"godot_scene": None}}
    apply_godot_overlay(asset, "polygon-starter/Assets/Synty/PolygonStarter/Prefabs/SM_Bld_Door_01.tscn")
    assert asset["files"]["godot_scene"] == "polygon-starter/Assets/Synty/PolygonStarter/Prefabs/SM_Bld_Door_01.tscn"
    assert "provenance" not in asset


def test_apply_godot_overlay_noop_when_no_match():
    asset = {"id": "SM_Bld_Door_01", "files": {"godot_scene": None}}
    apply_godot_overlay(asset, None)
    assert asset["files"]["godot_scene"] is None
