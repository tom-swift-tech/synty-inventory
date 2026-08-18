from synty_inventory.merge import field_hash, merge_asset, stamp_auto


def test_merge_preserves_human_description():
    old = stamp_auto(
        {
            "id": "SM_Prop_Sign_Police_01",
            "name": "Police Sign",
            "type": "prop/signage",
            "category": ["sign"],
            "tags": ["police"],
            "description": "auto text",
            "semantic_role": "identifies_building_as_police_station",
            "placement": {"mount": "wall"},
            "ai_notes": "auto notes",
            "paths": {"prefab": "old.prefab", "mesh": None, "materials": []},
        }
    )
    old["description"] = "Human-authored: this plaque says POLICE in gold."
    old["provenance"]["description"] = "human"
    old["locked_fields"] = ["description"]

    new = stamp_auto(
        {
            "id": "SM_Prop_Sign_Police_01",
            "name": "Police Sign",
            "type": "prop/signage",
            "category": ["sign"],
            "tags": ["police"],
            "description": "REPLACED auto text",
            "semantic_role": "identifies_building_as_police_station",
            "placement": {"mount": "wall"},
            "ai_notes": "new notes",
            "paths": {"prefab": "new.prefab", "mesh": "new.fbx", "materials": []},
        }
    )
    merged = merge_asset(old, new)
    assert merged["description"].startswith("Human-authored")
    assert merged["paths"]["prefab"] == "new.prefab"
    assert merged["paths"]["mesh"] == "new.fbx"


def test_merge_updates_rules_fields():
    old = stamp_auto(
        {
            "id": "X",
            "name": "X",
            "type": "prop",
            "category": [],
            "tags": [],
            "description": "old auto",
            "semantic_role": "old",
            "placement": {"mount": "ground"},
            "ai_notes": "old",
            "paths": {"prefab": "a", "mesh": None, "materials": []},
        }
    )
    new = stamp_auto(
        {
            "id": "X",
            "name": "X Better",
            "type": "prop",
            "category": ["prop"],
            "tags": ["x"],
            "description": "new auto",
            "semantic_role": "new_role",
            "placement": {"mount": "wall"},
            "ai_notes": "new",
            "paths": {"prefab": "b", "mesh": None, "materials": []},
        }
    )
    merged = merge_asset(old, new)
    assert merged["description"] == "new auto"
    assert merged["semantic_role"] == "new_role"


def test_field_hash_stable():
    assert field_hash(["a", "b"]) == field_hash(["a", "b"])
    assert field_hash(["a", "b"]) != field_hash(["b", "a"])
