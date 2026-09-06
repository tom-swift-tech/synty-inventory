"""GUID -> asset-path index built once by walking every ``.meta`` file.

The Unity scene YAML references every prefab/material/asset by GUID, never
by path; the catalog's join key (``files.unity_prefab``) is a path. This
module is the bridge: it walks ``<extracted_root>/**/*.meta`` exactly once
and reads the ``guid:`` line directly (a plain regex, not a full YAML parse
— ``.meta`` files are tiny and always trivial YAML, so this is both faster
and simpler than a real parser), mapping each GUID to the asset path it
describes (the ``.meta`` path minus its own ``.meta`` suffix, relative to
the extracted root, posix separators).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ..paths import posix

_GUID_RE = re.compile(r"^guid:\s*([0-9a-fA-F]{32})\s*$", re.MULTILINE)


class GuidIndexError(ValueError):
    """The extracted tree has two ``.meta`` files claiming the same GUID.

    This means the extracted tree is corrupt (a GUID must be unique); there
    is no sane way to pick one over the other, so this always raises rather
    than silently keeping the first (spec §7).
    """


@dataclass(frozen=True)
class GuidIndex:
    by_guid: Mapping[str, str]  # guid (lowercase hex) -> asset path relative to extracted_root, posix

    @classmethod
    def build(cls, extracted_root: Path) -> "GuidIndex":
        by_guid: dict[str, str] = {}
        for meta_path in sorted(extracted_root.rglob("*.meta")):
            text = meta_path.read_text(encoding="utf-8", errors="replace")
            match = _GUID_RE.search(text)
            if not match:
                continue
            guid = match.group(1).lower()
            asset_path = meta_path.with_suffix("")  # strip the trailing ".meta" only
            rel = posix(asset_path.relative_to(extracted_root))
            existing = by_guid.get(guid)
            if existing is not None and existing != rel:
                raise GuidIndexError(
                    f"duplicate GUID {guid} claimed by two .meta files: {existing!r} and {rel!r} "
                    f"under {extracted_root} -- the extracted tree is corrupt"
                )
            by_guid[guid] = rel
        return cls(by_guid=by_guid)
