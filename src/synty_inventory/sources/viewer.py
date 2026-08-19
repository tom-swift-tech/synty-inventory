"""Pull measured AABBs, signs, props, and module role/family from the
asset-viewer's generated per-pack profiles (``<viewer_data>/packs/*.json``,
``signs/*.json``, ``props/*.json``, ``types/*.json``).

This is the pre-Phase-2 data source (rank ``viewer``). It ships pre-computed
``aabb`` per piece — that is a measurement, so bounds derived from it are
stamped ``bounds.source == "measured"`` even though the *field* provenance
for module/tags overlay below is ``"viewer"``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..merge import may_overlay
from ..schema import MODULE_ROLES, empty_module

# asset-viewer role token -> schema.MODULE_ROLES. Everything else (misc,
# prop, dress, planter, road, sidewalk, vehicle, cable, apron, ...) is scene
# dressing, not a building-kit module role, and is ignored here.
VIEWER_ROLE_MAP = {
    "hero": "hero",
    "shell": "shell",
    "annex": "annex",
    "roof": "roof",
    "wall": "wall",
    "floor": "floor",
    "door": "door",
    "stair": "stairs",
    "ceiling": "ceiling",
    "pad": "pad",
    "opening": "opening",
    "pillar": "pillar",
    "window": "window",
    "backdrop": "backdrop",
    "cover": "cover",
    "spire": "spire",
    "base": "base",
    "corner": "corner",
}
assert set(VIEWER_ROLE_MAP.values()) <= set(MODULE_ROLES)

VIEWER_FAMILY_IGNORE = {"misc", "prop"}


@lru_cache(maxsize=16)
def load_viewer_pack(path: str) -> dict:
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load_viewer_pieces(viewer_data_dir: Path | None, pack_id: str) -> dict:
    """id -> viewer piece dict (``aabb``, ``size``, ``roles``, ``family``, ``mount``, ``tags``)."""
    if viewer_data_dir is None:
        return {}
    doc = load_viewer_pack(str(viewer_data_dir / "packs" / f"{pack_id}.json"))
    return doc.get("pieces") or {}


def measured_size(viewer_data_dir: Path | None, pack_id: str, asset_id: str) -> dict | None:
    if viewer_data_dir is None:
        return None
    piece = load_viewer_pieces(viewer_data_dir, pack_id).get(asset_id)
    if not piece:
        return None
    size = piece.get("size")
    if not (isinstance(size, list) and len(size) == 3):
        return None
    return {
        "approx": [round(float(size[0]), 4), round(float(size[1]), 4), round(float(size[2]), 4)],
        "units": "meters",
        "source": "measured",
        "aabb": piece.get("aabb"),
        "mount_hint": piece.get("mount"),
    }


def load_viewer_signs(viewer_data_dir: Path | None, pack_id: str) -> dict:
    if viewer_data_dir is None:
        return {}
    path = viewer_data_dir / "signs" / f"{pack_id}.json"
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return doc.get("signs") or {}


def load_viewer_props(viewer_data_dir: Path | None, pack_id: str) -> dict:
    if viewer_data_dir is None:
        return {}
    path = viewer_data_dir / "props" / f"{pack_id}.json"
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return doc.get("props") or {}


def load_type_sign_usage(viewer_data_dir: Path | None, pack_id: str) -> dict[str, list[str]]:
    """Map asset id → building type ids that reference it as neon/ad/banner/hero."""
    if viewer_data_dir is None:
        return {}
    path = viewer_data_dir / "types" / f"{pack_id}.json"
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    usage: dict[str, list[str]] = {}
    for t in doc.get("types") or []:
        tid = t.get("id")
        if not tid:
            continue
        ids: list[str] = []
        for hero in t.get("heroes") or []:
            ids.extend(hero.get("ids") or [])
        facade = t.get("facade") or {}
        for key in ("neon", "ads", "banners"):
            ids.extend(facade.get(key) or [])
        for hid in ids:
            usage.setdefault(hid, []).append(tid)
    return usage


def apply_viewer_module(asset: dict, piece: dict | None) -> dict:
    """Overlay ``module.role`` / ``module.family`` and union viewer tags.

    Provenance for ``module`` is stamped ``"viewer"`` only when this piece
    actually contributed a role or family (an asset with no viewer profile,
    or only ignored roles/family, keeps whatever rules already produced).
    """
    if not piece:
        return asset
    module = asset.setdefault("module", empty_module())
    role = None
    for r in piece.get("roles") or []:
        mapped = VIEWER_ROLE_MAP.get((r or "").strip().lower())
        if mapped:
            role = mapped
            break
    family = (piece.get("family") or "").strip().lower()
    use_family = family and family not in VIEWER_FAMILY_IGNORE
    if (role or use_family) and may_overlay(asset, "module", "viewer"):
        if role:
            module["role"] = role
        if use_family:
            module["family"] = family
        asset.setdefault("provenance", {})["module"] = "viewer"
    tags = asset.setdefault("tags", [])
    for t in piece.get("tags") or []:
        if t and t not in tags:
            tags.append(t)
    return asset
