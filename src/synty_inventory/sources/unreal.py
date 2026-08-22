"""Unreal ``.uasset`` pack tree discovery + per-asset overlay onto the
catalog of record.

No Unreal export tree exists on any known machine yet (unlike Godot — see
``sources/godot.py``, which this module mirrors exactly so the two engines
share one wiring shape in ``enrich.py``). Every function here degrades to
empty/null when ``unreal_root`` is unset or a pack subdirectory isn't
mapped; nothing here ever raises for a missing tree.

Distinct from ``scan.scan_unreal``: that function builds a *whole* catalog
from a pack that is natively Unreal (``engine == "Unreal"``, no Unity
source at all — see ``catalog.build_catalog``). This module instead
overlays ``files.unreal_uasset`` onto an already-cataloged (typically
Unity-sourced) asset from a separate Unreal reference tree, the same way
``sources/godot.py`` overlays ``files.godot_scene``. ``apply_unreal_overlay``
never clobbers a value ``scan_unreal`` already set for a native pack.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from ..paths import rel_posix
from .godot import _normalize_slug

# slug (folder name directly under unreal_root) -> pack_id. Empty today —
# no Unreal export tree exists anywhere yet. Unmapped folders are *not*
# guessed: overlays apply only when the folder name equals ``pack_id`` or
# an explicit override maps the slug. Guessing would silently misfile a
# whole pack, same as Godot.
SLUG_PACK_OVERRIDES: dict[str, str] = {}

UNREAL_EXT = ".uasset"

# Shape every real pack_id shares (POLYGON_City, SIDEKICK_Starter, SIMPLE_Sky,
# ANIMATION_Emotes_And_Taunts, GEN_<Theme>): capitalized first token plus at
# least one underscore-joined token. A vendor slug ("polygon-city-01") or a
# stray folder ("Content", "Docs") does not match — it is reported via
# ``unmapped_pack_dirs`` instead of silently becoming a bogus pack_id that
# matches no catalog and no-ops the whole overlay.
_PACK_ID_RE = re.compile(r"^[A-Z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+$")


def _classify(unreal_root: Path | None) -> tuple[dict[str, Path], list[Path], list[dict[str, str]]]:
    """One walk of ``unreal_root`` -> (pack_id -> folder, unmapped folders,
    collision rows). Explicit ``SLUG_PACK_OVERRIDES`` entries claim their
    pack_id first — an operator mapping always beats a literal folder-name
    match on the same pack_id; the loser is reported, never silently dropped.
    """
    mapped: dict[str, Path] = {}
    unmapped: list[Path] = []
    collisions: list[dict[str, str]] = []
    if unreal_root is None or not Path(unreal_root).is_dir():
        return mapped, unmapped, collisions
    children = [c for c in sorted(Path(unreal_root).iterdir()) if c.is_dir()]
    for child in children:
        pack_id = SLUG_PACK_OVERRIDES.get(child.name)
        if pack_id is None:
            continue
        if pack_id in mapped:
            collisions.append({"pack_id": pack_id, "kept": mapped[pack_id].name, "dropped": child.name})
            continue
        mapped[pack_id] = child
    for child in children:
        if child.name in SLUG_PACK_OVERRIDES:
            continue
        if not _PACK_ID_RE.match(child.name):
            unmapped.append(child)
            continue
        if child.name in mapped:
            collisions.append({"pack_id": child.name, "kept": mapped[child.name].name, "dropped": child.name})
            continue
        mapped[child.name] = child
    return mapped, unmapped, collisions


def discover_pack_dirs(unreal_root: Path | None) -> dict[str, Path]:
    """pack_id -> pack tree root for subdirectories of ``unreal_root``.

    A folder overlays a pack only when its name is an explicit
    ``SLUG_PACK_OVERRIDES`` slug or equals ``pack_id`` exactly (pack-id
    shape enforced by ``_PACK_ID_RE``). No title-case / drop-revision guess
    — a stray folder cannot stamp ``files.unreal_uasset`` on an unrelated
    pack. When an override and a literal folder resolve to the same
    pack_id, the override wins and the collision is reported via
    ``collision_pack_dirs`` — never silently overwritten. Returns ``{}``
    when ``unreal_root`` is ``None`` or missing — the expected state on
    every machine today.
    """
    mapped, _, _ = _classify(unreal_root)
    return mapped


def unmapped_pack_dirs(unreal_root: Path | None) -> list[dict[str, str]]:
    """Folders under ``unreal_root`` that neither carry a
    ``SLUG_PACK_OVERRIDES`` entry nor look like a literal pack_id.

    Each item is ``{slug, guess}`` — mirrors ``sources.godot.unmapped_pack_dirs``.
    Reported to the operator; never applied as an overlay.
    """
    _, unmapped, _ = _classify(unreal_root)
    return [{"slug": c.name, "guess": _normalize_slug(c.name)} for c in unmapped]


def collision_pack_dirs(unreal_root: Path | None) -> list[dict[str, str]]:
    """Folders dropped because another folder already claimed their pack_id.

    Each item is ``{pack_id, kept, dropped}``. Reported to the operator so a
    transitional layout (renamed vendor drop kept beside the old export)
    cannot silently discard a whole ``.uasset`` tree.
    """
    _, _, collisions = _classify(unreal_root)
    return collisions


@lru_cache(maxsize=16)
def _scan_uasset(pack_root_str: str) -> tuple[tuple[str, str], ...]:
    """(stem, absolute path str) for every ``.uasset`` under a pack tree."""
    pack_root = Path(pack_root_str)
    rows: list[tuple[str, str]] = []
    for p in sorted(pack_root.rglob(f"*{UNREAL_EXT}")):
        rows.append((p.stem, str(p)))
    return tuple(rows)


def asset_index(unreal_root: Path | None, pack_id: str) -> tuple[dict[str, str], dict[str, str]]:
    """(exact stem -> path, lowercase stem -> path), both relative to
    ``unreal_root`` with forward slashes — mirrors ``sources.godot.scene_index``."""
    exact: dict[str, str] = {}
    ci: dict[str, str] = {}
    if unreal_root is None:
        return exact, ci
    pack_root = discover_pack_dirs(unreal_root).get(pack_id)
    if pack_root is None:
        return exact, ci
    for stem, abs_path in _scan_uasset(str(pack_root)):
        rel = rel_posix(Path(abs_path), Path(unreal_root))
        exact.setdefault(stem, rel)
        ci.setdefault(stem.lower(), rel)
    return exact, ci


def apply_unreal_overlay(asset: dict, uasset_rel: str | None) -> dict:
    """Wire ``files.unreal_uasset`` when a stem match exists and nothing
    already claimed it. A native Unreal-sourced pack (``scan.scan_unreal``,
    via ``enrich.skeleton_asset``) already sets this field from the pack's
    own tree; a reference ``unreal_root`` overlay must not overwrite that
    with a (possibly different-revision) match from a separate tree. No
    provenance stamp — same reasoning as ``sources.godot.apply_godot_overlay``."""
    if not uasset_rel:
        return asset
    files = asset.setdefault("files", {})
    if not files.get("unreal_uasset"):
        files["unreal_uasset"] = uasset_rel
    return asset
