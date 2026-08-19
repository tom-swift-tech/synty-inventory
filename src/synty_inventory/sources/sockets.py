"""Ship-kit mating faces ("sockets") from mesh analysis.

Synty's ``SM_Veh_Part_*`` pieces carry no attach-point empties — the GLB is
a single mesh node — so where a cockpit meets a hull is only knowable from
the geometry: the parts are built with flat, axis-aligned mating caps (a
cockpit's rear face, an engine's front face, a hull's six end/side faces).
This module finds those caps:

1. decode the exact triangles (``glb_geometry.load_triangles``),
2. for each of the six axis directions, collect triangles whose normal
   points that way and group them into coplanar clusters,
3. keep the largest cluster that lies in the outer band of the part on
   that axis (the outward-facing cap), if it is big enough to be a
   deliberate mating face and not a greeble flange.

Per part class (``part.mates_axis`` from the rules) that yields

* ``part.mount`` — the single face this part uses to attach to its parent
  (cockpit → its -Z cap, engine → +Z, landing gear → +Y, wing → the root
  side, greeble → its largest flat face), and
* ``part.sockets`` — for hull/body parts, one entry per axis face that
  children can mate to (``front``/``rear``/``left``/``right``/``top``/
  ``bottom``).

All positions are in the same local space as ``bounds`` (GLB local, Y-up,
metres, origin = the prefab pivot). To attach child to parent:
``child_pos = parent_pos + socket.position - child.mount.position`` with
the child oriented so ``mount.normal == -socket.normal``. Parts are
unrotated by default, so the class conventions above already line up
(cockpit -Z cap ↔ body +Z/front socket).

Everything here is a ``source: measured`` derivation; when the mesh can't
be decoded the fields stay null and ``mates_axis`` remains the only hint.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .glb_geometry import load_triangles
from .glb_measure import _cache_key

SOCKETS_VERSION = 1  # bump to invalidate cached analyses when the algorithm changes

AXIS_DIRS: dict[str, tuple[int, float]] = {
    "+x": (0, 1.0),
    "-x": (0, -1.0),
    "+y": (1, 1.0),
    "-y": (1, -1.0),
    "+z": (2, 1.0),
    "-z": (2, -1.0),
}
SOCKET_ROLE_BY_AXIS = {"+z": "front", "-z": "rear", "+x": "right", "-x": "left", "+y": "top", "-y": "bottom"}
_OPPOSITE = {"+x": "-x", "-x": "+x", "+y": "-y", "-y": "+y", "+z": "-z", "-z": "+z"}

_FACING_COS = 0.985  # ~10 degrees: Synty caps are flat but not always axis-perfect
_OUTER_BAND = 0.30  # mating caps sit in the outer 30 % of the part on that axis
_MIN_FIT = 0.01  # cap area must cover >= 1 % of the AABB cross-section
_MIN_AREA = 0.002  # ... and be at least 20 cm^2 in absolute terms


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    n[n == 0] = 1.0
    return v / n


def planar_caps(verts: np.ndarray, tris: np.ndarray, axis: str) -> list[dict[str, Any]]:
    """Coplanar clusters of triangles facing ``axis``, outermost first.

    Each cluster: ``{"offset", "area", "centroid", "extent"}`` where
    ``extent`` is the in-plane bounding-box size over the two other axes
    (in xyz order)."""
    ai, sign = AXIS_DIRS[axis]
    p0, p1, p2 = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    cross = np.cross(p1 - p0, p2 - p0)
    area2 = np.linalg.norm(cross, axis=1)
    keep = area2 > 1e-12
    if not keep.any():
        return []
    normals = _unit(cross[keep])
    areas = area2[keep] * 0.5
    tri_idx = np.nonzero(keep)[0]
    facing = normals[:, ai] * sign >= _FACING_COS
    if not facing.any():
        return []
    sel = tri_idx[facing]
    areas = areas[facing]
    cent = (verts[tris[sel, 0]] + verts[tris[sel, 1]] + verts[tris[sel, 2]]) / 3.0
    offs = cent[:, ai]
    extent_axis = float(verts[:, ai].max() - verts[:, ai].min())
    tol = 0.01 + 0.002 * extent_axis
    order = np.argsort(-offs * sign)  # outermost first
    clusters: list[dict[str, Any]] = []
    cur: list[int] = []
    cur_off = None
    others = [k for k in range(3) if k != ai]

    def flush() -> None:
        if not cur:
            return
        idx = np.array(cur)
        a = areas[idx]
        total = float(a.sum())
        c = (cent[idx] * a[:, None]).sum(axis=0) / total
        vs = verts[tris[sel[idx]].reshape(-1)]
        ext = [float(vs[:, k].max() - vs[:, k].min()) for k in others]
        clusters.append(
            {
                "offset": float((offs[idx] * a).sum() / total),
                "area": total,
                "centroid": [float(x) for x in c],
                "extent": ext,
                "tris": int(len(idx)),
            }
        )

    for j in order:
        o = float(offs[j])
        if cur_off is None or abs(o - cur_off) <= tol:
            cur.append(int(j))
            cur_off = o if cur_off is None else cur_off
        else:
            flush()
            cur = [int(j)]
            cur_off = o
    flush()
    return clusters


def _best_cap(
    verts: np.ndarray, tris: np.ndarray, axis: str, mn: np.ndarray, mx: np.ndarray
) -> dict[str, Any] | None:
    """Largest deliberate-looking cap in the outer band on ``axis``."""
    ai, sign = AXIS_DIRS[axis]
    extent = float(mx[ai] - mn[ai])
    others = [k for k in range(3) if k != ai]
    cross_section = float((mx[others[0]] - mn[others[0]]) * (mx[others[1]] - mn[others[1]]))
    outer = (mx[ai] if sign > 0 else mn[ai]) - sign * max(0.05, _OUTER_BAND * extent)
    best = None
    for cap in planar_caps(verts, tris, axis):
        if (cap["offset"] - outer) * sign < 0:
            break  # clusters come outermost-first; past the band now
        fit = cap["area"] / cross_section if cross_section > 0 else 0.0
        if cap["area"] < _MIN_AREA or fit < _MIN_FIT:
            continue
        if best is None or cap["area"] > best["area"]:
            best = dict(cap, fit=fit)
    return best


def _face_record(axis: str, cap: dict[str, Any]) -> dict[str, Any]:
    ai, sign = AXIS_DIRS[axis]
    normal = [0.0, 0.0, 0.0]
    normal[ai] = sign
    return {
        "axis": axis,
        "position": [round(v, 4) for v in cap["centroid"]],
        "normal": normal,
        "area": round(cap["area"], 4),
        "extent": [round(v, 4) for v in cap["extent"]],
        "fit": round(min(cap["fit"], 1.0), 3),
        "source": "measured",
    }


def _mount_axes(part_class: str | None, mates_axis: str | None, mn: np.ndarray, mx: np.ndarray) -> list[str]:
    """Which outward faces may be the part's own attachment face. The
    rules' ``mates_axis`` names the PARENT socket the part goes on, so the
    part's own cap faces the opposite way."""
    if part_class == "body":
        return []
    if mates_axis in AXIS_DIRS:
        return [_OPPOSITE[mates_axis]]
    if mates_axis in ("±x", "+-x", "x"):
        lo, hi = abs(float(mn[0])), abs(float(mx[0]))
        span = max(lo, hi)
        if span > 0 and min(lo, hi) / span >= 0.8:
            # full-span wing straddling the hull: it sits on/under the hull
            return ["+y", "-y"]
        return ["+x", "-x"]
    # "any": greebles mate by their largest flat face; base (-Y) first so the
    # AABB fallback lands on the underside when no cap is found.
    return ["-y", "+y", "-z", "+z", "-x", "+x"]


def _aabb_face(axis: str, mn: np.ndarray, mx: np.ndarray) -> dict[str, Any]:
    """Fallback when no flat cap exists on ``axis`` (rounded hull ends,
    airfoil wings): the AABB face centre, flagged ``source: aabb`` so a
    consumer can tell it from a measured cap."""
    ai, sign = AXIS_DIRS[axis]
    centre = (mn + mx) / 2.0
    centre[ai] = mx[ai] if sign > 0 else mn[ai]
    normal = [0.0, 0.0, 0.0]
    normal[ai] = sign
    others = [k for k in range(3) if k != ai]
    return {
        "axis": axis,
        "position": [round(float(v), 4) for v in centre],
        "normal": normal,
        "area": None,
        "extent": [round(float(mx[k] - mn[k]), 4) for k in others],
        "fit": 0.0,
        "source": "aabb",
    }


def analyse_part(verts: np.ndarray, tris: np.ndarray, part_class: str | None, mates_axis: str | None) -> dict[str, Any]:
    """``{"mount": {...}|None, "sockets": [...]}`` for one decoded mesh.

    Child classes always get a mount (measured cap, else the AABB face on
    their preferred axis); body parts always get six sockets (measured
    where a cap exists, AABB face centre otherwise)."""
    mn = verts.min(axis=0)
    mx = verts.max(axis=0)
    axes = _mount_axes(part_class, mates_axis, mn, mx)
    mount = None
    for axis in axes:
        cap = _best_cap(verts, tris, axis, mn, mx)
        if cap is None:
            continue
        if mount is None or cap["area"] > mount[1]["area"]:
            mount = (axis, cap)
    mount_rec = _face_record(mount[0], mount[1]) if mount else (_aabb_face(axes[0], mn, mx) if axes else None)
    sockets = []
    if part_class == "body":
        for axis in AXIS_DIRS:
            cap = _best_cap(verts, tris, axis, mn, mx)
            rec = _face_record(axis, cap) if cap is not None else _aabb_face(axis, mn, mx)
            sockets.append(dict(rec, role=SOCKET_ROLE_BY_AXIS[axis]))
    return {"mount": mount_rec, "sockets": sockets}


def analyse_cached(
    threejs_v2_dir: Path,
    glb_rel: str,
    part_class: str | None,
    mates_axis: str | None,
    cache: dict[str, Any],
    node_name: str | None = None,
) -> dict[str, Any] | None:
    """Run ``analyse_part`` on a GLB through the shared measure cache
    (keyed like the AABB entries plus ``#sockets`` and the algorithm
    version / class inputs, so rule changes re-analyse)."""
    abs_path = threejs_v2_dir / glb_rel
    key = _cache_key(abs_path)
    if key is None:
        return None
    cache_id = f"{glb_rel}#{node_name}#sockets" if node_name else f"{glb_rel}#sockets"
    full_key = f"{key}:v{SOCKETS_VERSION}:{part_class}:{mates_axis}"
    entry = cache.get(cache_id)
    if entry and entry.get("key") == full_key:
        return entry.get("result")
    geo = load_triangles(abs_path, node_name)
    result = analyse_part(geo[0], geo[1], part_class, mates_axis) if geo else None
    cache[cache_id] = {"key": full_key, "result": result}
    return result


def apply_part_sockets(
    asset: dict,
    threejs_v2_dir: Path | None,
    cache: dict[str, Any],
    stats: dict[str, int],
) -> None:
    """Fill ``asset['part']['mount']`` / ``['sockets']`` for ship-kit parts
    that have a GLB; leaves both null otherwise."""
    part = asset.get("part")
    if not isinstance(part, dict) or not part.get("class"):
        return
    part.setdefault("mount", None)
    part.setdefault("sockets", None)
    glb_rel = (asset.get("files") or {}).get("glb")
    if not glb_rel or threejs_v2_dir is None:
        stats["sockets_missing_glb"] = stats.get("sockets_missing_glb", 0) + 1
        return
    result = analyse_cached(
        threejs_v2_dir, glb_rel, part.get("class"), part.get("mates_axis"), cache,
        node_name=(asset.get("files") or {}).get("glb_node"),
    )
    if result is None:
        stats["sockets_failed"] = stats.get("sockets_failed", 0) + 1
        return
    part["mount"] = result.get("mount")
    part["sockets"] = result.get("sockets") or []
    stats["sockets_analysed"] = stats.get("sockets_analysed", 0) + 1
    if (part["mount"] or {}).get("source") == "aabb":
        stats["sockets_mount_aabb"] = stats.get("sockets_mount_aabb", 0) + 1
