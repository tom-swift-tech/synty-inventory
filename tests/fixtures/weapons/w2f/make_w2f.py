"""Synthetic y-long meshes for the W2f tests (melee forward sign from the larger end head; butt inset). Boxes only, built
with the make_glbs helpers; nothing here is pack geometry. Every mesh has its butt at y = 0 and is returned UNshifted;
the tests move the origin with ``make_glbs.shifted``.

Windows used by the code under test: the current rule compares the lateral AABB AREA of the outer 10 % of the length at
each end; the W2f rule compares the largest lateral EXTENT of the outer 25 %, and only when the ends differ by 15 %.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("make_glbs_w2f", Path(__file__).resolve().parent.parent / "make_glbs.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)


def ornate_staff():
    """L 2.0. A 3 cm square shaft y 0..1.8 and an ornate 12 cm square head y 1.8..2.0. Outer 25 % windows: butt extent
    0.03, head extent 0.12 (ratio 4). Outer 10 % windows: butt area 0.03^2, head area 0.12^2, so the CURRENT rule (a
    non-headed archetype: the thinner end is the tip) points at the butt: -y. The head is the +y end."""
    return M.merge(M.bar(0.0, 1.8, 0.015, 0.015), M.bar(1.8, 2.0, 0.06, 0.06))


def twin_head_staff():
    """L 2.0, a head at each end: 6.0 cm (y 0..0.2) and 6.2 cm (y 1.8..2.0) square, a 3 cm shaft between. The ends differ
    by 3 %, inside the 15 % margin, so the W2f rule is silent and the current rule decides: the thinner (butt) end is the
    tip, forward -y. A rule without the margin would pick the 6.2 cm end: +y."""
    return M.merge(M.bar(0.0, 0.2, 0.030, 0.030), M.bar(0.2, 1.8, 0.015, 0.015), M.bar(1.8, 2.0, 0.031, 0.031))


def capped_spear():
    """L 2.0 spear: a 5 cm square butt cap y 0..0.08, a 2.4 cm shaft to 1.9, a 4 cm x 0.8 cm leaf head and an apex at 2.0.
    The butt (extent 0.05) is wider than the head (0.04), so 'larger end is forward' would say -y; the tip is +y and the
    current rule (outer 10 %: butt cap 0.0025, head 0.00096 area) says +y."""
    return M.merge(M.bar(0.0, 0.08, 0.025, 0.025), M.bar(0.08, 1.9, 0.012, 0.012),
                   M.loft(1, [(1.9, 0.02, 0.004), (2.0, 0.0, 0.0)]))


def guarded_sword():
    """L 0.9 sword: a 20 cm wide guard y 0..0.03 at the butt, a 5 cm wide blade to the apex at 0.9. The guard end is much
    larger; the blade tip is +y. The heavy end is the BUTT for a pointed archetype."""
    return M.merge(M.bar(0.0, 0.03, 0.10, 0.015), M.bar(0.03, 0.88, 0.025, 0.004),
                   M.loft(1, [(0.88, 0.025, 0.004), (0.9, 0.0, 0.0)]))


def tiny_item():
    """L 0.06: a 2 cm square box, butt at y 0. Shorter than twice the 0.045 butt inset."""
    return M.bar(0.0, 0.06, 0.01, 0.01)
