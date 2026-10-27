"""Rail detector of the geometry fit gate G1 (docs/weapon_attach_geometry.md 3.4): toothed runs, flat seat, sight clip, seat point.

A detector module imports only the standard library, ``numpy``, ``fit_types`` and ``mount_probe``; never ``geometry``, ``mounts`` or
``fit_geometry`` (no import cycle for the S7 wiring).

Public: ``rail_runs`` (steps 1 and 2), ``flat_seat`` (step 3), and the two pure helpers S7 uses for step 4: ``clip_run`` (sight seats) and
``seat_point``. Every function is pure over plain arrays: ``verts_fsu`` is an (N, 3) array in the host's (forward, side, up) frame, ``tris`` an
(M, 3) integer index array, ``rules`` the ``attachment_rules.fit_geometry`` block (this module reads ``rules["rail"]`` and ``rules["flat"]``).

Readings of the spec (each is a choice where 3.4 is silent; reported with the slice):

* **Surface, not corner vertices.** Step 1 says "the vertices within ``window_m`` of the centreline". A low-poly face has vertices only at its
  corners, so an 80 mm smooth top would be one 80 mm hole in a vertex-only profile (the finding of ``mount_probe``'s docstring too). The
  profile therefore reads the SURFACE: a bin's height is the highest (``top``) or lowest (``bottom``) u of the triangles' surface inside the
  side window, exact in s and sampled at ``bin_m / 2`` steps in f, plus every vertex in the window. A triangle with no extent in f (a wall)
  contributes only its vertices; its top edge is also the edge of the neighbouring roof triangle.
* **Teeth** come from a zig-zag extremum scan with hysteresis ``tooth_amp_min_m`` on the populated bins: an extreme counts once it is that far
  from the last opposite one, so a dip shallower than the amplitude floor never splits a tooth. A flat crest is one tooth at the middle of its
  plateau. A tooth needs a trough on both sides (the spec's "above both neighbouring troughs"), so the profile's first and last extremes never
  count. A tooth's amplitude is its top minus the HIGHER of its two troughs. Teeth closer than ``tooth_merge_m`` merge into the taller one.
  An empty bin ends a profile segment; teeth are never paired across a hole.
* **Runs.** A run is a contiguous stretch of teeth whose pitches are in [``pitch_min_m``, ``pitch_max_m``], with ``tooth_min_count`` teeth or
  more, pitch CV (population) ``<= pitch_cv_max``, and tops within ``tooth_h_tol_m`` of the run's median top. The longest such stretch is taken
  (the rearmost on a tie), then the teeth on either side of it are searched again, so a host with two rails reports both. The stored run
  covers whole pitch cells: ``f0``/``f1`` are the first/last tooth centre moved out by half a pitch (each tooth owns its slot; the spec fixes
  no other definition). ``pitch_m`` is the mean pitch, ``amp_m`` the median tooth amplitude, ``top_u`` the median tooth top.
* **Zone.** ``zone`` is a fraction of the f extent of ``verts_fsu`` as given, measured from the butt (lowest f). A run counts if it OVERLAPS
  the zone. A flat seat must be at least ``flat.min_m`` long INSIDE the zone, so its bins are limited to the zone before runs are formed.
* **Flat run.** "Within ``band_m`` of their running top" is read as: a run's flat bins all lie within ``band_m`` below one top level (the run's
  max minus its min is at most ``band_m``), so a ramp never counts. Bins off that band, or empty, are gaps; gaps up to ``close_m`` are bridged.
  Every bin height is tried as the top level and the longest run wins (the rearmost on a tie).
* **Bottom** is the exact mirror of top: u is negated, so "outward" is up in the working frame, and ``top_u`` is negated back.
* Stored floats are rounded to 1e-4 m (spec 4.3). Every comparison against a rule value uses the unrounded measure.

Determinism (spec 4.3): vertices are sorted lexicographically and bins use integer indices, ``floor(x / bin_m + 1e-6)`` (the epsilon absorbs the
division's float error; bin boundaries sit on multiples of ``bin_m`` from f = 0, not from the host's minimum). No set or dict order reaches
the output.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

import numpy as np

from .fit_types import RailRun

_SUB = 2  # f samples per bin (a bin is never read from a single sample)
_EPS_BIN = 1e-6  # added to x / bin_m before floor: absorbs float error of the division (~1e-9 at 1e3 bins)
_EPS_M = 1e-9  # comparison slack, metres: rule edges are exact in the spec, floats are not
_PLATEAU_M = 1e-5  # heights within 10 um are one plateau (a flat crest of a real mesh is not bit-equal)
_SEAT_BAND_M = 0.001  # step 2: width_m is the side extent of the run's top within 1 mm below top_u
_JOIN_M = 1e-6  # side intervals closer than 1 um are one (shared triangle edges)
_CHUNK = 1_500_000  # surface samples built per numpy block


def _prepare(verts_fsu, tris, side):
    """Working copy: float (N, 3), int (M, 3). Vertices sorted lexicographically (f, s, u), triangles remapped and sorted, u negated
    for ``bottom`` (the working frame always has "outward" as +u)."""
    v = np.asarray(verts_fsu, dtype=np.float64).reshape(-1, 3)
    t = np.asarray(tris, dtype=np.int64).reshape(-1, 3)
    if len(v) == 0:
        return v, t[:0]
    order = np.lexsort((v[:, 2], v[:, 1], v[:, 0]))
    rank = np.empty(len(v), dtype=np.int64)
    rank[order] = np.arange(len(v))
    v = v[order].copy()
    t = rank[t] if len(t) else t
    if len(t):
        t = t[np.lexsort((t[:, 2], t[:, 1], t[:, 0]))]
    if side == "bottom":
        v[:, 2] = -v[:, 2]
    return v, t


def _bin_of(x, bin_m):
    return np.floor(np.asarray(x) / bin_m + _EPS_BIN).astype(np.int64)


def _profile(v, t, s0, rules_rail):
    """Spec 3.4 step 1: ``(b0, h)``: ``h[i]`` is the highest u of the surface within ``window_m`` of ``s0`` in bin ``b0 + i``, -inf where
    nothing is there."""
    bin_m = float(rules_rail["bin_m"])
    w = float(rules_rail["window_m"])
    lo, hi = s0 - w - _EPS_M, s0 + w + _EPS_M
    b_all = _bin_of(v[:, 0], bin_m)
    b0, b1 = int(b_all.min()), int(b_all.max())
    h = np.full(b1 - b0 + 1, -np.inf)
    # the vertices inside the window
    vm = (v[:, 1] >= lo) & (v[:, 1] <= hi)
    np.maximum.at(h, b_all[vm] - b0, v[vm, 2])
    if len(t) == 0:
        return b0, h
    step = bin_m / _SUB
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    fmin = np.minimum(np.minimum(a[:, 0], b[:, 0]), c[:, 0])
    fmax = np.maximum(np.maximum(a[:, 0], b[:, 0]), c[:, 0])
    smin = np.minimum(np.minimum(a[:, 1], b[:, 1]), c[:, 1])
    smax = np.maximum(np.maximum(a[:, 1], b[:, 1]), c[:, 1])
    k0 = np.ceil(fmin / step - _EPS_BIN).astype(np.int64)
    k1 = np.floor(fmax / step + _EPS_BIN).astype(np.int64)
    cnt = np.where((smax >= lo) & (smin <= hi) & (fmax > fmin), np.maximum(k1 - k0 + 1, 0), 0)
    todo = np.flatnonzero(cnt > 0)
    start = 0
    while start < len(todo):
        # a chunk of triangles whose samples fit the block (at least one triangle)
        csum = np.cumsum(cnt[todo[start:]])
        n_tri = max(1, int(np.searchsorted(csum, _CHUNK, side="right")))
        idx = todo[start : start + n_tri]
        start += n_tri
        n = cnt[idx]
        tri = np.repeat(idx, n)
        offs = np.cumsum(n) - n
        k = np.repeat(k0[idx], n) + (np.arange(int(n.sum())) - np.repeat(offs, n))
        _slice_max(h, b0, a[tri], b[tri], c[tri], k, step, lo, hi)
    return b0, h


def _slice_max(h, b0, a, b, c, k, step, lo, hi):
    """Add to ``h`` the highest u in the window of each slice of a triangle (corners ``a``, ``b``, ``c``) at f = ``k * step``. A slice is a
    segment between two edge crossings and u is linear on it, so its maximum in the window is at a crossing inside the window or where
    the segment enters it."""
    f = k * step
    n = len(f)
    cs = np.full((3, n), np.nan)
    cu = np.zeros((3, n))
    for j, (p, q) in enumerate(((a, b), (b, c), (c, a))):
        df = q[:, 0] - p[:, 0]
        ok = (np.minimum(p[:, 0], q[:, 0]) <= f) & (f <= np.maximum(p[:, 0], q[:, 0])) & (df != 0)
        with np.errstate(divide="ignore", invalid="ignore"):
            tt = (f - p[:, 0]) / df  # inf / nan where the edge has no extent in f; those rows are masked by ``ok``
            cs[j] = np.where(ok, p[:, 1] + tt * (q[:, 1] - p[:, 1]), np.nan)
            cu[j] = np.where(ok, p[:, 2] + tt * (q[:, 2] - p[:, 2]), np.nan)
    have = ~np.isnan(cs)
    jp = np.argmin(np.where(have, cs, np.inf), axis=0)
    jq = np.argmax(np.where(have, cs, -np.inf), axis=0)
    col = np.arange(n)
    sp, up, sq, uq = cs[jp, col], cu[jp, col], cs[jq, col], cu[jq, col]
    good = have.any(axis=0)
    best = np.full(n, -np.inf)
    best = np.where(good & (sp >= lo) & (sp <= hi), np.maximum(best, up), best)
    best = np.where(good & (sq >= lo) & (sq <= hi), np.maximum(best, uq), best)
    span = np.where(good, sq - sp, 0.0)
    for edge in (lo, hi):  # the segment enters / leaves the window across a side plane
        cross = good & (span > 0) & (sp < edge) & (edge < sq)
        with np.errstate(divide="ignore", invalid="ignore"):
            ue = up + (edge - sp) / span * (uq - up)
        best = np.where(cross, np.maximum(best, ue), best)
    np.maximum.at(h, (k // _SUB) - b0, best)


def _zigzag(seg, amp):
    """Alternating extremes of the heights ``seg`` (a populated stretch) with hysteresis ``amp``: ``[(kind, value, i0, i1), ...]`` where
    ``i0..i1`` is the plateau of the extreme. The last tracked extreme is included (it may lack the opposite one beyond it)."""
    amp = amp - _EPS_M
    piv = []
    hi = lo = float(seg[0])
    hi0 = hi1 = lo0 = lo1 = 0
    mode = 0  # 0 undecided, +1 tracking a maximum (rising), -1 tracking a minimum (falling)
    cur = 0.0
    c0 = c1 = 0
    for i in range(1, len(seg)):
        x = float(seg[i])
        if mode == 0:
            if x > hi + _PLATEAU_M:
                hi, hi0, hi1 = x, i, i
            elif abs(x - hi) <= _PLATEAU_M:
                hi1 = i
            if x < lo - _PLATEAU_M:
                lo, lo0, lo1 = x, i, i
            elif abs(x - lo) <= _PLATEAU_M:
                lo1 = i
            if hi - lo >= amp:
                if hi0 > lo0:  # the minimum came first: now tracking the maximum
                    piv.append(("min", lo, lo0, lo1))
                    mode, cur, c0, c1 = 1, hi, hi0, hi1
                else:
                    piv.append(("max", hi, hi0, hi1))
                    mode, cur, c0, c1 = -1, lo, lo0, lo1
        elif mode == 1:
            if x > cur + _PLATEAU_M:
                cur, c0, c1 = x, i, i
            elif abs(x - cur) <= _PLATEAU_M:
                c1 = i
            elif cur - x >= amp:
                piv.append(("max", cur, c0, c1))
                mode, cur, c0, c1 = -1, x, i, i
        else:
            if x < cur - _PLATEAU_M:
                cur, c0, c1 = x, i, i
            elif abs(x - cur) <= _PLATEAU_M:
                c1 = i
            elif x - cur >= amp:
                piv.append(("min", cur, c0, c1))
                mode, cur, c0, c1 = 1, x, i, i
    if mode == 1:
        piv.append(("max", cur, c0, c1))
    elif mode == -1:
        piv.append(("min", cur, c0, c1))
    return piv


def _teeth(b0, h, rules_rail):
    """Spec 3.4 step 2: the teeth of the profile, rear to front: ``[(centre_f, top_h, amp), ...]`` (working frame heights)."""
    bin_m = float(rules_rail["bin_m"])
    amp_min = float(rules_rail["tooth_amp_min_m"])
    merge = float(rules_rail["tooth_merge_m"])
    pop = np.isfinite(h)
    teeth = []
    i = 0
    n = len(h)
    while i < n:
        if not pop[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and pop[j + 1]:
            j += 1
        piv = _zigzag(h[i : j + 1], amp_min)
        for q in range(1, len(piv) - 1):
            kind, val, p0, p1 = piv[q]
            if kind != "max":
                continue
            trough = max(piv[q - 1][1], piv[q + 1][1])  # the higher of the two flanking troughs
            centre = (b0 + i + (p0 + p1) / 2.0 + 0.5) * bin_m
            teeth.append((centre, val, val - trough))
        i = j + 1
    # extremes closer than tooth_merge_m merge into the taller (the earlier on a tie)
    merged = []
    for tooth in teeth:
        if merged and tooth[0] - merged[-1][0] < merge - _EPS_M:
            if tooth[1] > merged[-1][1] + _PLATEAU_M:
                merged[-1] = tooth
        else:
            merged.append(tooth)
    return merged


def _valid_run(win, rules_rail):
    """``win``: consecutive teeth. Conditions 2 and 3 of step 2 (the pitch window is checked by the caller's split)."""
    centres = np.array([x[0] for x in win])
    tops = np.array([x[1] for x in win])
    pitches = np.diff(centres)
    mean = float(pitches.mean())
    if mean <= 0 or float(pitches.std()) / mean > float(rules_rail["pitch_cv_max"]) + _EPS_M:
        return False
    return float(np.abs(tops - np.median(tops)).max()) <= float(rules_rail["tooth_h_tol_m"]) + _EPS_M


def _find_runs(teeth, rules_rail):
    """Teeth lists of every toothed run: split at pitches outside the window, then take the longest valid stretch of each piece (the rearmost
    on a tie) and search the remainder on both sides again."""
    pmin, pmax = float(rules_rail["pitch_min_m"]), float(rules_rail["pitch_max_m"])
    need = int(rules_rail["tooth_min_count"])
    pieces, cur = [], []
    for tooth in teeth:
        if cur and not (pmin - _EPS_M <= tooth[0] - cur[-1][0] <= pmax + _EPS_M):
            pieces.append(cur)
            cur = []
        cur.append(tooth)
    if cur:
        pieces.append(cur)
    out = []
    todo = list(reversed(pieces))
    while todo:
        piece = todo.pop()
        found = None
        for length in range(len(piece), need - 1, -1):
            for st in range(len(piece) - length + 1):
                if _valid_run(piece[st : st + length], rules_rail):
                    found = (st, length)
                    break
            if found:
                break
        if found:
            st, length = found
            out.append(piece[st : st + length])
            todo.append(piece[st + length :])  # the order of `out` is fixed by the sort below
            todo.append(piece[:st])
    out.sort(key=lambda r: r[0][0])
    return out


def _side_width(v, t, f0, f1, top_h, s0):
    """Side extent of the surface in ``f0..f1`` and within ``_SEAT_BAND_M`` below ``top_h`` (working frame, no upper cut), taken over the
    stretch of side coordinates that is connected to ``s0``. Exact: each triangle's polygon is clipped to the slab and contributes its
    side interval."""
    if len(t) == 0:
        return 0.0
    floor_h = top_h - _SEAT_BAND_M
    p = v[t]  # (M, 3, 3)
    keep = (p[:, :, 0].max(axis=1) >= f0) & (p[:, :, 0].min(axis=1) <= f1) & (p[:, :, 2].max(axis=1) >= floor_h)
    spans = []
    for tri in p[keep]:
        poly = [tuple(x) for x in tri]
        for axis, bound, sign in ((0, f0, 1.0), (0, f1, -1.0), (2, floor_h, 1.0)):
            poly = _clip(poly, axis, bound, sign)
            if not poly:
                break
        if poly:
            ss = [q[1] for q in poly]
            spans.append((min(ss), max(ss)))
    if not spans:
        return 0.0
    spans.sort()
    joined = [list(spans[0])]
    for lo, hi in spans[1:]:
        if lo <= joined[-1][1] + _JOIN_M:
            joined[-1][1] = max(joined[-1][1], hi)
        else:
            joined.append([lo, hi])

    def away(iv):  # distance of s0 from the interval: 0 when s0 is inside
        return 0.0 if iv[0] - _JOIN_M <= s0 <= iv[1] + _JOIN_M else min(abs(s0 - iv[0]), abs(s0 - iv[1]))

    pick = min(joined, key=lambda iv: (away(iv), iv[0]))
    return float(pick[1] - pick[0])


def _clip(poly, axis, bound, sign):
    """Sutherland-Hodgman against ``sign * (x[axis] - bound) >= 0``."""
    out = []
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        dp, dq = sign * (p[axis] - bound), sign * (q[axis] - bound)
        if dp >= 0:
            out.append(p)
        if (dp >= 0) != (dq >= 0):
            r = dp / (dp - dq)
            out.append(tuple(p[x] + r * (q[x] - p[x]) for x in range(3)))
    return out


def _zone(v, rules_rail):
    zlo, zhi = (float(x) for x in rules_rail["zone"])
    f_lo, f_hi = float(v[:, 0].min()), float(v[:, 0].max())
    length = f_hi - f_lo
    return f_lo + zlo * length, f_lo + zhi * length


def _toothed_runs(v, t, s0, rules, sign):
    """The runs of ``rail_runs`` on a prepared (sorted, u-signed) mesh; ``sign`` turns working heights back into the host's u."""
    if len(v) == 0:
        return []
    rr = rules["rail"]
    b0, h = _profile(v, t, s0, rr)
    z0, z1 = _zone(v, rr)
    out = []
    for run in _find_runs(_teeth(b0, h, rr), rr):
        centres = np.array([x[0] for x in run])
        tops = np.array([x[1] for x in run])
        pitch = float((centres[-1] - centres[0]) / (len(run) - 1))
        f0, f1 = float(centres[0]) - pitch / 2.0, float(centres[-1]) + pitch / 2.0
        if f1 < z0 - _EPS_M or f0 > z1 + _EPS_M:  # must overlap the zone
            continue
        top = float(np.median(tops))
        out.append(
            RailRun(
                f0=round(f0, 4),
                f1=round(f1, 4),
                top_u=round(sign * top, 4) + 0.0,
                pitch_m=round(pitch, 4),
                amp_m=round(float(np.median([x[2] for x in run])), 4),
                teeth=len(run),
                width_m=round(_side_width(v, t, f0, f1, top, s0), 4),
                toothed=True,
            )
        )
    return out


def rail_runs(verts_fsu, tris, side: Literal["top", "bottom"], s0: float, rules: dict) -> list[RailRun]:
    """Spec 3.4 steps 1 and 2: the toothed runs of the host's top or bottom profile, in (f, s, u) coordinates, rear to front.

    ``s0`` is the centreline side coordinate (the muzzle seat's, or the middle of the side extent; the caller decides). ``side`` is "top" (the
    highest u per bin) or "bottom" (the lowest u per bin; ``RailRun.top_u`` is then the lowest u of the run's teeth, a signed host coordinate).
    The result is empty when no toothed run overlaps the zone. See the module docstring for the readings."""
    if side not in ("top", "bottom"):
        raise ValueError(f"side must be 'top' or 'bottom', not {side!r}")
    v, t = _prepare(verts_fsu, tris, side)
    return _toothed_runs(v, t, float(s0), rules, 1.0 if side == "top" else -1.0)


def flat_seat(verts_fsu, tris, s0: float, rules: dict) -> RailRun | None:
    """Spec 3.4 step 3: the untoothed fallback, the longest flat top run (``toothed`` False, ``pitch_m``/``amp_m``/``teeth`` 0), or None.

    None as well when the host has a toothed top run (``rail_runs`` finds one): only an untoothed host takes the fallback. ``f0``/``f1`` are
    the run's extent inside the zone; ``top_u`` is the highest u of the run; ``width_m`` is measured as for a toothed run."""
    v, t = _prepare(verts_fsu, tris, "top")
    if len(v) == 0:
        return None
    if _toothed_runs(v, t, float(s0), rules, 1.0):
        return None
    rr, fl = rules["rail"], rules["flat"]
    bin_m = float(rr["bin_m"])
    band, close, min_m = float(fl["band_m"]), float(fl["close_m"]), float(fl["min_m"])
    b0, h = _profile(v, t, float(s0), rr)
    z0, z1 = _zone(v, rr)
    centre = (b0 + np.arange(len(h)) + 0.5) * bin_m
    hz = np.where(np.isfinite(h) & (centre >= z0 - _EPS_M) & (centre <= z1 + _EPS_M), h, -np.inf)
    levels = np.unique(hz[np.isfinite(hz)])
    max_gap = int(np.floor(close / bin_m + _EPS_BIN))  # bins that may be bridged
    min_bins = int(np.ceil(min_m / bin_m - _EPS_BIN))
    best = None  # (n_bins, -first bin, level, first, last)
    for level in levels:
        flat = np.flatnonzero((hz <= level + _PLATEAU_M) & (hz >= level - band - _EPS_M))
        if len(flat) == 0:
            continue
        cut = np.flatnonzero(np.diff(flat) - 1 > max_gap) + 1
        for part in np.split(flat, cut):
            n_bins = int(part[-1] - part[0]) + 1
            key = (n_bins, -int(part[0]), float(level))
            if best is None or key > best[:3]:
                best = key + (int(part[0]), int(part[-1]))
    if best is None or best[0] < min_bins:
        return None
    first, last = best[3], best[4]
    run_h = hz[first : last + 1]
    top = float(run_h[(run_h >= best[2] - band - _EPS_M) & (run_h <= best[2] + _PLATEAU_M)].max())
    f0, f1 = (b0 + first) * bin_m, (b0 + last + 1) * bin_m
    return RailRun(
        f0=round(f0, 4),
        f1=round(f1, 4),
        top_u=round(top, 4) + 0.0,
        pitch_m=0.0,
        amp_m=0.0,
        teeth=0,
        width_m=round(_side_width(v, t, f0, f1, top, float(s0)), 4),
        toothed=False,
    )


def clip_run(run: RailRun, sight_front_f: float, sight_clear_m: float) -> RailRun | None:
    """Spec 3.4 step 4, sight seats: end the run ``sight_clear_m`` behind a front sight at f = ``sight_front_f``, so an optic span never
    covers it. Returns ``run`` unchanged when it already ends that far behind the sight, a copy with a shorter ``f1`` otherwise, and None when
    nothing is left (the run starts at or beyond the clip, or lies wholly ahead of the sight). Only ``f1`` changes; the measures of the
    detected run (``teeth``, ``pitch_m``, ``amp_m``, ``width_m``) stay those of the run the detector found."""
    f1 = round(min(run.f1, sight_front_f - sight_clear_m), 4)
    if f1 <= run.f0:
        return None
    return run if f1 >= run.f1 else replace(run, f1=f1)


def seat_point(run: RailRun, default_seat_len_m: float) -> tuple[float, float]:
    """Spec 3.4 step 4: the seat point ``(f, u)``, the centre of the rearmost ``min(run length, default_seat_len_m)`` of the run, at
    ``run.top_u``. A ``RailRun`` carries no side coordinate, so the caller adds ``s`` (the centreline it passed to the detector). Metres,
    rounded to 1e-4."""
    seat_len = min(run.f1 - run.f0, default_seat_len_m)
    return round(run.f0 + seat_len / 2.0, 4), run.top_u
