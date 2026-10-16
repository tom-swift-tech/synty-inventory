"""The ``weapons_directory`` gauntlet gate (docs/weapon_directory.md section 6, AC30).

``check_weapons_directory(catalogs_dir)`` audits the written ``<catalogs>/weapons/directory.json`` + ``excluded.json``
against the pack catalogs and the committed rules and overrides. It is read-only (INV-5): the pack catalogs and the
sidecar are never written, and the "clean rebuild" of the gold regression runs in memory.

Checks (each is a row of ``checks``; the gate is the AND of the failing ones):

* ``directory_current``  the directory was built with this ``WEAPON_VERSION``, these rules and these overrides (a
  stale directory cannot be audited against the current inputs, so it fails with the instruction to rebuild);
* ``schema``             ``schema.validate_directory`` finds no violation (every enum, the id forms, the nullability
  rules);
* ``coverage``           per pack ``records + excluded == candidates`` (the stored row) AND every asset that
  ``evaluate_candidate`` calls a candidate, evaluated here from the catalogs with the rules and independent of the
  stored counts, has exactly one row; a row that no candidate and no exact-id override explains fails;
* ``ids_unique``         no id twice among records, among excluded rows, or across the two;
* ``geometry``           ``geometry`` is non-null for at least ``GEOMETRY_FLOOR`` of the records whose catalog has a GLB;
* ``muzzle``             every ``kind == ranged``, non-bow, ``whole`` record with geometry has a ``muzzle``;
* ``overrides_current``  every override key still matches at least one catalog asset. A stale one is LISTED either
  way and fails the gate only when ``strict`` is true (the ``--strict`` of ``build`` and ``gauntlet``);
* ``gold``               every id in the overrides file classifies to its overridden values after a clean rebuild
  (the scalar fields ``role``, ``kind``, ``archetype``, ``hold_class``, ``genre``; ``exclude`` means an excluded row
  with reason ``override``). An id that no longer exists is not a gold case, it is a stale override. An id entry
  with a ``forward`` (spec 4.5, W2e) is also a gold case, checked on the audited directory itself (the clean rebuild
  does not measure): its record needs ``geometry.axes.forward == forward`` and ``forward_source == "override"``, so a
  directory built before the override was added, or one whose geometry the override could not reach, fails. An
  excluded id is skipped.

A gate that finds no directory is skipped (``skipped`` true, ``ok`` true): a library that never ran ``weapons build``
is not a failure of the gauntlet.
"""

from __future__ import annotations

from pathlib import Path

from .. import weapons as _pkg
from . import NON_WEAPON_ROLES, WeaponsError, digest
from .candidates import evaluate_candidate
from .directory import (
    DIRECTORY_NAME,
    EXCLUDED_NAME,
    _stale_overrides,
    build_directory_report,
    load_pack_catalogs,
    read_json,
    weapons_dir,
)
from .overrides import load_overrides
from .rules import load_rules
from .schema import validate_directory

GEOMETRY_FLOOR = 0.97  # AC30: geometry non-null for at least 97 % of the records whose catalog has a GLB
GOLD_FIELDS = ("role", "kind", "archetype", "hold_class", "genre")
SHOWN = 5  # offenders listed per check


def _show(items: list, limit: int = SHOWN) -> str:
    rows = [str(i) for i in items[:limit]]
    return ", ".join(rows) + (f" (+{len(items) - limit} more)" if len(items) > limit else "")


def _check(name: str, ok: bool, detail: str) -> dict:
    return {"check": name, "ok": ok, "detail": detail}


def _dupes(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        if i in seen and i not in out:
            out.append(i)
        seen.add(i)
    return sorted(out)


def _coverage(directory: dict, excluded: dict, docs: dict[str, dict], rules: dict, overrides: dict) -> dict:
    rows_by_pack: dict[str, set[str]] = {}
    for rid in [w["id"] for w in directory["weapons"]] + [e["id"] for e in excluded["excluded"]]:
        rows_by_pack.setdefault(rid.split("/", 1)[0], set()).add(rid)
    stored = {p["pack"]: p for p in directory["packs"]}
    problems: list[str] = []
    n_candidates = 0
    for pack_id in sorted(set(docs) | set(rows_by_pack)):
        doc = docs.get(pack_id)
        if doc is None:
            problems.append(f"{pack_id}: in the directory but has no catalog")
            continue
        candidates = {
            f"{pack_id}/{a['id']}" for a in doc["assets"]
            if isinstance(a.get("id"), str) and evaluate_candidate(a, pack_id, rules)["candidate"]
        }
        n_candidates += len(candidates)
        have = rows_by_pack.get(pack_id, set())
        missing = sorted(candidates - have)
        declared = {  # an exact-id set/confirm override may declare a weapon the patterns missed
            rid for rid in (f"{pack_id}/{a['id']}" for a in doc["assets"] if isinstance(a.get("id"), str))
            if (overrides.get("ids", {}).get(rid) or {}).get("set")
            or (overrides.get("ids", {}).get(rid) or {}).get("confirm")
        }
        extra = sorted(have - candidates - declared)
        if missing:
            problems.append(f"{pack_id}: {len(missing)} candidate(s) without a row: {_show(missing, 3)}")
        if extra:
            problems.append(f"{pack_id}: {len(extra)} row(s) that are not candidates: {_show(extra, 3)}")
        row = stored.get(pack_id)
        if row is None:
            problems.append(f"{pack_id}: no pack row in directory.packs")
        elif row["records"] + row["excluded"] != row["candidates"] or row["candidates"] != len(have):
            problems.append(
                f"{pack_id}: pack row says records {row['records']} + excluded {row['excluded']} vs candidates "
                f"{row['candidates']} but {len(have)} rows exist")
    return {"ok": not problems, "problems": problems, "candidates": n_candidates}


def _forward_problem(key: str, want: str, rec: dict | None) -> str | None:
    """Why the audited record ``rec`` does not carry the ``forward`` override ``want``, or None when it does."""
    if rec is None:
        return f"{key}: forward override {want!r} but the directory has no record"
    geo = rec.get("geometry")
    if geo is None:
        return f"{key}: forward override {want!r} but the record has no geometry"
    axes = geo["axes"]
    if axes["forward"] != want or axes["forward_source"] != "override":
        return (f"{key}: forward is {axes['forward']!r} ({axes['forward_source']}), the override says {want!r} "
                f"(an override whose axis is not the measured forward axis is not applied)")
    return None


def _gold(overrides: dict, rebuilt: dict, rebuilt_excluded: dict, known_ids: set[str],
          directory: dict | None = None, audited_excluded: dict | None = None) -> tuple[int, list[str]]:
    by_id = {w["id"]: w for w in rebuilt["weapons"]}
    excluded = {e["id"]: e for e in rebuilt_excluded["excluded"]}
    audited = {w["id"]: w for w in (directory or {}).get("weapons", [])}
    audited_excluded_ids = {e["id"] for e in (audited_excluded or {}).get("excluded", [])}
    cases, bad = 0, []
    for key in sorted(overrides.get("ids", {})):
        entry = overrides["ids"][key]
        if key not in known_ids:
            continue  # stale, reported by overrides_current
        if entry.get("exclude"):
            cases += 1
            if excluded.get(key, {}).get("reason") != "override":
                bad.append(f"{key}: exclude did not give an excluded row with reason override")
            continue
        want = entry.get("set") or {}
        has_forward = bool(entry.get("forward")) and key not in audited_excluded_ids
        if has_forward:
            problem = _forward_problem(key, entry["forward"], audited.get(key))
            if problem:
                bad.append(problem)
        if not want:
            cases += has_forward  # one case per id, whether it carries a set, a forward or both
            continue
        cases += 1
        rec = by_id.get(key)
        if rec is None:
            bad.append(f"{key}: no record after a clean rebuild")
            continue
        for field in GOLD_FIELDS:
            if field not in want:
                continue
            if field == "kind" and rec["role"] in NON_WEAPON_ROLES:
                continue  # a part/ammo/carrier has no kind (spec 4.1)
            if rec[field] != want[field]:
                bad.append(f"{key}: {field} is {rec[field]!r}, the override says {want[field]!r}")
    return cases, bad


def check_weapons_directory(catalogs_dir: Path, *, strict: bool = False, rules: dict | None = None,
                            overrides: dict | None = None) -> dict:
    """``{"ok", "skipped", "strict", "checks": [...], "stale_overrides": [...], "detail"}``; never writes."""
    wdir = weapons_dir(catalogs_dir)
    dpath, epath = wdir / DIRECTORY_NAME, wdir / EXCLUDED_NAME
    if not dpath.is_file():
        return {"ok": True, "skipped": True, "strict": strict, "checks": [], "stale_overrides": [],
                "detail": "no weapon directory — skipped"}
    checks: list[dict] = []
    try:
        rules = rules if rules is not None else load_rules()
        overrides = overrides if overrides is not None else load_overrides()
        directory = read_json(dpath)
        if not epath.is_file():
            raise WeaponsError(f"{EXCLUDED_NAME} is missing beside {DIRECTORY_NAME}: run `weapons build`", 2)
        excluded = read_json(epath)
        docs = load_pack_catalogs(catalogs_dir)
        if not isinstance(directory, dict) or not isinstance(excluded, dict):
            raise WeaponsError("directory.json and excluded.json must be JSON objects", 2)
    except WeaponsError as exc:
        return _finish([_check("inputs", False, str(exc).splitlines()[0])], [], strict)

    current = (directory.get("weapon_version") == _pkg.WEAPON_VERSION
               and directory.get("rules_digest") == digest(rules)
               and directory.get("overrides_digest") == digest(overrides))
    checks.append(_check(
        "directory_current", current,
        "built with the current weapon version, rules and overrides" if current
        else "built with another weapon version, rules or overrides: run `weapons build`"))

    errors = validate_directory(directory, excluded)
    checks.append(_check("schema", not errors, f"{len(errors)} violation(s): {_show(errors, 3)}" if errors
                         else "valid weapon-directory/1"))
    if not current:
        return _finish(checks, [], strict)  # audited against the current inputs: against others it is just noise
    stale: list[dict] = []
    try:
        stale = _audit(checks, catalogs_dir, directory, excluded, docs, rules, overrides, strict)
    except (KeyError, TypeError, AttributeError) as exc:  # a malformed document: the schema check names the cause
        checks.append(_check("shape", False, f"the directory could not be audited: {type(exc).__name__}: {exc}"))
    return _finish(checks, stale, strict)


def _audit(checks: list[dict], catalogs_dir: Path, directory: dict, excluded: dict, docs: dict[str, dict],
           rules: dict, overrides: dict, strict: bool) -> list[dict]:
    """The checks that read the records; they run (and report) even when the schema check already failed."""
    cov = _coverage(directory, excluded, docs, rules, overrides)
    checks.append(_check(
        "coverage", cov["ok"],
        f"records + excluded == candidates in every pack ({cov['candidates']} candidates)" if cov["ok"]
        else "; ".join(cov["problems"][:SHOWN])))

    dup_w, dup_e = _dupes([w["id"] for w in directory["weapons"]]), _dupes([e["id"] for e in excluded["excluded"]])
    both = sorted({w["id"] for w in directory["weapons"]} & {e["id"] for e in excluded["excluded"]})
    checks.append(_check(
        "ids_unique", not (dup_w or dup_e or both),
        "every id appears once" if not (dup_w or dup_e or both)
        else f"duplicate records {_show(dup_w)}; duplicate excluded {_show(dup_e)}; in both {_show(both)}"))

    with_glb = [w for w in directory["weapons"] if (w.get("files") or {}).get("glb")]
    measured = [w for w in with_glb if w.get("geometry") is not None]
    ratio = len(measured) / len(with_glb) if with_glb else 1.0
    checks.append(_check(
        "geometry", ratio >= GEOMETRY_FLOOR,
        f"{len(measured)}/{len(with_glb)} records with a GLB are measured ({ratio:.1%}, floor {GEOMETRY_FLOOR:.0%})"))

    no_muzzle = sorted(
        w["id"] for w in directory["weapons"]
        if w["role"] == "whole" and w["kind"] == "ranged" and w["archetype"] != "bow"
        and w.get("geometry") is not None and w["geometry"].get("muzzle") is None)
    checks.append(_check("muzzle", not no_muzzle,
                         "every ranged, non-bow, whole record with geometry has a muzzle" if not no_muzzle
                         else f"{len(no_muzzle)} without a muzzle: {_show(no_muzzle)}"))

    known = {f"{pid}/{a['id']}" for pid, doc in docs.items() for a in doc["assets"] if isinstance(a.get("id"), str)}
    stale = _stale_overrides(overrides, known, set(docs), partial=False)
    stale_keys = [f"{s['kind']} {s['key']}" for s in stale]
    checks.append(_check(
        "overrides_current", not stale or not strict,
        "every override matches at least one asset" if not stale
        else (f"{len(stale)} stale override(s): {_show(stale_keys)}"
              + (" (fails: strict)" if strict else " (listed only; strict fails on these)"))))

    if overrides.get("ids"):
        try:
            rebuilt, rebuilt_excl, _ = build_directory_report(
                catalogs_dir, rules=rules, overrides=overrides, measure=False, geometry_cache={})
        except WeaponsError as exc:  # e.g. two equal-length globs that disagree: the rebuild itself is refused
            checks.append(_check("gold", False, f"the clean rebuild failed: {str(exc).splitlines()[0]}"))
        else:
            cases, bad = _gold(overrides, rebuilt, rebuilt_excl, known, directory, excluded)
            checks.append(_check(
                "gold", not bad,
                f"{cases} gold id(s) classify to their overridden values after a clean rebuild" if not bad
                else f"{len(bad)} of {cases} gold id(s) differ: {_show(bad, 3)}"))
    else:
        checks.append(_check("gold", True, "0 gold ids (the overrides file has no id entries yet)"))
    return stale


def _finish(checks: list[dict], stale: list[dict], strict: bool) -> dict:
    ok = all(c["ok"] for c in checks)
    failing = [c for c in checks if not c["ok"]]
    if failing:
        detail = "; ".join(f"{c['check']}: {c['detail']}" for c in failing)
    else:  # a passing run still names the stale overrides it let through
        detail = "; ".join(f"{c['check']}: {c['detail']}" if (stale and c["check"] == "overrides_current")
                           else f"{c['check']} ok" for c in checks)
    return {"ok": ok, "skipped": False, "strict": strict, "checks": checks, "stale_overrides": stale, "detail": detail}
