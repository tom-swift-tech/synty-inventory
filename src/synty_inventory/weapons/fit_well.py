"""Magazine well reference of the geometry fit gate G1 (docs/weapon_attach_geometry.md 3.7): STUBS, replaced by plan slice S6.

A detector module imports only the standard library, ``numpy``, ``fit_types`` and ``mount_probe``; never ``geometry``, ``mounts`` or
``fit_geometry`` (no import cycle for the S7 wiring).
"""

from __future__ import annotations

from .fit_types import WellRef


def well_reference(host_verts_fsu, host_tris, mag_verts_fsu, mag_tris, rules: dict) -> WellRef | None:
    """Spec 3.7 step 1: the receiver-bottom plane and the entry section of the authored magazine, or None. Not built yet (plan S6)."""
    raise NotImplementedError("fit_well.well_reference: plan slice S6")


def entry_section(mag_verts_fsu, mag_tris, u_plane: float) -> tuple[float, float] | None:
    """Spec 3.7 steps 1 and 2: the (f, s) extent of a magazine cut by the plane ``u = u_plane``; None when the section is empty (a drum, or
    a part that does not reach the plane). Not built yet (plan S6)."""
    raise NotImplementedError("fit_well.entry_section: plan slice S6")
