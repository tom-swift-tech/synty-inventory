"""Apply rule / viewer / optional VLM enrichment onto skeleton assets."""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path

from . import knowledge
from .dimensions import (
    load_type_sign_usage,
    load_viewer_props,
    load_viewer_signs,
    measured_size,
)
from .merge import stamp_auto
from .schema import empty_paths, empty_placement


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
            asset["semantic_role"] = f"displays_{_slug(text)}"
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


def skeleton_asset(
    raw,
    pack_id: str,
    viewer_data: Path | None,
) -> dict:
    inferred = knowledge.infer(raw.id)
    measured = measured_size(viewer_data, pack_id, raw.id)
    if measured:
        dims = {
            "approx": measured["approx"],
            "units": "meters",
            "source": "measured",
        }
    else:
        dims = {
            "approx": [round(float(x), 4) for x in inferred["dimensions_hint"]],
            "units": "meters",
            "source": "heuristic",
        }
    prefab = raw.prefab.rel if raw.prefab else None
    mesh = raw.mesh.rel if raw.mesh else None
    asset = {
        "id": raw.id,
        "name": inferred["name"],
        "type": inferred["type"],
        "category": list(inferred["category"]),
        "tags": list(inferred["tags"]),
        "description": inferred["description"],
        "semantic_role": inferred["semantic_role"],
        "placement": deepcopy(inferred["placement"]) if inferred["placement"] else empty_placement(),
        "dimensions": dims,
        "paths": {
            "prefab": prefab,
            "mesh": mesh,
            "materials": list(raw.materials or []),
        },
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
    vlm_fn=None,
    vlm_limit: int = 0,
) -> dict:
    pack_id = catalog["pack_id"]
    signs = load_viewer_signs(viewer_data, pack_id)
    props = load_viewer_props(viewer_data, pack_id)
    usage = load_type_sign_usage(viewer_data, pack_id)
    vlm_done = 0
    for asset in catalog["assets"]:
        apply_viewer_overlays(asset, signs, props, usage)
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
    return catalog


def ensure_schema_defaults(asset: dict) -> dict:
    asset.setdefault("category", [])
    asset.setdefault("tags", [])
    asset.setdefault("description", "")
    asset.setdefault("semantic_role", "")
    asset.setdefault("placement", empty_placement())
    asset.setdefault("paths", empty_paths())
    asset.setdefault("thumbnail", None)
    asset.setdefault("ai_notes", "")
    return asset
