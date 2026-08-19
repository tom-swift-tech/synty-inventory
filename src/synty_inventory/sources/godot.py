"""Godot pack tree discovery + per-asset ``.tscn`` scene resolution.

Godot export trees ship parallel to (not derived from) the Unity/GLB
sources this tool already reads: one folder per pack under ``godot_root``,
laid out like a Godot project (``Assets/Synty/<KitName>/Prefabs/**/*.tscn``
for pack-scale kits such as PolygonCity; ``Assets/<Name>/Prefabs/**/*.tscn``
for standalone drops such as particle-fx). Scene stems are the same
``SM_``/``FX_``/... ids used everywhere else in the catalog, so resolution
is a straight stem match — no GUID/hash to reconcile against Unity.

Mirrors ``sources/threejs_v2.py``'s ``glb_index`` / ``apply_threejs_overlay``
shape: an index built once per pack, an overlay applied once per asset,
``files.godot_scene`` wired with no provenance stamp (paths are scanner-
owned data, not a semantic judgement call — see ``merge.SCANNER_OWNED``).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ..paths import rel_posix

# slug (folder name directly under godot_root) -> pack_id. Explicit, not a
# normalization guess: the Godot export slug carries a drop-revision suffix
# ("-01") and drops "Polygon" from City's folder name, neither of which a
# generic normalizer could safely reverse for the packs that don't exist on
# disk yet (guessing wrong would silently misfile a whole pack's scenes).
SLUG_PACK_OVERRIDES: dict[str, str] = {
    "particle-fx": "POLYGON_Particle_FX",
    "polygon-city-01": "POLYGON_City",
    "polygon-starter": "POLYGON_Starter",
}

# Scenes every Godot export ships (top-level demo/showcase levels), never a
# stem a catalog asset id would match — excluded so they can't accidentally
# satisfy a match.
_DEMO_SCENE_STEMS = {"demo", "overview"}


def _normalize_slug(name: str) -> str:
    """Fallback slug -> pack_id guess for a folder with no override entry:
    strip a trailing drop-revision suffix ("-01"), title-case each hyphen
    segment, join with "_". ``"polygon-scifi-city-02"`` -> ``"Polygon_Scifi_City"``
    — close to, but not guaranteed to equal, a real ``POLYGON_SciFi_City`` id
    (multi-word compounds like "SciFi"/"PostApoc" don't round-trip through
    title-case). Good enough to surface an unmapped tree for discovery
    rather than dropping it silently; add an explicit
    ``SLUG_PACK_OVERRIDES`` entry once the real pack_id is confirmed."""
    import re

    stem = re.sub(r"-\d+$", "", name.strip().lower())
    words = [w for w in re.split(r"[^a-z0-9]+", stem) if w]
    return "_".join(w.capitalize() for w in words) if words else name


def discover_pack_dirs(godot_root: Path | None) -> dict[str, Path]:
    """pack_id -> pack tree root, for every subdirectory of ``godot_root``.
    ``SLUG_PACK_OVERRIDES`` wins when the slug is known; otherwise falls
    back to ``_normalize_slug`` so a new drop still shows up (under a
    best-guess id) instead of vanishing until the override map is updated."""
    if godot_root is None or not Path(godot_root).is_dir():
        return {}
    out: dict[str, Path] = {}
    for child in sorted(Path(godot_root).iterdir()):
        if not child.is_dir():
            continue
        pack_id = SLUG_PACK_OVERRIDES.get(child.name) or _normalize_slug(child.name)
        out[pack_id] = child
    return out


@lru_cache(maxsize=16)
def _scan_tscn(pack_root_str: str) -> tuple[tuple[str, str], ...]:
    """(stem, absolute path str) for every non-demo ``.tscn`` under a pack
    tree. Cached like ``threejs_v2._load_json`` — a rescan re-walks each
    pack tree at most once per process."""
    pack_root = Path(pack_root_str)
    rows: list[tuple[str, str]] = []
    for p in sorted(pack_root.rglob("*.tscn")):
        if p.stem.lower() in _DEMO_SCENE_STEMS:
            continue
        rows.append((p.stem, str(p)))
    return tuple(rows)


def scene_index(godot_root: Path | None, pack_id: str) -> tuple[dict[str, str], dict[str, str]]:
    """(exact stem -> path, lowercase stem -> path), both relative to
    ``godot_root`` with forward slashes — mirrors ``threejs_v2.glb_index``."""
    exact: dict[str, str] = {}
    ci: dict[str, str] = {}
    if godot_root is None:
        return exact, ci
    pack_root = discover_pack_dirs(godot_root).get(pack_id)
    if pack_root is None:
        return exact, ci
    for stem, abs_path in _scan_tscn(str(pack_root)):
        rel = rel_posix(Path(abs_path), Path(godot_root))
        exact.setdefault(stem, rel)
        ci.setdefault(stem.lower(), rel)
    return exact, ci


def apply_godot_overlay(asset: dict, scene_rel: str | None) -> dict:
    """Wire ``files.godot_scene`` when a stem match exists. No provenance
    stamp — matches ``apply_threejs_overlay``'s handling of ``files.glb``;
    ``files`` is scanner-owned and refreshed wholesale on every rescan
    (``merge.merge_asset``), so there is nothing for a provenance rank to
    protect here."""
    if scene_rel:
        asset.setdefault("files", {})["godot_scene"] = scene_rel
    return asset
