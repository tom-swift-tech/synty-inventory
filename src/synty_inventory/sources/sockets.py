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

Two conventions of the kit override the class axis (observed on the
decoded meshes, 2026-08):

* **Pivot at the mating plane.** Where a part's pivot is off-centre it
  sits on the attachment face — ``Engine_08/09`` are pylon pods whose
  pivot lies on the +X plate, not behind the nozzle. A measured cap whose
  plane passes close to the pivot therefore wins over the class axis on
  any face (``Engine_08.mount.axis == "+x"``; it fits the hull's ``left``
  socket unrotated, the mirrored copy the ``right``).
* **Wings are single root-at-X pieces**, pivots centred, with a dihedral
  on many of them — the root cap may be tilted up to ~30 deg off ±X. The
  root is the dominant ±X cap (a fin has two equal side faces and mounts
  by its top/bottom instead); ``mount.normal`` is the cap's real normal
  (``axis`` is the nearest axis).

``mount.parent_role`` names the hull socket the part fits **unrotated**
(the socket opposite the mount axis); greebles may be rotated onto any
socket by aligning ``mount.normal`` to ``-socket.normal``. Tilted wing
roots are *not* meant to be rotated flush — place by position only, the
tilt is the dihedral.

All positions are in the same local space as ``bounds`` (GLB local, Y-up,
metres, origin = the prefab pivot). To attach child to parent:
``child_pos = parent_pos + socket.position - child.mount.position`` with
the child oriented so ``mount.normal == -socket.normal`` (identity for
the class conventions above: cockpit -Z cap ↔ body +Z/front socket).

Everything here is a ``source: measured`` derivation; when the mesh can't
be decoded the fields stay null and ``mates_axis`` remains the only hint.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .glb_geometry import load_triangles
from .glb_measure import _cache_key

SOCKETS_VERSION = 2  # bump to invalidate cached analyses when the algorithm changes

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
_WING_ROOT_COS = 0.866  # ~30 degrees: wing roots carry the dihedral tilt
_SNAP_COS = 0.9998  # within ~1 degree: report the exact axis as the normal
_AXIS_TRUE_COS = 0.9962  # within ~5 degrees: a mating face, not a sloped body panel
_OUTER_BAND = 0.30  # mating caps sit in the outer 30 % of the part on that axis
_MIN_FIT = 0.01  # cap area must cover >= 1 % of the AABB cross-section
_MIN_AREA = 0.002  # ... and be at least 20 cm^2 in absolute terms
_PIVOT_PLANE = 0.20  # a cap within 20 % of the axis extent of the pivot is "at the pivot"
_PIVOT_MIN_RATIO = 0.5  # ... and must reach half the best fit of any face to count
_WING_ROOT_RATIO = 0.8  # ±x caps closer than this in fit are a symmetric fin, not root/tip

# Faces a part may attach with, per class: the rules' ``mates_axis`` names
# the PARENT socket, so the part's own cap faces the opposite way. Wings and
# greebles have their own selection logic (see ``_choose_mount``).
_CLASS_MOUNT_AXES: dict[str, list[str]] = {
    "cockpit": ["-z"],
    "engine": ["+z"],
    "landing_gear": ["+y"],
    "gear": ["+y"],
}


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    n[n == 0] = 1.0
    return v / n


def planar_caps(
    verts: np.ndarray, tris: np.ndarray, axis: str, facing_cos: float = _FACING_COS
) -> list[dict[str, Any]]:
    """Coplanar clusters of triangles facing ``axis`` (within the
    ``facing_cos`` cone), outermost first.

    Each cluster: ``{"offset", "area", "centroid", "extent", "normal",
    "tris"}`` where ``offset`` is the area-weighted centroid coordinate
    along the axis, ``extent`` the in-plane bounding-box size over the two
    other axes (in xyz order) and ``normal`` the cluster's unit normal
    (the exact axis when it is within ~1 degree of it)."""
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
    facing = normals[:, ai] * sign >= facing_cos
    if not facing.any():
        return []
    sel = tri_idx[facing]
    areas = areas[facing]
    normals = normals[facing]
    cent = (verts[tris[sel, 0]] + verts[tris[sel, 1]] + verts[tris[sel, 2]]) / 3.0
    offs = cent[:, ai]
    extent_axis = float(verts[:, ai].max() - verts[:, ai].min())
    tol = 0.01 + 0.002 * extent_axis
    order = np.argsort(-offs * sign)  # outermost first
    others = [k for k in range(3) if k != ai]
    axis_normal = np.zeros(3)
    axis_normal[ai] = sign

    # Greedy plane clustering: a triangle joins the first open cluster whose
    # plane it lies on (same normal within the cone tolerance, centroid
    # within ``tol`` of the plane), else opens a new one. Outermost-first
    # order keeps the result list sorted the way ``_best_cap`` wants.
    clusters: list[dict[str, Any]] = []
    for j in order:
        n, c = normals[j], cent[j]
        for cl in clusters:
            if float(n @ cl["n"]) >= _FACING_COS and abs(float((c - cl["c"]) @ cl["n"])) <= tol:
                cl["idx"].append(int(j))
                break
        else:
            clusters.append({"n": n, "c": c, "idx": [int(j)]})

    out: list[dict[str, Any]] = []
    for cl in clusters:
        idx = np.array(cl["idx"])
        a = areas[idx]
        total = float(a.sum())
        c = (cent[idx] * a[:, None]).sum(axis=0) / total
        n = _unit((normals[idx] * a[:, None]).sum(axis=0))
        if float(n @ axis_normal) >= _SNAP_COS:
            n = axis_normal
        vs = verts[tris[sel[idx]].reshape(-1)]
        out.append(
            {
                "offset": float((offs[idx] * a).sum() / total),
                "area": total,
                "centroid": [float(x) for x in c],
                "extent": [float(vs[:, k].max() - vs[:, k].min()) for k in others],
                "normal": [float(x) for x in n],
                "tris": int(len(idx)),
            }
        )
    return out


def _best_cap(
    verts: np.ndarray,
    tris: np.ndarray,
    axis: str,
    mn: np.ndarray,
    mx: np.ndarray,
    facing_cos: float = _FACING_COS,
) -> dict[str, Any] | None:
    """Largest deliberate-looking cap in the outer band on ``axis``; adds
    ``fit`` (area / AABB cross-section) and ``near_pivot`` (cap plane
    within ``_PIVOT_PLANE`` of the axis extent from the pivot)."""
    ai, sign = AXIS_DIRS[axis]
    extent = float(mx[ai] - mn[ai])
    others = [k for k in range(3) if k != ai]
    cross_section = float((mx[others[0]] - mn[others[0]]) * (mx[others[1]] - mn[others[1]]))
    outer = (mx[ai] if sign > 0 else mn[ai]) - sign * max(0.05, _OUTER_BAND * extent)
    best = None
    for cap in planar_caps(verts, tris, axis, facing_cos):
        if (cap["offset"] - outer) * sign < 0:
            break  # clusters come outermost-first; past the band now
        fit = cap["area"] / cross_section if cross_section > 0 else 0.0
        if cap["area"] < _MIN_AREA or fit < _MIN_FIT:
            continue
        if best is None or cap["area"] > best["area"]:
            near = extent > 0 and abs(cap["offset"]) <= _PIVOT_PLANE * extent
            best = dict(cap, fit=fit, near_pivot=bool(near))
    return best


def _face_record(axis: str, cap: dict[str, Any]) -> dict[str, Any]:
    return {
        "axis": axis,
        "position": [round(v, 4) for v in cap["centroid"]],
        "normal": [round(v, 4) + 0.0 for v in cap["normal"]],
        "area": round(cap["area"], 4),
        "extent": [round(v, 4) for v in cap["extent"]],
        "fit": round(min(cap["fit"], 1.0), 3),
        "source": "measured",
    }


def _with_parent_role(rec: dict[str, Any]) -> dict[str, Any]:
    """The hull socket this mount fits without rotation: the face opposite
    the mount's own axis (a -Z cockpit cap sits on the +Z/front socket)."""
    return dict(rec, parent_role=SOCKET_ROLE_BY_AXIS[_OPPOSITE[rec["axis"]]])


def _choose_mount(
    verts: np.ndarray, tris: np.ndarray, part_class: str | None, mates_axis: str | None, mn: np.ndarray, mx: np.ndarray
) -> dict[str, Any] | None:
    """The part's own attachment face (see the module docstring for the
    conventions). Returns a face record, ``None`` only for bodies."""
    if part_class == "body":
        return None
    caps = {axis: _best_cap(verts, tris, axis, mn, mx) for axis in AXIS_DIRS}
    is_wing = part_class == "wing" or mates_axis in ("±x", "+-x", "x")
    if is_wing:
        # the root may carry the dihedral: widen the cone on ±x only
        for axis in ("+x", "-x"):
            caps[axis] = _best_cap(verts, tris, axis, mn, mx, _WING_ROOT_COS)

    preferred = _CLASS_MOUNT_AXES.get(part_class or "")
    if preferred is None and mates_axis in AXIS_DIRS and not is_wing:
        preferred = [_OPPOSITE[mates_axis]]

    def rec(axis: str) -> dict[str, Any]:
        return _face_record(axis, caps[axis])  # type: ignore[arg-type]

    # Wall/roof/ground props: the stills-chosen axis is the contact, not the
    # pivot-at-plane foot (a sign's bottom sits on y=0 and would otherwise win).
    if part_class == "_prop" and preferred:
        for a in preferred:
            if caps[a] is not None:
                return rec(a)
        return _aabb_face(preferred[0], mn, mx)

    # 1. pivot-at-the-mating-plane beats the class axis (pylon pods, gear
    #    hung from the pivot, greebles pivoted on their base) -- provided the
    #    cap is a comparable face, so a small foot near the pivot does not
    #    outrank a full flat back (Misc_017: base fit 0.14 vs back 0.97).
    best_fit = max((c["fit"] for c in caps.values() if c is not None), default=0.0)
    at_pivot = [
        a for a, c in caps.items() if c is not None and c["near_pivot"] and c["fit"] >= _PIVOT_MIN_RATIO * best_fit
    ]
    if at_pivot:
        for a in preferred or []:
            if a in at_pivot:
                return rec(a)
        return rec(max(at_pivot, key=lambda a: caps[a]["fit"]))

    # 2. class axis (cockpit/engine/gear): measured cap or AABB face
    if preferred:
        for a in preferred:
            if caps[a] is not None:
                return rec(a)
        return _aabb_face(preferred[0], mn, mx)

    # 3. wings: dominant ±x cap is the root; two equal side faces = a fin
    #    that mounts by its top/bottom; nothing flat = AABB root at -x
    if is_wing:
        fx = {a: (caps[a]["fit"] if caps[a] else 0.0) for a in ("+x", "-x")}
        big, small = max(fx.values()), min(fx.values())
        if big > 0 and small / big < _WING_ROOT_RATIO:
            return rec(max(fx, key=fx.get))
        ys = [a for a in ("-y", "+y") if caps[a] is not None]
        if ys:
            return rec(max(ys, key=lambda a: caps[a]["fit"]))
        if big > 0:
            return rec(max(fx, key=fx.get))
        return _aabb_face("-x", mn, mx)

    # 4. greebles ("any"): largest axis-true flat face (a body panel sloping
    #    5-10 deg inside the cone is not a mating face), base (-y) first on
    #    ties so the AABB fallback lands on the underside
    order = ["-y", "+y", "-z", "+z", "-x", "+x"]
    flat = [a for a in order if caps[a] is not None]
    if flat:
        return rec(max(flat, key=lambda a: (_is_axis_true(caps[a], a), caps[a]["area"], -order.index(a))))
    return _aabb_face("-y", mn, mx)


def _is_axis_true(cap: dict[str, Any], axis: str) -> bool:
    ai, sign = AXIS_DIRS[axis]
    return cap["normal"][ai] * sign >= _AXIS_TRUE_COS


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
    their preferred axis) with ``parent_role``; body parts always get six sockets (measured
    where a cap exists, AABB face centre otherwise)."""
    mn = verts.min(axis=0)
    mx = verts.max(axis=0)
    mount_rec = _choose_mount(verts, tris, part_class, mates_axis, mn, mx)
    if mount_rec is not None:
        mount_rec = _with_parent_role(mount_rec)
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


# Parent face the prop seats on → mates_axis for analyse_part (child cap is opposite).
_PROP_MOUNT_MATES = {
    "wall": "+z",
    "roof": "+y",
    "ground": "+y",
    "floor": "+y",
    "ceiling": "-y",
}


def apply_prop_contact(
    asset: dict,
    threejs_v2_dir: Path | None,
    cache: dict[str, Any],
    stats: dict[str, int],
) -> None:
    """Fill ``placement.contact`` for wall/roof/ground props.

    Same measured cap as ship ``part.mount``. Buildings and ship parts skip
    (they stack / use sockets). Rank measured — stills must not invent this.
    """
    if (asset.get("part") or {}).get("class"):
        return
    if str(asset.get("type") or "").startswith("building"):
        return
    if not asset.get("placeable"):
        return
    place = asset.get("placement")
    if not isinstance(place, dict):
        return
    mates = _PROP_MOUNT_MATES.get(place.get("mount") or "")
    if not mates:
        return
    glb_rel = (asset.get("files") or {}).get("glb")
    if not glb_rel or threejs_v2_dir is None:
        stats["contact_missing_glb"] = stats.get("contact_missing_glb", 0) + 1
        return
    result = analyse_cached(
        threejs_v2_dir,
        glb_rel,
        "_prop",
        mates,
        cache,
        node_name=(asset.get("files") or {}).get("glb_node"),
    )
    contact = (result or {}).get("mount")
    if not contact:
        stats["contact_failed"] = stats.get("contact_failed", 0) + 1
        return
    place["contact"] = {
        "axis": contact.get("axis"),
        "position": contact.get("position"),
        "normal": contact.get("normal"),
        "fit": contact.get("fit"),
        "source": contact.get("source"),
    }
    cons = list(place.get("constraints") or [])
    if "seat_on_contact" not in cons:
        cons.append("seat_on_contact")
    if place.get("mount") == "roof":
        cons = [c for c in cons if c != "ground_only"]
        place["preferred_floors"] = []
    place["constraints"] = cons
    stats["contact_measured"] = stats.get("contact_measured", 0) + 1
