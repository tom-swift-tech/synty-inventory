"""JSON Schemas for ``weapon/1``, ``weapon-directory/1`` and ``weapon-excluded/1`` plus the cross-field checks that
JSON Schema cannot express (spec 4.1-4.3, INV-2/3/7/9/13).

The nullability rules of spec 4.1 and 3.6 are strict (W1's ``pre_geometry`` tolerance mode is gone): hints are
derived for every record, ``geometry`` is null exactly when the record is flagged ``unmeasured``, and
``quality_tier`` is null exactly for part/ammo/carrier roles and unknown archetypes (AC35).
"""

from __future__ import annotations

from jsonschema import Draft202012Validator

from . import (
    AMMO_FAMILIES,
    AMMO_PROJECTILES,
    ARCHETYPES,
    CANDIDATE_SOURCES,
    CARRIER_KINDS,
    COMPONENT_SLOTS,
    EXCLUDE_REASONS,
    FLAGS,
    GENRE_SOURCES,
    GENRES,
    HOLD_CLASSES,
    KINDS,
    NON_WEAPON_ROLES,
    PROVENANCES,
    REASONS,
    ROLES,
    SIZE_CLASSES_W,
    STATUSES,
    WEIGHT_CLASSES,
)

# <pack>/<asset_id>: the pack part has no whitespace; real Synty asset ids can contain spaces ("FX_Bullet_Trail 1")
_ID_PATTERN = r"^[^/\s]+/[^/]+$"
_HEX16 = r"^[0-9a-f]{16}$"


def _enum(values, nullable=False):
    return {"enum": list(values) + ([None] if nullable else [])}


_VEC3 = {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}
_VEC3_NULL = {"anyOf": [_VEC3, {"type": "null"}]}
_NUM_NULL = {"type": ["number", "null"]}
_STR_NULL = {"type": ["string", "null"]}
_AXIS = {"type": "string", "pattern": "^[+-][xyz]$"}

GEOMETRY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["frame", "node_offset", "axes", "item_basis", "bounds", "long_axis", "length_m", "pivot_frac",
                 "tip", "butt", "muzzle", "muzzle_source", "grip", "grip_r_m", "grip_source", "support",
                 "support_r_m", "support_source", "triangles"],
    "properties": {
        "frame": _enum(("asset", "item")),
        "node_offset": _VEC3_NULL,
        "axes": {
            "type": "object",
            "required": ["forward", "up", "forward_source", "up_source"],
            "properties": {"forward": _AXIS, "up": _AXIS, "forward_source": {"type": "string"},
                           "up_source": {"type": "string"}},
        },
        "item_basis": {"type": "array", "minItems": 3, "maxItems": 3,
                       "items": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "integer"}}},
        "bounds": {
            "type": "object",
            "required": ["min", "max", "size", "pivot"],
            "properties": {"min": _VEC3, "max": _VEC3, "size": _VEC3, "pivot": {"type": "string"}},
        },
        "long_axis": _enum(("x", "y", "z")),
        "length_m": {"type": "number", "minimum": 0},
        "pivot_frac": {"type": "number"},
        "tip": _VEC3_NULL,
        "butt": _VEC3,
        "muzzle": _VEC3_NULL,
        "muzzle_source": _enum(("face", "bounds_fallback"), nullable=True),
        "grip": _VEC3_NULL,
        "grip_r_m": _NUM_NULL,
        "grip_source": _enum(("pivot", "handle", "centre", "proportion"), nullable=True),
        "support": _VEC3_NULL,
        "support_r_m": _NUM_NULL,
        "support_source": _enum(("proportion",), nullable=True),
        "triangles": {"type": "integer", "minimum": 0},
    },
}

HINTS_SCHEMA = {
    # INV-9: any key outside this list (damage, price, rarity, ...) is a violation
    "type": "object",
    "additionalProperties": False,
    "required": ["size_class", "size_basis", "inventory_cells", "weight_class", "quality_tier", "ammo_family"],
    "properties": {
        "size_class": _enum(SIZE_CLASSES_W, nullable=True),
        "size_basis": _enum(("measured", "raw"), nullable=True),
        "inventory_cells": {"anyOf": [
            {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "integer", "minimum": 1}},
            {"type": "null"},
        ]},
        "weight_class": _enum(WEIGHT_CLASSES, nullable=True),
        "quality_tier": {"anyOf": [{"type": "integer", "minimum": 1, "maximum": 5}, {"type": "null"}]},
        "ammo_family": _enum(AMMO_FAMILIES, nullable=True),
    },
}

WEAPON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "id", "pack", "asset_id", "files", "renamed_from", "family", "role", "kind",
                 "genre", "genre_source", "archetype", "hold_class", "component", "carrier", "ammo", "flags",
                 "duplicate_of", "geometry", "hints", "visuals", "review", "provenance"],
    "properties": {
        "schema_version": {"const": 1},
        "id": {"type": "string", "pattern": _ID_PATTERN},
        "pack": {"type": "string", "minLength": 1},
        "asset_id": {"type": "string", "minLength": 1},
        "files": {
            "type": "object",
            "additionalProperties": {"anyOf": [
                {"type": "null"}, {"type": "string"}, {"type": "array", "items": {"type": "string"}},
            ]},
        },
        "renamed_from": {"type": "array", "uniqueItems": True, "items": {"type": "string", "pattern": _ID_PATTERN}},
        "family": {"type": "string", "minLength": 1},
        "role": _enum(ROLES),
        "kind": _enum(KINDS, nullable=True),
        "genre": _enum(GENRES),
        "genre_source": _enum(GENRE_SOURCES),
        "archetype": _enum(ARCHETYPES),
        "hold_class": _enum(HOLD_CLASSES),
        "component": {"anyOf": [
            {"type": "null"},
            {"type": "object", "additionalProperties": False, "required": ["slot", "fits"],
             "properties": {"slot": _enum(COMPONENT_SLOTS),
                            "fits": {"anyOf": [{"type": "null"},
                                               {"type": "array", "items": _enum(ARCHETYPES)}]}}},
        ]},
        "carrier": {"anyOf": [
            {"type": "null"},
            {"type": "object", "additionalProperties": False, "required": ["kind"],
             "properties": {"kind": _enum(CARRIER_KINDS)}},
        ]},
        "ammo": {"anyOf": [
            {"type": "null"},
            {"type": "object", "additionalProperties": False, "required": ["projectile"],
             "properties": {"projectile": _enum(AMMO_PROJECTILES)}},
        ]},
        "flags": {"type": "array", "uniqueItems": True, "items": _enum(FLAGS)},
        "duplicate_of": {"anyOf": [{"type": "string", "pattern": _ID_PATTERN}, {"type": "null"}]},
        "geometry": {"anyOf": [GEOMETRY_SCHEMA, {"type": "null"}]},
        "hints": HINTS_SCHEMA,
        "visuals": {
            "type": "object",
            "additionalProperties": False,
            "required": ["icon", "thumb", "icon_input_sha", "variants"],
            "properties": {
                "icon": _STR_NULL, "thumb": _STR_NULL, "icon_input_sha": _STR_NULL,
                "variants": {"type": "array", "items": {
                    "type": "object",
                    "required": ["variant_id", "mechanism", "source", "is_default", "icon"],
                    "properties": {"variant_id": {"type": "string"}, "mechanism": {"type": "string"},
                                   "source": {"type": "string"}, "is_default": {"type": "boolean"},
                                   "icon": _STR_NULL},
                }},
            },
        },
        "review": {
            "type": "object",
            "additionalProperties": False,
            "required": ["status", "confidence", "reasons", "matched_rule", "candidate_source"],
            "properties": {
                "status": _enum(STATUSES),
                "confidence": {"type": "number", "minimum": 0.05, "maximum": 1.0},
                "reasons": {"type": "array", "uniqueItems": True, "items": _enum(REASONS)},
                "matched_rule": _STR_NULL,
                "candidate_source": _enum(CANDIDATE_SOURCES),
            },
        },
        "provenance": {
            "type": "object",
            "additionalProperties": False,
            "properties": {k: _enum(PROVENANCES) for k in ("archetype", "kind", "hold_class", "genre", "geometry",
                                                           "hints")},
        },
    },
}

_COUNT_MAP = {"type": "object", "additionalProperties": {"type": "integer", "minimum": 0}}
DIRECTORY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema", "weapon_version", "geometry_version", "rules_digest", "overrides_digest", "packs",
                 "counts", "weapons"],
    "properties": {
        "schema": {"const": "weapon-directory/1"},
        "weapon_version": {"type": "integer", "minimum": 1},
        "geometry_version": {"type": "integer", "minimum": 1},
        "rules_digest": {"type": "string", "pattern": _HEX16},
        "overrides_digest": {"type": "string", "pattern": _HEX16},
        "packs": {"type": "array", "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["pack", "scanned_at", "asset_count", "candidates", "records", "excluded"],
            "properties": {
                "pack": {"type": "string", "minLength": 1}, "scanned_at": _STR_NULL,
                **{k: {"type": "integer", "minimum": 0} for k in ("asset_count", "candidates", "records", "excluded")},
            },
        }},
        "counts": {
            "type": "object",
            "additionalProperties": False,
            "required": ["by_role", "by_kind", "by_genre", "by_archetype", "by_status"],
            "properties": {k: _COUNT_MAP for k in ("by_role", "by_kind", "by_genre", "by_archetype", "by_status")},
        },
        "weapons": {"type": "array", "items": WEAPON_SCHEMA},
    },
}

EXCLUDED_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema", "excluded"],
    "properties": {
        "schema": {"const": "weapon-excluded/1"},
        "excluded": {"type": "array", "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["id", "reason", "matched", "source"],
            "properties": {
                "id": {"type": "string", "pattern": _ID_PATTERN},
                "reason": _enum(EXCLUDE_REASONS),
                "matched": {"type": "string"},
                "source": _enum(CANDIDATE_SOURCES),
            },
        }},
    },
}


def _schema_errors(schema: dict, doc, prefix: str = "") -> list[str]:
    validator = Draft202012Validator(schema)
    out = []
    for err in sorted(validator.iter_errors(doc), key=lambda e: [str(p) for p in e.absolute_path]):
        path = prefix + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in err.absolute_path)
        out.append(f"{path.lstrip('.') or '<root>'}: {err.message[:200]}")
    return out


def check_record(rec: dict, where: str) -> list[str]:
    """Cross-field rules of spec 4.1 for one record that already passed the structural schema."""
    errs: list[str] = []
    role, kind, arch = rec["role"], rec["kind"], rec["archetype"]
    flags = rec["flags"]
    if rec["id"] != f"{rec['pack']}/{rec['asset_id']}":
        errs.append(f"{where}.id: must equal pack/asset_id")
    if role in NON_WEAPON_ROLES and kind is not None:
        errs.append(f"{where}.kind: must be null for role {role}")
    if role in ("whole", "emplaced") and kind is None and arch != "unknown":
        errs.append(f"{where}.kind: required for role {role} with a known archetype")
    if (role in NON_WEAPON_ROLES or role == "emplaced" or "mech_scale" in flags) and rec["hold_class"] != "none":
        errs.append(f"{where}.hold_class: must be 'none' for role {role} / mech_scale")
    for field, owner in (("component", "part"), ("carrier", "carrier"), ("ammo", "ammo")):
        if (role == owner) != (rec[field] is not None):
            errs.append(f"{where}.{field}: present exactly when role is {owner}")
    if flags != sorted(flags):
        errs.append(f"{where}.flags: must be sorted")
    geom = rec["geometry"]
    if (geom is None) != ("unmeasured" in flags):
        errs.append(f"{where}.geometry: null exactly when flag 'unmeasured' is set")
    if rec["id"] in rec["renamed_from"]:
        errs.append(f"{where}.renamed_from: contains the record's own id")
    if rec["duplicate_of"] == rec["id"]:
        errs.append(f"{where}.duplicate_of: cannot point at itself")
    hints = rec["hints"]
    if (hints["size_class"] is None) != (geom is None) or (hints["inventory_cells"] is None) != (geom is None):
        errs.append(f"{where}.hints: size_class/inventory_cells null exactly when geometry is null")
    if (hints["size_basis"] is None) != (geom is None):
        errs.append(f"{where}.hints.size_basis: null exactly when geometry is null")
    no_tier = role in NON_WEAPON_ROLES or arch == "unknown"
    if (hints["quality_tier"] is None) != no_tier:
        errs.append(f"{where}.hints.quality_tier: null exactly when role is part/ammo/carrier or archetype unknown")
    if geom is not None:
        if (geom["muzzle"] is None) != (kind != "ranged" or arch == "bow"):
            errs.append(f"{where}.geometry.muzzle: present exactly for ranged, non-bow records")
        if (geom["muzzle"] is None) != (geom["muzzle_source"] is None):
            errs.append(f"{where}.geometry.muzzle_source: present exactly when muzzle is")
        if (geom["support"] is None) != (rec["hold_class"] != "long_gun"):
            errs.append(f"{where}.geometry.support: present exactly for hold_class long_gun")
        if (geom["tip"] is None) != (kind == "ranged"):
            errs.append(f"{where}.geometry.tip: null exactly for ranged records")
    return errs


def validate_directory(doc, excluded_doc=None) -> list[str]:
    """All violations of ``weapon-directory/1`` (structural + INV-2/3/13), as readable messages.

    ``excluded_doc`` (optional) lets the per-pack ``records + excluded == candidates`` identity be checked.
    """
    errors = _schema_errors(DIRECTORY_SCHEMA, doc)
    if errors:
        return errors
    weapons = doc["weapons"]
    ids = [w["id"] for w in weapons]
    seen: set[str] = set()
    for i, w in enumerate(weapons):
        if w["id"] in seen:
            errors.append(f"weapons[{i}].id: duplicate id {w['id']}")
        seen.add(w["id"])
        errors += check_record(w, f"weapons[{i}]")
    if ids != sorted(ids):
        errors.append("weapons: must be sorted by id")
    # INV-13: renamed ids are never live ids and are claimed by at most one record
    claimed: dict[str, str] = {}
    for w in weapons:
        for old in w["renamed_from"]:
            if old in seen:
                errors.append(f"renamed_from: {old!r} (claimed by {w['id']}) equals a live record id")
            if old in claimed and claimed[old] != w["id"]:
                errors.append(f"renamed_from: {old!r} is claimed by both {claimed[old]} and {w['id']}")
            claimed[old] = w["id"]
    by_pack: dict[str, int] = {}
    for w in weapons:
        by_pack[w["pack"]] = by_pack.get(w["pack"], 0) + 1
    excl_by_pack: dict[str, int] = {}
    if excluded_doc is not None:
        errors += _schema_errors(EXCLUDED_SCHEMA, excluded_doc, "excluded")
        if not errors:
            for row in excluded_doc["excluded"]:
                if row["id"] in seen:
                    errors.append(f"excluded: {row['id']} is also a record (INV-3)")
                pack = row["id"].split("/", 1)[0]
                excl_by_pack[pack] = excl_by_pack.get(pack, 0) + 1
    for row in doc["packs"]:
        if row["records"] != by_pack.get(row["pack"], 0):
            errors.append(f"packs[{row['pack']}].records: {row['records']} != {by_pack.get(row['pack'], 0)} records")
        if row["candidates"] != row["records"] + row["excluded"]:
            errors.append(f"packs[{row['pack']}]: candidates != records + excluded (INV-3)")
        if excluded_doc is not None and row["excluded"] != excl_by_pack.get(row["pack"], 0):
            errors.append(f"packs[{row['pack']}].excluded: {row['excluded']} != {excl_by_pack.get(row['pack'], 0)} rows")
    return errors


def validate_record(rec) -> list[str]:
    """Structural + cross-field errors for one ``weapon/1`` record."""
    errors = _schema_errors(WEAPON_SCHEMA, rec)
    if not errors:
        errors = check_record(rec, "record")
    return errors
