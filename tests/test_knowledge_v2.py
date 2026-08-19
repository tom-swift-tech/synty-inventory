"""Phase 3 catalog-v2 semantics: sci-fi ship/station kit vocabulary, City
exterior building-kit families, and non-placeable data rules in
``synty_inventory.knowledge``.

Every stem here is a fixture id, never a real scanned pack -- see the
brief's "read-only inspection ... is fine" note; these are just the
documented prefix families, not a live scan.
"""

from synty_inventory.knowledge import bld_exterior_family, infer, is_interior_bld
from synty_inventory.schema import (
    ATTACHMENTS,
    MODULE_ROLES,
    MOUNTS,
    PART_CLASSES,
    SEMANTIC_ROLES,
    TYPES,
)

# --- vehicle parts (SM_Veh_Part_*) ---------------------------------------------


def test_veh_part_body():
    rec = infer("SM_Veh_Part_Body_01")
    assert rec["type"] == "vehicle/part"
    assert rec["semantic_role"] == "vehicle_part"
    assert rec["part"]["class"] == "body"
    assert rec["part"]["symmetric"] is True
    assert rec["placement"]["mount"] == "socket"
    assert "ship_kit" in rec["placement"]["preferred_contexts"]


def test_veh_part_cockpit_mates_front():
    rec = infer("SM_Veh_Part_Cockpit_02")
    assert rec["part"]["class"] == "cockpit"
    assert rec["part"]["mates_axis"] == "+z"
    assert "front" in rec["description"].lower() or "+z" in rec["description"]


def test_veh_part_engine_mates_rear():
    rec = infer("SM_Veh_Part_Engine_01")
    assert rec["part"]["class"] == "engine"
    assert rec["part"]["mates_axis"] == "-z"
    assert rec["dimensions_hint"] == [1.5, 1.5, 3.0]


def test_veh_part_wing_symmetric_pair():
    rec = infer("SM_Veh_Part_Wing_01")
    assert rec["part"]["class"] == "wing"
    assert rec["part"]["symmetric"] is True
    assert "mirror" in rec["description"].lower() or "pair" in rec["description"].lower()


def test_veh_part_landing_gear_underside():
    rec = infer("SM_Veh_Part_LandingGear_Flat_01")
    assert rec["part"]["class"] == "landing_gear"
    assert rec["part"]["mates_axis"] == "-y"


def test_veh_part_misc_is_greeble():
    rec = infer("SM_Veh_Part_Misc_017")
    assert rec["part"]["class"] == "greeble"
    assert rec["semantic_detail"] == "greeble"


# --- spacecraft (SM_Ship_*) -----------------------------------------------------


def test_ship_fighter():
    rec = infer("SM_Ship_Fighter_01")
    assert rec["type"] == "vehicle/spacecraft"
    assert rec["semantic_role"] == "spacecraft"
    assert rec["part"]["size_class"] == "fighter"
    assert rec["dimensions_hint"] == [8.0, 3.0, 10.0]
    assert rec["placement"]["mount"] == "free"
    assert "not a hull part" in rec["description"].lower() or "not a part" in rec["description"].lower() or "spacecraft prefab" in rec["description"].lower()


def test_ship_stealth_is_fighter_class():
    assert infer("SM_Ship_Stealth_03")["part"]["size_class"] == "fighter"


def test_ship_massive_transport_is_transport_class():
    assert infer("SM_Ship_Massive_Transport_01")["part"]["size_class"] == "transport"


def test_ship_galactic_carrier_is_capital_class():
    rec = infer("SM_Ship_Galactic_Carrier_01")
    assert rec["part"]["size_class"] == "capital"
    assert rec["dimensions_hint"] == [60.0, 20.0, 120.0]


def test_ship_station_is_station_class():
    assert infer("SM_Ship_Station_04")["part"]["size_class"] == "station"


# --- Bld_* interior vs exterior decision function ------------------------------


def test_is_interior_bld_true_for_scifi_structural_tokens():
    assert is_interior_bld(["Wall"]) is True
    assert is_interior_bld(["Bridge", "Chair"]) is True
    assert is_interior_bld(["Base", "45", "Wall", "Door"]) is True


def test_is_interior_bld_false_for_city_exterior_family():
    # City's own Apartment_Door piece contains "Door" but is exterior.
    assert is_interior_bld(["Apartment", "Door"]) is False
    assert is_interior_bld(["Shop", "01"]) is False


def test_bld_exterior_family_matches_two_word_family():
    assert bld_exterior_family(["OfficeOld", "Large", "Base"]) == ("OfficeOld_Large", ["Base"])


def test_bld_exterior_family_none_for_scifi_stem():
    assert bld_exterior_family(["Wall"]) is None
    assert bld_exterior_family(["Bridge", "Ceiling"]) is None


# --- interior modules (sci-fi SM_Bld_*) -----------------------------------------


def test_bld_bridge_chair_is_misc_interior_module():
    rec = infer("SM_Bld_Bridge_Chair_01")
    assert rec["type"] == "building/interior_module"
    assert rec["semantic_role"] == "interior_module"
    assert rec["module"]["family"] == "Bridge"
    assert rec["module"]["role"] == "misc"


def test_bld_wall_is_interior_wall_module():
    rec = infer("SM_Bld_Wall_12")
    assert rec["module"]["family"] == "Interior"
    assert rec["module"]["role"] == "wall"
    assert rec["placement"]["mount"] == "module"


def test_bld_base_door_large_is_door_role():
    rec = infer("SM_Bld_Base_Door_Large_01")
    assert rec["module"]["family"] == "Base"
    assert rec["module"]["role"] == "door"


def test_interior_module_description_has_no_street_face():
    rec = infer("SM_Bld_Ceiling_04")
    assert "street face" not in rec["description"].lower()
    assert "street face" not in rec["ai_notes"].lower()


# --- exterior City building-kit modules -----------------------------------------


def test_bld_apartment_roof_corner_has_corner_footprint():
    rec = infer("SM_Bld_Apartment_Roof_Corner_01")
    assert rec["type"] == "building/module"
    assert rec["semantic_role"] == "building_module"
    assert rec["module"]["role"] == "roof"
    assert rec["module"]["footprint_class"] == "corner"


def test_bld_shop_bare_is_hero_shell():
    rec = infer("SM_Bld_Shop_01")
    assert rec["type"] == "building/shell"
    assert rec["semantic_role"] == "building_shell"
    assert rec["module"]["role"] == "hero"
    assert rec["semantic_detail"] == "shop"


def test_bld_apartment_stack_is_shell_role():
    rec = infer("SM_Bld_Apartment_Stack_01")
    assert rec["module"]["role"] == "shell"


def test_bld_apartment_stairs_corner():
    rec = infer("SM_Bld_Apartment_Stairs_Corner_01")
    assert rec["module"]["role"] == "stairs"
    assert rec["module"]["footprint_class"] == "corner"


def test_bld_officeoctagon_floor_stacks_on_base():
    rec = infer("SM_Bld_OfficeOctagon_Floor_01")
    assert rec["module"]["role"] == "floor"
    assert rec["module"]["stackable_on"] == ["base", "floor"]


def test_bld_fireescape_spire_roofaccess_cover_are_building_modules():
    for stem, role in (
        ("SM_Bld_FireEscape_01", "misc"),
        ("SM_Bld_Spire_01", "spire"),
        ("SM_Bld_Roof_Access_01", "roof"),
        ("SM_Bld_Cover_01", "cover"),
    ):
        rec = infer(stem)
        assert rec["type"] == "building/module", stem
        assert rec["module"]["role"] == role, stem


# --- environment (SM_Env_*) ------------------------------------------------------


def test_env_asteroid_and_astroid_spelling():
    assert infer("SM_Env_Asteroid_01")["semantic_detail"] == "asteroid"
    assert infer("SM_Env_Astroid_02")["semantic_detail"] == "asteroid"


def test_env_planet_and_debris_and_rubble():
    assert infer("SM_Env_Planet_01")["semantic_role"] == "celestial"
    assert infer("SM_Env_Debris_01")["semantic_role"] == "debris"
    assert infer("SM_Env_Rubble_01")["semantic_role"] == "debris"


def test_env_scifi_does_not_hijack_city_bridge_env():
    # POLYGON_City has SM_Env_Bridge_* (a road bridge), unrelated to space debris.
    rec = infer("SM_Env_Bridge_Pillar_01")
    assert rec["semantic_role"] != "celestial"
    assert rec["semantic_role"] != "debris"


# --- specific props ---------------------------------------------------------------


def test_prop_turret_is_weapon():
    rec = infer("SM_Prop_Turret_Heavy_01")
    assert rec["type"] == "weapon"
    assert rec["semantic_detail"] == "turret"
    assert rec["placement"]["mount"] == "socket"


def test_prop_greeble_and_detail_are_facade_dressing():
    for stem in ("SM_Prop_Greeble_03", "SM_Prop_Detail_11"):
        rec = infer(stem)
        assert rec["type"] == "prop"
        assert rec["semantic_role"] == "facade_dressing"


def test_prop_crate_is_container():
    rec = infer("SM_Prop_Crate_02")
    assert rec["semantic_role"] == "container"


def test_prop_light_mounts_on_ceiling():
    rec = infer("SM_Prop_Light_04")
    assert rec["placement"]["mount"] == "ceiling"


# --- character attach / non-placeable pieces --------------------------------------


def test_chr_attach_is_non_placeable_character_part():
    rec = infer("SM_Chr_Attach_Head_01")
    assert rec["type"] == "character/part"
    assert rec["semantic_role"] == "character_part"


def test_hud_and_icon_are_ui():
    for stem in ("SM_Hud_Reticle_01", "SM_Icon_Ammo_04"):
        rec = infer(stem)
        assert rec["type"] == "ui/icon"
        assert rec["semantic_role"] == "ui_element"


def test_signborder_number_is_wayfinding():
    rec = infer("SM_SignBorder_Number_03")
    assert rec["type"] == "prop/signage"
    assert rec["semantic_role"] == "wayfinding"
    assert rec["semantic_detail"] == "number"


# --- non-placeable packs (animation / character rig / ui / skybox / fx) -----------


def test_animation_clip_prefix():
    for stem in ("A_Crouch_BckStrafeBL_Femn", "Anim_Salute_01", "ANIM_Wave_01"):
        rec = infer(stem)
        assert rec["type"] == "animation"
        assert rec["semantic_role"] == "animation_clip"


def test_sk_part_is_character_part_not_placeable():
    rec = infer("SK_HUMN_BASE_01_01HEAD_HU01")
    assert rec["type"] == "character/part"
    assert rec["semantic_role"] == "character_part"


def test_sk_bare_stem_is_whole_skeleton_and_placeable():
    rec = infer("SK_HUMN_BASE_01")
    assert rec["type"] == "character/skeleton"
    assert rec.get("placeable") is True


def test_generic_ui_prefixes():
    for stem in ("T_Crosshair_01", "UI_Panel_Main", "Icon_Ammo_02", "HUD_Compass_01"):
        rec = infer(stem)
        assert rec["type"] == "ui/icon"


def test_skybox_prefixes():
    for stem in ("SkyDome", "Skybox_Day_01", "M_Sky_Night"):
        rec = infer(stem)
        assert rec["type"] == "skybox"


def test_fx_and_ps_prefixes():
    for stem in ("FX_Explosion_01", "PS_Sparkle_01"):
        rec = infer(stem)
        assert rec["type"] == "fx"
        assert rec["semantic_role"] == "visual_effect"


# --- curated quality bar -----------------------------------------------------------


def test_curated_police_is_channel_letters_not_a_badge():
    rec = infer("SM_Prop_Sign_Police_01")
    assert rec["name"] == "Police Channel Letters"
    assert "badge" not in rec["description"].lower() or "no backing board" in rec["description"].lower()
    assert rec["semantic_role"] == "building_identity"
    assert rec["semantic_detail"] == "police_station"
    assert "channel_letters" in rec["tags"]


def test_curated_barber_role_and_detail():
    rec = infer("SM_Prop_Sign_Barber_01")
    assert rec["semantic_role"] == "building_identity"
    assert rec["semantic_detail"] == "barber_shop"


# --- enum-membership sweep over representative stems from this brief --------------

REPRESENTATIVE_STEMS = [
    # vehicle parts
    "SM_Veh_Part_Body_01", "SM_Veh_Part_Cockpit_01", "SM_Veh_Part_Engine_02",
    "SM_Veh_Part_Wing_03", "SM_Veh_Part_LandingGear_Wheel_01", "SM_Veh_Part_Misc_005",
    # spacecraft
    "SM_Ship_Fighter_01", "SM_Ship_Fighter_Heavy_02", "SM_Ship_Bomber_01",
    "SM_Ship_Stealth_01", "SM_Ship_Cruiser_01", "SM_Ship_Transport_01",
    "SM_Ship_Massive_Transport_01", "SM_Ship_Galactic_Carrier_01",
    "SM_Ship_Galactic_Carrier_Armor_01", "SM_Ship_Colossal_01", "SM_Ship_Station_01",
    # interior sci-fi buildings
    "SM_Bld_Wall_01", "SM_Bld_Floor_02", "SM_Bld_Ceiling_01", "SM_Bld_Bridge_01",
    "SM_Bld_Bridge_Ceiling_01", "SM_Bld_Bridge_Chair_01", "SM_Bld_Crew_01",
    "SM_Bld_Corridor_01", "SM_Bld_Hydroponics_01", "SM_Bld_Base_45_Floor_01",
    "SM_Bld_Base_45_Wall_Door_01", "SM_Bld_Base_Ceiling_Half_01",
    "SM_Bld_Base_Door_Large_01", "SM_Bld_Base_Floor_Combined_01",
    # City exterior buildings
    "SM_Bld_Apartment_01", "SM_Bld_Apartment_Corner_01", "SM_Bld_Apartment_Door_01",
    "SM_Bld_Apartment_Door_Corner_01", "SM_Bld_Apartment_Roof_01",
    "SM_Bld_Apartment_Roof_Corner_01", "SM_Bld_Apartment_Stack_01",
    "SM_Bld_Apartment_Stairs_01", "SM_Bld_Apartment_Stairs_Corner_01",
    "SM_Bld_Apartment_Stairs_Planter_01", "SM_Bld_OfficeOld_Large_01",
    "SM_Bld_OfficeOld_Large_Base_01", "SM_Bld_OfficeOctagon_01",
    "SM_Bld_OfficeOctagon_Floor_01", "SM_Bld_OfficeRound_01", "SM_Bld_OfficeSquare_01",
    "SM_Bld_Shop_01", "SM_Bld_Shop_Corner_01", "SM_Bld_Shop_Cover_01",
    "SM_Bld_Station_01", "SM_Bld_CityHall_01", "SM_Bld_FireEscape_01",
    "SM_Bld_Spire_01", "SM_Bld_Roof_Access_01", "SM_Bld_Cover_01",
    # environment
    "SM_Env_Asteroid_01", "SM_Env_Astroid_02", "SM_Env_Planet_01",
    "SM_Env_Debris_01", "SM_Env_Rubble_01",
    # props
    "SM_Prop_Turret_01", "SM_Prop_Greeble_01", "SM_Prop_Detail_01",
    "SM_Prop_Screen_01", "SM_Prop_ControlPanel_01", "SM_Prop_Buttons_01",
    "SM_Prop_Light_01", "SM_Prop_Wires_01", "SM_Prop_Hose_01", "SM_Prop_Bed_01",
    "SM_Prop_Crate_01", "SM_Prop_Medical_01", "SM_Prop_FoodPacket_01",
    # character / ui / signage
    "SM_Chr_Attach_Head_01", "SM_Hud_Reticle_01", "SM_Icon_Ammo_01",
    "SM_SignBorder_Number_01",
    # non-placeable
    "A_Idle_01", "SK_HUMN_BASE_01_01HEAD_HU01", "SK_HUMN_BASE_01",
    "T_Crosshair_01", "SkyDome", "FX_Explosion_01",
    # curated
    "SM_Prop_Sign_Police_01", "SM_Prop_Sign_Barber_01",
]


def test_all_representative_stems_use_valid_enums():
    assert len(REPRESENTATIVE_STEMS) >= 60
    for stem in REPRESENTATIVE_STEMS:
        rec = infer(stem)
        assert rec["type"] in TYPES, (stem, rec["type"])
        assert rec["semantic_role"] in SEMANTIC_ROLES, (stem, rec["semantic_role"])
        placement = rec["placement"]
        assert placement["mount"] in MOUNTS, (stem, placement["mount"])
        assert placement["attachment"] in ATTACHMENTS, (stem, placement["attachment"])
        module = rec.get("module")
        if module and module.get("role") is not None:
            assert module["role"] in MODULE_ROLES, (stem, module["role"])
        part = rec.get("part")
        if part and part.get("class") is not None:
            assert part["class"] in PART_CLASSES, (stem, part["class"])
