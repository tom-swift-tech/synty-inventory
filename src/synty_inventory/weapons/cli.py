"""``synty-inventory weapons ...`` verb group (spec 3.2).

Every verb of the spec is registered here, so later slices add modules, not registrations: a verb whose module
does not exist yet answers ``{"ok": false, "error": "not built in this checkout"}`` with exit 2. A later slice
provides ``synty_inventory.weapons.<module>.cmd(args, cfg) -> int`` for its verb and the stub steps aside.

All verbs print JSON on stdout. Exit codes: 0 ok, 2 bad input, 3 refusal, 4 below --min-coverage, 5 renderer
unavailable, 6 schema violation.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from . import (
    ARCHETYPES,
    EXIT_BAD_INPUT,
    EXIT_COVERAGE,
    EXIT_OK,
    EXIT_REFUSED,
    EXIT_SCHEMA,
    GENRES,
    KINDS,
    ROLES,
    STATUSES,
    WeaponsError,
)

# verb -> module that implements it (None = implemented in this file)
_LATER_MODULES = {
    "icons": "icons",
    "review": "review",
    "apply-corrections": "corrections",
    "export": "export",
}


def _emit(obj) -> None:
    from ..cli import emit_json  # lazy: the root cli imports this module at import time

    emit_json(obj)


def _csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [p.strip() for p in value.split(",") if p.strip()]


def _error(message: str, code: int, **extra) -> int:
    _emit({"ok": False, "error": message, **extra})
    return code


def _catalogs(args, cfg) -> Path:
    from ..cli import _catalogs as root_catalogs

    return root_catalogs(args, cfg)


def _not_built(args, cfg, verb: str) -> int:
    module = _LATER_MODULES[verb]
    full = f"synty_inventory.weapons.{module}"
    try:
        mod = importlib.import_module(full)
    except ModuleNotFoundError as exc:
        if exc.name != full:
            raise  # a real import failure inside an existing module
        return _error("not built in this checkout", EXIT_BAD_INPUT, verb=verb)
    return mod.cmd(args, cfg)


def _guarded(fn):
    """Run a verb, turning ``WeaponsError`` into JSON + its exit code."""

    def wrapper(args, cfg) -> int:
        try:
            return fn(args, cfg)
        except WeaponsError as exc:
            return _error(str(exc), exc.code, **exc.details)

    wrapper.__name__ = fn.__name__
    return wrapper


@_guarded
def cmd_build(args, cfg) -> int:
    from .directory import (
        EXCLUDED_NAME,
        DIRECTORY_NAME,
        build_directory_report,
        read_json,
        weapons_dir,
        write_directory,
    )
    from ..cli import _threejs_v2
    from .geometry import CACHE_NAME, load_cache, save_cache
    from .overrides import load_overrides
    from .rules import load_rules

    catalogs_dir = _catalogs(args, cfg)
    packs = _csv(args.pack)
    rules = load_rules()
    overrides = load_overrides()
    base = None
    wdir = weapons_dir(catalogs_dir)
    if packs and (wdir / DIRECTORY_NAME).is_file() and (wdir / EXCLUDED_NAME).is_file():
        base = (read_json(wdir / DIRECTORY_NAME), read_json(wdir / EXCLUDED_NAME))
    threejs_v2 = _threejs_v2(cfg)
    cache_path = wdir / CACHE_NAME
    cache = {} if args.rebuild else load_cache(cache_path)
    directory, excluded, report = build_directory_report(
        catalogs_dir, packs=packs, rules=rules, overrides=overrides, measure=not args.no_geometry, base=base,
        threejs_v2_dir=threejs_v2, geometry_cache=cache,
    )
    dpath, epath = write_directory(catalogs_dir, directory, excluded)
    report["directory"] = dpath.name
    if args.no_geometry:
        report["geometry"] = "skipped (--no-geometry)"
    elif threejs_v2 is None:
        report["geometry"] = "skipped (threejs_v2 not configured)"
    else:
        report["geometry"] = "measured"
        if cache and report["geometry_stats"]["decoded"]:
            save_cache(cache_path, cache)  # only when something was decoded: a cache-hit run rewrites nothing
    if args.report:
        rpath = Path(args.report)
        rpath.parent.mkdir(parents=True, exist_ok=True)
        rpath.write_bytes((json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"))

    ok = True
    notes: list[str] = []
    if args.strict and report["stale_overrides"]:
        ok = False
        notes.append("stale overrides with --strict")
        code = EXIT_REFUSED
    elif args.min_coverage is not None and report["geometry_coverage"] < args.min_coverage:
        ok = False
        notes.append(f"geometry coverage {report['geometry_coverage']} below --min-coverage {args.min_coverage}")
        code = EXIT_COVERAGE
    else:
        code = EXIT_OK
    _emit({"ok": ok, "notes": notes, "report": report})
    return code


def _resolve_id(directory: dict, wanted: str) -> dict:
    weapons = directory["weapons"]
    if "/" in wanted:
        for w in weapons:
            if w["id"] == wanted:
                return w
        raise WeaponsError(f"no weapon with id {wanted!r}", EXIT_BAD_INPUT)
    hits = [w["id"] for w in weapons if w["asset_id"] == wanted]
    if not hits:
        raise WeaponsError(f"no weapon with asset id {wanted!r}", EXIT_BAD_INPUT)
    if len(hits) > 1:
        raise WeaponsError(
            f"asset id {wanted!r} is ambiguous; use one of the qualified ids", EXIT_BAD_INPUT,
            {"candidates": sorted(hits)},
        )
    return next(w for w in weapons if w["id"] == hits[0])


@_guarded
def cmd_show(args, cfg) -> int:
    from .directory import load_directory

    directory = load_directory(_catalogs(args, cfg))
    _emit({"ok": True, "weapon": _resolve_id(directory, args.id)})
    return EXIT_OK


def _row(w: dict) -> dict:
    return {
        "id": w["id"], "role": w["role"], "kind": w["kind"], "archetype": w["archetype"], "genre": w["genre"],
        "hold_class": w["hold_class"], "confidence": w["review"]["confidence"], "status": w["review"]["status"],
        "flags": w["flags"],
    }


@_guarded
def cmd_list(args, cfg) -> int:
    from .directory import load_directory

    directory = load_directory(_catalogs(args, cfg))
    packs = set(_csv(args.pack) or [])
    rows = []
    for w in directory["weapons"]:
        if packs and w["pack"] not in packs:
            continue
        if args.kind and w["kind"] != args.kind:
            continue
        if args.role and w["role"] != args.role:
            continue
        if args.archetype and w["archetype"] != args.archetype:
            continue
        if args.genre and w["genre"] != args.genre:
            continue
        if args.status and w["review"]["status"] != args.status:
            continue
        if args.max_confidence is not None and w["review"]["confidence"] > args.max_confidence:
            continue
        rows.append(_row(w))
    total = len(rows)
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]
    _emit({"ok": True, "total": total, "count": len(rows), "weapons": rows})
    return EXIT_OK


@_guarded
def cmd_validate(args, cfg) -> int:
    from .directory import DIRECTORY_NAME, EXCLUDED_NAME, read_json, weapons_dir
    from .overrides import load_overrides
    from .rules import load_rules, shadowed_rules
    from .schema import validate_directory

    if args.snapshot:
        return _error("not built in this checkout", EXIT_BAD_INPUT, verb="validate --snapshot")
    problems: dict[str, list] = {}
    rules = load_rules()  # SchemaError -> exit 6
    shadowed = shadowed_rules(rules)
    if shadowed:
        problems["shadowed_rules"] = shadowed
    load_overrides()  # SchemaError -> exit 6

    result: dict = {"rules": "ok" if not shadowed else "shadowed", "overrides": "ok", "directory": "absent"}
    if args.directory:
        dpath = Path(args.directory)
        if not dpath.is_file():
            raise WeaponsError(f"directory file not found: {dpath}", EXIT_BAD_INPUT)
    else:
        dpath = weapons_dir(_catalogs(args, cfg)) / DIRECTORY_NAME
    if dpath.is_file():
        epath = dpath.with_name(EXCLUDED_NAME)
        excluded = read_json(epath) if epath.is_file() else None
        errors = validate_directory(read_json(dpath), excluded)
        result["directory"] = "ok" if not errors else "invalid"
        if errors:
            problems["directory_errors"] = errors
    result["ok"] = not problems
    result.update(problems)
    _emit(result)
    return EXIT_OK if not problems else EXIT_SCHEMA


def register(sub) -> None:
    """Add the ``weapons`` group to the root parser's subparsers (spec 3.2)."""
    wp = sub.add_parser("weapons", help="Weapon directory: classified, measured per-weapon profiles")
    wsub = wp.add_subparsers(dest="weapons_cmd", required=True)

    def pack_opt(p):
        p.add_argument("--pack", default=None, help="comma list of pack ids; all packs when omitted")

    b = wsub.add_parser("build", help="Build <catalogs>/weapons/directory.json and excluded.json")
    pack_opt(b)
    b.add_argument("--rebuild", action="store_true", help="ignore the geometry cache")
    b.add_argument("--no-geometry", dest="no_geometry", action="store_true", help="skip geometry measurement")
    b.add_argument("--report", default=None, help="write the build report JSON here as well as stdout")
    b.add_argument("--min-coverage", dest="min_coverage", type=float, default=None,
                   help="exit 4 when geometry coverage of records with a GLB is below this fraction")
    b.add_argument("--strict", action="store_true", help="exit 3 when an override names a missing id/glob")
    b.set_defaults(func=cmd_build)

    s = wsub.add_parser("show", help="Print one record; ID is <pack>/<asset_id>, or a bare unique asset_id")
    s.add_argument("id", metavar="ID")
    s.set_defaults(func=cmd_show)

    ls = wsub.add_parser("list", help="List records with filters")
    pack_opt(ls)
    ls.add_argument("--kind", choices=KINDS)
    ls.add_argument("--role", choices=ROLES)
    ls.add_argument("--archetype", choices=ARCHETYPES)
    ls.add_argument("--genre", choices=GENRES)
    ls.add_argument("--status", choices=STATUSES)
    ls.add_argument("--max-confidence", dest="max_confidence", type=float, default=None)
    ls.add_argument("--limit", type=int, default=0, help="max rows (0 = all)")
    ls.set_defaults(func=cmd_list)

    ic = wsub.add_parser("icons", help="Render 256/64 px icons (later slice)")
    pack_opt(ic)
    ic.add_argument("--ids", default=None, help="comma list of <pack>/<asset_id>")
    ic.add_argument("--size", type=int, default=256)
    ic.add_argument("--rebuild", action="store_true")
    ic.add_argument("--variants", action="store_true")
    ic.set_defaults(func=lambda a, c: _not_built(a, c, "icons"))

    rv = wsub.add_parser("review", help="Write the static review page (later slice)")
    rv.add_argument("--out", dest="review_out", default=None, help="output directory (distinct from the global --out)")
    pack_opt(rv)
    rv.add_argument("--only-unreviewed", dest="only_unreviewed", action="store_true")
    rv.add_argument("--max-confidence", dest="max_confidence", type=float, default=None)
    rv.set_defaults(func=lambda a, c: _not_built(a, c, "review"))

    ac = wsub.add_parser("apply-corrections", help="Merge a weapon-corrections/1 file into the overrides (later slice)")
    ac.add_argument("file", metavar="FILE")
    ac.add_argument("--dry-run", dest="dry_run", action="store_true")
    ac.set_defaults(func=lambda a, c: _not_built(a, c, "apply-corrections"))

    ex = wsub.add_parser("export", help="Write a per-game snapshot (later slice)")
    ex.add_argument("--game", required=True)
    grp = ex.add_mutually_exclusive_group(required=True)
    grp.add_argument("--packs", default=None, help="comma list of pack ids")
    grp.add_argument("--ids-file", dest="ids_file", default=None)
    ex.add_argument("--out", dest="export_out", required=True, help="snapshot file (distinct from the global --out)")
    ex.add_argument("--roles", default="whole")
    ex.add_argument("--engine", choices=("godot", "unity", "threejs", "all"), default="all")
    ex.add_argument("--frame", choices=("item", "asset"), default="item")
    ex.add_argument("--icons-dir", dest="icons_dir", default=None)
    ex.add_argument("--profile", choices=("private", "public"), default="private")
    ex.set_defaults(func=lambda a, c: _not_built(a, c, "export"))

    v = wsub.add_parser("validate", help="Validate rules, overrides and a directory (exit 6 on violations)")
    v.add_argument("--directory", default=None, help="directory.json to check (default: the catalogs one)")
    v.add_argument("--snapshot", default=None, help="a snapshot file (later slice)")
    v.set_defaults(func=cmd_validate)

