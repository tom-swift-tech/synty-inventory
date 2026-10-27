"""Synthetic meshes for the G1 well slice (S6): a receiver block and magazines, in the host (f, s, u) frame (forward, side, up).

Everything is generated with numpy from the literals below; there is no pack mesh and no measured number. A mesh is ``(verts, tris)``: an (N, 3)
float array and an (M, 3) int array. Every rectangle face is two triangles split along the SAME corner pair (0-2), so its diagonal runs through
the face centre: that is the case a vertical line through a top-face centre has to survive without a double count (spec 3.7 step 1).

World (metres):

* ``receiver()``: a block f in [-0.08, 0.08], s in [-0.03, 0.03], u in [0.00, 0.05]; its bottom face (u = 0) is the receiver bottom, ``u_rb`` 0.
* ``mag_straight()``: a prism 0.060 x 0.024 (f x s) from u = -0.12 up to its top at u = 0.01 (it pokes 1 cm into the receiver).
* ``mag_tapered()``: 0.060 x 0.024 up to u = -0.005, then a linear neck to 0.040 x 0.016 at its top u = 0.01. At the entry plane u = -0.002 it is
  0.056 x 0.0224 (the neck is 20 % up), at its own top 0.040 x 0.016: two clearly different widths.
* ``mag_drum()``: a 0.10 x 0.10 prism whose top is at u = -0.03, i.e. below the entry plane: it does not reach it.
"""

from __future__ import annotations

import numpy as np


def loft(rings, cf: float = 0.0, cs: float = 0.0):
    """A closed prism through rectangular rings ``(u, half_f, half_s)``, centred on (cf, cs). Four vertices per ring, both caps and every side a
    quad split along corner pair 0-2."""
    rings = list(rings)
    verts = []
    for u, hf, hs in rings:
        for df, ds in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            verts.append((cf + df * hf, cs + ds * hs, u))
    tris = []

    def quad(a, b, c, d):
        tris.append((a, b, c))
        tris.append((a, c, d))

    quad(0, 3, 2, 1)  # bottom cap
    n = len(rings)
    top = 4 * (n - 1)
    quad(top, top + 1, top + 2, top + 3)  # top cap
    for k in range(n - 1):
        b0, b1 = 4 * k, 4 * (k + 1)
        for i in range(4):
            j = (i + 1) % 4
            quad(b0 + i, b0 + j, b1 + j, b1 + i)
    return np.array(verts, dtype=np.float64), np.array(tris, dtype=np.int64)


def box(f0: float, f1: float, s0: float, s1: float, u0: float, u1: float):
    hf, hs = (f1 - f0) / 2, (s1 - s0) / 2
    return loft([(u0, hf, hs), (u1, hf, hs)], cf=(f0 + f1) / 2, cs=(s0 + s1) / 2)


def receiver():
    return box(-0.08, 0.08, -0.03, 0.03, 0.00, 0.05)


def mag_straight(top: float = 0.01):
    return loft([(-0.12, 0.03, 0.012), (top, 0.03, 0.012)])


def mag_tapered():
    return loft([(-0.12, 0.03, 0.012), (-0.005, 0.03, 0.012), (0.01, 0.02, 0.008)])


def mag_drum():
    return loft([(-0.15, 0.05, 0.05), (-0.03, 0.05, 0.05)])


def scaled_fs(mesh, k_f: float, k_s: float | None = None):
    """The mesh scaled in f by ``k_f`` and in s by ``k_s`` (default ``k_f``) about the origin."""
    v, t = mesh
    k_s = k_f if k_s is None else k_s
    return v * np.array([k_f, k_s, 1.0]), t.copy()


def shifted(mesh, df: float = 0.0, ds: float = 0.0, du: float = 0.0):
    v, t = mesh
    return v + np.array([df, ds, du]), t.copy()


def merged(*meshes):
    verts, tris, base = [], [], 0
    for v, t in meshes:
        verts.append(v)
        tris.append(t + base)
        base += len(v)
    return np.concatenate(verts), np.concatenate(tris)


def shuffled(mesh, seed: int):
    """The same surface with the vertex order and the triangle order permuted (indices remapped)."""
    v, t = mesh
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(v))
    inv = np.empty_like(perm)
    inv[perm] = np.arange(len(v))
    t2 = inv[t]
    return v[perm], t2[rng.permutation(len(t2))]
