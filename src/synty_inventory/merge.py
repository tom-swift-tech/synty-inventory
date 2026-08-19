"""Re-scan merge: never destroy human (or better) edits."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .schema import SEMANTIC_FIELDS

SCANNER_OWNED = ("id", "paths", "files", "kit", "guid", "engine_paths")


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def field_hash(value: Any) -> str:
    return hashlib.sha256(_dump(value).encode("utf-8")).hexdigest()[:16]


def is_human_field(old: dict, field: str) -> bool:
    locked = set(old.get("locked_fields") or [])
    if field in locked or old.get("locked") is True:
        return True
    prov = (old.get("provenance") or {}).get(field)
    if prov == "human":
        return True
    # Hash mismatch only counts as a human edit when provenance is absent.
    # Viewer/rules/vlm overlays often change text after the last stamp.
    if prov in {"rules", "viewer", "vlm", "vlm_reviewed", "measured", "curated"}:
        return False
    auto = (old.get("_auto") or {}).get(field)
    if auto is None:
        return False
    return field_hash(old.get(field)) != auto


def merge_asset(old: dict | None, new: dict) -> dict:
    if old is None:
        return new
    out = dict(old)
    # scanner-owned paths always refresh
    if new.get("paths"):
        out["paths"] = new["paths"]
    if new.get("files"):
        out["files"] = new["files"]
    if new.get("thumbnail") and not old.get("thumbnail"):
        out["thumbnail"] = new["thumbnail"]
    elif new.get("thumbnail"):
        # keep existing unless it disappeared and new has one
        out["thumbnail"] = old.get("thumbnail") or new["thumbnail"]
    for key in ("kit", "guid", "shared_kit"):
        if new.get(key) is not None:
            out[key] = new[key]
    # Measured bounds always win; a fresh scan that has no measurement keeps
    # whatever bounds the old record had (measured or null). Never regress
    # measured → null, never accept a fake size.
    if (new.get("bounds") or {}).get("source") == "measured" or not old.get("bounds"):
        out["bounds"] = new.get("bounds")
    out["dimensions"] = new.get("dimensions") if out.get("bounds") is new.get("bounds") else old.get("dimensions")
    if new.get("size_hint") is not None:
        out["size_hint"] = new["size_hint"]

    auto_out = dict(old.get("_auto") or {})
    prov_out = dict(old.get("provenance") or {})
    for field in SEMANTIC_FIELDS:
        incoming = new.get(field)
        if incoming is None:
            continue
        if is_human_field(old, field):
            continue
        old_prov = (old.get("provenance") or {}).get(field)
        new_prov = (new.get("provenance") or {}).get(field, "rules")
        # vlm / human incoming may replace rules; rules do not clobber vlm
        # Plan precedence: human > curated > vlm_reviewed > measured > viewer > rules
        rank = {"rules": 1, "viewer": 2, "measured": 3, "vlm": 3, "vlm_reviewed": 4, "curated": 5, "human": 6}
        if rank.get(old_prov or "rules", 1) > rank.get(new_prov, 1) and old.get(field):
            continue
        out[field] = incoming
        if field in (new.get("_auto") or {}):
            auto_out[field] = new["_auto"][field]
        else:
            auto_out[field] = field_hash(incoming)
        if new_prov:
            prov_out[field] = new_prov
    if new.get("_auto"):
        for k, v in new["_auto"].items():
            if k not in auto_out or not is_human_field(old, k):
                auto_out[k] = v
    out["_auto"] = auto_out
    out["provenance"] = prov_out
    if old.get("locked_fields"):
        out["locked_fields"] = old["locked_fields"]
    return out


def merge_catalog(old: dict | None, new: dict) -> dict:
    if old is None:
        return new
    old_by_id = {a["id"]: a for a in old.get("assets") or [] if isinstance(a, dict) and a.get("id")}
    merged_assets = []
    seen: set[str] = set()
    for asset in new.get("assets") or []:
        aid = asset.get("id")
        merged_assets.append(merge_asset(old_by_id.get(aid), asset))
        if aid:
            seen.add(aid)
    # keep human-only extras that vanished from disk? drop — they no longer exist
    out = dict(new)
    out["assets"] = merged_assets
    # preserve pack-level notes
    if old.get("notes") and not new.get("notes"):
        out["notes"] = old["notes"]
    return out


def stamp_auto(asset: dict) -> dict:
    auto = dict(asset.get("_auto") or {})
    prov = dict(asset.get("provenance") or {})
    for field in SEMANTIC_FIELDS:
        if field in asset and field not in auto:
            auto[field] = field_hash(asset[field])
        if field in asset and field not in prov:
            prov[field] = "rules"
    asset["_auto"] = auto
    asset["provenance"] = prov
    return asset
