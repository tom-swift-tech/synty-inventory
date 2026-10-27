"""Synthetic meshes for the G1 bore detector tests (docs/weapon_attach_geometry.md 3.6; tests/test_weapons_g1_bore.py).

Pure numpy, no GLB and no pack data: every mesh is a tube or a box built from literals. A host is in the host's (f, s, u) frame (forward, side,
up; barrel along +f). A device is in its own asset axes (bore direction along +y unless a builder says otherwise).

Every tube puts vertices at the four axis angles, so the AABB of a ring (and with it the detector's slab centre and OD) is exact to float
precision. A ring is built at two stations (the end face and 5 mm behind it) so an end ring holds well over the six vertices that
``mount_probe.end_ring_d`` needs inside the 10 mm end slab. ``tube(..., n=6)`` and ``n=8`` are the polygonal tubes of E1.1.
"""

from __future__ import annotations

import numpy as np

N_RING = 32  # vertices per ring; a multiple of 4, so the axis angles are among them
STATION_BACK_M = 0.005  # the second ring station, behind the end face


def _ring(f: float, centre: tuple[float, float], rs: float, ru: float, n: int = N_RING) -> np.ndarray:
    a = 2.0 * np.pi * np.arange(n) / n
    return np.column_stack([np.full(n, f), centre[0] + rs * np.cos(a), centre[1] + ru * np.sin(a)])


def _band(lo: int, hi: int, n: int = N_RING) -> list[list[int]]:
    """Triangles between the ring starting at index ``lo`` and the ring starting at ``hi`` (same vertex count, same order)."""
    out = []
    for k in range(n):
        k2 = (k + 1) % n
        out += [[lo + k, lo + k2, hi + k], [lo + k2, hi + k2, hi + k]]
    return out


def tube(f0: float, f1: float, outer_r: float | tuple[float, float], inner_r: float | None = None,
         centre: tuple[float, float] = (0.0, 0.0), n: int = N_RING) -> tuple[np.ndarray, np.ndarray]:
    """A tube along +f from ``f0`` to the end face at ``f1``. ``outer_r`` is a radius, or ``(r_side, r_up)`` for an elliptical section.

    ``n`` is the vertex count of every ring (E1.1): 6 gives a hexagonal tube and 8 an octagonal one (outer vertices on ``outer_r``, one on +s).

    ``inner_r`` None gives a solid end (a fan to a centre vertex on the end face, which is one vertex at radius 0); a number gives a bore of that
    radius, open at the end face (the inner ring stands at the same two stations as the outer one: the "front-face ring").
    """
    rs, ru = (outer_r, outer_r) if np.isscalar(outer_r) else outer_r
    stations = [f1 - STATION_BACK_M, f1]
    verts = [_ring(f, centre, rs, ru, n) for f in (f0, *stations)]
    tris = _band(0, n, n) + _band(n, 2 * n, n)
    if inner_r is None:
        verts.append(np.array([[f1, centre[0], centre[1]]]))
        tris += [[2 * n + k, 2 * n + (k + 1) % n, 3 * n] for k in range(n)]
    else:
        base = 3 * n
        verts += [_ring(f, centre, inner_r, inner_r, n) for f in stations]
        tris += _band(base, base + n, n)  # the bore wall
        tris += _band(2 * n, base + n, n)  # the annular end face
    return np.concatenate(verts), np.array(tris, dtype=np.int64)


def box(f0: float, f1: float, half_s: float, half_u: float, centre: tuple[float, float] = (0.0, 0.0)) -> tuple[np.ndarray, np.ndarray]:
    """A rectangular block along +f: a flat-cut, non-round end (a slide or a boxy handguard)."""
    verts = np.array([[f, centre[0] + sx * half_s, centre[1] + su * half_u] for f in (f0, f1) for sx in (-1, 1) for su in (-1, 1)], dtype=np.float64)
    quads = [(0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)]
    tris = [[q[0], q[1], q[2]] for q in quads] + [[q[0], q[2], q[3]] for q in quads]
    return verts, np.array(tris, dtype=np.int64)


def merge(*meshes: tuple[np.ndarray, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    verts, tris, base = [], [], 0
    for v, t in meshes:
        verts.append(v)
        tris.append(t + base)
        base += len(v)
    return np.concatenate(verts), np.concatenate(tris)


def shuffled(mesh: tuple[np.ndarray, np.ndarray], seed: int) -> tuple[np.ndarray, np.ndarray]:
    """The same mesh with its vertices in another order (the triangle indices follow)."""
    v, t = mesh
    order = np.random.default_rng(seed).permutation(len(v))
    rank = np.empty(len(v), dtype=np.int64)
    rank[order] = np.arange(len(v))
    return v[order], rank[t]


def host_with_baked_device(body: str) -> dict:
    """A host whose barrel ends at f = 0.40 and carries a wider baked device in front of it (f 0.40 to 0.55).

    ``body`` is ``"round"`` (a solid round barrel of OD 0.030) or ``"box"`` (a 0.050 x 0.030 block with no round end and no ring). The device is
    a hollow tube of OD 0.045 with a 0.020 bore, so measured alone its end is a ringed one of OD 0.045. The caller of the detector hands in the host
    MINUS the baked device (``reduced``); ``unreduced`` is what the detector must not be fed.
    """
    barrel = tube(0.0, 0.40, 0.015) if body == "round" else box(0.0, 0.40, 0.025, 0.015)
    device = tube(0.40, 0.55, 0.0225, 0.010)
    return {"reduced": barrel, "device": device, "unreduced": merge(barrel, device)}


def device_mesh(outer_d: float, inner_d: float | None, axis: int = 1, sign: int = 1) -> np.ndarray:
    """A muzzle device in asset axes: a tube 0.10 long whose MATING face is at the origin and whose bore direction points along ``sign * axis``.

    ``outer_d`` and ``inner_d`` are diameters; ``inner_d`` None gives a solid mating face (no ring). Only vertices are returned: the device
    estimator reads vertices. The face is the tube's end face, mirrored so the body runs away from it.
    """
    v, _ = tube(-0.10, 0.0, outer_d / 2.0, None if inner_d is None else inner_d / 2.0)
    out = np.zeros_like(v)
    others = [i for i in range(3) if i != axis]
    out[:, axis] = -sign * v[:, 0]  # tube() runs back from its face along -f; the device runs from its face along sign * axis
    out[:, others[0]], out[:, others[1]] = v[:, 1], v[:, 2]
    return out
