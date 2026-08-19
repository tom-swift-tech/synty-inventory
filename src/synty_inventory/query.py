"""Query API over written catalogs."""

from __future__ import annotations

import re
from pathlib import Path

from .catalog import load_all_catalogs

_TOKEN = re.compile(r"[a-z0-9]+")

CONTEXT_ALIASES = {
    "police station": ["police", "station", "civic"],
    "police": ["police", "law_enforcement", "civic"],
    "barber": ["barber", "salon", "pole"],
    "barber pole": ["barber", "pole", "side_mount"],
    "barber shop": ["barber", "salon"],
    "first floor": ["first_floor", "1"],
    "first-floor": ["first_floor", "1"],
    "ground floor": ["first_floor", "1"],
    "billboard": ["billboard", "roadside", "advertisement"],
    "roadside": ["roadside", "street"],
    "facade": ["facade", "wall-mounted", "wall"],
    "wall": ["wall", "wall-mounted"],
    "side attachment": ["side_bracket", "side_mount", "attachment"],
    "side-mounted": ["side_bracket", "side_mount"],
    "neon": ["neon", "nightlife"],
    "hospital": ["hospital", "medical"],
    "fire": ["fire", "fire_station"],
    "cafe": ["cafe", "coffee"],
    "shop": ["shop", "commercial", "storefront"],
    "civic": ["civic"],
    "traffic": ["traffic", "roadside"],
}


ENGINES = ("unity", "unreal", "godot", "threejs", "all")


def engine_files(asset: dict, engine: str | None) -> dict:
    """Select the per-engine file paths an agent should instantiate. Semantics
    never change with engine; only which ``files.*`` keys are surfaced."""
    files = asset.get("files") or {}
    eng = (engine or "all").lower()
    if eng == "unity":
        return {k: files.get(k) for k in ("unity_prefab", "unity_mesh", "unity_materials")}
    if eng == "unreal":
        return {"unreal_uasset": files.get("unreal_uasset"), "glb": files.get("glb")}
    if eng in {"godot", "threejs"}:
        return {"glb": files.get("glb"), "godot_scene": files.get("godot_scene")}
    return dict(files)


def _result(pid: str, asset: dict, score: float | None = None, engine: str | None = None, why: bool = False) -> dict:
    out = {
        "pack_id": pid,
        "id": asset.get("id"),
        "name": asset.get("name"),
        "type": asset.get("type"),
        "placeable": asset.get("placeable"),
        "category": asset.get("category"),
        "tags": asset.get("tags"),
        "semantic_role": asset.get("semantic_role"),
        "semantic_detail": asset.get("semantic_detail"),
        ("why" if why else "description"): asset.get("description"),
        "placement": asset.get("placement"),
        "module": asset.get("module"),
        "part": asset.get("part"),
        "bounds": asset.get("bounds"),
        "dimensions": asset.get("dimensions"),
        "files": engine_files(asset, engine),
        "paths": asset.get("paths"),
        "ai_notes": asset.get("ai_notes"),
    }
    if score is not None:
        out["score"] = round(score, 2)
    return out


def _match_v2_filters(
    asset: dict,
    *,
    types: list[str] | None,
    roles: list[str] | None,
    module_roles: list[str] | None,
    part_classes: list[str] | None,
    include_nonplaceable: bool,
) -> bool:
    if not include_nonplaceable and asset.get("placeable") is False:
        return False
    if types and (asset.get("type") or "") not in set(types):
        return False
    if roles and (asset.get("semantic_role") or "") not in set(roles):
        return False
    if module_roles and ((asset.get("module") or {}).get("role") or "") not in set(module_roles):
        return False
    if part_classes and ((asset.get("part") or {}).get("class") or "") not in set(part_classes):
        return False
    return True


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _haystack(asset: dict) -> str:
    place = asset.get("placement") or {}
    parts = [
        asset.get("id") or "",
        asset.get("name") or "",
        asset.get("type") or "",
        asset.get("description") or "",
        asset.get("semantic_role") or "",
        asset.get("semantic_detail") or "",
        asset.get("ai_notes") or "",
        " ".join(asset.get("tags") or []),
        " ".join(asset.get("category") or []),
        place.get("mount") or "",
        place.get("attachment") or "",
        place.get("height") or "",
        " ".join(place.get("constraints") or []),
        " ".join(place.get("preferred_contexts") or []),
    ]
    return " ".join(parts).lower()


def _score(query: str, asset: dict, extra_tokens: list[str] | None = None) -> float:
    q = query.lower().strip()
    tokens = tokenize(query)
    if extra_tokens:
        tokens = list(dict.fromkeys(tokens + extra_tokens))
    if not tokens:
        return 0.0
    hay = _haystack(asset)
    score = 0.0
    aid = (asset.get("id") or "").lower()
    name = (asset.get("name") or "").lower()
    role = f"{asset.get('semantic_role') or ''} {asset.get('semantic_detail') or ''}".lower()
    tags = {t.lower() for t in asset.get("tags") or []}
    cats = {c.lower() for c in asset.get("category") or []}
    ctx = {c.lower() for c in (asset.get("placement") or {}).get("preferred_contexts") or []}
    if q and q in aid:
        score += 80
    if q and q in name:
        score += 50
    for t in tokens:
        if t in aid:
            score += 18
        if t in name.split():
            score += 14
        if t in tags:
            score += 16
        if t in cats:
            score += 12
        if t in ctx:
            score += 16
        if t in role:
            score += 20
        if t in hay:
            score += 4
    # identity signs beat random props when the query is a building type
    if asset.get("type") == "prop/signage":
        score += 6
    return score


def _match_filters(
    asset: dict,
    pack: str | None,
    tags: list[str] | None,
    category: list[str] | None,
    constraints: list[str] | None,
    pack_id: str,
) -> bool:
    if pack and pack_id.lower() != pack.lower() and pack.lower() not in pack_id.lower():
        return False
    if tags:
        have = {t.lower() for t in asset.get("tags") or []}
        if not all(t.lower() in have or t.lower() in _haystack(asset) for t in tags):
            return False
    if category:
        have = {c.lower() for c in asset.get("category") or []}
        if not any(c.lower() in have for c in category):
            return False
    if constraints:
        have = {c.lower() for c in (asset.get("placement") or {}).get("constraints") or []}
        hay = _haystack(asset)
        for c in constraints:
            cl = c.lower()
            if cl.startswith("no ") or cl.startswith("without "):
                forbidden = cl.split(" ", 1)[1]
                if forbidden in hay and "do_not_cover_" + forbidden.replace(" ", "_") not in have:
                    # allow if the asset itself is not a window piece
                    if forbidden in (asset.get("id") or "").lower():
                        return False
                continue
            if cl not in have and cl not in hay:
                return False
    return True


def list_packs(catalogs_dir: Path) -> list[dict]:
    out = []
    for doc in load_all_catalogs(catalogs_dir):
        out.append(
            {
                "pack_id": doc.get("pack_id"),
                "engine": doc.get("engine"),
                "origin": doc.get("origin"),
                "style": doc.get("style"),
                "asset_count": doc.get("asset_count") or len(doc.get("assets") or []),
                "scanned_at": doc.get("scanned_at"),
                "source": doc.get("source"),
            }
        )
    return out


def _iter_assets(catalogs_dir: Path, pack: str | None = None):
    for doc in load_all_catalogs(catalogs_dir):
        pid = doc.get("pack_id") or ""
        if pack and pack.lower() not in pid.lower():
            continue
        for asset in doc.get("assets") or []:
            yield pid, doc, asset


def search_assets(
    catalogs_dir: Path,
    query: str,
    pack: str | None = None,
    tags: list[str] | None = None,
    category: list[str] | None = None,
    constraints: list[str] | None = None,
    limit: int = 20,
    types: list[str] | None = None,
    roles: list[str] | None = None,
    module_roles: list[str] | None = None,
    part_classes: list[str] | None = None,
    include_nonplaceable: bool = False,
    engine: str | None = None,
) -> list[dict]:
    scored: list[tuple[float, str, dict]] = []
    for pid, _doc, asset in _iter_assets(catalogs_dir, pack):
        if not _match_filters(asset, pack, tags, category, constraints, pid):
            continue
        if not _match_v2_filters(
            asset,
            types=types,
            roles=roles,
            module_roles=module_roles,
            part_classes=part_classes,
            include_nonplaceable=include_nonplaceable,
        ):
            continue
        s = _score(query, asset)
        # measured pieces are more useful to an assembler than unmeasured ones
        if (asset.get("bounds") or {}).get("source") == "measured":
            s += 3
        if s <= 0 and query.strip():
            continue
        scored.append((s, pid, asset))
    scored.sort(key=lambda r: (-r[0], r[1], r[2].get("id") or ""))
    return [_result(pid, asset, s, engine) for s, pid, asset in scored[:limit]]


def get_asset_details(catalogs_dir: Path, asset_id_or_name: str) -> dict | None:
    needle = asset_id_or_name.lower().strip()
    exact = []
    fuzzy = []
    for pid, doc, asset in _iter_assets(catalogs_dir):
        aid = (asset.get("id") or "").lower()
        name = (asset.get("name") or "").lower()
        if aid == needle or name == needle:
            exact.append((pid, doc, asset))
        elif needle in aid or needle in name:
            fuzzy.append((pid, doc, asset))
    pick = exact or fuzzy
    if not pick:
        return None
    pid, doc, asset = pick[0]
    out = dict(asset)
    out["pack_id"] = pid
    out["pack_style"] = doc.get("style")
    out["engine"] = doc.get("engine")
    out["source"] = doc.get("source")
    return out


def _expand_context(context: str) -> list[str]:
    low = context.lower()
    extra: list[str] = []
    for phrase, toks in CONTEXT_ALIASES.items():
        if phrase in low:
            extra.extend(toks)
    extra.extend(tokenize(context))
    # "first floor" is a storey constraint, not a hit on SM_Bld_*_Floor_*
    if "first floor" in low or "first-floor" in low or "ground floor" in low:
        extra = [t for t in extra if t not in {"floor", "first"}]
        extra.append("first_floor")
    return list(dict.fromkeys(extra))


def suggest_recipes_for(
    catalogs_dir: Path, context: str, viewer_data: Path | None = None, limit: int = 3
) -> list[dict]:
    """Assembly requests ("row of shops", "fighter ship") should get a grammar,
    not only a ranked piece list. Lazy import keeps query free of recipe I/O
    unless asked."""
    from .recipes import load_recipes, match_recipes

    return match_recipes(load_recipes(catalogs_dir, viewer_data), context, limit=limit)


def suggest_assets_for(
    catalogs_dir: Path,
    context: str,
    pack: str | None = None,
    limit: int = 12,
    include_nonplaceable: bool = False,
    engine: str | None = None,
) -> list[dict]:
    extra = _expand_context(context)
    low = context.lower()
    constraints: list[str] = []
    if "without window" in low or "no window" in low:
        constraints.append("do_not_cover_windows")
    if "first-floor" in low or "first floor" in low:
        extra.append("1")
    if "side" in low and ("attach" in low or "pole" in low or "barber" in low):
        extra.extend(["side_bracket", "side_mount"])

    scored: list[tuple[float, str, dict]] = []
    for pid, _doc, asset in _iter_assets(catalogs_dir, pack):
        if not include_nonplaceable and asset.get("placeable") is False:
            continue
        floors = (asset.get("placement") or {}).get("preferred_floors") or []
        if ("first-floor" in low or "first floor" in low) and floors and 1 not in floors:
            continue
        if "without window" in low or "no window" in low:
            if "window" in (asset.get("id") or "").lower():
                continue
        s = _score(context, asset, extra_tokens=extra)
        role = (asset.get("semantic_role") or "").lower()
        atype = asset.get("type") or ""
        if "police" in low and "police" in role:
            s += 40
        if "barber" in low and "barber" in role:
            s += 40
        if "billboard" in low and "billboard" in (asset.get("id") or "").lower():
            s += 30
        if any(k in low for k in ("sign", "pole", "plaque", "neon", "poster", "billboard")):
            if atype == "prop/signage":
                s += 20
            elif atype.startswith("building"):
                s -= 25
        if s <= 0:
            continue
        scored.append((s, pid, asset))
    scored.sort(key=lambda r: (-r[0], r[1], r[2].get("id") or ""))
    return [_result(pid, asset, s, engine, why=True) for s, pid, asset in scored[:limit]]


def get_placement_guidance(catalogs_dir: Path, asset_id: str) -> dict | None:
    details = get_asset_details(catalogs_dir, asset_id)
    if details is None:
        return None
    return {
        "id": details.get("id"),
        "pack_id": details.get("pack_id"),
        "name": details.get("name"),
        "semantic_role": details.get("semantic_role"),
        "placement": details.get("placement"),
        "bounds": details.get("bounds"),
        "module": details.get("module"),
        "part": details.get("part"),
        "dimensions": details.get("dimensions"),
        "ai_notes": details.get("ai_notes"),
        "files": details.get("files"),
        "paths": details.get("paths"),
    }
