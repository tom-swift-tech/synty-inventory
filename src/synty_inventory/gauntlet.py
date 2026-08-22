"""Phase 4 acceptance gates against catalogs on disk + optional live rescan."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .catalog import catalog_path, load_catalog
from .merge import merge_catalog
from .query import (
    get_asset_details,
    get_placement_guidance,
    search_assets,
    suggest_assets_for,
    suggest_recipes_for,
)
from .recipes import kit_family, load_recipes, resolve_recipe
from .schema import validate_catalog
from .sources.godot import SLUG_PACK_OVERRIDES as GODOT_SLUG_PACK_OVERRIDES
from .sources.godot import discover_pack_dirs as discover_godot_pack_dirs

# Real-tree coverage of files.godot_scene over geometry-bearing (kind in
# {prefab, mesh}) assets across the three mapped packs, observed by reading
# the live catalogs + GoDot export tree on the reference machine (read-only
# scratch analysis, not committed): POLYGON_City 333/337 (98.8%),
# POLYGON_Starter 52/55 (94.5%), POLYGON_Particle_FX 0/12 (0% — the export
# only ships ~13 demo particle scenes, none matching the pack's SM_-stem
# "mesh"-kind entries; the pack's 227 "fx"-kind entries are excluded from
# this denominator, same as bounds_coverage/glb_paths above). Aggregate:
# 385/404 = 95.3%. Floor pinned a few points under that so a real
# regression trips the gate without being brittle to +/- one asset.
GODOT_COVERAGE_FLOOR = 0.90


QUALITY_IDS = ("SM_Prop_Sign_Police_01", "SM_Prop_Sign_Barber_01")

# Ceiling in JSON bytes for the canonical POI query set (see token_budget
# gate). Measured 48 KB on the full 12-pack catalogs with slim rows and
# recipe limit_per_step=16; pinned ~33% above so real regressions trip the
# gate without being brittle to a handful of new assets.
TOKEN_BUDGET_BYTES = 64_000


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


def run_gauntlet(catalogs_dir: Path, threejs_v2: Path | None = None, godot_root: Path | None = None) -> dict:
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

    if godot_root is not None:
        mapped = discover_godot_pack_dirs(godot_root)
        expected_packs = set(GODOT_SLUG_PACK_OVERRIDES.values())
        resolved_packs = expected_packs & set(mapped)
        missing_packs = sorted(expected_packs - resolved_packs)

        dangling = []
        matched = 0
        checked = 0
        for doc in docs:
            pid = doc.get("pack_id")
            if pid not in mapped:
                continue
            for a in (doc.get("assets") or []):
                rel = (a.get("files") or {}).get("godot_scene")
                if not rel:
                    continue
                checked += 1
                if (Path(godot_root) / rel).is_file():
                    matched += 1
                else:
                    dangling.append(f"{pid}/{a.get('id')}: {rel}")

        godot_placeable = [a for doc in docs if doc.get("pack_id") in mapped for a in (doc.get("assets") or []) if _geometry(a)]
        covered = sum(1 for a in godot_placeable if (a.get("files") or {}).get("godot_scene"))
        cov_ratio = (covered / len(godot_placeable)) if godot_placeable else 0
        worst_godot = _pack_breakdown(lambda a: bool((a.get("files") or {}).get("godot_scene")))
        gate(
            "godot_paths",
            not missing_packs and not dangling and bool(godot_placeable) and cov_ratio >= GODOT_COVERAGE_FLOOR,
            f"{len(resolved_packs)}/{len(expected_packs)} mapped packs resolved (missing={missing_packs}); "
            f"{matched}/{checked} non-null files.godot_scene paths exist on disk; "
            f"{covered}/{len(godot_placeable)} geometry-bearing assets covered ({cov_ratio:.1%}, "
            f"floor {GODOT_COVERAGE_FLOOR:.0%}); worst packs: {worst_godot}; "
            f"dangling={dangling[:5]}",
        )
    else:
        gate("godot_paths", True, "godot_root not configured — skipped")

    prov_ok = bool(police_asset and (police_asset.get("provenance") or {}).get("description") == "vlm_reviewed")
    desc_ok = bool(police_asset and "letters" in (police_asset.get("description") or "").lower())
    gate(
        "vlm_overlay_applied",
        prov_ok and desc_ok,
        f"description={(police_asset or {}).get('description')!r}",
    )

    # --- Phase 3/4/5 gates: assembly semantics, recipes, suggest pointers ----
    space = next((d for d in docs if d.get("pack_id") == "POLYGON_SciFi_Space"), None)
    if space:
        parts = [a for a in space["assets"] if a["id"].startswith("SM_Veh_Part_")]
        ships = [a for a in space["assets"] if a["id"].startswith("SM_Ship_")]
        bad_parts = [a["id"] for a in parts if a.get("type") != "vehicle/part" or not (a.get("part") or {}).get("class")]
        bad_ships = [a["id"] for a in ships if a.get("type") != "vehicle/spacecraft"]
        interior = [a for a in space["assets"] if a["id"].startswith(("SM_Bld_Corridor_", "SM_Bld_Bridge_", "SM_Bld_Crew_"))]
        bad_int = [a["id"] for a in interior if a.get("type") != "building/interior_module"]
        gate(
            "scifi_space_assembly_types",
            bool(parts) and not bad_parts and not bad_ships and not bad_int,
            f"{len(parts)} ship parts typed vehicle/part with class, {len(ships)} spacecraft, "
            f"{len(interior)} interior modules; bad={bad_parts[:3] + bad_ships[:3] + bad_int[:3]}",
        )
        # Mesh-analysed mating faces: every hull has six sockets (measured cap
        # or AABB fallback), every child part a mount with the hull socket it
        # fits unrotated; nearly all mounts must be a real measured cap, not
        # the AABB fallback, or the analysis regressed. Pylon pods and wings
        # are the known non-class-axis cases (Engine_08/09 on +x, wing roots
        # on the dominant x side) -- pin them so a heuristic change shows up.
        with_glb = [a for a in parts if (a.get("files") or {}).get("glb")]
        bodies = [a for a in with_glb if (a.get("part") or {}).get("class") == "body"]
        children = [a for a in with_glb if (a.get("part") or {}).get("class") != "body"]
        bad_sockets = [a["id"] for a in bodies if len((a.get("part") or {}).get("sockets") or []) != 6]
        no_mount = [a["id"] for a in children if not (a.get("part") or {}).get("mount")]
        no_role = [a["id"] for a in children if a.get("part", {}).get("mount") and not a["part"]["mount"].get("parent_role")]
        measured_mounts = sum(
            1 for a in children if ((a.get("part") or {}).get("mount") or {}).get("source") == "measured"
        )
        mount_ratio = measured_mounts / len(children) if children else 0.0
        by_id = {a["id"]: ((a.get("part") or {}).get("mount") or {}) for a in children}
        pinned = {"SM_Veh_Part_Engine_08": ("+x", "left"), "SM_Veh_Part_Engine_09": ("+x", "left"), "SM_Veh_Part_Wing_09": ("-x", "right")}
        unpinned = [
            f"{pid}={by_id.get(pid, {}).get('axis')}/{by_id.get(pid, {}).get('parent_role')}"
            for pid, (axis, role) in pinned.items()
            if pid in by_id and (by_id[pid].get("axis"), by_id[pid].get("parent_role")) != (axis, role)
        ]
        if threejs_v2 is not None and with_glb:
            gate(
                "ship_part_sockets",
                not bad_sockets and not no_mount and not no_role and not unpinned and mount_ratio >= 0.95,
                f"{len(bodies)} hulls with 6 sockets (bad={bad_sockets[:3]}), "
                f"{len(children) - len(no_mount)}/{len(children)} child parts with a mount "
                f"({measured_mounts} measured caps = {mount_ratio:.0%}); no_mount={no_mount[:3]}, "
                f"no_parent_role={no_role[:3]}, off-convention={unpinned}",
            )
        else:
            gate("ship_part_sockets", True, "threejs_v2 not configured — skipped")
    else:
        gate("scifi_space_assembly_types", True, "POLYGON_SciFi_Space not on disk — skipped")
        gate("ship_part_sockets", True, "POLYGON_SciFi_Space not on disk — skipped")

    # Mech body slots/variants + standalone attachment slot/bone
    # (sources/mech.py). id-prefix selection, not `type`/`kind`: POLYGON_Mech
    # stems have no knowledge.py classification rule yet (separate lane), so
    # a type-based denominator would be vacuous or fail for someone else's
    # reason. Skips cleanly when the pack isn't on disk yet.
    mech_pack = next((d for d in docs if d.get("pack_id") == "POLYGON_Mech"), None)
    if mech_pack:
        body = [a for a in mech_pack["assets"] if a.get("id", "").startswith("SM_Veh_Mech_")]
        bad_body = [
            a["id"]
            for a in body
            if not (a.get("mech") or {}).get("skeleton")
            or not (a.get("mech") or {}).get("slots")
            or not (a.get("mech") or {}).get("variants")
        ]
        attach = [a for a in mech_pack["assets"] if a.get("id", "").startswith("SM_Mech_")]
        with_slot = [a for a in attach if (a.get("part") or {}).get("slot") and (a.get("part") or {}).get("attach_bone")]
        attach_ratio = len(with_slot) / len(attach) if attach else 0.0
        attach_types = dict(Counter(a.get("type") for a in attach))

        # Pinned ground-truth conventions from the 6 factory prefabs
        # (parsed 2026-08-19, see sources/mech.py docstring): a specific
        # chest weapon-attach node roots on Spine_01, the cockpit slot roots
        # on CockpitDoor, and there are exactly 6 factory variants each
        # toggling 60-69 of the master mesh's 196 nodes.
        chest_pin_ok = any(
            "geo_r_chest_attach_weapon_01" in (slot.get("geo_nodes") or []) and slot.get("bone") == "Spine_01"
            for a in body
            for slot in (a.get("mech") or {}).get("slots") or []
        )
        cockpit_pin_ok = any(
            slot.get("region") == "cockpit" and slot.get("bone") == "CockpitDoor"
            for a in body
            for slot in (a.get("mech") or {}).get("slots") or []
        )
        variant_counts = []
        if body:
            variants = (body[0].get("mech") or {}).get("variants") or {}
            variant_counts = sorted(len(nodes) for nodes in variants.values())
        variants_ok = len(variant_counts) == 6 and all(60 <= n <= 69 for n in variant_counts)

        gate(
            "mech_slots",
            bool(body) and not bad_body and bool(attach) and attach_ratio >= 0.95 and chest_pin_ok and cockpit_pin_ok and variants_ok,
            f"{len(body)} SM_Veh_Mech_ body assets with skeleton+slots+variants (bad={bad_body[:3]}); "
            f"{len(with_slot)}/{len(attach)} SM_Mech_ attachments have part.slot+attach_bone "
            f"({attach_ratio:.0%}, attachment types={attach_types}); "
            f"pins: chest_attach_weapon_01->Spine_01={chest_pin_ok}, cockpit->CockpitDoor={cockpit_pin_ok}, "
            f"variants={variant_counts} (want 6x[60,69])",
        )
    else:
        gate("mech_slots", True, "POLYGON_Mech not on disk — skipped")

    recipes = load_recipes(catalogs_dir)
    want = {"ship_kit": None, "station_interior": None, "apartment_block": "POLYGON_City", "main_street_row": "POLYGON_City"}
    incomplete = []
    for rid, pack in want.items():
        rec = recipes.get(rid)
        if not rec:
            incomplete.append(f"{rid}: missing")
            continue
        res = resolve_recipe(catalogs_dir, rec, pack=pack)
        if not res["complete"]:
            incomplete.append(f"{rid}: missing roles {res['missing_required_roles']}")
    gate("recipes_resolve", not incomplete, "all package recipes complete" if not incomplete else "; ".join(incomplete))

    pointers = {
        "build me a fighter space ship": "ship_kit",
        "a row of shops for main street in a small town": "main_street_row",
        "six storey apartment building": "apartment_block",
        "space station corridor and bridge interior": "station_interior",
    }
    wrong = []
    for text, rid in pointers.items():
        hits = suggest_recipes_for(catalogs_dir, text)
        if not hits or hits[0]["id"] != rid:
            wrong.append(f"{text!r} -> {hits[0]['id'] if hits else None}")
    gate("suggest_recipe_pointers", not wrong, "all assembly prompts point at the right recipe" if not wrong else "; ".join(wrong))

    # Clips, HUD widgets and screen-space FX in ANIMATION_/INTERFACE_ packs must
    # not be offered to an assembler; only real SM_ demo meshes may stay placeable.
    nonplace = [
        a["id"]
        for d in docs
        for a in d["assets"]
        if d.get("pack_id", "").startswith(("ANIMATION_", "INTERFACE_"))
        and a.get("placeable")
        and not a["id"].upper().startswith(("SM_", "SK_", "CHR_"))
    ]
    gate("nonplaceable_packs", not nonplace, f"{len(nonplace)} ANIMATION_/INTERFACE_ non-mesh assets still placeable {nonplace[:5]}")

    # Phase 1 pin: the canonical "assemble a POI" call set must stay cheap
    # in an agent's context. Slim rows put the full-catalog set at ~48 KB
    # (search 20 ≈ 4.6 KB, suggest ≈ 3 KB, ship_kit + main_street_row
    # resolves ≈ 37 KB, kit Apartment ≈ 3.5 KB) vs ~290 KB before
    # projection. Partial/fixture catalogs emit less and pass trivially.
    poi_calls: list = [
        search_assets(catalogs_dir, "police station", limit=20),
        suggest_assets_for(catalogs_dir, "police station facade"),
        kit_family(catalogs_dir, "Apartment", "POLYGON_City"),
    ]
    for rid, pack in (("ship_kit", None), ("main_street_row", "POLYGON_City")):
        rec = recipes.get(rid)
        if rec:
            poi_calls.append(resolve_recipe(catalogs_dir, rec, pack=pack))
    poi_bytes = sum(len(json.dumps(c)) for c in poi_calls)
    gate(
        "token_budget",
        poi_bytes <= TOKEN_BUDGET_BYTES,
        f"canonical POI query set = {poi_bytes} bytes (ceiling {TOKEN_BUDGET_BYTES})",
    )

    ok = all(g["ok"] for g in gates)
    return {"ok": ok, "gates": gates}
