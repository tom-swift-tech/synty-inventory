"""Weapon geometry: axes, length, tip/butt, muzzle, grip, support (spec 3.5).

``measure_weapon_detail`` is the uncached core: one decode of the record's GLB (``glb_geometry.load_triangles``,
collision hulls dropped with ``naming.SKIP_STEM_RE``, ``files.glb_scale`` applied), then pure numpy on the vertex
array. ``measure_cached`` wraps it in the ``_geometry_cache.json`` cache. All points are asset-local metres in the
GLB scene space (never re-centred); every number in the block is rounded to 1e-4 with ``-0.0`` normalised, so the
cache round-trip cannot change a byte.

Nothing here knows about records: the caller passes archetype/kind/role/hold_class/genre and gets back the
geometry block plus the flags and reasons the measurement implies.
"""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .. import weapons as _pkg  # read WEAPON_GEOMETRY_VERSION at call time (a test may bump it)
from ..naming import SKIP_STEM_RE
from ..schema import pivot_from_aabb
from ..sources.glb_geometry import load_triangles, node_world_matrices
from ..sources.glb_measure import NodeSel, _cache_key, node_cache_tag, node_selected, read_glb_json
from ..sources.glb_scale import scale_cache_tag
from . import digest, write_text_lf
from . import fit_geometry as _fit
from .attach import measure_anchor, muzzle_silhouette, muzzle_stub, place, settle_pair
from .mount_probe import end_ring_d, surface_samples
from .mounts import build_mounts, eligible, matching_slots, mesh_nodes
from .rules import attachment_rules

CACHE_NAME = "_geometry_cache.json"

_AXES = "xyz"
_TIE = 0.05  # long-axis tie band (spec 3.5.2)
# G1 frame vote (docs/weapon_attach_geometry.md 3.3 and 3.11). Module constants, versioned by WEAPON_GEOMETRY_VERSION 6, not rules keys, so
# rules_digest does not move. The survey that fixed them measured every ring end on the end slab of this width.
_FRAME_END_SLAB_M = 0.010  # end slab of the vote's ring test
_FRAME_BORE_MAX_M = 0.025  # the largest bore ring that confirms a muzzle end
_PIVOT_BAND = 0.10  # |origin_frac - 0.5| below this: the origin is "near the middle"
_END_FRAC = 0.10  # outer share of the length compared by the cross-section fallback
_TIP_MM = 0.002  # tip / butt: vertices within 2 mm of the extreme forward coordinate
_BIN_M = 0.01  # handle detection bin height
_HANDLE_MIN_BINS = 6  # a handle run is >= 6 cm
_HANDLE_BUTT_FRAC = 0.60  # handle is searched in the butt-side 60 % of the length
_HANDLE_E_RATIO = 1.3  # e <= 1.3 * p10(e)  (surface step: e' <= 1.3 * w_ref)
_HANDLE_W_PCT = 20  # surface step: w_ref = p20(e') over the window ...
_HANDLE_W_FLOOR_M = 0.003  # ... floored at 3 mm, so a window of hair-thin bins cannot collapse the threshold to zero
# surface step: a run counts at >= max(2 cm, min(6 cm, 0.2 * length)): a 28 cm razor is not asked for a 6 cm handle
_HANDLE_MIN_FLOOR_M, _HANDLE_MIN_CAP_M, _HANDLE_MIN_FRAC = 0.02, 0.06, 0.2
_SNAP_FROM_BUTT_FRAC = 0.30  # an origin nearer the butt than this is a designer's grip and is never moved
_SNAP_REACH_FRAC = 0.10  # a mid-origin snaps onto a counting run at most this share of the length away
_SURFACE_STEP_M = 0.005  # e(bin) sees the surface: points along every triangle edge at most this far apart
_SURFACE_MAX_SEGMENTS = 2000  # sanity cap per edge (an edge over 10 m is not a weapon mesh); keeps a garbage mesh bounded
_SURFACE_CHUNK = 1 << 21  # sample points held at once
# melee grip butt inset (W2f): the hand fist is centred on `grip` (sit_melee: the mesh point held in the fist), so a grip at
# the very butt (a bat whose pivot is the end of the handle) leaves half the hand off the knob. The nearest sit_melee
# constant is `bat_hand_gap_m` = 0.09 m, the distance between a bat's two hands (the upper hand sits one hand-width up
# the shaft); half of it, 0.045 m, is fist centre to fist edge. `empty_fist_r` (0.012) and `default_shaft_r` (0.026) are
# radii ACROSS the handle, not along it, so they do not apply. 0.09 m is also the adult palm width. For a very short item
# the inset is capped at half the length.
_GRIP_BUTT_INSET_M = 0.045
_SUPPORT_AT = 0.62
_SUPPORT_SLICE_M = 0.01
_MUZZLE_TOLS_M = (0.001, 0.002, 0.005, 0.010)  # sit_weapons FACE_TOLS_M
_MUZZLE_SNAP_M = 0.0001
_MUZZLE_MIN_POINTS = 3
_MUZZLE_HEIGHT_FRAC = 0.75
_OUTSIDE_EPS = 1e-4  # the origin counts as inside the AABB within the rounding unit
_HEADED = ("axe", "mace", "hammer", "club")  # the larger end is the working end; every other archetype is pointed
# W2f: a melee item whose origin is mid-length reads its forward sign from the larger of the two end heads when the ends
# differ clearly. Calibrated on the melee records that have a designer-given sign (forward_source "pivot"): the larger
# lateral extent over the outer 25 % of the length is the forward end for these archetypes (agreement with the pivot sign,
# fallbacks included: axe .96, mace 1.0, hammer 1.0, club .80, staff 1.0, tool .69 (13 distinct meshes), polearm .83; the
# 10 % cross-section rule it replaces: .78 / .85 / .98 / .71 / .25 / .38 / .67). The pointed archetypes are left out on
# purpose: for sword / knife the heavier end (guard, pommel) is the BUTT, so the larger end is forward only .4-.5 of the
# time there; a spear's leaf head and its butt are a wash (.83 vs .79 for the current rule, the two rules disagree on 14
# of 48 and the larger end wins 8 of them), and a ferrule can be wider than the head; fist_weapon / wand are too few
# (4 / 2) to calibrate.
_HEAD_FORWARD = ("axe", "mace", "hammer", "club", "staff", "tool", "polearm")
_HEAD_FRAC = 0.25  # outer share of the length whose largest lateral extent is the end's head size
_HEAD_RATIO = 1.15  # the larger end must exceed the smaller by 15 %, else the end-section rule decides (agreement is flat
# for ratios 1.1-1.3; the upper bound is set by the double-headed staff that must still flip, ratio about 1.22)
# W7 (R-H1): for these archetypes a PIVOT-decided sign is replaced by the head sign when the ends differ clearly: the pivot
# rule assumes the origin is in the grip, and Halberd_06 / Farm Scythe_01 / the AncientEmpire Axe_02 have it at the head.
# club and tool are left out on purpose (side-handle batons, PipeWrench_01 and the motor-heavy Chainsaw_01 have a bigger
# end that is not the working end); tools whose head leads opt in through `head_lead` (R-H2, rules.head_lead_tokens).
_HEAD_PIVOT = ("axe", "mace", "hammer", "polearm", "staff")
# shield front face (spec 3.5.2 item 4): which side of the face normal is the outer face
_WELD_M = 1e-4  # vertices closer than this share a component (the GLB splits vertices at UV / normal seams)
_STRAP_MAX_AREA = 0.10  # a strap / handle is a small piece: at most 10 % of the surface area
_STRAP_ASPECT = 3.0  # ... elongated across the face (long lateral extent >= 3x the short one)
_STRAP_STANDOFF = 1.5  # ... and stands off the plate (extent along the normal >= 1.5x its short lateral extent)
_STRAP_OFFSET = 0.12  # ... with its centre >= 12 % of the thickness off the plate's mid-plane
# a piece in the outer 10 % of the bounding thickness (centre >= 40 % off the mid-plane) is a handle even when it is a
# flat bar barely deeper than wide (the Kids shields: standoff 1.10, offset 0.47); the real front decorations that
# pass the elongation test (spike arms, offsets <= 0.25, standoff 1.16) and the flat bands (standoff <= 1.0) stay out
_STRAP_OUTER_OFFSET = 0.40
_STRAP_OUTER_STANDOFF = 1.05
_STRAP_MIN_AREA = 0.02  # the biggest strap piece must reach 2 % of the surface to count
_STRAP_MARGIN = 1.1  # ... and beat the biggest piece on the other side by 10 %
_DISH_RIM_R, _DISH_CENTRE_R = 0.75, 0.40  # normalised elliptical radius of the rim / centre zones
_DISH_MIN = 0.03  # |centre - rim| along the normal, as a share of the thickness, that counts as a dish
# bow forward (spec 3.5.2 item 3): a strung bow's belly (riser / grip) bulges toward the target, the limb tips and the
# string sit toward the archer
_BOW_TIP_FRAC = 0.10  # each outer 10 % of the length along `up` is a tip window
_BOW_MID_FRAC = 0.20  # the middle 20 % is the riser window
_BOW_BELLY_MIN = 0.15  # |riser - tips| as a share of the forward extent that decides the sign; below it the origin does


# -- small helpers ---------------------------------------------------------------------------------------


def _r(x) -> float:
    """Round to 1e-4; ``+ 0.0`` turns -0.0 into 0.0 so the bytes cannot flip on noise."""
    return round(float(x), 4) + 0.0


def _vec(a) -> list[float]:
    return [_r(c) for c in a]


def _parse_axis(sig: str) -> tuple[int, int]:
    """'+z' -> (2, +1)."""
    if len(sig) != 2 or sig[0] not in "+-" or sig[1] not in _AXES:
        raise ValueError(f"bad signed axis {sig!r}")
    return _AXES.index(sig[1]), (1 if sig[0] == "+" else -1)


def _sig(idx: int, sign: int) -> str:
    return ("+" if sign > 0 else "-") + _AXES[idx]


def _unit(idx: int, sign: int = 1) -> np.ndarray:
    v = np.zeros(3)
    v[idx] = sign
    return v


def _snap(c: float) -> int:
    """Godot ``Vector3.snapped`` on one component, as an integer key (floor(x / step + 0.5))."""
    return int(math.floor(c / _MUZZLE_SNAP_M + 0.5))


# -- muzzle (M1-M6 port) ---------------------------------------------------------------------------------


def muzzle_point(vertices, forward: str = "+z", up: str = "+y", bounds: dict | None = None) -> tuple[list[float], str]:
    """Port of sit_weapons ``SitGunHold.muzzle_local`` (spec 3.5.4) along a signed ``forward`` axis.

    ``(point, 'face' | 'bounds_fallback')``. Faithful to the GDScript, including its two quirks: the dedupe keeps the
    last vertex of each snapped cell (not the snapped value), and the face point takes the mean of the two lateral
    coordinates while the forward coordinate is the bounds maximum (not a mean). ``bounds`` ({'min','max'}) defaults
    to the AABB of ``vertices``, which is what the Godot code measures.
    """
    point, source, _ = muzzle_probe(vertices, forward, up, bounds)
    return point, source


def muzzle_probe(vertices, forward: str = "+z", up: str = "+y", bounds: dict | None = None) -> tuple[list[float], str, np.ndarray]:
    """``muzzle_point`` plus the face points it averaged: ``(point, source, face [N,3])``.

    The one A0 algorithm (docs/weapon_attachments.md 4.2 forbids a second one): ``muzzle_point`` is this function minus the
    face. ``face`` is the deduplicated vertex set of the first tolerance window holding three or more points (the points
    the face point is the mean of) and is empty for ``bounds_fallback``. The host muzzle mount (``mounts.py``) runs it on the
    host mesh minus the baked muzzle devices and reads the bore from the same face.
    """
    v = np.asarray(vertices, dtype=np.float64).reshape(-1, 3)
    if not len(v):
        raise ValueError("muzzle_point needs at least one vertex")
    fa, fs = _parse_axis(forward)
    ua, us = _parse_axis(up)
    if fa == ua:
        raise ValueError("forward and up must be different axes")
    if bounds is None:
        bmin, bmax = v.min(axis=0), v.max(axis=0)
    else:
        bmin, bmax = np.asarray(bounds["min"], dtype=np.float64), np.asarray(bounds["max"], dtype=np.float64)
    fc = fs * v[:, fa]
    max_f = float(fs * bmax[fa] if fs > 0 else -bmin[fa])  # bounds end along the signed forward axis
    face: dict[tuple[int, int, int], np.ndarray] = {}
    for tol in _MUZZLE_TOLS_M:
        face = {}
        for p in v[fc >= max_f - tol]:
            face[(_snap(p[0]), _snap(p[1]), _snap(p[2]))] = p
        if len(face) >= _MUZZLE_MIN_POINTS:
            break
    pt = np.zeros(3)
    if len(face) >= _MUZZLE_MIN_POINTS:
        pts = np.array(list(face.values()))
        pt[:] = np.mean(pts, axis=0)
        pt[fa] = fs * max_f
        return _vec(pt), "face", pts
    side = 3 - fa - ua  # the lateral axis that is not up
    pt[side] = (bmin[side] + bmax[side]) * 0.5
    uc_min = float(us * bmax[ua] if us < 0 else bmin[ua])
    uc_max = float(us * bmin[ua] if us < 0 else bmax[ua])
    # signed up coordinate: min_up + 0.75 * up_extent, mapped back to the axis
    pt[ua] = us * (uc_min + _MUZZLE_HEIGHT_FRAC * (uc_max - uc_min))
    pt[fa] = fs * max_f
    return _vec(pt), "bounds_fallback", np.zeros((0, 3))


# -- decode ------------------------------------------------------------------------------------------------

_DECODE_MEMO: dict[tuple, tuple[np.ndarray, int] | None] = {}
_DECODE_MEMO_MAX = 4


def _collision(name: str) -> bool:
    return bool(SKIP_STEM_RE.search(name or ""))


def _decode(path: Path, glb_node: NodeSel, scale: float) -> tuple[np.ndarray, int, np.ndarray] | None:
    """(vertices [N,3], triangle count, triangle indices [M,3]) or None. A tiny memo lets the pass-2 re-measure skip a
    second decode."""
    try:
        st = path.stat()
    except OSError:
        return None
    key = (str(path), st.st_mtime_ns, st.st_size, node_cache_tag(glb_node), scale)
    if key in _DECODE_MEMO:
        return _DECODE_MEMO[key]
    got = load_triangles(path, glb_node, exclude=_collision, scale=scale)
    out = None
    if got is not None:
        verts, tris = got
        if len(verts) and len(tris) and np.isfinite(verts).all():
            verts = np.asarray(verts, dtype=np.float64)
            verts.flags.writeable = False
            out = (verts, int(len(tris)), np.asarray(tris, dtype=np.int64))
    if len(_DECODE_MEMO) >= _DECODE_MEMO_MAX:
        _DECODE_MEMO.pop(next(iter(_DECODE_MEMO)))
    _DECODE_MEMO[key] = out
    return out


def _node_info(path: Path, glb_node: NodeSel, scale: float) -> tuple[bool, list[float] | None, bool]:
    """(found, node_offset, transformed) for a node selection.

    ``node_offset`` is the world translation of a SINGLE named node in GLB scene space, scaled by ``glb_scale`` like
    the vertices so the consumer can subtract it from the bounds; it is never rotated and never item-baked. It is
    None for a list or null selection. ``transformed`` is True when any selected node's world transform has a
    rotation or scale (assumption NB-15): the points are then left for review.
    """
    if glb_node is None:
        return True, None, False
    doc = read_glb_json(path)
    if doc is None:
        return False, None, False
    nodes = doc.get("nodes") or []
    matched = [w for idx, w in node_world_matrices(doc).items() if node_selected(nodes[idx].get("name"), glb_node)]
    if not matched:
        return False, None, False
    transformed = any(not np.allclose(w[:3, :3], np.eye(3), atol=1e-6) for w in matched)
    offset = _vec(matched[0][:3, 3] * scale) if isinstance(glb_node, str) else None
    return True, offset, transformed


# -- the measurement -------------------------------------------------------------------------------------


def _frac(origin: float, lo: float, size: float) -> float:
    return (origin - lo) / size if size > 1e-9 else 0.5


def _pick_long_axis(size: np.ndarray, default: int) -> int:
    best = float(size.max())
    cands = [i for i in range(3) if size[i] >= (1.0 - _TIE) * best]
    return default if default in cands else int(np.argmax(size))


@dataclass(frozen=True)
class FrameVote:
    """The record frame an eligible host votes for (``frame_vote``). ``forward`` and ``up`` are ``(axis letter, sign)``.

    ``changed``: the forward axis differs from the build's. ``conflict``: the body axis differs from the build's and the bore ring test could not
    say which end is the muzzle (no end, or both ends), with no ``frame_axis`` to settle it: the vote keeps the build's frame and the S7 detector
    seats are withheld. ``sign_by_fallback`` (beside the spec's four fields, default False): a ``frame_axis`` moved the axis but no single ring
    gave the sign, so ``forward`` carries the default ``+`` and the caller flags it for review.
    """

    forward: tuple[str, int]
    up: tuple[str, int]
    changed: bool
    conflict: bool
    sign_by_fallback: bool = False


def _ranged_up_axis(forward_axis: int) -> int:
    """The build's up axis for a ranged host (``axes.up`` logic, unchanged): z when forward is y, else y. Only eligible hosts vote, and those are ranged."""
    return 2 if forward_axis == 1 else 1


def _ring_ends(body: np.ndarray, axis: int) -> tuple[bool, bool]:
    """``(low end, high end)``: does each end of ``axis`` carry a bore ring of at most ``_FRAME_BORE_MAX_M``? (spec 3.3 step 3)"""
    ends = []
    for sign in (-1, 1):
        d = end_ring_d(body, axis, sign, _FRAME_END_SLAB_M)
        ends.append(d is not None and d <= _FRAME_BORE_MAX_M + 1e-9)
    return ends[0], ends[1]


def frame_vote(verts, body_verts, build_forward: tuple[int, int], frame_axis: str | None = None) -> FrameVote:
    """The body-axis frame vote of an eligible host (spec 3.3). ``build_forward`` is the bounding-box frame's ``(axis index, sign)``.

    ``verts`` is the whole host mesh and ``body_verts`` the mesh minus its slot children (the nodes the child vocabulary matches). The body axis is
    ``_pick_long_axis`` on the body (default z: eligible hosts are ranged). The ring test reads the BODY, because the body axis' ends are the body's
    ends: a baked magazine or silencer must not hide or fake a ring. With no body left (``body_verts`` empty) the whole mesh stands in.

    ``frame_axis`` (an id override, spec 4.5) decides the axis when present. Otherwise a body axis that differs from the build's is confirmed by
    exactly one end ring (forward toward it), and is a conflict with none or two (the build's frame is kept). A ``frame_axis`` on a different axis
    also takes its sign from a single end ring there, else the default ``+`` (``sign_by_fallback``): the id's ``forward`` override then sets it.
    The up axis is the build's rule for a ranged host applied to the new forward.
    """
    b_axis, b_sign = build_forward
    keep = FrameVote((_AXES[b_axis], b_sign), (_AXES[_ranged_up_axis(b_axis)], 1), False, False)
    body = np.asarray(body_verts if body_verts is not None and len(body_verts) else verts, dtype=np.float64).reshape(-1, 3)
    axis = _AXES.index(frame_axis) if frame_axis is not None else _pick_long_axis(np.ptp(body, axis=0), 2)
    if axis == b_axis:
        return keep
    low, high = _ring_ends(body, axis)
    if low != high:
        sign, fallback = (1 if high else -1), False
    elif frame_axis is None:
        return FrameVote(keep.forward, keep.up, False, True)
    else:
        sign, fallback = 1, True
    return FrameVote((_AXES[axis], sign), (_AXES[_ranged_up_axis(axis)], 1), True, False, fallback)


def _body_vertices(glb: Path, glb_node: NodeSel, scale: float, rules: dict, verts: np.ndarray) -> np.ndarray:
    """The host mesh minus its slot children: the mesh nodes the child vocabulary matches (``attachment_rules.child_tokens`` and ``child_never``,
    through ``mounts.mesh_nodes`` and ``mounts.matching_slots``), before policy and before mount overrides (spec 3.3 step 1). It does not use
    ``occupied_by``, which ``build_mounts`` makes from the axes, and it keeps located preset parts. The whole mesh when no child matches or nothing is left."""
    tables = attachment_rules(rules)
    drop = frozenset(n for n in mesh_nodes(read_glb_json(glb), glb_node) if matching_slots(n, tables))
    if not drop:
        return verts
    got = load_triangles(glb, glb_node, exclude=lambda n: _collision(n) or n in drop, scale=scale)
    if got is None or not len(got[0]) or not np.isfinite(got[0]).all():
        return verts
    return np.asarray(got[0], dtype=np.float64)


def _cross_section(v: np.ndarray, axis: int) -> float:
    lat = [i for i in range(3) if i != axis]
    ext = v[:, lat].max(axis=0) - v[:, lat].min(axis=0)
    return float(ext[0] * ext[1])


def _section_sign(v: np.ndarray, axis: int, lo: float, size: float, headed: bool) -> int:
    """Forward sign from the end cross-sections over the outer 10 % of the length (spec 3.5.2 step 2).

    Cross-section = area of the lateral AABB of the vertices in the window. Equal areas resolve to '+'.
    """
    win = _END_FRAC * size
    a_lo = _cross_section(v[v[:, axis] <= lo + win + 1e-9], axis)
    a_hi = _cross_section(v[v[:, axis] >= lo + size - win - 1e-9], axis)
    if abs(a_hi - a_lo) <= 1e-12:
        return 1
    tip_is_hi = (a_hi > a_lo) if headed else (a_hi < a_lo)
    return 1 if tip_is_hi else -1


def _head_sign(v: np.ndarray, axis: int, lo: float, size: float) -> int:
    """Forward sign (+1 / -1) of the end with the clearly larger head, or 0 when the two ends are within ``_HEAD_RATIO``.

    Head size = the largest lateral AABB extent of the vertices in the outer ``_HEAD_FRAC`` of the length at each end.
    The caller applies it to the ``_HEAD_FORWARD`` archetypes (mid-origin items, falling back to ``_section_sign`` on 0) and,
    since W7, to the ``_HEAD_PIVOT`` archetypes and head-lead tools (pivot-decided items, keeping the pivot sign on 0).
    """
    win = _HEAD_FRAC * size
    lat = [i for i in range(3) if i != axis]
    a_lo, a_hi = (float((p[:, lat].max(axis=0) - p[:, lat].min(axis=0)).max())
                  for p in (v[v[:, axis] <= lo + win + 1e-9], v[v[:, axis] >= lo + size - win - 1e-9]))
    big, small = max(a_lo, a_hi), min(a_lo, a_hi)
    if big <= 1e-12 or big < _HEAD_RATIO * small:
        return 0
    return 1 if a_hi > a_lo else -1


def _ranged_convention_sign(rules: dict, genre: str | None, kind: str | None, fa: int, section_fs: int) -> int:
    """Forward sign of a firearm-like weapon whose origin says nothing (spec 3.5.2 step 2, ranged): the pack
    convention ``rules.axes_expected[genre][kind]`` when it names the long axis, else the end-section sign.

    The end cross-sections cannot tell a muzzle from a stock: on the live whole-role ranged weapons that fell through
    to the section rule, every -z result that could be judged by eye (stock, trigger and magazine toward -z, barrel,
    warhead or muzzle brake toward +z) was wrong, and the +z ones were all right. No shape feature separated the two
    groups cleanly (each flipped 8-28 % of the correct ones while fixing at most all but one of the wrong ones):
    surface area or AABB of the 10-30 % end windows, mean height of the end windows, the position of the
    area-weighted centroid, and where the lowest bins (grip, magazine, trigger guard) sit along the length.
    Every firearm that is measured by its origin or visibly judged is barrel-toward-+z (spec 3.5.1), so the convention
    decides the weak case. It stays a fallback: the flag ``forward_by_fallback`` is kept and an origin that decides
    (pivot) is never overridden -- a mismatch there is the ``axes_unexpected`` reason, as before. Only ``role ==
    "whole"`` uses it: emplaced weapons (cannons, ballistas, catapults) were judged by eye to face either way, so for
    them the end sections stay as they were, unverified.
    """
    expected = ((rules.get("axes_expected") or {}).get(genre) or {}).get(kind) if genre and kind else None
    if expected:
        axis, sign = _parse_axis(expected)
        if axis == fa:
            return sign
    return section_fs


def _bow_belly(v: np.ndarray, up: int, fwd: int) -> float:
    """How far the bow's riser sits along ``+fwd`` relative to its limb tips, as a share of the forward extent
    (spec 3.5.2 item 3): mean ``fwd`` coordinate of the vertices in the middle 20 % of the length along ``up`` minus the
    mean of the two outer-10 % window means (each end weighs the same, whatever its vertex count). Positive: the belly
    is on the ``+fwd`` side, so forward is ``+fwd``. 0.0 when a window is empty or the mesh is flat along ``fwd``.

    Measured on the 41 real whole bows: every real bow (long axis up, string toward the archer) has |belly| >= 0.27;
    the objects the archetype rules wrongly call bows (crossbows laid out limb-wise, gift ribbons) sit at <= 0.11.
    """
    lo, size = float(v[:, up].min()), float(np.ptp(v[:, up]))
    fext = float(np.ptp(v[:, fwd]))
    if size <= 1e-9 or fext <= 1e-9:
        return 0.0
    t = (v[:, up] - lo) / size
    mid = v[(t >= 0.5 - _BOW_MID_FRAC / 2) & (t <= 0.5 + _BOW_MID_FRAC / 2), fwd]
    end_a = v[t <= _BOW_TIP_FRAC, fwd]
    end_b = v[t >= 1.0 - _BOW_TIP_FRAC, fwd]
    if not (len(mid) and len(end_a) and len(end_b)):
        return 0.0
    return float((mid.mean() - 0.5 * (end_a.mean() + end_b.mean())) / fext)


def _weld_components(v: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """Connected-component id per triangle. Vertices are welded by position first (``_WELD_M``): the GLB duplicates
    vertices along UV and normal seams, so index adjacency alone would shred every plate into pieces. Ids are the
    smallest welded-vertex index in the component, so they are stable for a given mesh."""
    key = np.round(v / _WELD_M).astype(np.int64)
    _, inv = np.unique(key, axis=0, return_inverse=True)
    t = inv.ravel()[tris]
    parent = list(range(int(t.max()) + 1))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b, c in t.tolist():
        for x, y in ((a, b), (b, c)):
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[max(rx, ry)] = min(rx, ry)
    return np.array([find(a) for a in t[:, 0].tolist()], dtype=np.int64)


def _shield_front_sign(v: np.ndarray, tris: np.ndarray, normal: int) -> tuple[int, str | None]:
    """Which side of the face normal is the shield's outer face: ``(+1 | -1, signal)`` or ``(0, None)`` (spec 3.5.2
    item 4). Chosen against a visual check of real shields from many packs, because the origin alone is right for
    only about two thirds of them. Two signals, in priority order:

    1. ``strap``: the arm straps / handles are small, elongated pieces that stand off the BACK of the plate (the
       boss, studs and cross-bars on the front are flat or round, so they fail the elongation / stand-off tests).
       The side holding the biggest such piece is the back. A bowl-shaped shield whose handle sits on the convex
       side is decided here, not by the dish, because the handle is outermost (``_STRAP_OUTER_*``).
    2. ``dish``: a shield is convex toward the front. The largest component's centre sits further along the front
       normal than its rim (the component excludes the straps, which would drag the centre the wrong way).
    """
    mn, mx = v.min(axis=0), v.max(axis=0)
    size = mx - mn
    thick = float(size[normal])
    lat = [i for i in range(3) if i != normal]
    p = v[tris]
    area = 0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1)
    total = float(area.sum())
    if thick <= 1e-9 or total <= 1e-12:
        return 0, None
    comp = _weld_components(v, tris)
    ids = np.unique(comp)  # sorted: the largest component is the lowest id among equals
    shares = np.array([area[comp == c].sum() / total for c in ids])
    main = int(ids[int(np.argmax(shares))])
    boxes = {}
    for c in ids:
        pts = p[comp == c].reshape(-1, 3)
        boxes[int(c)] = (pts.min(axis=0), pts.max(axis=0))
    main_mid = 0.5 * (boxes[main][0][normal] + boxes[main][1][normal])
    side_max = {1: 0.0, -1: 0.0}  # the largest strap candidate on each side of the main plate
    for c, share in zip(ids, shares):
        c = int(c)
        if c == main or share > _STRAP_MAX_AREA:
            continue
        lo, hi = boxes[c]
        ext = hi - lo
        short, long_ = sorted(float(e) for e in ext[lat])
        off = (0.5 * (lo[normal] + hi[normal]) - main_mid) / thick
        standoff = _STRAP_OUTER_STANDOFF if abs(off) >= _STRAP_OUTER_OFFSET else _STRAP_STANDOFF
        if short <= 1e-6 or long_ < _STRAP_ASPECT * short or float(ext[normal]) < standoff * short:
            continue
        if abs(off) >= _STRAP_OFFSET:
            side = 1 if off > 0 else -1
            side_max[side] = max(side_max[side], float(share))
    # the bigger single piece wins, not the bigger total: a ring of small spikes on the front (several pieces) must
    # not outvote the one real handle behind
    back = 1 if side_max[1] > side_max[-1] else -1
    if side_max[back] >= _STRAP_MIN_AREA and side_max[back] >= _STRAP_MARGIN * side_max[-back]:
        return -back, "strap"
    # dish: area-weighted mean coordinate along the normal, centre zone minus rim zone of the main component
    sel = comp == main
    pts, w = p[sel].reshape(-1, 3), np.repeat(area[sel], 3)
    centre = 0.5 * (mn + mx)
    r = np.sqrt((((pts[:, lat] - centre[lat]) / np.maximum(size[lat] / 2.0, 1e-9)) ** 2).sum(axis=1))
    rim, mid = r > _DISH_RIM_R, r < _DISH_CENTRE_R
    if rim.any() and mid.any():
        t = pts[:, normal]
        dish = (float((t[mid] * w[mid]).sum() / w[mid].sum()) - float((t[rim] * w[rim]).sum() / w[rim].sum())) / thick
        if abs(dish) >= _DISH_MIN:
            return (1 if dish > 0 else -1), "dish"
    return 0, None


class _BinStats:
    """Per-bin count, lateral sum and lateral min / max of the surface points, over the first ``rn`` bins."""

    def __init__(self, rn: int):
        self.rn = rn
        self.count = np.zeros(rn)
        self.total = np.zeros((rn, 2))
        self.lo = np.full((rn, 2), np.inf)
        self.hi = np.full((rn, 2), -np.inf)

    def add(self, bins: np.ndarray, lat: np.ndarray) -> None:
        keep = bins < self.rn
        if not keep.all():
            bins, lat = bins[keep], lat[keep]
        if not len(bins):
            return
        self.count += np.bincount(bins, minlength=self.rn)
        for j in (0, 1):
            self.total[:, j] += np.bincount(bins, weights=lat[:, j], minlength=self.rn)
        np.minimum.at(self.lo, bins, lat)
        np.maximum.at(self.hi, bins, lat)


def _bin_of(f: np.ndarray, fmin: float, nb: int) -> np.ndarray:
    return np.clip(np.floor((f - fmin) / _BIN_M + 1e-6).astype(np.int64), 0, nb - 1)


def _surface_stats(v: np.ndarray, tris: np.ndarray, fa: int, fc: np.ndarray, fmin: float, nb: int, rn: int) -> _BinStats:
    """Bin the SURFACE of the mesh (spec 3.5.5, W2d): the vertices plus points along every triangle edge at no more than
    ``_SURFACE_STEP_M`` spacing. A low-poly haft has bins holding one vertex or none; its long edges still cross them.
    Edges are deduplicated (a shared edge is one edge) and only those longer than the step need samples, so a dense
    mesh costs one length test per edge. Chunked, so memory stays bounded; everything is vectorised."""
    lat = [i for i in range(3) if i != fa]
    stats = _BinStats(rn)
    stats.add(_bin_of(fc, fmin, nb), v[:, lat])
    if not len(tris):
        return stats
    edges = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    edges.sort(axis=1)
    length = np.linalg.norm(v[edges[:, 1]] - v[edges[:, 0]], axis=1)
    far = (length > _SURFACE_STEP_M) & ((np.minimum(fc[edges[:, 0]], fc[edges[:, 1]]) - fmin) / _BIN_M < rn)
    edges, length = edges[far], length[far]
    if not len(edges):
        return stats
    _, first = np.unique(edges[:, 0] * np.int64(len(v)) + edges[:, 1], return_index=True)
    edges, length = edges[first], length[first]
    seg = np.minimum(np.ceil(length / _SURFACE_STEP_M - 1e-9).astype(np.int64), _SURFACE_MAX_SEGMENTS)
    inner = seg - 1  # interior points per edge (>= 1: the edge is longer than the step)
    ends = np.cumsum(inner)
    start = 0
    while start < len(edges):
        base = int(ends[start - 1]) if start else 0
        stop = max(int(np.searchsorted(ends, base + _SURFACE_CHUNK, side="right")), start + 1)
        k = inner[start:stop]
        which = np.repeat(np.arange(start, stop), k)
        step = np.arange(int(k.sum())) - np.repeat(np.cumsum(k) - k, k) + 1  # 1 .. seg - 1 within each edge
        t = (step / seg[which])[:, None]
        p0, p1 = v[edges[which, 0]], v[edges[which, 1]]
        pts = p0 + t * (p1 - p0)
        f0, f1 = fc[edges[which, 0]], fc[edges[which, 1]]
        stats.add(_bin_of(f0 + t[:, 0] * (f1 - f0), fmin, nb), pts[:, lat])
        start = stop
    return stats


def _find_handle(v: np.ndarray, fa: int, fc: np.ndarray, fmin: float, flen: float):
    """Handle run (spec 3.5.5) -> (centre forward coordinate, lateral means by axis, radius) or None."""
    nb = max(1, int(math.ceil(flen / _BIN_M - 1e-6)))
    bidx = np.minimum(np.floor((fc - fmin) / _BIN_M + 1e-6).astype(np.int64), nb - 1)
    rn = min(nb, max(1, int(math.ceil(_HANDLE_BUTT_FRAC * flen / _BIN_M - 1e-6))))
    lat = [i for i in range(3) if i != fa]
    order = np.argsort(bidx, kind="stable")
    sorted_bins = bidx[order]
    e = np.zeros(rn)
    prev = 0.0
    for b in range(rn):  # empty bins inherit the previous bin's extent
        lo, hi = np.searchsorted(sorted_bins, b, "left"), np.searchsorted(sorted_bins, b, "right")
        if hi > lo:
            pts = v[order[lo:hi]][:, lat]
            prev = float((pts.max(axis=0) - pts.min(axis=0)).max())
        e[b] = prev
    thr = _HANDLE_E_RATIO * float(np.percentile(e, 10)) + 1e-9
    ok = e <= thr
    best = None  # (run length, start) with the butt-most run winning ties
    b = 0
    while b < rn:
        if not ok[b]:
            b += 1
            continue
        s = b
        while b < rn and ok[b]:
            b += 1
        if b - s >= _HANDLE_MIN_BINS and float(e[s:b].mean()) > 0 and (best is None or b - s > best[0]):
            best = (b - s, s)
    if best is None:
        return None
    n, s = best
    sel = (bidx >= s) & (bidx < s + n)
    lateral = {i: float(v[sel, i].mean()) for i in lat} if sel.any() else {}
    return fmin + (s + n * 0.5) * _BIN_M, lateral, float(e[s:s + n].mean()) / 2.0


def _pivot_handle(v: np.ndarray, tris: np.ndarray, fa: int, fc: np.ndarray, fmin: float, flen: float, origin_f: float):
    """Pivot-anchored handle from the surface profile (spec 3.5.5, W2d steps 2-4) -> (grip forward coordinate, lateral
    means by axis, radius) or None. The base rule above runs first; this runs when it finds nothing.

    ``e'(bin)`` is the larger lateral extent of the SURFACE points in a 1 cm bin (an empty bin inherits the previous).
    ``w_ref`` = p20 of ``e'`` over the butt-side 60 % window, floored at 3 mm; a bin is thin at ``e' <= 1.3 * w_ref``; a
    counting run is >= ``min_run`` of thin bins. The designer's pivot already lies on the handle, so the pivot decides:
    inside a counting run the grip stays AT the pivot (the run confirms it and measures the radius); a pivot in the far
    70 % within 10 % of the length of a run snaps onto that run's near end, ``min_run / 2`` inside it; a pivot in the
    butt-side 30 % (a machete's hilt is wider than its blade by this profile) is never moved.
    """
    lat = [i for i in range(3) if i != fa]
    nb = max(1, int(math.ceil(flen / _BIN_M - 1e-6)))
    rn = min(nb, max(1, int(math.ceil(_HANDLE_BUTT_FRAC * flen / _BIN_M - 1e-6))))
    st = _surface_stats(v, tris, fa, fc, fmin, nb, rn)
    seen = st.count > 0
    raw = np.where(seen, (st.hi - st.lo).max(axis=1), 0.0)
    # empty bins inherit the previous bin's extent (0 before the first occupied bin)
    last = np.maximum.accumulate(np.where(seen, np.arange(rn), -1))
    e = np.where(last >= 0, raw[np.maximum(last, 0)], 0.0)
    w_ref = max(float(np.percentile(e, _HANDLE_W_PCT)), _HANDLE_W_FLOOR_M)
    ok = e <= _HANDLE_E_RATIO * w_ref + 1e-9
    # ceil, like the bin counts above: a 28 cm knife (0.2 * 0.28 = 5.6 cm) needs 6 whole bins
    min_m = max(_HANDLE_MIN_FLOOR_M, min(_HANDLE_MIN_CAP_M, _HANDLE_MIN_FRAC * flen))
    min_bins = int(math.ceil(min_m / _BIN_M - 1e-6))
    runs = []  # counting runs as (first bin, one past the last bin); an all-zero run (nothing measurable) never counts
    b = 0
    while b < rn:
        if not ok[b]:
            b += 1
            continue
        s = b
        while b < rn and ok[b]:
            b += 1
        if b - s >= min_bins and float(e[s:b].mean()) > 0:
            runs.append((s, b))

    def hit(f: float, s: int, b: int):
        n = float(st.count[s:b].sum())
        lateral = {i: float(st.total[s:b, j].sum() / n) for j, i in enumerate(lat)} if n else {}
        return f, lateral, float(e[s:b].mean()) / 2.0

    ob = int(math.floor((origin_f - fmin) / _BIN_M + 1e-6))  # the pivot's bin on the long axis
    for s, b in runs:
        if s <= ob < b:
            return hit(origin_f, s, b)
    if origin_f - fmin < _SNAP_FROM_BUTT_FRAC * flen - 1e-9:
        return None
    best = None  # (distance, start, end); the butt-most run wins a tie
    for s, b in runs:
        lo, hi = fmin + s * _BIN_M, fmin + b * _BIN_M
        d = max(lo - origin_f, origin_f - hi, 0.0)
        if d <= _SNAP_REACH_FRAC * flen + 1e-9 and (best is None or d < best[0] - 1e-12):
            best = (d, s, b)
    if best is None:
        return None
    _, s, b = best
    half = min_bins * _BIN_M / 2.0  # a run is >= min_run long, so lo + half <= hi - half
    lo, hi = fmin + s * _BIN_M, fmin + b * _BIN_M
    return hit(min(max(origin_f, lo + half), hi - half), s, b)


def _fail(reasons: list[str], warning: str | None = None) -> dict:
    return {"geometry": None, "flags": [], "reasons": sorted(set(reasons) | {"no_geometry"}), "warning": warning}


def measure_weapon_detail(
    glb: Path, glb_node: NodeSel, scale: float, archetype: str, kind: str | None, role: str, rules: dict,
    *, hold_class: str | None = None, genre: str | None = None, forward_override: str | None = None,
    head_lead: bool = False, attach_slot: str | None = None, mount_overrides: dict | None = None,
    with_mounts: bool = False, host_id: str | None = None, attach_kind: str | None = None, host_pack: str | None = None,
    frame_axis: str | None = None, fit_cache: dict | None = None, fit_cache_id: str | None = None, fused_parts: tuple | None = None,
) -> dict:
    """``{'geometry': block | None, 'flags': [...], 'reasons': [...], 'warning': str | None}`` (spec 3.5).

    ``attach_slot`` (W8a: the part is an attachment seated in this slot) adds the key ``attach`` = ``attach.measure_anchor``
    of the same decoded vertices (the anchor, the footprint and the reasons they imply); ``forward_override`` then also
    fixes the anchor's forward sign. Without a slot the result has no such key. ``attach_kind`` (A4, W8l) is the part's kind in that slot: the
    free-end forward of ``attachment_rules.anchor.free_end`` reads it (a host's baked children are measured without one, in ``mounts.py``).

    ``with_mounts`` (W8b, off by default so a bare measurement is the W7 dict byte for byte) makes an eligible host
    (``mounts.eligible``: whole, ranged, one_hand / long_gun) add the keys ``mounts`` (the ``geometry.mounts`` block of
    ``mounts.build_mounts``) and ``mount_problems`` (and, W8c, ``child_extents``: the sorted AABB extents of each baked child a slot lists in
    ``occupied_by``, the twin evidence of spec 5.1); they sit beside ``geometry`` and not in it, and
    ``directory.py`` decides what the record carries. ``measure_cached`` and ``measure_weapon`` ask for them.
    ``mount_overrides`` is the categorical per-slot override mapping (W8c supplies it; None = none). ``host_id`` (A3, W8i) is the
    asset id of an eligible host: ``attach_host_never`` and the baked-sight detector read its name tokens (default: the GLB file stem).
    ``host_pack`` (A6, W8n) is its pack id: with it the sight probe finds the host's ``"<pack>/<host id>"`` key in ``sight_probe.receiver_tol_by_host``.

    ``flags``/``reasons`` hold only what the measurement adds (``forward_by_fallback``, ``origin_outside_bounds``;
    ``axes_unexpected``, ``muzzle_fallback``, ``origin_outside_bounds``, ``node_transform``) -- or, when the mesh
    cannot be measured, the failure (``no_geometry``, plus ``degenerate`` for a zero-extent mesh). A node that is not
    in the GLB is an undecodable mesh with a ``warning``. Never copies geometry from anywhere (INV-6).

    ``forward_override`` (spec 4.5, W2e: a signed axis such as ``"+z"``, from an id override's ``forward``) replaces
    the forward SIGN once the mesh has decided its own, when its axis equals the measured forward axis: the source
    becomes ``override`` and every sign-derived value follows as if the mesh had decided that sign natively. The
    fallback flag the natural sign may have carried goes (the sign is no longer a guess); ``axes_unexpected`` is still
    judged from the final sign. A different axis is not applied: the measurement stays natural and ``warning`` says so.

    ``head_lead`` (W7 R-H2: the record carries one of ``rules.head_lead_tokens``) lets a melee ``tool`` take the head sign
    over a pivot-decided sign, as the ``_HEAD_PIVOT`` archetypes do.

    G1 (geometry version 6, spec 3.3): on an eligible host (``mounts.eligible``, whatever ``with_mounts`` says) the forward AXIS is voted by
    ``frame_vote`` (the body axis, confirmed by one bore ring, or the id override ``frame_axis``) before the ``forward_override`` sets the SIGN on
    it. Everything after the axes follows the voted frame, and ``geometry.long_axis`` stays the bounding-box axis. With ``with_mounts`` the key
    ``frame_vote`` sits beside ``geometry`` (like ``child_extents``, never a record key; S7 fold-in 1 renamed it from ``frame``, which collides
    with ``geometry["frame"] == "asset"``): the vote's ``changed`` and ``conflict``, and the PRE-vote
    ``length_m``, ``axes_unexpected`` and ``forward_by_fallback`` that ``pass2_inputs`` hands to classification, so the vote never feeds
    ``kind``, ``archetype`` or ``hold_class``. An eligible host that skips the vote (a bow or shield archetype that an id override forced
    onto a gun hold, S7 fold-in 2) has ``changed`` and ``conflict`` False and no pre-vote keys: ``pass2_inputs`` then reads the measured ones.

    S7: the key ``host_feats`` (``fit_geometry.host_features``: ``s0``, ``slots`` and the ``located`` placements) sits beside the block too. ``fit_cache`` (a
    dict the caller persists with ``fit_geometry.save_fit_cache``) and ``fit_cache_id`` (the entry id ``measure_cached`` uses) let the features be
    cached (spec 3.11); ``fused_parts`` is ``(key, load)`` for a preset host (``fit_geometry``, "Host features").
    """
    if hold_class is None:
        hold_class = (rules.get("hold_by_archetype") or {}).get(archetype, "none") if role == "whole" else "none"
    decoded = _decode(glb, glb_node, scale)
    if decoded is None:
        warning = None
        if glb_node is not None and glb.is_file() and not _node_info(glb, glb_node, scale)[0]:
            warning = f"{glb.name}: glb_node {glb_node!r} not found"
        return _fail([], warning)
    _, node_offset, transformed = _node_info(glb, glb_node, scale)
    verts, n_tris, tris = decoded
    mn, mx = verts.min(axis=0), verts.max(axis=0)
    size = mx - mn
    if float(size.max()) <= 1e-9:
        return _fail(["degenerate"])

    flags: set[str] = set()
    reasons: set[str] = set()
    is_bow = archetype == "bow"
    is_shield = kind == "shield" or archetype == "shield"
    origin = np.zeros(3)

    # --- axes (3.5.2) ---
    if is_shield:
        normal = int(np.argmin(size))
        rest = [i for i in range(3) if i != normal]
        # up = the longer of the two face axes; a near-tie (round shield) prefers y
        longer = max(rest, key=lambda i: size[i])
        up_axis = 1 if (1 in rest and size[1] >= (1.0 - _TIE) * size[longer]) else longer
        long_axis = up_axis
        # front face: measured straps / dish first; the origin ("sits near the arm face") only when neither decides
        fs, signal = _shield_front_sign(verts, tris, normal)
        if signal:
            f_src = "shield_front"
        else:
            fn = _frac(0.0, mn[normal], size[normal])
            # an origin in the middle band of the thickness says nothing (float noise would decide it): the tie goes
            # to '+', as the other axis ties do
            fs, f_src = (1 if (fn < 0.5 or abs(fn - 0.5) < _PIVOT_BAND - 1e-9) else -1), "shield_rule"
        fa = normal
        ua, us, u_src = up_axis, 1, "shield_rule"
    else:
        default = 1 if kind in ("melee", "thrown") else 2
        long_axis = _pick_long_axis(size, default)
        if is_bow:
            ua, us, u_src = long_axis, 1, "long_axis"
            rest = [i for i in range(3) if i != long_axis]
            fa = max(rest, key=lambda i: (size[i], i))  # the larger remaining axis (ties go to the later axis, z)
            belly = _bow_belly(verts, ua, fa)
            f_src = "bow_rule"
            if abs(belly) >= _BOW_BELLY_MIN:
                fs = 1 if belly > 0 else -1
            else:
                # no readable belly (a flat stave, or an object that is not a bow): the sign the origin gave before
                # this rule existed -- away from the origin -- stays, flagged as a fallback
                fs = 1 if _frac(0.0, mn[fa], size[fa]) < 0.5 else -1
                flags.add("forward_by_fallback")
        else:
            fa = long_axis
            f = _frac(0.0, mn[fa], size[fa])
            if abs(f - 0.5) >= _PIVOT_BAND - 1e-9:
                fs, f_src = (1 if f < 0.5 else -1), "pivot"
                if kind == "melee" and (archetype in _HEAD_PIVOT or (archetype == "tool" and head_lead)):
                    # W7: the clearly larger head decides over a pivot sign that disagrees; `forward_by_fallback`
                    # stays unset, this is a measured rule (like the bow belly), not a guess
                    hs = _head_sign(verts, fa, mn[fa], size[fa])
                    if hs and hs != fs:
                        fs, f_src = hs, "head"
            else:
                fs = _section_sign(verts, fa, mn[fa], size[fa], archetype in _HEADED)
                f_src = "section"
                flags.add("forward_by_fallback")
                if kind == "melee" and archetype in _HEAD_FORWARD:
                    fs = _head_sign(verts, fa, mn[fa], size[fa]) or fs
                if kind == "ranged" and role == "whole":
                    fs = _ranged_convention_sign(rules, genre, kind, fa, fs)
            if kind == "ranged":
                ua, us, u_src = (2 if fa == 1 else 1), 1, "fixed"
            else:
                rest = [i for i in range(3) if i != fa]
                ua = max(rest, key=lambda i: (size[i], -i))  # widest remaining axis; ties go to the earlier axis
                us, u_src = 1, "width_axis"
    expected = ((rules.get("axes_expected") or {}).get(genre) or {}).get(kind) if genre and kind else None
    o_axis, o_sign = _parse_axis(forward_override) if forward_override is not None else (None, 0)
    # --- the frame vote (G1, 3.3): the forward AXIS of an eligible host, before the override sets the sign on it ---
    vote = pre_vote = None
    if eligible(role, kind, hold_class) and not is_bow and not is_shield:
        overridden = o_axis == fa  # what the bounding-box frame, version 5, makes of the override: classification reads these values
        pre_vote = {
            "length_m": _r(size[long_axis]),
            "axes_unexpected": bool(expected and _sig(fa, o_sign if overridden else fs) != expected),
            "forward_by_fallback": "forward_by_fallback" in flags and not overridden,
        }
        vote = frame_vote(verts, _body_vertices(glb, glb_node, scale, rules, verts), (fa, fs), frame_axis)
        if vote.changed:
            fa, fs, f_src = _AXES.index(vote.forward[0]), vote.forward[1], "body"
            ua, us, u_src = _AXES.index(vote.up[0]), vote.up[1], "fixed"
            # the sign of a ring-confirmed end is measured, not a guess (as an override's is); a frame_axis with no single ring is a guess
            flags.discard("forward_by_fallback")
            if vote.sign_by_fallback:
                flags.add("forward_by_fallback")
    len_axis = fa if vote is not None and vote.changed else long_axis  # the length and the pivot fraction follow the voted frame
    warning = None
    if forward_override is not None:
        if o_axis == fa:
            fs, f_src = o_sign, "override"
            flags.discard("forward_by_fallback")
        else:
            warning = (f"forward override {forward_override!r} ignored: its axis is not the measured forward axis "
                       f"({_sig(fa, fs)})")
    forward, up = _sig(fa, fs), _sig(ua, us)
    basis = np.cross(_unit(ua, us), _unit(fa, fs))
    item_basis = [[int(round(c)) for c in row] for row in (basis, _unit(ua, us), _unit(fa, fs))]

    if expected and not is_bow and forward != expected:
        reasons.add("axes_unexpected")

    # --- length, tip, butt, pivot (3.5.3) ---
    fc = fs * verts[:, fa]
    fmin, fmax = float(fc.min()), float(fc.max())
    flen = fmax - fmin
    length = float(size[len_axis])
    tip = None
    if kind != "ranged":
        tip = _vec(verts[fc >= fmax - _TIP_MM - 1e-9].mean(axis=0))
    butt = _vec(verts[fc <= fmin + _TIP_MM + 1e-9].mean(axis=0))
    pivot_frac = _frac(0.0, mn[len_axis], size[len_axis])

    outside = bool(((origin < mn - _OUTSIDE_EPS) | (origin > mx + _OUTSIDE_EPS)).any())
    if outside:
        flags.add("origin_outside_bounds")
        reasons.add("origin_outside_bounds")
    centre = (mn + mx) * 0.5

    # --- muzzle (3.5.4) ---
    muzzle = muzzle_source = None
    if kind == "ranged" and not is_bow:
        muzzle, muzzle_source = muzzle_point(verts, forward, up)
        if muzzle_source == "bounds_fallback":
            reasons.add("muzzle_fallback")

    # --- grip (3.5.5) ---
    grip = grip_r = grip_source = None

    def at(f_coord: float, lateral: dict[int, float]) -> list[float]:
        p = centre.copy()
        for i, c in lateral.items():
            p[i] = c
        p[fa] = fs * f_coord
        return _vec(p)

    if is_bow:
        grip, grip_source = _vec(centre), "centre"
    elif is_shield:
        grip, grip_source = at(fmin, {}), "centre"
    elif kind == "melee" or archetype == "throwing_blade":
        # the fist is centred on the grip: keep it a hand-half off the butt end, along the forward axis only
        butt_min = fmin + min(_GRIP_BUTT_INSET_M, 0.5 * flen)
        run = _find_handle(verts, fa, fc, fmin, flen)
        if run is None and not outside:
            # the base rule found no handle: let the pivot decide, checked against the surface profile (W2d). An origin
            # outside the AABB is no pivot (spec 3.5.5), so it is never used as the anchor.
            run = _pivot_handle(verts, tris, fa, fc, fmin, flen, float(fs * origin[fa]))
        if run is not None:
            grip, grip_r, grip_source = at(max(run[0], butt_min), run[1]), _r(run[2]), "handle"
        elif not outside:
            # no handle run: the origin projected onto the weapon's long axis (the line through the bounds centre)
            grip, grip_source = at(max(float(fs * origin[fa]), butt_min), {}), "pivot"
    elif not outside:
        grip, grip_source = _vec(origin), "pivot"
    else:
        prop = (rules.get("grip_proportion") or {}).get(archetype)
        if prop:
            uc = us * verts[:, ua]
            p = centre.copy()
            p[fa] = fs * (fmin + prop[0] * flen)
            p[ua] = us * (float(uc.min()) + prop[1] * float(uc.max() - uc.min()))
            grip, grip_source = _vec(p), "proportion"

    # --- support (3.5.6): long_gun only, radius unclamped ---
    support = support_r = support_source = None
    if hold_class == "long_gun":
        at_f = fmin + _SUPPORT_AT * flen
        sl = verts[np.abs(fc - at_f) <= _SUPPORT_SLICE_M + 1e-9]
        lat = [i for i in range(3) if i != fa]
        if len(sl):
            lateral = {i: float(sl[:, i].mean()) for i in lat}
            ext = sl[:, lat].max(axis=0) - sl[:, lat].min(axis=0)
            support_r = _r(float(ext.min()) / 2.0)
        else:
            lateral = {}  # nothing in the slice: lateral falls back to the bounds centre, the radius is unknown
        support, support_source = at(at_f, lateral), "proportion"

    if transformed:
        reasons.add("node_transform")

    rmn, rmx = _vec(mn), _vec(mx)
    geometry = {
        "frame": "asset",
        "node_offset": node_offset,
        "axes": {"forward": forward, "up": up, "forward_source": f_src, "up_source": u_src},
        "item_basis": item_basis,
        "bounds": {"min": rmn, "max": rmx, "size": _vec(size), "pivot": pivot_from_aabb(rmn, rmx)},
        "long_axis": _AXES[long_axis],
        "length_m": _r(length),
        "pivot_frac": _r(pivot_frac),
        "tip": tip,
        "butt": butt,
        "muzzle": muzzle,
        "muzzle_source": muzzle_source,
        "grip": grip,
        "grip_r_m": grip_r,
        "grip_source": grip_source,
        "support": support,
        "support_r_m": support_r,
        "support_source": support_source,
        "triangles": int(n_tris),
    }
    out = {"geometry": geometry, "flags": sorted(flags), "reasons": sorted(reasons), "warning": warning}
    if attach_slot is not None:
        out["attach"] = measure_anchor(verts, attach_slot, forward_override, kind=attach_kind,
                                       params=attachment_rules(rules).get("anchor"))
    if with_mounts and eligible(role, kind, hold_class):
        built = build_mounts(glb, glb_node, scale, rules, verts=verts, axes={"forward": forward, "up": up},
                             transformed=transformed, probe=muzzle_probe, overrides=mount_overrides, host_id=host_id, host_pack=host_pack,
                             frame_changed=bool(vote and vote.changed), frame_conflict=bool(vote and vote.conflict),
                             fit_cache=fit_cache, fit_cache_id=fit_cache_id, fused_parts=fused_parts)
        out["mounts"], out["mount_problems"] = built["mounts"], built["problems"]
        out["child_extents"] = built["child_extents"]  # W8c twin evidence: beside the block, never in the record
        out["host_feats"] = {k: built["host_feats"][k] for k in ("s0", "slots", "located")}  # S7: the detectors' features, beside the block
        out["refused_by_located"] = built["refused_by_located"]  # E3 D3 (trace T-fill): the slots refuse_filled refused through its located-part disjunct, for the report's fill_list
        # G1: the vote's state and the pre-vote pass 2 inputs, beside the block. A bow or shield never votes (vote and pre_vote are None):
        # unchanged, no conflict, and pass2_inputs falls back to the measured values (S7 fold-ins 1 and 2)
        out["frame_vote"] = {"changed": vote.changed if vote else False, "conflict": vote.conflict if vote else False, **(pre_vote or {})}
    return out


def measure_weapon(
    glb: Path, glb_node: NodeSel, scale: float, archetype: str, kind: str | None, role: str, rules: dict,
    *, hold_class: str | None = None, genre: str | None = None, forward_override: str | None = None,
) -> dict | None:
    """The spec 4.1 ``geometry`` block as a directory record stores it (``mounts`` included, None for a record that is not
    an eligible host), or None when the mesh cannot be measured (spec 3.3 signature)."""
    detail = measure_weapon_detail(
        glb, glb_node, scale, archetype, kind, role, rules, hold_class=hold_class, genre=genre,
        forward_override=forward_override, with_mounts=True,
    )
    return None if detail["geometry"] is None else {**detail["geometry"], "mounts": detail.get("mounts")}


def pass2_inputs(detail: dict) -> dict | None:
    """What classification pass 2 needs from a measurement (``classify(measured=...)``); None when unmeasured."""
    geo = detail["geometry"]
    if geo is None:
        return None
    # G1: the frame vote never feeds classification, so an eligible host hands over what the bounding-box frame measured (``frame``), not the voted
    # length, fallback flag and reason. Otherwise a kind guessed from the long axis could turn ranged, vote, and turn back (spec 3.3)
    measured = {
        "length_m": geo["length_m"], "forward_by_fallback": "forward_by_fallback" in detail["flags"],
        "axes_unexpected": "axes_unexpected" in detail["reasons"],
    }
    vote = detail.get("frame_vote") or {}  # S7 fold-in 1: renamed from "frame"; a host that skipped the vote has no pre-vote keys
    pre = {k: vote.get(k, measured[k]) for k in measured}
    return {
        "length_m": pre["length_m"],
        "long_axis": geo["long_axis"],  # W7b: the measured fallback for a still-null kind (z -> ranged, else melee); always the bounding-box axis
        "forward_by_fallback": pre["forward_by_fallback"],
        "axes_unexpected": pre["axes_unexpected"],
    }


# -- cache -------------------------------------------------------------------------------------------------


def load_cache(path: Path) -> dict:
    """The geometry cache, or an empty one when absent or unreadable."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return doc if isinstance(doc, dict) else {}


def save_cache(path: Path, cache: dict) -> None:
    write_text_lf(path, json.dumps(cache, sort_keys=True, separators=(",", ":")) + "\n")


def code_digest(data: bytes) -> str:
    """First 12 hex characters of the sha256 of source text with CRLF turned into LF, so a CRLF worktree and the LF blob
    of the same commit agree."""
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()[:12]


# The digest of this file, computed once at import. A cache entry's version is "<WEAPON_GEOMETRY_VERSION>+<digest>", so a
# rule change that forgot the version bump (or an edit between two commits at the same version) rebuilds the entry
# instead of serving stale geometry. It is cache-only: `directory.json` keeps `generated_from.geometry_version` as the
# plain integer (the schema says integer), because the directory must stay byte-identical across machines and a
# digest of the local checkout would not be.
_CODE_DIGEST = code_digest(Path(__file__).read_bytes())
_ATTACH_CODE_DIGEST = code_digest((Path(__file__).parent / "attach.py").read_bytes())  # the anchor algorithm's own digest
_MOUNTS_CODE_DIGEST = code_digest((Path(__file__).parent / "mounts.py").read_bytes())  # and the mount builder's
_PROBE_CODE_DIGEST = code_digest((Path(__file__).parent / "mount_probe.py").read_bytes())  # and the sight seat probe's (A2)


def _inputs_fingerprint(archetype, kind, role, hold_class, genre, rules: dict, forward_override=None,
                        *, head_lead: bool = False, attach_slot: str | None = None,
                        mount_overrides: dict | None = None, host_id: str | None = None, attach_kind: str | None = None,
                        host_pack: str | None = None, frame_axis: str | None = None, fused_key: str | None = None) -> str:
    # the measurement depends on the classification context, not only on the file (spec 3.5 says file + versions;
    # deviation reported): a rules or override change that flips archetype/kind/hold must not serve stale geometry
    fp = {
        "a": archetype, "k": kind, "r": role, "h": hold_class, "g": genre,
        "ax": rules.get("axes_expected"), "gp": rules.get("grip_proportion"),
    }
    if forward_override is not None:
        # the key exists only for an override, so every natural fingerprint (and every cache already on disk) is
        # unchanged, while a natural result is never served for an override or the other way round
        fp["fo"] = forward_override
    if frame_axis is not None:
        # G1 (spec 4.5): the same for the id override that names the frame's axis, so a natural result is never served for it
        fp["fa"] = frame_axis
    if head_lead:
        # same idea for the W7 head-lead tool flag: absent when false, so an unrelated fingerprint is unchanged, and a
        # head-lead result is never served for a record that does not lead with its head (or the other way round)
        fp["hl"] = True
    if attach_slot is not None:
        # same idea for an attachment part (W8a): absent for every other record, so no existing fingerprint changes. The
        # attachment version and the digest of attach.py keep a stale anchor from surviving an algorithm change or a bump
        fp["as"], fp["av"], fp["ad"] = attach_slot, _pkg.WEAPON_ATTACH_VERSION, _ATTACH_CODE_DIGEST
        # A4 (W8l): the anchor now depends on the part's kind (the free-end forward) and on the anchor table (foot ladder, free-end pairs), so
        # both are inputs; a code change moves `ad`, a parameter or kind change moves these two
        fp["ak"], fp["ap"] = attach_kind, attachment_rules(rules).get("anchor")
    if eligible(role, kind, hold_class):
        # W8b: only an eligible host carries mounts, so only its fingerprint changes. The attachment version is read at call
        # time (a bump must miss the cache, AC78) and WEAPON_GEOMETRY_VERSION stays untouched (D-12). The child vocabulary
        # is an input, so an edit to child_tokens / child_never cannot serve a stale mount; so are the two algorithms
        # that make it (anchor of the child, the mount builder) and a categorical override.
        tables = attachment_rules(rules)
        fp["mv"] = {
            "v": _pkg.WEAPON_ATTACH_VERSION, "ad": _ATTACH_CODE_DIGEST, "md": _MOUNTS_CODE_DIGEST,
            "ct": tables.get("child_tokens"), "cn": tables.get("child_never"),
            # A2: the sight seat probe is an input too, its code (pd) and its parameters (sp)
            "pd": _PROBE_CODE_DIGEST, "sp": tables.get("sight_probe"),
            # A3: the excluded-host table and the baked-sight tokens are inputs, and so is the host's name (it decides the exclusion
            # and is the stem the baked-sight detector strips); the detector's code is part of mounts.py (md). Addendum 3 (W8j): `bs` is the
            # whole baked_sights table, so the glass / body / handle lists, the handle height fraction and every fused_post parameter move the
            # key; the fused front post detector itself lives in mount_probe.py (pd) and its caller in mounts.py (md)
            "hn": tables.get("attach_host_never"), "bs": tables.get("baked_sights"), "hi": host_id,
            # A6 (W8n): the host classes (and the slots they refuse) are inputs like `hn`, and so is the host's pack (the key of the per-host receiver
            # tolerance of the sight probe, whose table `sp` already carries)
            "hc": tables.get("attach_host_class"), "kn": tables.get("attach_class_never"), "hp": host_pack,
            # A6 (W8n, Tom 2026-10-24): the hosts that refuse the slots their built-in parts fill are an input like `hc`
            "fh": tables.get("attach_filled_hosts"), "fo": tables.get("attach_filled_open"),
            # A4 (W8l): a child's anchor follows the foot ladder (`ap`, the anchor table), and the mirrored pair lives in mounts.py (`md`).
            # A5 (W8m, item 2) retired the optic seat lift and its `os` input: the mounts source changed, so `md` moves the key
            "ap": tables.get("anchor"),
            # G1 S7 (spec 3.11): rail, flat, muzzle and magazine seats are mounts, so the fit_geometry block (`fg`: every detector literal) and the code
            # of the fit gate (`fd`: the fit_*.py digests, read at call time) are inputs. Geometry and attach versions are `v` and the cache version
            "fg": tables.get("fit_geometry"), "fd": _fit.FIT_CODE_DIGESTS,
        }
        if fused_key is not None:
            fp["mv"]["pk"] = fused_key  # a preset host: the part set the locator searched for (absent on every other host)
        if mount_overrides:
            fp["mv"]["mo"] = mount_overrides
    return digest(fp)


def measure_cached(
    threejs_v2_dir: Path, glb_rel: str, glb_node: NodeSel, scale: float, archetype: str, kind: str | None,
    role: str, rules: dict, cache: dict, *, hold_class: str | None = None, genre: str | None = None,
    forward_override: str | None = None, head_lead: bool = False, attach_slot: str | None = None,
    mount_overrides: dict | None = None, host_id: str | None = None, attach_kind: str | None = None, host_pack: str | None = None,
    frame_axis: str | None = None, fit_cache: dict | None = None, fused_parts: tuple | None = None,
) -> tuple[dict, bool]:
    """``(detail, was_cached)``. Entry id = relative GLB path + node tag + scale tag (as ``glb_measure``); the
    entry is valid while ``mtime:size`` and its version (``WEAPON_GEOMETRY_VERSION`` + the digest of this file) match, and holds one result per
    classification-context fingerprint (which includes ``forward_override``, ``frame_axis``, ``head_lead`` and, for an attachment part, its slot). Failures are cached too (an undecodable mesh stays undecodable); a missing
    file is not. The returned dict is a private copy.
    """
    abs_path = threejs_v2_dir / glb_rel
    key = _cache_key(abs_path)
    if hold_class is None:
        hold_class = (rules.get("hold_by_archetype") or {}).get(archetype, "none") if role == "whole" else "none"
    if key is None:
        return _fail([], None), False
    cache_id = f"{glb_rel}#{node_cache_tag(glb_node)}" if glb_node else glb_rel
    cache_id += scale_cache_tag(scale)
    version = f"{_pkg.WEAPON_GEOMETRY_VERSION}+{_CODE_DIGEST}"
    fp = _inputs_fingerprint(archetype, kind, role, hold_class, genre, rules, forward_override, head_lead=head_lead,
                             attach_slot=attach_slot, mount_overrides=mount_overrides, host_id=host_id, attach_kind=attach_kind,
                             host_pack=host_pack, frame_axis=frame_axis, fused_key=fused_parts[0] if fused_parts else None)
    entry = cache.get(cache_id)
    if not entry or entry.get("key") != key or entry.get("version") != version:
        entry = {"key": key, "version": version, "by_inputs": {}}
        cache[cache_id] = entry
    hit = entry["by_inputs"].get(fp)
    if hit is not None:
        return deepcopy(hit), True
    detail = measure_weapon_detail(
        abs_path, glb_node, scale, archetype, kind, role, rules, hold_class=hold_class, genre=genre,
        forward_override=forward_override, head_lead=head_lead, attach_slot=attach_slot, mount_overrides=mount_overrides,
        with_mounts=True, host_id=host_id, attach_kind=attach_kind, host_pack=host_pack, frame_axis=frame_axis,
        fit_cache=fit_cache, fit_cache_id=cache_id, fused_parts=fused_parts,
    )
    entry["by_inputs"][fp] = deepcopy(detail)
    return detail, False


# -- settle to contact, per pair (A5, W8m; spec 5.4) ---------------------------------------------------------------------------

_SETTLE_MEMO_HOSTS = 2  # decoded host meshes kept while a build walks the pairs host by host
_SETTLE_MEMO_PARTS = 512  # sampled part meshes kept (a few thousand points each)


def _glb_ids(files: dict) -> tuple[str, NodeSel, float, str]:
    """``(relative path, node selection, scale, cache id)`` of a record's ``files``; the id is the one ``measure_cached`` uses."""
    glb, node, scale = files["glb"], files.get("glb_node") or None, float(files.get("glb_scale") or 1.0)
    return glb, node, scale, (f"{glb}#{node_cache_tag(node)}" if node else glb) + scale_cache_tag(scale)


def _settle_meshes(root: Path, part_files: dict, host_files: dict, hide: list[str], pitch: float, memo: dict):
    """``(part surface samples, host vertices, host triangles)`` or None when a mesh cannot be read. The caller's ``memo`` keeps the last host
    meshes and the sampled parts of one build, so a post-pass that walks host by host decodes each host once."""
    parts, hosts = memo.setdefault("parts", {}), memo.setdefault("hosts", {})
    p_glb, p_node, p_scale, _ = _glb_ids(part_files)
    h_glb, h_node, h_scale, _ = _glb_ids(host_files)
    pk = (str(root / p_glb), node_cache_tag(p_node), p_scale, pitch)
    if pk not in parts:
        got = load_triangles(root / p_glb, p_node, exclude=_collision, scale=p_scale)
        samples = None
        if got is not None and len(got[0]) and len(got[1]) and np.isfinite(got[0]).all():
            samples = surface_samples(np.asarray(got[0], dtype=np.float64), np.asarray(got[1]), pitch)
        if len(parts) >= _SETTLE_MEMO_PARTS:
            parts.pop(next(iter(parts)))
        parts[pk] = samples
    hk = (str(root / h_glb), node_cache_tag(h_node), h_scale, tuple(hide))
    if hk not in hosts:
        drop = frozenset(hide)
        got = load_triangles(root / h_glb, h_node, exclude=lambda n: _collision(n) or n in drop, scale=h_scale)
        mesh = None
        if got is not None and len(got[0]) and len(got[1]) and np.isfinite(got[0]).all():
            mesh = (np.asarray(got[0], dtype=np.float64), np.asarray(got[1], dtype=np.int64))
        while len(hosts) >= _SETTLE_MEMO_HOSTS:
            hosts.pop(next(iter(hosts)))
        hosts[hk] = mesh
    if parts[pk] is None or hosts[hk] is None:
        return None
    return parts[pk], hosts[hk][0], hosts[hk][1]


def settle_cached(
    threejs_v2_dir: Path, part_files: dict, host_files: dict, anchor: dict, mount: dict, hide: list[str], slot: str,
    params: dict, cache: dict, memo: dict | None = None,
) -> tuple[float | None, str]:
    """``(seat_shift_m, how)`` of one pair (``attach.settle_pair``), ``how`` being ``cached``, ``computed`` or ``unavailable`` (a file is
    missing or undecodable: nothing is stored, the caller keeps whatever it had).

    The pair is cached beside the measurements, in the same ``cache`` dict: entry id ``pair|<part id>|<host id>`` (the ids of ``measure_cached``),
    valid while both files' ``mtime:size`` and the version (``WEAPON_GEOMETRY_VERSION`` + the digest of this file) match, one result per
    fingerprint of the pair's inputs: the part's anchor, the mount frame, the hidden nodes, the slot, the ``contact`` table, the attach version
    and the digests of ``attach.py`` (the rule) and ``mount_probe.py`` (the sampler). A cache hit therefore equals a recompute (AC78), and a
    build with nothing changed reads no mesh. A "no key" result is cached too (``shift`` null)."""
    memo = memo if memo is not None else {}
    p_glb, _, _, p_id = _glb_ids(part_files)
    h_glb, _, _, h_id = _glb_ids(host_files)
    p_key, h_key = _cache_key(threejs_v2_dir / p_glb), _cache_key(threejs_v2_dir / h_glb)
    if p_key is None or h_key is None:
        return None, "unavailable"
    cache_id, key = f"pair|{p_id}|{h_id}", f"{p_key}+{h_key}"
    version = f"{_pkg.WEAPON_GEOMETRY_VERSION}+{_CODE_DIGEST}"
    fp = digest({
        "slot": slot, "an": anchor, "mt": {k: mount[k] for k in ("point", "forward", "up")}, "hide": list(hide), "ct": params,
        "av": _pkg.WEAPON_ATTACH_VERSION, "ad": _ATTACH_CODE_DIGEST, "pd": _PROBE_CODE_DIGEST,
    })
    entry = cache.get(cache_id)
    if not entry or entry.get("key") != key or entry.get("version") != version:
        entry = {"key": key, "version": version, "by_inputs": {}}
        cache[cache_id] = entry
    hit = entry["by_inputs"].get(fp)
    if hit is not None:
        return hit.get("shift"), "cached"
    meshes = _settle_meshes(threejs_v2_dir, part_files, host_files, list(hide), float(params["pitch_m"]), memo)
    if meshes is None:
        return None, "unavailable"
    samples, host_v, host_t = meshes
    m = place(anchor, mount)  # the A4 placement; the shift is measured from there
    _, shift = settle_pair(samples @ m[:3, :3].T + m[:3, 3], host_v, host_t, mount["up"], params)
    entry["by_inputs"][fp] = {"shift": shift}
    return shift, "computed"


# -- the silencer seat, per host (A6, W8n; spec 13.7 A6-2) ------------------------------------------------------------------------


def _muzzle_samples(root: Path, host_files: dict, hide: list[str], pitch: float, memo: dict):
    """The host's render mesh (collision nodes and the ``hide`` nodes dropped) sampled every ``pitch`` metres, or None when it cannot be read.
    The caller's ``memo`` keeps the last host meshes of one build, so a pass that walks host by host decodes each host once."""
    hosts = memo.setdefault("muzzle_hosts", {})
    h_glb, h_node, h_scale, _ = _glb_ids(host_files)
    hk = (str(root / h_glb), node_cache_tag(h_node), h_scale, tuple(hide), pitch)
    if hk not in hosts:
        drop = frozenset(hide)
        got = load_triangles(root / h_glb, h_node, exclude=lambda n: _collision(n) or n in drop, scale=h_scale)
        samples = None
        if got is not None and len(got[0]) and len(got[1]) and np.isfinite(got[0]).all():
            samples = surface_samples(np.asarray(got[0], dtype=np.float64), np.asarray(got[1]), pitch)
        while len(hosts) >= _SETTLE_MEMO_HOSTS:
            hosts.pop(next(iter(hosts)))
        hosts[hk] = samples
    return hosts[hk]


def muzzle_stub_cached(
    threejs_v2_dir: Path, host_files: dict, mount: dict, hide: list[str], params: dict, cache: dict, memo: dict | None = None,
) -> tuple[dict | None, str]:
    """``(result, how)`` of one host's muzzle end: ``result`` is ``{"stub": metres, "dev": metres}`` (``attach.muzzle_stub``) or None when the host has
    no barrel to read; ``how`` is ``cached``, ``computed`` or ``unavailable`` (the file is missing or undecodable: nothing is stored, the caller
    keeps whatever it had).

    The result is the host's alone (every suppressor on it shares it; the part only brings its length), so it is cached beside the measurements, in
    the same ``cache`` dict: entry id ``muz|<host id>`` (the id of ``measure_cached``), valid while the file's ``mtime:size`` and the version
    (``WEAPON_GEOMETRY_VERSION`` + the digest of this file) match, one result per fingerprint of the question: the mount's point and up, the hidden
    nodes, the ``muzzle_seat`` table, the attach version and the digests of ``attach.py`` (the silhouette) and ``mount_probe.py`` (the sampler). A cache
    hit therefore equals a recompute, and a build with nothing changed reads no mesh. A "no barrel" result is cached too (``null``)."""
    memo = memo if memo is not None else {}
    h_glb, _, _, h_id = _glb_ids(host_files)
    h_key = _cache_key(threejs_v2_dir / h_glb)
    if h_key is None:
        return None, "unavailable"
    cache_id = f"muz|{h_id}"
    version = f"{_pkg.WEAPON_GEOMETRY_VERSION}+{_CODE_DIGEST}"
    fp = digest({
        "mt": {k: mount[k] for k in ("point", "up")}, "hide": list(hide), "ms": params,
        "av": _pkg.WEAPON_ATTACH_VERSION, "ad": _ATTACH_CODE_DIGEST, "pd": _PROBE_CODE_DIGEST,
    })
    entry = cache.get(cache_id)
    if not entry or entry.get("key") != h_key or entry.get("version") != version:
        entry = {"key": h_key, "version": version, "by_inputs": {}}
        cache[cache_id] = entry
    if fp in entry["by_inputs"]:
        return deepcopy(entry["by_inputs"][fp]), "cached"
    samples = _muzzle_samples(threejs_v2_dir, host_files, list(hide), float(params["sample_pitch_m"]), memo)
    if samples is None:
        return None, "unavailable"
    got = muzzle_stub(muzzle_silhouette(samples, mount["point"], mount["up"], params), params)
    result = None if got is None else {"stub": got[0], "dev": got[1]}
    entry["by_inputs"][fp] = deepcopy(result)
    return result, "computed"
