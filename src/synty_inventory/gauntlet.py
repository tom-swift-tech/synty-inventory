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
    dims = (asset.get("dimensions") or {}).get("approx") or []
    if len(dims) != 3 or not all(isinstance(n, (int, float)) and n > 0 for n in dims):
        bad.append("dimensions missing")
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


def run_gauntlet(catalogs_dir: Path) -> dict:
    gates: list[dict] = []

    def gate(name: str, ok: bool, detail: str) -> None:
        gates.append({"gate": name, "ok": ok, "detail": detail})

    docs = []
    if catalogs_dir.is_dir():
        for p in sorted(catalogs_dir.glob("*.json")):
            if p.name == "index.json":
                continue
            doc = load_catalog(p)
            if doc:
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

    ok = all(g["ok"] for g in gates)
    return {"ok": ok, "gates": gates}
