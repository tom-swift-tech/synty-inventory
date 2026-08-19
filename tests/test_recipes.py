"""Recipes: package recipes validate, selectors resolve, viewer types convert, matching works."""

import json
from pathlib import Path

from synty_inventory.catalog import write_catalog
from synty_inventory.recipes import (
    PACKAGE_RECIPES_DIR,
    kit_family,
    load_recipes,
    match_recipes,
    resolve_recipe,
    validate_recipe,
)
from synty_inventory.schema import (
    DEFAULT_CONVENTIONS,
    DEFAULT_GRID,
    empty_files,
    empty_module,
    empty_part,
    empty_placement,
    validate_catalog,
)


def _asset(aid, atype, role, **kw):
    module = empty_module()
    module.update(kw.pop("module", {}))
    part = empty_part()
    part.update(kw.pop("part", {}))
    files = empty_files()
    files["unity_prefab"] = f"Prefabs/{aid}.prefab"
    files["glb"] = f"PACK/models/{aid}.glb"
    place = empty_placement()
    place.update(kw.pop("placement", {}))
    return {
        "id": aid,
        "name": aid,
        "kind": "prefab",
        "placeable": True,
        "type": atype,
        "category": kw.pop("category", []),
        "tags": kw.pop("tags", []),
        "description": "d",
        "semantic_role": role,
        "semantic_detail": kw.pop("detail", ""),
        "placement": place,
        "bounds": {"min": [0, 0, -5], "max": [5, 3, 0], "size": [5, 3, 5], "pivot": "corner", "source": "measured"},
        "dimensions": {"approx": [5, 3, 5], "units": "meters", "source": "measured"},
        "module": module,
        "part": part,
        "files": files,
        "paths": {"prefab": files["unity_prefab"], "mesh": None, "materials": []},
        "thumbnail": None,
        "ai_notes": "",
    }


def _catalogs(tmp_path: Path) -> Path:
    space = {
        "pack_id": "POLYGON_SciFi_Space",
        "engine": "Unity",
        "origin": "Synty",
        "style": "lowpoly_scifi_space",
        "units": "meters",
        "version": 2,
        "scanned_at": "2026-08-19T00:00:00+00:00",
        "grid": DEFAULT_GRID,
        "conventions": DEFAULT_CONVENTIONS,
        "assets": [
            _asset("SM_Veh_Part_Body_01", "vehicle/part", "vehicle_part", part={"class": "body"}),
            _asset("SM_Veh_Part_Cockpit_01", "vehicle/part", "vehicle_part", part={"class": "cockpit"}),
            _asset("SM_Veh_Part_Engine_01", "vehicle/part", "vehicle_part", part={"class": "engine"}),
            _asset("SM_Veh_Part_Wing_01", "vehicle/part", "vehicle_part", part={"class": "wing"}),
            _asset("SM_Ship_Fighter_01", "vehicle/spacecraft", "spacecraft", part={"size_class": "fighter"}),
            _asset("SM_Bld_Floor_01", "building/interior_module", "interior_module", module={"family": "Interior", "role": "floor"}),
            _asset("SM_Bld_Wall_01", "building/interior_module", "interior_module", module={"family": "Interior", "role": "wall"}),
        ],
    }
    city = dict(space)
    city.update(
        pack_id="POLYGON_City",
        style="lowpoly_modern_city",
        assets=[
            _asset("SM_Bld_Shop_01", "building/shell", "building_shell", tags=["shop"], module={"family": "Shop", "role": "hero"}),
            _asset("SM_Bld_Shop_02", "building/shell", "building_shell", tags=["shop"], module={"family": "Shop", "role": "hero"}),
            _asset("SM_Bld_Apartment_Door_01", "building/module", "building_module", module={"family": "Apartment", "role": "door"}),
            _asset("SM_Bld_Apartment_Floor_01", "building/module", "building_module", module={"family": "Apartment", "role": "floor"}),
            _asset("SM_Bld_Apartment_Roof_01", "building/module", "building_module", module={"family": "Apartment", "role": "roof"}),
            _asset("SM_Prop_Sign_Barber_01", "prop/signage", "building_identity", detail="barber_shop"),
        ],
    )
    assert validate_catalog(space) == [], validate_catalog(space)
    assert validate_catalog(city) == [], validate_catalog(city)
    write_catalog(tmp_path / "POLYGON_SciFi_Space.json", space)
    write_catalog(tmp_path / "POLYGON_City.json", city)
    return tmp_path


def test_package_recipes_are_valid():
    files = sorted(PACKAGE_RECIPES_DIR.glob("*.json"))
    assert {f.stem for f in files} >= {"ship_kit", "station_interior", "main_street_row", "apartment_block"}
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        assert validate_recipe(doc) == [], (f.name, validate_recipe(doc))
        assert doc["id"] == f.stem


def test_resolve_ship_kit_and_apartment(tmp_path):
    cat = _catalogs(tmp_path)
    recipes = load_recipes(cat)
    ship = resolve_recipe(cat, recipes["ship_kit"])
    by_role = {s["role"]: s for s in ship["resolved_steps"]}
    assert [p["id"] for p in by_role["engine"]["eligible"]] == ["SM_Veh_Part_Engine_01"]
    assert [p["id"] for p in by_role["wing"]["eligible"]] == ["SM_Veh_Part_Wing_01"]
    assert by_role["reference_ships"]["eligible"][0]["id"] == "SM_Ship_Fighter_01"
    assert ship["complete"] is True
    apt = resolve_recipe(cat, recipes["apartment_block"], pack="POLYGON_City")
    by_role = {s["role"]: s for s in apt["resolved_steps"]}
    assert by_role["base"]["eligible"][0]["id"] == "SM_Bld_Apartment_Door_01"
    assert by_role["floor"]["eligible"][0]["id"] == "SM_Bld_Apartment_Floor_01"
    assert by_role["roof"]["eligible"][0]["id"] == "SM_Bld_Apartment_Roof_01"
    assert apt["complete"] is True
    # every eligible piece carries bounds + per-engine files
    piece = by_role["floor"]["eligible"][0]
    assert piece["bounds"]["size"] == [5, 3, 5]
    assert piece["files"]["glb"].endswith("SM_Bld_Apartment_Floor_01.glb")


def test_missing_required_is_reported(tmp_path):
    cat = _catalogs(tmp_path)
    recipes = load_recipes(cat)
    row = resolve_recipe(cat, recipes["main_street_row"], pack="POLYGON_SciFi_Space")
    assert row["complete"] is False
    assert "shell" in row["missing_required_roles"]


def test_kit_family(tmp_path):
    cat = _catalogs(tmp_path)
    fams = kit_family(cat, "apartment")
    assert len(fams) == 1
    assert set(fams[0]["roles"]) == {"door", "floor", "roof"}


def test_viewer_types_convert(tmp_path):
    viewer = tmp_path / "viewer"
    (viewer / "types").mkdir(parents=True)
    (viewer / "types" / "POLYGON_City.json").write_text(
        json.dumps(
            {
                "pack": "POLYGON_City",
                "types": [
                    {
                        "id": "shop",
                        "label": "Shop",
                        "required": ["hero", "sign"],
                        "height": {"low": [3, 6]},
                        "heroes": [{"ids": ["SM_Bld_Shop_01"], "weight": 3}],
                        "annex": [],
                        "facade": {"ads": ["SM_Prop_Poster_01"], "adCount": [1, 2], "heights": [2.2]},
                        "roof": {"ids": ["SM_Prop_Roof_Aircon_01"], "count": [0, 1]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    recipes = load_recipes(None, viewer)
    rec = recipes["building_shop@POLYGON_City"]
    assert validate_recipe(rec) == []
    roles = [s["role"] for s in rec["steps"]]
    assert roles == ["hero", "ad", "roof"]
    assert rec["steps"][0]["required"] is True


def test_user_recipes_override_package(tmp_path):
    cat = _catalogs(tmp_path)
    (cat / "recipes").mkdir()
    (cat / "recipes" / "ship_kit.json").write_text(
        json.dumps({"id": "ship_kit", "kind": "vehicle", "label": "Mine", "description": "x",
                    "steps": [{"role": "body", "select": {"part_class": "body"}}]}),
        encoding="utf-8",
    )
    recipes = load_recipes(cat)
    assert recipes["ship_kit"]["label"] == "Mine"
    assert recipes["ship_kit"]["source"] == "user"


def test_match_recipes():
    recipes = load_recipes(None)
    assert match_recipes(recipes, "a row of shops for main street in a small town")[0]["id"] == "main_street_row"
    assert match_recipes(recipes, "build me a fighter space ship")[0]["id"] == "ship_kit"
    assert match_recipes(recipes, "six storey apartment building")[0]["id"] == "apartment_block"
    assert match_recipes(recipes, "station corridor and bridge interior")[0]["id"] == "station_interior"
    assert match_recipes(recipes, "zzqx") == []
