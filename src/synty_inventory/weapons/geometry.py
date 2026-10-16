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

import json
import math
from copy import deepcopy
from pathlib import Path

import numpy as np

from .. import weapons as _pkg  # read WEAPON_GEOMETRY_VERSION at call time (a test may bump it)
from ..naming import SKIP_STEM_RE
from ..schema import pivot_from_aabb
from ..sources.glb_geometry import load_triangles, node_world_matrices
from ..sources.glb_measure import NodeSel, _cache_key, node_cache_tag, node_selected, read_glb_json
from ..sources.glb_scale import scale_cache_tag
from . import digest, write_text_lf

CACHE_NAME = "_geometry_cache.json"

_AXES = "xyz"
_TIE = 0.05  # long-axis tie band (spec 3.5.2)
_PIVOT_BAND = 0.10  # |origin_frac - 0.5| below this: the origin is "near the middle"
_END_FRAC = 0.10  # outer share of the length compared by the cross-section fallback
_TIP_MM = 0.002  # tip / butt: vertices within 2 mm of the extreme forward coordinate
_BIN_M = 0.01  # handle detection bin height
_HANDLE_MIN_BINS = 6  # a handle run is >= 6 cm
_HANDLE_BUTT_FRAC = 0.60  # handle is searched in the butt-side 60 % of the length
_HANDLE_E_RATIO = 1.3  # e <= 1.3 * p10(e)
_SUPPORT_AT = 0.62
_SUPPORT_SLICE_M = 0.01
_MUZZLE_TOLS_M = (0.001, 0.002, 0.005, 0.010)  # sit_weapons FACE_TOLS_M
_MUZZLE_SNAP_M = 0.0001
_MUZZLE_MIN_POINTS = 3
_MUZZLE_HEIGHT_FRAC = 0.75
_OUTSIDE_EPS = 1e-4  # the origin counts as inside the AABB within the rounding unit
_HEADED = ("axe", "mace", "hammer", "club")  # the larger end is the working end; every other archetype is pointed
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
        mean = np.mean(np.array(list(face.values())), axis=0)
        pt[:] = mean
        pt[fa] = fs * max_f
        return _vec(pt), "face"
    side = 3 - fa - ua  # the lateral axis that is not up
    pt[side] = (bmin[side] + bmax[side]) * 0.5
    uc_min = float(us * bmax[ua] if us < 0 else bmin[ua])
    uc_max = float(us * bmin[ua] if us < 0 else bmax[ua])
    # signed up coordinate: min_up + 0.75 * up_extent, mapped back to the axis
    pt[ua] = us * (uc_min + _MUZZLE_HEIGHT_FRAC * (uc_max - uc_min))
    pt[fa] = fs * max_f
    return _vec(pt), "bounds_fallback"


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


def _fail(reasons: list[str], warning: str | None = None) -> dict:
    return {"geometry": None, "flags": [], "reasons": sorted(set(reasons) | {"no_geometry"}), "warning": warning}


def measure_weapon_detail(
    glb: Path, glb_node: NodeSel, scale: float, archetype: str, kind: str | None, role: str, rules: dict,
    *, hold_class: str | None = None, genre: str | None = None, forward_override: str | None = None,
) -> dict:
    """``{'geometry': block | None, 'flags': [...], 'reasons': [...], 'warning': str | None}`` (spec 3.5).

    ``flags``/``reasons`` hold only what the measurement adds (``forward_by_fallback``, ``origin_outside_bounds``;
    ``axes_unexpected``, ``muzzle_fallback``, ``origin_outside_bounds``, ``node_transform``) -- or, when the mesh
    cannot be measured, the failure (``no_geometry``, plus ``degenerate`` for a zero-extent mesh). A node that is not
    in the GLB is an undecodable mesh with a ``warning``. Never copies geometry from anywhere (INV-6).

    ``forward_override`` (spec 4.5, W2e: a signed axis such as ``"+z"``, from an id override's ``forward``) replaces
    the forward SIGN once the mesh has decided its own, when its axis equals the measured forward axis: the source
    becomes ``override`` and every sign-derived value follows as if the mesh had decided that sign natively. The
    fallback flag the natural sign may have carried goes (the sign is no longer a guess); ``axes_unexpected`` is still
    judged from the final sign. A different axis is not applied: the measurement stays natural and ``warning`` says so.
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
            else:
                fs = _section_sign(verts, fa, mn[fa], size[fa], archetype in _HEADED)
                f_src = "section"
                flags.add("forward_by_fallback")
                if kind == "ranged" and role == "whole":
                    fs = _ranged_convention_sign(rules, genre, kind, fa, fs)
            if kind == "ranged":
                ua, us, u_src = (2 if fa == 1 else 1), 1, "fixed"
            else:
                rest = [i for i in range(3) if i != fa]
                ua = max(rest, key=lambda i: (size[i], -i))  # widest remaining axis; ties go to the earlier axis
                us, u_src = 1, "width_axis"
    warning = None
    if forward_override is not None:
        o_axis, o_sign = _parse_axis(forward_override)
        if o_axis == fa:
            fs, f_src = o_sign, "override"
            flags.discard("forward_by_fallback")
        else:
            warning = (f"forward override {forward_override!r} ignored: its axis is not the measured forward axis "
                       f"({_sig(fa, fs)})")
    forward, up = _sig(fa, fs), _sig(ua, us)
    basis = np.cross(_unit(ua, us), _unit(fa, fs))
    item_basis = [[int(round(c)) for c in row] for row in (basis, _unit(ua, us), _unit(fa, fs))]

    expected = ((rules.get("axes_expected") or {}).get(genre) or {}).get(kind) if genre and kind else None
    if expected and not is_bow and forward != expected:
        reasons.add("axes_unexpected")

    # --- length, tip, butt, pivot (3.5.3) ---
    fc = fs * verts[:, fa]
    fmin, fmax = float(fc.min()), float(fc.max())
    flen = fmax - fmin
    length = float(size[long_axis])
    tip = None
    if kind != "ranged":
        tip = _vec(verts[fc >= fmax - _TIP_MM - 1e-9].mean(axis=0))
    butt = _vec(verts[fc <= fmin + _TIP_MM + 1e-9].mean(axis=0))
    pivot_frac = _frac(0.0, mn[long_axis], size[long_axis])

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
        run = _find_handle(verts, fa, fc, fmin, flen)
        if run is not None:
            grip, grip_r, grip_source = at(run[0], run[1]), _r(run[2]), "handle"
        elif not outside:
            # no handle run: the origin projected onto the weapon's long axis (the line through the bounds centre)
            grip, grip_source = at(float(fs * origin[fa]), {}), "pivot"
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
    return {"geometry": geometry, "flags": sorted(flags), "reasons": sorted(reasons), "warning": warning}


def measure_weapon(
    glb: Path, glb_node: NodeSel, scale: float, archetype: str, kind: str | None, role: str, rules: dict,
    *, hold_class: str | None = None, genre: str | None = None, forward_override: str | None = None,
) -> dict | None:
    """The spec 4.1 ``geometry`` block, or None when the mesh cannot be measured (spec 3.3 signature)."""
    return measure_weapon_detail(
        glb, glb_node, scale, archetype, kind, role, rules, hold_class=hold_class, genre=genre,
        forward_override=forward_override,
    )["geometry"]


def pass2_inputs(detail: dict) -> dict | None:
    """What classification pass 2 needs from a measurement (``classify(measured=...)``); None when unmeasured."""
    geo = detail["geometry"]
    if geo is None:
        return None
    return {
        "length_m": geo["length_m"],
        "forward_by_fallback": "forward_by_fallback" in detail["flags"],
        "axes_unexpected": "axes_unexpected" in detail["reasons"],
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


def _inputs_fingerprint(archetype, kind, role, hold_class, genre, rules: dict, forward_override=None) -> str:
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
    return digest(fp)


def measure_cached(
    threejs_v2_dir: Path, glb_rel: str, glb_node: NodeSel, scale: float, archetype: str, kind: str | None,
    role: str, rules: dict, cache: dict, *, hold_class: str | None = None, genre: str | None = None,
    forward_override: str | None = None,
) -> tuple[dict, bool]:
    """``(detail, was_cached)``. Entry id = relative GLB path + node tag + scale tag (as ``glb_measure``); the
    entry is valid while ``mtime:size`` and ``WEAPON_GEOMETRY_VERSION`` match, and holds one result per
    classification-context fingerprint (which includes ``forward_override``). Failures are cached too (an undecodable mesh stays undecodable); a missing
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
    version = _pkg.WEAPON_GEOMETRY_VERSION
    fp = _inputs_fingerprint(archetype, kind, role, hold_class, genre, rules, forward_override)
    entry = cache.get(cache_id)
    if not entry or entry.get("key") != key or entry.get("version") != version:
        entry = {"key": key, "version": version, "by_inputs": {}}
        cache[cache_id] = entry
    hit = entry["by_inputs"].get(fp)
    if hit is not None:
        return deepcopy(hit), True
    detail = measure_weapon_detail(
        abs_path, glb_node, scale, archetype, kind, role, rules, hold_class=hold_class, genre=genre,
        forward_override=forward_override,
    )
    entry["by_inputs"][fp] = deepcopy(detail)
    return detail, False
