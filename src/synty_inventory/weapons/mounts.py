"""Host mounts: where on a gun a separate attachment seats (docs/weapon_attachments.md 4, slice W8b).

``build_mounts`` returns the ``geometry.mounts`` block of one eligible host (``whole``, ``ranged``, hold class
``one_hand`` / ``long_gun``; every other record gets ``mounts: null``, D-9) with every slot key of ATTACH_SLOTS present.
Per slot the sources are tried in the order ``override > child_node > probe > none`` (D-3, ``resolve_slot``):

* ``child_node``: the host GLB's baked child meshes (collision hulls dropped with ``SKIP_STEM_RE``, limited to the
  descendants of the selected ``glb_node``) matched by name token against ``attachment_rules.child_tokens`` /
  ``child_never``. A match is measured with the SAME anchor function as an attachment part (``attach.measure_anchor``),
  so a standalone twin and the baked child agree on what "the foot" is. ``occupied_by`` lists EVERY matching child (raw
  GLB node names, unsanitised, sorted); the seat comes from the larger one by AABB volume (name breaks a tie) and
  several of them give the review reason ``mount_ambiguous``.
* ``probe`` (muzzle only in v1): the A0 muzzle probe run on the host mesh minus the nodes of ``occupied_by``, so a baked
  brake or suppressor is not the seat (AC84). With nothing to remove it is the very computation behind
  ``geometry.muzzle``, so the two are equal bit for bit (AC67). The bore diameter comes from a ring estimator over the
  probe's own face points. The rail probe for the other slots is spike W9 and does not exist here.
* ``override``: categorical (D-5). ``{"source": "child_node", "child": <node name>}`` seats the slot on that node,
  ``{"source": "none"}`` disables it. The mapping is passed in by the caller (W8c loads it from the committed file); a
  named node that is not a mesh node of the host is reported in ``problems`` (``child_not_found``) and the ladder goes on.
* ``none``: every coordinate null and a reason (D-8). A missing mount is NEVER defaulted to a bounds guess (AC68).

Judgment calls, stated once (the spec fixes only the 0.5 / 0.4 muzzle values):

* A candidate child is a mesh node strictly below a scene root (``glb_node`` unset) or strictly below a selected node
  (``glb_node`` set). The asset's own root node is never a child of itself: a host named after a scope would otherwise
  occupy its own slot and empty the muzzle probe. A node whose AABB volume is at least ``_BODY_FRAC`` of the whole
  host's is the body, not a child, for the same reason.
* A child whose anchor cannot be measured (``anchor_unmeasured``) is not used and not listed in ``occupied_by``; the
  slot is then ``none``. (INV-16 forbids an ``occupied_by`` on a ``none`` slot.)
* A muzzle slot only collects its matching children into ``occupied_by``; they are not anchor-measured. An override
  naming a child for the muzzle slot adds that node to ``occupied_by`` and the seat stays the probe's.
* ``bore_d_m`` is the diameter, i.e. twice the radius: the mean radius of the innermost ring (1 mm radial bins around
  the face centre, at least ``_RING_MIN_POINTS`` points), or twice the largest radial distance of any face point when no
  ring exists (``face_extent``). A ``bounds_fallback`` face has no points, so both bore fields are null.
* Confidence literals: ``child_node`` 0.9 (0.6 when several children compete), ``override`` 1.0, muzzle probe 0.8 with a
  ring / 0.5 with ``face_extent`` / 0.4 ``bounds_fallback``, ``none`` 0.0. A host whose selected node, or the chosen
  child, carries a rotation or scale (NB-15) caps the slot at 0.4.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from ..naming import SKIP_STEM_RE
from ..sources.glb_geometry import load_triangles, node_world_matrices
from ..sources.glb_measure import NodeSel, node_selected, read_glb_json
from . import ATTACH_SLOTS
from .attach import measure_anchor
from .classify import raw_tokens
from .rules import attachment_rules

HOST_HOLDS = ("one_hand", "long_gun")  # with role whole and kind ranged: the hosts that carry mounts (4.1)

CONF_CHILD = 0.9
CONF_CHILD_AMBIGUOUS = 0.6
CONF_OVERRIDE = 1.0
CONF_RING = 0.8
CONF_FACE_EXTENT = 0.5  # spec 4.2
CONF_FALLBACK = 0.4  # spec 4.2 (bounds_fallback)
CONF_TRANSFORMED = 0.4  # spec 9 (a node with rotation or scale)
CONF_NONE = 0.0

_BODY_FRAC = 0.9  # a node this large against the whole host is the body, not a baked child
_RING_BIN_M = 0.001  # radial histogram bin of the bore estimator (spec 4.2)
_RING_MIN_POINTS = 6
_EPS = 1e-9
# slot -> sign of the host's up axis that the mount's `up` takes (spec 4.2): optic out of the receiver, the others hang below
_UP_SIGN = {"optic": 1, "underbarrel": -1, "magazine": -1, "laser_light": -1}

Rung = dict | None


def _r(x) -> float:
    return round(float(x), 4) + 0.0


def eligible(role: str | None, kind: str | None, hold_class: str | None) -> bool:
    """Spec 4.1: whole, ranged, one_hand or long_gun. Grenades, melee, shields, emplaced guns and bows are not hosts."""
    return role == "whole" and kind == "ranged" and hold_class in HOST_HOLDS


def none_mount(reason: str) -> dict:
    """An unavailable slot (INV-15): coordinates null, a reason set. Consumers never synthesise a position (D-8)."""
    return {
        "source": "none", "point": None, "forward": None, "up": None, "span_m": None, "span_source": None,
        "occupied_by": [], "child_node": None, "bore_d_m": None, "bore_source": None, "confidence": CONF_NONE,
        "reason": reason,
    }


def resolve_slot(override: Rung, child: Rung, probe: Rung) -> dict:
    """The precedence ``override > child_node > probe > none`` (D-3): the first rung that is not None wins.

    A rung is a finished mount dict, so a disabling override is itself a rung (a ``none`` mount with reason
    ``slot_disabled``) and beats a child that is there. When nothing applies the slot is ``none`` / ``no_child_no_probe``.
    """
    for rung in (override, child, probe):
        if rung is not None:
            return rung
    return none_mount("no_child_no_probe")


# -- child discovery --------------------------------------------------------------------------------------


def _collision(name: str) -> bool:
    return bool(SKIP_STEM_RE.search(name or ""))


def mesh_nodes(doc: dict | None, glb_node: NodeSel) -> dict[str, bool]:
    """``{node name: rotation and scale free}`` of the candidate child meshes of a host GLB (spec 4.2).

    Mesh nodes only, collision hulls dropped together with their subtree, strictly below a scene root (``glb_node`` unset)
    or strictly below a selected node (``glb_node`` set). A name used by several nodes is one entry (the GLB name is the
    identity the game hides by); it is rotation free only when all of its nodes are.
    """
    if not doc:
        return {}
    nodes = doc.get("nodes") or []
    scenes = doc.get("scenes") or []
    scene = doc.get("scene", 0)
    if not (0 <= scene < len(scenes)):
        return {}
    worlds = node_world_matrices(doc)
    out: dict[str, bool] = {}
    seen: set[int] = set()

    def walk(idx: int, depth: int, below_selected: bool) -> None:
        if not (0 <= idx < len(nodes)) or idx in seen:
            return
        seen.add(idx)
        node = nodes[idx]
        name = node.get("name") or ""
        if _collision(name):
            return
        is_child = below_selected if glb_node is not None else depth >= 1
        if node.get("mesh") is not None and name and is_child:
            world = worlds.get(idx)
            free = world is not None and bool(np.allclose(world[:3, :3], np.eye(3), atol=1e-6))
            out[name] = out.get(name, True) and free
        selected_here = glb_node is not None and node_selected(name, glb_node)
        for child in node.get("children") or []:
            walk(child, depth + 1, below_selected or selected_here)

    for root in scenes[scene].get("nodes") or []:
        walk(root, 0, False)
    return out


def matching_slots(name: str, tables: dict) -> list[str]:
    """The slots whose ``child_tokens`` the node name hits (``child_never`` vetoes all of them), in ATTACH_SLOTS order."""
    tokens = raw_tokens(name)
    if tokens & set(tables.get("child_never") or ()):
        return []
    child_tokens = tables.get("child_tokens") or {}
    return [s for s in ATTACH_SLOTS if tokens & set(child_tokens.get(s) or ())]


def _load(path, selection, glb_node, scale, drop: frozenset[str] = frozenset()) -> np.ndarray | None:
    """Finite world vertices of the nodes named ``selection`` (``None``: the host's own ``glb_node`` selection), or None."""
    got = load_triangles(path, selection if selection is not None else glb_node,
                         exclude=lambda n: _collision(n) or n in drop, scale=scale)
    if got is None:
        return None
    v = np.asarray(got[0], dtype=np.float64)
    return v if len(v) and np.isfinite(v).all() else None


def _volume(v: np.ndarray) -> float:
    return float(np.prod(v.max(axis=0) - v.min(axis=0)))


# -- frames -----------------------------------------------------------------------------------------------


def _axis_vec(signed: str) -> np.ndarray:
    v = np.zeros(3)
    v["xyz".index(signed[1])] = 1.0 if signed[0] == "+" else -1.0
    return v


def _frame(point, forward: np.ndarray, up: np.ndarray) -> dict:
    return {"point": [_r(c) for c in point], "forward": [_r(c) for c in forward], "up": [_r(c) for c in up]}


# -- the child rung ---------------------------------------------------------------------------------------


def _child_mount(slot: str, node: str, names: list[str], measured: dict, axes: dict, cap: float | None, source: str,
                 ambiguous: bool) -> dict:
    """The mount seated on child ``node`` (its anchor point, its foot length), listing ``names`` in ``occupied_by``."""
    anchor, footprint, _ = measured[node]
    fwd, up = _axis_vec(axes["forward"]), _axis_vec(axes["up"]) * _UP_SIGN[slot]
    conf = CONF_OVERRIDE if source == "override" else (CONF_CHILD_AMBIGUOUS if ambiguous else CONF_CHILD)
    if cap is not None:
        conf = min(conf, cap)
    return {
        **_frame(anchor["point"], fwd, up), "source": source, "span_m": footprint["foot_length_m"],
        "span_source": "child_foot", "occupied_by": sorted(names), "child_node": node, "bore_d_m": None,
        "bore_source": None, "confidence": conf, "reason": None,
    }


def _measure_children(vertices: Callable, slot: str, names) -> dict:
    """``{name: (anchor, footprint, volume)}`` of the children whose anchor can be measured (``attach.measure_anchor``)."""
    out = {}
    for name in sorted(set(names)):
        v = vertices(name)
        if v is None:
            continue
        got = measure_anchor(v, slot)
        if got["anchor"] is not None:
            out[name] = (got["anchor"], got["footprint"], _volume(v))
    return out


def _seat(measured: dict) -> str:
    """The larger child by AABB volume; the lower name breaks a tie, so the choice is deterministic."""
    return min(measured, key=lambda n: (-measured[n][2], n))


# -- the muzzle probe rung --------------------------------------------------------------------------------


def bore_diameter(face: np.ndarray, forward_axis: int) -> tuple[float | None, str | None]:
    """``(bore_d_m, 'ring' | 'face_extent' | None)`` from the muzzle face points (spec 4.2 and 4.4).

    Radial histogram of the points around the face centre in 1 mm bins; the innermost bin holding at least
    ``_RING_MIN_POINTS`` points is the bore ring and ``bore_d_m`` is twice its mean radius. With no such bin the face
    extent (twice the largest radial distance) is returned and marked as the weaker ``face_extent``.
    """
    if not len(face):
        return None, None
    lat = [i for i in range(3) if i != forward_axis]
    pts = face[:, lat]
    radius = np.linalg.norm(pts - pts.mean(axis=0), axis=1)
    bins = np.floor(radius / _RING_BIN_M + _EPS).astype(np.int64)
    for b in np.unique(bins):
        sel = bins == b
        if int(sel.sum()) >= _RING_MIN_POINTS:
            return _r(2.0 * float(radius[sel].mean())), "ring"
    return _r(2.0 * float(radius.max())), "face_extent"


def _muzzle_mount(path, glb_node, scale, verts, axes: dict, occupied: list[str], cap: float | None,
                  probe: Callable) -> dict:
    """The A0 probe on the host minus ``occupied`` (the whole host when it is empty), as a mount (spec 4.2)."""
    reduced = verts if not occupied else _load(path, None, glb_node, scale, frozenset(occupied))
    if reduced is None:
        return none_mount("probe_unavailable")
    point, muzzle_source, face = probe(reduced, axes["forward"], axes["up"])
    bore, bore_source = bore_diameter(face, "xyz".index(axes["forward"][1]))
    conf = CONF_FALLBACK if muzzle_source == "bounds_fallback" else (CONF_RING if bore_source == "ring" else CONF_FACE_EXTENT)
    if cap is not None:
        conf = min(conf, cap)
    return {
        # the mount frame of a muzzle: `up` is the bore direction (host forward), `forward` the roll reference (host up)
        **_frame(point, _axis_vec(axes["up"]), _axis_vec(axes["forward"])), "source": "probe", "span_m": None,
        "span_source": None, "occupied_by": sorted(occupied), "child_node": None, "bore_d_m": bore,
        "bore_source": bore_source, "confidence": conf, "reason": None,
    }


# -- the block --------------------------------------------------------------------------------------------


def build_mounts(
    path, glb_node: NodeSel, scale: float, rules: dict, *, verts: np.ndarray, axes: dict, transformed: bool = False,
    probe: Callable, overrides: dict | None = None,
) -> dict:
    """``{"mounts": block, "problems": [str]}`` for one eligible host (spec 4).

    ``verts`` are the host's own decoded vertices (what ``geometry`` measured), ``axes`` its ``{forward, up}`` signed
    axes, ``transformed`` the NB-15 flag of the selected node, ``probe`` the A0 muzzle probe
    (``geometry.muzzle_probe``; passed in because geometry imports this module), ``overrides`` the categorical mount
    overrides ``{slot: {"source": "child_node", "child": name} | {"source": "none"}}`` (W8c loads them; None = no
    override). ``problems`` lists what could not be honoured (``child_not_found: <slot>: <name>``), never silently dropped.
    """
    tables = attachment_rules(rules)
    overrides = overrides or {}
    candidates = mesh_nodes(read_glb_json(path), glb_node)
    host_volume = _volume(verts)
    cap = CONF_TRANSFORMED if transformed else None
    problems: list[str] = []
    memo: dict[str, np.ndarray | None] = {}

    def vertices(name: str) -> np.ndarray | None:
        if name not in memo:
            memo[name] = _load(path, name, glb_node, scale)
        return memo[name]

    by_slot: dict[str, list[str]] = {s: [] for s in ATTACH_SLOTS}
    for name in sorted(candidates):
        slots = matching_slots(name, tables)
        if not slots:
            continue
        v = vertices(name)
        if v is not None and host_volume > _EPS and _volume(v) >= _BODY_FRAC * host_volume:
            continue  # the body of the gun, not a baked child
        for slot in slots:
            by_slot[slot].append(name)

    mounts: dict[str, dict] = {}
    for slot in ATTACH_SLOTS:
        ov = overrides.get(slot) if isinstance(overrides.get(slot), dict) else {}
        if ov.get("source") == "none":
            mounts[slot] = resolve_slot(none_mount("slot_disabled"), None, None)
            continue
        forced = ov.get("child") if ov.get("source") == "child_node" else None
        if forced is not None and forced not in candidates:
            problems.append(f"child_not_found: {slot}: {forced}")
            forced = None
        if slot == "muzzle":
            # the matching children only fill occupied_by; the seat is the probe's, whatever else is baked on
            occupied = sorted(set(by_slot[slot]) | ({forced} if forced else set()))
            mounts[slot] = resolve_slot(None, None, _muzzle_mount(path, glb_node, scale, verts, axes, occupied, cap, probe))
            continue
        measured = _measure_children(vertices, slot, by_slot[slot] + ([forced] if forced else []))
        if forced is not None and forced not in measured:
            problems.append(f"child_unmeasured: {slot}: {forced}")
            forced = None
        listed = sorted(n for n in by_slot[slot] if n in measured)
        override_rung = child_rung = None
        if forced is not None:
            override_rung = _child_mount(slot, forced, sorted(set(listed) | {forced}), measured, axes,
                                         _child_cap(cap, candidates, forced), "override", False)
        if listed:
            seat = _seat({n: measured[n] for n in listed})
            child_rung = _child_mount(slot, seat, listed, measured, axes, _child_cap(cap, candidates, seat),
                                      "child_node", len(listed) > 1)
        mounts[slot] = resolve_slot(override_rung, child_rung, None)
    return {"mounts": mounts, "problems": problems}


def _child_cap(cap: float | None, candidates: dict[str, bool], name: str) -> float | None:
    """Confidence ceiling for a mount seated on ``name``: the host's NB-15 cap, or 0.4 when the node itself is rotated."""
    if candidates.get(name, True):
        return cap
    return CONF_TRANSFORMED if cap is None else min(cap, CONF_TRANSFORMED)


# -- review reasons ---------------------------------------------------------------------------------------


def mount_reasons(mounts: dict | None, compatible_slots=frozenset()) -> set[str]:
    """The review reasons a mounts block implies (spec 4.2).

    ``mount_ambiguous``: a ``child_node`` slot (not the muzzle, whose children only fill ``occupied_by``) with several
    matching children. ``mount_missing``: a ``none`` slot that is in ``compatible_slots``, the slots with at least one
    inferred-compatible attachment. Compatibility inference is W8c, so the directory passes the empty default until
    then and the reason cannot fire from a build yet.
    """
    reasons: set[str] = set()
    for slot, m in (mounts or {}).items():
        if slot != "muzzle" and m["source"] == "child_node" and len(m["occupied_by"]) > 1:
            reasons.add("mount_ambiguous")
        if m["source"] == "none" and slot in compatible_slots:
            reasons.add("mount_missing")
    return reasons
