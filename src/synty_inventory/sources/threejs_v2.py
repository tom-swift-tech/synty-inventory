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

from ..discover import PackRef
from ..merge import may_overlay
from ..naming import should_skip
from ..scan import RawAsset
from ..schema import (
    MODULE_ROLE_FROM_STILLS,
    MODULE_ROLES,
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


def glb_raw_assets(threejs_v2_dir: Path | None, pack_id: str) -> list[RawAsset]:
    """One RawAsset per converted GLB stem. Fills catalog holes the Unity
    prefab scan misses (GLB-only meshes, package-shared kit dumped into this
    pack's threejs-v2 folder). Overlay later wires ``files.glb``."""
    exact, _ = glb_index(threejs_v2_dir, pack_id)
    out: list[RawAsset] = []
    for stem, rel in exact.items():
        if stem.lower() in BUNDLE_STEMS:
            continue
        if should_skip(rel, stem):
            continue
        out.append(RawAsset(id=stem, kit=None, shared=False, engine="Unity"))
    out.sort(key=lambda a: a.id)
    return out


def discover_converted_packs(
    threejs_v2_dir: Path | None, existing_ids: set[str] | None = None
) -> list[PackRef]:
    """Packs that have a converted tree but no Unity/Unreal scan root.

    Coffee Shop, and any future convert-only drop, otherwise never appear in
    synty_catalogs.
    """
    have = existing_ids or set()
    refs: list[PackRef] = []
    if threejs_v2_dir is None or not threejs_v2_dir.is_dir():
        return refs
    for path in sorted(threejs_v2_dir.iterdir()):
        if not path.is_dir() or path.name.startswith(("_", ".")):
            continue
        if path.name.startswith("GEN_"):
            continue
        if path.name in have:
            continue
        if not (path / "manifest.json").is_file():
            continue
        refs.append(PackRef(pack_id=path.name, engine="Unity", extras={"threejs_dir": path}))
    return refs


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
        role, detail = normalize_semantic_role(raw_role)
        asset["semantic_role"] = role
        asset["semantic_detail"] = detail
        prov["semantic_role"] = "vlm_reviewed"

    etype = TYPE_MIGRATION.get(entry.get("type") or "", entry.get("type") or "")
    if (
        etype in TYPES
        and _allowed(asset, "type")
        and not (asset.get("part") or {}).get("class")
    ):
        asset["type"] = etype
        prov["type"] = "vlm_reviewed"

    if _allowed(asset, "module") and not (asset.get("part") or {}).get("class"):
        mrole = _stills_module_role(entry, asset.get("id") or "")
        if mrole:
            module = asset.setdefault("module", {})
            module["role"] = mrole
            prov["module"] = "vlm_reviewed"

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

    _tune_kit_placement(asset)
    return asset


def _stills_module_role(entry: dict, asset_id: str) -> str | None:
    explicit = None
    module = entry.get("module")
    if isinstance(module, dict):
        explicit = module.get("role")
    elif isinstance(module, str):
        explicit = module
    if not explicit:
        explicit = entry.get("module_role")
    if explicit in MODULE_ROLES:
        return explicit
    low = (asset_id or "").lower()
    for token, role in (
        ("roof", "roof"),
        ("door", "door"),
        ("corner", "corner"),
        ("stair", "stairs"),
        ("window", "window"),
    ):
        if token in low:
            return role
    raw = (entry.get("semantic_role") or "").strip()
    mapped = MODULE_ROLE_FROM_STILLS.get(raw)
    if mapped and mapped in MODULE_ROLES:
        return mapped
    etype = entry.get("type") or ""
    migrated = TYPE_MIGRATION.get(etype, etype)
    if not str(migrated).startswith("building") and not etype.startswith("building"):
        return None
    if "floor" in low:
        return "floor"
    if etype in {"building/kit", "building/modular"} or migrated == "building/module":
        return "floor"
    if etype == "building/hero" or migrated == "building/shell":
        return "hero"
    return None


def _tune_kit_placement(asset: dict) -> None:
    """Stackable kit pieces are not ground props. Roofs are not storey 1."""
    role = (asset.get("module") or {}).get("role")
    if role not in {"roof", "floor", "corner", "door", "base", "hero", "shell", "stairs"}:
        return
    place = asset.setdefault("placement", {})
    cons = [c for c in (place.get("constraints") or []) if c != "ground_only"]
    for token in ("snap_to_grid", "seat_on_contact"):
        if token not in cons:
            cons.append(token)
    place["constraints"] = cons
    if role == "roof":
        place["preferred_floors"] = []
        place["height"] = "roof"
    elif role == "door":
        place["preferred_floors"] = [1]
    elif role == "floor":
        place["preferred_floors"] = []
        if place.get("height") in {"grade", "ground"}:
            place["height"] = "storey"
