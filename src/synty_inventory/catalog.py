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


def write_index(catalogs_dir: Path, packs: list[dict]) -> Path:
    doc = {
        "version": CATALOG_VERSION,
        "updated_at": now_iso(),
        "catalogs_dir": posix(catalogs_dir),
        "packs": packs,
    }
    return write_catalog(catalogs_dir / "index.json", doc)


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
            "catalog": extra.get("catalog") or posix(catalog_path(catalogs_dir, pid)),
            "errors": extra.get("errors") or [],
            "source": extra["source"] if "source" in extra else doc.get("source"),
        }
    for pid, extra in extras.items():
        if pid not in by_id:
            by_id[pid] = extra
    packs = [by_id[key] for key in sorted(by_id)]
    return write_index(catalogs_dir, packs)


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
    if engine == "Unreal" and ref.unreal_path:
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

    assets = [skeleton_asset(r, ref.pack_id, viewer_data) for r in raw]
    doc = {
        "pack_id": ref.pack_id,
        "engine": engine,
        "origin": "Synty",
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
    enrich_catalog(doc, viewer_data, threejs_v2=threejs_v2, catalogs_dir=catalogs_dir)
    doc["asset_count"] = len(doc["assets"])
    return doc


def scan_and_write(
    ref: PackRef,
    catalogs_dir: Path,
    *,
    include_shared: bool = False,
    viewer_data: Path | None = None,
    threejs_v2: Path | None = None,
    from_package: bool = False,
    vlm_fn=None,
    vlm_limit: int = 0,
) -> tuple[dict, list[str]]:
    fresh = build_catalog(
        ref,
        include_shared=include_shared,
        viewer_data=viewer_data,
        threejs_v2=threejs_v2,
        catalogs_dir=catalogs_dir,
        from_package=from_package,
    )
    if vlm_fn is not None:
        enrich_catalog(
            fresh, viewer_data, threejs_v2=threejs_v2, catalogs_dir=catalogs_dir, vlm_fn=vlm_fn, vlm_limit=vlm_limit
        )
    dest = catalog_path(catalogs_dir, ref.pack_id)
    existing = load_catalog(dest)
    merged = merge_catalog(existing, fresh)
    merged["asset_count"] = len(merged["assets"])
    write_catalog(dest, merged)
    errors = validate_catalog(merged)
    return merged, errors
