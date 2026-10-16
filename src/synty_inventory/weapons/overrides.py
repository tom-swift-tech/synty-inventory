"""``weapon_overrides.json`` (``weapon-overrides/1``): load, validate, resolve precedence (spec 3.9, 4.5).

Precedence per field, highest first: exact-id entry > longest matching glob > rule match. The file holds ids,
globs and enum values only: no measurements and no pack data (INV-1).
"""

from __future__ import annotations

import json
from fnmatch import fnmatchcase
from pathlib import Path

from . import (
    AMMO_PROJECTILES,
    ARCHETYPES,
    CARRIER_KINDS,
    COMPONENT_SLOTS,
    GENRES,
    HOLD_CLASSES,
    KINDS,
    ROLES,
    InputError,
    SchemaError,
)

SCHEMA = "weapon-overrides/1"
SET_KEYS = ("role", "kind", "archetype", "hold_class", "genre", "component", "carrier", "ammo")
ID_ENTRY_KEYS = ("set", "confirm", "exclude", "renamed_from", "note")
GLOB_ENTRY_KEYS = ("set", "confirm", "exclude", "note")


def default_overrides_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "weapon_overrides.json"


def empty_overrides() -> dict:
    return {"schema": SCHEMA, "ids": {}, "globs": {}}


def well_formed_id(value) -> bool:
    """``<pack>/<asset_id>``: exactly one slash, both halves non-empty, no whitespace."""
    if not isinstance(value, str) or value.count("/") != 1:
        return False
    pack, asset = value.split("/")
    return bool(pack) and bool(asset) and not any(c.isspace() for c in value)


def _name_of(value, key: str):
    """Shorthand string or {key: ...} object -> the string, else None."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get(key)
    return None


def _validate_set(s, where: str, errors: list[str]) -> None:
    if not isinstance(s, dict):
        errors.append(f"{where}: must be a mapping")
        return
    for key, val in s.items():
        if key not in SET_KEYS:
            errors.append(f"{where}.{key}: not an overridable field (allowed: {', '.join(SET_KEYS)})")
    enums = (("role", ROLES), ("kind", KINDS), ("archetype", ARCHETYPES), ("hold_class", HOLD_CLASSES),
             ("genre", GENRES))
    for key, allowed in enums:
        if key in s and s[key] not in allowed:
            errors.append(f"{where}.{key}: {s[key]!r} not in {list(allowed)}")
    if "component" in s:
        slot = _name_of(s["component"], "slot")
        if slot not in COMPONENT_SLOTS:
            errors.append(f"{where}.component: slot {slot!r} not in {list(COMPONENT_SLOTS)}")
        fits = s["component"].get("fits") if isinstance(s["component"], dict) else None
        if fits is not None and not (isinstance(fits, list) and set(fits) <= set(ARCHETYPES)):
            errors.append(f"{where}.component.fits: must be null or a list of archetypes")
    if "carrier" in s and _name_of(s["carrier"], "kind") not in CARRIER_KINDS:
        errors.append(f"{where}.carrier: kind not in {list(CARRIER_KINDS)}")
    if "ammo" in s and _name_of(s["ammo"], "projectile") not in AMMO_PROJECTILES:
        errors.append(f"{where}.ammo: projectile not in {list(AMMO_PROJECTILES)}")
    if s.get("role") == "carrier" and "carrier" not in s:
        errors.append(f"{where}: role carrier needs a carrier kind in the same set")
    if s.get("role") == "ammo" and "ammo" not in s:
        errors.append(f"{where}: role ammo needs a projectile in the same set")


def validate_overrides(doc) -> list[str]:
    """Every violation of ``weapon-overrides/1`` as a message naming the offending key."""
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["overrides: top level must be an object"]
    if doc.get("schema") != SCHEMA:
        errors.append(f"schema: expected {SCHEMA!r}, got {doc.get('schema')!r}")
    for key in doc:
        if key not in ("schema", "ids", "globs"):
            errors.append(f"{key}: unknown top-level key")
    for section, allowed in (("ids", ID_ENTRY_KEYS), ("globs", GLOB_ENTRY_KEYS)):
        entries = doc.get(section)
        if not isinstance(entries, dict):
            errors.append(f"{section}: must be an object")
            continue
        for key, entry in entries.items():
            where = f"{section}[{key}]"
            if not isinstance(key, str) or key.count("/") < 1 or key.startswith("/") or key.endswith("/"):
                errors.append(f"{where}: key must look like '<pack>/<asset_id>'")
            if section == "ids" and not well_formed_id(key):
                errors.append(f"{where}: an id key must be exactly '<pack>/<asset_id>'")
            if not isinstance(entry, dict):
                errors.append(f"{where}: must be an object")
                continue
            for k in entry:
                if k not in allowed:
                    hint = " (renamed_from is for exact ids only)" if k == "renamed_from" else ""
                    errors.append(f"{where}.{k}: unknown key{hint}")
            if "set" in entry:
                _validate_set(entry["set"], f"{where}.set", errors)
            for flag in ("confirm", "exclude"):
                if flag in entry and not isinstance(entry[flag], bool):
                    errors.append(f"{where}.{flag}: must be a bool")
            if "note" in entry and not isinstance(entry["note"], str):
                errors.append(f"{where}.note: must be a string")
            if "renamed_from" in entry and section == "ids":
                rf = entry["renamed_from"]
                if not isinstance(rf, list) or not all(well_formed_id(r) for r in rf):
                    errors.append(f"{where}.renamed_from: must be a list of '<pack>/<asset_id>' ids")
                elif key in rf:
                    errors.append(f"{where}.renamed_from: an id cannot be renamed from itself")
    return errors


def load_overrides(path: Path | None = None) -> dict:
    """Read and validate the overrides file (missing/unreadable JSON = exit 2, schema violation = exit 6)."""
    path = path or default_overrides_path()
    if not path.is_file():
        raise InputError(f"weapon_overrides.json not found: {path}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"weapon_overrides.json is not readable JSON: {exc}") from exc
    return checked_overrides(doc)


def checked_overrides(doc) -> dict:
    errors = validate_overrides(doc)
    if errors:
        raise SchemaError(
            "weapon_overrides.json violates weapon-overrides/1:\n  " + "\n  ".join(errors[:25]),
            details={"errors": errors},
        )
    return doc


def _glob_hits(full_id: str, doc: dict) -> list[str]:
    return [g for g in doc.get("globs", {}) if fnmatchcase(full_id, g)]


def matching_keys(full_id: str, doc: dict) -> list[str]:
    """Keys of every entry (id first, then globs by descending length then name) that applies to ``full_id``."""
    keys = [full_id] if full_id in doc.get("ids", {}) else []
    return keys + sorted(_glob_hits(full_id, doc), key=lambda g: (-len(g), g))


def effective_override(full_id: str, doc: dict | None) -> dict | None:
    """The merged override for one id, or None when nothing applies.

    Per field: exact-id entry wins, then the longest matching glob. Two equal-length globs that set the same
    field to different values are ambiguous and raise ``SchemaError`` naming both (spec section 7).
    """
    if not doc:
        return None
    id_entry = doc.get("ids", {}).get(full_id)
    globs = sorted(_glob_hits(full_id, doc), key=lambda g: (-len(g), g))
    if id_entry is None and not globs:
        return None

    merged_set: dict = {}
    set_from: dict[str, str] = {}
    sources: list[tuple[str, dict]] = ([(full_id, id_entry)] if id_entry is not None else [])
    sources += [(g, doc["globs"][g]) for g in globs]
    for key, entry in sources:
        for field, value in (entry.get("set") or {}).items():
            if field not in merged_set:
                merged_set[field] = value
                set_from[field] = key
            elif set_from[field] != key and len(set_from[field]) == len(key) and set_from[field] != full_id \
                    and merged_set[field] != value:
                raise SchemaError(
                    f"globs {set_from[field]!r} and {key!r} have equal length, both match {full_id!r} and set "
                    f"{field!r} differently"
                )
    return {
        "set": merged_set,
        "confirm": any(e.get("confirm") for _, e in sources),
        "exclude": any(e.get("exclude") for _, e in sources),
        "exclude_by": next((k for k, e in sources if e.get("exclude")), None),
        "renamed_from": sorted(set((id_entry or {}).get("renamed_from") or [])),
        "note": next((e["note"] for _, e in sources if e.get("note")), ""),
        "matched": [k for k, _ in sources],
    }
