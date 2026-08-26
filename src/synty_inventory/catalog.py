"""Build, load, write, and index per-pack JSON catalogs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import knowledge
from .discover import PackRef
from .enrich import enrich_catalog, skeleton_asset
from .merge import merge_catalog
from .paths import posix
from .scan import scan_extracted, scan_from_package_listing, scan_unreal
from .schema import (
    CATALOG_VERSION,
    DEFAULT_CONVENTIONS,
    DEFAULT_GRID,
    migrate_catalog,
    validate_catalog,
)
from .unitypackage import list_pathnames


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def catalog_path(catalogs_dir: Path, pack_id: str) -> Path:
    return catalogs_dir / f"{pack_id}.json"


def load_catalog(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    # v1 catalogs on disk are upgraded on read; the next write persists v2.
    return migrate_catalog(doc) if isinstance(doc, dict) else None


def write_catalog(path: Path, doc: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def write_index(catalogs_dir: Path, packs: list[dict], extra: dict | None = None) -> Path:
    doc = {
        "version": CATALOG_VERSION,
        "updated_at": now_iso(),
        "catalogs_dir": posix(catalogs_dir),
        **(extra or {}),
        "packs": packs,
    }
    return write_catalog(catalogs_dir / "index.json", doc)


def _pack_stats(doc: dict) -> dict:
    """Discovery stats for index.json — what an agent reads before any query."""
    assets = doc.get("assets") or []
    placeable = [a for a in assets if a.get("placeable") is not False]
    reviewed = sum(1 for a in assets if (a.get("provenance") or {}).get("description") == "vlm_reviewed")
    measured = sum(1 for a in placeable if (a.get("bounds") or {}).get("source") == "measured")
    kits = sorted({(a.get("module") or {}).get("family") for a in assets if (a.get("module") or {}).get("family")})
    return {
        "placeable": len(placeable),
        "measured": measured,
        "reviewed": reviewed,
        "kits": kits,
    }


def rebuild_index(catalogs_dir: Path, run_summaries: list[dict] | None = None) -> Path:
    """Write index.json from every catalog on disk.

    A single-pack scan must not drop other packs. Overlay this-run
    ``errors`` / ``source`` onto matching pack_id entries.
    """
    extras = {s["pack_id"]: s for s in (run_summaries or []) if s.get("pack_id")}
    by_id: dict[str, dict] = {}
    for doc in load_all_catalogs(catalogs_dir):
        pid = doc.get("pack_id")
        if not pid:
            continue
        extra = extras.get(pid) or {}
        by_id[pid] = {
            "pack_id": pid,
            "engine": doc.get("engine"),
            "assets": doc.get("asset_count") or len(doc.get("assets") or []),
            **_pack_stats(doc),
            "catalog": extra.get("catalog") or posix(catalog_path(catalogs_dir, pid)),
            "errors": extra.get("errors") or [],
            "source": extra["source"] if "source" in extra else doc.get("source"),
        }
    for pid, extra in extras.items():
        if pid not in by_id:
            by_id[pid] = extra
    packs = [by_id[key] for key in sorted(by_id)]
    # Discovery header: totals + recipe ids, so an agent's first read answers
    # "what is here and what can I ask for" without loading any catalog.
    # Viewer-derived building types are added at query time (`recipes` verb);
    # only package + user recipes are known from the catalogs dir alone.
    from .recipes import load_recipes  # local import: recipes imports catalog

    totals = {
        "assets": sum(p.get("assets") or 0 for p in packs),
        "placeable": sum(p.get("placeable") or 0 for p in packs),
        "measured": sum(p.get("measured") or 0 for p in packs),
        "reviewed": sum(p.get("reviewed") or 0 for p in packs),
    }
    extra_doc = {
        "totals": totals,
        "recipes": sorted(load_recipes(catalogs_dir)),
        "hint": "search/suggest/recipe/kit return slim rows; `details <id>` is the full record; `--fields a,b,c` widens",
    }
    path = write_index(catalogs_dir, packs, extra_doc)
    # Phase 2: search.db is derived from the catalogs and rebuilt wherever
    # the index is — one choke point keeps it consistent with every scan/
    # enrich path. Built last, so its mtime marks it fresh.
    from . import searchdb  # local import: searchdb loads catalogs via us

    searchdb.build(catalogs_dir)
    return path


def load_all_catalogs(catalogs_dir: Path) -> list[dict]:
    docs = []
    if not catalogs_dir.is_dir():
        return docs
    for path in sorted(catalogs_dir.glob("*.json")):
        # index.json and private state (_measure_cache.json, ...) are not
        # pack catalogs.
        if path.name == "index.json" or path.name.startswith("_"):
            continue
        doc = load_catalog(path)
        if doc and isinstance(doc.get("assets"), list) and doc.get("pack_id"):
            docs.append(doc)
    return docs


def build_catalog(
    ref: PackRef,
    *,
    include_shared: bool = False,
    viewer_data: Path | None = None,
    threejs_v2: Path | None = None,
    godot_root: Path | None = None,
    unreal_root: Path | None = None,
    catalogs_dir: Path | None = None,
    from_package: bool = False,
) -> dict:
    engine = ref.engine
    raw = []
    source = {
        "extracted": posix(ref.extracted_path) if ref.extracted_path else None,
        "unitypackage": posix(ref.package_path) if ref.package_path else None,
        "unreal": posix(ref.unreal_path) if ref.unreal_path else None,
    }
    if engine == "GLB" and ref.extras.get("gen_dir"):
        # Generator-fed pack (docs/gen_manifest_v1.md): skeletons come from
        # the GLB stems + sidecar manifests, not a Unity/Unreal tree.
        from .sources.manifest import scan_gen

        gen_dir = ref.extras["gen_dir"]
        raw = scan_gen(threejs_v2 or gen_dir.parent, ref.pack_id)
        source["gen"] = posix(gen_dir)
    elif engine == "Unreal" and ref.unreal_path:
        raw = scan_unreal(ref.unreal_path)
    elif ref.extracted_path and not from_package:
        raw = scan_extracted(ref.extracted_path, include_shared=include_shared)
    elif ref.package_path:
        listing = list_pathnames(ref.package_path)
        raw = scan_from_package_listing(
            listing, include_shared=include_shared, pack_id=ref.pack_id
        )
        source["listed_from_package"] = True
    else:
        raw = []

    # Converted GLBs that have no Unity prefab/FBX still belong in the catalog.
    if engine != "GLB" and threejs_v2 is not None:
        from .sources.threejs_v2 import glb_raw_assets

        have = {r.id for r in raw}
        raw.extend(extra for extra in glb_raw_assets(threejs_v2, ref.pack_id) if extra.id not in have)

    assets = [skeleton_asset(r, ref.pack_id, viewer_data) for r in raw]
    doc = {
        "pack_id": ref.pack_id,
        "engine": engine,
        "origin": "Generated" if engine == "GLB" else "Synty",
        "style": knowledge.pack_style(ref.pack_id),
        "units": "meters",
        "version": CATALOG_VERSION,
        "scanned_at": now_iso(),
        "grid": dict(DEFAULT_GRID),
        "conventions": dict(DEFAULT_CONVENTIONS),
        "source": source,
        "asset_count": len(assets),
        "assets": assets,
    }
    enrich_catalog(doc, viewer_data, threejs_v2=threejs_v2, catalogs_dir=catalogs_dir, godot_root=godot_root, unreal_root=unreal_root)
    doc["asset_count"] = len(doc["assets"])
    return doc


def _human_only(doc: dict) -> dict:
    """Strip a catalog down to the fields a human locked, per asset."""
    keep = []
    for a in doc.get("assets") or []:
        locked = set(a.get("locked_fields") or [])
        prov = a.get("provenance") or {}
        human = locked | {f for f, v in prov.items() if v == "human"}
        if a.get("locked") is True:
            keep.append(a)
            continue
        if not human:
            continue
        slim = {"id": a.get("id"), "locked_fields": sorted(human), "provenance": {f: "human" for f in human}}
        for f in human:
            if f in a:
                slim[f] = a[f]
        keep.append(slim)
    out = dict(doc)
    out["assets"] = keep
    return out


def scan_and_write(
    ref: PackRef,
    catalogs_dir: Path,
    *,
    include_shared: bool = False,
    viewer_data: Path | None = None,
    threejs_v2: Path | None = None,
    godot_root: Path | None = None,
    unreal_root: Path | None = None,
    from_package: bool = False,
    vlm_fn=None,
    vlm_limit: int = 0,
    rebuild: bool = False,
) -> tuple[dict, list[str]]:
    """``rebuild=True`` discards every auto-derived value on disk and keeps
    only human-locked fields (``locked_fields`` / ``provenance: human``) —
    use after a rules/schema change so old ``viewer``/``rules`` provenance
    cannot outrank the new derivation during merge."""
    fresh = build_catalog(
        ref,
        include_shared=include_shared,
        viewer_data=viewer_data,
        threejs_v2=threejs_v2,
        godot_root=godot_root,
        unreal_root=unreal_root,
        catalogs_dir=catalogs_dir,
        from_package=from_package,
    )
    if vlm_fn is not None:
        enrich_catalog(
            fresh, viewer_data, threejs_v2=threejs_v2, catalogs_dir=catalogs_dir,
            godot_root=godot_root, unreal_root=unreal_root, vlm_fn=vlm_fn, vlm_limit=vlm_limit
        )
    dest = catalog_path(catalogs_dir, ref.pack_id)
    existing = load_catalog(dest)
    if rebuild and existing:
        existing = _human_only(existing)
    merged = merge_catalog(existing, fresh)
    merged["asset_count"] = len(merged["assets"])
    write_catalog(dest, merged)
    errors = validate_catalog(merged)
    return merged, errors
