from synty_inventory.merge import PROVENANCE_RANK, field_hash, may_overlay, merge_asset, stamp_auto
from synty_inventory.schema import empty_module


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


def test_provenance_rank_order():
    """human > curated > vlm_reviewed > measured/vlm > viewer > rules."""
    order = ["rules", "viewer", "measured", "vlm_reviewed", "curated", "human"]
    ranks = [PROVENANCE_RANK[p] for p in order]
    assert ranks == sorted(ranks)
    assert len(set(ranks)) == len(ranks)  # each is strictly higher than the last
    assert PROVENANCE_RANK["vlm"] == PROVENANCE_RANK["measured"]


def test_may_overlay_respects_rank():
    # semantic_role is not in FORCE_OVERLAY_PAIRS, so ordinary rank applies.
    asset = {"provenance": {"semantic_role": "curated"}}
    assert may_overlay(asset, "semantic_role", "vlm_reviewed") is False
    assert may_overlay(asset, "semantic_role", "human") is True
    assert may_overlay(asset, "semantic_role", "curated") is True  # ties refresh
    untouched = {"provenance": {}}
    assert may_overlay(untouched, "semantic_role", "rules") is True


def test_may_overlay_forces_vlm_reviewed_text_over_curated():
    # name/description/tags are the one documented exception: VLM-reviewed
    # threejs-v2 prose is allowed to overwrite even a curated stamp.
    asset = {"provenance": {"name": "curated", "description": "curated", "tags": "curated"}}
    assert may_overlay(asset, "name", "vlm_reviewed") is True
    assert may_overlay(asset, "description", "vlm_reviewed") is True
    assert may_overlay(asset, "tags", "vlm_reviewed") is True
    # but not over a human lock
    human = {"provenance": {"description": "human"}}
    assert may_overlay(human, "description", "vlm_reviewed") is False


def test_merge_asset_lets_vlm_reviewed_overwrite_curated_description_on_rescan():
    """Regression test: apply_threejs_overlay() computes vlm_reviewed inside
    a single build_catalog() pass, but scan_and_write() then runs
    merge_catalog(existing_on_disk, fresh) — merge_asset() must honor the
    same curated->vlm_reviewed carve-out or a rescan silently discards the
    VLM text the moment a prior run stamped it "curated" once."""
    old = stamp_auto(
        {
            "id": "SM_Prop_Sign_Police_01",
            "name": "Police Sign",
            "type": "prop/signage",
            "category": ["sign"],
            "tags": ["police"],
            "description": "old curated description",
            "semantic_role": "identifies_building_as_police_station",
            "placement": {"mount": "wall"},
            "ai_notes": "old curated notes",
            "paths": {"prefab": "old.prefab", "mesh": None, "materials": []},
        }
    )
    old["provenance"]["description"] = "curated"
    old["provenance"]["name"] = "curated"

    new = stamp_auto(
        {
            "id": "SM_Prop_Sign_Police_01",
            "name": "Police Sign",
            "type": "prop/signage",
            "category": ["sign"],
            "tags": ["police"],
            "description": "Sign with raised channel letters spelling POLICE.",
            "semantic_role": "identifies_building_as_police_station",
            "placement": {"mount": "wall"},
            "ai_notes": "old curated notes",
            "paths": {"prefab": "old.prefab", "mesh": None, "materials": []},
        }
    )
    new["provenance"]["description"] = "vlm_reviewed"
    new["provenance"]["name"] = "vlm_reviewed"

    merged = merge_asset(old, new)
    assert merged["description"] == "Sign with raised channel letters spelling POLICE."
    assert merged["provenance"]["description"] == "vlm_reviewed"


def test_rescan_bounds_never_regress_to_null():
    old = stamp_auto(
        {
            "id": "SM_Bld_Apartment_01",
            "name": "Apartment",
            "type": "building/shell",
            "category": [],
            "tags": [],
            "description": "d" * 80,
            "semantic_role": "building_shell",
            "placement": {"mount": "ground"},
            "ai_notes": "n" * 40,
            "paths": {"prefab": "a", "mesh": None, "materials": []},
            "bounds": {"min": [0, 0, 0], "max": [5, 3, 5], "size": [5, 3, 5], "pivot": "corner", "source": "measured"},
        }
    )
    new = stamp_auto(
        {
            "id": "SM_Bld_Apartment_01",
            "name": "Apartment",
            "type": "building/shell",
            "category": [],
            "tags": [],
            "description": "d" * 80,
            "semantic_role": "building_shell",
            "placement": {"mount": "ground"},
            "ai_notes": "n" * 40,
            "paths": {"prefab": "a", "mesh": None, "materials": []},
            "bounds": None,  # this scan had no threejs_v2 configured
        }
    )
    merged = merge_asset(old, new)
    assert merged["bounds"] is not None
    assert merged["bounds"]["source"] == "measured"


def test_rescan_module_never_regresses_when_viewer_drops_out():
    old = stamp_auto(
        {
            "id": "SM_Bld_Apartment_01",
            "name": "Apartment",
            "type": "building/shell",
            "category": [],
            "tags": [],
            "description": "d" * 80,
            "semantic_role": "building_shell",
            "placement": {"mount": "ground"},
            "ai_notes": "n" * 40,
            "paths": {"prefab": "a", "mesh": None, "materials": []},
            "module": {**empty_module(), "role": "hero", "family": "hero"},
        }
    )
    old["provenance"]["module"] = "viewer"
    new = stamp_auto(
        {
            "id": "SM_Bld_Apartment_01",
            "name": "Apartment",
            "type": "building/shell",
            "category": [],
            "tags": [],
            "description": "d" * 80,
            "semantic_role": "building_shell",
            "placement": {"mount": "ground"},
            "ai_notes": "n" * 40,
            "paths": {"prefab": "a", "mesh": None, "materials": []},
            "module": empty_module(),  # viewer_data unavailable this run -> rules default
        }
    )
    merged = merge_asset(old, new)
    assert merged["module"]["role"] == "hero"
    assert merged["provenance"]["module"] == "viewer"
