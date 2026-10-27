"""Rail detector of the geometry fit gate G1 (docs/weapon_attach_geometry.md 3.4): STUBS, replaced by plan slice S4.

A detector module imports only the standard library, ``numpy``, ``fit_types`` and ``mount_probe``; never ``geometry``, ``mounts`` or
``fit_geometry`` (no import cycle for the S7 wiring).
"""

from __future__ import annotations

from typing import Literal

from .fit_types import RailRun


def rail_runs(verts_fsu, tris, side: Literal["top", "bottom"], s0: float, rules: dict) -> list[RailRun]:
    """Spec 3.4 steps 1 and 2: the toothed runs of the host's top or bottom profile, in (f, s, u) coordinates. Not built yet (plan S4)."""
    raise NotImplementedError("fit_rails.rail_runs: plan slice S4")


def flat_seat(verts_fsu, tris, s0: float, rules: dict) -> RailRun | None:
    """Spec 3.4 step 3: the untoothed fallback, the longest flat top run (``toothed`` False), or None. Not built yet (plan S4)."""
    raise NotImplementedError("fit_rails.flat_seat: plan slice S4")
