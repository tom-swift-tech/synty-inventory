"""Hosted Grok vision pass for threejs-v2 pack catalogs.

``review`` is the local Ollama prose path and must not run on City / SciFi /
Starter. This module asks Grok 4.6 to look at stills and emit enum-locked
JSON for assembler-safe fields only, then merge-not-replace into
``catalog.json`` (the overlay ``sources.threejs_v2`` already ingests).

Forbidden from the model: ``placement.contact`` (measured GLB cap), ship/mech
sockets and bones, ``type`` on anything with ``part.class``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from importlib.resources import files as pkg_files
from pathlib import Path
from typing import Any, Callable, Sequence

from .review import RenderError, _load_json, _scaffold_catalog, _stem_index, _write_catalog
from .schema import (
    ATTACHMENTS,
    MODULE_ROLES,
    MOUNTS,
    ROLE_ALIASES,
    SEMANTIC_ROLES,
    TYPE_MIGRATION,
    TYPES,
    normalize_attachment,
    normalize_mount,
    normalize_semantic_role,
)
from .sources.threejs_v2 import BUNDLE_STEMS
from .vlm import HOSTED_DEFAULT_MODEL, query_hosted_vlm, vlm_available

CATALOG_NAME = "catalog.json"
MANIFEST_NAME = "manifest.json"
GOLD_DATA = "vision_gold_city.json"
DEFAULT_VIEWS: tuple[str, ...] = ("front", "quarter")
PROSE_ONLY_PREFIXES = ("SM_Veh_Part_", "SM_Mech_")
INTERIOR_KIT_PREFIXES = ("SM_Bld_Bridge_", "SM_Bld_Corridor_", "SM_Bld_Crew_")
_TAG_RE = re.compile(r"^[a-z0-9][a-z0-9_\-+.]*$")
ARTIFACT_TAGS = {
    "texture_atlas",
    "atlas",
    "atlas_bleed",
    "uv_artifact",
    "uv_bleed",
    "untextured",
    "shared_atlas",
    "placeholder_texture",
}
# Shared City albedo on SM_Bld_Base_* walls — not real posters/signage.
ATLAS_BLEED_TAGS = {
    "posters",
    "poster",
    "urban_signs",
    "advertising",
    "advertisement",
    "taxi",
    "police",
    "ambulance",
    "atm",
    "bus_stop",
    "city_life",
    "citylife",
}
ROOF_MOUNT_TOKENS = (
    "billboard",
    "roof",
    "spire",
    "cover",
    "tank",
    "vent",
    "antenna",
    "chimney",
    "hvac",
    "satdish",
    "acunit",
)
# Kit roof slabs (Apartment_Roof_01) sit on the lot grid. ``roof`` is in
# ROOF_MOUNT_TOKENS so we exclude ``*_Roof_##`` stems from mount=roof.
_KIT_ROOF_SLAB_RE = re.compile(r"(?:^|_)roof_\d+$")
KIT_GROUND_ROLES = frozenset({"base", "floor", "door", "corner", "stairs", "roof", "hero", "shell"})
CITY_LAYOUT_ROLES = frozenset({"ground_surface", "road_surface"})
VISION_ATTACHMENT_ALIASES = {
    "origin": "bottom",
    "base": "bottom",
    "base_to_ground": "bottom",
    "base_to_roof": "bottom",
}
# Synty stems encode kit slot. Used only to demote a false hero/shell, never
# to invent a slot the still did not support.
_FILENAME_KIT_SLOTS = (
    ("_door_", "door"),
    ("_corner_", "corner"),
    ("_stairs_", "stairs"),
    ("_stair_", "stairs"),
)
def _default_log(msg: str) -> None:
    print(msg, file=sys.stderr)


def default_stills_root() -> Path | None:
    """Viewer contact-sheet cache next to this checkout, if present."""
    env = os.environ.get("SYNTI_VISION_STILLS")
    if env:
        path = Path(env)
        return path if path.is_dir() else None
    here = Path(__file__).resolve()
    # .../tools/inventoryagent/src/synty_inventory/vision.py → tools/viewer/...
    candidate = here.parents[3] / "viewer" / "tasks" / "vision_qa" / "stills"
    return candidate if candidate.is_dir() else None


def load_gold(path: Path | None = None) -> dict:
    if path is not None:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    resource = pkg_files("synty_inventory").joinpath("data", GOLD_DATA)
    return json.loads(resource.read_text(encoding="utf-8"))


def prose_only(stem: str, existing: dict | None = None) -> bool:
    if any(stem.startswith(p) for p in PROSE_ONLY_PREFIXES):
        return True
    if existing:
        if (existing.get("part") or {}).get("class"):
            return True
        if existing.get("mech"):
            return True
    return False


def roof_mount_ok(stem: str) -> bool:
    low = stem.lower()
    if _KIT_ROOF_SLAB_RE.search(low):
        return False
    return any(token in low for token in ROOF_MOUNT_TOKENS)


def _shop_canopy_stem(stem: str) -> bool:
    low = stem.lower()
    return "awning" in low or "canopy" in low or ("shop" in low and "cover" in low)


def _roof_cover_stem(stem: str) -> bool:
    """SM_Bld_Cover_* hip/corrugated caps, not shop canopies."""
    low = stem.lower()
    return low.startswith("sm_bld_cover_") and "shop" not in low


def _base_kit_stem(stem: str) -> bool:
    return stem.lower().startswith("sm_bld_base_")


def filename_kit_slot(stem: str) -> str | None:
    low = stem.lower()
    for token, role in _FILENAME_KIT_SLOTS:
        if token in low:
            return role
    return None


def _clean_tags(values: Any, *, stem: str | None = None) -> list[str]:
    out: list[str] = []
    drop = set(ARTIFACT_TAGS)
    if stem and _base_kit_stem(stem):
        drop |= ATLAS_BLEED_TAGS
    for v in values or []:
        if not isinstance(v, str):
            continue
        t = v.strip().lower().replace(" ", "_")
        if t and t not in drop and _TAG_RE.match(t) and t not in out:
            out.append(t)
    return out


def _token_list(values: Any) -> list[str]:
    out: list[str] = []
    for v in values or []:
        if not isinstance(v, str):
            continue
        t = v.strip().lower().replace(" ", "_")
        if t and _TAG_RE.match(t) and t not in out:
            out.append(t)
    return out


def _floors(values: Any) -> list[int] | None:
    if not isinstance(values, list):
        return None
    out: list[int] = []
    for n in values:
        if isinstance(n, bool):
            continue
        if isinstance(n, int):
            v = n
        elif isinstance(n, str) and n.isdigit():
            v = int(n)
        else:
            continue
        if 1 <= v <= 20 and v not in out:
            out.append(v)
    return out


def adopt_mount(stem: str, new: str | None, existing: str | None) -> str | None:
    """Keep stills from flipping a wall/roof prop back to ground, and from
    seating generic signs on a roof."""
    if not new:
        return None
    adopted = normalize_mount(new)
    if adopted not in MOUNTS or adopted == "none":
        return None
    if adopted == "roof" and not roof_mount_ok(stem):
        return None
    old = normalize_mount(existing) if existing else "none"
    if old in {"wall", "pole", "pole_or_wall"} and adopted == "ground":
        return None
    if old == "roof" and adopted == "ground":
        return None
    return adopted


def build_prompt(stem: str, *, contact_sheet: bool) -> str:
    views = (
        "This image is a contact sheet: LEFT is the front view, RIGHT is a 3/4 quarter view."
        if contact_sheet
        else "Images are front then 3/4 quarter of the same mesh."
    )
    return (
        "You catalog a single low-poly Synty POLYGON-style 3D game asset from stills.\n"
        f"{views} Dark studio background. Ignore atlas bleed, UV seams, and any teal humanoid scale gizmo. "
        "City-kit wall modules often show a shared texture atlas (POLICE, TAXI, ATM, "
        "bus stop, City Life). That is bleed, not signage — do not name, tag, or "
        "describe those as posters, advertisements, or building identity.\n"
        f"The source filename stem is {stem!r}. Filenames are usually truthful about identity, "
        "but SM_Bld_* is NOT automatically a whole building — believe the still when it contradicts.\n"
        "Rules:\n"
        "- A one-storey window bay (no door, no roof, no second floor) is type building/module "
        "with module_role floor, never building/shell and never module_role hero.\n"
        "- Jagged, broken, or unfinished vertical side edges mean a kit module that snaps to a "
        "neighbor: type building/module, never building/shell, never module_role hero. A flat "
        "top slab on a jagged bay is NOT a finished whole-building roof.\n"
        "- Door bays (jagged sides + a door, even with a cornice slab) → module_role door. "
        "Corner / end-of-row bays → module_role corner even if they have an awning and a roof. "
        "Stoops → stairs. A complete shop or civic building with CLEAN closed corners on every "
        "side that happens to have a door is NOT a door bay.\n"
        "- A complete building has clean closed corners on every side, a finished roof, and no "
        "snap jags. Those are type building/shell, semantic_role building_shell, module_role hero "
        "— even if only one storey. A one-storey glass shop with clean closed sides, a flat roof, "
        "and blank side walls is a shell.\n"
        "- An open-topped hollow curtain-wall shaft with no roof and no door is a stackable "
        "building/module, module_role floor, never building/shell.\n"
        "- Kit roof slabs that cap a wall kit (flat cornice slab, same footprint as the bay) "
        "are module_role roof but still sit on the lot grid: mount ground, attachment bottom. "
        "Do not set mount=roof just because module_role is roof.\n"
        "- mount=roof is only for objects that rest ON an existing roof: spires, billboards, "
        "HVAC, tanks, and solid corrugated roof covers.\n"
        "- Solid corrugated terracotta/metal roof covers (ridged slab, hollow underside, no wood slats) "
        "are type building/module, module_role roof, mount roof, attachment bottom — not facade awnings.\n"
        "- Hollow slatted shop canopies/pergolas/awnings (open between slats) are type prop, "
        "semantic_role facade_dressing, mount wall (or roof if they clearly sit on an eave), "
        "attachment bottom or back_side. Always set mount for canopies; do not omit it.\n"
        "- Fire-escape landings with wall brackets are facade_dressing on a wall, not a floor bay. "
        "type prop, mount wall, attachment back_side. Omit module_role on props.\n"
        "- Grass park paths are semantic_role ground_surface and semantic_detail park_path_tile, "
        "not sidewalk tiles. Sidewalks use semantic_detail sidewalk_tile. Road asphalt is road_surface.\n"
        "- City roads, sidewalks, and park paths are type environment/city_layout, never type environment.\n"
        "- Extruded building-name letters (POLICE, HOSPITAL, …) are type prop/signage, "
        "semantic_role building_identity, mount wall, attachment back_side.\n"
        "- A striped barber pole with a wall bracket is building_identity, mount wall, "
        "attachment side_bracket, preferred_floors [1].\n"
        "- Billboard frames/panels mount roof unless they clearly have a street pole and base. "
        "attachment bottom.\n"
        "- Outdoor building kit pieces (floor/door/corner/roof/stairs/hero) use mount ground "
        "and attachment bottom. Never mount=module (that is interior kit snaps). Never "
        "attachment origin, base_to_ground, or base_to_roof — use bottom, back_side, or side_bracket.\n"
        "- Every building/shell gets module_role hero. Every building/module gets a kit "
        "module_role (floor/door/corner/roof/stairs/spire). Omit module_role on props, signs, "
        "vehicles, characters.\n"
        "- If mount is not visible and the asset is not a canopy, awning, or kit bay, omit it. "
        "Never guess roof or none for a wall plaque.\n"
        "- Do not output placement.contact, part, sockets, mech, or ai_notes.\n"
        "Reply with ONLY a JSON object using these exact keys (omit a key rather than inventing):\n"
        '{"name":"<short human name>",'
        '"description":"<1-2 sentences: what it is, colours, notable features>",'
        '"tags":["<lowercase snake_case>"],'
        '"tags_remove":["<tags the still contradicts>"],'
        f'"type":"<one of: {", ".join(TYPES)}>",'
        f'"semantic_role":"<one of: {", ".join(SEMANTIC_ROLES)}>",'
        '"semantic_detail":"<snake_case or empty>",'
        f'"module_role":"<one of: {", ".join(MODULE_ROLES)} or omit>",'
        f'"mount":"<one of: {", ".join(MOUNTS)}>",'
        f'"attachment":"<one of: {", ".join(ATTACHMENTS)}>",'
        '"orientation":"<snake_case>",'
        '"height":"<snake_case>",'
        '"preferred_floors":[<ints>],'
        '"constraints":["<snake_case>"],'
        '"preferred_contexts":["<snake_case>"]}'
    )


def sanitize_draft(stem: str, draft: dict | None, existing: dict | None = None) -> dict:
    """Enum-lock a model reply. Drops forbidden and invalid fields."""
    out: dict[str, Any] = {"id": stem}
    if not isinstance(draft, dict):
        return out
    blocked = prose_only(stem, existing)

    name = str(draft.get("name") or "").strip()
    if name:
        out["name"] = name
    desc = str(draft.get("description") or "").strip()
    if len(desc) >= 20:
        out["description"] = desc
    tags = _clean_tags(draft.get("tags"), stem=stem)
    if tags:
        out["tags"] = tags
    removed = _clean_tags(draft.get("tags_remove"), stem=stem)
    if removed:
        out["tags_remove"] = removed
    if blocked:
        return out

    raw_type = draft.get("type")
    if isinstance(raw_type, str) and raw_type.strip():
        migrated = TYPE_MIGRATION.get(raw_type.strip(), raw_type.strip())
        if migrated in TYPES:
            out["type"] = migrated

    raw_role = draft.get("semantic_role")
    if isinstance(raw_role, str) and raw_role.strip():
        raw = raw_role.strip()
        role, detail = normalize_semantic_role(raw, str(draft.get("semantic_detail") or "").strip())
        # ``unknown`` is the catch-all — keep it only when the model said so.
        if role in SEMANTIC_ROLES and (role != "unknown" or raw == "unknown"):
            out["semantic_role"] = role
            if detail and role != "unknown":
                out["semantic_detail"] = detail
    elif isinstance(draft.get("semantic_detail"), str) and draft["semantic_detail"].strip():
        role, detail = normalize_semantic_role(draft["semantic_detail"].strip())
        if role in SEMANTIC_ROLES and role != "unknown":
            out["semantic_role"] = role
            if detail:
                out["semantic_detail"] = detail

    if out.get("type") == "environment" and out.get("semantic_role") in CITY_LAYOUT_ROLES:
        out["type"] = "environment/city_layout"
    if any(stem.startswith(p) for p in INTERIOR_KIT_PREFIXES):
        out["type"] = "building/interior_module"
        if out.get("semantic_role") in {
            None,
            "building_module",
            "building_shell",
            "prop",
            "interior_prop",
            "street_furniture",
        }:
            out["semantic_role"] = "interior_module"

    etype = out.get("type") or (existing or {}).get("type") or ""
    migrated_type = TYPE_MIGRATION.get(etype, etype)

    mrole = draft.get("module_role")
    if mrole is None and isinstance(draft.get("module"), dict):
        mrole = draft["module"].get("role")
    if isinstance(mrole, str) and mrole in MODULE_ROLES:
        if str(migrated_type).startswith("building"):
            out["module_role"] = mrole
    elif str(migrated_type) == "building/shell":
        out["module_role"] = "hero"

    slot = filename_kit_slot(stem)
    if slot:
        role = out.get("module_role")
        etype = out.get("type")
        if role in {None, "hero", "shell"} or etype == "building/shell":
            out["module_role"] = slot
        if etype == "building/shell" and (
            slot in {"door", "stairs"} or (slot == "corner" and "apartment" in stem.lower())
        ):
            out["type"] = "building/module"
            if out.get("semantic_role") == "building_shell":
                out["semantic_role"] = "building_module"

    if any(stem.startswith(p) for p in INTERIOR_KIT_PREFIXES):
        out["type"] = "building/interior_module"
        if out.get("module_role") in {"hero", "shell"}:
            out.pop("module_role", None)

    place_in = draft.get("placement") if isinstance(draft.get("placement"), dict) else {}
    raw_mount = draft.get("mount") if isinstance(draft.get("mount"), str) else place_in.get("mount")
    existing_place = (existing or {}).get("placement")
    existing_mount = None
    if isinstance(existing_place, dict):
        existing_mount = existing_place.get("mount")
    elif existing:
        existing_mount = existing.get("mount")
    mount = adopt_mount(stem, raw_mount if isinstance(raw_mount, str) else None, existing_mount)
    kit_role = out.get("module_role")
    if mount == "module" and kit_role in KIT_GROUND_ROLES:
        mount = "ground"
    if not mount and _shop_canopy_stem(stem):
        mount = "wall"
    if not mount and kit_role in KIT_GROUND_ROLES:
        mount = "ground"
    if mount:
        out["mount"] = mount

    raw_att = draft.get("attachment") if isinstance(draft.get("attachment"), str) else place_in.get("attachment")
    att = None
    if isinstance(raw_att, str) and raw_att.strip():
        att = normalize_attachment(raw_att)
        att = VISION_ATTACHMENT_ALIASES.get(att, att)
        if att in ATTACHMENTS and att != "none":
            out["attachment"] = att
        else:
            att = None
    if not att:
        if out.get("mount") == "wall" and _shop_canopy_stem(stem):
            out["attachment"] = "back_side"
        elif out.get("mount") in {"ground", "roof"} and kit_role in KIT_GROUND_ROLES:
            out["attachment"] = "bottom"

    for key in ("orientation", "height"):
        val = draft.get(key) if draft.get(key) is not None else place_in.get(key)
        if isinstance(val, str):
            token = val.strip().lower().replace(" ", "_")
            if token and _TAG_RE.match(token) and token not in {"unknown", "none", "n/a"}:
                out[key] = token

    floors = _floors(draft.get("preferred_floors") if "preferred_floors" in draft else place_in.get("preferred_floors"))
    if floors is not None:
        out["preferred_floors"] = floors

    constraints = _token_list(draft.get("constraints") if "constraints" in draft else place_in.get("constraints"))
    if constraints:
        out["constraints"] = [c for c in constraints if c not in {"unknown", "none"}]
    contexts = _token_list(
        draft.get("preferred_contexts") if "preferred_contexts" in draft else place_in.get("preferred_contexts")
    )
    if contexts:
        out["preferred_contexts"] = [c for c in contexts if c not in {"unknown", "none"}]

    if _roof_cover_stem(stem):
        if out.get("type") not in {"building/module", "building/shell"}:
            out["type"] = "building/module"
        if out.get("semantic_role") not in {"building_module", "roof_dressing", "building_shell"}:
            out["semantic_role"] = "building_module"
        if out.get("module_role") not in MODULE_ROLES or out.get("module_role") in {"hero", "misc"}:
            out["module_role"] = "roof"
        if out.get("mount") in {None, "ground", "wall", "module"}:
            out["mount"] = "roof"
        if not out.get("attachment"):
            out["attachment"] = "bottom"
        drop = {"rock", "terrain", "block", "obstacle"}
        if out.get("tags"):
            out["tags"] = [t for t in out["tags"] if t not in drop]
        removed = list(out.get("tags_remove") or [])
        for t in drop:
            if t not in removed:
                removed.append(t)
        out["tags_remove"] = removed

    # Never leak measured or kit-mating fields even if the model echoed them.
    for banned in ("contact", "placement", "part", "sockets", "mech", "ai_notes"):
        out.pop(banned, None)
    return out


def merge_vision_entry(existing: dict | None, sanitized: dict, rel_path: str | None = None) -> dict:
    """Merge-not-replace into a threejs-v2 catalog row."""
    out = dict(existing) if existing else {}
    out["id"] = sanitized.get("id") or out.get("id")
    out["reviewed"] = True
    if rel_path:
        out["file"] = rel_path
    elif sanitized.get("file"):
        out["file"] = sanitized["file"]

    for key in ("name", "description"):
        val = sanitized.get(key)
        if val not in (None, ""):
            out[key] = val

    tags = _clean_tags(out.get("tags"), stem=str(out.get("id") or sanitized.get("id") or ""))
    for t in sanitized.get("tags") or []:
        if t not in tags:
            tags.append(t)
    removed = set(sanitized.get("tags_remove") or [])
    if removed:
        tags = [t for t in tags if t not in removed]
    if tags:
        out["tags"] = tags

    if "type" in sanitized:
        out["type"] = sanitized["type"]
    if "semantic_role" in sanitized:
        out["semantic_role"] = sanitized["semantic_role"]
    if "semantic_detail" in sanitized:
        out["semantic_detail"] = sanitized["semantic_detail"]

    if "module_role" in sanitized:
        module = dict(out["module"]) if isinstance(out.get("module"), dict) else {}
        module["role"] = sanitized["module_role"]
        out["module"] = module
        out["module_role"] = sanitized["module_role"]

    place = dict(out["placement"]) if isinstance(out.get("placement"), dict) else {}
    for key in ("mount", "attachment", "orientation", "height", "preferred_floors"):
        if key in sanitized:
            place[key] = sanitized[key]
    for key in ("constraints", "preferred_contexts"):
        if key not in sanitized:
            continue
        cur = [t for t in (place.get(key) or []) if isinstance(t, str)]
        for t in sanitized[key]:
            if t not in cur:
                cur.append(t)
        place[key] = cur
    if place:
        out["placement"] = place
    return out


def _norm_type(value: str | None) -> str:
    raw = (value or "").strip()
    return TYPE_MIGRATION.get(raw, raw)


def _skip_module_role(sanitized: dict, gold: dict) -> bool:
    """Props do not carry module_role; skip when gold allows a non-building type."""
    got_type = _norm_type(sanitized.get("type") if isinstance(sanitized.get("type"), str) else None)
    expected = gold.get("type")
    options = expected if isinstance(expected, list) else [expected]
    allows_non_building = any(
        isinstance(v, str) and not _norm_type(v).startswith("building") for v in options
    )
    return bool(allows_non_building and got_type and not got_type.startswith("building"))


def _match_expected(got: Any, expected: Any, *, kind: str) -> bool:
    if expected is None:
        return True
    values = expected if isinstance(expected, list) else [expected]
    if kind == "type":
        got_n = _norm_type(got if isinstance(got, str) else None)
        return any(_norm_type(v) == got_n for v in values if isinstance(v, str))
    if kind == "semantic_role":
        got_role, _ = normalize_semantic_role(got if isinstance(got, str) else None)
        return any(normalize_semantic_role(v)[0] == got_role for v in values if isinstance(v, str))
    if kind == "semantic_detail":
        got_s = str(got or "").strip()
        return any(got_s == str(v) for v in values)
    if kind == "mount":
        got_n = normalize_mount(got if isinstance(got, str) else None)
        return any(normalize_mount(v) == got_n for v in values if isinstance(v, str))
    if kind == "attachment":
        got_n = normalize_attachment(got if isinstance(got, str) else None)
        return any(normalize_attachment(v) == got_n for v in values if isinstance(v, str))
    if kind == "preferred_floors":
        got_l = list(got or [])
        # Gold ``[1]`` is one floors value. A list of lists is OR of acceptable values.
        # Do not reuse the generic "list means alternatives" unpack — that made
        # ``[1]`` compare as the integer 1 and fail against got ``[1]``.
        if isinstance(expected, list) and expected and all(isinstance(v, list) for v in expected):
            options = expected
        elif isinstance(expected, list):
            options = [expected]
        else:
            options = [[expected] if expected is not None else []]
        return any(isinstance(v, list) and sorted(got_l) == sorted(v) for v in options)
    got_s = got
    return any(got_s == v for v in values)


def compare_gold(sanitized: dict, gold: dict) -> list[dict]:
    """Return mismatch records for assembler fields present on the gold row."""
    mismatches: list[dict] = []
    mapping = (
        ("type", "type"),
        ("semantic_role", "semantic_role"),
        ("semantic_detail", "semantic_detail"),
        ("module_role", "module_role"),
        ("mount", "mount"),
        ("attachment", "attachment"),
        ("preferred_floors", "preferred_floors"),
    )
    for field, kind in mapping:
        if field not in gold:
            continue
        if field == "module_role" and _skip_module_role(sanitized, gold):
            continue
        got = sanitized.get(field)
        if field == "semantic_detail" and not got:
            # Role aliases (shop_canopy, park_path_tile) land in semantic_role
            # before sanitize splits them; accept either form.
            raw_role = sanitized.get("semantic_role")
            if raw_role in ROLE_ALIASES and ROLE_ALIASES[raw_role][1] == gold[field]:
                continue
            if isinstance(gold[field], list) and raw_role in gold[field]:
                continue
            got = sanitized.get("semantic_detail")
        if not _match_expected(got, gold[field], kind=kind):
            mismatches.append({"field": field, "expected": gold[field], "got": got})
    return mismatches


def resolve_stills(
    pack_id: str,
    stem: str,
    *,
    stills_root: Path | None,
    threejs_v2: Path | None,
    views: Sequence[str] = DEFAULT_VIEWS,
) -> list[Path]:
    if stills_root is not None:
        sheet = Path(stills_root) / pack_id / f"{stem}.png"
        if sheet.is_file():
            return [sheet]
    if threejs_v2 is not None:
        cached = Path(threejs_v2) / pack_id / "_review_stills" / stem
        found = [cached / f"{v}.png" for v in views if (cached / f"{v}.png").is_file()]
        if found:
            return found
    return []


def _render_missing(
    glb: Path,
    stills_dir: Path,
    views: Sequence[str],
    synty_glb_root: Path,
    *,
    timeout: int = 600,
) -> list[Path]:
    from .review import _render_stills

    return _render_stills(glb, stills_dir, views, synty_glb_root, timeout=timeout)


def vision_pack(
    pack_id: str,
    *,
    threejs_v2_root: Path | None,
    stills_root: Path | None = None,
    synty_glb_root: Path | None = None,
    catalogs_dir: Path | None = None,
    ids: Sequence[str] | None = None,
    match: str | None = None,
    limit: int | None = None,
    model: str = HOSTED_DEFAULT_MODEL,
    views: Sequence[str] = DEFAULT_VIEWS,
    apply: bool = True,
    force: bool = False,
    calibrate: bool = False,
    gold_path: Path | None = None,
    render_fn: Callable[..., list[Path]] | None = None,
    query_fn: Callable[[list[Path], str], dict | None] | None = None,
    vlm_timeout: int = 180,
    log: Callable[[str], None] | None = None,
) -> dict:
    """Vision-label assets in ``pack_id``. Calibrate mode never writes."""
    log = log or _default_log
    stills_root = Path(stills_root) if stills_root else default_stills_root()
    threejs = Path(threejs_v2_root) if threejs_v2_root else None
    query = query_fn or (
        lambda images, prompt: query_hosted_vlm(images, prompt, model=model, timeout=vlm_timeout)
    )

    gold_doc = load_gold(gold_path) if calibrate else None
    gold_by_id: dict[str, dict] = {}
    if gold_doc:
        for row in gold_doc.get("assets") or []:
            if isinstance(row, dict) and row.get("id"):
                gold_by_id[row["id"]] = row
        pack_id = gold_doc.get("pack_id") or pack_id
        if not ids:
            ids = list(gold_by_id)

    pack_dir = threejs / pack_id if threejs else None
    manifest = _load_json(pack_dir / MANIFEST_NAME) if pack_dir else None
    stems = _stem_index(manifest.get("models") or []) if manifest else {}
    catalog_file = pack_dir / CATALOG_NAME if pack_dir else None
    doc = (_load_json(catalog_file) if catalog_file else None) or _scaffold_catalog(pack_id)
    doc.setdefault("assets", [])
    by_id = {a["id"]: a for a in doc["assets"] if isinstance(a, dict) and a.get("id")}

    if ids:
        candidates = list(ids)
    else:
        candidates = sorted(stems) if stems else sorted(by_id)
        if match:
            needle = match.lower()
            candidates = [s for s in candidates if needle in s.lower()]

    if not query_fn and not vlm_available():
        return {
            "ok": False,
            "pack_id": pack_id,
            "error": "no XAI_API_KEY / OPENAI_API_KEY / SYNTI_VLM_API_KEY",
        }

    reviewed_ids: list[str] = []
    skipped_bundle: list[str] = []
    skipped_reviewed: list[str] = []
    failed: list[dict] = []
    gold_passed: list[str] = []
    gold_failed: list[dict] = []

    apply_writes = apply and not calibrate and catalog_file is not None

    for stem in candidates:
        if stem.lower() in BUNDLE_STEMS:
            skipped_bundle.append(stem)
            continue
        existing = by_id.get(stem)
        if existing and existing.get("reviewed") and not force and not calibrate:
            skipped_reviewed.append(stem)
            continue
        if limit is not None and len(reviewed_ids) >= limit:
            break

        rel_path = stems.get(stem)
        images = resolve_stills(pack_id, stem, stills_root=stills_root, threejs_v2=threejs, views=views)
        if not images and render_fn and pack_dir and rel_path:
            glb = pack_dir / rel_path
            if glb.is_file():
                stills_dir = pack_dir / "_review_stills" / stem
                try:
                    images = render_fn(glb, stills_dir, views, synty_glb_root)
                except (RenderError, subprocess.SubprocessError, OSError, TimeoutError) as exc:
                    failed.append({"id": stem, "error": f"render: {exc}"})
                    continue
        elif not images and synty_glb_root and pack_dir and rel_path:
            glb = pack_dir / rel_path
            if glb.is_file():
                try:
                    images = _render_missing(glb, pack_dir / "_review_stills" / stem, views, Path(synty_glb_root))
                except (RenderError, subprocess.SubprocessError, OSError, TimeoutError) as exc:
                    failed.append({"id": stem, "error": f"render: {exc}"})
                    continue
        if not images:
            failed.append({"id": stem, "error": "no stills"})
            continue

        prompt = build_prompt(stem, contact_sheet=len(images) == 1)
        draft = query(images, prompt)
        if not draft:
            failed.append({"id": stem, "error": "vlm: no usable JSON reply"})
            log(f"vision: no JSON for {stem}")
            continue

        query_existing = existing
        if catalogs_dir and query_existing is None:
            packed = _load_json(Path(catalogs_dir) / f"{pack_id}.json")
            if packed:
                query_existing = next(
                    (a for a in packed.get("assets") or [] if isinstance(a, dict) and a.get("id") == stem),
                    None,
                )
        sanitized = sanitize_draft(stem, draft, query_existing)
        reviewed_ids.append(stem)

        if calibrate and stem in gold_by_id:
            mismatches = compare_gold(sanitized, gold_by_id[stem])
            if mismatches:
                gold_failed.append({"id": stem, "mismatches": mismatches, "got": sanitized})
                log(f"vision: GOLD FAIL {stem} {mismatches}")
            else:
                gold_passed.append(stem)
                log(f"vision: GOLD PASS {stem}")

        if apply_writes:
            by_id[stem] = merge_vision_entry(existing, sanitized, rel_path)
            doc["assets"] = list(by_id.values())
            _write_catalog(catalog_file, doc)
            log(f"vision: {stem} -> {sanitized.get('name')!r}")

    ok = not failed and (not calibrate or not gold_failed)
    result = {
        "ok": ok,
        "pack_id": pack_id,
        "catalog": str(catalog_file) if catalog_file else None,
        "model": model,
        "apply": apply_writes,
        "calibrate": calibrate,
        "reviewed": reviewed_ids,
        "skipped_already_reviewed": len(skipped_reviewed),
        "skipped_bundle": skipped_bundle,
        "failed": failed,
        "candidates": len(candidates),
    }
    if calibrate:
        result["gold_passed"] = gold_passed
        result["gold_failed"] = gold_failed
        result["gold_total"] = len(gold_by_id)
    return result
