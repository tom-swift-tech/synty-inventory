from synty_inventory.merge import stamp_auto
from synty_inventory.schema import empty_module
from synty_inventory.sources.viewer import VIEWER_ROLE_MAP, apply_viewer_module


def _asset(**over) -> dict:
    asset = {
        "id": "SM_Bld_Apartment_01",
        "name": "Apartment",
        "type": "building/shell",
        "category": [],
        "tags": ["existing"],
        "description": "x" * 80,
        "semantic_role": "building_shell",
        "placement": {},
        "ai_notes": "y" * 40,
        "module": empty_module(),
    }
    asset.update(over)
    return stamp_auto(asset)


def test_role_mapped_and_family_set():
    asset = _asset()
    piece = {"roles": ["hero", "shell"], "family": "hero", "tags": ["exterior"]}
    apply_viewer_module(asset, piece)
    assert asset["module"]["role"] == "hero"
    # viewer "family" is a generator bucket, not a kit family: it lands in tags
    assert asset["module"]["family"] is None
    assert "viewer_hero" in asset["tags"]
    assert asset["provenance"]["module"] == "viewer"
    assert "exterior" in asset["tags"] and "existing" in asset["tags"]


def test_viewer_role_does_not_clobber_rules_role():
    asset = _asset()
    asset["module"]["family"] = "Apartment"
    asset["module"]["role"] = "floor"
    apply_viewer_module(asset, {"roles": ["wall"], "family": "base", "tags": []})
    assert asset["module"] ["family"] == "Apartment"
    assert asset["module"]["role"] == "floor"


def test_ignored_roles_and_family_do_not_stamp_module():
    asset = _asset()
    piece = {"roles": ["prop", "dress"], "family": "misc", "tags": []}
    apply_viewer_module(asset, piece)
    assert asset["module"]["role"] is None
    assert asset["module"]["family"] is None
    assert asset["provenance"]["module"] == "rules"


def test_missing_piece_is_a_noop():
    asset = _asset()
    before = dict(asset["module"])
    apply_viewer_module(asset, None)
    assert asset["module"] == before


def test_curated_module_field_not_clobbered_by_viewer():
    asset = _asset()
    asset["module"]["role"] = "hero"
    asset.setdefault("provenance", {})["module"] = "curated"
    apply_viewer_module(asset, {"roles": ["wall"], "family": "annex", "tags": []})
    assert asset["module"]["role"] == "hero"
    assert asset["provenance"]["module"] == "curated"


def test_every_mapped_role_is_a_valid_module_role():
    from synty_inventory.schema import MODULE_ROLES

    assert set(VIEWER_ROLE_MAP.values()) <= set(MODULE_ROLES)
