"""Read Unity .unitypackage archives without the Editor (gzip+tar)."""

from __future__ import annotations

import gzip
import tarfile
from pathlib import Path

from .paths import posix


def list_pathnames(package: Path) -> list[dict]:
    """Return [{guid, pathname, has_preview}] by reading the archive once."""
    rows: dict[str, dict] = {}
    with gzip.open(package, "rb") as gz:
        with tarfile.open(fileobj=gz, mode="r|") as tar:
            for member in tar:
                name = member.name.replace("\\", "/").lstrip("./")
                parts = [p for p in name.split("/") if p]
                if len(parts) < 2:
                    continue
                guid, leaf = parts[0], parts[-1]
                rec = rows.setdefault(guid, {"guid": guid, "pathname": None, "has_preview": False})
                if leaf == "pathname" and member.isfile():
                    fh = tar.extractfile(member)
                    if fh is not None:
                        rec["pathname"] = fh.read().decode("utf-8", "replace").splitlines()[0].strip()
                elif leaf.lower() == "preview.png":
                    rec["has_preview"] = True
    return [r for r in rows.values() if r.get("pathname")]


def extract_previews(
    package: Path,
    dest_dir: Path,
    wanted_stems: set[str] | None = None,
    limit: int = 0,
) -> list[str]:
    """Extract preview.png next to dest_dir/<stem>.png for matching pathnames."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    # First pass: map guid -> stem
    guid_to_stem: dict[str, str] = {}
    with gzip.open(package, "rb") as gz:
        with tarfile.open(fileobj=gz, mode="r|") as tar:
            for member in tar:
                name = member.name.replace("\\", "/").lstrip("./")
                parts = [p for p in name.split("/") if p]
                if len(parts) < 2:
                    continue
                guid, leaf = parts[0], parts[-1]
                if leaf != "pathname" or not member.isfile():
                    continue
                fh = tar.extractfile(member)
                if fh is None:
                    continue
                pathname = fh.read().decode("utf-8", "replace").splitlines()[0].strip()
                stem = Path(pathname.replace("\\", "/")).stem
                if wanted_stems is not None and stem not in wanted_stems:
                    continue
                guid_to_stem[guid] = stem

    written: list[str] = []
    with gzip.open(package, "rb") as gz:
        with tarfile.open(fileobj=gz, mode="r|") as tar:
            for member in tar:
                name = member.name.replace("\\", "/").lstrip("./")
                parts = [p for p in name.split("/") if p]
                if len(parts) < 2 or parts[-1].lower() != "preview.png":
                    continue
                guid = parts[0]
                stem = guid_to_stem.get(guid)
                if not stem:
                    continue
                fh = tar.extractfile(member)
                if fh is None:
                    continue
                out = dest_dir / f"{stem}.png"
                out.write_bytes(fh.read())
                written.append(posix(out))
                if limit and len(written) >= limit:
                    break
    return written
