from pathlib import Path

from synty_inventory.catalog import write_catalog
from synty_inventory.query import (
    get_asset_details,
    get_placement_guidance,
    list_packs,
    search_assets,
    suggest_assets_for,
)
from synty_inventory.schema import validate_catalog, migrate_catalog


def _asset(aid, name, **kwargs):
    place = {
        "mount": "wall",
        "height": "eye_level",
        "orientation": "outward_facing",
        "attachment": "back_side",
        "preferred_floors": [1, 2],
        "constraints": ["exterior_only", "attach_to_building"],
        "preferred_contexts": ["police_station"],
    }
    place.update(kwargs.pop("placement", {}))
    rec = {
        "id": aid,
        "name": name,
        "type": kwargs.get("type", "prop/signage"),
        "category": kwargs.get("category", ["sign"]),
        "tags": kwargs.get("tags", []),
        "description": kwargs.get("description", name + " description " + "x" * 80),
        "semantic_role": kwargs.get("semantic_role", "identifies_building_as_police_station"),
        "placement": place,
        "dimensions": {"approx": [1.0, 0.6, 0.1], "units": "meters"},
        "paths": {"prefab": f"Prefabs/{aid}.prefab", "mesh": None, "materials": []},
        "thumbnail": None,
        "ai_notes": kwargs.get("ai_notes", "Use on the matching facade. " + "y" * 20),
    }
    return rec


def test_query_api(tmp_path: Path):
    city = {
        "pack_id": "POLYGON_City",
        "engine": "Unity",
        "origin": "Synty",
        "style": "lowpoly_modern_city",
        "units": "meters",
        "version": 1,
        "scanned_at": "2026-08-18T00:00:00+00:00",
        "assets": [
            _asset(
                "SM_Prop_Sign_Police_01",
                "Police Sign",
                tags=["police", "facade", "station"],
                semantic_role="identifies_building_as_police_station",
            ),
            _asset(
                "SM_Prop_Sign_Barber_01",
                "Barber Pole",
                tags=["barber", "pole", "salon"],
                semantic_role="identifies_building_as_barber_shop",
                placement={
                    "attachment": "side_bracket",
                    "preferred_floors": [1],
                    "preferred_contexts": ["barber_shop"],
                },
            ),
            _asset(
                "SM_Prop_Billboard_01",
                "Billboard",
                tags=["billboard", "roadside"],
                semantic_role="advertises_on_facade_or_roadside",
                placement={"mount": "pole_or_wall", "preferred_contexts": ["roadside"]},
            ),
        ],
    }
    # hand-built v1 doc: migrate_catalog is what load_catalog does on read
    city = migrate_catalog(city)
    assert validate_catalog(city) == []
    write_catalog(tmp_path / "POLYGON_City.json", city)

    packs = list_packs(tmp_path)
    assert packs[0]["pack_id"] == "POLYGON_City"

    hits = search_assets(tmp_path, "police")
    assert hits[0]["id"] == "SM_Prop_Sign_Police_01"
    # slim rows by default: prose/placement stay behind `details` / --fields
    assert hits[0]["pack"] == "POLYGON_City"
    assert "description" not in hits[0] and "placement" not in hits[0]
    wide = search_assets(tmp_path, "police", fields=["description", "placement"])
    assert wide[0]["description"].startswith("Police Sign")
    assert wide[0]["placement"]["mount"] == "wall"

    details = get_asset_details(tmp_path, "SM_Prop_Sign_Police_01")
    assert details["semantic_role"] == "building_identity"
    assert details["semantic_detail"] == "police_station"

    guide = get_placement_guidance(tmp_path, "police sign")
    assert guide["placement"]["mount"] == "wall"

    sug = suggest_assets_for(tmp_path, "first-floor barber pole")
    assert sug[0]["id"] == "SM_Prop_Sign_Barber_01"

    sug2 = suggest_assets_for(tmp_path, "roadside billboard without windows")
    assert sug2[0]["id"] == "SM_Prop_Billboard_01"


def test_search_type_and_nonplaceable_filters(tmp_path: Path):
    city = migrate_catalog(
        {
            "pack_id": "POLYGON_City",
            "engine": "Unity",
            "origin": "Synty",
            "style": "lowpoly_modern_city",
            "units": "meters",
            "version": 1,
            "scanned_at": "2026-08-18T00:00:00+00:00",
            "assets": [
                _asset(
                    "SM_Prop_Sign_Police_01",
                    "Police Sign",
                    tags=["police", "facade"],
                    semantic_role="identifies_building_as_police_station",
                ),
                _asset(
                    "A_Police_Idle_01",
                    "Police Idle",
                    type="animation",
                    tags=["police", "clip"],
                    semantic_role="unknown",
                    category=[],
                ),
            ],
        }
    )
    city["assets"][1]["placeable"] = False
    city["assets"][1]["kind"] = "animation"
    write_catalog(tmp_path / "POLYGON_City.json", city)

    hidden = search_assets(tmp_path, "police")
    assert [h["id"] for h in hidden] == ["SM_Prop_Sign_Police_01"]

    shown = search_assets(tmp_path, "police", include_nonplaceable=True)
    ids = [h["id"] for h in shown]
    assert "SM_Prop_Sign_Police_01" in ids
    assert "A_Police_Idle_01" in ids

    signs = search_assets(tmp_path, "police", types=["prop/signage"])
    assert [h["id"] for h in signs] == ["SM_Prop_Sign_Police_01"]
    none = search_assets(tmp_path, "police", types=["building/module"])
    assert none == []


def test_search_engine_unity_puts_prefab_in_file(tmp_path: Path):
    city = migrate_catalog(
        {
            "pack_id": "POLYGON_City",
            "engine": "Unity",
            "origin": "Synty",
            "style": "lowpoly_modern_city",
            "units": "meters",
            "version": 1,
            "scanned_at": "2026-08-18T00:00:00+00:00",
            "assets": [
                _asset("SM_Prop_Sign_Police_01", "Police Sign", tags=["police"]),
            ],
        }
    )
    write_catalog(tmp_path / "POLYGON_City.json", city)
    hits = search_assets(tmp_path, "police", engine="unity")
    assert hits[0]["file"] == "Prefabs/SM_Prop_Sign_Police_01.prefab"


def test_suggest_police_station_facade_ranks_sign_above_generic_prop(tmp_path: Path):
    city = migrate_catalog(
        {
            "pack_id": "POLYGON_City",
            "engine": "Unity",
            "origin": "Synty",
            "style": "lowpoly_modern_city",
            "units": "meters",
            "version": 1,
            "scanned_at": "2026-08-18T00:00:00+00:00",
            "assets": [
                _asset(
                    "SM_Prop_Sign_Police_01",
                    "Police Sign",
                    tags=["police", "facade", "station"],
                    semantic_role="identifies_building_as_police_station",
                ),
                _asset(
                    "SM_Prop_Crate_01",
                    "Crate",
                    type="prop",
                    tags=["crate", "box"],
                    category=["prop"],
                    semantic_role="dresses_scene",
                    description="Generic crate prop " + "x" * 80,
                ),
            ],
        }
    )
    write_catalog(tmp_path / "POLYGON_City.json", city)
    sug = suggest_assets_for(tmp_path, "police station facade")
    ids = [r["id"] for r in sug]
    assert ids[0] == "SM_Prop_Sign_Police_01"
    assert "SM_Prop_Crate_01" in ids
    assert ids.index("SM_Prop_Sign_Police_01") < ids.index("SM_Prop_Crate_01")


def test_get_asset_details_exact_id_wins_over_substring(tmp_path: Path):
    city = migrate_catalog(
        {
            "pack_id": "POLYGON_City",
            "engine": "Unity",
            "origin": "Synty",
            "style": "lowpoly_modern_city",
            "units": "meters",
            "version": 1,
            "scanned_at": "2026-08-18T00:00:00+00:00",
            "assets": [
                _asset("SM_Prop_Sign_Police_01b", "Police Sign B", tags=["police"]),
                _asset("SM_Prop_Sign_Police_01", "Police Sign", tags=["police"]),
            ],
        }
    )
    write_catalog(tmp_path / "POLYGON_City.json", city)
    rec = get_asset_details(tmp_path, "SM_Prop_Sign_Police_01")
    assert rec is not None
    assert rec["id"] == "SM_Prop_Sign_Police_01"
