"""First-class character gear block (Border Suns wardrobe + weapon attachments)."""


from synty_inventory.schema import (
    empty_gear,
    empty_files,
    empty_module,
    empty_part,
    empty_paths,
    empty_placement,
    dimensions_from_bounds,
    validate_asset,
    validate_catalog,
    CATALOG_VERSION,
    DEFAULT_GRID,
    DEFAULT_CONVENTIONS,
    GEAR_KINDS,
    GEAR_ROLES,
)


def _minimal_asset(**overrides):
    a = {
        "id": "SM_Chr_Attach_Helmet_01",
        "name": "Helmet",
        "kind": "mesh",
        "placeable": False,
        "type": "character/part",
        "category": ["character", "wardrobe"],
        "tags": ["wardrobe", "helmet", "slot_head"],
        "description": "x",
        "semantic_role": "character_part",
        "semantic_detail": "helmet",
        "placement": empty_placement(),
        "bounds": None,
        "dimensions": dimensions_from_bounds(None),
        "files": empty_files(),
        "paths": empty_paths(),
        "thumbnail": None,
        "ai_notes": "",
        "module": empty_module(),
        "part": empty_part(),
        "gear": empty_gear(),
    }
    a.update(overrides)
    return a


def test_empty_gear_validates():
    errors = []
    validate_asset(_minimal_asset(), "a", errors)
    assert errors == [], errors


def test_gear_enums_reject_unknown():
    bad = _minimal_asset(gear={**empty_gear(), "kind": "hat", "slot": "head"})
    errors = []
    validate_asset(bad, "a", errors)
    assert any("gear.kind" in e for e in errors)


def test_gear_kinds_include_attachment():
    assert "attachment" in GEAR_KINDS
    assert "weapon" in GEAR_KINDS


def test_gear_roles_include_optic():
    assert "optic" in GEAR_ROLES
    assert "wardrobe" in GEAR_ROLES
    assert "preset" in GEAR_ROLES


def test_optic_attachment_gear_validates():
    gear = empty_gear()
    gear.update({
        "kind": "attachment",
        "slot": "none",
        "fits": "any",
        "coverage": None,
        "role": "optic",
        "attach": True,
        "twoHanded": None,
        "paintFamily": None,
    })
    errors = []
    validate_asset(_minimal_asset(id="SM_Wep_Mod_Scope_01", gear=gear), "a", errors)
    assert errors == [], errors


def test_gear_happy_path_in_catalog():
    gear = empty_gear()
    gear.update({
        "kind": "helmet",
        "slot": "head",
        "fits": "human",
        "coverage": "heavy",
        "role": "wardrobe",
        "attach": True,
        "twoHanded": None,
        "paintFamily": "red",
    })
    doc = {
        "pack_id": "TEST_Gear",
        "engine": "Unity",
        "origin": "Synty",
        "style": "test",
        "units": "meters",
        "version": CATALOG_VERSION,
        "scanned_at": "2026-09-16T00:00:00+00:00",
        "grid": dict(DEFAULT_GRID),
        "conventions": dict(DEFAULT_CONVENTIONS),
        "assets": [_minimal_asset(gear=gear)],
    }
    assert validate_catalog(doc) == []
