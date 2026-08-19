"""Deprecated import path — moved to :mod:`synty_inventory.sources.viewer`.

Kept as a thin re-export so any external caller doing
``from synty_inventory.dimensions import measured_size`` still works.
"""

from __future__ import annotations

from .sources.viewer import (
    load_type_sign_usage,
    load_viewer_pack,
    load_viewer_pieces,
    load_viewer_props,
    load_viewer_signs,
    measured_size,
)

__all__ = [
    "load_type_sign_usage",
    "load_viewer_pack",
    "load_viewer_pieces",
    "load_viewer_props",
    "load_viewer_signs",
    "measured_size",
]
