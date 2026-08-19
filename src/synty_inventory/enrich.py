"""Apply rule / viewer / optional VLM enrichment onto skeleton assets."""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path

from . import knowledge
from .merge import stamp_auto
from .sources.glb_measure import apply_measured_bounds, bundle_index, load_cache, save_cache
from .sources.threejs_v2 import apply_threejs_overlay, bundle_glbs, catalog_by_id, glb_index
from .sources.viewer import (
    apply_viewer_module,
    load_type_sign_usage,
    load_viewer_pieces,
    load_viewer_props,
    load_viewer_signs,
    measured_size,
)
from .schema import (
    TYPE_MIGRATION,
    default_placeable,
    dimensions_from_bounds,
    empty_files,
    empty_module,
    empty_part,
    empty_paths,
    empty_placement,
    kind_for_type,
    make_bounds,
    normalize_semantic_role,
    paths_from_files,
    pivot_from_aabb,
)


def _unique(seq: list) -> list:
    out = []
    seen = set()
    for item in seq:
        key = item if not isinstance(item, list) else tuple(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:48]


def apply_viewer_overlays(
    asset: dict,
    signs: dict,
    props: dict,
    usage: dict[str, list[str]],
) -> dict:
    aid = asset["id"]
    sign = signs.get(aid)
    if sign:
        text = (sign.get("text") or "").strip()
        kind = (sign.get("kind") or "").strip()
        sign_tags = list(sign.get("tags") or [])
        if text:
            kind_label = {
                "poster": "Poster advertisement",
                "neon": "Neon sign",
                "word-plaque": "Hanging word plaque",
                "billboard": "Billboard",
            }.get(kind, "Sign")
            asset["description"] = (
                f'{kind_label} depicting "{text}". '
                "Mount on the street-facing facade, keep off windows, readable from the sidewalk."
            )
            if kind == "neon":
                asset["description"] += " Night-readable letterform or icon; pair with other neon on nightlife fronts."
            if "civic-only" in sign_tags:
                asset["description"] += " Civic/corporate copy only — never on bars, vice, or residential junk ads."
            slug_tag = _slug(text)
            if slug_tag and slug_tag not in asset["tags"]:
                asset["tags"].append(slug_tag)
            pretty = text.split("/")[0].strip()
            if pretty and len(pretty) <= 28:
                asset["name"] = pretty.title() if pretty.isupper() or pretty.islower() else pretty
                if kind == "poster" and "poster" not in asset["name"].lower():
                    asset["name"] = f"{asset['name']} Poster"
                elif kind == "neon" and "neon" not in asset["name"].lower():
                    asset["name"] = f"{asset['name']} Neon"
        if kind and kind not in asset["tags"]:
            asset["tags"].append(kind)
        for t in sign_tags:
            if t not in asset["tags"]:
                asset["tags"].append(t)
        if text:
            asset["semantic_role"] = "advertisement"
            asset["semantic_detail"] = f"displays_{_slug(text)}"
        if "civic-only" in sign_tags:
            cons = asset["placement"].setdefault("constraints", [])
            if "civic_facade_only" not in cons:
                cons.append("civic_facade_only")
            asset["ai_notes"] = (
                "Civic/corporate facades only (police, bank, office, outpost). "
                "Do not place on bars, strip clubs, noodle shops, or vice posters."
            )
        elif kind == "neon":
            asset["ai_notes"] = (
                "Nightlife / shop night identity. Cluster 2–4 neon pieces on the +Z street face; "
                "do not put neon on civic heroes."
            )
        elif kind == "poster":
            asset["ai_notes"] = (
                "Facade poster. One cluster per storey band. "
                "Respect civic-only siblings; do not mix civic posters onto nightlife or vice fronts."
            )
        asset.setdefault("provenance", {})["description"] = "viewer"
        asset.setdefault("_auto", {})
    prop = props.get(aid)
    if prop:
        if prop.get("note") and prop["note"] not in asset["ai_notes"]:
            asset["ai_notes"] = f"{asset['ai_notes']} {prop['note']}"
        if prop.get("mount"):
            asset["placement"]["mount"] = (
                "wall" if prop["mount"] == "facade" else prop["mount"]
            )
        if prop.get("look"):
            asset["placement"]["orientation"] = f"looks_{prop['look']}"
    contexts = usage.get(aid) or []
    if contexts:
        pc = asset["placement"].setdefault("preferred_contexts", [])
        for c in contexts:
            if c not in pc:
                pc.append(c)
    sign = signs.get(aid) or {}
    if "civic-only" in (sign.get("tags") or []):
        civic_ctx = {"police", "office", "outpost", "bank", "civic", "hospital", "security"}
        pc = asset["placement"].setdefault("preferred_contexts", [])
        asset["placement"]["preferred_contexts"] = [
            c for c in pc if c in civic_ctx or c.endswith("_station") or c == "civic_building"
        ] or ["civic_building"]
    return asset


PACK_PREFIX_CLASS = {
    # pack_id prefix → (type, kind, placeable, semantic_role). Applied only when
    # the stem-level rules left the asset on the generic "prop" fallback —
    # e.g. INTERFACE_* HUD stems (AssetDemo_/Button_/Dial_/Slider_…) and
    # ANIMATION_* clips that carry no recognisable prefix.
    "INTERFACE_": ("ui", "ui", False, "ui_element"),
    "ANIMATION_": ("animation", "animation", False, "animation_clip"),
    "SIMPLE_Sky": ("skybox", "material", False, "skybox"),
}


def _apply_pack_overrides(inferred: dict, pack_id: str, raw) -> None:
    for prefix, (atype, kind, placeable, role) in PACK_PREFIX_CLASS.items():
        if not pack_id.startswith(prefix):
            continue
        stem_up = (raw.id or "").upper()
        # real meshes inside these packs (demo props, targets) stay as classified
        if stem_up.startswith(("SM_", "SK_", "CHR_")):
            return
        if inferred.get("type") in {"prop", None} or inferred.get("type") == atype:
            inferred["type"] = atype
            inferred["kind"] = kind
            inferred["placeable"] = placeable
            inferred["semantic_role"] = role
            inferred.setdefault("semantic_detail", "")
        return


def skeleton_asset(
    raw,
    pack_id: str,
    viewer_data: Path | None,
) -> dict:
    inferred = knowledge.infer(raw.id)
    _apply_pack_overrides(inferred, pack_id, raw)
    measured = measured_size(viewer_data, pack_id, raw.id)
    bounds = None
    if measured:
        aabb = measured.get("aabb") or {}
        bounds = make_bounds(
            measured["approx"],
            source="measured",
            min_=aabb.get("min"),
            max_=aabb.get("max"),
            pivot=pivot_from_aabb(aabb["min"], aabb["max"]) if aabb.get("min") and aabb.get("max") else "unknown",
        )
    # Rule-based dimension hints are NOT bounds. They are kept only as a
    # search hint under ``size_hint`` so an agent can never mistake them for a
    # measurement. Phase 2 fills bounds from GLB measurement instead.
    prefab = raw.prefab.rel if raw.prefab else None
    mesh = raw.mesh.rel if raw.mesh else None
    files = empty_files()
    if raw.engine == "Unreal":
        files["unreal_uasset"] = mesh
        mesh = None
    files["unity_prefab"] = prefab
    files["unity_mesh"] = mesh
    files["unity_materials"] = list(raw.materials or [])
    atype = TYPE_MIGRATION.get(inferred["type"], inferred["type"])
    kind = inferred.get("kind") or kind_for_type(atype, bool(prefab))
    role, detail = normalize_semantic_role(inferred["semantic_role"], inferred.get("semantic_detail"))
    asset = {
        "id": raw.id,
        "name": inferred["name"],
        "kind": kind,
        "placeable": inferred.get("placeable", default_placeable(atype, kind)),
        "type": atype,
        "category": list(inferred["category"]),
        "tags": list(inferred["tags"]),
        "description": inferred["description"],
        "semantic_role": role,
        "semantic_detail": detail,
        "placement": deepcopy(inferred["placement"]) if inferred["placement"] else empty_placement(),
        "bounds": bounds,
        "dimensions": dimensions_from_bounds(bounds),
        "size_hint": [round(float(x), 4) for x in inferred["dimensions_hint"]] if inferred.get("dimensions_hint") else None,
        "module": deepcopy(inferred.get("module") or empty_module()),
        "part": deepcopy(inferred.get("part") or empty_part()),
        "files": files,
        "paths": paths_from_files(files),
        "thumbnail": raw.thumbnail,
        "ai_notes": inferred["ai_notes"],
        "kit": raw.kit,
        "shared_kit": bool(raw.shared),
        "guid": raw.guid,
    }
    if raw.id in knowledge.CURATED:
        for field in ("name", "type", "category", "tags", "description", "semantic_role", "placement", "ai_notes"):
            asset.setdefault("provenance", {})[field] = "curated"
    return stamp_auto(asset)


def enrich_catalog(
    catalog: dict,
    viewer_data: Path | None,
    threejs_v2: Path | None = None,
    catalogs_dir: Path | None = None,
    vlm_fn=None,
    vlm_limit: int = 0,
) -> dict:
    """Layer every enrichment source onto the rule-based skeleton, in
    precedence order: viewer signs/props (existing) -> viewer module/aabb ->
    threejs-v2 VLM-reviewed catalog overlay (also wires ``files.glb``) ->
    GLB-measured bounds (the authoritative last pass, see
    sources.glb_measure.apply_measured_bounds) -> stamp_auto.
    """
    pack_id = catalog["pack_id"]
    signs = load_viewer_signs(viewer_data, pack_id)
    props = load_viewer_props(viewer_data, pack_id)
    usage = load_type_sign_usage(viewer_data, pack_id)
    pieces = load_viewer_pieces(viewer_data, pack_id)
    tj_catalog = catalog_by_id(threejs_v2, pack_id)
    glb_exact, glb_ci = glb_index(threejs_v2, pack_id)
    bundles = bundle_index(threejs_v2, pack_id, bundle_glbs(threejs_v2, pack_id))

    cache_path = (catalogs_dir / "_measure_cache.json") if catalogs_dir else None
    cache = load_cache(cache_path) if cache_path else {}
    stats = {"measured": 0, "missing_glb": 0, "measure_failed": 0, "skipped": 0, "disagree": 0}

    vlm_done = 0
    for asset in catalog["assets"]:
        apply_viewer_overlays(asset, signs, props, usage)
        apply_viewer_module(asset, pieces.get(asset["id"]))
        glb_rel = glb_exact.get(asset["id"]) or glb_ci.get(asset["id"].lower())
        apply_threejs_overlay(asset, tj_catalog.get(asset["id"]), glb_rel)
        apply_measured_bounds(asset, threejs_v2, cache, stats, bundles=bundles)
        stamp_auto(asset)
        if vlm_fn is None:
            continue
        if vlm_limit and vlm_done >= vlm_limit:
            continue
        # Prefer signs / attachments for VLM
        high = asset["type"] == "prop/signage" or "sign" in asset.get("category", [])
        if not high and vlm_limit:
            continue
        updated = vlm_fn(asset)
        if updated:
            vlm_done += 1

    if cache_path is not None and cache:
        save_cache(cache_path, cache)
    catalog["_measure_stats"] = stats
    return catalog


def ensure_schema_defaults(asset: dict) -> dict:
    asset.setdefault("category", [])
    asset.setdefault("tags", [])
    asset.setdefault("description", "")
    asset.setdefault("semantic_role", "")
    asset.setdefault("placement", empty_placement())
    asset.setdefault("files", empty_files())
    asset.setdefault("paths", empty_paths())
    asset.setdefault("module", empty_module())
    asset.setdefault("part", empty_part())
    asset.setdefault("bounds", None)
    asset.setdefault("semantic_detail", "")
    asset.setdefault("thumbnail", None)
    asset.setdefault("ai_notes", "")
    return asset
