"""Phase 4 acceptance gates against catalogs on disk + optional live rescan."""

from __future__ import annotations

from pathlib import Path

from .catalog import catalog_path, load_catalog
from .merge import merge_catalog
from .query import get_asset_details, get_placement_guidance, search_assets, suggest_assets_for
from .schema import validate_catalog


QUALITY_IDS = ("SM_Prop_Sign_Police_01", "SM_Prop_Sign_Barber_01")


def _rich_enough(asset: dict) -> list[str]:
    bad = []
    if not asset:
        return ["missing"]
    desc = asset.get("description") or ""
    if len(desc) < 80:
        bad.append("description too short")
    if not asset.get("semantic_role"):
        bad.append("no semantic_role")
    place = asset.get("placement") or {}
    for key in ("mount", "height", "attachment", "constraints", "preferred_contexts"):
        if not place.get(key):
            bad.append(f"placement.{key} empty")
    notes = asset.get("ai_notes") or ""
    if len(notes) < 40:
        bad.append("ai_notes too thin")
    size = (asset.get("bounds") or {}).get("size") or []
    if len(size) != 3 or not all(isinstance(n, (int, float)) and n > 0 for n in size):
        bad.append("bounds missing")
    paths = asset.get("paths") or {}
    if not paths.get("prefab") and not paths.get("mesh"):
        bad.append("no prefab/mesh path")
    return bad


def _path_exists(source: dict | None, rel: str | None) -> bool:
    if not rel or not source:
        return False
    root = source.get("extracted")
    if not root:
        return False
    return (Path(root) / rel).is_file()


def run_gauntlet(catalogs_dir: Path, threejs_v2: Path | None = None) -> dict:
    gates: list[dict] = []

    def gate(name: str, ok: bool, detail: str) -> None:
        gates.append({"gate": name, "ok": ok, "detail": detail})

    docs = []
    if catalogs_dir.is_dir():
        for p in sorted(catalogs_dir.glob("*.json")):
            if p.name == "index.json" or p.name.startswith("_"):
                continue
            doc = load_catalog(p)
            if doc and doc.get("pack_id"):
                docs.append(doc)

    gate("catalogs_present", len(docs) >= 2, f"{len(docs)} pack catalogs")

    path_ok = 0
    path_checked = 0
    schema_bad = []
    for doc in docs:
        errs = validate_catalog(doc)
        if errs:
            schema_bad.append(f"{doc.get('pack_id')}: {errs[:3]}")
        src = doc.get("source") or {}
        for asset in (doc.get("assets") or [])[:80]:
            prefab = (asset.get("paths") or {}).get("prefab")
            mesh = (asset.get("paths") or {}).get("mesh")
            if prefab:
                path_checked += 1
                path_ok += int(_path_exists(src, prefab))
            if mesh:
                path_checked += 1
                path_ok += int(_path_exists(src, mesh))
    gate("schema_valid", not schema_bad, "; ".join(schema_bad) or "all catalogs valid")
    ratio = (path_ok / path_checked) if path_checked else 0
    gate(
        "paths_exist",
        path_checked > 0 and ratio >= 0.95,
        f"{path_ok}/{path_checked} prefab/mesh paths exist on disk",
    )

    quality_bits = []
    for aid in QUALITY_IDS:
        details = get_asset_details(catalogs_dir, aid)
        bad = _rich_enough(details or {})
        quality_bits.append(f"{aid}: {'ok' if not bad else ', '.join(bad)}")
        if details and details.get("paths"):
            src = details.get("source")
            prefab = details["paths"].get("prefab")
            if prefab and not _path_exists(src, prefab):
                quality_bits[-1] += " (prefab missing on disk)"
    gate(
        "high_value_richness",
        all(": ok" in b for b in quality_bits),
        "; ".join(quality_bits),
    )

    police = search_assets(catalogs_dir, "police", limit=8)
    police_hit = any("police" in (r.get("id") or "").lower() for r in police)
    gate("search_police", police_hit, f"{len(police)} hits, top={(police[0]['id'] if police else None)}")

    details = get_asset_details(catalogs_dir, "SM_Prop_Sign_Police_01")
    place = get_placement_guidance(catalogs_dir, "SM_Prop_Sign_Police_01")
    gate(
        "details_and_placement",
        bool(details and place and place.get("placement", {}).get("mount") == "wall"),
        f"mount={None if not place else place.get('placement', {}).get('mount')}",
    )

    sug_police = suggest_assets_for(catalogs_dir, "police station facade")
    sug_barber = suggest_assets_for(catalogs_dir, "first-floor barber pole")
    sug_bill = suggest_assets_for(catalogs_dir, "roadside billboard without windows")
    top_p = sug_police[0]["id"] if sug_police else None
    top_b = sug_barber[0]["id"] if sug_barber else None
    top_bill = sug_bill[0]["id"] if sug_bill else None
    gate(
        "suggest_contexts",
        top_p == "SM_Prop_Sign_Police_01" and top_b == "SM_Prop_Sign_Barber_01" and bool(top_bill),
        f"police->{top_p}; barber->{top_b}; billboard->{top_bill}",
    )

    # merge preservation: if police catalog exists, provenance/curated fields stay
    city = load_catalog(catalog_path(catalogs_dir, "POLYGON_City"))
    police_asset = None
    if city:
        police_asset = next((a for a in city["assets"] if a["id"] == "SM_Prop_Sign_Police_01"), None)
    gate(
        "city_pack_present",
        bool(city and police_asset),
        f"POLYGON_City assets={0 if not city else len(city.get('assets') or [])}",
    )

    if city and police_asset:
        locked = dict(city)
        locked_assets = []
        marker = "HUMAN LOCK: do not clobber this description."
        for a in city["assets"]:
            copy = dict(a)
            if copy.get("id") == "SM_Prop_Sign_Police_01":
                copy["description"] = marker
                copy["locked_fields"] = ["description"]
                copy["provenance"] = dict(copy.get("provenance") or {})
                copy["provenance"]["description"] = "human"
            locked_assets.append(copy)
        locked["assets"] = locked_assets
        # Simulate a rescan that would try to replace the description.
        incoming = dict(city)
        incoming_assets = []
        for a in city["assets"]:
            copy = dict(a)
            if copy.get("id") == "SM_Prop_Sign_Police_01":
                copy["description"] = "REPLACED by scanner — should not win"
            incoming_assets.append(copy)
        incoming["assets"] = incoming_assets
        merged = merge_catalog(locked, incoming)
        kept = next(a for a in merged["assets"] if a["id"] == "SM_Prop_Sign_Police_01")
        gate(
            "rescan_preserves_human",
            kept.get("description") == marker,
            f"after merge description={kept.get('description')!r}",
        )
    else:
        gate("rescan_preserves_human", False, "no POLYGON_City police asset")

    # --- Phase 2 gates: threejs-v2 / GLB-measured sources ---------------------

    def _geometry(a: dict) -> bool:
        """Coverage denominator: placeable assets that have geometry to
        measure. Particle-system prefabs (kind fx) and UI have no mesh."""
        return bool(a.get("placeable")) and a.get("kind") in {"prefab", "mesh"}

    placeable = [a for doc in docs for a in (doc.get("assets") or []) if _geometry(a)]

    # Per-pack coverage, worst-first, so a failing aggregate gate points at
    # *which* packs to look at instead of just a global ratio. Low coverage
    # here usually traces to `placeable` over-assignment upstream (knowledge
    # infer classifying animation/UI/rig-part assets as placeable props) or
    # to composite character prefabs with no single matching GLB stem —
    # neither is a threejs-v2/glb_measure defect; see report for detail.
    def _pack_breakdown(pred) -> list[str]:
        rows = []
        for doc in docs:
            pack_placeable = [a for a in (doc.get("assets") or []) if _geometry(a)]
            if not pack_placeable:
                continue
            hit = sum(1 for a in pack_placeable if pred(a))
            rows.append((hit / len(pack_placeable), doc.get("pack_id"), hit, len(pack_placeable)))
        rows.sort()
        return [f"{pid} {hit}/{n} ({ratio:.0%})" for ratio, pid, hit, n in rows[:5]]

    measured = sum(1 for a in placeable if (a.get("bounds") or {}).get("source") == "measured")
    bounds_ratio = (measured / len(placeable)) if placeable else 0
    worst_bounds = _pack_breakdown(lambda a: (a.get("bounds") or {}).get("source") == "measured")
    gate(
        "bounds_coverage",
        bool(placeable) and bounds_ratio >= 0.95,
        f"{measured}/{len(placeable)} placeable assets have measured bounds ({bounds_ratio:.1%}); "
        f"worst packs: {worst_bounds}",
    )

    fake = [
        a["id"]
        for doc in docs
        for a in (doc.get("assets") or [])
        if a.get("bounds") is None and (a.get("dimensions") or {}).get("approx") is not None
    ]
    gate("no_fake_dimensions", not fake, f"{len(fake)} assets with dimensions.approx but no bounds: {fake[:5]}")

    if threejs_v2 is not None:
        glb_ok = 0
        glb_checked = 0
        for a in placeable:
            rel = (a.get("files") or {}).get("glb")
            if not rel:
                continue
            glb_checked += 1
            if (threejs_v2 / rel).is_file():
                glb_ok += 1
        glb_ratio = (glb_ok / len(placeable)) if placeable else 0
        worst_glb = _pack_breakdown(
            lambda a: bool((a.get("files") or {}).get("glb")) and (threejs_v2 / a["files"]["glb"]).is_file()
        )
        gate(
            "glb_paths",
            bool(placeable) and glb_ratio >= 0.90,
            f"{glb_ok}/{len(placeable)} placeable assets resolve files.glb under threejs_v2 "
            f"({glb_checked} had a path set); worst packs: {worst_glb}",
        )
    else:
        gate("glb_paths", True, "threejs_v2 not configured — skipped")

    prov_ok = bool(police_asset and (police_asset.get("provenance") or {}).get("description") == "vlm_reviewed")
    desc_ok = bool(police_asset and "letters" in (police_asset.get("description") or "").lower())
    gate(
        "vlm_overlay_applied",
        prov_ok and desc_ok,
        f"description={(police_asset or {}).get('description')!r}",
    )

    ok = all(g["ok"] for g in gates)
    return {"ok": ok, "gates": gates}
