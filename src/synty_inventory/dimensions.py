"""Pull measured AABBs from asset-viewer pack profiles when present."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=16)
def load_viewer_pack(path: str) -> dict:
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def measured_size(viewer_data_dir: Path | None, pack_id: str, asset_id: str) -> dict | None:
    if viewer_data_dir is None:
        return None
    doc = load_viewer_pack(str(viewer_data_dir / "packs" / f"{pack_id}.json"))
    piece = (doc.get("pieces") or {}).get(asset_id)
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
