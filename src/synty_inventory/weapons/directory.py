"""``build_directory``: the weapon directory from the per-pack catalogs (spec 3.1, 3.3, 4.2, 4.3).

Pure given its inputs: no clock, no network, no randomness (INV-4). Catalogs are only read (INV-5); the single
write path is ``write_directory``, which touches nothing but ``<catalogs>/weapons/``. W1 writes records with
``geometry: null`` (flag ``unmeasured``, reason ``no_geometry``) and all-null ``hints``; W2 replaces those stubs.
"""

from __future__ import annotations

import json
from copy import deepcopy
from fnmatch import fnmatchcase
from pathlib import Path

from .. import weapons as _pkg  # read versions at call time (a test may bump WEAPON_VERSION)
from ..paths import is_pack_catalog_file
from ..schema import migrate_catalog
from . import InputError, SchemaError, digest, to_text, write_text_lf
from .candidates import evaluate_candidate
from .classify import classify
from .overrides import effective_override, load_overrides
from .rules import load_rules
from .schema import validate_directory

DIRECTORY_NAME = "directory.json"
EXCLUDED_NAME = "excluded.json"


def weapons_dir(catalogs_dir: Path) -> Path:
    return catalogs_dir / "weapons"


def load_pack_catalogs(catalogs_dir: Path) -> dict[str, dict]:
    """pack_id -> catalog doc for every top-level pack catalog (``weapons/`` and sidecars are invisible)."""
    if not catalogs_dir.is_dir():
        raise InputError(f"catalogs directory not found: {catalogs_dir}")
    docs: dict[str, dict] = {}
    for path in sorted(catalogs_dir.glob("*.json")):
        if not is_pack_catalog_file(path):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InputError(f"catalog unreadable: {path.name}: {exc}") from exc
        if not isinstance(raw, dict) or not raw.get("pack_id") or not isinstance(raw.get("assets"), list):
            continue  # a sidecar that is not a pack catalog
        doc = migrate_catalog(raw)
        if doc["pack_id"] in docs:
            raise InputError(f"two catalog files declare pack_id {doc['pack_id']}")
        docs[doc["pack_id"]] = doc
    return docs


def _pack_settings(pack_settings: dict | None) -> dict:
    if pack_settings is not None:
        return pack_settings
    from ..packs.profile import load_settings_table

    return load_settings_table()


def _record(asset: dict, pack_id: str, cls: dict, source: str, renamed_from: list[str]) -> dict:
    files = deepcopy(asset.get("files") or {})
    files.setdefault("glb_node", None)
    flags = sorted(set(cls["flags"]) | {"unmeasured"})
    reasons = sorted(set(cls["reasons"]) | {"no_geometry"})
    return {
        "schema_version": 1,
        "id": f"{pack_id}/{asset['id']}",
        "pack": pack_id,
        "asset_id": asset["id"],
        "files": files,
        "renamed_from": sorted(set(renamed_from)),
        "family": cls["family"],
        "role": cls["role"],
        "kind": cls["kind"],
        "genre": cls["genre"],
        "genre_source": cls["genre_source"],
        "archetype": cls["archetype"],
        "hold_class": cls["hold_class"],
        "component": cls["component"],
        "carrier": cls["carrier"],
        "ammo": cls["ammo"],
        "flags": flags,
        "duplicate_of": None,
        "geometry": None,
        "hints": {"size_class": None, "size_basis": None, "inventory_cells": None, "weight_class": None,
                  "quality_tier": None, "ammo_family": None},
        "visuals": {"icon": None, "thumb": None, "icon_input_sha": None, "variants": []},
        "review": {
            "status": cls["status"],
            "confidence": cls["confidence"],
            "reasons": reasons,
            "matched_rule": cls["matched_rule"],
            "candidate_source": source,
        },
        "provenance": dict(cls["provenance"]),
    }


def _mark_duplicates(records: list[dict]) -> None:
    """duplicate_of = id of the first record (by id) sharing the same GLB file and node selection."""
    for rec in records:  # reset, so carried-over records from a partial build are recomputed on the union
        rec["duplicate_of"] = None
        rec["flags"] = [f for f in rec["flags"] if f != "duplicate_mesh"]
    owner: dict[str, str] = {}
    for rec in sorted(records, key=lambda r: r["id"]):
        glb = rec["files"].get("glb")
        if not glb:
            continue
        key = json.dumps([glb, rec["files"].get("glb_node")], sort_keys=True)
        if key in owner:
            rec["duplicate_of"] = owner[key]
            rec["flags"] = sorted(set(rec["flags"]) | {"duplicate_mesh"})
        else:
            owner[key] = rec["id"]


def _check_renames(records: list[dict]) -> None:
    """INV-13: a renamed id is never a live record id and is claimed by at most one record (exit 6)."""
    live = {r["id"] for r in records}
    claimed: dict[str, str] = {}
    for rec in sorted(records, key=lambda r: r["id"]):
        for old in rec["renamed_from"]:
            if old in live:
                raise SchemaError(f"renamed_from {old!r} (claimed by {rec['id']}) equals a live record id")
            if old in claimed:
                raise SchemaError(f"renamed_from {old!r} is claimed by both {claimed[old]} and {rec['id']}")
            claimed[old] = rec["id"]


def _counts(records: list[dict]) -> dict:
    def tally(values):
        out: dict[str, int] = {}
        for v in values:
            if v is not None:
                out[v] = out.get(v, 0) + 1
        return dict(sorted(out.items()))

    return {
        "by_role": tally(r["role"] for r in records),
        "by_kind": tally(r["kind"] for r in records),
        "by_genre": tally(r["genre"] for r in records),
        "by_archetype": tally(r["archetype"] for r in records),
        "by_status": tally(r["review"]["status"] for r in records),
    }


def _stale_overrides(overrides: dict, all_ids: set[str], pack_ids: set[str], *, partial: bool) -> list[dict]:
    rows = []

    def relevant(key: str) -> bool:
        if not partial:
            return True
        pack_part = key.split("/", 1)[0]
        return any(fnmatchcase(p, pack_part) for p in pack_ids)

    for key in sorted(overrides.get("ids", {})):
        if relevant(key) and key not in all_ids:
            rows.append({"key": key, "kind": "id"})
    for key in sorted(overrides.get("globs", {})):
        if relevant(key) and not any(fnmatchcase(i, key) for i in all_ids):
            rows.append({"key": key, "kind": "glob"})
    return rows


def build_directory_report(
    catalogs_dir: Path,
    *,
    packs: list[str] | None = None,
    rules: dict | None = None,
    overrides: dict | None = None,
    measure: bool = True,  # noqa: ARG001 (W2 measures geometry; W1 leaves every record unmeasured)
    threejs_v2_dir: Path | None = None,  # noqa: ARG001 (W2)
    pack_settings: dict | None = None,
    base: tuple[dict, dict] | None = None,
) -> tuple[dict, dict, dict]:
    """``(directory doc, excluded doc, report)``.

    ``pack_settings`` (pack_id -> {setting, era}) defaults to the curated table; ``base`` is the previous
    ``(directory, excluded)`` pair that a ``packs=`` partial build merges into (other packs stay untouched).
    The report carries stale overrides, warnings and live-run statistics; it is never part of the directory.
    """
    rules = rules if rules is not None else load_rules()
    overrides = overrides if overrides is not None else load_overrides()
    settings = _pack_settings(pack_settings)
    docs = load_pack_catalogs(catalogs_dir)
    if not docs:
        raise InputError(f"no pack catalogs found in {catalogs_dir}")

    if packs:
        missing = sorted(set(packs) - set(docs))
        if missing:
            raise InputError(f"unknown pack(s), no catalog in {catalogs_dir}: {', '.join(missing)}")
        selected = sorted(set(packs))
    else:
        selected = sorted(docs)
    partial = bool(packs) and set(selected) != set(docs)

    rules_digest, overrides_digest = digest(rules), digest(overrides)
    records: list[dict] = []
    excluded: list[dict] = []
    pack_rows: list[dict] = []
    all_ids: set[str] = set()
    warnings: list[str] = []

    if partial:
        if base is None:
            raise InputError("a --pack build needs the existing directory to merge into; run a full build first")
        base_dir, base_excl = base
        if (base_dir.get("weapon_version") != _pkg.WEAPON_VERSION
                or base_dir.get("rules_digest") != rules_digest
                or base_dir.get("overrides_digest") != overrides_digest):
            raise InputError("the existing directory was built with other rules/overrides/version; run a full build")
        keep = set(selected)
        records += [deepcopy(w) for w in base_dir["weapons"] if w["pack"] not in keep]
        excluded += [deepcopy(e) for e in base_excl["excluded"] if e["id"].split("/", 1)[0] not in keep]
        pack_rows += [deepcopy(p) for p in base_dir["packs"] if p["pack"] not in keep]

    for pack_id in selected:
        doc = docs[pack_id]
        if pack_id not in settings:
            warnings.append(f"pack {pack_id} is missing from pack_settings: genre falls back to the archetype table")
        seen_asset_ids: set[str] = set()
        n_records = n_excluded = 0
        for asset in doc["assets"]:
            aid = asset.get("id")
            if not isinstance(aid, str) or not aid:
                raise SchemaError(f"{pack_id}: an asset has no string id")
            if aid in seen_asset_ids:
                raise SchemaError(f"{pack_id}: duplicate asset id {aid}")
            seen_asset_ids.add(aid)
            full_id = f"{pack_id}/{aid}"
            all_ids.add(full_id)

            ev = evaluate_candidate(asset, pack_id, rules)
            id_entry = overrides.get("ids", {}).get(full_id) or {}
            eff = effective_override(full_id, overrides) if (ev["candidate"] or id_entry) else None
            wants_in = bool(id_entry.get("set") or id_entry.get("confirm"))
            placeable = asset.get("placeable") is not False

            accepted, source, reason, matched = ev["accepted"], ev["source"], ev["reason"], ev["matched"]
            if not ev["candidate"]:
                # an exact-id set/confirm override declares the asset a weapon the patterns missed
                if wants_in and placeable and not id_entry.get("exclude"):
                    accepted, source = True, "name_token"
                else:
                    continue
            elif not accepted and reason != "nonplaceable" and placeable and wants_in and not id_entry.get("exclude"):
                accepted = True  # "Restore": an explicit override beats a name-pattern rejection
            if accepted and eff and eff["exclude"]:
                accepted, reason = False, "override"
                matched = "override:" + eff["exclude_by"]
            if not accepted:
                excluded.append({"id": full_id, "reason": reason, "matched": matched, "source": source})
                n_excluded += 1
                continue
            cls = classify(asset, pack_id, rules, overrides, settings.get(pack_id), candidate_source=source)
            records.append(_record(asset, pack_id, cls, source, (eff or {}).get("renamed_from") or []))
            n_records += 1
        pack_rows.append({
            "pack": pack_id,
            "scanned_at": doc.get("scanned_at"),
            "asset_count": len(doc["assets"]),
            "candidates": n_records + n_excluded,
            "records": n_records,
            "excluded": n_excluded,
        })

    _mark_duplicates(records)
    _check_renames(records)
    records.sort(key=lambda r: r["id"])
    excluded.sort(key=lambda e: e["id"])
    pack_rows.sort(key=lambda p: p["pack"])

    directory = {
        "schema": "weapon-directory/1",
        "weapon_version": _pkg.WEAPON_VERSION,
        "geometry_version": _pkg.WEAPON_GEOMETRY_VERSION,
        "rules_digest": rules_digest,
        "overrides_digest": overrides_digest,
        "packs": pack_rows,
        "counts": _counts(records),
        "weapons": records,
    }
    excluded_doc = {"schema": "weapon-excluded/1", "excluded": excluded}

    mine = [r for r in records if r["pack"] in set(selected)]
    with_glb = [r for r in mine if r["files"].get("glb")]
    n = len(mine) or 1
    report = {
        "packs_built": selected,
        "records": len(mine),
        "excluded": sum(1 for e in excluded if e["id"].split("/", 1)[0] in set(selected)),
        "counts": _counts(mine),
        "low_confidence_share": round(sum(1 for r in mine if r["review"]["confidence"] < 0.6) / n, 4),
        "unknown_share": round(sum(1 for r in mine if r["archetype"] == "unknown" and r["role"] in ("whole", "emplaced")) / n, 4),
        "geometry_coverage": (round(sum(1 for r in with_glb if r["geometry"] is not None) / len(with_glb), 4)
                              if with_glb else 1.0),
        "stale_overrides": _stale_overrides(overrides, all_ids, set(selected), partial=partial),
        "warnings": sorted(warnings),
    }
    return directory, excluded_doc, report


def build_directory(catalogs_dir: Path, **kwargs) -> tuple[dict, dict]:
    """``(directory doc, excluded doc)``; same keyword arguments as ``build_directory_report``."""
    directory, excluded, _ = build_directory_report(catalogs_dir, **kwargs)
    return directory, excluded


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"unreadable JSON {path}: {exc}") from exc


def load_directory(catalogs_dir: Path, path: Path | None = None) -> dict:
    path = path or weapons_dir(catalogs_dir) / DIRECTORY_NAME
    if not path.is_file():
        raise InputError(f"no weapon directory at {path}; run `weapons build` first")
    return read_json(path)


def write_directory(catalogs_dir: Path, directory: dict, excluded: dict) -> tuple[Path, Path]:
    """Validate then write ``weapons/directory.json`` and ``weapons/excluded.json`` (LF, sorted keys).

    A schema violation raises ``SchemaError`` before anything is written (spec section 7).
    """
    errors = validate_directory(directory, excluded, pre_geometry=True)
    if errors:
        raise SchemaError("the built directory violates weapon-directory/1:\n  " + "\n  ".join(errors[:25]),
                          details={"errors": errors})
    out = weapons_dir(catalogs_dir)
    dpath, epath = out / DIRECTORY_NAME, out / EXCLUDED_NAME
    write_text_lf(dpath, to_text(directory))
    write_text_lf(epath, to_text(excluded))
    return dpath, epath
