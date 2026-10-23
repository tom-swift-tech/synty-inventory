"""Weapon directory (docs/weapon_directory.md): objective per-weapon profiles derived from the pack catalogs.

This module holds only versions, the closed enumerations of spec section 4.6, the shared error type and the
canonical-JSON helpers. It imports no sibling module, so every other module (and the tests) can import it freely.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

WEAPON_VERSION = 1  # classification + hints; bump invalidates directory.json
WEAPON_GEOMETRY_VERSION = 5  # geometry algorithm; bump invalidates _geometry_cache.json entries (2: bow belly rule, ranged section-sign convention, shield front; 3: melee grip anchored on the pivot, checked against a surface width profile; 4: melee grip kept 0.045 m off the butt end (W2f), melee forward sign of a mid-origin item from the larger end head over the outer 25 % for the head-forward archetypes (W2f); 5: the head sign decides over a differing pivot sign for the pivot-sourced headed melee archetypes and for head-lead tools (W7))

WEAPON_ATTACH_VERSION = 3  # attachment records (docs/weapon_attachments.md D-12); joins the attachment cache fingerprint, never WEAPON_GEOMETRY_VERSION (2: A1 twin seats and twin forward, W8f; 3: A2 sight slots, kinds, pairs, setting gate and sight seats, W8h)

ROLES = ("whole", "part", "ammo", "carrier", "emplaced")
NON_WEAPON_ROLES = ("part", "ammo", "carrier")  # kind is null for these (spec 4.1)
KINDS = ("ranged", "melee", "thrown", "shield")

# archetype -> kind (spec 3.4.2 table). Emplaced archetypes are kind "ranged".
ARCHETYPE_KIND = {
    **{a: "ranged" for a in (
        "pistol", "revolver", "smg", "rifle", "shotgun", "sniper", "lmg", "heavy_gun", "launcher",
        "flamethrower", "bow", "crossbow", "utility_gun",
    )},
    **{a: "melee" for a in (
        "knife", "sword", "axe", "mace", "hammer", "club", "spear", "polearm", "staff", "wand", "whip",
        "fist_weapon", "tool",
    )},
    **{a: "thrown" for a in ("grenade", "bomb", "mine", "throwing_blade")},
    "shield": "shield",
    **{a: "ranged" for a in ("turret", "cannon", "siege_engine", "mortar")},
}
EMPLACED_ARCHETYPES = ("turret", "cannon", "siege_engine", "mortar")
ARCHETYPES = tuple(sorted(ARCHETYPE_KIND)) + ("unknown",)

HOLD_CLASSES = (
    "one_hand", "long_gun", "melee_one", "melee_two", "melee_bat", "bow", "crossbow", "thrown", "shield", "none",
)
GENRES = ("modern", "scifi", "fantasy", "western", "other")
GENRE_SOURCES = ("pack", "archetype", "override")
STATUSES = ("auto", "reviewed", "overridden")
FLAGS = (
    "duplicate_mesh", "forward_by_fallback", "mech_scale", "needs_scale_check", "origin_outside_bounds",
    "preset", "prefab_only", "shared_glb_node", "token_candidate", "unmeasured",
)  # sorted: records carry them sorted (spec 3.4.5)
REASONS = (
    "anchor_forward_unsure", "anchor_unmeasured", "attach_kind_unknown", "axes_unexpected", "colourway_unknown",
    "compat_cross_pack", "degenerate", "kind_guessed", "low_confidence", "mount_ambiguous", "mount_estimated",
    "mount_missing", "muzzle_fallback", "no_geometry", "node_transform", "origin_outside_bounds",
    "sight_side_unsure", "twin_multi", "unknown_archetype",
)  # the eight attachment reasons (docs/weapon_attachments.md section 8) are used from W8a (anchor_*, attach_kind_*) and W8b/W8c (rest)
EXCLUDE_REASONS = (
    "nonplaceable", "ui", "fx", "character_attachment", "mech_attachment", "scenery", "tool_prop", "override",
)
CANDIDATE_SOURCES = ("catalog", "name_token")
SIZE_CLASSES_W = ("tiny", "small", "medium", "large", "huge")
WEIGHT_CLASSES = ("light", "medium", "heavy", "very_heavy")
AMMO_FAMILIES = ("handgun", "rifle", "shotgun", "heavy", "rocket", "grenade", "arrow", "bolt", "energy", "fuel")
COMPONENT_SLOTS = (
    "optic", "magazine", "stock", "barrel", "body", "grip", "silencer", "bayonet", "rail", "trigger",
    "handguard", "misc",
)
# Attachment vocabulary (docs/weapon_attachments.md sections 3.2 and 8). W8a owns every enum addition; later slices only import.
ATTACH_SLOTS = ("optic", "muzzle", "underbarrel", "magazine", "laser_light", "sight_front", "sight_rear")  # A2: the sight slots are appended
SIGHT_SLOTS = ("sight_front", "sight_rear")  # frame convention of `optic` (foot at the bottom); pairs and the sight probe live here
ATTACH_KINDS = {  # per slot, closed; every slot also has `other` (an unrecognised kind inside a known slot)
    "optic": ("scope", "sniper_scope", "reflex", "carry_handle_scope", "other"),  # A2: `iron` moved to the sight slots
    "muzzle": ("suppressor", "brake", "flash_hider", "other"),
    "underbarrel": ("foregrip", "bipod", "other"),
    "magazine": ("standard", "extended", "drum", "cell", "other"),
    "laser_light": ("laser", "light", "other"),
    "sight_front": ("post", "hooded", "canted", "other"),
    "sight_rear": ("notch", "aperture", "canted", "other"),
}
COMPAT_TIERS = ("override", "twin", "same_pack_fit", "cross_pack_fit")  # rank = index + 1
MOUNT_SOURCES = ("override", "child_node", "probe", "none")
MOUNT_NONE_REASONS = ("no_child_no_probe", "slot_disabled", "probe_unavailable")
ANCHOR_FOOT_SOURCES = ("authored_up", "measured", "override")
ANCHOR_FORWARD_SOURCES = ("section", "authored", "twin", "override")  # twin: the forward a baked twin child fixes (A1, W8f)
CARRIER_KINDS = ("quiver", "sheath", "scabbard", "holster")
AMMO_PROJECTILES = ("bullet", "shell", "arrow", "bolt", "rocket", "other")
PROVENANCES = ("rules", "override", "pack_settings", "measured")

# Process exit codes shared by every `weapons` verb (spec 3.2).
EXIT_OK = 0
EXIT_BAD_INPUT = 2
EXIT_REFUSED = 3
EXIT_COVERAGE = 4
EXIT_RENDERER = 5
EXIT_SCHEMA = 6


class WeaponsError(Exception):
    """A user-facing failure carrying the CLI exit code (spec 3.2 / section 7)."""

    code = EXIT_BAD_INPUT

    def __init__(self, message: str, code: int | None = None, details: dict | None = None):
        super().__init__(message)
        if code is not None:
            self.code = code
        self.details = details or {}


class InputError(WeaponsError):
    code = EXIT_BAD_INPUT


class RefusalError(WeaponsError):
    code = EXIT_REFUSED


class SchemaError(WeaponsError):
    code = EXIT_SCHEMA


def canonical_json(obj) -> str:
    """Canonical JSON used for digests: sorted keys, compact separators, ASCII only."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(obj) -> str:
    """sha256 over canonical JSON, first 16 hex characters (spec 3.3)."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()[:16]


def to_text(obj) -> str:
    """Deterministic file text: sorted keys, 1-space indent, LF, trailing newline, no clock."""
    return json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def write_text_lf(path: Path, text: str) -> None:
    """Write UTF-8 with LF endings on every platform (INV-4: byte-identical output).

    Goes through a temp file so a crash never leaves a half-written directory.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(text.encode("utf-8"))
    tmp.replace(path)
