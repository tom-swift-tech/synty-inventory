"""Sight seat probe: where the rear and front iron sights stand on a host (docs/weapon_attachments.md 4.6, W8h-B).

Pure numpy over a mesh: no files, no clock. No live host names its iron-sight children by side, so the seats are estimated
from the top profile of the gun, and a host the probe cannot decide stays ``none`` (``probe_unavailable``):

1. The caller passes the host mesh minus the nodes of ``occupied_by`` of ``optic``, ``sight_front`` and ``sight_rear``
   (a baked scope is not the rail).
2. Profile: host forward is binned (``bin_m``); a bin's height is the highest ``up`` of the SURFACE within
   ``max(side_min_m, side_frac x side extent)`` of the side centre. An empty bin breaks a run. The side centre is the median side
   coordinate of the surface within ``ridge_tol_m`` of the highest point (the line the sights stand on), not the middle of the
   bounding box: a stock, a side pouch or a magazine skews the box off the barrel line (live measurement, 2026-10-23).
3. ``h_top`` is the highest bin. The receiver run is the contiguous bins around it within ``receiver_tol_m`` of ``h_top``; the
   rail run continues it forward while the bins stay within ``rail_tol_m`` (a handguard lower than the receiver).
4. Rear seat = the receiver run's rear end moved forward by ``rear_inset_m``; front seat = the rail run's forward end moved back
   by ``front_inset_m``; each at the height of the surface under it: five vertical rays over the footprint (the seat and the points
   ``seat_ray_m`` ahead, behind and to each side) read the first surface hit, the seat takes their median. A sloping face or a
   groove down the ridge would otherwise leave a bin-height seat floating (live measurement, 2026-10-23: 65 of 131 seats > 3 mm off).
5. A receiver run of fewer than ``min_receiver_bins`` bins, or a front seat less than ``min_separation_m`` ahead of the rear
   seat, refuses both seats. So does a seat whose three rays along the bore do not all hit the host (the side rays may miss: a
   ridge can be narrower than the footprint) or whose hits spread more than ``seat_flat_tol_m`` (a cliff or a hole under the
   seat, where a sight has nothing to stand on): the numeric gates of 4.6 item 6 hold by construction.

Judgment call (reported): the spec says "the vertices whose side coordinate is within ...", but a low-poly top face has
vertices only at its ends, so every bin between them would be empty and every host refused. The profile therefore reads
the surface: each triangle is sampled on a barycentric grid no coarser than ``_SAMPLE_M`` and the samples stand in for
the vertices. A flat face then gives the same height in every bin it covers, which is what the rule means.
"""

from __future__ import annotations

import numpy as np

_SAMPLE_M = 0.0025  # triangle sampling pitch: half the default bin, so no bin a face covers stays empty
_MAX_GRID = 400  # a triangle edge longer than 400 x _SAMPLE_M (1 m) is capped; no gun part has one
_CHUNK_POINTS = 1_000_000  # samples built per numpy block
_EPS = 1e-9


def _r(x) -> float:
    return round(float(x), 4) + 0.0


def surface_samples(vertices: np.ndarray, triangles: np.ndarray, pitch: float = _SAMPLE_M) -> np.ndarray:
    """The vertices plus barycentric grid samples of every triangle (spacing at most ``pitch`` along its longest edge)."""
    v = np.asarray(vertices, dtype=np.float64).reshape(-1, 3)
    t = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    if not len(v) or not len(t):
        return v
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    longest = np.maximum.reduce([np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1), np.linalg.norm(a - c, axis=1)])
    n_of = np.clip(np.ceil(longest / pitch - _EPS).astype(np.int64), 1, _MAX_GRID)
    out = [v]
    for n in np.unique(n_of):
        if n <= 1:
            continue
        i, j = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing="ij")
        keep = (i + j) <= n
        wb, wc = (i[keep] / n)[:, None, None], (j[keep] / n)[:, None, None]  # [K,1,1]
        wa = 1.0 - wb - wc
        ia = np.flatnonzero(n_of == n)
        step = max(1, _CHUNK_POINTS // len(wb))  # bound the [K,T,3] block of one group
        for lo in range(0, len(ia), step):
            sel = ia[lo : lo + step]
            out.append((wa * a[sel][None] + wb * b[sel][None] + wc * c[sel][None]).reshape(-1, 3))
    return np.concatenate(out)


def _top_up(tri: np.ndarray, f: float, s: float) -> float | None:
    """The highest signed-up coordinate of the surface above the point ``(f, s)`` of the forward/side plane, or None when it misses.

    ``tri`` is ``[T, 3, 3]`` holding (forward, side, up) per triangle corner. Barycentric test in the plane, then the up
    coordinate interpolated at the point; triangles standing edge-on in the plane (zero area there) are skipped.
    """
    f0, f1, f2 = tri[:, 0, 0], tri[:, 1, 0], tri[:, 2, 0]
    s0, s1, s2 = tri[:, 0, 1], tri[:, 1, 1], tri[:, 2, 1]
    det = (s1 - s2) * (f0 - f2) + (f2 - f1) * (s0 - s2)
    ok = np.abs(det) > 1e-14
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    l1 = ((s1 - s2) * (f - f2) + (f2 - f1) * (s - s2)) * inv
    l2 = ((s2 - s0) * (f - f2) + (f0 - f2) * (s - s2)) * inv
    l3 = 1.0 - l1 - l2
    hit = ok & (l1 >= -_EPS) & (l2 >= -_EPS) & (l3 >= -_EPS)
    if not hit.any():
        return None
    return float((l1 * tri[:, 0, 2] + l2 * tri[:, 1, 2] + l3 * tri[:, 2, 2])[hit].max())


def sight_seats(vertices: np.ndarray, triangles: np.ndarray, axes: dict, params: dict) -> dict | None:
    """``{"sight_rear": [x, y, z], "sight_front": [x, y, z]}`` in the mesh's own axes, or None when the probe refuses (step 5).

    ``axes`` is the host's ``{forward, up}`` signed axes (``"-z"``, ``"+y"``); ``params`` is ``attachment_rules.sight_probe``.
    """
    samples = surface_samples(vertices, triangles)
    if not len(samples):
        return None
    f_i, u_i = "xyz".index(axes["forward"][1]), "xyz".index(axes["up"][1])
    f_s, u_s = (1.0 if axes["forward"][0] == "+" else -1.0), (1.0 if axes["up"][0] == "+" else -1.0)
    s_i = ({0, 1, 2} - {f_i, u_i}).pop()
    fc, uc, sc = f_s * samples[:, f_i], u_s * samples[:, u_i], samples[:, s_i]
    s_lo, s_hi = float(sc.min()), float(sc.max())
    ridge = uc >= float(uc.max()) - params["ridge_tol_m"] - _EPS
    s_mid = float(np.median(sc[ridge]))
    window = max(params["side_min_m"], params["side_frac"] * (s_hi - s_lo))
    near = np.abs(sc - s_mid) <= window + _EPS
    if not near.any():
        return None
    fc, uc, sc = fc[near], uc[near], sc[near]
    bin_m = params["bin_m"]
    f_lo = float(fc.min())
    index = np.floor((fc - f_lo) / bin_m + _EPS).astype(np.int64)
    height = np.full(int(index.max()) + 1, -np.inf)
    np.maximum.at(height, index, uc)
    filled = np.isfinite(height)  # an empty bin breaks a run
    top_bin = int(np.argmax(height))
    h_top = float(height[top_bin])

    def run(start: int, step: int, tol: float) -> int:
        """The last bin reached from ``start`` in direction ``step`` while bins are filled and within ``tol`` of h_top."""
        k = start
        while 0 <= k + step < len(height) and filled[k + step] and height[k + step] >= h_top - tol - _EPS:
            k += step
        return k

    rec_lo, rec_hi = run(top_bin, -1, params["receiver_tol_m"]), run(top_bin, +1, params["receiver_tol_m"])
    if rec_hi - rec_lo + 1 < params["min_receiver_bins"]:
        return None
    rail_hi = run(rec_hi, +1, params["rail_tol_m"])
    rear_f = f_lo + rec_lo * bin_m + params["rear_inset_m"]
    front_f = f_lo + (rail_hi + 1) * bin_m - params["front_inset_m"]
    if front_f - rear_f < params["min_separation_m"] - _EPS:
        return None
    v = np.asarray(vertices, dtype=np.float64).reshape(-1, 3)
    corners = np.stack([f_s * v[:, f_i], v[:, s_i], u_s * v[:, u_i]], axis=1)[np.asarray(triangles, dtype=np.int64).reshape(-1, 3)]
    d = params["seat_ray_m"]
    seats = {}
    for slot, f_val in (("sight_rear", rear_f), ("sight_front", front_f)):
        along = [_top_up(corners, f_val + df, s_mid) for df in (0.0, -d, d)]
        if any(h is None for h in along):
            return None  # the host does not run on along the bore under this seat
        side = [h for h in (_top_up(corners, f_val, s_mid - d), _top_up(corners, f_val, s_mid + d)) if h is not None]  # a ridge may be narrower
        hits = along + side
        if max(hits) - min(hits) > params["seat_flat_tol_m"] + _EPS:
            return None
        up_val = float(np.median(hits))
        point = np.zeros(3)
        point[f_i], point[u_i], point[s_i] = f_s * f_val, u_s * up_val, s_mid
        seats[slot] = [_r(c) for c in point]
    return seats
