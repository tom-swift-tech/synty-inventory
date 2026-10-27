"""``weapon_overrides.json`` (``weapon-overrides/1``): load, validate, resolve precedence (spec 3.9, 4.5).

Precedence per field, highest first: exact-id entry > longest matching glob > rule match. The file holds ids,
globs and enum values only: no measurements and no pack data (INV-1).

W8c (docs/weapon_attachments.md 6.1, D-5, INV-17) adds three categorical keys, still ids, globs, node names and enums only:
``set.attachment_slot`` / ``set.attachment_kind``, ``compatible {add, remove}`` (host ids and host globs; allowed on an id
entry and on a glob entry) and ``mounts {slot: {source: child_node | none, child: <node name>}}`` (id entries only). Any other
key inside ``compatible`` or ``mounts`` (``point``, ``up``, ``span_m``, ``offset``, a bare number...) is a SchemaError (exit 6).

W8h (A2) adds the id-only ``pair``: another sight part of the SAME pack (or null to unpair); see ``pair_overrides``.
"""

from __future__ import annotations

import json
from copy import deepcopy
from fnmatch import fnmatchcase
from pathlib import Path

from . import (
    AMMO_PROJECTILES,
    ARCHETYPES,
    ATTACH_KINDS,
    ATTACH_SLOTS,
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
SET_KEYS = ("role", "kind", "archetype", "hold_class", "genre", "component", "carrier", "ammo", "attachment_slot",
            "attachment_kind")
# `forward` and `confidence_cap` (spec 4.5, W2e) are id-only: they correct ONE weapon's measured direction / rate it for
# review, which a pattern must never do to a whole family
# `mounts` is id-only for the same reason (a host's seat is one gun's); `compatible` is also allowed on a glob (the family case)
# `pair` (A2) is id-only as well: it pairs ONE sight part with its partner, categorical (an id or null)
# `frame_axis` (G1, spec 4.5) is id-only too: it names ONE gun's forward axis, "x", "y" or "z" (categorical, no number: INV-17)
ID_ENTRY_KEYS = ("set", "confirm", "exclude", "renamed_from", "forward", "confidence_cap", "note", "compatible", "mounts", "pair", "frame_axis")
GLOB_ENTRY_KEYS = ("set", "confirm", "exclude", "note", "compatible")
COMPATIBLE_KEYS = ("add", "remove")
MOUNT_OVERRIDE_KEYS = ("source", "child")  # nothing else: a coordinate here would be pack-derived data (INV-17)
MOUNT_OVERRIDE_SOURCES = ("child_node", "none")
FORWARD_VALUES = ("+x", "-x", "+y", "-y", "+z", "-z")
FRAME_AXIS_VALUES = ("x", "y", "z")
CONFIDENCE_CAP_RANGE = (0.05, 0.59)  # inclusive: below 0.6 so the record lands in Low confidence, the classifier's floor


def default_overrides_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "weapon_overrides.json"


def empty_overrides() -> dict:
    return {"schema": SCHEMA, "ids": {}, "globs": {}}


def well_formed_id(value) -> bool:
    """``<pack>/<asset_id>``: exactly one slash, both halves non-empty, no whitespace in the pack.

    The asset half may contain spaces: real Synty asset ids do (``FX_Bullet_Trail 1``).
    """
    if not isinstance(value, str) or value.count("/") != 1:
        return False
    pack, asset = value.split("/")
    return bool(pack) and bool(asset) and not any(c.isspace() for c in pack)


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
    slot, kind = s.get("attachment_slot"), s.get("attachment_kind")
    if "attachment_slot" in s and slot not in ATTACH_SLOTS:
        errors.append(f"{where}.attachment_slot: {slot!r} not in {list(ATTACH_SLOTS)}")
    all_kinds = sorted({k for kinds in ATTACH_KINDS.values() for k in kinds})
    if "attachment_kind" in s and kind not in all_kinds:
        errors.append(f"{where}.attachment_kind: {kind!r} not in {all_kinds}")
    elif slot in ATTACH_SLOTS and "attachment_kind" in s and kind not in ATTACH_KINDS[slot]:
        errors.append(f"{where}.attachment_kind: {kind!r} is not a kind of slot {slot} ({list(ATTACH_KINDS[slot])})")
    if s.get("role") == "carrier" and "carrier" not in s:
        errors.append(f"{where}: role carrier needs a carrier kind in the same set")
    if s.get("role") == "ammo" and "ammo" not in s:
        errors.append(f"{where}: role ammo needs a projectile in the same set")


def validate_compatible(val, where: str, errors: list[str]) -> None:
    """``{"add": [pattern], "remove": [pattern]}``: host ids or host globs (``<pack>/<pattern>``) and nothing else."""
    if not isinstance(val, dict) or not val:
        errors.append(f"{where}: must be a non-empty object with add and/or remove")
        return
    for key, patterns in val.items():
        if key not in COMPATIBLE_KEYS:
            errors.append(f"{where}.{key}: not allowed (only {', '.join(COMPATIBLE_KEYS)}; ids and globs, never numbers)")
        elif not isinstance(patterns, list) or not all(well_formed_id(p) for p in patterns):
            errors.append(f"{where}.{key}: must be a list of '<pack>/<asset id or glob>' strings")


def validate_mounts(val, where: str, errors: list[str]) -> None:
    """``{slot: {"source": "child_node", "child": <node name>} | {"source": "none"}}``: categorical only (INV-17, AC74).

    A key other than ``source`` / ``child`` (``point``, ``up``, ``span_m``, ``offset``, a number...) is rejected: the file
    selects a seat, it never places one.
    """
    if not isinstance(val, dict) or not val:
        errors.append(f"{where}: must be a non-empty object slot -> {{source, child}}")
        return
    for slot, entry in val.items():
        here = f"{where}.{slot}"
        if slot not in ATTACH_SLOTS:
            errors.append(f"{here}: slot not in {list(ATTACH_SLOTS)}")
        if not isinstance(entry, dict):
            errors.append(f"{here}: must be an object with source (and child)")
            continue
        for key in entry:
            if key not in MOUNT_OVERRIDE_KEYS:
                errors.append(f"{here}.{key}: not allowed (only {', '.join(MOUNT_OVERRIDE_KEYS)}: the file never carries "
                              "coordinates or measured numbers, INV-17)")
        source = entry.get("source")
        if source not in MOUNT_OVERRIDE_SOURCES:
            errors.append(f"{here}.source: {source!r} not in {list(MOUNT_OVERRIDE_SOURCES)}")
        elif source == "child_node" and not (isinstance(entry.get("child"), str) and entry["child"]):
            errors.append(f"{here}.child: source child_node needs the GLB node name")
        elif source == "none" and "child" in entry:
            errors.append(f"{here}.child: not allowed with source none")


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
                    hint = (f" ({k} is for exact ids only)"
                            if k in ("renamed_from", "forward", "confidence_cap", "mounts", "pair", "frame_axis") else "")
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
            if "compatible" in entry:
                validate_compatible(entry["compatible"], f"{where}.compatible", errors)
            if "mounts" in entry and section == "ids":
                validate_mounts(entry["mounts"], f"{where}.mounts", errors)
            if "pair" in entry and section == "ids":
                partner = entry["pair"]
                if partner is not None:
                    if not well_formed_id(partner):
                        errors.append(f"{where}.pair: must be null or a '<pack>/<asset_id>' id")
                    elif partner == key:
                        errors.append(f"{where}.pair: a part cannot be paired with itself")
                    elif partner.split("/")[0] != key.split("/")[0]:
                        errors.append(f"{where}.pair: {partner!r} is in another pack (a pair is one pack's set, INV-20)")
            if "forward" in entry and section == "ids" and entry["forward"] not in FORWARD_VALUES:
                errors.append(f"{where}.forward: {entry['forward']!r} not in {list(FORWARD_VALUES)}")
            if "frame_axis" in entry and section == "ids" and entry["frame_axis"] not in FRAME_AXIS_VALUES:
                errors.append(f"{where}.frame_axis: {entry['frame_axis']!r} not in {list(FRAME_AXIS_VALUES)}")
            if "confidence_cap" in entry and section == "ids":
                cap = entry["confidence_cap"]
                lo, hi = CONFIDENCE_CAP_RANGE
                # a bool is an int in Python: reject it explicitly (true would otherwise read as 1)
                if isinstance(cap, bool) or not isinstance(cap, (int, float)) or not lo <= cap <= hi:
                    errors.append(f"{where}.confidence_cap: must be a number from {lo} to {hi}, got {cap!r}")
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
    compat_sources = [
        {"key": key, "exact": key == full_id, "add": sorted(set(entry["compatible"].get("add") or [])),
         "remove": sorted(set(entry["compatible"].get("remove") or []))}
        for key, entry in sources if entry.get("compatible")
    ]
    return {
        "set": merged_set,
        "confirm": any(e.get("confirm") for _, e in sources),
        "exclude": any(e.get("exclude") for _, e in sources),
        "exclude_by": next((k for k, e in sources if e.get("exclude")), None),
        "renamed_from": sorted(set((id_entry or {}).get("renamed_from") or [])),
        # id-only (a glob entry cannot carry them, see validate_overrides)
        "forward": (id_entry or {}).get("forward"),
        "confidence_cap": (id_entry or {}).get("confidence_cap"),
        "frame_axis": (id_entry or {}).get("frame_axis"),
        # W8c: categorical attachment keys. `compat_sources` keeps every entry that carries a `compatible` block in
        # precedence order (the exact id first, then globs by descending length) for `compatible_verdict`; `mounts` is id-only
        "compat_sources": compat_sources,
        "mounts": deepcopy((id_entry or {}).get("mounts")) or None,
        "note": next((e["note"] for _, e in sources if e.get("note")), ""),
        "matched": [k for k, _ in sources],
    }


def pair_overrides(doc: dict | None) -> dict[str, str | None]:
    """``{part id: partner id or None}`` from the id entries that carry a ``pair`` key (A2, spec 3.5 and 6.1).

    A ``null`` is an explicit unpair, so it is kept; an id entry without the key is absent. The entry acts on both members
    (``pairs.apply_pairs`` makes the relation symmetric), so naming the relation on one side is enough.
    """
    return {k: v["pair"] for k, v in sorted(((doc or {}).get("ids") or {}).items()) if "pair" in v}


def compatible_verdict(sources: list[dict], part_id: str, host_id: str) -> str | None:
    """``"add"``, ``"remove"`` or None: what the ``compatible`` overrides of one part say about one host (AC74).

    ``sources`` is ``effective_override(part)["compat_sources"]``: the exact-id entry first, then the matching globs by
    descending length. The first entry that names the host decides (exact id > longest glob); inside one entry the most
    specific host pattern wins (the host's exact id over a glob, a longer glob over a shorter) and a remove beats an add
    of equal specificity. Two glob entries of equal length that name the host differently are ambiguous: SchemaError.
    """
    def decide(src: dict) -> str | None:
        best: tuple[int, int] | None = None
        verdict = None
        for kind in ("add", "remove"):  # remove last: it wins a tie
            for pat in src[kind]:
                if fnmatchcase(host_id, pat):
                    spec = (1 if pat == host_id else 0, len(pat))
                    if best is None or spec >= best:
                        best, verdict = spec, kind
        return verdict

    i = 0
    while i < len(sources):
        group = [sources[i]]
        while i + len(group) < len(sources) and not sources[i]["exact"] \
                and len(sources[i + len(group)]["key"]) == len(sources[i]["key"]):
            group.append(sources[i + len(group)])
        i += len(group)
        verdicts = [(src["key"], decide(src)) for src in group]
        verdicts = [(k, v) for k, v in verdicts if v is not None]
        if len({v for _, v in verdicts}) > 1:
            raise SchemaError(f"globs {verdicts[0][0]!r} and {verdicts[1][0]!r} have equal length, both match {part_id!r} "
                              f"and disagree on host {host_id!r} (compatible add versus remove)")
        if verdicts:
            return verdicts[0][1]
    return None
