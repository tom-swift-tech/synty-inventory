"""Synthetic meshes for the G1 locator and strip tests (docs/weapon_attach_geometry.md 3.2; nothing here is from a real pack).

The part is a 12-vertex, 12-triangle asymmetric mesh about 2 cm across. Each vertex is written as ``(cell + fraction) * 0.0005`` per axis, the
cell being a whole number of 0.5 mm grid cells and the fraction 0.25 or 0.75, so no vertex sits on a grid-cell edge (float rounding cannot flip
a cell) and a translation of a whole number of cells keeps every vertex off the edges as well. The lexicographically smallest vertex (the one
the locator takes its candidate translations from) is vertex 0, whose three fractions are all 0.25. Because the other vertices carry fraction
0.75 on some axes, a translation of half a cell (0.25 mm) carries them across a cell edge but not vertex 0: the case only the 27-neighbour
tolerance finds. Vertices are at least about 3 mm apart, and the mesh has no translation symmetry, so a located copy has no aliases.

``host_from`` builds a host as the base mesh followed by translated copies of the part (vertex indices of the copies are offset).
"""

from __future__ import annotations

import numpy as np

_G = 0.0005  # the cell size the vertex table below is written in (a literal here, the fixture does not read the rules)

# (cell_x, cell_y, cell_z, frac_x, frac_y, frac_z); the lexicographically smallest vertex is the first row
_PART_TABLE = [
    (0, 0, 0, 0.25, 0.25, 0.25),
    (12, 0, 0, 0.75, 0.25, 0.75),
    (12, 16, 0, 0.25, 0.75, 0.25),
    (4, 16, 6, 0.75, 0.75, 0.25),
    (24, 6, 10, 0.25, 0.25, 0.75),
    (24, 22, 4, 0.75, 0.75, 0.75),
    (8, 8, 30, 0.25, 0.75, 0.75),
    (20, 12, 26, 0.75, 0.25, 0.25),
    (36, 10, 14, 0.25, 0.75, 0.25),
    (30, 30, 18, 0.75, 0.25, 0.75),
    (16, 26, 34, 0.25, 0.25, 0.75),
    (40, 4, 22, 0.75, 0.75, 0.25),
]
_PART_TRIS = [
    (0, 1, 2), (0, 2, 3), (1, 4, 2), (2, 4, 5), (3, 2, 5), (3, 5, 6),
    (4, 7, 5), (5, 7, 6), (7, 4, 8), (8, 9, 7), (9, 10, 7), (10, 11, 9),
]  # fmt: skip


def asymmetric_part() -> tuple[np.ndarray, np.ndarray]:
    """``(verts (12, 3) float64, tris (12, 3) int64)`` of the part, in metres."""
    t = np.array(_PART_TABLE, dtype=np.float64)
    verts = (t[:, :3] + t[:, 3:]) * _G
    return verts, np.array(_PART_TRIS, dtype=np.int64)


def moved(verts, index: int, delta) -> np.ndarray:
    """A copy of ``verts`` with vertex ``index`` moved by ``delta`` (metres)."""
    out = np.array(verts, dtype=np.float64)
    out[index] += np.asarray(delta, dtype=np.float64)
    return out


def host_from(base_verts, base_tris, part_verts, part_tris, translations) -> tuple[np.ndarray, np.ndarray]:
    """The base mesh followed by one translated copy of the part per translation: ``(verts, tris)``."""
    bv = np.asarray(base_verts, dtype=np.float64).reshape(-1, 3)
    bt = np.asarray(base_tris, dtype=np.int64).reshape(-1, 3)
    pv = np.asarray(part_verts, dtype=np.float64)
    pt = np.asarray(part_tris, dtype=np.int64)
    verts, tris = [bv], [bt]
    offset = len(bv)
    for t in translations:
        verts.append(pv + np.asarray(t, dtype=np.float64))
        tris.append(pt + offset)
        offset += len(pv)
    return np.vstack(verts), np.vstack(tris)
