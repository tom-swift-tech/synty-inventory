"""Synthetic W7b ids and their literal expectations (docs/weapon_directory.md 3.4.2 PATCH W7b; AC58-AC60, AC9).

The shared fixture catalogs (make_catalogs.py / expected.json) are generated and pinned, so the W7b rules, aliases and
kind hints get their fixture ids here. tests/test_weapons_w7_kind.py runs them through ``classify`` and the AC9 hygiene
test in test_weapons_classify.py counts RULE_CASES as the first-match proof of the new rules. Every value is a literal:
nothing is read from the code or the rules under test. Ids and packs are invented; no pack data.
"""

from __future__ import annotations

WORLDS = "FAKE_SciFi_Worlds_Pack"  # matches the `*SciFi_Worlds*` pack glob
OTHER = "FAKE_Pack"  # matches it not

# (rule, pack, asset id, expected archetype, expected kind): the id is classified with a bare `type: weapon` asset
RULE_CASES = [
    ("assault_rifle", OTHER, "SM_Wep_Assault_01", "rifle", "ranged"),
    ("heavy_gun_worlds", WORLDS, "SM_Wep_Heavy_01", "heavy_gun", "ranged"),
    ("alien_gun", WORLDS, "SM_Wep_Alien_01", "rifle", "ranged"),
    ("preset_gun", OTHER, "SM_Wep_Zorb_Preset_01", "unknown", "ranged"),
    ("preset_gun", OTHER, "Preset_Zorb_01", "unknown", "ranged"),
]
# (pack, id, matched rule, archetype): the same words outside the pack, or with a named gun, stay as they were
RULE_KEEP_CASES = [
    (OTHER, "SM_Wep_Heavy_01", None, "unknown"),
    (OTHER, "SM_Wep_Alien_01", None, "unknown"),
    (WORLDS, "SM_Wep_Heavy_Preset_01", "preset_gun", "unknown"),  # `tokens_none: [preset]` on heavy_gun_worlds
    (OTHER, "SM_Wep_Rifle_Preset_01", "rifle", "rifle"),  # a named gun wins over the generic preset rule
    (OTHER, "SM_Wep_Sword_Preset_01", "sword", "sword"),
    (OTHER, "SM_Wep_Assault_Rifle_01", "rifle", "rifle"),
]

# (asset id, role, archetype, component slot or None, matched rule): classified only through the new alias / token
ALIAS_CASES = [
    ("SM_Wep_FlameThrower_01", "whole", "flamethrower", None, "flamethrower"),
    ("SM_Wep_Flame_Thrower_01", "whole", "flamethrower", None, "flamethrower"),
    ("SM_Wep_ChainSaw_01", "whole", "tool", None, "tool"),
    ("SM_Wep_Chain_Saw_01", "whole", "tool", None, "tool"),
    ("SM_Wep_Blunderbuss_01", "whole", "shotgun", None, "shotgun"),
    ("SM_Wep_Stungun_01", "whole", "utility_gun", None, "utility_gun"),
    ("SM_Wep_Gunstock_01", "part", "unknown", "stock", "part_stock"),
    ("SM_Wep_Cleaver_01", "whole", "knife", None, "knife"),
    ("SM_Wep_Mining_Laser_Battery_01", "part", "unknown", "misc", "part_misc"),
]

# kind hints: every token of the shipped lists, by kind. The id is `SM_Wep_<Token>_01`; the archetype stays unknown.
HINT_TOKENS = {
    "ranged": ["laser", "cutter", "mining", "slingshot"],
    "melee": ["shock", "stick", "sickle", "hacksaw", "spanner", "drill", "surgical", "scalpel", "charm", "sceptre",
              "scepter"],
    "thrown": ["rock", "stone"],
}
# the spec's named examples: (asset id, kind)
HINT_CASES = [
    ("SM_Wep_Shock_Stick_01", "melee"),
    ("SM_Wep_Sickle_01", "melee"),
    ("SM_Wep_Laser_01", "ranged"),
    ("SM_Wep_Rock_01", "thrown"),
]
