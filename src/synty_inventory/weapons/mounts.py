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
* ``probe`` (``sight_front`` / ``sight_rear``, A2 / W8h-B): no host names its iron-sight children by side, so a sight slot with
  no child and no override takes the seat of ``mount_probe.sight_seats`` (spec 4.6), run on the host minus the ``occupied_by`` of
  ``optic``, ``sight_front``, ``sight_rear`` and (A3, W8i) ``muzzle``, ``underbarrel`` and ``laser_light`` (a baked suppressor is
  not the rail either). Confidence 0.5 (0.4 on a transformed node), ``span_m`` null, review reason
  ``mount_estimated``; a host the probe refuses has both slots ``none`` / ``probe_unavailable``. Rules without a ``sight_probe``
  table run no probe (the slots stay ``no_child_no_probe``).
* A3 (W8i) and addendum 3 (W8j, spec 4.6 item 8), ways a slot is refused (``none`` / ``slot_disabled``, which the slot veto of compat.py
  turns into "no candidate"). They run in this order after the ladder above resolved every slot, and none of them touches an ``override``
  mount, a slot that is already ``none`` (its reason stays) or an id override of the slot (the human wins):
  (E) ``attachment_rules.attach_host_never`` (flare guns, props, toy and water guns: ``excluded_slots``; it may name ``optic`` too, a
  baked scope child included); then, from the host's baked children (``baked_children``), (A) a BODY child (a separate optic node, which
  can be hidden) refuses both sight slots and keeps ``optic``; (B) a GLASS-ONLY host (a glass sheet child and no body child: the optic body
  is fused into the host and cannot be hidden) refuses ``optic`` and both sight slots; (C) a baked iron sight child (named
  ``Sight_01`` / ``Sights``, or sided), a carry handle child, or a fused front post (``mount_probe.fused_front_posts`` on the sight
  probe's own mesh) refuses BOTH sight slots, half a pair is never offered. A sight slot is only changed when the probe seated it OR it is
  ``none`` with a pending reason (``probe_unavailable``, ``no_child_no_probe``: addendum 3b, W8k, item 9, so a baked host has no pending
  sight entries), so a sided ``child_node`` keeps its seat; the ``optic`` slot of (B) is changed whatever its source (a glass ``child_node``
  stops being a seat).
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
* A1 (W8f). A slot that lists more than one measured child also carries ``seats`` (``{node: {point, forward, up, span_m}}``, one
  frame per listed child built exactly like the mount's own seat), whatever rung won, because a baked twin of the SMALLER child
  must be placed on that child's frame; the larger one stays ``child_node`` and the mount's own seat. A slot with one listed
  child, a ``none`` slot and the muzzle slot have no ``seats`` key. ``child_extents`` (the twin evidence beside the record)
  gives each listed child ``{extents, axes, seat}``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np

from ..naming import SKIP_STEM_RE
from ..sources.glb_geometry import load_triangles, node_world_matrices
from ..sources.glb_measure import NodeSel, node_selected, read_glb_json
from . import ATTACH_SLOTS, SIGHT_SLOTS
from .attach import measure_anchor
from .classify import raw_tokens
from .mount_probe import fused_front_posts, sight_profile, sight_seats
from .rules import attachment_rules

# the slots whose baked children are not part of the surface the sight probe reads (spec 4.6 item 1; A3 added the last three)
PROBE_DROP_SLOTS = ("optic", "sight_front", "sight_rear", "muzzle", "underbarrel", "laser_light")
# the reasons of a sight slot the probe could not seat, which compat turns into a pending entry (spec 4.6 item 9): the baked-sight rules reach them
PENDING_SIGHT_REASONS = ("probe_unavailable", "no_child_no_probe")
HOST_HOLDS = ("one_hand", "long_gun")  # with role whole and kind ranged: the hosts that carry mounts (4.1)

CONF_CHILD = 0.9
CONF_CHILD_AMBIGUOUS = 0.6
CONF_OVERRIDE = 1.0
CONF_RING = 0.8
CONF_FACE_EXTENT = 0.5  # spec 4.2
CONF_SIGHT_PROBE = 0.5  # spec 4.6
CONF_FALLBACK = 0.4  # spec 4.2 (bounds_fallback)
CONF_TRANSFORMED = 0.4  # spec 9 (a node with rotation or scale)
CONF_NONE = 0.0

_BODY_FRAC = 0.9  # a node this large against the whole host is the body, not a baked child
_RING_BIN_M = 0.001  # radial histogram bin of the bore estimator (spec 4.2)
_RING_MIN_POINTS = 6
_EPS = 1e-9
# slot -> sign of the host's up axis that the mount's `up` takes (spec 4.2): optic out of the receiver, the others hang below
_UP_SIGN = {"optic": 1, "sight_front": 1, "sight_rear": 1, "underbarrel": -1, "magazine": -1, "laser_light": -1}

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
    """The slots whose ``child_tokens`` the node name hits (``child_never`` vetoes all of them), in ATTACH_SLOTS order.

    A2: a node that hits a sight slot is not also an optic child unless an optic token OTHER than the bare ``sight`` hits
    (``Front_Sight`` hits ``sight`` for the optic and ``frontsight`` for the sight slot, and is an iron sight; a
    ``Sight_Glass`` hits only the optic).
    """
    tokens = raw_tokens(name)
    if tokens & set(tables.get("child_never") or ()):
        return []
    child_tokens = tables.get("child_tokens") or {}
    slots = [s for s in ATTACH_SLOTS if tokens & set(child_tokens.get(s) or ())]
    if "optic" in slots and any(s in slots for s in SIGHT_SLOTS) \
            and not (tokens & set(child_tokens.get("optic") or ())) - {"sight"}:
        slots.remove("optic")
    return slots


def excluded_slots(host_id: str, tables: dict) -> list[str]:
    """The slots ``attachment_rules.attach_host_never`` refuses for host ``host_id`` (A3, spec 7), in ATTACH_SLOTS order.

    The host's tokens are those of its asset id (the id after the pack) as ``raw_tokens`` makes them: split on ``_`` and
    camelCase, digits dropped, plus the joins of two or three neighbours (so ``Flare_Gun`` reaches ``flaregun``). A token is a
    whole word: ``Properly`` is not ``prop``. No table, no exclusion.
    """
    never = tables.get("attach_host_never") or {}
    tokens = raw_tokens(host_id)
    return [s for s in ATTACH_SLOTS if tokens & set(never.get(s) or ())]


def baked_children(candidates, host_id: str, tables: dict, vertices: Callable, verts: np.ndarray, axes: dict,
                   host_volume: float) -> dict[str, list[str]]:
    """The host's baked optic and iron sight children by class (A3 spec 4.6 item 7 and addendum 3 item 8), sorted node names per class.

    ``candidates`` are the host's mesh nodes. Name tokens are ``raw_tokens`` (whole words); a child's tokens MINUS those of the host's own
    name (``SM_Wep_Rifle_Assault_Sight_01`` on host ``SM_Wep_Rifle_Assault_01`` leaves ``sight``) decide a positive, and the child's FULL
    name decides a veto or a glass child (a host word never makes a child a sight, and never lifts a veto). Classes:

    * ``glass``: a token of ``baked_sights.glass_tokens`` (``Scope_Glass_01`` is glass); ``body``: a token of ``body_tokens`` and no glass token.
    * ``handle``: a carry handle, i.e. a ``rear_tokens`` token (``carryhandle``, ``carry``, at any height), or a ``handle_tokens`` token
      with none of ``handle_not_tokens`` (``ChargeHandle``, ``PumpHandle``...) whose bounding box centre along ``up`` lies above
      ``handle_min_height_frac`` of the host's extent along ``up`` (a lower handle is a grip, a guard or a lever).
    * ``iron``: a token of ``tokens`` and none of ``not_tokens``, or a child that names its side (the sided ``child_node`` of 4.2: since
      addendum 3 it counts as a baked sight too, the pair is refused as a whole).

    The body of the gun and a child that cannot be decoded are not children. ``vertices`` is the memoised per-child loader of
    ``build_mounts`` (a child is decoded once, and only when its name can be one of the classes).
    """
    out: dict[str, list[str]] = {"glass": [], "body": [], "handle": [], "iron": []}
    spec = tables.get("baked_sights")
    if not spec or not len(verts):
        return out
    sight, veto, rear_only = set(spec.get("tokens") or ()), set(spec.get("not_tokens") or ()), set(spec.get("rear_tokens") or ())
    glass_t, body_t = set(spec.get("glass_tokens") or ()), set(spec.get("body_tokens") or ())
    handle_t, handle_not = set(spec.get("handle_tokens") or ()), set(spec.get("handle_not_tokens") or ())
    frac = spec.get("handle_min_height_frac")
    u_i, u_s = "xyz".index(axes["up"][1]), (1.0 if axes["up"][0] == "+" else -1.0)
    host_u = u_s * verts[:, u_i]
    u_lo, u_hi = float(host_u.min()), float(host_u.max())
    own = raw_tokens(host_id)
    for name in sorted(candidates):
        full = raw_tokens(name)
        tokens = full - own  # the host's own words never make a child a sight ...
        glass = bool(full & glass_t)
        body = bool(tokens & body_t) and not glass
        carry = bool(tokens & rear_only)
        handle_word = bool(tokens & handle_t) and not full & handle_not and frac is not None  # its height is judged below
        iron = bool(set(matching_slots(name, tables)) & set(SIGHT_SLOTS)) or bool(tokens & sight and not full & veto)  # ... nor lift a veto word
        if not (glass or body or carry or handle_word or iron):
            continue
        v = vertices(name)
        if v is None or (host_volume > _EPS and _volume(v) >= _BODY_FRAC * host_volume):
            continue  # undecodable, or the body of the gun
        high = False
        if handle_word and not carry and u_hi - u_lo > _EPS:
            centre_u = u_s * (float(v[:, u_i].min()) + float(v[:, u_i].max())) / 2.0
            high = (centre_u - u_lo) / (u_hi - u_lo) > frac
        if glass:
            out["glass"].append(name)
        elif body:
            out["body"].append(name)
        elif carry or high:
            out["handle"].append(name)
        elif iron:
            out["iron"].append(name)
    return out


def refuse_baked(mounts: dict, found: dict[str, list[str]], fused_post: bool) -> None:
    """Rules (A), (B), (C) of spec 4.6 item 8 as slot rewrites, in place (``found`` from ``baked_children``).

    (A) a body child: both sight slots go; (B) glass children and no body child: ``optic`` and both sight slots go; (C) a baked iron sight
    or carry handle child, or a fused front post: both sight slots go. A SIGHT slot is only changed when the probe seated it or when it is
    ``none`` with a PENDING reason (``probe_unavailable``, or ``no_child_no_probe`` when the rules carry no probe table; spec 4.6 item 9,
    addendum 3b: compat turns such a slot into a pending entry, a promise a baked host cannot keep). A sided ``child_node`` baked sight is
    replaced and not doubled, so it keeps its seat (judgment call, reported: this keeps the W8h hide fixture, a host with a scope child AND
    sided sight children, valid); the ``optic`` slot of (B) is changed whatever its source, a glass child that was its ``child_node``
    included. An ``override`` mount is never touched and a slot that is already ``none`` / ``slot_disabled`` keeps its reason.
    """
    def refuse(slot: str, *, probe_only: bool = True) -> None:
        mount = mounts[slot]
        source = mount["source"]
        if source == "override":
            return
        if source == "none":
            if not (probe_only and mount["reason"] in PENDING_SIGHT_REASONS):
                return  # `slot_disabled` (an override, a host name or a rule) keeps its reason; so does an `optic` that is none
        elif probe_only and source != "probe":
            return  # a `child_node` sight keeps its seat
        mounts[slot] = none_mount("slot_disabled")

    if found["glass"] and not found["body"]:
        refuse("optic", probe_only=False)
        for slot in SIGHT_SLOTS:
            refuse(slot)
    elif found["body"]:
        for slot in SIGHT_SLOTS:
            refuse(slot)
    if found["iron"] or found["handle"] or fused_post:
        for slot in SIGHT_SLOTS:
            refuse(slot)


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


def _child_frame(slot: str, node: str, measured: dict, axes: dict) -> dict:
    """``{point, forward, up, span_m}`` of child ``node``: its own anchor point and foot length, the slot's axes from the host's."""
    anchor, footprint, _ = measured[node]
    fwd, up = _axis_vec(axes["forward"]), _axis_vec(axes["up"]) * _UP_SIGN[slot]
    return {**_frame(anchor["point"], fwd, up), "span_m": footprint["foot_length_m"]}


def _child_mount(slot: str, node: str, names: list[str], measured: dict, axes: dict, cap: float | None, source: str,
                 ambiguous: bool) -> dict:
    """The mount seated on child ``node`` (its anchor point, its foot length), listing ``names`` in ``occupied_by``.

    A1: with more than one listed child the mount also carries ``seats``, the same frame for every listed child, so a twin of
    the smaller one is placed on ITS child and not on the larger one that owns the mount's own seat.
    """
    conf = CONF_OVERRIDE if source == "override" else (CONF_CHILD_AMBIGUOUS if ambiguous else CONF_CHILD)
    if cap is not None:
        conf = min(conf, cap)
    frame = _child_frame(slot, node, measured, axes)
    mount = {
        **{k: frame[k] for k in ("point", "forward", "up")}, "source": source, "span_m": frame["span_m"],
        "span_source": "child_foot", "occupied_by": sorted(names), "child_node": node, "bore_d_m": None,
        "bore_source": None, "confidence": conf, "reason": None,
    }
    if len(names) > 1:  # `names` are all measured: the caller lists only children whose anchor could be measured
        mount["seats"] = {n: _child_frame(slot, n, measured, axes) for n in sorted(names)}
    return mount


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


# -- the sight probe rung ---------------------------------------------------------------------------------


def _load_mesh(path, glb_node, scale, drop: frozenset[str]):
    """``(vertices, triangles)`` of the host minus the nodes in ``drop`` (collision hulls dropped), or None when nothing is left."""
    got = load_triangles(path, glb_node, exclude=lambda n: _collision(n) or n in drop, scale=scale)
    if got is None:
        return None
    v = np.asarray(got[0], dtype=np.float64)
    t = np.asarray(got[1])
    return (v, t) if len(v) and len(t) and np.isfinite(v).all() else None


def _sight_probe_mount(point, axes: dict, slot: str, cap: float | None) -> dict:
    """The mount a probe seat gives: host forward and host up, no span (spec 4.6), confidence 0.5."""
    conf = CONF_SIGHT_PROBE if cap is None else min(CONF_SIGHT_PROBE, cap)
    return {
        **_frame(point, _axis_vec(axes["forward"]), _axis_vec(axes["up"]) * _UP_SIGN[slot]), "source": "probe",
        "span_m": None, "span_source": None, "occupied_by": [], "child_node": None, "bore_d_m": None,
        "bore_source": None, "confidence": conf, "reason": None,
    }


def _probe_sights(mounts: dict, path, glb_node, scale, axes: dict, tables: dict, cap: float | None, verts: np.ndarray) -> bool:
    """Fill the sight slots that have neither a child nor an override from the seat probe (spec 4.6), in place.

    A slot disabled by an override stays disabled. The probe sees the host without the nodes already listed by
    ``optic``, ``sight_front``, ``sight_rear`` and, from A3, ``muzzle``, ``underbarrel`` and ``laser_light`` (a baked scope is not
    the rail, and neither is a baked suppressor, laser or foregrip: the A2 close-up showed the front seat on top of a baked
    suppressor). When it refuses, every slot it was to fill becomes ``none`` / ``probe_unavailable``.

    Returns True when the fused front post detector (addendum 3, item 8 D) finds a post on that very mesh (same samples, same side window).
    Since addendum 3b (W8k, item 9) it is asked whenever the mesh yields a profile, a host the probe refused to seat included: the slot reason
    stays ``probe_unavailable`` here, and ``refuse_baked`` turns it into ``slot_disabled`` when the detector (or a baked child) says so. No
    profile (no mesh, no surface) or no ``sight_probe`` table means no detection.
    """
    params = tables.get("sight_probe")
    open_slots = [s for s in SIGHT_SLOTS if mounts[s]["source"] == "none" and mounts[s]["reason"] == "no_child_no_probe"]
    if not params or not open_slots:
        return False
    drop = frozenset(n for s in PROBE_DROP_SLOTS for n in mounts[s]["occupied_by"])
    mesh = _load_mesh(path, glb_node, scale, drop)
    profile = sight_profile(mesh[0], mesh[1], axes, params) if mesh is not None else None
    seats = sight_seats(mesh[0], mesh[1], axes, params, profile) if profile is not None else None
    for slot in open_slots:
        mounts[slot] = none_mount("probe_unavailable") if seats is None else _sight_probe_mount(seats[slot], axes, slot, cap)
    fused = (tables.get("baked_sights") or {}).get("fused_post")
    if profile is None or not fused or not len(verts):
        return False
    f_i, f_s = "xyz".index(axes["forward"][1]), (1.0 if axes["forward"][0] == "+" else -1.0)
    host_f = f_s * verts[:, f_i]  # the forward extent of the FULL host mesh, not of the probe mesh
    return bool(fused_front_posts(profile, fused, (float(host_f.min()), float(host_f.max()))))


# -- the block --------------------------------------------------------------------------------------------


def build_mounts(
    path, glb_node: NodeSel, scale: float, rules: dict, *, verts: np.ndarray, axes: dict, transformed: bool = False,
    probe: Callable, overrides: dict | None = None, host_id: str | None = None,
) -> dict:
    """``{"mounts": block, "problems": [str], "child_extents": {...}}`` for one eligible host (spec 4).

    ``verts`` are the host's own decoded vertices (what ``geometry`` measured), ``axes`` its ``{forward, up}`` signed
    axes, ``transformed`` the NB-15 flag of the selected node, ``probe`` the A0 muzzle probe
    (``geometry.muzzle_probe``; passed in because geometry imports this module), ``overrides`` the categorical mount
    overrides ``{slot: {"source": "child_node", "child": name} | {"source": "none"}}`` (W8c loads them; None = no
    override). ``host_id`` is the host's asset id (A3: ``attach_host_never`` and the baked-child classes read its name tokens;
    the GLB file stem when None). ``problems`` lists what could not be honoured (``child_not_found: <slot>: <name>``), never silently dropped.
    """
    tables = attachment_rules(rules)
    overrides = overrides or {}
    host_id = host_id or Path(path).stem
    never = excluded_slots(host_id, tables)
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
    measured_by_slot: dict[str, dict] = {}
    for slot in ATTACH_SLOTS:
        ov = overrides.get(slot) if isinstance(overrides.get(slot), dict) else {}
        if ov.get("source") == "none" or (slot in never and not ov):  # A3: a table exclusion is a rule, and an id override beats a rule
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
        measured = measured_by_slot[slot] = _measure_children(vertices, slot, by_slot[slot] + ([forced] if forced else []))
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
    fused_post = _probe_sights(mounts, path, glb_node, scale, axes, tables, cap, verts)
    refuse_baked(mounts, baked_children(candidates, host_id, tables, vertices, verts, axes, host_volume), fused_post)
    return {"mounts": mounts, "problems": problems,
            "child_extents": _child_extents(mounts, vertices, measured_by_slot, axes)}


def _child_extents(mounts: dict, vertices: Callable, measured_by_slot: dict, axes: dict) -> dict:
    """``{slot: {node: {"extents", "axes", "seat"}}}`` of every child a slot lists in ``occupied_by`` (twin evidence, W8c / A1).

    The twin rule of spec 5.1 compares the SORTED AABB extents of a standalone part with those of "a child of the same
    slot", and the mount block only keeps the seat's foot length, so the evidence rides beside it in the measurement detail
    (and the geometry cache) and never enters the record. Per child: ``extents`` the sorted AABB extents (metres),
    ``axes`` the same extents per axis x, y, z (the yaw-free test of the forward correction, 3.4 step 3a) and ``seat`` the
    frame ``_child_frame`` builds for it (None for a muzzle device, which is not anchor-measured). The vertices are the
    memo ``build_mounts`` already filled, so this costs no second decode. A slot without baked children is absent.
    """
    out: dict[str, dict[str, dict]] = {}
    for slot, m in mounts.items():
        measured = measured_by_slot.get(slot) or {}
        rows = {}
        for name in m["occupied_by"]:
            v = vertices(name)
            if v is not None:
                per_axis = [_r(e) for e in (v.max(axis=0) - v.min(axis=0))]
                rows[name] = {"extents": sorted(per_axis), "axes": per_axis,
                              "seat": _child_frame(slot, name, measured, axes) if name in measured else None}
        if rows:
            out[slot] = rows
    return out


def _child_cap(cap: float | None, candidates: dict[str, bool], name: str) -> float | None:
    """Confidence ceiling for a mount seated on ``name``: the host's NB-15 cap, or 0.4 when the node itself is rotated."""
    if candidates.get(name, True):
        return cap
    return CONF_TRANSFORMED if cap is None else min(cap, CONF_TRANSFORMED)


# -- review reasons ---------------------------------------------------------------------------------------


def mount_reasons(mounts: dict | None, compatible_slots=frozenset()) -> set[str]:
    """The review reasons a mounts block implies (spec 4.2).

    ``mount_ambiguous``: a ``child_node`` slot (not the muzzle, whose children only fill ``occupied_by``) with several
    matching children. ``mount_estimated`` (A2): a sight slot seated by the probe (the muzzle probe is a measurement, not an estimate). ``mount_missing``: a ``none`` slot that is in ``compatible_slots``, the slots with at least one
    inferred-compatible attachment. Compatibility inference is W8c, so the directory passes the empty default until
    then and the reason cannot fire from a build yet.
    """
    reasons: set[str] = set()
    for slot, m in (mounts or {}).items():
        if slot != "muzzle" and m["source"] == "child_node" and len(m["occupied_by"]) > 1:
            reasons.add("mount_ambiguous")
        if slot in SIGHT_SLOTS and m["source"] == "probe":
            reasons.add("mount_estimated")
        if m["source"] == "none" and slot in compatible_slots:
            reasons.add("mount_missing")
    return reasons
