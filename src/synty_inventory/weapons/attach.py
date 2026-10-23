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


def _foot_slab(v: np.ndarray, low: bool, axis: int, p: dict) -> np.ndarray:
    """The slab of the first rung of ``foot_depths_m`` that is not a lip along ``forward`` (``axis``) or ``right`` (the other horizontal axis)."""
    depths = p["foot_depths_m"]
    right = 0 if axis == 2 else 2
    rung = 0
    slab = _slab(v, low, depths[0])
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
    slab = _foot_slab(v, low, axis, p)  # A4 item 3: one rung deeper when the 4 mm slab only cut a lip
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
