"""CLI: scan / enrich / list-packs / search / details / suggest / placement / gauntlet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import query
from .catalog import (
    build_catalog,
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
)
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


def _viewer(cfg) -> Path | None:
    viewer = cfg.get("viewer_data")
    if viewer is not None and viewer.exists():
        return viewer
    return None


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
    target = Path(args.path) if args.path else require_path(cfg, "unity_root")
    catalogs_dir = _catalogs(args, cfg)
    viewer = _viewer(cfg)
    refs = discover(target, extracted_root=cfg.get("extracted_root"))
    if args.pack:
        refs = [r for r in refs if args.pack.lower() in r.pack_id.lower()]
    if not refs:
        return _fail(f"no Synty packs found under {target}")

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
        if not ref.extracted_path and not ref.package_path and not ref.unreal_path:
            summaries.append({"pack_id": ref.pack_id, "error": "no extracted tree or package"})
            continue
        doc, errors = scan_and_write(
            ref,
            catalogs_dir,
            include_shared=args.include_shared,
            viewer_data=viewer,
            from_package=args.from_package,
            vlm_fn=vlm_fn,
            vlm_limit=args.vlm_limit,
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
            }
        )
    rebuild_index(catalogs_dir, summaries)
    emit_json({"ok": all(not s.get("errors") for s in summaries), "packs": summaries})
    return 0 if all(not s.get("errors") for s in summaries) else 2


def cmd_enrich(args, cfg) -> int:
    catalogs_dir = _catalogs(args, cfg)
    viewer = _viewer(cfg)
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
        enrich_catalog(doc, viewer, vlm_fn=vlm_fn, vlm_limit=args.vlm_limit)
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
        )
    )
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
    emit_json(
        query.suggest_assets_for(
            catalogs_dir,
            args.context,
            pack=args.pack,
            limit=args.limit,
        )
    )
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


def cmd_gauntlet(args, cfg) -> int:
    catalogs_dir = _catalogs(args, cfg)
    result = run_gauntlet(catalogs_dir)
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
    se.set_defaults(func=cmd_search)

    de = sub.add_parser("details", help="get_asset_details(id)")
    de.add_argument("id")
    de.set_defaults(func=cmd_details)

    su = sub.add_parser("suggest", help="suggest_assets_for(context)")
    su.add_argument("context")
    su.add_argument("--pack", default=None)
    su.add_argument("--limit", type=int, default=12)
    su.set_defaults(func=cmd_suggest)

    pl = sub.add_parser("placement", help="get_placement_guidance(id)")
    pl.add_argument("id")
    pl.set_defaults(func=cmd_placement)

    va = sub.add_parser("validate", help="Schema-check written catalogs")
    va.add_argument("--pack", default=None)
    va.set_defaults(func=cmd_validate)

    g = sub.add_parser("gauntlet", help="Run acceptance gates against live catalogs")
    g.set_defaults(func=cmd_gauntlet)
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
