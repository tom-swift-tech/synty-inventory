"""Bore detector of the geometry fit gate G1 (docs/weapon_attach_geometry.md 3.6): STUBS, replaced by plan slice S5.

A detector module imports only the standard library, ``numpy``, ``fit_types`` and ``mount_probe``; never ``geometry``, ``mounts`` or
``fit_geometry`` (no import cycle for the S7 wiring).
"""

from __future__ import annotations

from .fit_types import BarrelEnd


def barrel_end(verts_fsu, tris, mount: dict, rules: dict) -> BarrelEnd | None:
    """Spec 3.6: the host's barrel end (existing ring bore, front-face ring or round end section), or None. Not built yet (plan S5)."""
    raise NotImplementedError("fit_bore.barrel_end: plan slice S5")


def device_inner_d(part_verts_fsu, anchor: dict, rules: dict) -> float | None:
    """Spec 3.6 "Part side": the inner bore ring diameter on a device's mating face, or None when it has none. Not built yet (plan S5)."""
    raise NotImplementedError("fit_bore.device_inner_d: plan slice S5")
