"""Grok 4.6 vision CLI: enum lock, merge-not-replace, stills, City gold."""

from __future__ import annotations

import json
from pathlib import Path

from synty_inventory.schema import MODULE_ROLES, SEMANTIC_ROLES, TYPES
from synty_inventory.sources.threejs_v2 import apply_threejs_overlay
from synty_inventory.vision import (
    adopt_mount,
    compare_gold,
    load_gold,
    merge_vision_entry,
    prose_only,
    resolve_stills,
    sanitize_draft,
    vision_pack,
)
from synty_inventory.vlm import HOSTED_DEFAULT_MODEL


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _pack(tmp_path: Path, pack_id: str, models: list[str]) -> Path:
    pack_dir = tmp_path / pack_id
    _write(pack_dir / "manifest.json", {"models": models})
    for rel in models:
        glb = pack_dir / rel
        glb.parent.mkdir(parents=True, exist_ok=True)
        glb.write_bytes(b"fake-glb")
    return pack_dir


def _query(draft_by_stem: dict):
    def query(images, prompt):
        stem = Path(images[0]).stem
        if stem not in draft_by_stem:
            # contact sheet named by id; per-view stills live in a stem folder
            stem = Path(images[0]).parent.name
        return draft_by_stem.get(stem)

    return query


def test_gold_file_has_twenty_unique_city_ids():
    gold = load_gold()
    assert gold["pack_id"] == "POLYGON_City"
    ids = [a["id"] for a in gold["assets"]]
    assert len(ids) == 20
    assert len(set(ids)) == 20
    for row in gold["assets"]:
        t = row.get("type")
        for val in t if isinstance(t, list) else [t]:
            if val:
                assert val in TYPES or val in {
                    "building/module",
                    "building/shell",
                    "prop",
                    "prop/signage",
                    "environment/city_layout",
                }
        role = row.get("semantic_role")
        for val in role if isinstance(role, list) else [role]:
            if val:
                assert val in SEMANTIC_ROLES
        mrole = row.get("module_role")
        for val in mrole if isinstance(mrole, list) else [mrole]:
            if val:
                assert val in MODULE_ROLES


def test_sanitize_drops_contact_sockets_and_mech():
    out = sanitize_draft(
        "SM_Prop_Sign_Police_01",
        {
            "name": "POLICE Letters",
            "description": "Extruded white POLICE channel letters for a station facade.",
            "type": "prop/signage",
            "semantic_role": "building_identity",
            "mount": "wall",
            "placement": {"contact": {"axis": "-z", "position": [0, 0, 0], "normal": [0, 0, -1]}},
            "part": {"class": "engine", "sockets": [{"role": "rear"}]},
            "mech": {"skeleton": ["Hips"]},
        },
    )
    assert "contact" not in out
    assert "part" not in out
    assert "mech" not in out
    assert "placement" not in out
    assert out["mount"] == "wall"
    assert out["type"] == "prop/signage"


def test_sanitize_is_prose_only_for_mech_and_ship_parts():
    assert prose_only("SM_Mech_Head_01_Armor_Helmet_01") is True
    assert prose_only("SM_Veh_Part_Engine_01") is True
    assert prose_only("SM_Prop_Crate_01") is False
    out = sanitize_draft(
        "SM_Veh_Part_Engine_01",
        {
            "name": "Engine",
            "description": "A low-poly spacecraft engine nozzle with heat-stained metal.",
            "type": "vehicle",
            "semantic_role": "vehicle",
            "mount": "socket",
            "tags": ["engine"],
        },
    )
    assert out["name"] == "Engine"
    assert "type" not in out
    assert "mount" not in out
    assert "semantic_role" not in out


def test_sanitize_drops_type_when_existing_has_part_class():
    out = sanitize_draft(
        "SM_Ship_Body_01",
        {"name": "Hull", "description": "A spacecraft hull with a cockpit blister on top.", "type": "vehicle"},
        existing={"part": {"class": "body"}},
    )
    assert "type" not in out


def test_sanitize_enum_locks_invalid_role_and_mount():
    out = sanitize_draft(
        "SM_Prop_Crate_01",
        {
            "name": "Crate",
            "description": "A wooden crate bound with metal straps on all sides.",
            "semantic_role": "not_a_real_role",
            "mount": "floating",
            "type": "spaceship",
        },
    )
    assert "semantic_role" not in out
    assert "mount" not in out
    assert "type" not in out


def test_sanitize_locks_scifi_interior_kit_type():
    chair = sanitize_draft(
        "SM_Bld_Bridge_Chair_Captain_01",
        {
            "name": "Captain Chair",
            "description": "A sci-fi bridge captain chair with a high back and arm consoles.",
            "type": "prop",
            "semantic_role": "interior_prop",
            "module_role": "hero",
        },
    )
    assert chair["type"] == "building/interior_module"
    assert chair["semantic_role"] == "interior_module"
    assert "module_role" not in chair
    corridor = sanitize_draft(
        "SM_Bld_Corridor_Single_Arch_01",
        {
            "name": "Corridor Arch",
            "description": "A single sci-fi corridor arch with ribbed metal plating.",
            "type": "building/module",
            "semantic_role": "building_module",
            "module_role": "corridor",
        },
    )
    assert corridor["type"] == "building/interior_module"
    assert corridor["semantic_role"] == "interior_module"
    assert corridor["module_role"] == "corridor"


def test_sanitize_maps_stills_role_aliases():
    out = sanitize_draft(
        "SM_Bld_Shop_Cover_01",
        {
            "name": "Shop Canopy",
            "description": "A slatted grey shop canopy that sits on a storefront eave.",
            "type": "prop",
            "semantic_role": "shop_canopy",
            "mount": "wall",
        },
    )
    assert out["type"] == "prop"
    assert out["semantic_role"] == "facade_dressing"
    assert out["semantic_detail"] == "shop_canopy"


def test_roof_mount_blocked_on_wall_sign_allowed_on_billboard():
    assert adopt_mount("SM_Prop_Sign_Police_01", "roof", "wall") is None
    assert adopt_mount("SM_Prop_Billboard_01", "roof", "ground") == "roof"
    assert adopt_mount("SM_Prop_Sign_Police_01", "ground", "wall") is None
    assert adopt_mount("SM_Prop_Sign_Police_01", "wall", None) == "wall"
    assert adopt_mount("SM_Bld_Apartment_Roof_01", "roof", None) is None
    assert adopt_mount("SM_Bld_Cover_01", "roof", None) == "roof"
    assert adopt_mount("SM_Bld_Spire_01", "roof", None) == "roof"


def test_sanitize_aliases_kit_mount_and_attachment():
    out = sanitize_draft(
        "SM_Bld_Apartment_01",
        {
            "name": "Window Bay",
            "description": "A one-storey pink brick three-window apartment bay.",
            "type": "building/module",
            "semantic_role": "building_module",
            "module_role": "floor",
            "mount": "module",
            "attachment": "origin",
        },
    )
    assert out["mount"] == "ground"
    assert out["attachment"] == "bottom"
    roof = sanitize_draft(
        "SM_Bld_Apartment_Roof_01",
        {
            "name": "Roof Slab",
            "description": "A thin grey apartment roof slab with a cream soffit.",
            "type": "building/module",
            "semantic_role": "building_module",
            "module_role": "roof",
            "mount": "roof",
            "attachment": "base_to_roof",
        },
    )
    assert roof["mount"] == "ground"
    assert roof["attachment"] == "bottom"
    door = sanitize_draft(
        "SM_Bld_Apartment_Door_01",
        {
            "name": "Door Bay",
            "description": "A one-storey apartment entrance module with a central door.",
            "type": "building/module",
            "semantic_role": "building_module",
            "module_role": "door",
            "mount": "ground",
            "attachment": "base_to_ground",
        },
    )
    assert door["attachment"] == "bottom"


def test_sanitize_city_layout_type_and_shell_hero_and_canopy_defaults():
    path = sanitize_draft(
        "SM_Env_GrassPath_Straight_01",
        {
            "name": "Grass Path",
            "description": "A straight park path tile with grass banks on both sides.",
            "type": "environment",
            "semantic_role": "ground_surface",
            "semantic_detail": "park_path_tile",
            "mount": "ground",
        },
    )
    assert path["type"] == "environment/city_layout"
    hall = sanitize_draft(
        "SM_Bld_CityHall_01",
        {
            "name": "City Hall",
            "description": "A complete two-storey neoclassical city hall with a columned portico.",
            "type": "building/shell",
            "semantic_role": "building_shell",
            "mount": "ground",
        },
    )
    assert hall["module_role"] == "hero"
    canopy = sanitize_draft(
        "SM_Bld_Shop_Cover_01",
        {
            "name": "Shop Canopy",
            "description": "A slatted grey shop canopy that sits on a storefront eave.",
            "type": "prop",
            "semantic_role": "facade_dressing",
        },
    )
    assert canopy["mount"] == "wall"
    assert canopy["attachment"] == "back_side"


def test_sanitize_filename_kit_slot_demotes_false_hero():
    corner = sanitize_draft(
        "SM_Bld_Apartment_Corner_01",
        {
            "name": "Apartment corner",
            "description": "A one-storey pink apartment bay with three sash windows and a flat top.",
            "type": "building/shell",
            "semantic_role": "building_shell",
            "module_role": "hero",
            "mount": "ground",
        },
    )
    assert corner["type"] == "building/module"
    assert corner["semantic_role"] == "building_module"
    assert corner["module_role"] == "corner"
    door = sanitize_draft(
        "SM_Bld_Apartment_Door_01",
        {
            "name": "Apartment door",
            "description": "A compact one-storey pink brick apartment bay with a central double door.",
            "type": "building/shell",
            "semantic_role": "building_shell",
            "module_role": "hero",
            "mount": "ground",
        },
    )
    assert door["type"] == "building/module"
    assert door["module_role"] == "door"
    shop_corner = sanitize_draft(
        "SM_Bld_Shop_Corner_01",
        {
            "name": "Corner shop",
            "description": "A one-storey corner shop shell with a salmon awning and glass storefront.",
            "type": "building/shell",
            "semantic_role": "building_shell",
            "module_role": "hero",
            "mount": "ground",
        },
    )
    assert shop_corner["type"] == "building/shell"
    assert shop_corner["module_role"] == "corner"
    shop = sanitize_draft(
        "SM_Bld_Shop_01",
        {
            "name": "Shop",
            "description": "A one-storey glass shop with a flat roof and blank side walls.",
            "type": "building/shell",
            "semantic_role": "building_shell",
            "module_role": "hero",
            "mount": "ground",
        },
    )
    assert shop["type"] == "building/shell"
    assert shop["module_role"] == "hero"


def test_sanitize_strips_base_kit_atlas_bleed_tags():
    out = sanitize_draft(
        "SM_Bld_Base_45_Wall_Door_01",
        {
            "name": "Door Wall",
            "description": "A one-storey grey concrete wall module with a rectangular open doorway.",
            "type": "building/module",
            "semantic_role": "building_module",
            "module_role": "door",
            "mount": "ground",
            "tags": ["door", "posters", "taxi", "police", "urban_signs", "advertising"],
        },
    )
    assert "posters" not in out["tags"]
    assert "taxi" not in out["tags"]
    assert "police" not in out["tags"]
    assert "door" in out["tags"]


def test_sanitize_promotes_bld_cover_not_shop_canopy():
    out = sanitize_draft(
        "SM_Bld_Cover_02",
        {
            "name": "low poly rock cover",
            "description": "A small faceted pink-terracotta cover block with a flat top and bottom.",
            "type": "prop",
            "semantic_role": "exterior_prop",
            "mount": "ground",
            "tags": ["rock", "terrain", "cover", "pink"],
        },
    )
    assert out["type"] == "building/module"
    assert out["semantic_role"] == "building_module"
    assert out["module_role"] == "roof"
    assert out["mount"] == "roof"
    assert "rock" not in out.get("tags", [])
    assert "cover" in out["tags"]
    assert "rock" in out.get("tags_remove", [])


def test_compare_gold_preferred_floors_list_is_a_value():
    gold = {"preferred_floors": [1], "mount": "wall"}
    assert compare_gold({"preferred_floors": [1], "mount": "wall"}, gold) == []
    bad = compare_gold({"preferred_floors": [1, 2], "mount": "wall"}, gold)
    assert any(m["field"] == "preferred_floors" for m in bad)


def test_compare_gold_skips_module_role_when_type_is_allowed_prop():
    gold = {
        "type": ["building/module", "prop"],
        "semantic_role": "facade_dressing",
        "module_role": ["stairs", "misc", "wall"],
        "mount": ["wall", "module"],
    }
    got = {
        "type": "prop",
        "semantic_role": "facade_dressing",
        "mount": "wall",
    }
    assert compare_gold(got, gold) == []
    missing = compare_gold(
        {"type": "building/module", "semantic_role": "facade_dressing", "mount": "wall"},
        gold,
    )
    assert any(m["field"] == "module_role" for m in missing)


def test_merge_unions_tags_and_keeps_unmentioned_fields():
    existing = {
        "id": "SM_Bld_Shop_Cover_01",
        "name": "Shop Cover",
        "type": "building/shell",
        "semantic_role": "building_shell",
        "tags": ["shop", "cover"],
        "placement": {"mount": "ground", "contact": {"axis": "-y", "position": [0, 0, 0], "normal": [0, -1, 0]}},
        "reviewed": False,
    }
    out = merge_vision_entry(
        existing,
        {
            "id": "SM_Bld_Shop_Cover_01",
            "name": "Slatted Shop Canopy",
            "description": "A low-poly slatted canopy for a shop front eave.",
            "type": "prop",
            "semantic_role": "facade_dressing",
            "tags": ["awning"],
            "tags_remove": ["building"],
            "mount": "wall",
        },
        "models/SM_Bld_Shop_Cover_01.glb",
    )
    assert out["type"] == "prop"
    assert out["name"] == "Slatted Shop Canopy"
    assert "shop" in out["tags"] and "awning" in out["tags"]
    assert "building" not in out["tags"]
    assert out["placement"]["mount"] == "wall"
    assert out["placement"]["contact"]["axis"] == "-y"
    assert out["reviewed"] is True


def test_merge_does_not_write_contact_from_draft():
    out = merge_vision_entry(
        {"id": "SM_X", "placement": {"mount": "ground"}},
        {"id": "SM_X", "mount": "wall", "contact": {"normal": [0, 0, -1]}},
    )
    assert "contact" not in out["placement"]


def test_compare_gold_apartment_floor_not_hero():
    gold = {
        "id": "SM_Bld_Apartment_01",
        "type": "building/module",
        "semantic_role": "building_module",
        "module_role": "floor",
        "mount": "ground",
    }
    bad = compare_gold(
        {"type": "building/shell", "semantic_role": "building_shell", "module_role": "hero", "mount": "ground"},
        gold,
    )
    fields = {m["field"] for m in bad}
    assert "type" in fields and "module_role" in fields
    good = compare_gold(
        {"type": "building/module", "semantic_role": "building_module", "module_role": "floor", "mount": "ground"},
        gold,
    )
    assert good == []


def test_resolve_stills_prefers_contact_sheet(tmp_path: Path):
    stills = tmp_path / "stills"
    sheet = stills / "POLYGON_City" / "SM_Prop_Sign_Police_01.png"
    sheet.parent.mkdir(parents=True)
    sheet.write_bytes(b"sheet")
    review = tmp_path / "threejs" / "POLYGON_City" / "_review_stills" / "SM_Prop_Sign_Police_01"
    review.mkdir(parents=True)
    (review / "front.png").write_bytes(b"front")
    found = resolve_stills(
        "POLYGON_City",
        "SM_Prop_Sign_Police_01",
        stills_root=stills,
        threejs_v2=tmp_path / "threejs",
    )
    assert found == [sheet]


def test_vision_pack_calibrate_does_not_write(tmp_path: Path):
    pack_dir = _pack(tmp_path, "POLYGON_City", ["models/SM_Bld_Apartment_01.glb"])
    stills = tmp_path / "stills" / "POLYGON_City"
    stills.mkdir(parents=True)
    (stills / "SM_Bld_Apartment_01.png").write_bytes(b"png")
    gold = {
        "pack_id": "POLYGON_City",
        "assets": [
            {
                "id": "SM_Bld_Apartment_01",
                "type": "building/module",
                "semantic_role": "building_module",
                "module_role": "floor",
                "mount": "ground",
            }
        ],
    }
    gold_path = tmp_path / "gold.json"
    gold_path.write_text(json.dumps(gold), encoding="utf-8")
    result = vision_pack(
        "POLYGON_City",
        threejs_v2_root=tmp_path,
        stills_root=tmp_path / "stills",
        calibrate=True,
        apply=True,  # must still refuse to write
        gold_path=gold_path,
        query_fn=_query(
            {
                "SM_Bld_Apartment_01": {
                    "name": "Window Bay",
                    "description": "A one-storey pink brick three-window apartment bay.",
                    "type": "building/module",
                    "semantic_role": "building_module",
                    "module_role": "floor",
                    "mount": "ground",
                    "attachment": "bottom",
                }
            }
        ),
    )
    assert result["ok"] is True
    assert result["gold_passed"] == ["SM_Bld_Apartment_01"]
    assert result["apply"] is False
    assert not (pack_dir / "catalog.json").is_file()


def test_vision_pack_writes_structure_merge(tmp_path: Path):
    pack_dir = _pack(tmp_path, "POLYGON_City", ["models/SM_Bld_Shop_Cover_01.glb"])
    _write(
        pack_dir / "catalog.json",
        {
            "pack_id": "POLYGON_City",
            "assets": [
                {
                    "id": "SM_Bld_Shop_Cover_01",
                    "name": "Shop Cover",
                    "type": "building/shell",
                    "semantic_role": "building_shell",
                    "tags": ["shop"],
                    "placement": {"mount": "ground"},
                    "reviewed": False,
                    "file": "models/SM_Bld_Shop_Cover_01.glb",
                }
            ],
        },
    )
    stills = tmp_path / "stills" / "POLYGON_City"
    stills.mkdir(parents=True)
    (stills / "SM_Bld_Shop_Cover_01.png").write_bytes(b"png")
    result = vision_pack(
        "POLYGON_City",
        threejs_v2_root=tmp_path,
        stills_root=tmp_path / "stills",
        apply=True,
        query_fn=_query(
            {
                "SM_Bld_Shop_Cover_01": {
                    "name": "Slatted Shop Canopy",
                    "description": "A grey slatted canopy that sits on a shop eave.",
                    "type": "prop",
                    "semantic_role": "facade_dressing",
                    "tags": ["awning"],
                    "mount": "wall",
                }
            }
        ),
    )
    assert result["ok"] is True
    entry = json.loads((pack_dir / "catalog.json").read_text(encoding="utf-8"))["assets"][0]
    assert entry["type"] == "prop"
    assert entry["semantic_role"] == "facade_dressing"
    assert entry["placement"]["mount"] == "wall"
    assert "shop" in entry["tags"] and "awning" in entry["tags"]
    assert entry["reviewed"] is True


def test_overlay_uses_explicit_module_role():
    from synty_inventory.merge import stamp_auto
    from synty_inventory.schema import empty_placement

    asset = stamp_auto(
        {
            "id": "SM_Bld_Apartment_01",
            "name": "Apartment",
            "type": "building/shell",
            "kind": "mesh",
            "placeable": True,
            "category": [],
            "tags": [],
            "description": "",
            "semantic_role": None,
            "semantic_detail": None,
            "placement": empty_placement(),
            "module": {"family": "Apartment", "role": "hero"},
            "ai_notes": "",
            "files": {"glb": None},
        }
    )
    apply_threejs_overlay(
        asset,
        {
            "reviewed": True,
            "type": "building/module",
            "semantic_role": "building_module",
            "module_role": "floor",
        },
        None,
    )
    assert asset["type"] == "building/module"
    assert asset["module"]["role"] == "floor"


def test_cli_vision_parser_has_calibrate():
    from synty_inventory.cli import build_parser

    args = build_parser().parse_args(["vision", "--calibrate", "--pack", "POLYGON_City"])
    assert args.cmd == "vision"
    assert args.calibrate is True
    assert args.pack == "POLYGON_City"


def test_cli_vision_calibrate_injected(tmp_path: Path, monkeypatch, capsys):
    from synty_inventory.cli import main
    from synty_inventory.paths import CONFIG_KEYS

    monkeypatch.delenv("SYNTI_CONFIG", raising=False)
    for env in CONFIG_KEYS.values():
        monkeypatch.delenv(env, raising=False)

    stills = tmp_path / "stills" / "POLYGON_City"
    stills.mkdir(parents=True)
    (stills / "SM_Bld_Apartment_01.png").write_bytes(b"png")
    gold = {
        "pack_id": "POLYGON_City",
        "assets": [
            {
                "id": "SM_Bld_Apartment_01",
                "type": "building/module",
                "semantic_role": "building_module",
                "module_role": "floor",
                "mount": "ground",
            }
        ],
    }
    gold_path = tmp_path / "gold.json"
    gold_path.write_text(json.dumps(gold), encoding="utf-8")
    threejs = tmp_path / "threejs"
    _pack(threejs, "POLYGON_City", ["models/SM_Bld_Apartment_01.glb"])

    import synty_inventory.cli as cli_mod
    import synty_inventory.vision as vision_mod

    def fake_pack(*args, **kwargs):
        kwargs["query_fn"] = _query(
            {
                "SM_Bld_Apartment_01": {
                    "name": "Bay",
                    "description": "A one-storey three-window apartment bay in pink brick.",
                    "type": "building/module",
                    "semantic_role": "building_module",
                    "module_role": "floor",
                    "mount": "ground",
                }
            }
        )
        return vision_mod.vision_pack(*args, **kwargs)

    monkeypatch.setattr(cli_mod, "vision_pack", fake_pack)

    unity = tmp_path / "unity"
    extracted = tmp_path / "extracted"
    catalogs = tmp_path / "catalogs"
    for p in (unity, extracted, catalogs):
        p.mkdir()
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "\n".join(
            [
                f"unity_root: {str(unity).replace(chr(92), '/')}",
                f"extracted_root: {str(extracted).replace(chr(92), '/')}",
                f"catalogs: {str(catalogs).replace(chr(92), '/')}",
                f"threejs_v2: {str(threejs).replace(chr(92), '/')}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    code = main(
        [
            "--config",
            str(cfg),
            "vision",
            "--calibrate",
            "--gold",
            str(gold_path),
            "--stills-root",
            str(tmp_path / "stills"),
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["calibrate"] is True
    assert payload["gold_passed"] == ["SM_Bld_Apartment_01"]


def test_hosted_default_model_is_grok_46():
    assert HOSTED_DEFAULT_MODEL == "grok-4.6"
