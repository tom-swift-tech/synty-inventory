"""Per-GLB uniform scale corrections (``data/glb_scale_overrides.json``).

A handful of threejs-v2 GLBs were converted at the wrong unit (the SciFi
Space asteroids, planets and capital ships are exactly 100x too small). The
measurer is right about the file it reads; the file is wrong, and it is not
ours to re-convert. So the correction is data: a factor resolved once per
asset into ``files.glb_scale`` and applied by every geometry reader
(bounds, footprint, prop contact, part sockets) to the decoded mesh, so all
derived fields agree in true metres. The factor is folded into each cache id
so a table change never serves a stale unscaled entry.
"""

from __future__ import annotations

import fnmatch
import json
from functools import lru_cache
from pathlib import Path, PurePosixPath

_TABLE_PATH = Path(__file__).resolve().parent.parent / "data" / "glb_scale_overrides.json"


@lru_cache(maxsize=1)
def load_table() -> dict[str, list[tuple[str, float]]]:
    """pack_id -> [(glob over GLB stem, factor)] in file order."""
    raw = json.loads(_TABLE_PATH.read_text(encoding="utf-8"))
    table: dict[str, list[tuple[str, float]]] = {}
    for pack_id, entries in raw.items():
        if pack_id.startswith("_") or not isinstance(entries, dict):
            continue
        table[pack_id] = [(g, float(f)) for g, f in entries.items() if not g.startswith("_")]
    return table


def glb_scale_for(pack_id: str, glb_rel: str | None) -> float:
    """Correction factor for ``glb_rel`` in ``pack_id``; 1.0 when none applies."""
    if not glb_rel:
        return 1.0
    stem = PurePosixPath(glb_rel).stem
    for pattern, factor in load_table().get(pack_id, []):
        if fnmatch.fnmatchcase(stem, pattern):
            return factor
    return 1.0


def apply_glb_scale(asset: dict, pack_id: str) -> None:
    """Record the correction for the asset's current ``files.glb`` (or drop a
    stale one). Runs after every step that can (re)wire ``files.glb``."""
    files = asset.get("files")
    if not isinstance(files, dict):
        return
    factor = glb_scale_for(pack_id, files.get("glb"))
    if factor != 1.0:
        files["glb_scale"] = factor
    else:
        files.pop("glb_scale", None)


def asset_glb_scale(asset: dict) -> float:
    return float((asset.get("files") or {}).get("glb_scale") or 1.0)


def scale_cache_tag(scale: float) -> str:
    """Cache-id suffix: empty at 1.0 so every existing entry keeps its key."""
    return "" if scale == 1.0 else f"#s{scale:g}"
