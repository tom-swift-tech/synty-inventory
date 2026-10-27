"""The W7 reference files, read as the geometry-version-6 builds should match them (G1, docs/weapon_attach_geometry.md 3.3 and 3.11).

``w7_default_export.json``, ``w8d_w7_attach_default_export.json``, ``w8d_w7_attach_roles_all_export.json`` and ``w8d_w7_directory.json.gz`` are REAL
W7 outputs and stay untouched: the files say ``"geometry_version": 5``. A version 6 build of the same worlds is byte-equal to them in every other
character (no existing synthetic record changes its frame), so the comparison text is the reference with that one number changed. Replacing
exactly one occurrence, and failing on any other count, keeps this from becoming a general text rewrite that could hide a real difference.
"""

from __future__ import annotations

import re

_V5 = re.compile(r'"geometry_version"(\s*):(\s*)5\b')


def as_geometry_v6(text: str) -> str:
    """``text`` of a W7 reference with its one ``"geometry_version": 5`` read as 6. Raises when the key is not there exactly once."""
    hits = _V5.findall(text)
    if len(hits) != 1:
        raise AssertionError(f'expected exactly one "geometry_version": 5 in the reference, found {len(hits)}')
    return _V5.sub(lambda m: f'"geometry_version"{m.group(1)}:{m.group(2)}6', text, count=1)
