"""Locator and strip of the geometry fit gate G1 (docs/weapon_attach_geometry.md 3.2): STUBS, replaced by plan slice S3.

A detector module imports only the standard library, ``numpy``, ``fit_types`` and ``mount_probe``; never ``geometry``, ``mounts`` or
``fit_geometry`` (no import cycle for the S7 wiring).
"""

from __future__ import annotations

from .fit_types import Placement


def locate_by_translation(host_verts, part_verts, rules: dict) -> list[Placement]:
    """Spec 3.2 "Presets": find ``part_verts`` inside ``host_verts`` by translation only (0.5 mm grid, 27-neighbour tolerance, accepted at
    hit fraction ``rules['locator']['hit_min']``, placements within ``merge_m`` merged). Not built yet (plan S3)."""
    raise NotImplementedError("fit_locate.locate_by_translation: plan slice S3")


def strip(host_verts, host_tris, placements: list[Placement], part_meshes: dict) -> tuple:
    """Spec 3.2 "strip": drop the host triangles whose three vertices all lie on a located part. Not built yet (plan S3)."""
    raise NotImplementedError("fit_locate.strip: plan slice S3")
