from pathlib import Path

from synty_inventory.catalog import write_catalog
from synty_inventory.query import (
    get_asset_details,
    get_placement_guidance,
    list_packs,
    search_assets,
    suggest_assets_for,
)
from synty_inventory.schema import validate_catalog


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
    assert validate_catalog(city) == []
    write_catalog(tmp_path / "POLYGON_City.json", city)

    packs = list_packs(tmp_path)
    assert packs[0]["pack_id"] == "POLYGON_City"

    hits = search_assets(tmp_path, "police")
    assert hits[0]["id"] == "SM_Prop_Sign_Police_01"

    details = get_asset_details(tmp_path, "SM_Prop_Sign_Police_01")
    assert details["semantic_role"] == "identifies_building_as_police_station"

    guide = get_placement_guidance(tmp_path, "police sign")
    assert guide["placement"]["mount"] == "wall"

    sug = suggest_assets_for(tmp_path, "first-floor barber pole")
    assert sug[0]["id"] == "SM_Prop_Sign_Barber_01"

    sug2 = suggest_assets_for(tmp_path, "roadside billboard without windows")
    assert sug2[0]["id"] == "SM_Prop_Billboard_01"
