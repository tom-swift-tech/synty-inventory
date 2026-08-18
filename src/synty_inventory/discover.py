"""Find Synty packs from Unity packages, extracted folders, or Unreal trees."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .paths import posix

PACKAGE_RE = re.compile(
    r"^(?P<id>[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*)_Unity_(?P<ver>.+)\.unitypackage$",
    re.IGNORECASE,
)
UNREAL_MARKERS = ("Content", ".uproject", ".uasset")
SKIP_DIR_NAMES = {
    "asset-viewer",
    "tasks",
    "__pycache__",
    "node_modules",
    ".git",
    "syntypackagehelper",
}


@dataclass
class PackRef:
    pack_id: str
    engine: str
    package_path: Path | None = None
    extracted_path: Path | None = None
    unreal_path: Path | None = None
    extras: dict = field(default_factory=dict)

    @property
    def scan_root(self) -> Path | None:
        return self.extracted_path or self.unreal_path

    @property
    def label(self) -> str:
        return self.pack_id.replace("_", " ")


def pack_id_from_package_name(name: str) -> str | None:
    m = PACKAGE_RE.match(name)
    if m:
        return m.group("id")
    if name.lower().endswith(".unitypackage"):
        return Path(name).stem
    return None


def pack_id_from_folder(name: str) -> str:
    return name


def is_extracted_unity_pack(path: Path) -> bool:
    if not path.is_dir():
        return False
    assets = path / "Assets" if (path / "Assets").is_dir() else path
    if (assets / "Synty").is_dir():
        return True
    # SIMPLE_Sky and similar
    if any(p.suffix.lower() == ".prefab" for p in assets.rglob("*.prefab")):
        return True
    return False


def is_unreal_pack(path: Path) -> bool:
    if not path.is_dir():
        return False
    if any(path.glob("*.uproject")):
        return True
    content = path / "Content"
    if content.is_dir() and any(content.rglob("*.uasset")):
        return True
    return False


def _extracted_for(pack_id: str, extracted_root: Path | None) -> Path | None:
    if extracted_root is None or not extracted_root.is_dir():
        return None
    direct = extracted_root / pack_id
    if direct.is_dir():
        return direct
    # case-insensitive
    low = pack_id.lower()
    for child in extracted_root.iterdir():
        if child.is_dir() and child.name.lower() == low:
            return child
    return None


def discover(target: Path, extracted_root: Path | None = None) -> list[PackRef]:
    """Discover packs under a Unity root, an extracted root, a single pack, or a .unitypackage."""
    target = target.resolve()
    found: dict[str, PackRef] = {}

    def add(ref: PackRef) -> None:
        existing = found.get(ref.pack_id)
        if existing is None:
            found[ref.pack_id] = ref
            return
        if ref.package_path and not existing.package_path:
            existing.package_path = ref.package_path
        if ref.extracted_path and not existing.extracted_path:
            existing.extracted_path = ref.extracted_path
        if ref.unreal_path and not existing.unreal_path:
            existing.unreal_path = ref.unreal_path

    if target.is_file() and target.suffix.lower() == ".unitypackage":
        pid = pack_id_from_package_name(target.name) or target.stem
        add(
            PackRef(
                pack_id=pid,
                engine="Unity",
                package_path=target,
                extracted_path=_extracted_for(pid, extracted_root),
            )
        )
        return list(found.values())

    if not target.is_dir():
        return []

    if is_extracted_unity_pack(target):
        pid = pack_id_from_folder(target.name)
        add(PackRef(pack_id=pid, engine="Unity", extracted_path=target))
        return list(found.values())

    if is_unreal_pack(target):
        add(PackRef(pack_id=target.name, engine="Unreal", unreal_path=target))
        return list(found.values())

    # Root that may contain packages + subfolders
    for child in sorted(target.iterdir()):
        if child.name in SKIP_DIR_NAMES or child.name.startswith("."):
            continue
        if child.is_file() and child.suffix.lower() == ".unitypackage":
            pid = pack_id_from_package_name(child.name) or child.stem
            add(
                PackRef(
                    pack_id=pid,
                    engine="Unity",
                    package_path=child,
                    extracted_path=_extracted_for(pid, extracted_root),
                )
            )
        elif child.is_dir() and is_extracted_unity_pack(child):
            add(PackRef(pack_id=child.name, engine="Unity", extracted_path=child))
        elif child.is_dir() and is_unreal_pack(child):
            add(PackRef(pack_id=child.name, engine="Unreal", unreal_path=child))

    # If we were pointed at the Unity packages folder, also pick up extracted twins
    # that have no package (shouldn't happen) and attach extracted_root matches.
    if extracted_root and extracted_root.is_dir():
        for ref in list(found.values()):
            if ref.extracted_path is None:
                ref.extracted_path = _extracted_for(ref.pack_id, extracted_root)

    return sorted(found.values(), key=lambda r: r.pack_id)


def summarize(refs: list[PackRef]) -> list[dict]:
    return [
        {
            "pack_id": r.pack_id,
            "engine": r.engine,
            "package": posix(r.package_path) if r.package_path else None,
            "extracted": posix(r.extracted_path) if r.extracted_path else None,
            "unreal": posix(r.unreal_path) if r.unreal_path else None,
            "scannable": r.scan_root is not None or r.package_path is not None,
        }
        for r in refs
    ]
