"""Colourway discovery and the variant texture resolver (docs/weapon_directory.md section 3.7).

A Synty pack that ships colourways does it with *atlas alts*: one UV atlas texture per colourway, each wrapped by a
material ``<Pack>/Materials/Alts/<Atlas>_NN_<L>.mat`` (``L`` = ``A``, ``B``, ...) with its texture beside it under
``<Pack>/Textures/Alts/``. The catalog's ``files.unity_materials`` points at one of them (the default colourway);
the sibling letters exist only on disk in the extracted Unity tree, so discovery lists the directory.

``discover_variants(asset, extracted_root)`` returns the ``visuals.variants[]`` list. ``extracted_root`` is the
extracted tree of ONE pack, the folder whose ``Assets/Synty/<Pack>/...`` the catalog's relative paths hang off
(``<configured extracted_root>/<pack_id>``). Each variant's ``source`` is its material path relative to that folder,
in the same form as ``files.unity_materials`` (``Assets/Synty/<Pack>/Materials/Alts/<Atlas>_NN_B.mat``), so it
carries no machine path.

``resolve_variant_texture`` is the material -> texture mapping ``icons --variants`` needs: read the albedo slot of the
material, take its texture guid, find the ``.meta`` that declares that guid in the mirrored ``Textures`` directory,
and fall back to the same file stem there. It is stdlib only and never writes.
"""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath

MECHANISM = "atlas_alt"
# <Atlas>_NN_<L>.mat : a numbered atlas and one capital letter for the colourway
_ALTS_MAT = re.compile(r"^(?P<prefix>.+_\d+_)(?P<letter>[A-Z])\.mat$")
_LETTER_MAT = re.compile(r"^[A-Z]\.mat$")
# The albedo slot of a Unity material, by shader family (Synty shader graphs use _Albedo_Map, URP lit _BaseMap,
# built-in lit _MainTex). The first slot in this order that holds a texture wins.
_ALBEDO_SLOTS = ("_Albedo_Map", "_BaseMap", "_MainTex", "_BaseColorMap")
# Slots only the icon renderer's albedo-from-material path adds (spec 3.8 PATCH W7): the Viking_Realm shield materials
# keep their texture in ``_Base_Texture``. Colourway resolution never passes this, so its behaviour is unchanged.
EXTRA_ALBEDO_SLOTS = ("_Base_Texture",)
MATERIAL_ALBEDO_SLOTS = _ALBEDO_SLOTS + EXTRA_ALBEDO_SLOTS
_GUID = re.compile(r"^\s*guid:\s*([0-9a-fA-F]{32})\s*$", re.MULTILINE)
TEXTURE_EXTS = (".png", ".jpg", ".jpeg")  # what the browser harness loads; .tga and others are reported, not guessed


class TextureNotFound(LookupError):
    """The variant's material or texture cannot be resolved to a loadable image (the message says why)."""


def _listing(directory: Path, cache: dict | None) -> list[str]:
    """Sorted file names of ``directory`` ([] when it is missing); cached per directory when ``cache`` is given."""
    if cache is not None and directory in cache:
        return cache[directory]
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        names = []
    if cache is not None:
        cache[directory] = names
    return names


def _safe_rel(path: str) -> PurePosixPath | None:
    """A catalog material path as a relative POSIX path, or None when it is absolute or climbs out of the tree."""
    rel = PurePosixPath(path.replace("\\", "/"))
    if rel.is_absolute() or ".." in rel.parts or (rel.parts and rel.parts[0].endswith(":")):
        return None
    return rel


def variant_link_paths(icons_dirname: str, pack: str, asset_id: str, letter: str) -> tuple[str, str]:
    """``(icon, thumb)`` of one variant as written into ``visuals.variants[]``: relative to directory.json.

    ``icons/<pack>/<asset_id>@<L>.png`` and ``...@<L>@64.png``: the default icon's names with the colourway letter
    inserted, so the two sets can never collide (a plain ``@64`` never has a letter in front of it).
    """
    base = f"{icons_dirname}/{pack}/{asset_id}@{letter}"
    return f"{base}.png", f"{base}@64.png"


def has_colourway_info(asset: dict) -> bool:
    """True when the catalog recorded at least one material (the ``colourway_unknown`` test, spec 3.7)."""
    return bool(((asset.get("files") or {}).get("unity_materials")) or [])


def default_alts_material(asset: dict) -> tuple[PurePosixPath, str, str] | None:
    """``(material path, name prefix, default letter)`` of the first Alts material the catalog lists, else None."""
    for raw in (asset.get("files") or {}).get("unity_materials") or []:
        if not isinstance(raw, str):
            continue
        rel = _safe_rel(raw)
        if rel is None or len(rel.parts) < 3 or rel.parts[-2] != "Alts" or rel.parts[-3] != "Materials":
            continue
        m = _ALTS_MAT.match(rel.name)
        if m:
            return rel, m.group("prefix"), m.group("letter")
    return None


def discover_variants(asset: dict, extracted_root: Path | None, listing_cache: dict | None = None) -> list[dict]:
    """The ``visuals.variants[]`` of one asset or record; ``[]`` when there is nothing to list.

    ``[]`` covers: no extracted tree given, no Alts material in the catalog's list (a dedicated material or a
    mesh-level colourway: spec 3.7 lists those as not variants), an unreadable directory, and a lone colourway
    (one letter is not a choice). With several Alts materials the first in catalog order decides, so the result
    is a function of the catalog and the directory listing alone (INV-4). ``listing_cache`` (dir -> names) lets a
    whole build list each Alts directory once.
    """
    if extracted_root is None:
        return []
    found = default_alts_material(asset)
    if found is None:
        return []
    rel, prefix, default = found
    names = _listing(Path(extracted_root) / Path(*rel.parent.parts), listing_cache)
    letters = {n[len(prefix)] for n in names if n.startswith(prefix) and _LETTER_MAT.match(n[len(prefix):])}
    letters.add(default)  # the catalog's own pointer counts even if the file went missing from the tree
    if len(letters) < 2:
        return []
    return [
        {"variant_id": letter, "mechanism": MECHANISM,
         "source": (rel.parent / f"{prefix}{letter}.mat").as_posix(), "is_default": letter == default, "icon": None}
        for letter in sorted(letters)
    ]


def _guid_index(directory: Path, cache: dict | None) -> dict[str, str]:
    """guid -> texture file name for every ``X.meta`` in ``directory`` (the guid line sits in the first lines)."""
    key = ("guids", directory)
    if cache is not None and key in cache:
        return cache[key]
    index: dict[str, str] = {}
    for name in _listing(directory, cache):
        if not name.endswith(".meta"):
            continue
        try:
            with open(directory / name, "r", encoding="utf-8", errors="replace") as fh:
                head = fh.read(512)
        except OSError:
            continue
        m = _GUID.search(head)
        if m:
            index.setdefault(m.group(1).lower(), name[: -len(".meta")])
    if cache is not None:
        cache[key] = index
    return index


def _albedo_guid(material_text: str, slots: tuple[str, ...] = _ALBEDO_SLOTS) -> str | None:
    for slot in slots:
        m = re.search(rf"^\s*-\s*{re.escape(slot)}:\s*\r?\n\s*m_Texture:\s*\{{[^}}]*guid:\s*([0-9a-fA-F]{{32}})",
                      material_text, re.MULTILINE)
        if m:
            return m.group(1).lower()
    return None


def _texture_dirs(material_rel: PurePosixPath) -> list[PurePosixPath]:
    """Where the texture of a material can sit, nearest first: the ``Textures`` directory mirroring the material's
    ``Materials`` directory (``Materials/Alts`` -> ``Textures/Alts``), then each parent up to ``Textures`` itself
    (some packs keep their Alts atlases directly in ``Textures``)."""
    parts = list(material_rel.parent.parts)
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] == "Materials":
            tail = parts[i + 1:]
            out = [PurePosixPath(*parts[:i], "Textures", *tail[:n]) for n in range(len(tail), -1, -1)]
            # some packs name the atlas folder "Alt" (Materials/Alts, Textures/Alt): try both spellings last
            for alt in ("Alt", "Alts"):
                extra = PurePosixPath(*parts[:i], "Textures", alt)
                if extra not in out:
                    out.append(extra)
            return out
    return []


def resolve_variant_texture(extracted_root: Path, source: str, cache: dict | None = None, *,
                            slots: tuple[str, ...] = _ALBEDO_SLOTS) -> Path:
    """The albedo image of the variant material ``source`` (a path relative to ``extracted_root``).

    ``slots`` are the albedo slots tried in order; the default is the colourway set. The icon renderer's
    albedo-from-material path passes ``MATERIAL_ALBEDO_SLOTS``.

    Order: the texture whose ``.meta`` guid the material's albedo slot names, looked up in the mirrored
    ``Textures`` directory; then the same file stem there with a loadable extension. ``TextureNotFound`` carries
    the reason (no material, no albedo, no texture, or a format the harness cannot load such as ``.tga``).
    """
    rel = _safe_rel(source)
    if rel is None:
        raise TextureNotFound(f"unsafe material path {source!r}")
    mat = Path(extracted_root) / Path(*rel.parts)
    try:
        text = mat.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise TextureNotFound(f"material not readable: {rel.as_posix()} ({exc.strerror or exc})") from exc
    dirs = _texture_dirs(rel)
    if not dirs:
        raise TextureNotFound(f"material is not under a Materials directory: {rel.as_posix()}")
    guid = _albedo_guid(text, slots)
    stem = rel.name[: -len(".mat")]
    unsupported: str | None = None
    for d_rel in dirs:  # the guid beats the file name in every directory before the next directory is tried
        d = Path(extracted_root) / Path(*d_rel.parts)
        names = set(_listing(d, cache))
        picks = []
        if guid and guid in _guid_index(d, cache):
            picks.append(_guid_index(d, cache)[guid])
        picks += [n for n in sorted(names) if Path(n).stem == stem and not n.endswith(".meta")]
        for name in picks:
            if name not in names:
                continue
            if Path(name).suffix.lower() in TEXTURE_EXTS:
                return d / name
            unsupported = unsupported or name
    if unsupported:
        raise TextureNotFound(f"unsupported texture format {Path(unsupported).suffix} for {rel.as_posix()} "
                              f"(the harness loads {', '.join(TEXTURE_EXTS)})")
    raise TextureNotFound(f"no texture found for {rel.as_posix()} under {dirs[-1].as_posix()}")
