"""Assembly recipes — "how the pieces are used", as queryable catalog data.

A recipe is an engine-neutral grammar: ordered steps, each selecting eligible
pieces from the catalogs by structured criteria (type, role, module/part
fields, tags, explicit ids) and saying how many / how to lay them out. Three
sources are merged, later ones override earlier by ``id``:

1. Package recipes shipped in ``synty_inventory/recipes/*.json`` (authored:
   ship kit, station interior, main street row, apartment block).
2. asset-viewer building types (``<viewer_data>/types/<pack>.json``) converted
   on the fly — the generator grammars that already drive the Kit Viewer.
3. User recipes in ``<catalogs>/recipes/*.json``.

``resolve_recipe`` turns each step's selector into concrete pieces with bounds
and per-engine files, so an agent gets "here is the grammar and here are the
exact prefabs/GLBs that fit each slot" in one call.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from .catalog import load_all_catalogs
from .project import slim_row

PACKAGE_RECIPES_DIR = Path(__file__).parent / "recipes"

RECIPE_REQUIRED = ("id", "kind", "label", "description", "steps")
STEP_REQUIRED = ("role", "select")
SELECT_KEYS = {
    "ids",
    "pack",
    "type",
    "semantic_role",
    "semantic_detail",
    "module_role",
    "module_family",
    "part_class",
    "size_class",
    "part_slot_region",
    "tags_any",
    "tags_all",
    "contexts_any",
    "placeable",
    "id_prefix",
    "id_regex",
}
LAYOUTS = (
    "single",
    "row_along_x",
    "stack_along_y",
    "mirror_x_pair",
    "attach_rear",
    "attach_front",
    "attach_under",
    "facade_band",
    "roof_pad",
    "scatter_on_surface",
    "grid_xz",
    "free",
)

_TOKEN = re.compile(r"[a-z0-9]+")


# --- loading ---------------------------------------------------------------------------


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def validate_recipe(doc: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["recipe is not an object"]
    for key in RECIPE_REQUIRED:
        if key not in doc:
            errors.append(f"missing {key}")
    if not isinstance(doc.get("steps"), list) or not doc.get("steps"):
        errors.append("steps must be a non-empty list")
        return errors
    for i, step in enumerate(doc["steps"]):
        p = f"steps[{i}]"
        if not isinstance(step, dict):
            errors.append(f"{p} not an object")
            continue
        for key in STEP_REQUIRED:
            if key not in step:
                errors.append(f"{p} missing {key}")
        sel = step.get("select")
        if not isinstance(sel, dict):
            errors.append(f"{p}.select must be an object")
        else:
            for key in sel:
                if key not in SELECT_KEYS:
                    errors.append(f"{p}.select unknown key {key!r}")
        if "layout" in step and step["layout"] not in LAYOUTS:
            errors.append(f"{p}.layout invalid: {step['layout']!r}")
        count = step.get("count")
        if count is not None and not (
            isinstance(count, list) and len(count) == 2 and all(isinstance(n, int) for n in count)
        ):
            errors.append(f"{p}.count must be [min,max] ints")
    return errors


def _viewer_type_to_recipe(pack_id: str, t: dict, pack_doc: dict) -> dict:
    """Convert one asset-viewer building type into recipe form (lossless enough
    for agents; the viewer keeps its own file for the Kit Viewer)."""
    steps: list[dict] = []
    for i, hero in enumerate(t.get("heroes") or []):
        steps.append(
            {
                "role": "hero",
                "select": {"ids": list(hero.get("ids") or []), "pack": pack_id},
                "count": [1, 1],
                "layout": "single",
                "weight": hero.get("weight", 1),
                "required": "hero" in (t.get("required") or []),
            }
        )
    for annex in t.get("annex") or []:
        steps.append(
            {
                "role": "annex",
                "select": {"ids": list(annex.get("ids") or []), "pack": pack_id},
                "count": [0, 1],
                "layout": "row_along_x",
                "chance": annex.get("chance"),
                "note": annex.get("kind"),
            }
        )
    facade = t.get("facade") or {}
    for key, role, cnt in (
        ("neon", "neon", "neonCount"),
        ("ads", "ad", "adCount"),
        ("banners", "sign", "bannerCount"),
    ):
        ids = facade.get(key) or []
        if not ids:
            continue
        steps.append(
            {
                "role": role,
                "select": {"ids": ids, "pack": pack_id},
                "count": list(facade.get(cnt) or [0, 1]),
                "layout": "facade_band",
                "heights_m": list(facade.get("heights") or []),
                "required": role == "sign" and "sign" in (t.get("required") or []),
            }
        )
    roof = t.get("roof") or {}
    if roof.get("ids"):
        steps.append(
            {
                "role": "roof",
                "select": {"ids": roof["ids"], "pack": pack_id},
                "count": list(roof.get("count") or [0, 1]),
                "layout": "roof_pad",
            }
        )
    dress = t.get("dress") or t.get("street") or {}
    if dress.get("ids"):
        steps.append(
            {
                "role": "dress",
                "select": {"ids": dress["ids"], "pack": pack_id},
                "count": list(dress.get("count") or [0, 1]),
                "layout": "scatter_on_surface",
            }
        )
    return {
        "id": f"building_{t['id']}",
        "kind": "building",
        "label": t.get("label") or t["id"],
        "description": (
            f"{t.get('label') or t['id']} building for {pack_id}: weighted hero shell, optional annex, "
            "facade signage on the +Z street face, roof dressing. Imported from the asset-viewer "
            "generator grammar."
        ),
        "packs": [pack_id],
        "source": "asset_viewer_types",
        "height_bands_m": t.get("height") or {},
        "street_note": pack_doc.get("street") or pack_doc.get("note") or "",
        "constraints": [
            "no_city_layout_pieces",
            "no_scaling",
            "snap_0_25",
            "street_face_plus_z",
            "civic_types_civic_only_ads",
        ],
        "steps": steps,
    }


def load_recipes(catalogs_dir: Path | None, viewer_data: Path | None = None) -> dict[str, dict]:
    recipes: dict[str, dict] = {}

    def add(doc: dict | None, origin: str) -> None:
        if not doc or not isinstance(doc, dict) or not doc.get("id"):
            return
        doc = dict(doc)
        doc.setdefault("source", origin)
        recipes[doc["id"]] = doc

    if PACKAGE_RECIPES_DIR.is_dir():
        for p in sorted(PACKAGE_RECIPES_DIR.glob("*.json")):
            add(_read_json(p), "package")
    if viewer_data and (viewer_data / "types").is_dir():
        for p in sorted((viewer_data / "types").glob("*.json")):
            doc = _read_json(p)
            if not doc:
                continue
            pack_id = doc.get("pack") or p.stem
            for t in doc.get("types") or []:
                if t.get("id"):
                    rec = _viewer_type_to_recipe(pack_id, t, doc)
                    # one id per pack: building_shop@POLYGON_City
                    rec["id"] = f"{rec['id']}@{pack_id}"
                    add(rec, "asset_viewer_types")
    if catalogs_dir and (catalogs_dir / "recipes").is_dir():
        for p in sorted((catalogs_dir / "recipes").glob("*.json")):
            add(_read_json(p), "user")
    return recipes


# --- selection -------------------------------------------------------------------------------


def _tagset(asset: dict) -> set[str]:
    return {t.lower() for t in asset.get("tags") or []} | {c.lower() for c in asset.get("category") or []}


def asset_matches(asset: dict, pack_id: str, sel: dict) -> bool:
    if sel.get("pack") and sel["pack"].lower() not in pack_id.lower():
        return False
    aid = asset.get("id") or ""
    if sel.get("ids") is not None:
        return aid in set(sel["ids"])
    if sel.get("id_prefix") and not aid.startswith(sel["id_prefix"]):
        return False
    if sel.get("id_regex") and not re.search(sel["id_regex"], aid):
        return False
    if sel.get("placeable") is not None and bool(asset.get("placeable")) != bool(sel["placeable"]):
        return False
    for key in ("type", "semantic_role", "semantic_detail"):
        want = sel.get(key)
        if want is None:
            continue
        want = want if isinstance(want, list) else [want]
        if (asset.get(key) or "") not in want:
            return False
    module = asset.get("module") or {}
    for skey, mkey in (("module_role", "role"), ("module_family", "family")):
        want = sel.get(skey)
        if want is None:
            continue
        want = want if isinstance(want, list) else [want]
        have = module.get(mkey)
        if have is None or not any(str(have).lower() == str(w).lower() for w in want):
            return False
    part = asset.get("part") or {}
    for skey, pkey in (("part_class", "class"), ("size_class", "size_class")):
        want = sel.get(skey)
        if want is None:
            continue
        want = want if isinstance(want, list) else [want]
        if part.get(pkey) not in want:
            return False
    slot_region_want = sel.get("part_slot_region")
    if slot_region_want is not None:
        slot_region_want = slot_region_want if isinstance(slot_region_want, list) else [slot_region_want]
        if (part.get("slot") or {}).get("region") not in slot_region_want:
            return False
    tags = _tagset(asset)
    if sel.get("tags_any") and not any(t.lower() in tags for t in sel["tags_any"]):
        return False
    if sel.get("tags_all") and not all(t.lower() in tags for t in sel["tags_all"]):
        return False
    if sel.get("contexts_any"):
        ctx = {c.lower() for c in (asset.get("placement") or {}).get("preferred_contexts") or []}
        if not any(c.lower() in ctx for c in sel["contexts_any"]):
            return False
    return True


def select_pieces(
    docs: Iterable[dict],
    sel: dict,
    pack: str | None = None,
    limit: int | None = None,
    engine: str | None = None,
    fields: list[str] | None = None,
) -> list[dict]:
    out: list[dict] = []
    for doc in docs:
        pid = doc.get("pack_id") or ""
        if pack and pack.lower() not in pid.lower():
            continue
        for asset in doc.get("assets") or []:
            if asset_matches(asset, pid, sel):
                out.append(slim_row(pid, asset, engine=engine, fields=fields))
    out.sort(key=lambda p: (p["pack"], p["id"] or ""))
    return out[:limit] if limit else out


def resolve_recipe(
    catalogs_dir: Path,
    recipe: dict,
    pack: str | None = None,
    limit_per_step: int = 16,
    engine: str | None = None,
    fields: list[str] | None = None,
) -> dict:
    docs = load_all_catalogs(catalogs_dir)
    steps_out = []
    missing_required = []
    for step in recipe.get("steps") or []:
        pieces = select_pieces(docs, step.get("select") or {}, pack=pack, limit=limit_per_step, engine=engine, fields=fields)
        total = len(select_pieces(docs, step.get("select") or {}, pack=pack))
        if step.get("required") and not pieces:
            missing_required.append(step.get("role"))
        steps_out.append(
            {
                **{k: v for k, v in step.items() if k != "select"},
                "select": step.get("select"),
                "eligible_count": total,
                "eligible": pieces,
            }
        )
    out = dict(recipe)
    out["resolved_steps"] = steps_out
    out["missing_required_roles"] = missing_required
    out["complete"] = not missing_required
    return out


def kit_families(
    catalogs_dir: Path,
    pack: str | None = None,
    engine: str | None = None,
    fields: list[str] | None = None,
) -> dict[str, dict]:
    """Group module pieces by family → role → slim rows (what an assembler
    stacks). Pack and kit are already on the family entry, so per-piece rows
    keep only id / size / file (plus any ``fields`` asked for)."""
    out: dict[str, dict] = {}
    for doc in load_all_catalogs(catalogs_dir):
        pid = doc.get("pack_id") or ""
        if pack and pack.lower() not in pid.lower():
            continue
        for asset in doc.get("assets") or []:
            module = asset.get("module") or {}
            fam = module.get("family")
            if not fam:
                continue
            key = f"{fam}@{pid}"
            entry = out.setdefault(key, {"family": fam, "pack_id": pid, "roles": {}, "count": 0})
            role = module.get("role") or "misc"
            row = slim_row(pid, asset, engine=engine, fields=fields)
            for drop in ("pack", "type", "role", "kit", "kit_role"):
                row.pop(drop, None)
            entry["roles"].setdefault(role, []).append(row)
            entry["count"] += 1
    for entry in out.values():
        for role in entry["roles"]:
            entry["roles"][role].sort(key=lambda p: p["id"] or "")
    return dict(sorted(out.items()))


def kit_family(
    catalogs_dir: Path,
    family: str,
    pack: str | None = None,
    engine: str | None = None,
    fields: list[str] | None = None,
) -> list[dict]:
    fams = kit_families(catalogs_dir, pack, engine=engine, fields=fields)
    needle = family.lower()
    return [v for k, v in fams.items() if v["family"].lower() == needle or needle in v["family"].lower()]


# --- matching a free-text request to a recipe ----------------------------------------------


def match_recipes(recipes: dict[str, dict], text: str, limit: int = 3) -> list[dict]:
    """Rank recipes against a request like "row of shops for a small town main
    street" using label/description/trigger tokens. Returns [{id, score, label}]."""
    tokens = set(_TOKEN.findall(text.lower()))
    if not tokens:
        return []
    scored = []
    for rid, rec in recipes.items():
        hay_tokens = set(_TOKEN.findall(f"{rec.get('label','')} {rec.get('description','')} {rid}".lower()))
        triggers = {t.lower() for t in rec.get("triggers") or []}
        score = 0
        for t in tokens:
            if t in triggers:
                score += 10
            elif t in hay_tokens:
                score += 2
        # trigger phrases ("main street", "space ship") as bigrams
        low = text.lower()
        for phrase in triggers:
            if " " in phrase and phrase in low:
                score += 15
        if score > 0:
            scored.append((score, rid))
    scored.sort(key=lambda r: (-r[0], r[1]))
    return [
        {"id": rid, "score": score, "label": recipes[rid].get("label"), "kind": recipes[rid].get("kind")}
        for score, rid in scored[:limit]
    ]
