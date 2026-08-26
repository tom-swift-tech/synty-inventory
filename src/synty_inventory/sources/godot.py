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
# generic normalizer could safely reverse. New Godot export folders get an
# override *before* they are used — do not guess a pack_id. Guessing wrong
# silently misfiles a whole pack's scenes onto nobody (or the wrong pack).
SLUG_PACK_OVERRIDES: dict[str, str] = {
    # "particle-fx" (Synty's hand-made 13-effect export) is intentionally
    # unmapped: superseded for catalog purposes by polygon-particle-fx-01,
    # which contains those scenes verbatim plus the 178 GPUParticles3D
    # rebuilds. One pack_id maps to exactly one folder (discover_pack_dirs).
    "polygon-particle-fx-01": "POLYGON_Particle_FX",
    "polygon-city-01": "POLYGON_City",
    "polygon-starter": "POLYGON_Starter",
    # Synty-shipped Godot exports (previously unmapped)
    "polygon-battle-royale-01": "POLYGON_BattleRoyale",
    "polygon-gang-warfare-01": "POLYGON_Gang_Warfare",
    "polygon-heist-01": "POLYGON_Heist",
    "polygon-military-01": "POLYGON_Military",
    "polygon-sci-fi-city-01": "POLYGON_SciFi_City",
    # locally converted via tools/godot_convert (Unidot / FBX pipelines)
    "polygon-adult-face-plates": "POLYGON_AdultFacePlates",
    "polygon-coffee-shop": "POLYGON_Coffee_Shop",
    "polygon-mech-01": "POLYGON_Mech",
    "polygon-military-warehouse-map-01": "POLYGON_Military_Warehouse_Map",
    "polygon-prototype-01": "POLYGON_Prototype",
    "polygon-quad-bike-01": "POLYGON_QuadBike",
    "polygon-sci-fi-space-01": "POLYGON_SciFi_Space",
    "polygon-war-01": "POLYGON_War",
    "simple-sky": "SIMPLE_Sky",
    # polygon-stunt-plane / polygon-water-guns: no catalog pack_id exists yet;
    # add here once those packs are cataloged
}

# Scenes every Godot export ships (top-level demo/showcase levels), never a
# stem a catalog asset id would match — excluded so they can't accidentally
# satisfy a match.
_DEMO_SCENE_STEMS = {"demo", "overview"}


def _normalize_slug(name: str) -> str:
    """Guess a pack_id from an unmapped folder name — for the warning only.

    Never used to attach scenes. ``"polygon-scifi-city-02"`` ->
    ``"Polygon_Scifi_City"``: close to, but not equal to, ``POLYGON_SciFi_City``
    (multi-word compounds like "SciFi"/"PostApoc" don't round-trip). Add an
    explicit ``SLUG_PACK_OVERRIDES`` entry before scanning a new export.
    """
    import re

    stem = re.sub(r"-\d+$", "", name.strip().lower())
    words = [w for w in re.split(r"[^a-z0-9]+", stem) if w]
    return "_".join(w.capitalize() for w in words) if words else name


def discover_pack_dirs(godot_root: Path | None) -> dict[str, Path]:
    """pack_id -> pack tree root for mapped subdirectories of ``godot_root``.

    Only folders listed in ``SLUG_PACK_OVERRIDES`` are returned. Unmapped
    folders are skipped (see ``unmapped_pack_dirs``) so a guessed id cannot
    attach another pack's scenes.
    """
    if godot_root is None or not Path(godot_root).is_dir():
        return {}
    out: dict[str, Path] = {}
    for child in sorted(Path(godot_root).iterdir()):
        if not child.is_dir():
            continue
        pack_id = SLUG_PACK_OVERRIDES.get(child.name)
        if pack_id is None:
            continue
        out[pack_id] = child
    return out


def unmapped_pack_dirs(godot_root: Path | None) -> list[dict[str, str]]:
    """Folders under ``godot_root`` with no ``SLUG_PACK_OVERRIDES`` entry.

    Each item is ``{slug, guess}``. Reported to the operator; never applied
    as an overlay.
    """
    if godot_root is None or not Path(godot_root).is_dir():
        return []
    rows: list[dict[str, str]] = []
    for child in sorted(Path(godot_root).iterdir()):
        if not child.is_dir():
            continue
        if child.name in SLUG_PACK_OVERRIDES:
            continue
        rows.append({"slug": child.name, "guess": _normalize_slug(child.name)})
    return rows


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
