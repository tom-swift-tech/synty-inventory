"""Attachment anchors, footprints and the placement math (docs/weapon_attachments.md 3.1 and 3.4).

Pure functions over a vertex array: no files, no clock, no changing globals. ``measure_anchor`` gives the contact frame
``{point, forward, up}`` of one mesh (a part's selected node, and from W8b a host's child mesh) plus its footprint;
``place`` is the placement transform ``T(mount) * T(anchor)^-1`` of section 3.1. All numbers are asset-local metres in
GLB scene space after ``glb_scale``, rounded to 1e-4 with ``-0.0`` normalised so the cache round-trip cannot change a byte.

The authored axes of Synty parts are Y-up: the contact side is taken from the slot along Y and checked by the number of
distinct points in the foot slab (fewer than three is a point or an edge, not a foot; then the other end is tried). The
along-rail axis is the longer horizontal AABB axis, so a part yawed by a multiple of 90 degrees measures like the
original; an arbitrary yaw or tilt is outside this prior.
"""

from __future__ import annotations

import re

import numpy as np

_MIN_POINTS = 3  # distinct points (0.1 mm dedupe) a slab or a face needs
_DEDUPE_M = 1e-4
_WINDOW_FRAC = 0.25  # outer share of the length whose cross-section decides a sign (spec 3.4 step 3)
_SYMMETRIC_RATIO = 1.15  # larger/smaller end section below this: the sign is a coin flip
_MATE_TOLS_M = (0.001, 0.002, 0.005, 0.010)  # mating-face tolerances, as the A0 muzzle probe (geometry._MUZZLE_TOLS_M)
_EPS = 1e-9
_AXES = "xyz"
_SIGNED_AXIS_RE = re.compile(r"^[+-][xyz]$")
_RAIL_SLOTS = ("optic", "underbarrel")  # A4 1b (errata E3-Q7): the foot rung must hold the mid-line on these slots only; the others keep their 1a footprint
_FOOT_AT_BOTTOM = ("optic", "laser_light", "sight_front", "sight_rear")  # the others hang from a +Y foot; the sights stand on the receiver like an optic (A2)

# A4 (W8l): the numbers of attachment_rules.anchor (spec 3.4 steps 1a and 3b). The build threads the table of the rules in force; these are
# the same numbers for a caller that passes none (the shipped weapon_rules.yaml carries them, a test pins the two equal). Parameters, not contract.
DEFAULT_ANCHOR_PARAMS = {
    "foot_depths_m": [0.004, 0.008, 0.016],  # step 1 slab, then the two rungs of the lip ladder (1a)
    "lip_min_m": 0.001,  # a slab extent below this is a line contact (a flashlight), not a lip
    "lip_max_m": 0.0045,  # a slab extent up to this can be a lip: the slab is cutting a ridge, a rim or a stub
    "lip_growth": 2.0,  # ... when the next rung is at least this many times as large on that axis
    "free_end": {"min_displacement_m": 0.010, "kinds": {"magazine": ["standard"], "underbarrel": ["bipod"]}},  # 3b
}


def _r(x) -> float:
    return round(float(x), 4) + 0.0


def _vec(a) -> list[float]:
    return [_r(c) for c in a]


def _unit(axis: int, sign: int = 1) -> np.ndarray:
    v = np.zeros(3)
    v[axis] = sign
    return v


def _distinct(points: np.ndarray) -> np.ndarray:
    if not len(points):
        return points
    cells = np.floor(points / _DEDUPE_M + 0.5).astype(np.int64)
    _, first = np.unique(cells, axis=0, return_index=True)
    return points[np.sort(first)]


def _section(points: np.ndarray, axis: int) -> float:
    lat = [i for i in range(3) if i != axis]
    ext = points[:, lat].max(axis=0) - points[:, lat].min(axis=0)
    return float(ext[0] * ext[1])


def _end_sections(v: np.ndarray, axis: int) -> tuple[float, float]:
    lo, hi = float(v[:, axis].min()), float(v[:, axis].max())
    win = _WINDOW_FRAC * (hi - lo)
    return (_section(v[v[:, axis] <= lo + win + _EPS], axis), _section(v[v[:, axis] >= hi - win - _EPS], axis))


def _end_sign(a_lo: float, a_hi: float) -> tuple[int, bool]:
    big, small = max(a_lo, a_hi), min(a_lo, a_hi)
    ratio = (big / small) if small > 1e-12 else (float("inf") if big > 1e-12 else 1.0)
    if ratio < _SYMMETRIC_RATIO:
        return 1, False
    return (1 if a_hi > a_lo else -1), True


def _override_sign(forward_override, axis: int):
    if forward_override is None or not _SIGNED_AXIS_RE.match(forward_override):
        return None
    if _AXES.index(forward_override[1]) != axis:
        return None
    return 1 if forward_override[0] == "+" else -1


def _extent(points: np.ndarray, direction: np.ndarray) -> float:
    proj = points @ direction
    return float(proj.max() - proj.min())


def _unmeasured() -> dict:
    return {"anchor": None, "footprint": None, "reasons": ["anchor_unmeasured"]}


def _result(point, forward, up, foot_source, forward_source, symmetric, v, foot, mate_d=None) -> dict:
    right = np.cross(up, forward)
    reasons = ["anchor_forward_unsure"] if symmetric else []
    return {
        "anchor": {
            "point": _vec(point), "forward": _vec(forward), "up": _vec(up),
            "foot_source": foot_source, "forward_source": forward_source, "symmetric": bool(symmetric),
        },
        "footprint": {
            "length_m": _r(_extent(v, forward)), "width_m": _r(_extent(v, right)), "height_m": _r(_extent(v, up)),
            "foot_length_m": _r(_extent(foot, forward)), "foot_width_m": _r(_extent(foot, right)),
            "mate_d_m": None if mate_d is None else _r(mate_d),
        },
        "reasons": reasons,
    }


def _slab(v: np.ndarray, low: bool, depth: float) -> np.ndarray:
    y = v[:, 1]
    return v[y <= float(y.min()) + depth + _EPS] if low else v[y >= float(y.max()) - depth - _EPS]


def _is_lip(slab: np.ndarray, deeper: np.ndarray, axes: tuple[int, ...], p: dict) -> bool:
    """Spec 3.4 step 1a: some axis of ``slab`` is a lip, i.e. thin but not a line (``lip_min_m`` .. ``lip_max_m``) AND the next rung is at
    least ``lip_growth`` times as large on that axis. A thin foot that stays thin (an iron-sight post) is a foot; a line contact has extent 0."""
    for a in axes:
        e = float(slab[:, a].max() - slab[:, a].min())
        e_next = float(deeper[:, a].max() - deeper[:, a].min())
        if p["lip_min_m"] - _EPS <= e <= p["lip_max_m"] + _EPS and e_next >= p["lip_growth"] * e - _EPS:
            return True
    return False


def _foot_slab(v: np.ndarray, low: bool, axis: int, p: dict, slot: str | None = None) -> np.ndarray:
    """The slab of the first rung of ``foot_depths_m`` that is not a lip along ``forward`` (``axis``) or ``right`` (the other horizontal axis).

    Spec 3.4 step 1b (errata E3.7), on the rail slots only: a rung also has to hold the part's mid-line, the line through the centre of the whole
    extent of ``v`` along ``right``; a rung whose slab misses it is a side feature (a hook, a lug), so the ladder starts at the first rung that
    holds it. The rungs nest (each slab contains the one before), so the rungs that hold the mid-line are the deeper ones; the lip rule then runs
    from that rung exactly as in 1a, against the next rung of the ladder. When no rung holds the mid-line, or the slot is not a rail slot, the
    1a ladder is unchanged.
    """
    depths = p["foot_depths_m"]
    right = 0 if axis == 2 else 2
    rung = 0
    if slot in _RAIL_SLOTS:
        mid = (float(v[:, right].min()) + float(v[:, right].max())) / 2.0
        for i, depth in enumerate(depths):
            s = _slab(v, low, depth)
            if float(s[:, right].min()) - _EPS <= mid <= float(s[:, right].max()) + _EPS:
                rung = i
                break
    slab = _slab(v, low, depths[rung])
    while rung + 1 < len(depths):
        deeper = _slab(v, low, depths[rung + 1])
        if not _is_lip(slab, deeper, (axis, right), p):
            break
        slab, rung = deeper, rung + 1
    return slab


def _free_end_sign(v: np.ndarray, slab: np.ndarray, low: bool, axis: int, p: dict) -> int | None:
    """Spec 3.4 step 3b: +1 / -1 for the side of ``axis`` that the free end leans to, or None below ``min_displacement_m``.

    The free end is the outer ``_WINDOW_FRAC`` of the extent along ``up`` at the end away from the foot; the displacement is the midpoint of its
    AABB along ``axis`` minus the midpoint of the foot slab's AABB (the slab the ladder chose) along the same axis.
    """
    y = v[:, 1]
    lo, hi = float(y.min()), float(y.max())
    win = _WINDOW_FRAC * (hi - lo)
    free = v[y >= hi - win - _EPS] if low else v[y <= lo + win + _EPS]
    disp = (float(free[:, axis].min()) + float(free[:, axis].max())) / 2.0 - (float(slab[:, axis].min()) + float(slab[:, axis].max())) / 2.0
    if abs(disp) < p["free_end"]["min_displacement_m"] - _EPS:
        return None
    return 1 if disp > 0 else -1


def _slab_centre(slab: np.ndarray, low: bool) -> np.ndarray:
    lo, hi = slab.min(axis=0), slab.max(axis=0)
    return np.array([(lo[0] + hi[0]) / 2.0, lo[1] if low else hi[1], (lo[2] + hi[2]) / 2.0])


def _foot_anchor(v: np.ndarray, slot: str, forward_override, kind, p: dict) -> dict:
    expected_low = slot in _FOOT_AT_BOTTOM
    for attempt, low in enumerate((expected_low, not expected_low)):
        slab = _slab(v, low, p["foot_depths_m"][0])
        if len(_distinct(slab)) >= _MIN_POINTS:
            break
    else:
        return _unmeasured()
    foot_source = "authored_up" if attempt == 0 else "measured"
    up = _unit(1, 1 if low else -1)
    ext = v.max(axis=0) - v.min(axis=0)
    axis = 2 if ext[2] >= ext[0] else 0
    slab = _foot_slab(v, low, axis, p, slot)  # A4 item 3: one rung deeper when the 4 mm slab only cut a lip; 1b: skip a rung off the mid-line (rail slots)
    sign, decided = _end_sign(*_end_sections(v, axis))
    forward_source, symmetric = ("section", False) if decided else ("authored", True)
    if kind in (p["free_end"].get("kinds") or {}).get(slot, ()):  # A4 item 1: the pairs of attachment_rules.anchor.free_end only
        leaning = _free_end_sign(v, slab, low, axis, p)
        if leaning is not None:
            sign, forward_source, symmetric = leaning, "free_end", False
    forced = _override_sign(forward_override, axis)
    if forced is not None:
        sign, forward_source, symmetric = forced, "override", False
    return _result(_slab_centre(slab, low), _unit(axis, sign), up, foot_source, forward_source, symmetric, v, slab)


def _muzzle_anchor(v: np.ndarray, forward_override) -> dict:
    ext = v.max(axis=0) - v.min(axis=0)
    axis = max((2, 1, 0), key=lambda a: ext[a])
    a_lo, a_hi = _end_sections(v, axis)
    sign, decided = _end_sign(a_lo, a_hi)
    forward_source, symmetric = "authored", not decided
    forced = _override_sign(forward_override, axis)
    if forced is not None:
        sign, forward_source, symmetric = forced, "override", False
    up = _unit(axis, sign)
    mating_low = sign > 0
    coord = v[:, axis]
    extreme = float(coord.min() if mating_low else coord.max())
    for tol in _MATE_TOLS_M:
        face = _distinct(v[(coord <= extreme + tol + _EPS) if mating_low else (coord >= extreme - tol - _EPS)])
        if len(face) >= _MIN_POINTS:
            break
    else:
        return _unmeasured()
    lat = [i for i in range(3) if i != axis]
    centre = face[:, lat].mean(axis=0)
    mate_d = 2.0 * float(np.linalg.norm(face[:, lat] - centre, axis=1).mean())
    point = np.zeros(3)
    point[lat], point[axis] = centre, extreme
    roll = _unit(1) - float(up[1]) * up
    norm = float(np.linalg.norm(roll))
    forward = roll / norm if norm > 1e-6 else _unit(2)
    return _result(point, forward, up, "measured", forward_source, symmetric, v, face, mate_d)


def measure_anchor(vertices, slot: str, forward_override=None, kind: str | None = None, params: dict | None = None) -> dict:
    """The anchor and footprint of one mesh (spec 3.4). ``kind`` (A4, item 1) is the part's kind within ``slot``: only a part measures with it,
    a host's baked child is measured without (it keeps step 3). ``params`` is ``attachment_rules.anchor`` (default: ``DEFAULT_ANCHOR_PARAMS``)."""
    v = np.asarray(vertices, dtype=np.float64).reshape(-1, 3)
    if not len(v):
        return _unmeasured()
    if slot == "muzzle":
        return _muzzle_anchor(v, forward_override)
    return _foot_anchor(v, slot, forward_override, kind, params or DEFAULT_ANCHOR_PARAMS)


def frame_matrix(frame: dict) -> np.ndarray:
    forward = np.asarray(frame["forward"], dtype=np.float64)
    up = np.asarray(frame["up"], dtype=np.float64)
    m = np.eye(4)
    m[:3, 0], m[:3, 1], m[:3, 2] = np.cross(up, forward), up, forward
    m[:3, 3] = np.asarray(frame["point"], dtype=np.float64)
    return m


def _rigid_inverse(m: np.ndarray) -> np.ndarray:
    inv = np.eye(4)
    inv[:3, :3] = m[:3, :3].T
    inv[:3, 3] = -m[:3, :3].T @ m[:3, 3]
    return inv


def place(anchor: dict, mount: dict) -> np.ndarray:
    return frame_matrix(mount) @ _rigid_inverse(frame_matrix(anchor))


# -- the hidden nodes and settle to contact (A5, W8m; spec 4.3 and 5.4) ---------------------------------------------------


def hidden_nodes(mounts: dict, slot: str, entry: dict | None) -> list[str]:
    """The host nodes a pair does not draw (and settle to contact does not count): every node of the slot's ``occupied_by`` plus its
    ``child_node`` for EVERY pair (E1: the runtime hides the whole slot whichever child the part is seated on), and the same of each slot in the
    entry's ``hides_slots`` (A2, 4.3: the rear sight an optic covers). One source of truth for ``preview.build_job`` and the contact post-pass."""

    def slot_nodes(m: dict) -> set[str]:
        return set(m.get("occupied_by") or []) | ({m["child_node"]} if m.get("child_node") else set())

    hide = slot_nodes(mounts[slot])
    for hidden in (entry or {}).get("hides_slots") or []:
        hide |= slot_nodes(mounts.get(hidden) or {})
    return sorted(hide)


_SETTLE_AXIS_COS = float(np.cos(np.radians(1.0)))  # a mount's up counts as axis-aligned within 1 degree (5.4 (e))
_SETTLE_OFFSET_M = (1.37e-5, 0.93e-5)  # lateral ray offset: no ray runs exactly along a triangle edge or a box side
_SETTLE_BUDGET = 1 << 21  # (sample, triangle) pairs held at once


def up_axis(up) -> tuple[int, int] | None:
    """``(axis index, sign)`` of a mount's ``up`` when it is within 1 degree of a coordinate axis, else None."""
    if up is None:
        return None
    u = np.asarray(up, dtype=np.float64).reshape(-1)
    n = float(np.linalg.norm(u)) if u.shape == (3,) else 0.0
    if not np.isfinite(n) or n < _EPS:
        return None
    a = int(np.argmax(np.abs(u)))
    return (a, 1 if u[a] > 0 else -1) if abs(float(u[a])) / n >= _SETTLE_AXIS_COS else None


def settle_applies(slot: str, mount: dict | None, tier: str, anchor: dict | None, params: dict) -> bool:
    """Which pairs get a ``seat_shift_m`` (5.4 "Which pairs"): a slot of ``contact.slots`` whose host mount is a real seat (a, not ``none``), not an
    authored one (b, source not ``override``), whose entry is not authored either (c, tier not ``twin`` or ``override``), with a measured anchor (d)
    and an axis-aligned ``up`` (e)."""
    if slot not in params["slots"] or anchor is None or tier in ("twin", "override"):
        return False
    if mount is None or mount.get("source") in (None, "none", "override") or mount.get("point") is None:
        return False
    return up_axis(mount.get("up")) is not None


def settle_pair(samples, host_v, host_t, up, params: dict) -> tuple[float | None, float | None]:
    """``(d, seat_shift_m)`` of one pair (5.4); ``(None, None)`` when nothing counts, ``(d, None)`` when ``|d|`` is inside the dead zone.

    ``samples`` are the part's surface samples (``mount_probe.surface_samples``) already carried through the placement into the host's space;
    ``host_v`` / ``host_t`` are the host's render triangles; ``up`` is the mount's ``up`` (``u``: the host lies along ``-u`` from the part);
    ``params`` is ``attachment_rules.contact``. The contact face is the samples within ``slab_m`` of the part's extreme along ``-u``. Each face
    sample casts a line along ``u`` (offset across it by ``_SETTLE_OFFSET_M``) at the host triangles; the OUTER surface is the hit with the
    greatest coordinate along ``u`` (not the nearest: a hollow tube has surfaces inside), and ``s = p.u - h.u`` is positive for a gap, negative
    for a part sunk in. A sample with no hit or ``|s|`` over ``reach_m`` is ignored. ``d`` is the MINIMUM ``s`` (the sample that touches first);
    ``seat_shift_m = -clamp(d)`` rounded to 1e-4, moving a gap toward the host (negative) and a sunk part away (positive).
    """
    axis = up_axis(up)
    p = np.asarray(samples, dtype=np.float64).reshape(-1, 3)
    v = np.asarray(host_v, dtype=np.float64).reshape(-1, 3)
    t = np.asarray(host_t, dtype=np.int64).reshape(-1, 3)
    if axis is None or not len(p) or not len(t):
        return None, None
    a, sign = axis
    lat = [i for i in range(3) if i != a]
    along = sign * p[:, a]
    face = p[along <= along.min() + params["slab_m"] + _EPS]
    face_c = sign * face[:, a]
    q = face[:, lat] + np.asarray(_SETTLE_OFFSET_M)
    order = np.lexsort((q[:, 1], q[:, 0]))  # strips of neighbours: each chunk's bounding box stays small, so its triangle prefilter bites
    q, face_c = q[order], face_c[order]

    tri = v[t]
    A, B, C = tri[:, 0][:, lat], tri[:, 1][:, lat], tri[:, 2][:, lat]
    den = (B[:, 1] - C[:, 1]) * (A[:, 0] - C[:, 0]) + (C[:, 0] - B[:, 0]) * (A[:, 1] - C[:, 1])
    keep = np.abs(den) > 1e-14  # a triangle edge-on to the cast is a line, not a surface
    if not keep.any():
        return None, None
    A, B, C, den = A[keep], B[keep], C[keep], den[keep]
    hc = sign * tri[keep][:, :, a]
    lo, hi = np.minimum(np.minimum(A, B), C), np.maximum(np.maximum(A, B), C)
    top = np.full(len(q), -np.inf)
    step = max(1, min(256, _SETTLE_BUDGET // len(den)))
    for i in range(0, len(q), step):
        qc = q[i:i + step]
        near = ((hi >= qc.min(axis=0)) & (lo <= qc.max(axis=0))).all(axis=1)
        if not near.any():
            continue
        a_, b_, c_, d_, h_ = A[near], B[near], C[near], den[near], hc[near]
        qa, qb = qc[:, 0:1], qc[:, 1:2]
        l1 = ((b_[:, 1] - c_[:, 1]) * (qa - c_[:, 0]) + (c_[:, 0] - b_[:, 0]) * (qb - c_[:, 1])) / d_
        l2 = ((c_[:, 1] - a_[:, 1]) * (qa - c_[:, 0]) + (a_[:, 0] - c_[:, 0]) * (qb - c_[:, 1])) / d_
        l3 = 1.0 - l1 - l2
        h = l1 * h_[:, 0] + l2 * h_[:, 1] + l3 * h_[:, 2]
        top[i:i + step] = np.where((l1 >= 0) & (l2 >= 0) & (l3 >= 0), h, -np.inf).max(axis=1)
    s = face_c - top
    counts = np.isfinite(top) & (np.abs(s) <= params["reach_m"])
    if not counts.any():
        return None, None
    d = float(s[counts].min())
    if abs(d) <= params["dead_m"]:
        return d, None
    shift = _r(-min(max(d, -params["clamp_m"]), params["clamp_m"]))
    return d, (shift if shift != 0.0 else None)


# -- the silencer seat (A6, W8n; docs/weapon_attachments.md 13.7 A6-2) ----------------------------------------------------
#
# A probe muzzle mount sits at the barrel tip, so a suppressor starts where the barrel ends and leaves a built-in brake, flash hider or
# shroud stub exposed behind it. The pair therefore moves back along the bore by ``d`` (the entry key ``seat_setback_m``). ``d`` comes from
# a radial silhouette of the host's muzzle end (``muzzle_silhouette``), read for its shroud and its devices (``muzzle_stub``), and from the
# part's own length (``setback_of``). All numbers are ``attachment_rules.muzzle_seat``; the three below are not parameters of it.

_MUZZLE_AHEAD_M = 0.10  # the silhouette also reads this far PAST the tip (a probe point can sit a little behind the mesh end)
_STUB_DEVICE_MARGIN_M = 0.010  # with no shroud, the stub is the rearmost device's rear face plus this
_REF_WINDOW_BINS = 10  # the reference radius: the median of this many bins at a time (windows with fewer than 5 populated bins are skipped)
_REF_MIN_POPULATED = 5


def setback_applies(slot: str, kind: str | None, tier: str, mount: dict | None) -> bool:
    """Which pairs get a ``seat_setback_m`` (13.7 A6-2): a ``suppressor`` of the ``muzzle`` slot, not an authored entry (tier neither ``twin`` nor
    ``override``), on a host whose muzzle mount is the probe's (``source == "probe"``) with nothing baked on it (empty ``occupied_by``, no
    ``child_node``). A mount an override made, or a seat taken from a baked child, is never moved."""
    if slot != "muzzle" or kind != "suppressor" or tier in ("twin", "override") or not mount:
        return False
    if mount.get("source") != "probe" or mount.get("occupied_by") or mount.get("child_node"):
        return False
    return mount.get("point") is not None and mount.get("up") is not None


def muzzle_silhouette(samples, point, up, params: dict) -> np.ndarray:
    """The silhouette radius per ``bin_m`` bin along the bore at the host's muzzle end: ``[(range_m + 0.10) / bin_m]`` metres, 0 for an empty bin.

    ``samples`` are the host's surface samples (``mount_probe.surface_samples`` at ``sample_pitch_m``), ``point`` the muzzle mount point P and
    ``up`` its bore direction u. For a sample v: ``s = (v - P).u`` (0 at the tip, negative behind) and ``r`` its distance from the bore line; the
    samples with ``-range_m < s < 0.10`` and ``r < radius_cap_m`` are kept (a wider thing is the receiver or a magazine, not the muzzle end).
    Bin ``i`` holds ``[-range_m + i * bin_m, -range_m + (i + 1) * bin_m)`` and its value is the largest ``r`` in it.
    """
    v = np.asarray(samples, dtype=np.float64).reshape(-1, 3)
    p = np.asarray(point, dtype=np.float64)
    u = np.asarray(up, dtype=np.float64)
    u = u / np.linalg.norm(u)
    d = v - p
    s = d @ u
    r = np.linalg.norm(d - np.outer(s, u), axis=1)
    keep = (s > -params["range_m"]) & (s < _MUZZLE_AHEAD_M) & (r < params["radius_cap_m"])
    s, r = s[keep], r[keep]
    bin_m = params["bin_m"]
    n = int(round((params["range_m"] + _MUZZLE_AHEAD_M) / bin_m))
    sil = np.zeros(n)
    for i in range(n):
        lo = -params["range_m"] + i * bin_m
        k = (s >= lo) & (s < lo + bin_m)
        if k.any():
            sil[i] = r[k].max()
    return sil


def muzzle_stub(sil, params: dict) -> tuple[float, float] | None:
    """``(stub, dev_rear_near)`` in metres from a ``muzzle_silhouette``, or None when the host has no barrel to read (no 10-bin window holds
    5 populated bins in the last ``window_m``).

    ``r_ref``, the thinnest sustained radius, is the minimum over every 10-bin window inside ``s`` in ``[-window_m, 0]`` of the window's
    median over its populated bins. A bin is wide when its silhouette exceeds ``ref_ratio * r_ref``. Walking from the tip backwards, a run is a
    maximal group of wide bins in which a single empty or narrow bin does not split it (a run of fewer than ``run_min_bins`` bins is noise and
    ignored); its front and rear distances are measured from the tip at the bins' lower edges. A run shorter than ``device_max_m`` is a DEVICE
    (brake, hider, gas block, stud); the first run of ``device_max_m`` or more is the shroud and ends the walk: ``stub`` is its front distance.
    With no such run ``stub`` is the rearmost device's rear distance plus 10 mm, or 0 with no device. ``dev_rear_near`` is the largest rear
    distance among the devices whose rear face lies within ``device_reach_m`` of the tip (0 when none): a device further back is a gas block or a
    sling stud and must not pull the sleeve over it.
    """
    sil = np.asarray(sil, dtype=np.float64)
    bin_m = params["bin_m"]
    s = -params["range_m"] + np.arange(len(sil)) * bin_m
    win = np.where((s >= -params["window_m"]) & (s <= 0.0))[0]
    if not len(win):
        return None
    meds = []
    for a in range(win[0], win[-1] - (_REF_WINDOW_BINS - 1)):
        seg = sil[a:a + _REF_WINDOW_BINS]
        seg = seg[seg > 0]
        if len(seg) >= _REF_MIN_POPULATED:
            meds.append(float(np.median(seg)))
    if not meds:
        return None
    wide = sil > params["ref_ratio"] * min(meds)
    runs = []  # (front distance from the tip, rear distance, length)
    i = int(win[-1])
    while i >= win[0]:
        if wide[i]:
            k = i
            while k - 1 >= win[0] and (wide[k - 1] or (k - 2 >= win[0] and wide[k - 2])):
                k -= 1
            if i - k + 1 >= params["run_min_bins"]:
                runs.append((-float(s[i]), -float(s[k]), (i - k + 1) * bin_m))
            i = k - 1
        else:
            i -= 1
    dev_rear = dev_near = 0.0
    stub = None
    for front, rear, length in sorted(runs, key=lambda run: run[0]):
        if length < params["device_max_m"]:
            dev_rear = max(dev_rear, rear)
            if rear <= params["device_reach_m"]:
                dev_near = max(dev_near, rear)
            continue
        stub = front
        break
    if stub is None:
        stub = (dev_rear + _STUB_DEVICE_MARGIN_M) if dev_rear else 0.0
    return stub, dev_near


def setback_of(stub: float, dev_rear_near: float, length: float, params: dict) -> float | None:
    """``seat_setback_m`` of one pair, or None for no key: ``d = min(stub, max(cover * L, dev_rear_near + device_cover_m), max_frac * L)`` with
    ``L`` the part's length along the bore (``footprint.height_m``), rounded to 1e-4; a ``d`` of ``dead_m`` or less writes no key."""
    d = _r(min(stub, max(params["cover"] * length, dev_rear_near + params["device_cover_m"]), params["max_frac"] * length))
    return d if d > params["dead_m"] + _EPS else None
