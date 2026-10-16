"""``weapons apply-corrections``: merge a ``weapon-corrections/1`` file into ``weapon_overrides.json`` (spec 3.9).

This is the writing side of the override table; W1 owns the reading side (``overrides.py``: validation and
precedence), which is not changed here. The merge rules:

* the target is an exact id or a glob; a later correction for the same target replaces the earlier one's
  ``set`` / ``confirm`` / ``exclude`` / ``note``;
* ``forward`` and ``confidence_cap`` (exact-id entries, written by hand, W2e) are carried over unchanged when a
  later correction replaces the classification; a correction cannot create or change them;
* ``renamed_from`` (exact-id targets only) is *unioned* into the entry as a sorted, de-duplicated list, so it
  survives a later ``set`` correction and a correction that carries only ``renamed_from`` never wipes a ``set``;
* applying the same file twice is a no-op (INV-10): every rule above is idempotent and the file is written in
  one canonical form (sorted keys, 2-space indent, LF, trailing newline), and not at all when nothing changed.

``exclude`` is only *stored* here. It takes effect at the next ``weapons build``, which moves the record to
``excluded.json`` with reason ``override``; this module never touches the directory.
"""

from __future__ import annotations

import json
from copy import deepcopy
from fnmatch import fnmatchcase
from pathlib import Path

from ..paths import ConfigError
from . import EXIT_OK, InputError, SchemaError, write_text_lf
from . import overrides as _ov
from .cli import _catalogs, _emit, _guarded

SCHEMA = "weapon-corrections/1"
CORRECTION_KEYS = ("target", "set", "confirm", "exclude", "renamed_from", "note")
_CLASSIFY_KEYS = ("set", "confirm", "exclude")


# -- validation -------------------------------------------------------------------------------------------


def _entry_of(corr: dict) -> dict:
    """The classification part of a correction as an overrides entry (falsy actions are not stored)."""
    entry: dict = {}
    if corr.get("set"):
        entry["set"] = deepcopy(corr["set"])
    if corr.get("confirm") is True:
        entry["confirm"] = True
    if corr.get("exclude") is True:
        entry["exclude"] = True
    if corr.get("note"):
        entry["note"] = corr["note"]
    return entry


def target_of(corr: dict) -> tuple[str, str]:
    """``("ids" | "globs", key)`` for a (valid) correction."""
    target = corr["target"]
    return ("ids", target["id"]) if "id" in target else ("globs", target["glob"])


def validate_corrections(doc) -> list[str]:
    """Every violation of ``weapon-corrections/1`` as a message naming the offending correction."""
    if not isinstance(doc, dict):
        return ["corrections: top level must be an object"]
    errors: list[str] = []
    if doc.get("schema") != SCHEMA:
        errors.append(f"schema: expected {SCHEMA!r}, got {doc.get('schema')!r}")
    for key in doc:
        if key not in ("schema", "corrections"):
            errors.append(f"{key}: unknown top-level key")
    items = doc.get("corrections")
    if not isinstance(items, list):
        errors.append("corrections: must be a list")
        return errors
    for i, corr in enumerate(items):
        where = f"corrections[{i}]"
        if not isinstance(corr, dict):
            errors.append(f"{where}: must be an object")
            continue
        for key in corr:
            if key not in CORRECTION_KEYS:
                errors.append(f"{where}.{key}: unknown key")
        target = corr.get("target")
        key_ok = False
        if not isinstance(target, dict) or sorted(target) not in (["id"], ["glob"]) \
                or not isinstance(next(iter(target.values())), str):
            errors.append(f"{where}.target: must be exactly one of {{'id': ...}} or {{'glob': ...}}")
        elif "id" in target:
            key_ok = _ov.well_formed_id(target["id"])
            if not key_ok:
                errors.append(f"{where}.target.id: must be exactly '<pack>/<asset_id>'")
        else:
            glob = target["glob"]
            key_ok = glob.count("/") >= 1 and not glob.startswith("/") and not glob.endswith("/")
            if not key_ok:
                errors.append(f"{where}.target.glob: must look like '<pack>/<pattern>'")
        for flag in ("confirm", "exclude"):
            if flag in corr and not isinstance(corr[flag], bool):
                errors.append(f"{where}.{flag}: must be a bool")
        if "note" in corr and not isinstance(corr["note"], str):
            errors.append(f"{where}.note: must be a string")
        if "set" in corr and not isinstance(corr["set"], dict):
            errors.append(f"{where}.set: must be an object")
        rf = corr.get("renamed_from")
        if "renamed_from" in corr:
            if not isinstance(rf, list) or not all(_ov.well_formed_id(r) for r in rf):
                errors.append(f"{where}.renamed_from: must be a list of '<pack>/<asset_id>' ids")
            elif isinstance(target, dict) and "id" not in target:
                errors.append(f"{where}.renamed_from: needs an exact-id target, not a glob")
            elif isinstance(target, dict) and target.get("id") in rf:
                errors.append(f"{where}.renamed_from: an id cannot be renamed from itself")
        has_action = bool(corr.get("set")) or corr.get("confirm") is True or corr.get("exclude") is True \
            or bool(rf)
        if not has_action:
            errors.append(f"{where}: carries no action (set, confirm, exclude or renamed_from)")
        if corr.get("exclude") is True and (corr.get("set") or corr.get("confirm") is True):
            errors.append(f"{where}: exclude cannot be combined with set or confirm")
        # enum / shape checks of `set` are the override validator's job: run the entry through it
        if key_ok and isinstance(corr.get("set", {}), dict):
            section, key = target_of(corr)
            trial = {"schema": _ov.SCHEMA, "ids": {}, "globs": {}}
            trial[section][key] = _entry_of(corr)
            errors += [f"{where}: {e}" for e in _ov.validate_overrides(trial)]
    return errors


# -- merge ------------------------------------------------------------------------------------------------


def _merged_entry(old: dict | None, corr: dict) -> dict:
    old = old or {}
    classify = [k for k in _CLASSIFY_KEYS if corr.get(k)]  # the correction decides the classification
    if classify:
        new = _entry_of(corr)
        for kept in ("renamed_from", "forward", "confidence_cap"):  # not classification: a later correction keeps them
            if kept in old:
                new[kept] = deepcopy(old[kept])
    else:
        new = deepcopy(old)  # renamed_from-only: everything else stays
        if corr.get("note"):
            new["note"] = corr["note"]
    if corr.get("renamed_from"):
        new["renamed_from"] = sorted(set(new.get("renamed_from") or []) | set(corr["renamed_from"]))
    return new


def _check_claims(doc: dict, live_ids: set[str] | None) -> None:
    """INV-13 on the merged table: an old id is never live and is claimed by one entry only (exit 6)."""
    claimed: dict[str, str] = {}
    for key in sorted(doc["ids"]):
        for old in doc["ids"][key].get("renamed_from") or []:
            if live_ids is not None and old in live_ids:
                raise SchemaError(f"renamed_from {old!r} (claimed by {key}) equals a live record id")
            if old in claimed and claimed[old] != key:
                raise SchemaError(f"renamed_from {old!r} is claimed by both {claimed[old]} and {key}")
            claimed[old] = key


def apply_corrections(
    corrections: dict, overrides: dict, *, known_packs: set[str] | None = None, live_ids: set[str] | None = None,
    all_ids: set[str] | None = None,
) -> tuple[dict, list[str]]:
    """``(new overrides, warnings)``; ``overrides`` is not modified.

    Raises ``SchemaError`` (exit 6) for an invalid corrections file or a merged table that violates
    ``weapon-overrides/1``, INV-13 or the equal-length-glob rule, so the caller can write nothing. ``known_packs``
    (cataloged pack ids) drives the unknown-pack warning, ``live_ids`` the INV-13 live-id check and ``all_ids``
    (live plus excluded ids) the glob-conflict check; each is skipped when None.
    """
    errors = validate_corrections(corrections)
    if errors:
        raise SchemaError("corrections violate weapon-corrections/1:\n  " + "\n  ".join(errors[:25]),
                          details={"errors": errors})
    new = deepcopy(overrides)
    warnings: list[str] = []
    for i, corr in enumerate(corrections["corrections"]):
        section, key = target_of(corr)
        new[section][key] = _merged_entry(new[section].get(key), corr)
        if known_packs is not None:
            pack_part = key.split("/", 1)[0]
            if not any(fnmatchcase(p, pack_part) for p in known_packs):
                warnings.append(f"corrections[{i}]: pack {pack_part!r} of {key!r} is not cataloged; stored anyway")
    errors = _ov.validate_overrides(new)
    if errors:
        raise SchemaError("the merged overrides violate weapon-overrides/1:\n  " + "\n  ".join(errors[:25]),
                          details={"errors": errors})
    _check_claims(new, live_ids)
    for full_id in sorted(all_ids or ()):
        _ov.effective_override(full_id, new)  # SchemaError on two equal-length globs that disagree
    return new, warnings


def diff_overrides(old: dict, new: dict) -> list[dict]:
    """One row per override key whose entry differs between the two tables."""
    rows = []
    for section in ("ids", "globs"):
        for key in sorted(set(old[section]) | set(new[section])):
            before, after = old[section].get(key), new[section].get(key)
            if before != after:
                rows.append({"section": section, "key": key, "change": "added" if before is None else "changed",
                             "before": before, "after": after})
    return rows


def overrides_text(doc: dict) -> str:
    """The committed file's canonical form: sorted keys, 2-space indent, LF, trailing newline."""
    return json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


# -- CLI --------------------------------------------------------------------------------------------------


def _live_context(args, cfg) -> tuple[set[str] | None, set[str] | None, set[str] | None]:
    """``(known packs, live record ids, all ids)`` from the built directory, or Nones when there is none."""
    from .directory import DIRECTORY_NAME, EXCLUDED_NAME, read_json, weapons_dir

    try:
        wdir = weapons_dir(_catalogs(args, cfg))
    except ConfigError:
        return None, None, None
    if not (wdir / DIRECTORY_NAME).is_file():
        return None, None, None
    directory = read_json(wdir / DIRECTORY_NAME)
    live = {w["id"] for w in directory.get("weapons", [])}
    excluded = read_json(wdir / EXCLUDED_NAME) if (wdir / EXCLUDED_NAME).is_file() else {}
    others = {e["id"] for e in excluded.get("excluded", [])}
    return {p["pack"] for p in directory.get("packs", [])}, live, live | others


@_guarded
def cmd(args, cfg) -> int:
    """``apply-corrections FILE [--dry-run]``.

    ``args.overrides_path`` (not a CLI option) lets a caller aim the merge at another file; the default is the
    committed ``data/weapon_overrides.json``. Without a built directory the pack and live-id checks are skipped
    with a warning, except that a ``renamed_from`` correction is refused (exit 2): INV-13 cannot be checked.
    """
    src = Path(args.file)
    if not src.is_file():
        raise InputError(f"corrections file not found: {src}")
    try:
        corrections = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"corrections file is not readable JSON: {exc}") from exc

    target_path = getattr(args, "overrides_path", None) or _ov.default_overrides_path()
    current = _ov.load_overrides(target_path)
    known, live, every = _live_context(args, cfg)
    pre_warnings: list[str] = []
    if live is None:
        wants_rename = isinstance(corrections, dict) and any(
            isinstance(c, dict) and c.get("renamed_from") for c in corrections.get("corrections") or [])
        if wants_rename:
            raise InputError("no built weapon directory: renamed_from cannot be checked against live ids "
                             "(INV-13); run `weapons build` first")
        pre_warnings.append("no built weapon directory: target packs and glob conflicts were not checked")

    new, warnings = apply_corrections(corrections, current, known_packs=known, live_ids=live, all_ids=every)
    diff = diff_overrides(current, new)
    text = overrides_text(new)
    wrote = False
    if not args.dry_run and (not target_path.is_file() or target_path.read_bytes() != text.encode("utf-8")):
        write_text_lf(target_path, text)
        wrote = True
    _emit({"ok": True, "dry_run": bool(args.dry_run), "applied": len(corrections["corrections"]),
           "changed": bool(diff), "wrote": wrote, "warnings": pre_warnings + warnings, "diff": diff})
    return EXIT_OK
