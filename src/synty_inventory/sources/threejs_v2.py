"""VLM-reviewed threejs-v2 pack catalogs (POLYGON_City, POLYGON_SciFi_City,
POLYGON_Starter today) plus the per-pack ``manifest.json`` GLB listing every
converted pack ships.

``<threejs_v2>/<pack_id>/manifest.json``  -> ``{"models": ["models/Models/SM_X.glb", ...]}``
``<threejs_v2>/<pack_id>/catalog.json``   -> ``{"assets": [{id, name, type, ..., reviewed}, ...]}`` (some packs only)

Two independent things happen here:
  1. every asset whose stem matches a GLB in the manifest gets ``files.glb``
     wired up, regardless of whether a reviewed catalog entry exists;
  2. reviewed catalog entries overlay richer, visually-grounded text.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from ..merge import may_overlay
from ..schema import (
    TYPE_MIGRATION,
    TYPES,
    normalize_attachment,
    normalize_mount,
    normalize_semantic_role,
)

_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9_\-+.]*$")

# Precedence carve-out (see brief item 5 / gauntlet `vlm_overlay_applied`):
# a curated (hand-authored, exact-id) asset normally outranks vlm_reviewed
# and would keep its own text everywhere. For name/description/tags only,
# the VLM-reviewed threejs-v2 text is visually grounded and better than the
# hand-written copy, so it is allowed to win even over "curated" — but
# placement/ai_notes/semantic_role/type stay curated when curated is set,
# since those encode a human placement judgement call, not just prose. The
# exception itself is defined once in merge.FORCE_OVERLAY_PAIRS and applied
# via may_overlay() so this single-pass overlay and merge_asset() on rescan
# agree (a rescan must not discard what a fresh build would have applied).


@lru_cache(maxsize=8)
def _load_json(path: str) -> dict | None:
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_manifest(threejs_v2_dir: Path | None, pack_id: str) -> dict | None:
    if threejs_v2_dir is None:
        return None
    return _load_json(str(threejs_v2_dir / pack_id / "manifest.json"))


def load_catalog(threejs_v2_dir: Path | None, pack_id: str) -> dict | None:
    if threejs_v2_dir is None:
        return None
    return _load_json(str(threejs_v2_dir / pack_id / "catalog.json"))


BUNDLE_STEMS = {"characters", "br_characters", "generic_characters"}


def glb_index(threejs_v2_dir: Path | None, pack_id: str) -> tuple[dict[str, str], dict[str, str]]:
    """(exact stem -> path, lowercase stem -> path), both relative to ``threejs_v2_dir``."""
    manifest = load_manifest(threejs_v2_dir, pack_id)
    exact: dict[str, str] = {}
    ci: dict[str, str] = {}
    if not manifest:
        return exact, ci
    for rel in manifest.get("models") or []:
        stem = Path(rel).stem
        rel_full = f"{pack_id}/{rel}"
        exact.setdefault(stem, rel_full)
        ci.setdefault(stem.lower(), rel_full)
    return exact, ci


def bundle_glbs(threejs_v2_dir: Path | None, pack_id: str) -> list[str]:
    """Bundle GLBs (many assets as named nodes) listed in the pack manifest."""
    manifest = load_manifest(threejs_v2_dir, pack_id)
    if not manifest:
        return []
    return [
        f"{pack_id}/{rel}" for rel in manifest.get("models") or []
        if Path(rel).stem.lower() in BUNDLE_STEMS
    ]


def catalog_by_id(threejs_v2_dir: Path | None, pack_id: str) -> dict[str, dict]:
    doc = load_catalog(threejs_v2_dir, pack_id)
    if not doc:
        return {}
    return {a["id"]: a for a in doc.get("assets") or [] if isinstance(a, dict) and a.get("id")}


def _allowed(asset: dict, field: str) -> bool:
    return may_overlay(asset, field, "vlm_reviewed")


def apply_threejs_overlay(asset: dict, entry: dict | None, glb_rel: str | None) -> dict:
    """Wire ``files.glb`` (always, when a GLB stem match exists) and overlay
    reviewed text/placement/type onto ``asset`` in place."""
    if glb_rel:
        asset.setdefault("files", {})["glb"] = glb_rel
    if not entry or not entry.get("reviewed"):
        return asset

    prov = asset.setdefault("provenance", {})

    name = (entry.get("name") or "").strip()
    if name and _allowed(asset, "name"):
        asset["name"] = name
        prov["name"] = "vlm_reviewed"

    desc = (entry.get("description") or "").strip()
    if desc and _allowed(asset, "description"):
        asset["description"] = desc
        prov["description"] = "vlm_reviewed"

    new_tags = [t for t in (entry.get("tags") or []) if isinstance(t, str) and _TOKEN_RE.match(t)]
    if new_tags and _allowed(asset, "tags"):
        merged = list(asset.get("tags") or [])
        for t in new_tags:
            if t not in merged:
                merged.append(t)
        asset["tags"] = merged
        prov["tags"] = "vlm_reviewed"

    raw_role = entry.get("semantic_role")
    if raw_role and _allowed(asset, "semantic_role"):
        role, detail = normalize_semantic_role(raw_role, raw_role)
        asset["semantic_role"] = role
        asset["semantic_detail"] = detail
        prov["semantic_role"] = "vlm_reviewed"

    etype = TYPE_MIGRATION.get(entry.get("type") or "", entry.get("type") or "")
    if etype in TYPES and _allowed(asset, "type"):
        asset["type"] = etype
        prov["type"] = "vlm_reviewed"

    notes = (entry.get("ai_notes") or "").strip()
    if notes and _allowed(asset, "ai_notes"):
        asset["ai_notes"] = notes
        prov["ai_notes"] = "vlm_reviewed"

    place_in = entry.get("placement") or {}
    place = asset.setdefault("placement", {})
    if place_in and _allowed(asset, "placement"):
        if place_in.get("mount") is not None:
            place["mount"] = normalize_mount(place_in.get("mount"))
        if place_in.get("attachment") is not None:
            place["attachment"] = normalize_attachment(place_in.get("attachment"))
        for key in ("height", "orientation", "preferred_floors", "constraints"):
            val = place_in.get(key)
            if val:
                place[key] = val
        prov["placement"] = "vlm_reviewed"
    # preferred_contexts is additive-only, so union it in regardless of the
    # placement field's precedence — it never overwrites a curated value.
    contexts = place_in.get("preferred_contexts") or []
    if contexts:
        pc = place.setdefault("preferred_contexts", [])
        for c in contexts:
            if c not in pc:
                pc.append(c)

    return asset
