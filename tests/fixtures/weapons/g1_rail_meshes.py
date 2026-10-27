"""Synthetic host meshes for the G1 rail detector tests (docs/weapon_attach_geometry.md 3.4, AC134, AC148): numpy arrays, no GLB, no pack data.

Every mesh is ``(verts, tris)`` in the host's (f, s, u) frame: ``verts`` float (N, 3), ``tris`` int (M, 3). A host is a long body (a box or a
profile prism) with an optional toothed rail prism on top of it. The shapes are made-up numbers (a 23.5 mm pitch, a 4 mm tooth, a 17 mm rail
top); nothing is measured from a pack.

* ``prism(profile, s_lo, s_hi, floor_u)``: the solid under a top profile ``[(f, u), ...]`` extruded over the side range. A profile with two
  points at one f is a vertical wall.
* ``toothed_host(...)``: a body 0..``length`` in f plus a rail of ``n`` teeth, one pitch cell each, starting at ``start_f``.
* ``staircase_host(...)``: a body whose top is a staircase (never flat for 60 mm) with one chosen plateau on it.
* ``mirror_u(mesh)`` flips a host upside down (u negated, winding kept outward): the bottom-rail twin of a top-rail host.
"""

from __future__ import annotations

import numpy as np

BODY_HALF_W = 0.020  # the body is 40 mm wide, centred on ``s_centre``
BODY_DEPTH = 0.050


def concat(*meshes):
    """Join meshes into one ``(verts, tris)``."""
    verts, tris, base = [], [], 0
    for v, t in meshes:
        verts.append(v)
        tris.append(t + base)
        base += len(v)
    return np.vstack(verts), np.vstack(tris).astype(np.int64)


def prism(profile, s_lo, s_hi, floor_u):
    """The solid under the top ``profile`` (``[(f, u), ...]`` rear to front, successive f never decreasing): a top strip, two side walls, a floor
    and two end caps. Outward windings."""
    pts = []
    for p in profile:
        if not pts or tuple(p) != tuple(pts[-1]):
            pts.append((float(p[0]), float(p[1])))
    n = len(pts)
    v = []
    for f, u in pts:  # per profile point: top-lo, top-hi, floor-lo, floor-hi
        v += [(f, s_lo, u), (f, s_hi, u), (f, s_lo, floor_u), (f, s_hi, floor_u)]
    t = []
    for i in range(n - 1):
        a, b = 4 * i, 4 * (i + 1)
        t += [(a, b, b + 1), (a, b + 1, a + 1)]  # top
        t += [(a + 2, b + 2, b), (a + 2, b, a)]  # side s_lo
        t += [(a + 1, b + 1, b + 3), (a + 1, b + 3, a + 3)]  # side s_hi
        t += [(a + 2, a + 3, b + 3), (a + 2, b + 3, b + 2)]  # floor
    t += [(0, 1, 3), (0, 3, 2)]  # rear cap
    e = 4 * (n - 1)
    t += [(e, e + 3, e + 1), (e, e + 2, e + 3)]  # front cap
    return np.array(v, dtype=np.float64), np.array(t, dtype=np.int64)


def box(f0, f1, s0, s1, u0, u1):
    return prism([(f0, u1), (f1, u1)], s0, s1, u0)


def mirror_u(mesh):
    """The host upside down: u negated and the triangle winding reversed (so the mesh stays outward-facing)."""
    v, t = mesh
    v = v * np.array([1.0, 1.0, -1.0])
    return v, t[:, [0, 2, 1]]


def tooth_profile(start_f, n, pitch, crest_w, trough_u, amps):
    """Top profile of ``n`` teeth, one ``pitch`` cell each from ``start_f``: floor at ``trough_u``, a flat crest ``crest_w`` wide, ``amps[i]``
    above the floor (a float means the same for every tooth)."""
    amps = [amps] * n if np.isscalar(amps) else list(amps)
    pts = []
    for i in range(n):
        c = start_f + pitch * (i + 0.5)
        top = trough_u + amps[i]
        pts += [(start_f + pitch * i, trough_u), (c - crest_w / 2, trough_u), (c - crest_w / 2, top), (c + crest_w / 2, top), (c + crest_w / 2, trough_u)]
    pts.append((start_f + pitch * n, trough_u))
    return pts


def toothed_host_at(centres, amp=0.004, crest_w=0.008, rail_w=0.017, length=1.0):
    """Like ``toothed_host`` but with the teeth at explicit ``centres`` (uneven pitches), each a ``crest_w`` crest on a floor 1 mm above the body."""
    body = box(0.0, length, -BODY_HALF_W, BODY_HALF_W, -BODY_DEPTH, 0.0)
    pts = [(centres[0] - 0.010, 0.001)]
    for c in centres:
        pts += [(c - crest_w / 2, 0.001), (c - crest_w / 2, 0.001 + amp), (c + crest_w / 2, 0.001 + amp), (c + crest_w / 2, 0.001)]
    pts.append((centres[-1] + 0.010, 0.001))
    return concat(body, prism(pts, -rail_w / 2, rail_w / 2, 0.0))


def toothed_host(
    n=6,
    pitch=0.0235,
    start_f=0.12,
    amp=0.004,
    amps=None,
    crest_w=0.010,
    rail_w=0.017,
    length=1.0,
    s_centre=0.0,
):
    """A body (f 0..``length``, 40 mm wide, top at u = 0) with a rail on it: ``n`` teeth, ``pitch`` apart, ``amp`` tall (or ``amps`` per tooth),
    each a ``crest_w`` flat crest on a floor 1 mm above the body top, ``rail_w`` wide, centred on ``s_centre``. The rail covers
    ``start_f`` .. ``start_f + n * pitch``. Tooth i is centred at ``start_f + pitch * (i + 0.5)``."""
    body = box(0.0, length, s_centre - BODY_HALF_W, s_centre + BODY_HALF_W, -BODY_DEPTH, 0.0)
    prof = tooth_profile(start_f, n, pitch, crest_w, 0.001, amp if amps is None else amps)
    rail = prism(prof, s_centre - rail_w / 2, s_centre + rail_w / 2, 0.0)
    return concat(body, rail)


def staircase_profile(f_plateau, plateau_len, length=1.0, tread=0.040, riser=0.010, step_after=0.0):
    """A top profile that is a staircase (tread 40 mm, riser 10 mm: neither a 5 mm band nor a 60 mm run fits a tread) around one flat plateau
    ``f_plateau`` .. ``f_plateau + plateau_len`` at u = 0. ``step_after`` lowers the front half of the plateau by that much (a step inside it)."""
    pts = []
    f, u = f_plateau, 0.0
    left = []
    while f > 0.0:  # walk back from the plateau, one tread at a time
        f_next = max(f - tread, 0.0)
        left += [(f, u), (f, u - riser), (f_next, u - riser)]  # backwards: a wall down, then a tread
        f, u = f_next, u - riser
    pts += list(reversed(left))
    half = plateau_len / 2.0
    if step_after:
        pts += [(f_plateau, 0.0), (f_plateau + half, 0.0), (f_plateau + half, -step_after), (f_plateau + plateau_len, -step_after)]
        f, u = f_plateau + plateau_len, -step_after
    else:
        pts += [(f_plateau, 0.0), (f_plateau + plateau_len, 0.0)]
        f, u = f_plateau + plateau_len, 0.0
    while f < length:
        f_next = min(f + tread, length)
        u -= riser
        pts += [(f, u), (f_next, u)]
        f = f_next
    return pts


def staircase_host(f_plateau=0.42, plateau_len=0.080, step_after=0.0, notch=0.0, notch_depth=0.020, length=1.0, s_centre=0.0):
    """A body with a staircase top and one flat plateau on it (f ``f_plateau`` .. ``f_plateau + plateau_len``, u = 0). ``step_after`` drops the
    front half of the plateau by that much; ``notch`` cuts a groove of that width and ``notch_depth`` into the middle of the plateau."""
    prof = staircase_profile(f_plateau, plateau_len, length, step_after=step_after)
    if notch:
        mid = f_plateau + plateau_len / 2.0
        prof = [p for p in prof if not (f_plateau < p[0] < f_plateau + plateau_len)]
        i = next(k for k, p in enumerate(prof) if p[0] >= f_plateau + plateau_len)
        prof[i:i] = [(mid - notch / 2, 0.0), (mid - notch / 2, -notch_depth), (mid + notch / 2, -notch_depth), (mid + notch / 2, 0.0)]
    return prism(prof, s_centre - BODY_HALF_W, s_centre + BODY_HALF_W, -0.2)
