import json
from pathlib import Path

from synty_inventory.merge import stamp_auto
from synty_inventory.schema import empty_placement
from synty_inventory.sources.threejs_v2 import (
    apply_threejs_overlay,
    glb_index,
    load_catalog,
    load_manifest,
)


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_glb_index_exact_and_case_insensitive(tmp_path: Path):
    pack = tmp_path / "POLYGON_City"
    _write(
        pack / "manifest.json",
        {"models": ["models/Models/SM_Bld_Apartment_01.glb", "models/FX/FX_Plane_01.glb"]},
    )
    exact, ci = glb_index(tmp_path, "POLYGON_City")
    assert exact["SM_Bld_Apartment_01"] == "POLYGON_City/models/Models/SM_Bld_Apartment_01.glb"
    assert ci["sm_bld_apartment_01"] == "POLYGON_City/models/Models/SM_Bld_Apartment_01.glb"
    assert exact.get("sm_bld_apartment_01") is None


def test_glb_index_missing_manifest_returns_empty(tmp_path: Path):
    exact, ci = glb_index(tmp_path, "NoSuchPack")
    assert exact == {} and ci == {}
    assert load_manifest(None, "x") is None
    assert load_catalog(None, "x") is None


def _base_asset(aid="SM_Prop_Sign_Police_01") -> dict:
    asset = {
        "id": aid,
        "name": "Police Sign",
        "type": "prop/signage",
        "category": ["sign"],
        "tags": ["police"],
        "description": "auto text " * 5,
        "semantic_role": "building_identity",
        "semantic_detail": "police_station",
        "placement": empty_placement(),
        "ai_notes": "auto notes " * 4,
        "files": {"glb": None},
    }
    return stamp_auto(asset)


def test_overlay_attaches_glb_even_without_catalog_entry():
    asset = _base_asset()
    apply_threejs_overlay(asset, None, "POLYGON_City/models/Models/SM_Prop_Sign_Police_01.glb")
    assert asset["files"]["glb"] == "POLYGON_City/models/Models/SM_Prop_Sign_Police_01.glb"


def test_overlay_ignored_when_not_reviewed():
    asset = _base_asset()
    entry = {"name": "New Name", "description": "New description", "reviewed": False}
    before = dict(asset)
    apply_threejs_overlay(asset, entry, None)
    assert asset["name"] == before["name"]
    assert asset["description"] == before["description"]


def test_overlay_on_rules_asset_applies_all_fields():
    asset = _base_asset()
    asset["provenance"] = {k: "rules" for k in asset["provenance"]}
    entry = {
        "reviewed": True,
        "name": "Police Channel Letters",
        "description": "White 3D extruded block letters spelling POLICE.",
        "tags": ["channel_letters", "wordmark"],
        "semantic_role": "identifies_building_as_police_station",
        "type": "prop/signage",
        "ai_notes": "Lettering only, mount on facade.",
        "placement": {
            "mount": "wall",
            "attachment": "back_side",
            "height": "eye_level",
            "preferred_contexts": ["police_station", "civic_building"],
        },
    }
    apply_threejs_overlay(asset, entry, None)
    assert asset["name"] == "Police Channel Letters"
    assert asset["description"].startswith("White 3D extruded")
    assert "channel_letters" in asset["tags"] and "police" in asset["tags"]
    assert asset["semantic_role"] == "building_identity"
    assert asset["semantic_detail"] == "identifies_building_as_police_station"
    assert asset["ai_notes"].startswith("Lettering only")
    assert asset["placement"]["mount"] == "wall"
    assert asset["placement"]["attachment"] == "back_side"
    assert "police_station" in asset["placement"]["preferred_contexts"]
    for field in ("name", "description", "tags", "semantic_role", "ai_notes", "placement"):
        assert asset["provenance"][field] == "vlm_reviewed"


def test_overlay_on_curated_asset_keeps_placement_and_ai_notes_but_takes_text():
    asset = _base_asset()
    asset["provenance"] = {
        "name": "curated",
        "description": "curated",
        "tags": "curated",
        "semantic_role": "curated",
        "placement": "curated",
        "ai_notes": "curated",
    }
    curated_placement = dict(asset["placement"])
    curated_ai_notes = asset["ai_notes"]
    entry = {
        "reviewed": True,
        "name": "Police Channel Letters",
        "description": "White 3D extruded block letters spelling POLICE, channel-letter civic wordmark.",
        "tags": ["channel_letters"],
        "semantic_role": "some_other_role_string",
        "ai_notes": "REPLACED — should not win",
        "placement": {"mount": "roof"},
    }
    apply_threejs_overlay(asset, entry, None)
    # Forced-through even though curated:
    assert asset["name"] == "Police Channel Letters"
    assert "letters" in asset["description"]
    assert "channel_letters" in asset["tags"]
    assert asset["provenance"]["name"] == "vlm_reviewed"
    assert asset["provenance"]["description"] == "vlm_reviewed"
    assert asset["provenance"]["tags"] == "vlm_reviewed"
    # Curated judgement calls stay put:
    assert asset["placement"] == curated_placement
    assert asset["ai_notes"] == curated_ai_notes
    assert asset["provenance"]["placement"] == "curated"
    assert asset["provenance"]["ai_notes"] == "curated"


def test_type_only_migrated_when_in_schema_types():
    asset = _base_asset()
    asset["provenance"]["type"] = "rules"
    asset["type"] = "prop"
    apply_threejs_overlay(asset, {"reviewed": True, "type": "building/modular"}, None)
    assert asset["type"] == "building/module"  # via TYPE_MIGRATION

    asset2 = _base_asset()
    asset2["provenance"]["type"] = "rules"
    asset2["type"] = "prop"
    apply_threejs_overlay(asset2, {"reviewed": True, "type": "environment/nature"}, None)
    assert asset2["type"] == "prop"  # not a schema.TYPES value — kept ours
