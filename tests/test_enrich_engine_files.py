"""enrich_catalog wiring for files.godot_scene / files.unreal_uasset — the
per-asset overlay point next to apply_threejs_overlay's files.glb wiring."""

from pathlib import Path

from synty_inventory.enrich import enrich_catalog
from synty_inventory.merge import stamp_auto
from synty_inventory.schema import empty_files, empty_placement
from synty_inventory.sources import unreal as unreal_src


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")


def _catalog(pack_id: str, asset_id: str) -> dict:
    asset = stamp_auto(
        {
            "id": asset_id,
            "name": "Door",
            "type": "prop",
            "category": [],
            "tags": [],
            "description": "",
            "semantic_role": "unknown",
            "semantic_detail": "",
            "placement": empty_placement(),
            "ai_notes": "",
            "files": empty_files(),
        }
    )
    return {"pack_id": pack_id, "assets": [asset]}


def test_enrich_catalog_wires_godot_scene_when_root_configured(tmp_path: Path):
    godot_root = tmp_path / "godot"
    _touch(godot_root / "polygon-city-01" / "Assets/Synty/PolygonCity/Prefabs/Buildings/SM_Bld_Door_01.tscn")
    doc = _catalog("POLYGON_City", "SM_Bld_Door_01")

    enrich_catalog(doc, viewer_data=None, godot_root=godot_root)

    rel = doc["assets"][0]["files"]["godot_scene"]
    assert rel == "polygon-city-01/Assets/Synty/PolygonCity/Prefabs/Buildings/SM_Bld_Door_01.tscn"
    assert (godot_root / rel).is_file()


def test_enrich_catalog_leaves_godot_scene_null_when_root_not_configured():
    doc = _catalog("POLYGON_City", "SM_Bld_Door_01")
    enrich_catalog(doc, viewer_data=None)
    assert doc["assets"][0]["files"]["godot_scene"] is None


def test_enrich_catalog_leaves_godot_scene_null_when_no_stem_match(tmp_path: Path):
    godot_root = tmp_path / "godot"
    _touch(godot_root / "polygon-city-01" / "Assets/Synty/PolygonCity/Prefabs/SM_Bld_Other_01.tscn")
    doc = _catalog("POLYGON_City", "SM_Bld_Door_01")
    enrich_catalog(doc, viewer_data=None, godot_root=godot_root)
    assert doc["assets"][0]["files"]["godot_scene"] is None


def test_enrich_catalog_skips_unmapped_godot_slug(tmp_path: Path):
    godot_root = tmp_path / "godot"
    _touch(godot_root / "polygon-scifi-city-02" / "Assets/SM_Bld_Shop_01.tscn")
    _touch(godot_root / "polygon-city-01" / "Assets/SM_Bld_Door_01.tscn")
    scifi = _catalog("POLYGON_SciFi_City", "SM_Bld_Shop_01")
    enrich_catalog(scifi, viewer_data=None, godot_root=godot_root)
    assert scifi["assets"][0]["files"]["godot_scene"] is None
    city = _catalog("POLYGON_City", "SM_Bld_Door_01")
    enrich_catalog(city, viewer_data=None, godot_root=godot_root)
    assert city["assets"][0]["files"]["godot_scene"] == "polygon-city-01/Assets/SM_Bld_Door_01.tscn"


def test_enrich_catalog_wires_unreal_uasset_when_root_configured(tmp_path, monkeypatch):
    monkeypatch.setitem(unreal_src.SLUG_PACK_OVERRIDES, "unreal-city", "POLYGON_City")
    unreal_root = tmp_path / "unreal"
    _touch(unreal_root / "unreal-city" / "Content/Buildings/SM_Bld_Door_01.uasset")
    doc = _catalog("POLYGON_City", "SM_Bld_Door_01")

    enrich_catalog(doc, viewer_data=None, unreal_root=unreal_root)

    rel = doc["assets"][0]["files"]["unreal_uasset"]
    assert rel == "unreal-city/Content/Buildings/SM_Bld_Door_01.uasset"


def test_enrich_catalog_leaves_unreal_uasset_null_on_real_machine_default():
    """No unreal_root is ever configured today — the default must stay null,
    not raise."""
    doc = _catalog("POLYGON_City", "SM_Bld_Door_01")
    enrich_catalog(doc, viewer_data=None)
    assert doc["assets"][0]["files"]["unreal_uasset"] is None
