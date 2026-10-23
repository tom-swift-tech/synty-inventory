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
    ANCHOR_FOOT_SOURCES,
    ANCHOR_FORWARD_SOURCES,
    ARCHETYPES,
    ATTACH_KINDS,
    ATTACH_SLOTS,
    CANDIDATE_SOURCES,
    CARRIER_KINDS,
    COMPAT_TIERS,
    COMPONENT_SLOTS,
    EXCLUDE_REASONS,
    FLAGS,
    GENRE_SOURCES,
    GENRES,
    HOLD_CLASSES,
    KINDS,
    MOUNT_NONE_REASONS,
    MOUNT_SOURCES,
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
_ICON_MODE = {"type": "string", "enum": ["blend_retry"]}  # icons.ICON_MODE_BLEND (schema imports no sibling)
_AXIS = {"type": "string", "pattern": "^[+-][xyz]$"}

_ATTACH_KIND_VALUES = sorted({k for kinds in ATTACH_KINDS.values() for k in kinds})  # per-slot membership: check_record
_FRAME = {
    "type": "object",
    "additionalProperties": False,
    "required": ["point", "forward", "up", "foot_source", "forward_source", "symmetric"],
    "properties": {
        "point": _VEC3, "forward": _VEC3, "up": _VEC3,
        "foot_source": _enum(ANCHOR_FOOT_SOURCES), "forward_source": _enum(ANCHOR_FORWARD_SOURCES),
        "symmetric": {"type": "boolean"},
    },
}
_METRES = {"type": "number", "minimum": 0}
ATTACHMENT_SCHEMA = {
    # docs/weapon_attachments.md 3.2; the directory form of pending_hosts is {host, tier} (the export form is bare ids)
    "type": "object",
    "additionalProperties": False,
    "required": ["slot", "kind", "anchor", "footprint", "compatible_hosts", "pending_hosts"],
    "properties": {
        "slot": _enum(ATTACH_SLOTS),
        "kind": _enum(_ATTACH_KIND_VALUES),
        "anchor": {"anyOf": [_FRAME, {"type": "null"}]},
        "footprint": {"anyOf": [{
            "type": "object",
            "additionalProperties": False,
            "required": ["length_m", "width_m", "height_m", "foot_length_m", "foot_width_m", "mate_d_m"],
            "properties": {k: _METRES for k in ("length_m", "width_m", "height_m", "foot_length_m", "foot_width_m")}
                          | {"mate_d_m": {"anyOf": [_METRES, {"type": "null"}]}},
        }, {"type": "null"}]},
        "compatible_hosts": {"type": "array", "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["host", "tier", "score", "signals", "replaces"],
            "properties": {
                "host": {"type": "string", "pattern": _ID_PATTERN}, "tier": _enum(COMPAT_TIERS),
                "score": {"type": "number", "minimum": 0, "maximum": 1},
                "signals": {"type": "array", "items": {"type": "string"}},
                "replaces": {"type": "array", "items": {"type": "string"}},
            },
        }},
        "pending_hosts": {"type": "array", "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["host", "tier"],
            "properties": {"host": {"type": "string", "pattern": _ID_PATTERN}, "tier": _enum(COMPAT_TIERS)},
        }},
    },
}
_HOST_HOLDS = ("one_hand", "long_gun")  # hosts that carry mounts (docs/weapon_attachments.md 4.1)
_FRAME_TOL = 1e-3  # INV-18: unit length and mutual orthogonality

_MOUNT = {
    # one slot of geometry.mounts (docs/weapon_attachments.md 4.1); the cross-field rules (INV-15 to INV-18) are in _check_mounts
    "type": "object",
    "additionalProperties": False,
    "required": ["source", "point", "forward", "up", "span_m", "span_source", "occupied_by", "child_node", "bore_d_m",
                 "bore_source", "confidence", "reason"],
    "properties": {
        "source": _enum(MOUNT_SOURCES),
        "point": _VEC3_NULL, "forward": _VEC3_NULL, "up": _VEC3_NULL,
        "span_m": {"anyOf": [_METRES, {"type": "null"}]},
        "span_source": _enum(("child_foot", "probe"), nullable=True),
        "occupied_by": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "child_node": {"anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}]},
        "bore_d_m": {"anyOf": [_METRES, {"type": "null"}]},
        "bore_source": _enum(("ring", "face_extent"), nullable=True),
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": _enum(MOUNT_NONE_REASONS, nullable=True),
    },
}
MOUNTS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": list(ATTACH_SLOTS),
    "properties": {slot: _MOUNT for slot in ATTACH_SLOTS},
}

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
            # forward_source stays a free string (pivot, section, bow_rule, shield_front, shield_rule, override, ...)
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
        # W8b: optional, so a W7 / W8a directory still validates and the default export (which drops it) too
        "mounts": {"anyOf": [MOUNTS_SCHEMA, {"type": "null"}]},
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
                {"type": "number"},  # files.glb_scale (e.g. 0.01): the one numeric entry the catalogs carry
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
                # present only when the icon needed the BLEND retry (weapons icons, spec 3.8); absent for a normal render
                "icon_mode": _ICON_MODE,
                "variants": {"type": "array", "items": {
                    "type": "object",
                    "required": ["variant_id", "mechanism", "source", "is_default", "icon"],
                    "properties": {"variant_id": {"type": "string"}, "mechanism": {"type": "string"},
                                   "source": {"type": "string"}, "is_default": {"type": "boolean"},
                                   "icon": _STR_NULL, "icon_mode": _ICON_MODE,
                                   # true when the colourway icon looks like the default icon; written on every variant
                                   # that has an icon while the default icon exists
                                   "visually_identical": {"type": "boolean"}},
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
        "attachment": {"anyOf": [ATTACHMENT_SCHEMA, {"type": "null"}]},  # optional: only part records carry the key (W8a)
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
                 "counts", "weapons"],  # attach_version / attach_rules_digest are optional: a W7 directory has neither
    "properties": {
        "schema": {"const": "weapon-directory/1"},
        "weapon_version": {"type": "integer", "minimum": 1},
        "geometry_version": {"type": "integer", "minimum": 1},
        "rules_digest": {"type": "string", "pattern": _HEX16},
        "overrides_digest": {"type": "string", "pattern": _HEX16},
        "attach_version": {"type": "integer", "minimum": 1},
        "attach_rules_digest": {"type": "string", "pattern": _HEX16},
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


def _frame_errors(frame: dict, where: str) -> list[str]:
    """INV-18: unit forward and up, orthogonal to each other (right = up x forward is then right-handed by construction)."""
    f, u = frame["forward"], frame["up"]
    dot = sum(a * b for a, b in zip(f, u))
    errs = [f"{where}.{name}: not a unit vector" for name, v in (("forward", f), ("up", u))
            if abs(sum(c * c for c in v) ** 0.5 - 1.0) > _FRAME_TOL]
    if abs(dot) > _FRAME_TOL:
        errs.append(f"{where}: forward and up are not orthogonal")
    return errs


def _check_attachment(att: dict, role: str, where: str) -> list[str]:
    """Cross-field rules of docs/weapon_attachments.md 3.2 and INV-14/18 for one non-null ``attachment`` block."""
    errs: list[str] = []
    here = f"{where}.attachment"
    if role != "part":
        errs.append(f"{here}: non-null only for role part")
    if att["kind"] not in ATTACH_KINDS[att["slot"]]:
        errs.append(f"{here}.kind: {att['kind']!r} is not a kind of slot {att['slot']} ({list(ATTACH_KINDS[att['slot']])})")
    if (att["anchor"] is None) != (att["footprint"] is None):
        errs.append(f"{here}: anchor and footprint are null together")
    if att["anchor"] is not None:
        errs += _frame_errors(att["anchor"], f"{here}.anchor")
    if att["footprint"] is not None and (att["footprint"]["mate_d_m"] is not None) != (att["slot"] == "muzzle"):
        errs.append(f"{here}.footprint.mate_d_m: non-null exactly for the muzzle slot")
    keys = [(COMPAT_TIERS.index(h["tier"]), -h["score"], h["host"]) for h in att["compatible_hosts"]]
    if keys != sorted(keys):
        errs.append(f"{here}.compatible_hosts: must be sorted by (tier rank, -score, host)")
    return errs


def _check_mount(slot: str, m: dict, geom: dict, where: str) -> list[str]:
    """INV-15 to INV-18 for one slot of ``geometry.mounts``."""
    errs: list[str] = []
    here = f"{where}.geometry.mounts.{slot}"
    src = m["source"]
    coords = [m[k] is None for k in ("point", "forward", "up", "span_m")]
    if (src == "none") != all(coords) or (src != "none" and any(coords[:3])):
        errs.append(f"{here}: coordinates are null exactly when source is none (INV-15)")
    if (src == "none") != (m["reason"] is not None):
        errs.append(f"{here}.reason: set exactly when source is none (INV-15)")
    if (m["span_m"] is None) != (m["span_source"] is None):
        errs.append(f"{here}.span_source: null exactly when span_m is")
    if src != "none" and not any(coords[:3]):
        errs += _frame_errors(m, here)
    occ = m["occupied_by"]
    if occ != sorted(set(occ)):
        errs.append(f"{here}.occupied_by: must be sorted and duplicate-free (INV-16)")
    probe_muzzle = slot == "muzzle" and src == "probe"
    if occ and src not in ("child_node", "override") and not probe_muzzle:
        errs.append(f"{here}.occupied_by: non-empty only for child_node or override, or a probe muzzle (INV-16)")
    seated = src in ("child_node", "override")
    if seated != (m["child_node"] is not None):
        errs.append(f"{here}.child_node: set exactly for source child_node or override (INV-16)")
    elif seated and m["child_node"] not in occ:
        errs.append(f"{here}.occupied_by: must contain child_node {m['child_node']!r} (INV-16)")
    if (m["bore_d_m"] is None) != (m["bore_source"] is None):
        errs.append(f"{here}.bore_source: null exactly when bore_d_m is")
    if m["bore_d_m"] is not None and not probe_muzzle:
        errs.append(f"{here}.bore_d_m: only the probe muzzle carries a bore")
    if slot == "muzzle" and src not in ("probe", "none"):
        errs.append(f"{here}.source: the muzzle seat always comes from the probe (or the slot is none)")
    if probe_muzzle and not any(coords[:3]):
        muzzle = geom["muzzle"]
        if muzzle is None:
            errs.append(f"{here}: a probe muzzle needs geometry.muzzle (a ranged, non-bow host)")
        elif not occ and m["point"] != muzzle:
            errs.append(f"{here}.point: with no occupied_by the seat is geometry.muzzle exactly (AC67)")
        axes = geom["axes"]
        for key, want in (("up", axes["forward"]), ("forward", axes["up"])):
            vec = [0.0, 0.0, 0.0]
            vec["xyz".index(want[1])] = 1.0 if want[0] == "+" else -1.0
            if m[key] != vec:
                errs.append(f"{here}.{key}: must be the host's axes.{'forward' if key == 'up' else 'up'} {want}")
    return errs


def _check_mounts(rec: dict, geom: dict, where: str) -> list[str]:
    """``geometry.mounts`` is non-null exactly for an eligible host (whole, ranged, one_hand / long_gun; D-9)."""
    mounts = geom["mounts"]
    host = rec["role"] == "whole" and rec["kind"] == "ranged" and rec["hold_class"] in _HOST_HOLDS
    if (mounts is None) == host:
        return [f"{where}.geometry.mounts: non-null exactly for a whole, ranged one_hand / long_gun host (D-9)"]
    if mounts is None:
        return []
    errs: list[str] = []
    for slot in ATTACH_SLOTS:
        errs += _check_mount(slot, mounts[slot], geom, where)
    return errs


def check_record(rec: dict, where: str) -> list[str]:
    """Cross-field rules of spec 4.1 for one record that already passed the structural schema."""
    errs: list[str] = []
    role, kind, arch = rec["role"], rec["kind"], rec["archetype"]
    flags = rec["flags"]
    if rec["id"] != f"{rec['pack']}/{rec['asset_id']}":
        errs.append(f"{where}.id: must equal pack/asset_id")
    if role in NON_WEAPON_ROLES and kind is not None:
        errs.append(f"{where}.kind: must be null for role {role}")
    if role in ("whole", "emplaced") and kind is None:
        # W7b: no exemption for archetype `unknown`; kind is non-null iff role is whole or emplaced (spec 4.1)
        errs.append(f"{where}.kind: required (non-null) for role {role}; kind is null only for part, ammo and carrier")
    if (role in NON_WEAPON_ROLES or role == "emplaced" or "mech_scale" in flags) and rec["hold_class"] != "none":
        errs.append(f"{where}.hold_class: must be 'none' for role {role} / mech_scale")
    for field, owner in (("component", "part"), ("carrier", "carrier"), ("ammo", "ammo")):
        if (role == owner) != (rec[field] is not None):
            errs.append(f"{where}.{field}: present exactly when role is {owner}")
    if flags != sorted(flags):
        errs.append(f"{where}.flags: must be sorted")
    if rec.get("attachment") is not None:
        errs += _check_attachment(rec["attachment"], role, where)
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
    if geom is not None and "mounts" in geom:
        errs += _check_mounts(rec, geom, where)
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
    # INV-14: the hosts an attachment names exist in the directory and are eligible (whole, ranged, one_hand/long_gun)
    by_id = {w["id"]: w for w in weapons}
    for i, w in enumerate(weapons):
        att = w.get("attachment")
        for field in (("compatible_hosts", "pending_hosts") if att else ()):
            for j, entry in enumerate(att[field]):
                host = by_id.get(entry["host"])
                if host is None:
                    errors.append(f"weapons[{i}].attachment.{field}[{j}].host: {entry['host']} is not in the directory")
                elif not (host["role"] == "whole" and host["kind"] == "ranged" and host["hold_class"] in _HOST_HOLDS):
                    errors.append(f"weapons[{i}].attachment.{field}[{j}].host: {entry['host']} is not an eligible host "
                                  "(whole, ranged, one_hand or long_gun)")
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
