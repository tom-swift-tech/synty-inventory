"""Catalog schema v2 — one engine-neutral record per asset.

v2 keeps every v1 field (agents and the skill already read them) and adds the
assembly layer: ``placeable``, ``kind``, ``bounds`` (origin-relative AABB, never a
fake number), ``module`` (building kit role/family), ``part`` (vehicle/ship kit
class), ``files`` (per-engine file paths) and ``semantic_detail``.

Vocabularies that an agent filters on are enums here. ``constraints`` and
``preferred_contexts`` stay open snake_case token lists — they are descriptive,
not a join key, and the asset-viewer vocabulary (``city-layout``, ``loose-roof``)
is folded in rather than re-invented.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

CATALOG_VERSION = 2
SUPPORTED_VERSIONS = (1, 2)

# --- catalog-level -----------------------------------------------------------

DEFAULT_GRID = {"snap": 0.25, "module": 2.5, "tile": 5.0, "story": 3.0}
DEFAULT_CONVENTIONS = {"street_axis": "+z", "rotate_deg": 90, "scale": 1, "up_axis": "+y"}

REQUIRED_CATALOG = (
    "pack_id",
    "engine",
    "origin",
    "style",
    "units",
    "version",
    "scanned_at",
    "grid",
    "conventions",
    "assets",
)

# --- asset-level ---------------------------------------------------------------

REQUIRED_ASSET = (
    "id",
    "name",
    "kind",
    "placeable",
    "type",
    "category",
    "tags",
    "description",
    "semantic_role",
    "semantic_detail",
    "placement",
    "bounds",
    "dimensions",
    "files",
    "paths",
    "thumbnail",
    "ai_notes",
)
REQUIRED_PLACEMENT = (
    "mount",
    "height",
    "orientation",
    "attachment",
    "preferred_floors",
    "constraints",
    "preferred_contexts",
)
# Fields that enrichment owns and humans may lock. merge.py preserves these.
SEMANTIC_FIELDS = (
    "name",
    "type",
    "category",
    "tags",
    "description",
    "semantic_role",
    "semantic_detail",
    "placement",
    "module",
    "part",
    "ai_notes",
)

KINDS = (
    "prefab",
    "mesh",
    "animation",
    "ui",
    "skeleton",
    "fx",
    "material",
    "texture",
    "audio",
    "other",
)

TYPES = (
    "building/shell",
    "building/module",
    "building/interior_module",
    "prop",
    "prop/signage",
    "vehicle",
    "vehicle/part",
    "vehicle/spacecraft",
    "character",
    "character/part",
    "character/skeleton",
    "environment",
    "environment/city_layout",
    "fx",
    "ui",
    "ui/icon",
    "animation",
    "weapon",
    "skybox",
)
# v1 → v2 type renames
TYPE_MIGRATION = {"building/modular": "building/module"}

# Types that are scene-placeable by default. Everything else is data (clips,
# icons, skeleton parts, skyboxes) unless a source says otherwise.
PLACEABLE_TYPES = {
    "building/shell",
    "building/module",
    "building/interior_module",
    "prop",
    "prop/signage",
    "vehicle",
    "vehicle/part",
    "vehicle/spacecraft",
    "character",
    "environment",
    "environment/city_layout",
    "weapon",
    "fx",
}

SEMANTIC_ROLES = (
    "building_shell",  # a whole hero building
    "building_module",  # stackable exterior kit piece (floor/roof/corner…)
    "interior_module",  # corridor / bridge / room kit piece
    "building_identity",  # sign that says what the building is
    "advertisement",
    "traffic_control",
    "wayfinding",
    "mounting_hardware",
    "facade_dressing",
    "roof_dressing",
    "street_furniture",
    "ground_surface",
    "road_surface",
    "foliage",
    "vehicle",
    "vehicle_part",
    "spacecraft",
    "character",
    "character_part",
    "weapon",
    "visual_effect",
    "ui_element",
    "animation_clip",
    "skybox",
    "interior_prop",
    "exterior_prop",
    "debris",
    "celestial",
    "container",
    "unknown",
)

MOUNTS = (
    "ground",
    "wall",
    "roof",
    "ceiling",
    "pole",
    "pole_or_wall",
    "module",  # snaps to a kit grid / neighbour module
    "socket",  # mates to a parent part (ship kits)
    "none",
    "free",
)
MOUNT_ALIASES = {"facade": "wall", "n/a": "none", "": "none"}

ATTACHMENTS = (
    "base_to_ground",
    "back_side",
    "side_bracket",
    "base_to_roof",
    "back_or_pole",
    "bottom",
    "origin",
    "socket",
    "none",
)
ATTACHMENT_ALIASES = {"": "none", "n/a": "none"}

MODULE_ROLES = (
    "base",
    "floor",
    "roof",
    "corner",
    "door",
    "stairs",
    "wall",
    "ceiling",
    "floor_tile",
    "bridge",
    "corridor",
    "hero",
    "annex",
    "backdrop",
    "pad",
    "opening",
    "pillar",
    "window",
    "shell",
    "cover",
    "spire",
    "misc",
)
PART_CLASSES = (
    "body",
    "cockpit",
    "engine",
    "wing",
    "landing_gear",
    "greeble",
    "turret",
    "armor",
    "weapon_mount",
    "misc",
)
SIZE_CLASSES = ("fighter", "bomber", "transport", "cruiser", "capital", "station")
PIVOTS = ("corner", "center_bottom", "center", "other", "unknown")
BOUNDS_SOURCES = ("measured", "vlm", "rules")
PROVENANCES = ("rules", "viewer", "vlm", "vlm_reviewed", "measured", "curated", "human")

FILE_KEYS = ("unity_prefab", "unity_mesh", "unity_materials", "glb", "unreal_uasset", "godot_scene")

_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9_\-+.]*$")


# --- factories -------------------------------------------------------------------


def empty_placement() -> dict[str, Any]:
    return {
        "mount": "ground",
        "height": "grade",
        "orientation": "upright",
        "attachment": "base_to_ground",
        "preferred_floors": [1],
        "constraints": [],
        "preferred_contexts": [],
    }


def empty_files() -> dict[str, Any]:
    return {
        "unity_prefab": None,
        "unity_mesh": None,
        "unity_materials": [],
        "glb": None,
        "unreal_uasset": None,
        "godot_scene": None,
    }


def empty_paths() -> dict[str, Any]:
    """v1 alias view of ``files`` (kept one release for the skill)."""
    return {"prefab": None, "mesh": None, "materials": []}


def paths_from_files(files: dict) -> dict:
    return {
        "prefab": files.get("unity_prefab"),
        "mesh": files.get("unity_mesh"),
        "materials": list(files.get("unity_materials") or []),
    }


def files_from_paths(paths: dict | None) -> dict:
    files = empty_files()
    if paths:
        files["unity_prefab"] = paths.get("prefab")
        files["unity_mesh"] = paths.get("mesh")
        files["unity_materials"] = list(paths.get("materials") or [])
    return files


def empty_module() -> dict[str, Any]:
    return {
        "family": None,
        "role": None,
        "footprint_class": None,
        "stackable_on": [],
        "street_side": None,
        "blank_sides": [],
        "sign_zones": [],
    }


def empty_part() -> dict[str, Any]:
    return {"class": None, "mates_axis": None, "symmetric": None, "size_class": None}


def make_bounds(
    size: list[float],
    *,
    source: str,
    min_: list[float] | None = None,
    max_: list[float] | None = None,
    pivot: str = "unknown",
) -> dict[str, Any]:
    return {
        "min": [round(float(v), 4) for v in min_] if min_ else None,
        "max": [round(float(v), 4) for v in max_] if max_ else None,
        "size": [round(float(v), 4) for v in size],
        "pivot": pivot if pivot in PIVOTS else "unknown",
        "source": source,
    }


def dimensions_from_bounds(bounds: dict | None) -> dict[str, Any]:
    """v1 ``dimensions`` mirror. ``approx`` is null when bounds are unknown."""
    if not bounds or not bounds.get("size"):
        return {"approx": None, "units": "meters", "source": "none"}
    return {"approx": list(bounds["size"]), "units": "meters", "source": bounds.get("source", "measured")}


def pivot_from_aabb(min_: list[float], max_: list[float]) -> str:
    """Classify where the origin sits relative to the AABB (Synty kits are
    mostly corner- or centre-bottom-pivoted; this is what a placer needs)."""
    try:
        sx = max_[0] - min_[0]
        sz = max_[2] - min_[2]
    except (TypeError, IndexError):
        return "unknown"
    tol_y = 0.05
    bottom = abs(min_[1]) <= tol_y
    cx = (min_[0] + max_[0]) / 2
    cz = (min_[2] + max_[2]) / 2
    centred_xz = abs(cx) <= max(0.05, 0.05 * sx) and abs(cz) <= max(0.05, 0.05 * sz)
    # Corner pivots tolerate small overhangs (awnings, trims) up to one snap
    # step or 5 % of the extent — Synty shells often poke 0.1–0.2 m past origin.
    tx = max(0.25, 0.05 * sx)
    tz = max(0.25, 0.05 * sz)
    at_corner = (abs(min_[0]) <= tx or abs(max_[0]) <= tx) and (
        abs(min_[2]) <= tz or abs(max_[2]) <= tz
    )
    if bottom and centred_xz:
        return "center_bottom"
    if bottom and at_corner:
        return "corner"
    cy = (min_[1] + max_[1]) / 2
    if centred_xz and abs(cy) <= max(0.05, 0.05 * (max_[1] - min_[1])):
        return "center"
    return "other"


def default_placeable(asset_type: str, kind: str) -> bool:
    if kind in {"animation", "ui", "skeleton", "material", "texture", "audio"}:
        return False
    return asset_type in PLACEABLE_TYPES


def kind_for_type(asset_type: str, has_prefab: bool) -> str:
    if asset_type == "animation":
        return "animation"
    if asset_type in {"ui", "ui/icon"}:
        return "ui"
    if asset_type == "character/skeleton":
        return "skeleton"
    if asset_type == "fx":
        return "fx"
    if asset_type == "skybox":
        return "material"
    return "prefab" if has_prefab else "mesh"


# --- v1 → v2 migration ---------------------------------------------------------------

# Free-form v1 semantic_role strings → (enum, detail). Patterns checked in order.
_ROLE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^identifies_building_as_(.+)$"), "building_identity"),
    (re.compile(r"^identifies_or_decorates_facade$"), "facade_dressing"),
    (re.compile(r"^displays_(.+)$"), "advertisement"),
    (re.compile(r"^advertises"), "advertisement"),
    (re.compile(r"^regulates_traffic$"), "traffic_control"),
    (re.compile(r"^marks_bus_stop$"), "wayfinding"),
    (re.compile(r"^nighttime_facade_identity$"), "building_identity"),
    (re.compile(r"^mounting_hardware"), "mounting_hardware"),
    (re.compile(r"^forms_(.+)_shell$"), "building_shell"),
    (re.compile(r"^forms_building_volume$"), "building_module"),
    (re.compile(r"^(apartment|office|shop|residential|.*)_floor_module$"), "building_module"),
    (re.compile(r"^(shop|residential|office|civic|.*)_building$"), "building_shell"),
    (re.compile(r"^forms_drivable_surface$"), "road_surface"),
    (re.compile(r"^forms_pedestrian_surface$"), "ground_surface"),
    (re.compile(r"^dresses_exterior_ground$"), "ground_surface"),
    (re.compile(r"^populates_street_or_lot$"), "vehicle"),
    (re.compile(r"^populates_scene_as_person$"), "character"),
    (re.compile(r"^visual_effect$"), "visual_effect"),
    (re.compile(r"^dresses_scene$"), "exterior_prop"),
]


def normalize_semantic_role(role: str | None, detail: str | None = None) -> tuple[str, str]:
    """Map any role string onto (enum, detail). Enum values pass through."""
    role = (role or "").strip()
    if role in SEMANTIC_ROLES:
        return role, detail or ""
    for pat, enum in _ROLE_PATTERNS:
        m = pat.match(role)
        if m:
            d = detail or (m.group(1) if m.groups() else role)
            return enum, d
    return "unknown", detail or role


def normalize_mount(value: str | None) -> str:
    v = (value or "").strip().lower()
    v = MOUNT_ALIASES.get(v, v)
    return v if v in MOUNTS else "none"


def normalize_attachment(value: str | None) -> str:
    v = (value or "").strip().lower()
    v = ATTACHMENT_ALIASES.get(v, v)
    return v if v in ATTACHMENTS else "none"


def migrate_asset_v1(asset: dict) -> dict:
    """In-place-safe v1 → v2 upgrade of one asset record."""
    a = deepcopy(asset)
    a["type"] = TYPE_MIGRATION.get(a.get("type") or "prop", a.get("type") or "prop")
    if a["type"] not in TYPES:
        a["type"] = "prop"
    paths = a.get("paths") or {}
    files = a.get("files") or files_from_paths(paths)
    for k in FILE_KEYS:
        files.setdefault(k, [] if k == "unity_materials" else None)
    a["files"] = files
    a["paths"] = paths_from_files(files)
    a.setdefault("kind", kind_for_type(a["type"], bool(files.get("unity_prefab"))))
    a.setdefault("placeable", default_placeable(a["type"], a["kind"]))
    role, detail = normalize_semantic_role(a.get("semantic_role"), a.get("semantic_detail"))
    a["semantic_role"], a["semantic_detail"] = role, detail
    place = a.get("placement") or empty_placement()
    place["mount"] = normalize_mount(place.get("mount"))
    place["attachment"] = normalize_attachment(place.get("attachment"))
    for k, default in (
        ("height", "grade"),
        ("orientation", "upright"),
        ("preferred_floors", []),
        ("constraints", []),
        ("preferred_contexts", []),
    ):
        place.setdefault(k, deepcopy(default))
    a["placement"] = place
    if "bounds" not in a:
        dims = a.get("dimensions") or {}
        approx = dims.get("approx")
        src = dims.get("source")
        if src == "measured" and isinstance(approx, list) and len(approx) == 3:
            a["bounds"] = make_bounds(approx, source="measured")
        else:
            # heuristic numbers are not bounds — never carry a fake size forward
            a["bounds"] = None
    a["dimensions"] = dimensions_from_bounds(a.get("bounds"))
    a.setdefault("module", empty_module())
    a.setdefault("part", empty_part())
    a.setdefault("thumbnail", None)
    a.setdefault("ai_notes", "")
    a.setdefault("category", [])
    a.setdefault("tags", [])
    a.setdefault("description", "")
    return a


def migrate_catalog(doc: dict) -> dict:
    """Upgrade a v1 catalog document to v2. v2 documents pass through."""
    if doc.get("version") == CATALOG_VERSION:
        return doc
    out = dict(doc)
    out["version"] = CATALOG_VERSION
    out.setdefault("grid", deepcopy(DEFAULT_GRID))
    out.setdefault("conventions", deepcopy(DEFAULT_CONVENTIONS))
    out["assets"] = [migrate_asset_v1(a) for a in doc.get("assets") or [] if isinstance(a, dict)]
    out["asset_count"] = len(out["assets"])
    return out


# --- validation -----------------------------------------------------------------------


def _is_vec3(v: Any) -> bool:
    return isinstance(v, list) and len(v) == 3 and all(isinstance(n, (int, float)) for n in v)


def _check_tokens(values: Any, where: str, errors: list[str]) -> None:
    if not isinstance(values, list):
        errors.append(f"{where} must be a list")
        return
    for t in values:
        if not isinstance(t, str) or not _TOKEN_RE.match(t):
            errors.append(f"{where} token {t!r} is not snake_case")


def validate_bounds(bounds: Any, prefix: str, errors: list[str]) -> None:
    if bounds is None:
        return
    if not isinstance(bounds, dict):
        errors.append(f"{prefix}.bounds must be an object or null")
        return
    if not _is_vec3(bounds.get("size")):
        errors.append(f"{prefix}.bounds.size must be [x,y,z]")
    for key in ("min", "max"):
        if bounds.get(key) is not None and not _is_vec3(bounds.get(key)):
            errors.append(f"{prefix}.bounds.{key} must be [x,y,z] or null")
    if bounds.get("pivot") not in PIVOTS:
        errors.append(f"{prefix}.bounds.pivot invalid: {bounds.get('pivot')!r}")
    if bounds.get("source") not in BOUNDS_SOURCES:
        errors.append(f"{prefix}.bounds.source invalid: {bounds.get('source')!r}")


def validate_asset(asset: Any, prefix: str, errors: list[str]) -> None:
    if not isinstance(asset, dict):
        errors.append(f"{prefix} is not an object")
        return
    for key in REQUIRED_ASSET:
        if key not in asset:
            errors.append(f"{prefix} missing {key}")
    if asset.get("kind") not in KINDS:
        errors.append(f"{prefix}.kind invalid: {asset.get('kind')!r}")
    if not isinstance(asset.get("placeable"), bool):
        errors.append(f"{prefix}.placeable must be bool")
    if asset.get("type") not in TYPES:
        errors.append(f"{prefix}.type invalid: {asset.get('type')!r}")
    if asset.get("semantic_role") not in SEMANTIC_ROLES:
        errors.append(f"{prefix}.semantic_role invalid: {asset.get('semantic_role')!r}")
    if not isinstance(asset.get("semantic_detail", ""), str):
        errors.append(f"{prefix}.semantic_detail must be a string")
    _check_tokens(asset.get("tags", []), f"{prefix}.tags", errors)
    _check_tokens(asset.get("category", []), f"{prefix}.category", errors)
    place = asset.get("placement")
    if isinstance(place, dict):
        for key in REQUIRED_PLACEMENT:
            if key not in place:
                errors.append(f"{prefix}.placement missing {key}")
        if place.get("mount") not in MOUNTS:
            errors.append(f"{prefix}.placement.mount invalid: {place.get('mount')!r}")
        if place.get("attachment") not in ATTACHMENTS:
            errors.append(f"{prefix}.placement.attachment invalid: {place.get('attachment')!r}")
        _check_tokens(place.get("constraints", []), f"{prefix}.placement.constraints", errors)
        _check_tokens(place.get("preferred_contexts", []), f"{prefix}.placement.preferred_contexts", errors)
    else:
        errors.append(f"{prefix}.placement must be an object")
    validate_bounds(asset.get("bounds"), prefix, errors)
    dims = asset.get("dimensions")
    if not isinstance(dims, dict) or "approx" not in dims or "units" not in dims:
        errors.append(f"{prefix}.dimensions must have approx + units")
    elif dims.get("approx") is not None and not _is_vec3(dims.get("approx")):
        errors.append(f"{prefix}.dimensions.approx must be [x,y,z] or null")
    elif asset.get("bounds") is None and dims.get("approx") is not None:
        errors.append(f"{prefix}.dimensions.approx set without bounds (fake size)")
    module = asset.get("module")
    if isinstance(module, dict):
        if module.get("role") is not None and module["role"] not in MODULE_ROLES:
            errors.append(f"{prefix}.module.role invalid: {module['role']!r}")
    elif module is not None:
        errors.append(f"{prefix}.module must be an object or null")
    part = asset.get("part")
    if isinstance(part, dict):
        if part.get("class") is not None and part["class"] not in PART_CLASSES:
            errors.append(f"{prefix}.part.class invalid: {part['class']!r}")
        if part.get("size_class") is not None and part["size_class"] not in SIZE_CLASSES:
            errors.append(f"{prefix}.part.size_class invalid: {part['size_class']!r}")
    elif part is not None:
        errors.append(f"{prefix}.part must be an object or null")
    files = asset.get("files")
    if not isinstance(files, dict):
        errors.append(f"{prefix}.files must be an object")
    else:
        for key in FILE_KEYS:
            if key not in files:
                errors.append(f"{prefix}.files missing {key}")
    paths = asset.get("paths")
    if not isinstance(paths, dict):
        errors.append(f"{prefix}.paths must be an object")
    else:
        for key in ("prefab", "mesh", "materials"):
            if key not in paths:
                errors.append(f"{prefix}.paths missing {key}")
    prov = asset.get("provenance") or {}
    for field, value in prov.items():
        if value not in PROVENANCES:
            errors.append(f"{prefix}.provenance.{field} invalid: {value!r}")


def validate_catalog(doc: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["catalog is not an object"]
    for key in REQUIRED_CATALOG:
        if key not in doc:
            errors.append(f"missing catalog.{key}")
    if doc.get("units") != "meters":
        errors.append("units must be 'meters'")
    if doc.get("version") != CATALOG_VERSION:
        errors.append(f"version must be {CATALOG_VERSION}")
    grid = doc.get("grid")
    if isinstance(grid, dict):
        for key in ("snap", "module", "tile", "story"):
            if not isinstance(grid.get(key), (int, float)):
                errors.append(f"grid.{key} must be a number")
    assets = doc.get("assets")
    if not isinstance(assets, list):
        errors.append("assets must be a list")
        return errors
    seen: set[str] = set()
    for i, asset in enumerate(assets):
        prefix = f"assets[{i}]"
        validate_asset(asset, prefix, errors)
        aid = asset.get("id") if isinstance(asset, dict) else None
        if isinstance(aid, str):
            if aid in seen:
                errors.append(f"duplicate asset id {aid}")
            seen.add(aid)
    return errors
