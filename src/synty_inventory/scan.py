"""Walk extracted Unity/Unreal trees and emit skeleton asset records."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .naming import normalize_stem, should_skip
from .paths import rel_posix

GUID_RE = re.compile(r"^guid:\s*([0-9a-fA-F]{32})\s*$", re.MULTILINE)
MAT_GUID_RE = re.compile(r"guid:\s*([0-9a-fA-F]{32}).*type:\s*2")
SHARED_KIT_NAMES = {"polygongeneric", "generic"}
MESH_EXTS = {".fbx", ".obj", ".blend"}
PREFAB_EXTS = {".prefab"}
UNREAL_EXTS = {".uasset"}


@dataclass
class RawFile:
    stem: str
    rel: str
    abs_path: Path
    kind: str  # prefab | mesh | material | thumbnail | unreal
    kit: str | None = None
    guid: str | None = None
    shared: bool = False


@dataclass
class RawAsset:
    id: str
    kit: str | None
    shared: bool
    prefab: RawFile | None = None
    mesh: RawFile | None = None
    materials: list[str] = field(default_factory=list)
    thumbnail: str | None = None
    guid: str | None = None
    engine: str = "Unity"


def find_assets_root(pack_root: Path) -> Path:
    if (pack_root / "Assets").is_dir():
        return pack_root / "Assets"
    return pack_root


def kit_dirs(assets_root: Path) -> list[Path]:
    synty = assets_root / "Synty"
    if synty.is_dir():
        return [
            p
            for p in sorted(synty.iterdir())
            if p.is_dir() and p.name.lower() != "syntypackagehelper"
        ]
    return [p for p in sorted(assets_root.iterdir()) if p.is_dir()]


def index_guids(root: Path) -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    for meta in root.rglob("*.meta"):
        try:
            text = meta.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = GUID_RE.search(text)
        if not m:
            continue
        asset = meta.with_suffix("")
        # .prefab.meta -> .prefab  (with_suffix strips .meta only if we handle)
        if meta.name.endswith(".meta"):
            asset = meta.parent / meta.name[:-5]
        mapping[m.group(1).lower()] = asset
    return mapping


def _read_guid(meta_path: Path) -> str | None:
    try:
        text = meta_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = GUID_RE.search(text)
    return m.group(1).lower() if m else None


def _prefab_material_guids(prefab: Path) -> list[str]:
    try:
        text = prefab.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    found: list[str] = []
    idx = 0
    while True:
        start = text.find("m_Materials:", idx)
        if start < 0:
            break
        # Consume the YAML list immediately under m_Materials; stop at the next key.
        for line in text[start:].splitlines()[1:]:
            stripped = line.strip()
            if not stripped:
                continue
            if not line[:1].isspace() and not stripped.startswith("-"):
                break
            if stripped.startswith("m_") and not stripped.startswith("-"):
                break
            m = MAT_GUID_RE.search(line)
            if m:
                g = m.group(1).lower()
                if g not in found:
                    found.append(g)
            elif stripped.startswith("-") and "guid:" not in stripped:
                break
        idx = start + 12
    return found


def _kit_name(path: Path, assets_root: Path) -> str | None:
    try:
        rel = path.relative_to(assets_root)
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) >= 2 and parts[0].lower() == "synty":
        return parts[1]
    if parts:
        return parts[0]
    return None


def _is_shared(kit: str | None) -> bool:
    return bool(kit) and kit.lower() in SHARED_KIT_NAMES


def _collect_files(assets_root: Path) -> list[RawFile]:
    files: list[RawFile] = []
    for path in assets_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() == ".meta":
            continue
        rel = rel_posix(path, assets_root.parent if assets_root.name == "Assets" else assets_root)
        # keep paths relative to pack root (parent of Assets when present)
        pack_root = assets_root.parent if assets_root.name == "Assets" else assets_root
        rel = rel_posix(path, pack_root)
        stem = normalize_stem(path.name)
        if should_skip(rel, stem):
            continue
        ext = path.suffix.lower()
        if ext in PREFAB_EXTS:
            kind = "prefab"
        elif ext in MESH_EXTS:
            kind = "mesh"
        elif ext == ".mat":
            kind = "material"
        elif ext in {".png", ".tga", ".jpg"} and "preview" in path.name.lower():
            kind = "thumbnail"
        else:
            continue
        kit = _kit_name(path, assets_root)
        files.append(
            RawFile(
                stem=stem,
                rel=rel,
                abs_path=path,
                kind=kind,
                kit=kit,
                guid=_read_guid(Path(str(path) + ".meta")),
                shared=_is_shared(kit),
            )
        )
    return files


def scan_extracted(pack_root: Path, include_shared: bool = False) -> list[RawAsset]:
    assets_root = find_assets_root(pack_root)
    files = _collect_files(assets_root)
    guid_index = index_guids(assets_root)

    by_stem: dict[str, RawAsset] = {}
    thumbs: dict[str, str] = {}
    thumbs_shared: dict[str, bool] = {}

    def take(f: RawFile) -> RawAsset | None:
        """Prefer pack-specific files over PolygonGeneric twins of the same stem."""
        rec = by_stem.get(f.stem)
        if rec is None:
            rec = RawAsset(id=f.stem, kit=f.kit, shared=f.shared)
            by_stem[f.stem] = rec
            return rec
        if rec.shared and not f.shared:
            rec = RawAsset(id=f.stem, kit=f.kit, shared=False)
            by_stem[f.stem] = rec
            return rec
        if (not rec.shared) and f.shared:
            return None
        return rec

    for f in files:
        if f.shared and not include_shared:
            continue
        if f.kind == "thumbnail":
            if f.stem in thumbs and not thumbs_shared.get(f.stem) and f.shared:
                continue
            thumbs[f.stem] = f.rel
            thumbs_shared[f.stem] = f.shared
            continue
        if f.kind == "material":
            continue
        rec = take(f)
        if rec is None:
            continue
        if f.kind == "prefab":
            rec.prefab = f
            rec.guid = f.guid
            rec.engine = "Unity"
            for g in _prefab_material_guids(f.abs_path):
                mat = guid_index.get(g)
                if mat is None:
                    continue
                rel = rel_posix(mat, pack_root)
                if rel not in rec.materials:
                    rec.materials.append(rel)
        elif f.kind == "mesh" and rec.mesh is None:
            rec.mesh = f

    out: list[RawAsset] = []
    for rec in by_stem.values():
        if rec.prefab is None and rec.mesh is None:
            continue
        if rec.shared and not include_shared:
            continue
        # mesh-only collision leftovers
        if rec.prefab is None and rec.mesh and should_skip(rec.mesh.rel, rec.id):
            continue
        rec.thumbnail = thumbs.get(rec.id)
        out.append(rec)
    out.sort(key=lambda a: a.id)
    return out


def scan_unreal(pack_root: Path) -> list[RawAsset]:
    content = pack_root / "Content" if (pack_root / "Content").is_dir() else pack_root
    assets: list[RawAsset] = []
    seen: set[str] = set()
    for path in content.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in UNREAL_EXTS:
            continue
        rel = rel_posix(path, pack_root)
        stem = normalize_stem(path.name)
        if should_skip(rel, stem) or stem in seen:
            continue
        seen.add(stem)
        assets.append(
            RawAsset(
                id=stem,
                kit=None,
                shared=False,
                mesh=RawFile(stem=stem, rel=rel, abs_path=path, kind="unreal"),
                engine="Unreal",
            )
        )
    assets.sort(key=lambda a: a.id)
    return assets


def preview_relpath(pack_id: str | None, stem: str) -> str:
    if pack_id:
        return f"previews/{pack_id}/{stem}.png"
    return f"previews/{stem}.png"


def scan_from_package_listing(
    pathnames: list[dict],
    include_shared: bool = False,
    pack_id: str | None = None,
) -> list[RawAsset]:
    """Build skeleton assets from unitypackage pathname entries."""
    by_stem: dict[str, RawAsset] = {}
    for row in pathnames:
        pathname = (row.get("pathname") or "").replace("\\", "/")
        if not pathname:
            continue
        stem = normalize_stem(pathname)
        if should_skip(pathname, stem):
            continue
        low = pathname.lower()
        shared = "/polygongeneric/" in low
        if shared and not include_shared:
            continue
        rec = by_stem.get(stem)
        if rec is None:
            rec = RawAsset(id=stem, kit=None, shared=shared)
            by_stem[stem] = rec
        elif rec.shared and not shared:
            rec = RawAsset(id=stem, kit=None, shared=False)
            by_stem[stem] = rec
        elif (not rec.shared) and shared:
            continue
        rec.guid = row.get("guid")
        if pathname.lower().endswith(".prefab"):
            rec.prefab = RawFile(stem=stem, rel=pathname, abs_path=Path(pathname), kind="prefab")
        elif Path(pathname).suffix.lower() in MESH_EXTS:
            if rec.mesh is None:
                rec.mesh = RawFile(stem=stem, rel=pathname, abs_path=Path(pathname), kind="mesh")
        if row.get("has_preview"):
            rec.thumbnail = preview_relpath(pack_id, stem)
    return sorted(
        [a for a in by_stem.values() if a.prefab or a.mesh],
        key=lambda a: a.id,
    )
