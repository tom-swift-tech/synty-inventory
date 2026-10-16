"""Synthetic fixture catalogs for the weapon directory tests (spec 4.8). No Synty content: every id, path and
label below is invented. The labels in this file are the single source of truth for ``expected.json``; the
committed ``catalogs/*.json`` and ``expected.json`` are the output of ``python make_catalogs.py`` (a test
regenerates them and fails if the committed copies drift).

Labels are written as LITERALS (archetype, hold_class, genre, first-match rule), never derived from the rules
file or from ``synty_inventory.weapons`` constants, so the tests cannot be loosened by changing the code.

Packs: FAKE_Modern (military/modern), FAKE_Fantasy (fantasy/medieval), FAKE_SciFi (scifi_frontier/far_future),
FAKE_Mech (mech-scale flag), FAKE_Generic (absent from pack_settings: genre falls back to the archetype table).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from synty_inventory import schema as S  # noqa: E402  (fixtures are valid v2 catalog assets)

SCANNED_AT = "2026-01-01T00:00:00+00:00"
PACKS = ("FAKE_Fantasy", "FAKE_Generic", "FAKE_Mech", "FAKE_Modern", "FAKE_SciFi")
PACK_SETTINGS = {  # FAKE_Generic is deliberately absent (AC5)
    "FAKE_Modern": {"setting": "military", "era": "modern"},
    "FAKE_Fantasy": {"setting": "fantasy", "era": "medieval"},
    "FAKE_SciFi": {"setting": "scifi_frontier", "era": "far_future"},
    "FAKE_Mech": {"setting": "scifi_city", "era": "far_future"},
}
PACK_GENRE = {"FAKE_Modern": "modern", "FAKE_Fantasy": "fantasy", "FAKE_SciFi": "scifi", "FAKE_Mech": "scifi"}

# literal copies of the spec tables (3.4.2): archetype -> kind, archetype -> default hold_class
KIND = {
    **dict.fromkeys(["pistol", "revolver", "smg", "rifle", "shotgun", "sniper", "lmg", "heavy_gun", "launcher",
                     "flamethrower", "bow", "crossbow", "utility_gun", "turret", "cannon", "siege_engine", "mortar"],
                    "ranged"),
    **dict.fromkeys(["knife", "sword", "axe", "mace", "hammer", "club", "spear", "polearm", "staff", "wand", "whip",
                     "fist_weapon", "tool"], "melee"),
    **dict.fromkeys(["grenade", "bomb", "mine", "throwing_blade"], "thrown"),
    "shield": "shield",
    "unknown": None,
}
HOLD = {
    **dict.fromkeys(["pistol", "revolver", "utility_gun"], "one_hand"),
    **dict.fromkeys(["smg", "rifle", "shotgun", "sniper", "lmg", "heavy_gun", "launcher", "flamethrower"], "long_gun"),
    **dict.fromkeys(["knife", "sword", "axe", "mace", "whip", "wand", "tool", "fist_weapon"], "melee_one"),
    **dict.fromkeys(["spear", "polearm", "staff"], "melee_two"),
    **dict.fromkeys(["club", "hammer"], "melee_bat"),
    **dict.fromkeys(["grenade", "bomb", "mine", "throwing_blade"], "thrown"),
    "bow": "bow", "crossbow": "crossbow", "shield": "shield",
    **dict.fromkeys(["turret", "cannon", "siege_engine", "mortar", "unknown"], "none"),
}

ASSETS: dict[str, list[dict]] = {p: [] for p in PACKS}
WEAPONS: dict[str, dict] = {}  # id -> expected record labels
TRAPS: dict[str, dict] = {}  # id -> {reason, entry}
NOT_CANDIDATES: list[str] = []


def _asset(pack: str, aid: str, *, kind="mesh", typ="weapon", role="weapon", placeable=True, gear_kind="weapon",
           two=None, glb: str | None = "own", prefab_only=False) -> dict:
    files = S.empty_files()
    files["unity_prefab"] = f"Prefabs/{aid}.prefab"
    if not prefab_only:
        files["unity_mesh"] = f"Meshes/{aid}.fbx"
        files["glb"] = f"glb/{pack}/{aid}.glb" if glb == "own" else glb
    files["glb_node"] = None
    gear = S.empty_gear()
    gear["kind"], gear["twoHanded"] = gear_kind, two
    return {
        "id": aid, "name": aid.replace("_", " "), "kind": kind, "placeable": placeable, "type": typ,
        "category": [], "tags": [], "description": "", "semantic_role": role, "semantic_detail": "",
        "placement": S.empty_placement(), "bounds": None, "dimensions": S.dimensions_from_bounds(None),
        "files": files, "paths": S.paths_from_files(files), "thumbnail": None, "ai_notes": "", "gear": gear,
    }


def _label(pack, aid, rule, role, archetype, *, hold=None, kind="auto", genre=None, source="catalog", flags=(),
           component=None, carrier=None, ammo=None, dup_of=None):
    wid = f"{pack}/{aid}"
    assert wid not in WEAPONS and wid not in TRAPS, wid
    WEAPONS[wid] = {
        "role": role,
        "kind": KIND[archetype] if kind == "auto" and role in ("whole", "emplaced") else (None if kind == "auto" else kind),
        "archetype": archetype,
        "hold_class": hold if hold is not None else (HOLD[archetype] if role == "whole" else "none"),
        "genre": genre or PACK_GENRE[pack],
        "rule": rule,
        "source": source,
        "flags": sorted(flags),
        "component": component, "carrier": carrier, "ammo": ammo, "duplicate_of": dup_of,
    }


def wep(pack, aid, rule, archetype, *, two=None, hold=None, genre=None, flags=(), kind_override="auto", **asset_kw):
    ASSETS[pack].append(_asset(pack, aid, two=two, **asset_kw))
    _label(pack, aid, rule, "whole", archetype, hold=hold, genre=genre, flags=flags, kind=kind_override)


def tok(pack, aid, rule, archetype, *, role="whole", genre=None, typ="prop", sem="interior_prop", **kw):
    """name_token candidate: no catalog weapon signal."""
    ASSETS[pack].append(_asset(pack, aid, typ=typ, role=sem, gear_kind=None))
    _label(pack, aid, rule, role, archetype, genre=genre, source="name_token", flags=["token_candidate"], **kw)


def part(pack, aid, rule, slot, **kw):
    ASSETS[pack].append(_asset(pack, aid))
    _label(pack, aid, rule, "part", "unknown", component={"slot": slot, "fits": None}, **kw)


def ammo(pack, aid, rule, projectile, **kw):
    ASSETS[pack].append(_asset(pack, aid))
    _label(pack, aid, rule, "ammo", "unknown", ammo={"projectile": projectile}, **kw)


def carrier(pack, aid, rule, kind, **kw):
    ASSETS[pack].append(_asset(pack, aid))
    _label(pack, aid, rule, "carrier", "unknown", carrier={"kind": kind}, **kw)


def emplaced(pack, aid, rule, archetype, **kw):
    ASSETS[pack].append(_asset(pack, aid))
    _label(pack, aid, rule, "emplaced", archetype, **kw)


def trap(pack, aid, reason, entry, **asset_kw):
    ASSETS[pack].append(_asset(pack, aid, **asset_kw))
    TRAPS[f"{pack}/{aid}"] = {"reason": reason, "entry": entry}


def plain(pack, aid, *, kind="mesh", typ="prop", role="interior_prop", placeable=True):
    ASSETS[pack].append(_asset(pack, aid, kind=kind, typ=typ, role=role, placeable=placeable, gear_kind=None))
    NOT_CANDIDATES.append(f"{pack}/{aid}")


M, F, X, G, K = "FAKE_Modern", "FAKE_Fantasy", "FAKE_SciFi", "FAKE_Generic", "FAKE_Mech"

# ---------------------------------------------------------------- five stems shared by three packs (AC7)
STEMS = (("SM_Wep_Pistol_01", "pistol", "pistol"), ("SM_Wep_Axe_01", "axe", "axe"), ("SM_Wep_Knife_01", "knife", "knife"),
         ("SM_Wep_Grenade_01", "grenade", "grenade"), ("SM_Wep_Shield_01", "shield", "shield"))
for _pack in (M, F, X):
    for _aid, _rule, _arch in STEMS:
        wep(_pack, _aid, _rule, _arch)

# ---------------------------------------------------------------- modern: ranged
wep(M, "SM_Wep_Pistol_Heavy_02", "pistol", "pistol")
wep(M, "SM_Wep_Handgun_03", "pistol", "pistol")  # alias handgun -> pistol
wep(M, "SM_Wep_Revolver_01", "revolver", "revolver")
wep(M, "SM_Wep_Revolver_02", "revolver", "revolver")
wep(M, "SM_Wep_SubMGun_01", "smg", "smg")  # alias submgun -> smg; twoHanded unknown -> long_gun
wep(M, "SM_Wep_SMG_02", "smg", "smg", two=False, hold="one_hand")  # explicit twoHanded false -> one_hand
wep(M, "SM_Wep_Rifle_Assault_01", "rifle", "rifle", two=True)
wep(M, "SM_Wep_Rifle_Assault_02", "rifle", "rifle")
wep(M, "SM_Wep_Carbine_01", "rifle", "rifle")
wep(M, "SM_Wep_Rifle_BoltAction_01", "rifle", "rifle")  # "bolt" is not ammo when action/rifle is present
wep(M, "SM_Wep_Shotgun_Pump_01", "shotgun", "shotgun")
wep(M, "SM_Wep_Shotgun_Sawn_02", "shotgun", "shotgun")
wep(M, "SM_Wep_Sniper_Rifle_01", "sniper", "sniper")  # sniper beats rifle (first match)
wep(M, "SM_Wep_Sniper_02", "sniper", "sniper")
wep(M, "SM_Wep_LMG_01", "lmg", "lmg")
wep(M, "SM_Wep_MachineGun_02", "lmg", "lmg")  # alias machinegun -> lmg
wep(M, "SM_Wep_Minigun_01", "heavy_gun", "heavy_gun")
wep(M, "SM_Wep_Gatling_02", "heavy_gun", "heavy_gun")
wep(M, "SM_Wep_RPG_01", "launcher", "launcher")
wep(M, "SM_Wep_Grenade_Launcher_02", "launcher", "launcher")  # launcher beats grenade
wep(M, "SM_Wep_Rocket_Launcher_03", "launcher", "launcher")  # launcher beats the rocket ammo rule
wep(M, "SM_Wep_Flamethrower_01", "flamethrower", "flamethrower")
wep(M, "SM_Wep_Flamethrower_02", "flamethrower", "flamethrower")
wep(M, "SM_Wep_Nail_Gun_01", "utility_gun", "utility_gun")  # Nail + Gun joins to the nailgun alias
wep(M, "SM_Wep_Flare_Gun_02", "utility_gun", "utility_gun")

# modern: gun parts
part(M, "SM_Wep_Rifle_Scope_01", "part_optic", "optic")
part(M, "SM_Wep_Sniper_Scope_02", "part_optic", "optic")  # a part wins over the host gun's name
part(M, "SM_Wep_Rifle_Mag_01", "part_magazine", "magazine")
part(M, "SM_Wep_Rifle_Stock_01", "part_stock", "stock")
part(M, "SM_Wep_Mod_Barrel_01", "part_barrel", "barrel")
part(M, "SM_Wep_Pistol_Silencer_01", "part_silencer", "silencer")
part(M, "SM_Wep_Rifle_Bayonet_01", "part_bayonet", "bayonet")
part(M, "SM_Wep_Mod_Rail_01", "part_rail", "rail")
part(M, "SM_Wep_Mod_Trigger_01", "part_trigger", "trigger")
part(M, "SM_Wep_Mod_Handguard_01", "part_handguard", "handguard")
part(M, "SM_Wep_Mod_Grip_01", "part_grip", "grip")
part(M, "SM_Wep_Mod_Body_01", "part_body", "body")
part(M, "SM_Wep_Mod_Bipod_01", "part_misc", "misc")

# modern: ammo, carriers, emplaced
ammo(M, "SM_Wep_Bullet_01", "ammo_bullet", "bullet")
ammo(M, "SM_Wep_Shotgun_Shell_01", "ammo_shell", "shell")  # shell beats shotgun
ammo(M, "SM_Wep_Rocket_01", "ammo_rocket", "rocket")
ammo(M, "SM_Wep_Cannon_Ball_01", "ammo_cannonball", "other")  # Cannon + Ball joins to one token
carrier(M, "SM_Wep_Holster_01", "carrier_holster", "holster")
emplaced(M, "SM_Wep_Turret_01", "emplaced_turret", "turret")
emplaced(M, "SM_Wep_Mortar_01", "emplaced_mortar", "mortar")
emplaced(M, "SM_Wep_Flak_02", "emplaced_mortar", "mortar")  # alias flak -> mortar
emplaced(M, "SM_Wep_Cannon_02", "emplaced_cannon", "cannon")

# modern: thrown, melee, shared kit
wep(M, "SM_Wep_Grenade_Frag_02", "grenade", "grenade")
wep(M, "SM_Wep_Flashbang_03", "grenade", "grenade")  # alias flashbang -> grenade
wep(M, "SM_Wep_Molotov_01", "bomb", "bomb")
wep(M, "SM_Wep_Dynamite_02", "bomb", "bomb")
wep(M, "SM_Wep_Landmine_01", "mine", "mine")
wep(M, "SM_Wep_Claymore_02", "mine", "mine")  # claymore is a mine outside the fantasy-style packs
wep(M, "SM_Wep_Bat_01", "club", "club")
wep(M, "SM_Wep_Crowbar_02", "club", "club")
wep(M, "SM_Wep_Wrench_01", "tool", "tool")
wep(M, "SM_Gen_Wep_Pickaxe_01", "tool", "tool")  # Wep-prefixed pickaxe is a weapon (the Prop one is a trap)

# ---------------------------------------------------------------- fantasy: melee
wep(F, "SM_Wep_Sword_01", "sword", "sword")
wep(F, "SM_Wep_Sword_02", "sword", "sword")
wep(F, "SM_Wep_Katana_03", "sword", "sword")  # alias katana -> sword
wep(F, "SM_Wep_Rapier_04", "sword", "sword")
wep(F, "SM_Wep_Greatsword_05", "sword", "sword", two=True, hold="melee_two")
wep(F, "SM_Wep_Claymore_06", "claymore_sword", "sword")  # claymore is a sword in a fantasy pack
wep(F, "SM_Wep_Dagger_02", "knife", "knife")
wep(F, "SM_Wep_Battleaxe_02", "axe", "axe")
wep(F, "SM_Wep_Tomahawk_03", "axe", "axe")
wep(F, "SM_Wep_Mace_01", "mace", "mace")
wep(F, "SM_Wep_Flail_02", "mace", "mace")
wep(F, "SM_Wep_Hammer_01", "hammer", "hammer")
wep(F, "SM_Wep_Warhammer_02", "hammer", "hammer", two=True, hold="melee_two")
wep(F, "SM_Wep_Club_01", "club", "club")
wep(F, "SM_Wep_Spear_01", "spear", "spear")
wep(F, "SM_Wep_Trident_02", "spear", "spear")
wep(F, "SM_Wep_Halberd_01", "polearm", "polearm")
wep(F, "SM_Wep_Scythe_02", "polearm", "polearm")
wep(F, "SM_Wep_Staff_01", "staff", "staff")
wep(F, "SM_Wep_Wand_01", "wand", "wand")
wep(F, "SM_Wep_Wand_02", "wand", "wand")
wep(F, "SM_Wep_Whip_01", "whip", "whip")
wep(F, "SM_Wep_Knuckles_01", "fist_weapon", "fist_weapon")
wep(F, "SM_Wep_Claw_02", "fist_weapon", "fist_weapon")
wep(F, "SM_Wep_Shield_Set_01", "shield", "shield")
wep(F, "SM_Wep_Shield_Set_02", "shield", "shield")
wep(F, "SM_Wep_Shield_Set_02_Clean", "shield", "shield")  # family strips the numbering and _Clean
wep(F, "SM_Wep_Buckler_01", "shield", "shield")
part(F, "SM_Wep_Sword_Hilt_01", "part_melee", "misc")

# fantasy: ranged, ammo, carriers, siege, thrown
wep(F, "Wep_RecurveBow_01", "bow", "bow")  # un-prefixed bow pack; camelCase split
wep(F, "Wep_Longbow_02", "bow", "bow")  # alias longbow -> bow
wep(F, "SM_Wep_Bow_03", "bow", "bow")
wep(F, "SM_Wep_Crossbow_01", "crossbow", "crossbow")
wep(F, "SM_Wep_Crossbow_02", "crossbow", "crossbow")
ammo(F, "SM_Wep_Arrow_01", "ammo_arrow", "arrow")
ammo(F, "SM_Wep_Arrow_Fire_02", "ammo_arrow", "arrow")
ammo(F, "SM_Wep_Crossbow_Bolt_01", "ammo_bolt", "bolt")  # bolt stays ammo next to a crossbow
carrier(F, "SM_Wep_Quiver_01", "carrier_quiver", "quiver")
carrier(F, "SM_Wep_Sheath_01", "carrier_sheath", "sheath")
carrier(F, "SM_Wep_Scabbard_02", "carrier_scabbard", "scabbard")
emplaced(F, "SM_Wep_Catapult_01", "emplaced_siege", "siege_engine")
emplaced(F, "SM_Wep_Ballista_02", "emplaced_siege", "siege_engine")
wep(F, "SM_Wep_Shuriken_01", "throwing_blade", "throwing_blade")
wep(F, "SM_Wep_Throwing_Knife_02", "throwing_blade", "throwing_blade")  # joins to the throwingknife alias

# fantasy: prefab presets (no GLB, prefab only)
wep(F, "Preset_Sword_03", "sword", "sword", flags=["preset", "prefab_only"], prefab_only=True)
wep(F, "Wep_Preset_Axe_01", "axe", "axe", flags=["preset", "prefab_only"], prefab_only=True)

# shared-mesh kit: the same GLB in two packs; the later id (by sort order) is the duplicate
_SHARED = "glb/shared/Gen_Wep_Crowbar_01.glb"
wep(F, "SM_Gen_Wep_Crowbar_01", "club", "club", glb=_SHARED)
wep(M, "SM_Gen_Wep_Crowbar_01", "club", "club", glb=_SHARED, flags=["duplicate_mesh"])
WEAPONS[f"{M}/SM_Gen_Wep_Crowbar_01"]["duplicate_of"] = f"{F}/SM_Gen_Wep_Crowbar_01"

# ---------------------------------------------------------------- scifi
wep(X, "SM_Wep_Blaster_Pistol_01", "pistol", "pistol")
wep(X, "SM_Wep_Laser_Rifle_01", "rifle", "rifle")
wep(X, "SM_Wep_Plasma_Rifle_02", "rifle", "rifle")
wep(X, "SM_Wep_Blaster_01", "generic_gun", "unknown", kind_override="ranged")  # a gun, which gun is unknown
wep(X, "SM_Wep_Plasma_Gun_02", "generic_gun", "unknown", kind_override="ranged")
wep(X, "SM_Wep_Energy_Sword_01", "sword", "sword")
wep(X, "SM_Wep_Plasma_Grenade_02", "grenade", "grenade")
emplaced(X, "SM_Wep_Turret_Plasma_01", "emplaced_turret", "turret")
emplaced(X, "SM_Wep_Sentry_02", "emplaced_turret", "turret")  # alias sentry -> turret
wep(X, "SM_Wep_Mine_01", "mine", "mine")
wep(X, "SM_Wep_Mystery_01", None, "unknown", kind_override=None)  # catalog says weapon, no rule matches
# catalog signals, one at a time (type / semantic_role / gear.kind)
ASSETS[X].append(_asset(X, "SM_Prop_Device_01", typ="weapon", role="interior_prop", gear_kind=None))
_label(X, "SM_Prop_Device_01", None, "whole", "unknown", kind=None)
ASSETS[X].append(_asset(X, "SM_Prop_Device_02", typ="prop", role="weapon", gear_kind=None))
_label(X, "SM_Prop_Device_02", None, "whole", "unknown", kind=None)
ASSETS[X].append(_asset(X, "SM_Prop_Device_03", typ="prop", role="interior_prop", gear_kind="weapon"))
_label(X, "SM_Prop_Device_03", None, "whole", "unknown", kind=None)

# ---------------------------------------------------------------- mech scale (pack flag), generic (no pack setting)
wep(K, "SM_Wep_Rifle_Mech_01", "rifle", "rifle", flags=["mech_scale"], hold="none")
emplaced(K, "SM_Wep_Cannon_Mech_02", "emplaced_cannon", "cannon", flags=["mech_scale"])
wep(G, "SM_Wep_Sword_01", "sword", "sword", genre="fantasy")  # genre from the archetype table
wep(G, "SM_Wep_Pistol_01", "pistol", "pistol", genre="modern")
wep(G, "SM_Wep_Club_01", "club", "club", genre="other")
wep(G, "SM_Wep_Shield_01", "shield", "shield", genre="other")
wep(G, "SM_Wep_Mystery_01", None, "unknown", genre="other", kind_override=None)

# ---------------------------------------------------------------- name_token candidates (no catalog weapon signal)
tok(F, "SM_Prop_Axe_01", "axe", "axe")
tok(F, "SM_Item_Dagger_01", "knife", "knife")
tok(F, "SM_Prop_Spear_01", "spear", "spear")
tok(M, "SM_Prop_Pistol_01", "pistol", "pistol")
tok(X, "SM_Prop_Rifle_01", "rifle", "rifle")
tok(M, "SM_Veh_Cannon_01", "emplaced_cannon", "cannon", role="emplaced", typ="vehicle", sem="vehicle")

# ---------------------------------------------------------------- the trap set: rejected, never a record (AC2, AC8)
trap(M, "SM_Chr_Attach_Pistol_01", "character_attachment", "chr_attach", placeable=False)
trap(K, "SM_Mech_Arm_Weapon_01", "mech_attachment", "mech_weapon_attach")
trap(K, "geo_Weapon_L", "mech_attachment", "mech_weapon_attach")
trap(M, "UI_Icon_Sword_01", "ui", "ui_kind", kind="ui", typ="ui", role="ui_element", placeable=False, gear_kind=None)
trap(M, "SM_Wep_Crosshair_01", "ui", "ui_crosshair")
trap(M, "FX_Confetti_Cannon_01", "fx", "fx_prefix", typ="fx", role="visual_effect", gear_kind=None)
trap(M, "SM_Prop_Spark_Gun_Fx_01", "fx", "fx_kind", kind="fx", typ="fx", role="visual_effect", gear_kind=None)
trap(F, "SM_Prop_Bow_Ribbon_01", "scenery", "ribbon_bow", typ="prop", role="interior_prop", gear_kind=None)
trap(M, "SM_Env_Road_Arrow_01", "scenery", "road_arrow", typ="environment/city_layout", role="road_surface", gear_kind=None)
trap(M, "SM_Env_MineTunnel_01", "scenery", "mine_tunnel", typ="environment", role="foliage", gear_kind=None)
trap(M, "SM_Env_Mine_Track_01", "scenery", "mine_tunnel", typ="environment", role="foliage", gear_kind=None)
trap(M, "SM_Prop_Club_Awning_01", "scenery", "club_awning", typ="prop", role="facade_dressing", gear_kind=None)
trap(M, "SM_Veh_Windshield_01", "scenery", "windshield", typ="vehicle/part", role="vehicle_part", gear_kind=None)
trap(M, "SM_Prop_FaceShield_01", "scenery", "face_shield", typ="prop", role="interior_prop", gear_kind=None)
trap(M, "SM_Prop_WeaponRack_01", "scenery", "weapon_rack_sign", typ="prop", role="interior_prop", gear_kind=None)
trap(M, "SM_Sign_Weapon_Shop_01", "scenery", "weapon_rack_sign", typ="prop/signage", role="building_identity", gear_kind=None)
trap(M, "SM_Env_Grass_Blade_01", "scenery", "grass_blade", typ="environment", role="foliage", gear_kind=None)
trap(F, "SM_Prop_Torch_01", "tool_prop", "torch", typ="prop", role="interior_prop", gear_kind=None)
trap(F, "SM_Wep_Torch_02", "tool_prop", "torch")  # even Wep-prefixed, a torch is not a weapon
trap(M, "SM_Prop_Pickaxe_01", "tool_prop", "nonwep_tool_prop", typ="prop", role="interior_prop", gear_kind=None)
trap(M, "SM_Prop_Syringe_01", "tool_prop", "nonwep_tool_prop", typ="prop", role="interior_prop", gear_kind=None)
trap(G, "A_Emote_FingerGun_01", "nonplaceable", "nonmesh_noun", kind="animation", typ="animation", role="animation_clip",
     placeable=False, gear_kind=None)

# ---------------------------------------------------------------- not weapon-like at all: no row anywhere
plain(M, "SM_Prop_Chair_01")
plain(M, "SM_Prop_Barrel_01")
plain(M, "SM_Prop_Crate_01")
plain(M, "SM_Env_Rock_01", typ="environment", role="foliage")
plain(M, "SM_Bld_House_01", typ="building/shell", role="building_shell")
plain(F, "SM_Prop_Rope_01")
plain(F, "A_Idle_01", kind="animation", typ="animation", role="animation_clip", placeable=False)
plain(X, "SM_Prop_Console_01")

STEM_GROUP = {"stems": [s[0] for s in STEMS], "packs": [F, M, X]}


def catalog_doc(pack: str) -> dict:
    assets = sorted(ASSETS[pack], key=lambda a: a["id"])
    return {
        "pack_id": pack, "engine": "Unity", "origin": "fixture", "style": "synthetic", "units": "meters",
        "version": S.CATALOG_VERSION, "scanned_at": SCANNED_AT, "grid": dict(S.DEFAULT_GRID),
        "conventions": dict(S.DEFAULT_CONVENTIONS), "asset_count": len(assets), "assets": assets,
    }


def expected_doc() -> dict:
    return {
        "schema": "weapon-fixture-expected/1",
        "weapons": WEAPONS,
        "traps": TRAPS,
        "not_candidates": sorted(NOT_CANDIDATES),
        "stem_group": STEM_GROUP,
        "pack_settings": PACK_SETTINGS,
    }


def _dump(obj) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def write_all(out: Path) -> list[Path]:
    """Write catalogs/*.json and expected.json under ``out`` (LF endings). Returns the files written."""
    written = []
    (out / "catalogs").mkdir(parents=True, exist_ok=True)
    for pack in PACKS:
        path = out / "catalogs" / f"{pack}.json"
        path.write_bytes(_dump(catalog_doc(pack)))
        written.append(path)
    path = out / "expected.json"
    path.write_bytes(_dump(expected_doc()))
    written.append(path)
    return written


if __name__ == "__main__":
    for p in write_all(HERE):
        print(p.relative_to(HERE))
