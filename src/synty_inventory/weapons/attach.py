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

_FOOT_SLAB_M = 0.004  # the foot slab: vertices within 4 mm of the contact extreme (spec 3.4 step 1)
_MIN_POINTS = 3  # distinct points (0.1 mm dedupe) a slab or a face needs
_DEDUPE_M = 1e-4
_WINDOW_FRAC = 0.25  # outer share of the length whose cross-section decides a sign (spec 3.4 step 3)
_SYMMETRIC_RATIO = 1.15  # larger/smaller end section below this: the sign is a coin flip
_MATE_TOLS_M = (0.001, 0.002, 0.005, 0.010)  # mating-face tolerances, as the A0 muzzle probe (geometry._MUZZLE_TOLS_M)
_EPS = 1e-9
_AXES = "xyz"
_SIGNED_AXIS_RE = re.compile(r"^[+-][xyz]$")
_FOOT_AT_BOTTOM = ("optic", "laser_light")  # the others hang from a +Y foot


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


def _slab(v: np.ndarray, low: bool) -> np.ndarray:
    y = v[:, 1]
    return v[y <= float(y.min()) + _FOOT_SLAB_M + _EPS] if low else v[y >= float(y.max()) - _FOOT_SLAB_M - _EPS]


def _slab_centre(slab: np.ndarray, low: bool) -> np.ndarray:
    lo, hi = slab.min(axis=0), slab.max(axis=0)
    return np.array([(lo[0] + hi[0]) / 2.0, lo[1] if low else hi[1], (lo[2] + hi[2]) / 2.0])


def _foot_anchor(v: np.ndarray, slot: str, forward_override) -> dict:
    expected_low = slot in _FOOT_AT_BOTTOM
    for attempt, low in enumerate((expected_low, not expected_low)):
        slab = _slab(v, low)
        if len(_distinct(slab)) >= _MIN_POINTS:
            break
    else:
        return _unmeasured()
    foot_source = "authored_up" if attempt == 0 else "measured"
    up = _unit(1, 1 if low else -1)
    ext = v.max(axis=0) - v.min(axis=0)
    axis = 2 if ext[2] >= ext[0] else 0
    sign, decided = _end_sign(*_end_sections(v, axis))
    forward_source, symmetric = ("section", False) if decided else ("authored", True)
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


def measure_anchor(vertices, slot: str, forward_override=None) -> dict:
    v = np.asarray(vertices, dtype=np.float64).reshape(-1, 3)
    if not len(v):
        return _unmeasured()
    return _muzzle_anchor(v, forward_override) if slot == "muzzle" else _foot_anchor(v, slot, forward_override)


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
