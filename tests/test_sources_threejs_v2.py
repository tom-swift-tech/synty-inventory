import json
from pathlib import Path

from synty_inventory.merge import stamp_auto
from synty_inventory.schema import empty_placement
from synty_inventory.catalog import build_catalog
from synty_inventory.discover import PackRef
from synty_inventory.sources.threejs_v2 import (
    apply_threejs_overlay,
    discover_converted_packs,
    glb_index,
    glb_raw_assets,
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


def test_glb_raw_assets_skips_bundles_and_collisions(tmp_path: Path):
    pack = tmp_path / "POLYGON_War"
    _write(
        pack / "manifest.json",
        {
            "models": [
                "models/Models/SM_Prop_Crate_01.glb",
                "models/Models/Characters.glb",
                "models/Models/SM_Prop_Crate_01_Convex.glb",
            ]
        },
    )
    ids = {a.id for a in glb_raw_assets(tmp_path, "POLYGON_War")}
    assert ids == {"SM_Prop_Crate_01"}


def test_discover_converted_packs_skips_known_and_gen(tmp_path: Path):
    _write(tmp_path / "POLYGON_Coffee_Shop" / "manifest.json", {"models": ["models/a.glb"]})
    _write(tmp_path / "GEN_Test" / "manifest.json", {"models": ["models/a.glb"]})
    _write(tmp_path / "POLYGON_City" / "manifest.json", {"models": ["models/a.glb"]})
    refs = discover_converted_packs(tmp_path, {"POLYGON_City"})
    assert {r.pack_id for r in refs} == {"POLYGON_Coffee_Shop"}


def test_build_catalog_unions_glb_only_stems(tmp_path: Path):
    pack = tmp_path / "FakeGlbPack"
    models = pack / "Assets" / "Synty" / "FakeGlb" / "Prefabs"
    models.mkdir(parents=True)
    (models / "SM_Prop_Crate_01.prefab").write_text("%YAML 1.1\n", encoding="utf-8")
    tj = tmp_path / "threejs"
    _write(
        tj / "FakeGlbPack" / "manifest.json",
        {"models": ["models/Models/SM_Prop_Crate_01.glb", "models/Models/SM_Prop_GlbOnly_01.glb"]},
    )
    ref = PackRef(pack_id="FakeGlbPack", engine="Unity", extracted_path=pack)
    doc = build_catalog(ref, threejs_v2=tj)
    ids = {a["id"] for a in doc["assets"]}
    assert "SM_Prop_Crate_01" in ids
    assert "SM_Prop_GlbOnly_01" in ids
    only = next(a for a in doc["assets"] if a["id"] == "SM_Prop_GlbOnly_01")
    assert only["files"]["glb"] == "FakeGlbPack/models/Models/SM_Prop_GlbOnly_01.glb"
    assert only["files"]["unity_prefab"] is None


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
    assert asset["semantic_detail"] == "police_station"
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
    assert asset2["type"] == "environment"  # via TYPE_MIGRATION

    asset3 = _base_asset()
    asset3["provenance"]["type"] = "rules"
    asset3["type"] = "prop"
    apply_threejs_overlay(asset3, {"reviewed": True, "type": "building/hero"}, None)
    assert asset3["type"] == "building/shell"

    asset4 = _base_asset()
    asset4["provenance"]["type"] = "rules"
    asset4["type"] = "prop"
    apply_threejs_overlay(asset4, {"reviewed": True, "type": "building/kit"}, None)
    assert asset4["type"] == "building/module"

    asset5 = _base_asset()
    asset5["provenance"]["type"] = "rules"
    asset5["type"] = "prop"
    apply_threejs_overlay(asset5, {"reviewed": True, "type": "not_a_type"}, None)
    assert asset5["type"] == "prop"  # unmapped — kept ours


def test_overlay_without_type_keeps_rules_type():
    asset = _base_asset()
    asset["provenance"]["type"] = "rules"
    asset["type"] = "vehicle/part"
    apply_threejs_overlay(
        asset,
        {"reviewed": True, "name": "Engine Cowling", "description": "A rear engine cowling with a round intake."},
        None,
    )
    assert asset["type"] == "vehicle/part"
    assert asset["name"] == "Engine Cowling"


def test_overlay_maps_vision_qa_role_and_mount():
    asset = _base_asset()
    asset["provenance"] = {k: "rules" for k in asset["provenance"]}
    asset["type"] = "building/shell"
    asset["semantic_role"] = "building_shell"
    apply_threejs_overlay(
        asset,
        {
            "reviewed": True,
            "type": "prop",
            "semantic_role": "shop_canopy",
            "placement": {"mount": "floor", "attachment": "bottom"},
        },
        None,
    )
    assert asset["type"] == "prop"
    assert asset["semantic_role"] == "facade_dressing"
    assert asset["semantic_detail"] == "shop_canopy"
    assert asset["placement"]["mount"] == "ground"


def test_overlay_sets_module_role_and_tunes_roof_placement():
    asset = _base_asset("SM_Bld_Apartment_01")
    asset["type"] = "building/shell"
    asset["module"] = {"family": "Apartment", "role": "hero", "stackable_on": []}
    asset["provenance"] = {k: "rules" for k in ("type", "semantic_role", "module", "placement")}
    asset["placement"] = {
        "mount": "ground",
        "height": "grade",
        "orientation": "upright",
        "attachment": "base_to_ground",
        "preferred_floors": [1],
        "constraints": ["ground_only"],
        "preferred_contexts": [],
    }
    apply_threejs_overlay(
        asset,
        {
            "reviewed": True,
            "type": "building/modular",
            "semantic_role": "apartment_floor_module",
        },
        None,
    )
    assert asset["type"] == "building/module"
    assert asset["module"]["role"] == "floor"
    assert "ground_only" not in asset["placement"]["constraints"]
    assert asset["placement"]["preferred_floors"] == []

    roof = _base_asset("SM_Bld_Apartment_Roof_01")
    roof["type"] = "building/module"
    roof["module"] = {"family": "Apartment", "role": "roof", "stackable_on": ["floor", "base"]}
    roof["provenance"] = {"placement": "rules", "module": "rules"}
    roof["placement"] = {
        "mount": "ground",
        "height": "grade",
        "orientation": "upright",
        "attachment": "base_to_ground",
        "preferred_floors": [1],
        "constraints": ["ground_only"],
        "preferred_contexts": [],
    }
    apply_threejs_overlay(
        roof,
        {"reviewed": True, "type": "building/modular", "semantic_role": "building_roof"},
        None,
    )
    assert roof["module"]["role"] == "roof"
    assert roof["placement"]["preferred_floors"] == []
    assert "ground_only" not in roof["placement"]["constraints"]

    corner = _base_asset("SM_Bld_Apartment_Corner_01")
    corner["module"] = {"family": "Apartment", "role": "hero"}
    corner["provenance"] = {"module": "rules", "type": "rules"}
    apply_threejs_overlay(
        corner,
        {"reviewed": True, "type": "building/modular", "semantic_role": "apartment_floor_module"},
        None,
    )
    assert corner["module"]["role"] == "corner"


def test_overlay_prefers_explicit_module_role_over_type_fallback():
    asset = _base_asset("SM_Bld_Block_01")
    asset["type"] = "building/shell"
    asset["module"] = {"family": "Block", "role": "hero"}
    asset["provenance"] = {"module": "rules", "type": "rules"}
    apply_threejs_overlay(
        asset,
        {"reviewed": True, "type": "building/module", "module_role": "stairs"},
        None,
    )
    assert asset["type"] == "building/module"
    assert asset["module"]["role"] == "stairs"


def test_overlay_does_not_retype_ship_parts():
    asset = _base_asset("SM_Veh_Part_Engine_01")
    asset["type"] = "vehicle/part"
    asset["part"] = {"class": "engine"}
    asset["provenance"]["type"] = "rules"
    apply_threejs_overlay(asset, {"reviewed": True, "type": "vehicle", "name": "Engine"}, None)
    assert asset["type"] == "vehicle/part"
    assert asset["name"] == "Engine"
