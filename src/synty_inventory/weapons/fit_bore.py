"""Bore detector of the geometry fit gate G1 (docs/weapon_attach_geometry.md 3.6; plan slice S5; errata E1.1).

``barrel_end`` finds the barrel end of a host (an existing ring bore, a front-face ring, or a round end section) and ``device_inner_d`` reads the
inner bore ring on a muzzle device's mating face. Both are pure functions over vertex arrays: no I/O, no clock, no global state.

A detector module imports only the standard library, ``numpy``, ``fit_types`` and ``mount_probe``; never ``geometry``, ``mounts`` or
``fit_geometry`` (no import cycle for the S7 wiring). The ring estimator is ``mount_probe.end_ring_d``, shared with the frame vote of 3.3 step 3.

The caller hands in the host mesh already reduced (minus the muzzle ``occupied_by`` children, minus located parts, minus collision). A baked
device left in the mesh would put its own face at the forward extreme and be read as the barrel (AC135 break); this module cannot tell it apart.

Judgment calls (reported with the slice):

* The slab centre is the middle of the slab's lateral extent (min + max over 2), the convention of ``end_ring_d`` and of ``attach``'s "not the vertex
  mean" rule: vertex density is arbitrary. ``od_m`` is twice the largest distance of any slab vertex from that centre, as 3.6 says. That is the
  reading for evidence (ii) and (iii). For evidence (i) E3.1 (B) reads the barrel FACE instead (below): on a slide or receiver face the whole face
  sits in the slab and its far corners are not the barrel.
* Evidence (i) is read on the stripped mesh (E3.2, W1). This module cannot probe (it may not import ``geometry`` or ``mounts``), so the caller probes
  the stripped host and hands the answer in as data inside ``mount["stripped_face"]`` = ``{"ring": bool, "centre_su": [s, u] | None, "od_m": float |
  None}`` (``mounts.stripped_muzzle_face``). The record's centre is the mean of the face points (s, u) and ``od_m`` twice their largest distance from
  it: a face is a ring of points, so the vertex-density argument above does not apply to it. A mount with no ``stripped_face`` key is read as it was
  before E3: the mount's own ``bore_source`` decides (i) and the slab gives the values (a hand-built mount, the unit tests).
* Only vertices that a triangle uses count. A caller that reduced the triangles but left the host's vertex array whole would otherwise leak the
  removed child's vertices into the end slab. With no triangles at all the vertices are used as given.
* The (iii) roundness test reads the slab's side and up extents (3.6 gives the formula). Extents alone call every square round (ratio 1.0), so E1.1
  adds ``circ_min``: the convex hull of the slab's (s, u) points must fill that share of the circle of diameter ``od_m`` (a square fills 0.637, any
  rectangle at most 2/pi, a regular hexagon 0.827, an octagon 0.900). The hull area needs no sampling and does not depend on vertex density.
"""

from __future__ import annotations

import numpy as np

from .fit_types import BarrelEnd
from .mount_probe import end_ring_d

_EPS = 1e-9
_AXIS_DOMINANCE = 0.999  # a device's `up` counts as axis-aligned when one component holds this share of its length (anchors are unit axes, rounded to 1e-4)


def _r(x) -> float:
    return round(float(x), 4) + 0.0


def _sorted(v: np.ndarray) -> np.ndarray:
    """Spec 4.3: vertices sorted lexicographically (f, then s, then u) before any binning."""
    return v[np.lexsort((v[:, 2], v[:, 1], v[:, 0]))] if len(v) else v


def _hull_area(points: np.ndarray) -> float:
    """Area of the convex hull of the (N, 2) ``points``: Andrew's monotone chain over the sorted distinct points (collinear points dropped), then
    the shoelace sum. Fewer than three distinct points, or all on one line, give 0."""
    pts = np.unique(np.asarray(points, dtype=np.float64).reshape(-1, 2), axis=0)  # sorted lexicographically (s, then u), duplicates gone
    if len(pts) < 3:
        return 0.0

    def chain(seq) -> list:
        out: list = []
        for p in seq:
            while len(out) >= 2 and (out[-1][0] - out[-2][0]) * (p[1] - out[-2][1]) - (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0]) <= 0.0:
                out.pop()
            out.append(p)
        return out

    lower, upper = chain(pts), chain(pts[::-1])
    hull = lower[:-1] + upper[:-1]  # counter-clockwise, each chain's last point is the other's first
    if len(hull) < 3:
        return 0.0
    h = np.array(hull)
    return 0.5 * abs(float(np.dot(h[:, 0], np.roll(h[:, 1], -1)) - np.dot(h[:, 1], np.roll(h[:, 0], -1))))


def _used_vertices(verts, tris) -> np.ndarray:
    v = np.asarray(verts, dtype=np.float64).reshape(-1, 3)
    t = np.asarray(tris if tris is not None else [], dtype=np.int64).reshape(-1, 3)
    if len(t):
        v = v[np.unique(t)]
    return _sorted(v)


def barrel_end(verts_fsu, tris, mount: dict, rules: dict) -> BarrelEnd | None:
    """Spec 3.6: the host's barrel end (existing ring bore, front-face ring or round end section), or None.

    ``verts_fsu`` is (N, 3) in the host's (forward, side, up) frame and ``tris`` (M, 3) integer indices; the mesh is the host minus muzzle
    ``occupied_by``, minus located parts, minus collision. ``rules`` is the ``attachment_rules.fit_geometry`` block; this reads ``rules["bore"]``
    (``end_slab_m``, ``round_min``, ``circ_min``, ``barrel_od_max_m``). ``mount`` is the host's muzzle mount (``mounts.py``); only ``bore_source`` and
    the optional ``stripped_face`` are read.

    The end slab is the vertices within ``end_slab_m`` of the forward extreme. A barrel end exists when, in this order of evidence:

    * (i) the A0 probe found a ring bore (evidence ``ring``). Without ``mount["stripped_face"]`` that is ``mount["bore_source"] == "ring"``. With it,
      the ring must be on the stripped host's muzzle face (``stripped_face["ring"]``) AND the host must have a muzzle mount that found a face
      (``bore_source`` not None): a preset that is no host has no mount and so no (i), and a mount whose own face is a ring but whose stripped face
      has none (the ring was a fused device's) falls through to (ii);
    * (ii) ``mount_probe.end_ring_d`` finds a front-face ring in the slab (evidence ``face_ring``);
    * (iii) the slab is a round end section: ``min(extent_s, extent_u) / max(...)`` >= ``round_min``, the hull of the slab's (s, u) points fills
      ``circ_min`` of the circle of diameter ``od_m`` (E1.1: a square or any rectangle never does), and OD <= ``barrel_od_max_m`` (evidence
      ``round_section``).

    ``od_m`` is twice the slab's outer radius around the slab centre and ``centre_su`` that centre, for (ii) and (iii); for (i) read through a
    ``stripped_face`` they are the barrel face's (E3.1: the face's mean position and twice its largest distance from it). ``face_f`` is the forward
    extreme. The bore axis is host forward through ``centre_su``. Measures are rounded to 1e-4. An empty mesh has no end, whatever the mount says.
    """
    v = _used_vertices(verts_fsu, tris)
    if not len(v):
        return None
    bore = rules["bore"]
    slab_m = bore["end_slab_m"]
    face_f = float(v[:, 0].max())
    slab = v[v[:, 0] >= face_f - slab_m - _EPS]
    lat = slab[:, 1:]
    lo, hi = lat.min(axis=0), lat.max(axis=0)
    centre = (lo + hi) / 2.0
    od = 2.0 * float(np.linalg.norm(lat - centre, axis=1).max())
    mount = mount or {}
    face = mount.get("stripped_face")
    if face is None:
        ring = mount.get("bore_source") == "ring"
    else:  # E3.2 (W1): the stripped host decides, and only a host with a muzzle mount that found a face can have (i)
        ring = mount.get("bore_source") is not None and bool(face.get("ring"))
    if ring:
        evidence = "ring"
        if face is not None and face.get("centre_su") is not None and face.get("od_m") is not None:  # E3.1 (B): the barrel face, not the slab
            centre, od = np.asarray(face["centre_su"], dtype=np.float64), float(face["od_m"])
    elif end_ring_d(v, 0, 1, slab_m) is not None:
        evidence = "face_ring"
    else:
        ext = hi - lo
        longest = float(ext.max())
        round_enough = longest > _EPS and float(ext.min()) / longest >= bore["round_min"] - _EPS
        if not (round_enough and od <= bore["barrel_od_max_m"] + _EPS):
            return None
        # E1.1: the section fills its circle (A_hull over the disc of diameter od_m); od > 0 here, a round_enough slab has a nonzero extent
        if _hull_area(lat) / (np.pi * (od / 2.0) ** 2) < bore["circ_min"] - _EPS:
            return None
        evidence = "round_section"
    return BarrelEnd(centre_su=(_r(centre[0]), _r(centre[1])), face_f=_r(face_f), od_m=_r(od), evidence=evidence)


def device_inner_d(part_verts_fsu, anchor: dict, rules: dict) -> float | None:
    """Spec 3.6 "Part side": the inner bore ring diameter on a device's mating face, or None when it has none.

    ``part_verts_fsu`` is the device's vertex array and ``anchor`` its muzzle anchor (``attach.measure_anchor``); the vertices and the anchor are in
    the same frame, and only ``anchor["up"]`` is read. For a muzzle device ``up`` is the bore direction toward the free end (3.4 step 4), so the
    mating face is the extreme on the opposite side. The ring is ``mount_probe.end_ring_d`` on that face with the same ``bore.end_slab_m`` slab
    as the host side (the same estimator, spec 3.6), and a ring close to the device's own outer radius is not a bore (None).

    None as well when the anchor is missing, has no ``up``, or its ``up`` is not along one coordinate axis.
    """
    up = (anchor or {}).get("up")
    if up is None:
        return None
    u = np.asarray(up, dtype=np.float64).reshape(-1)
    norm = float(np.linalg.norm(u)) if u.shape == (3,) else 0.0
    if not np.isfinite(norm) or norm < _EPS:
        return None
    axis = int(np.argmax(np.abs(u)))
    if abs(float(u[axis])) < _AXIS_DOMINANCE * norm:
        return None
    v = np.asarray(part_verts_fsu, dtype=np.float64).reshape(-1, 3)
    if not len(v):
        return None
    d = end_ring_d(_sorted(v), axis, -1 if u[axis] > 0 else 1, rules["bore"]["end_slab_m"])
    return None if d is None else _r(d)
