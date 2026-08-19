"""Schema v2: enums, migration, null bounds."""

from copy import deepcopy

from synty_inventory.schema import (
    CATALOG_VERSION,
    migrate_catalog,
    normalize_semantic_role,
    pivot_from_aabb,
    validate_catalog,
)


def _v1_doc():
    return {
        "pack_id": "POLYGON_Test",
        "engine": "Unity",
        "origin": "Synty",
        "style": "lowpoly_test",
        "units": "meters",
        "version": 1,
        "scanned_at": "2026-08-18T00:00:00+00:00",
        "assets": [
            {
                "id": "SM_Bld_Apartment_01",
                "name": "Apartment",
                "type": "building/modular",
                "category": ["building"],
                "tags": ["apartment"],
                "description": "x",
                "semantic_role": "forms_residential_block_shell",
                "placement": {
                    "mount": "ground",
                    "height": "grade",
                    "orientation": "street_face_plus_z",
                    "attachment": "base_to_ground",
                    "preferred_floors": [1],
                    "constraints": ["snap_to_grid"],
                    "preferred_contexts": [],
                },
                "dimensions": {"approx": [5.0, 3.0, 5.2], "units": "meters", "source": "measured"},
                "paths": {"prefab": "Assets/P.prefab", "mesh": None, "materials": []},
                "thumbnail": None,
                "ai_notes": "",
            },
            {
                "id": "SM_Veh_Part_Engine_01",
                "name": "Part Engine",
                "type": "vehicle",
                "category": [],
                "tags": [],
                "description": "",
                "semantic_role": "populates_street_or_lot",
                "placement": {
                    "mount": "facade",
                    "height": "grade",
                    "orientation": "upright",
                    "attachment": "base_to_ground",
                    "preferred_floors": [1],
                    "constraints": [],
                    "preferred_contexts": [],
                },
                "dimensions": {"approx": [4.5, 1.6, 2.0], "units": "meters", "source": "heuristic"},
                "paths": {"prefab": None, "mesh": "Assets/M.fbx", "materials": []},
                "thumbnail": None,
                "ai_notes": "",
            },
        ],
    }


def test_v1_fails_v2_validation_until_migrated():
    doc = _v1_doc()
    assert validate_catalog(doc)  # v1 is not valid v2
    v2 = migrate_catalog(doc)
    assert v2["version"] == CATALOG_VERSION
    assert validate_catalog(v2) == [], validate_catalog(v2)


def test_migration_maps_types_roles_files_and_bounds():
    v2 = migrate_catalog(_v1_doc())
    bld, eng = v2["assets"]
    assert bld["type"] == "building/module"
    assert bld["semantic_role"] == "building_shell"
    assert bld["semantic_detail"] == "residential_block"
    assert bld["files"]["unity_prefab"] == "Assets/P.prefab"
    assert bld["paths"]["prefab"] == "Assets/P.prefab"
    assert bld["kind"] == "prefab" and bld["placeable"] is True
    # measured v1 dims survive as bounds
    assert bld["bounds"]["size"] == [5.0, 3.0, 5.2]
    assert bld["bounds"]["source"] == "measured"
    assert bld["dimensions"]["approx"] == [5.0, 3.0, 5.2]
    # heuristic dims do NOT become bounds
    assert eng["bounds"] is None
    assert eng["dimensions"]["approx"] is None
    assert eng["placement"]["mount"] == "wall"  # facade alias
    assert eng["kind"] == "mesh"


def test_enum_rejection():
    v2 = migrate_catalog(_v1_doc())
    bad = deepcopy(v2)
    a = bad["assets"][0]
    a["type"] = "building/whatever"
    a["semantic_role"] = "forms_residential_block_shell"
    a["placement"]["mount"] = "sideways"
    a["module"]["role"] = "penthouse"
    a["part"]["class"] = "thruster"
    a["tags"] = ["Has Spaces"]
    errs = validate_catalog(bad)
    assert any(".type invalid" in e for e in errs)
    assert any(".semantic_role invalid" in e for e in errs)
    assert any(".placement.mount invalid" in e for e in errs)
    assert any(".module.role invalid" in e for e in errs)
    assert any(".part.class invalid" in e for e in errs)
    assert any("not snake_case" in e for e in errs)


def test_fake_dimensions_without_bounds_rejected():
    v2 = migrate_catalog(_v1_doc())
    v2["assets"][1]["dimensions"]["approx"] = [1.0, 1.0, 1.0]
    assert any("fake size" in e for e in validate_catalog(v2))


def test_role_normalisation():
    assert normalize_semantic_role("identifies_building_as_barber_shop") == ("building_identity", "barber_shop")
    assert normalize_semantic_role("displays_syn_corp") == ("advertisement", "syn_corp")
    assert normalize_semantic_role("building_module", "floor") == ("building_module", "floor")
    assert normalize_semantic_role("totally_new_thing") == ("unknown", "totally_new_thing")


def test_pivot_classification():
    assert pivot_from_aabb([0, 0, -5], [5, 3, 0.19]) == "corner"
    assert pivot_from_aabb([-2.5, 0, -2.5], [2.5, 3, 2.5]) == "center_bottom"
    assert pivot_from_aabb([-1, -1, -1], [1, 1, 1]) == "center"
