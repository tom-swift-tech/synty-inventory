"""Synthetic W7 ids and their literal expectations (docs/weapon_directory.md 3.4.1 PATCH W7; AC50-AC53, AC9).

The shared fixture catalogs (make_catalogs.py / expected.json) are generated and pinned, so the W7 entries get their
fixture ids here instead: tests/test_weapons_w7_rules.py runs them through ``evaluate_candidate`` and ``classify`` and
the AC9 hygiene tests in test_weapons_candidates.py / test_weapons_classify.py count them as the first-match proof of
the new exclude / rule entries. Every value is a literal: nothing is read from the code or the rules under test.
"""

from __future__ import annotations

# (exclude entry, asset id, reason, what the SAME id becomes when that entry is removed from the table):
# "accepted" = a candidate again, or the name of the next exclude entry that then catches it.
EXCLUDE_CASES = [
    ("strip_club", "SM_Prop_StripClub_01", "scenery", "accepted"),
    # SM_Bld_* is also caught by bld_env_prefix, which sits after strip_club: removing strip_club alone only renames it
    ("strip_club", "SM_Bld_StripClub_01", "scenery", "bld_env_prefix"),
    ("bld_env_prefix", "SM_Env_Planetary_Cannon_01", "scenery", "accepted"),
    ("bld_env_prefix", "SM_Bld_Mine_Tower_01", "scenery", "accepted"),
    ("chr_prefix", "SM_Chr_Shieldmaiden_01", "character_attachment", "accepted"),
    ("sign_prop", "SM_Prop_Sign_Arrow_01", "scenery", "accepted"),
    ("sign_prop", "SM_Prop_Club_Neon_Sign_01", "scenery", "accepted"),
    ("container_furniture", "SM_Prop_Gun_Case_01", "scenery", "accepted"),
    ("container_furniture", "SM_Prop_Pike_Fence_01", "scenery", "accepted"),
    ("container_furniture", "SM_Prop_Claw_Machine_01", "scenery", "accepted"),
    ("container_furniture", "SM_Item_Knife_Holder_01", "scenery", "accepted"),
    ("pestle", "SM_Prop_Mortar_Pestle_01", "scenery", "accepted"),
]
# the entries added by W7, in table order (they follow the pre-W7 survey families)
W7_EXCLUDES = ("strip_club", "bld_env_prefix", "chr_prefix", "sign_prop", "container_furniture", "pestle")

# ids that must stay accepted candidates, with the rule that classifies them (AC50, AC51)
KEEP_CASES = [
    ("SM_Wep_Club_01", "club"),
    ("SM_Prop_Club_01", "club"),
    ("SM_Wep_Sign_Shield_01", "shield"),
    ("SM_Prop_Wep_Sign_Shield_01", "shield"),  # the wep token alone saves it from sign_prop
    ("SM_Prop_Crate_Bullets_01", "ammo_bullet"),
    ("SM_Wep_Pistol_Case_01", "pistol"),
    ("SM_Prop_Wep_Pistol_Case_01", "pistol"),  # the wep token alone saves it from container_furniture
    ("SM_Prop_Ammo_Box_01", "ammo_bullet"),
    ("SM_Prop_Quiver_Stand_01", "carrier_quiver"),
]
# ids an older exclude entry still owns after W7 (entry, id): the new entries sit behind them
OLDER_ENTRY_STILL_WINS = [
    ("club_awning", "SM_Prop_Club_Sign_01"),
    ("mine_tunnel", "SM_Env_Mine_Tunnel_01"),
    ("grass_blade", "SM_Env_Grass_Blade_01"),
]

# (rule, asset id, expected role, archetype, component slot) -- classified with a bare `type: weapon` asset
RULE_CASES = [
    ("part_attach", "SM_Veh_Attach_HMG_01", "part", "unknown", "misc"),
    ("part_attach", "SM_Jet_Attach_Bomb_01", "part", "unknown", "misc"),
    ("part_attach", "SM_Wep_Attach_Axe_01", "part", "unknown", "misc"),
    ("emplaced_vehicle", "SM_Wep_Veh_MiniGun_01", "emplaced", "turret", None),
    ("emplaced_vehicle", "SM_Veh_Extra_Gun_01", "emplaced", "turret", None),
]
# ids the new rules must NOT take: (id, matched rule, role, archetype)
RULE_KEEP_CASES = [
    ("SM_Heli_Attach_Missile_01", "ammo_rocket", "ammo", "unknown"),
    ("SM_Veh_Attach_Bolt_01", "ammo_bolt", "ammo", "unknown"),
    ("SM_Veh_Cannon_01", "emplaced_cannon", "emplaced", "cannon"),
]

# (alias target, variant, asset id, role, archetype): the id classifies as described only through the alias
ALIAS_CASES = [
    ("axe", "fireaxe", "SM_Wep_Fireaxe_01", "whole", "axe"),
    ("sword", "straightsword", "SM_Wep_Straightsword_01", "whole", "sword"),
    ("sword", "zweihander", "SM_Wep_Zweihander_01", "whole", "sword"),
    ("sword", "ninjato", "SM_Wep_Ninjato_01", "whole", "sword"),
    ("sword", "odachi", "SM_Wep_Odachi_01", "whole", "sword"),
    ("sword", "machette", "SM_Wep_Machette_01", "whole", "sword"),
    ("pickaxe", "pickacxe", "SM_Wep_Pickacxe_01", "whole", "tool"),
    ("cannonball", "cannonballs", "SM_Wep_CannonBalls_01", "ammo", "unknown"),
]

HEAD_LEAD_TOKENS = ("spade", "shovel", "pitchfork")
ALBEDO_ENTRY = {"name": "viking_shield_sets", "packs_any": ["POLYGON_Viking_Realm"], "id_regex": "^SM_Wep_Shield_Set_"}
