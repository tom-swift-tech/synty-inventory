"""CLI: scan / enrich / list-packs / search / details / suggest / placement / gauntlet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import query, recipes
from .catalog import (
    catalog_path,
    load_catalog,
    load_all_catalogs,
    rebuild_index,
    scan_and_write,
)
from .discover import discover, summarize
from .gauntlet import run_gauntlet
from .merge import merge_catalog
from .paths import (
    ConfigError,
    load_config,
    missing_required,
    posix,
    require_path,
    resolve_config,
    resolve_settings,
)
from .review import DEFAULT_VIEWS as REVIEW_DEFAULT_VIEWS
from .review import review_pack
from .schema import validate_catalog
from .unitypackage import extract_previews
from .vlm import enrich_asset_vlm, vlm_available


def configure_stdio() -> None:
    """Use UTF-8 on stdout/stderr so JSON with arrows etc. survives Windows consoles."""
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if reconf is None:
            continue
        try:
            reconf(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue


def dumps(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def emit_json(obj, stream=None) -> None:
    """Write JSON without crashing when the console encoding cannot represent Unicode."""
    stream = sys.stdout if stream is None else stream
    text = dumps(obj) + "\n"
    try:
        stream.write(text)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        stream.write(text.encode(encoding, errors="replace").decode(encoding, errors="replace"))


def attach_extracted_previews(assets: list[dict], written: list[str], catalogs_dir: Path) -> None:
    """Set thumbnail to the extracted file, relative to the catalogs dir when possible."""
    by_id = {a["id"]: a for a in assets}
    root = Path(catalogs_dir)
    for thumb in written:
        stem = Path(thumb).stem
        if stem not in by_id:
            continue
        path = Path(thumb)
        try:
            rel = path.resolve().relative_to(root.resolve())
            by_id[stem]["thumbnail"] = posix(rel)
        except ValueError:
            by_id[stem]["thumbnail"] = posix(path)


def _fail(msg: str, code: int = 1) -> int:
    print(msg, file=sys.stderr)
    return code


def _csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [p.strip() for p in value.split(",") if p.strip()]


def _optional_root(cfg, key: str) -> Path | None:
    """Optional configured root: None when unset or missing on disk.

    ``load_config`` already returns ``Path`` objects — do not wrap in ``Path()``
    as a substitute for ``exists()``. A ghost path is treated as unset.
    """
    root = cfg.get(key)
    if root is not None and root.exists():
        return root
    return None


def _viewer(cfg) -> Path | None:
    return _optional_root(cfg, "viewer_data")


def _threejs_v2(cfg) -> Path | None:
    """Optional source root for VLM-reviewed catalogs + GLB measurement.

    Required to fill ``bounds``/``files.glb`` — without it scan still runs,
    just leaving those null and reporting a warning per pack.
    """
    return _optional_root(cfg, "threejs_v2")


def _engine_root(cfg, key: str) -> Path | None:
    """Optional engine tree root (``godot_root`` / ``unreal_root``).

    None when unconfigured or missing on disk — scan/enrich then leave the
    corresponding ``files.*`` field null, same contract as ``_threejs_v2``.
    """
    return _optional_root(cfg, key)


def _warn_unmapped_godot(godot_root: Path | None) -> None:
    if godot_root is None:
        return
    from .sources.godot import unmapped_pack_dirs

    for row in unmapped_pack_dirs(godot_root):
        print(
            f"warning: unmapped Godot export folder {row['slug']!r} "
            f"(guess {row['guess']!r}) — skipped; add SLUG_PACK_OVERRIDES before using it",
            file=sys.stderr,
        )


def _catalogs(args, cfg) -> Path:
    if getattr(args, "out", None):
        return Path(args.out)
    return require_path(cfg, "catalogs")


def cmd_config(args, cfg) -> int:
    meta = resolve_config(args.config)
    paths = {}
    for key in meta["sources"]:
        path = meta["paths"].get(key)
        paths[key] = {
            "path": posix(path) if path else None,
            "exists": bool(path and path.exists()),
            "source": meta["sources"][key],
        }
    emit_json(
        {
            "config_file": posix(meta["config_file"]) if meta["config_file"] else None,
            "example_file": posix(meta["example_file"]),
            "paths": paths,
        }
    )
    return 0 if not missing_required(meta["paths"]) else 2


def cmd_discover(args, cfg) -> int:
    target = Path(args.path) if args.path else require_path(cfg, "unity_root")
    refs = discover(target, extracted_root=cfg.get("extracted_root"))
    emit_json(summarize(refs))
    return 0


def cmd_scan(args, cfg) -> int:
    catalogs_dir = _catalogs(args, cfg)
    if args.index:
        # Rebuild the discovery index + derived search.db from the catalogs
        # already on disk — no pack scan, no source tree needed.
        from .searchdb import db_path

        idx = rebuild_index(catalogs_dir)
        db = db_path(catalogs_dir)
        emit_json(
            {
                "ok": True,
                "index": str(idx),
                "search_db": str(db) if db.is_file() else None,
            }
        )
        return 0
    target = Path(args.path) if args.path else require_path(cfg, "unity_root")
    viewer = _viewer(cfg)
    threejs_v2 = _threejs_v2(cfg)
    godot_root = _engine_root(cfg, "godot_root")
    unreal_root = _engine_root(cfg, "unreal_root")
    _warn_unmapped_godot(godot_root)
    refs = discover(target, extracted_root=cfg.get("extracted_root"))
    # Generator-fed GEN_* packs live under threejs_v2, not the Unity root
    # (docs/gen_manifest_v1.md). Default scans pick them all up; an explicit
    # --path may point straight at one GEN pack dir.
    from .sources.manifest import discover_gen_packs, gen_pack_ref

    if args.path:
        gref = gen_pack_ref(target)
        if gref is not None:
            refs.append(gref)
    else:
        refs.extend(discover_gen_packs(threejs_v2))
    if args.pack:
        refs = [r for r in refs if args.pack.lower() in r.pack_id.lower()]
    if not refs:
        return _fail(f"no Synty or GEN packs found under {target}")
    if threejs_v2 is None:
        print(
            "warning: threejs_v2 not configured (or path missing) — "
            "bounds and files.glb will be left null for this scan",
            file=sys.stderr,
        )

    vlm_fn = None
    if args.vlm:
        if not vlm_available():
            return _fail("--vlm set but no XAI_API_KEY / OPENAI_API_KEY / SYNTI_VLM_API_KEY")

        def vlm_fn(asset):
            thumb = None
            if asset.get("thumbnail"):
                thumb = Path(asset["thumbnail"])
                if not thumb.is_file():
                    thumb = catalogs_dir / "previews" / asset["id"]
                    thumb = thumb.with_suffix(".png")
                    if not thumb.is_file():
                        thumb = None
            return enrich_asset_vlm(asset, thumb)

    summaries = []
    for ref in refs:
        if (
            not ref.extracted_path
            and not ref.package_path
            and not ref.unreal_path
            and not ref.extras.get("gen_dir")
        ):
            summaries.append({"pack_id": ref.pack_id, "error": "no extracted tree or package"})
            continue
        doc, errors = scan_and_write(
            ref,
            catalogs_dir,
            include_shared=args.include_shared,
            viewer_data=viewer,
            threejs_v2=threejs_v2,
            godot_root=godot_root,
            unreal_root=unreal_root,
            from_package=args.from_package,
            vlm_fn=vlm_fn,
            vlm_limit=args.vlm_limit,
            rebuild=args.rebuild,
        )
        if args.extract_previews and ref.package_path:
            wanted = {
                a["id"]
                for a in doc["assets"]
                if a.get("type") == "prop/signage" or "sign" in (a.get("category") or [])
            }
            dest = catalogs_dir / "previews" / ref.pack_id
            written = extract_previews(ref.package_path, dest, wanted_stems=wanted)
            attach_extracted_previews(doc["assets"], written, catalogs_dir)
            from .catalog import write_catalog

            write_catalog(catalog_path(catalogs_dir, ref.pack_id), doc)
        summaries.append(
            {
                "pack_id": doc["pack_id"],
                "engine": doc["engine"],
                "assets": len(doc["assets"]),
                "catalog": str(catalog_path(catalogs_dir, ref.pack_id)),
                "errors": errors,
                "source": doc.get("source"),
                "measure": doc.get("_measure_stats"),
                # Phase 3 permissive: sidecar problems are reported, not fatal
                # (Phase 4's manifest_present gate hard-rejects).
                "gen_errors": doc.get("_gen_errors") or [],
            }
        )
    rebuild_index(catalogs_dir, summaries)
    emit_json({"ok": all(not s.get("errors") for s in summaries), "packs": summaries})
    return 0 if all(not s.get("errors") for s in summaries) else 2


def cmd_enrich(args, cfg) -> int:
    catalogs_dir = _catalogs(args, cfg)
    viewer = _viewer(cfg)
    threejs_v2 = _threejs_v2(cfg)
    godot_root = _engine_root(cfg, "godot_root")
    unreal_root = _engine_root(cfg, "unreal_root")
    _warn_unmapped_godot(godot_root)
    from .enrich import enrich_catalog
    from .catalog import write_catalog

    docs = load_all_catalogs(catalogs_dir)
    if args.pack:
        docs = [d for d in docs if args.pack.lower() in d["pack_id"].lower()]
    if not docs:
        return _fail("no catalogs to enrich — run scan first")
    vlm_fn = None
    if args.vlm:
        if not vlm_available():
            return _fail("--vlm set but no API key in the environment")

        def vlm_fn(asset):
            thumb = None
            t = asset.get("thumbnail")
            if t and Path(t).is_file():
                thumb = Path(t)
            return enrich_asset_vlm(asset, thumb)

    out = []
    for doc in docs:
        enrich_catalog(doc, viewer, threejs_v2=threejs_v2, catalogs_dir=catalogs_dir, godot_root=godot_root, unreal_root=unreal_root, vlm_fn=vlm_fn, vlm_limit=args.vlm_limit)
        dest = catalog_path(catalogs_dir, doc["pack_id"])
        existing = load_catalog(dest)
        merged = merge_catalog(existing, doc)
        write_catalog(dest, merged)
        out.append({"pack_id": doc["pack_id"], "assets": len(merged["assets"])})
    emit_json({"ok": True, "packs": out})
    return 0


def cmd_list_packs(args, cfg) -> int:
    catalogs_dir = _catalogs(args, cfg)
    emit_json(query.list_packs(catalogs_dir))
    return 0


def cmd_search(args, cfg) -> int:
    catalogs_dir = _catalogs(args, cfg)
    emit_json(
        query.search_assets(
            catalogs_dir,
            args.query,
            pack=args.pack,
            tags=_csv(args.tags),
            category=_csv(args.category),
            constraints=_csv(args.constraints),
            limit=args.limit,
            types=_csv(args.type),
            roles=_csv(args.role),
            module_roles=_csv(args.module_role),
            part_classes=_csv(args.part_class),
            include_nonplaceable=args.include_nonplaceable,
            engine=args.engine,
            fields=_csv(args.fields),
        )
    )
    return 0


def cmd_recipes(args, cfg) -> int:
    catalogs_dir = _catalogs(args, cfg)
    recs = recipes.load_recipes(catalogs_dir, _viewer(cfg))
    rows = []
    for rid, rec in sorted(recs.items()):
        if args.pack and not any(args.pack.lower() in p.lower() for p in rec.get("packs") or [rid.split("@")[-1]]):
            continue
        rows.append(
            {
                "id": rid,
                "kind": rec.get("kind"),
                "label": rec.get("label"),
                "packs": rec.get("packs"),
                "source": rec.get("source"),
                "steps": [st.get("role") for st in rec.get("steps") or []],
                "triggers": rec.get("triggers"),
            }
        )
    emit_json(rows)
    return 0


def cmd_recipe(args, cfg) -> int:
    catalogs_dir = _catalogs(args, cfg)
    recs = recipes.load_recipes(catalogs_dir, _viewer(cfg))
    rec = recs.get(args.id)
    if rec is None:
        # allow "building_shop" to resolve to "building_shop@<pack>" when unique / pack given
        cands = [k for k in recs if k.split("@")[0] == args.id and (not args.pack or args.pack.lower() in k.lower())]
        if len(cands) == 1:
            rec = recs[cands[0]]
        elif cands:
            return _fail(f"ambiguous recipe {args.id}: {cands}", 3)
    if rec is None:
        return _fail(f"recipe not found: {args.id}", 3)
    out = recipes.resolve_recipe(
        catalogs_dir, rec, pack=args.pack, limit_per_step=args.limit, engine=args.engine, fields=_csv(args.fields)
    )
    emit_json(out)
    return 0 if out.get("complete") else 4


def cmd_kit(args, cfg) -> int:
    catalogs_dir = _catalogs(args, cfg)
    if args.family == "*" or args.family.lower() == "all":
        emit_json(recipes.kit_families(catalogs_dir, args.pack, engine=args.engine, fields=_csv(args.fields)))
        return 0
    fams = recipes.kit_family(catalogs_dir, args.family, args.pack, engine=args.engine, fields=_csv(args.fields))
    if not fams:
        return _fail(f"no module family matches: {args.family}", 3)
    emit_json(fams)
    return 0


def cmd_details(args, cfg) -> int:
    catalogs_dir = _catalogs(args, cfg)
    rec = query.get_asset_details(catalogs_dir, args.id)
    if rec is None:
        return _fail(f"asset not found: {args.id}", 3)
    emit_json(rec)
    return 0


def cmd_suggest(args, cfg) -> int:
    catalogs_dir = _catalogs(args, cfg)
    assets = query.suggest_assets_for(
        catalogs_dir,
        args.context,
        pack=args.pack,
        limit=args.limit,
        include_nonplaceable=args.include_nonplaceable,
        engine=args.engine,
        fields=_csv(args.fields),
    )
    if args.assets_only:
        emit_json(assets)
        return 0
    # Assembly requests get a grammar pointer first, then ranked pieces.
    matched = query.suggest_recipes_for(catalogs_dir, args.context, _viewer(cfg))
    emit_json({"recipes": matched, "assets": assets})
    return 0


def cmd_placement(args, cfg) -> int:
    catalogs_dir = _catalogs(args, cfg)
    rec = query.get_placement_guidance(catalogs_dir, args.id)
    if rec is None:
        return _fail(f"asset not found: {args.id}", 3)
    emit_json(rec)
    return 0


def cmd_validate(args, cfg) -> int:
    catalogs_dir = _catalogs(args, cfg)
    if not catalogs_dir.is_dir():
        return _fail(f"catalogs directory not found: {catalogs_dir}")
    docs = load_all_catalogs(catalogs_dir)
    if args.pack:
        docs = [d for d in docs if args.pack.lower() in d["pack_id"].lower()]
    if not docs:
        return _fail("no catalogs to validate — run scan first")
    report = []
    ok = True
    for doc in docs:
        errs = validate_catalog(doc)
        report.append({"pack_id": doc.get("pack_id"), "errors": errs})
        if errs:
            ok = False
    emit_json({"ok": ok, "packs": report})
    return 0 if ok else 2


def cmd_review(args, cfg) -> int:
    threejs_v2 = require_path(cfg, "threejs_v2")
    synty_glb_root = require_path(cfg, "synty_glb_root")
    settings = resolve_settings(args.config)
    model = args.model or settings["vlm_local_model"]
    url = args.url or settings["vlm_local_url"]
    views = tuple(v.strip() for v in args.views.split(",") if v.strip()) if args.views else REVIEW_DEFAULT_VIEWS
    result = review_pack(
        args.pack,
        threejs_v2_root=threejs_v2,
        synty_glb_root=synty_glb_root,
        catalogs_dir=cfg.get("catalogs"),
        limit=args.limit or None,
        match=args.match,
        model=model,
        url=url,
        views=views,
        vlm_timeout=args.vlm_timeout,
    )
    emit_json(result)
    return 0 if result.get("ok") else 2


def cmd_gauntlet(args, cfg) -> int:
    catalogs_dir = _catalogs(args, cfg)
    result = run_gauntlet(catalogs_dir, threejs_v2=_threejs_v2(cfg), godot_root=_engine_root(cfg, "godot_root"))
    emit_json(result)
    return 0 if result["ok"] else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="synty-inventory",
        description="Synty Pack Inventory: scan Unity/Unreal packs into JSON catalogs and query them.",
    )
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml (default: SYNTI_CONFIG, ./config.yaml, or the tool checkout)",
    )
    p.add_argument("--out", type=Path, default=None, help="Override catalogs directory from config")
    sub = p.add_subparsers(dest="cmd", required=True)

    cfg_cmd = sub.add_parser("config", help="Print resolved path configuration as JSON")
    cfg_cmd.set_defaults(func=cmd_config)

    d = sub.add_parser("discover", help="List packs under a root (no write)")
    d.add_argument("path", nargs="?", default=None)
    d.set_defaults(func=cmd_discover)

    s = sub.add_parser("scan", help="Scan packs and write/merge catalogs")
    s.add_argument("path", nargs="?", default=None, help="Unity root, extracted pack, or .unitypackage")
    s.add_argument("--pack", default=None, help="Restrict to pack_id substring")
    s.add_argument("--include-shared", action="store_true", help="Include PolygonGeneric in each pack")
    s.add_argument("--from-package", action="store_true", help="Index the .unitypackage even if extracted exists")
    s.add_argument("--rebuild", action="store_true", help="Drop auto-derived values on disk; keep only human-locked fields")
    s.add_argument("--index", action="store_true", help="Only rebuild index.json + search.db from catalogs on disk (no pack scan)")
    s.add_argument(
        "--extract-previews",
        action="store_true",
        help="Write Synty preview.png files under catalogs/previews/ (do not commit or share)",
    )
    s.add_argument(
        "--vlm",
        action="store_true",
        help="Optional VLM pass (API key required). May upload previews; can conflict with Synty/Unity EULA",
    )
    s.add_argument("--vlm-limit", type=int, default=0)
    s.set_defaults(func=cmd_scan)

    e = sub.add_parser("enrich", help="Re-run enrichment on existing catalogs")
    e.add_argument("--pack", default=None)
    e.add_argument(
        "--vlm",
        action="store_true",
        help="Optional VLM pass (API key required). May upload previews; can conflict with Synty/Unity EULA",
    )
    e.add_argument("--vlm-limit", type=int, default=0)
    e.set_defaults(func=cmd_enrich)

    lp = sub.add_parser("list-packs", help="list_packs()")
    lp.set_defaults(func=cmd_list_packs)

    se = sub.add_parser("search", help="search_assets(query, ...)")
    se.add_argument("query")
    se.add_argument("--pack", default=None)
    se.add_argument("--tags", default=None)
    se.add_argument("--category", default=None)
    se.add_argument("--constraints", default=None)
    se.add_argument("--limit", type=int, default=20)
    se.add_argument("--type", default=None, help="comma list of schema types (e.g. vehicle/part)")
    se.add_argument("--role", default=None, help="comma list of semantic_role enums")
    se.add_argument("--module-role", dest="module_role", default=None)
    se.add_argument("--part-class", dest="part_class", default=None)
    se.add_argument("--include-nonplaceable", action="store_true")
    se.add_argument("--engine", choices=query.ENGINES, default=None, help="which files.* to print")
    se.add_argument("--fields", default=None, help="comma list of full-record fields to add to each slim row (e.g. description,placement,part)")
    se.set_defaults(func=cmd_search)

    rl = sub.add_parser("recipes", help="List assembly recipes (package + asset-viewer types + user)")
    rl.add_argument("--pack", default=None)
    rl.set_defaults(func=cmd_recipes)

    rc = sub.add_parser("recipe", help="Resolve one recipe: grammar + eligible pieces with bounds/files")
    rc.add_argument("id")
    rc.add_argument("--pack", default=None)
    rc.add_argument("--limit", type=int, default=16, help="eligible pieces per step (eligible_count reports the full pool)")
    rc.add_argument("--engine", choices=query.ENGINES, default=None)
    rc.add_argument("--fields", default=None, help="comma list of full-record fields to add to each slim row (e.g. description,placement,part)")
    rc.set_defaults(func=cmd_recipe)

    kt = sub.add_parser("kit", help="Module family grouped by role (use '*' for all families)")
    kt.add_argument("family")
    kt.add_argument("--pack", default=None)
    kt.add_argument("--engine", choices=query.ENGINES, default=None)
    kt.add_argument("--fields", default=None, help="comma list of full-record fields to add to each slim row (e.g. description,placement,part)")
    kt.set_defaults(func=cmd_kit)

    de = sub.add_parser("details", help="get_asset_details(id)")
    de.add_argument("id")
    de.set_defaults(func=cmd_details)

    su = sub.add_parser("suggest", help="suggest_assets_for(context)")
    su.add_argument("context")
    su.add_argument("--pack", default=None)
    su.add_argument("--limit", type=int, default=12)
    su.add_argument("--include-nonplaceable", action="store_true")
    su.add_argument("--engine", choices=query.ENGINES, default=None)
    su.add_argument("--fields", default=None, help="comma list of full-record fields to add to each slim row (e.g. description,placement,part)")
    su.add_argument("--assets-only", action="store_true", help="v1 output: a bare list of assets")
    su.set_defaults(func=cmd_suggest)

    pl = sub.add_parser("placement", help="get_placement_guidance(id)")
    pl.add_argument("id")
    pl.set_defaults(func=cmd_placement)

    va = sub.add_parser("validate", help="Schema-check written catalogs")
    va.add_argument("--pack", default=None)
    va.set_defaults(func=cmd_validate)

    g = sub.add_parser("gauntlet", help="Run acceptance gates against live catalogs")
    g.set_defaults(func=cmd_gauntlet)

    rv = sub.add_parser(
        "review",
        help="Local VLM pass over a threejs-v2 pack: render stills, write catalog.json (reviewed:true)",
    )
    rv.add_argument("--pack", required=True, help="threejs-v2 pack_id, e.g. POLYGON_SciFi_Space")
    rv.add_argument("--limit", type=int, default=0, help="max unreviewed assets this run (0 = no limit)")
    rv.add_argument("--match", default=None, help="only stems containing this substring (case-insensitive)")
    rv.add_argument("--model", default=None, help="override vlm_local_model (default: config/env/gemma4:26b)")
    rv.add_argument("--url", default=None, help="override vlm_local_url (default: config/env/localhost:11434)")
    rv.add_argument(
        "--views",
        default=None,
        help=f"comma list of harness views (default: {','.join(REVIEW_DEFAULT_VIEWS)})",
    )
    rv.add_argument(
        "--vlm-timeout",
        type=int,
        default=600,
        help="seconds to wait per VLM call (default: 600; raise for larger/slower model tags)",
    )
    rv.set_defaults(func=cmd_review)
    return p


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        cfg = load_config(args.config, require=args.cmd != "config")
        if args.out:
            cfg["catalogs"] = Path(args.out)
        return args.func(args, cfg)
    except ConfigError as exc:
        return _fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
