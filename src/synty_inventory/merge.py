"""Re-scan merge: never destroy human (or better) edits."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .schema import SEMANTIC_FIELDS

SCANNER_OWNED = ("id", "paths", "files", "kit", "guid", "engine_paths")

# Field precedence for enrichment sources. Higher wins on rescan and inside a
# single enrich_catalog() pass. vlm_reviewed (threejs-v2, VLM-graded per
# asset) outranks the rule/viewer/GLB-measurement sources but never a human
# or curated (hand-authored, exact-id) override.
PROVENANCE_RANK = {
    "rules": 1,
    "viewer": 2,
    "measured": 3,
    "vlm": 3,
    "vlm_reviewed": 4,
    "curated": 5,
    "human": 6,
}

# Single exception to strict rank order: threejs-v2's VLM-reviewed name/
# description/tags are allowed to overwrite a "curated" (hand-authored, but
# not `human`-locked) record for those three text fields specifically. The
# VLM pass looks at the actual mesh and writes grounded prose ("channel
# letters", etc.) that is usually better than older hand-typed copy; but a
# human's placement/ai_notes/semantic_role judgement calls are not
# second-guessed this way. This must be consulted both by a single
# build_catalog() pass (see sources/threejs_v2.py::apply_threejs_overlay,
# which calls may_overlay) AND by merge_asset() on rescan, where the
# on-disk record's provenance is the "current" one being compared against —
# defining it once here keeps the two call sites from drifting apart.
FORCE_OVERLAY_PAIRS: dict[tuple[str, str], set[str]] = {
    ("curated", "vlm_reviewed"): {"name", "description", "tags"},
}


def _rank_allows(current: str | None, source: str, field: str) -> bool:
    if PROVENANCE_RANK.get(current or "rules", 1) <= PROVENANCE_RANK.get(source, 1):
        return True
    return field in FORCE_OVERLAY_PAIRS.get((current, source), set())


def may_overlay(asset: dict, field: str, source: str) -> bool:
    """True when ``source`` may (over)write ``asset[field]`` given whatever
    already stamped that field's provenance. Ties go to the incoming source
    (a fresh pass from the same-rank source should still refresh content)."""
    current = (asset.get("provenance") or {}).get(field)
    return _rank_allows(current, source, field)


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
    # Classification flags are rules/scanner-owned: a rescan with better
    # rules must be able to flip ANIMATION clips to placeable=False. Humans
    # can still pin them via locked_fields.
    for key in ("placeable", "kind", "size_hint"):
        if key in new and not is_human_field(old, key):
            out[key] = new[key]
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
        # (with the curated->vlm_reviewed name/description/tags exception in
        # FORCE_OVERLAY_PAIRS above — a rescan must not discard the same
        # overlay that a single build_catalog() pass would have applied).
        if not _rank_allows(old_prov, new_prov, field) and old.get(field):
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
