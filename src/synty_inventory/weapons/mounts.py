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
* A4 (W8l, spec 4.2 "A4 on the child seat", item 5) A slot with EXACTLY two measured children whose sorted AABB extents are twins (spec 5.1
  tolerance), whose anchor points differ by at most 1 mm along host forward and along host up and by more than 5 mm along the third axis, is a
  mirrored pair (the two legs of a bipod): the mount's ``point`` is the midpoint of the two anchor points, ``child_node`` the lower name, ``seats``
  and ``occupied_by`` as for any pair. A5 (W8m, item 2) retired the optic seat lift of A4 item 4: a ``child_node`` ``optic`` seat is the child's own
  ``point`` again, and the per-pair settle-to-contact rule (spec 5.4, ``attach.settle_pair``) brings a replacement optic to the host surface.
* A1 (W8f). A slot that lists more than one measured child also carries ``seats`` (``{node: {point, forward, up, span_m}}``, one
  frame per listed child built exactly like the mount's own seat), whatever rung won, because a baked twin of the SMALLER child
  must be placed on that child's frame; the larger one stays ``child_node`` and the mount's own seat. A slot with one listed
  child, a ``none`` slot and the muzzle slot have no ``seats`` key. ``child_extents`` (the twin evidence beside the record)
  gives each listed child ``{extents, axes, seat}``.
* G1 (slice S7, docs/weapon_attach_geometry.md 3.4 to 3.7, 3.11): the geometry detectors run once per eligible host (``fit_geometry.host_features``,
  cached in ``_fit_cache.json``) after the ladder and ``refuse_baked``, and before ``refuse_filled``. They write the optional mount key ``feature``:
  a rail seat on a slot with no child and no override (``source`` ``probe``, ``feature`` ``rail_teeth`` / ``rail_flat`` (optic only), confidence
  0.5, ``span_m`` the run length after the sight clip, ``span_source`` ``probe``); ``barrel_ring`` / ``barrel_round`` on the muzzle seat (the seat
  stays the A0 probe's); ``seat_ref`` on an authored optic or underbarrel seat the detectors confirm; ``well_ref`` on an authored magazine seat with a
  well reference. A frame-conflict host (3.3 step 4, INV-27) keeps no detector seat: its probe muzzle and its empty rail and magazine slots are
  ``none`` / ``probe_unavailable``; an authored (child or override) seat is not a detector seat and stays. On a preset host (``attach_filled_hosts``)
  the fused parts the locator finds count as filled for ``refuse_filled`` (Q-G11).
* E3.1 / E3.2 (docs/weapon_attach_geometry_errata.md): the barrel end's evidence (i) and its outer diameter are read on the STRIPPED host (minus the muzzle
  ``occupied_by``, the located slot parts and collision), not on the host the mount probed. ``stripped_muzzle_face`` is the one helper that probes it
  (the A0 probe and ``bore_diameter`` on the stripped mesh); ``build_mounts`` injects it into ``host_features`` and ``cli._gather_oracle`` calls the same
  function, so the build and ``attach-calibrate`` cannot drift. The helper's code is not a fit module, so its digest (``_MOUNTS_CODE_DIGEST``) joins the
  host-features cache key.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .. import weapons as _pkg  # versions are read at call time (a test may bump them)
from ..naming import SKIP_STEM_RE
from ..sources.glb_geometry import load_triangles, node_world_matrices
from ..sources.glb_measure import NodeSel, node_cache_tag, node_selected, read_glb_json
from ..sources.glb_scale import scale_cache_tag
from . import ATTACH_SLOTS, SIGHT_SLOTS, TWIN_ABS_TOL_M, TWIN_REL_TOL
from . import fit_geometry as _fit
from .attach import measure_anchor
from .classify import raw_tokens
from .fit_bore import _used_vertices
from .mount_probe import fused_front_posts, sight_profile, sight_seats
from .rules import attach_rules_digest, attachment_rules

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
CONF_RAIL = 0.5  # spec 3.4 step 4: a rail or flat seat
CONF_NONE = 0.0

_BODY_FRAC = 0.9  # a node this large against the whole host is the body, not a baked child
_RING_BIN_M = 0.001  # radial histogram bin of the bore estimator (spec 4.2)
_RING_MIN_POINTS = 6
_EPS = 1e-9
# The digest of this file, for the host-features cache key (E3.2): ``stripped_muzzle_face`` is mounts code, so it is in neither ``FIT_CODE_DIGESTS`` nor the
# geometry cache fingerprint of the fit modules. Cache-only, like ``geometry._MOUNTS_CODE_DIGEST`` (the same bytes, so the same value); read at call time.
_MOUNTS_CODE_DIGEST = _fit._code_digest(Path(__file__).read_bytes())
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
    """The slots ``attachment_rules.attach_host_never`` and, A6 (W8n), the host classes refuse for host ``host_id`` (A3, spec 7), in ATTACH_SLOTS order.

    The host's tokens are those of its asset id (the id after the pack) as ``raw_tokens`` makes them: split on ``_`` and
    camelCase, digits dropped, plus the joins of two or three neighbours (so ``Flare_Gun`` reaches ``flaregun``). A token is a
    whole word: ``Properly`` is not ``prop``. No table, no exclusion.

    A6 (W8n, 13.7 A6-1): ``attach_host_class`` maps a class to host name tokens (the same tokens) and ``attach_class_never`` a class to the
    slots it refuses; a host whose tokens hit a class is refused those slots, a host in several classes the union, and the union with
    ``attach_host_never`` is the answer. An empty class row refuses nothing (a switched-off row); a host in no class is a firearm.
    """
    never = tables.get("attach_host_never") or {}
    tokens = raw_tokens(host_id)
    refused = set()  # A6 (W8n): the slots of every class the host's tokens hit, joined with the slot rows above (a host in several classes: the union)
    class_never = tables.get("attach_class_never") or {}
    for name, class_tokens in (tables.get("attach_host_class") or {}).items():
        if tokens & set(class_tokens or ()):
            refused.update(class_never.get(name) or ())
    return [s for s in ATTACH_SLOTS if s in refused or tokens & set(never.get(s) or ())]


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


def is_filled_host(host_id: str, tables: dict) -> bool:
    """True when the host's name tokens hit ``attach_filled_hosts`` (a preset: a gun with its parts already on it)."""
    hosts = set(tables.get("attach_filled_hosts") or ())
    return bool(hosts) and bool(raw_tokens(host_id) & hosts)


def refuse_filled(mounts: dict, found: dict[str, list[str]], host_id: str, tables: dict, located: list[dict] | None = None) -> None:
    """A6 (W8n, Tom 2026-10-24: "presets only refuse the slots their built-in parts already fill; other slots stay open"), in place.

    A host whose name tokens hit ``attachment_rules.attach_filled_hosts`` (the ``preset`` token: a Preset_* prefab is a gun with its parts
    already on it) refuses every slot a baked child of its own fills: a slot whose mount lists a child in ``occupied_by`` (a magazine, a muzzle
    device, a foregrip, a laser, a sided iron sight; the muzzle's seat is still the probe's, but a device on it fills it), and ``optic`` when
    the host carries an optic body or glass child (``baked_children``). The rule reads the host's own measured children, never a per-host list;
    a slot no child fills stays open, and an ``override`` mount is never touched (the human wins). A refused slot is ``none`` /
    ``slot_disabled`` like every other refusal, so the slot veto of compat.py removes its candidates (an authored twin of a built-in
    muzzle device or foregrip included: the preset already has it).

    ``attachment_rules.attach_filled_open`` names the slots that stay open although a baked child fills them (Tom, 2026-10-24: "preset guns can
    take other magazines (size rule still applies)": ``magazine``). The baked child stays in ``occupied_by``, so the existing hide (W8g) removes it
    where a replacement part seats, and the foot-length rule decides the fit; the authored twin of the baked
    magazine is a candidate again too (it seats where the baked one stood; a pair a human refuses is an id override).

    G1 (Q-G11, docs/weapon_attach_geometry.md 3.8): ``located`` is the list of fused parts the locator found on the host
    (``fit_geometry.host_features``, each ``{part, slot, t, hit}``). A slot of such a part is filled like a slot of a baked child: a located fused
    scope or silencer refuses ``optic`` or ``muzzle``, and a located magazine leaves ``magazine`` open (``attach_filled_open``). It can only add
    refusals. A located part with no attachment slot fills nothing.
    """
    if not is_filled_host(host_id, tables):
        return
    keep = set(tables.get("attach_filled_open") or ())
    filled = {p["slot"] for p in located or () if p.get("slot")}
    for slot in ATTACH_SLOTS:
        m = mounts[slot]
        if slot in keep or m["source"] == "override" or m["source"] == "none":
            continue
        if m["occupied_by"] or slot in filled or (slot == "optic" and (found["glass"] or found["body"])):
            mounts[slot] = none_mount("slot_disabled")


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


def _measure_children(vertices: Callable, slot: str, names, params: dict | None = None) -> dict:
    """``{name: (anchor, footprint, volume)}`` of the children whose anchor can be measured (``attach.measure_anchor``).

    A child is measured without a kind (a host child keeps the section forward, spec 3.4 step 3b) but with the rules' anchor table, so its
    ``point`` and ``span_m`` follow the foot ladder (step 1a) exactly like a part's.
    """
    out = {}
    for name in sorted(set(names)):
        v = vertices(name)
        if v is None:
            continue
        got = measure_anchor(v, slot, params=params)
        if got["anchor"] is not None:
            out[name] = (got["anchor"], got["footprint"], _volume(v))
    return out


def _seat(measured: dict) -> str:
    """The larger child by AABB volume; the lower name breaks a tie, so the choice is deterministic."""
    return min(measured, key=lambda n: (-measured[n][2], n))


# -- A4 corrections of the child seat (W8l) ----------------------------------------------------------------

_MIRROR_ALIGN_M = 0.001  # a mirrored pair agrees within 1 mm along host forward and along host up ...
_MIRROR_APART_M = 0.005  # ... and is more than 5 mm apart along the third axis


def _same_extents(a: np.ndarray, b: np.ndarray) -> bool:
    """Spec 5.1 twin test on two meshes: the sorted AABB extents agree within ``max(3 %, 0.8 mm)`` per axis."""
    xs, ys = np.sort(a.max(axis=0) - a.min(axis=0)), np.sort(b.max(axis=0) - b.min(axis=0))
    return all(abs(float(x) - float(y)) <= max(TWIN_REL_TOL * max(float(x), float(y)), TWIN_ABS_TOL_M) for x, y in zip(xs, ys))


def mirrored_point(listed: list[str], measured: dict, vertices: Callable, axes: dict) -> list[float] | None:
    """The midpoint of the two anchor points when ``listed`` is a mirrored pair of children (spec 4.2 A4, item 5), else None.

    Exactly two measured children with equal sorted extents (twin tolerance), anchor points within 1 mm of each other along host forward and
    along host up and more than 5 mm apart along the third axis. The left and right leg of a bipod seat a whole bipod on the centre line.
    """
    if len(listed) != 2:
        return None
    a, b = sorted(listed)
    va, vb = vertices(a), vertices(b)
    if va is None or vb is None or not _same_extents(va, vb):
        return None
    pa, pb = np.asarray(measured[a][0]["point"], dtype=np.float64), np.asarray(measured[b][0]["point"], dtype=np.float64)
    f_i, u_i = "xyz".index(axes["forward"][1]), "xyz".index(axes["up"][1])
    third = ({0, 1, 2} - {f_i, u_i}).pop()
    d = np.abs(pa - pb)
    if d[f_i] > _MIRROR_ALIGN_M + _EPS or d[u_i] > _MIRROR_ALIGN_M + _EPS or d[third] <= _MIRROR_APART_M + _EPS:
        return None
    return [_r(c) for c in (pa + pb) / 2.0]


# -- the muzzle probe rung --------------------------------------------------------------------------------


def bore_diameter(face: np.ndarray, forward_axis: int) -> tuple[float | None, str | None]:
    """``(bore_d_m, 'ring' | 'face_extent' | None)`` from the muzzle face points (spec 4.2 and 4.4).

    Radial histogram of the points around the face centre in 1 mm bins; the innermost bin other than the centre bin
    (radius under 1 mm) holding at least ``_RING_MIN_POINTS`` points is the bore ring, and ``bore_d_m`` is twice its
    mean radius, but only when some point lies in a bin beyond it: a ring needs an inner and an outer radius (G1 errata
    E2.6, E2-Q2). With no such ring the face extent (twice the largest radial distance) is returned and marked as the
    weaker ``face_extent``.
    """
    if not len(face):
        return None, None
    lat = [i for i in range(3) if i != forward_axis]
    pts = face[:, lat]
    radius = np.linalg.norm(pts - pts.mean(axis=0), axis=1)
    bins = np.floor(radius / _RING_BIN_M + _EPS).astype(np.int64)
    for b in np.unique(bins):
        sel = bins == b
        # bin 0 is the centre (a fan's hub, a solid end's middle), never a ring; a ring needs a point beyond it, or the end is one radius (E2-Q2)
        if b > 0 and int(sel.sum()) >= _RING_MIN_POINTS:
            if int(bins.max()) > b:
                return _r(2.0 * float(radius[sel].mean())), "ring"
            break
    return _r(2.0 * float(radius.max())), "face_extent"


def stripped_muzzle_face(verts_fsu, tris=None) -> dict | None:
    """The muzzle face of the STRIPPED host (E3.1, E3.2): ``{"ring": bool, "centre_su": [s, u] | None, "od_m": float | None}``, or None for an empty mesh.

    ``verts_fsu`` (and ``tris``) is the host in its (f, s, u) frame, minus the muzzle ``occupied_by``, minus the located slot parts and minus collision:
    the mesh ``fit_bore.barrel_end`` reads its end slab from. Only the vertices a triangle uses count and they are taken in lexicographic order
    (as ``barrel_end`` does), so the answer does not depend on the order the file lists them. It runs the one A0 algorithm (``geometry.muzzle_probe``,
    forward ``+x`` and up ``+z`` in this frame) and the same bore test as the mount (``bore_diameter``); ``ring`` is its ring verdict.

    ``centre_su`` is the mean of the face points' (s, u) and ``od_m`` twice their largest distance from it, unrounded (``barrel_end`` rounds): the
    barrel face's own centre and outer diameter (B). A ``bounds_fallback`` face has no points, so no ring and no centre. ``geometry`` imports this module,
    so the A0 probe is imported at call time.
    """
    from .geometry import muzzle_probe

    v = _used_vertices(verts_fsu, tris)
    if not len(v):
        return None
    _point, _source, face = muzzle_probe(v, "+x", "+z")
    _bore, bore_source = bore_diameter(face, 0)
    if not len(face):
        return {"ring": False, "centre_su": None, "od_m": None}
    lat = np.asarray(face, dtype=np.float64)[:, 1:]
    centre = lat.mean(axis=0)
    return {"ring": bore_source == "ring", "centre_su": [float(centre[0]), float(centre[1])],
            "od_m": 2.0 * float(np.linalg.norm(lat - centre, axis=1).max())}


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


def _probe_sights(mounts: dict, path, glb_node, scale, axes: dict, tables: dict, cap: float | None, verts: np.ndarray,
                  host_key: str | None = None) -> bool:
    """Fill the sight slots that have neither a child nor an override from the seat probe (spec 4.6), in place.

    A slot disabled by an override stays disabled. The probe sees the host without the nodes already listed by
    ``optic``, ``sight_front``, ``sight_rear`` and, from A3, ``muzzle``, ``underbarrel`` and ``laser_light`` (a baked scope is not
    the rail, and neither is a baked suppressor, laser or foregrip: the A2 close-up showed the front seat on top of a baked
    suppressor). When it refuses, every slot it was to fill becomes ``none`` / ``probe_unavailable``.

    Returns True when the fused front post detector (addendum 3, item 8 D) finds a post on that very mesh (same samples, same side window).
    Since addendum 3b (W8k, item 9) it is asked whenever the mesh yields a profile, a host the probe refused to seat included: the slot reason
    stays ``probe_unavailable`` here, and ``refuse_baked`` turns it into ``slot_disabled`` when the detector (or a baked child) says so. No
    profile (no mesh, no surface) or no ``sight_probe`` table means no detection.

    A6 (W8n, 13.7 A6-4 d2): ``sight_probe.receiver_tol_by_host`` maps ``"<pack>/<host id>"`` to a receiver tolerance used for that host only
    (``host_key`` is its key); every other host reads ``receiver_tol_m``.
    """
    params = tables.get("sight_probe")
    if params and host_key is not None and host_key in (params.get("receiver_tol_by_host") or {}):
        params = {**params, "receiver_tol_m": params["receiver_tol_by_host"][host_key]}
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


# -- the G1 detector seats --------------------------------------------------------------------------------


def _rail_mount(slot: str, seat: dict, axes: dict, cap: float | None) -> dict:
    """The mount a rail or flat seat gives (spec 3.4 step 4): ``probe``, host forward, +u (optic) or -u (underbarrel), span = the run length."""
    point = _fit.from_fsu(_fit.frame_basis(axes), seat["f"], seat["s"], seat["u"])
    return {
        **_frame(point, _axis_vec(axes["forward"]), _axis_vec(axes["up"]) * _UP_SIGN[slot]), "source": "probe", "span_m": seat["span_m"],
        "span_source": "probe", "occupied_by": [], "child_node": None, "bore_d_m": None, "bore_source": None,
        "confidence": CONF_RAIL if cap is None else min(CONF_RAIL, cap), "reason": None, "feature": seat["feature"],
    }


def _empty_features() -> dict:
    return {"s0": None, "slots": {slot: {} for slot in _fit.FIT_SLOTS}, "seats": {}, "located": []}


def _apply_features(mounts: dict, feats: dict, axes: dict, cap: float | None, frame_conflict: bool) -> None:
    """Write the detector seats and ``feature`` keys into ``mounts``, in place (spec 3.4 step 4, 3.6, 3.7; INV-27 on a frame conflict)."""
    if frame_conflict:
        # 3.3 step 4: every detector seat is withheld, the slot is none / probe_unavailable. A child or override seat is authored, not a detector's
        if mounts["muzzle"]["source"] == "probe":
            mounts["muzzle"] = none_mount("probe_unavailable")
        for slot in ("optic", "underbarrel", "magazine"):
            if mounts[slot]["source"] == "none" and mounts[slot]["reason"] == "no_child_no_probe":
                mounts[slot] = none_mount("probe_unavailable")
        return
    for slot, seat in sorted(feats["seats"].items()):
        if "f" in seat:
            mounts[slot] = _rail_mount(slot, seat, axes, cap)
        else:
            mounts[slot]["feature"] = seat["feature"]


# -- the block --------------------------------------------------------------------------------------------


def build_mounts(
    path, glb_node: NodeSel, scale: float, rules: dict, *, verts: np.ndarray, axes: dict, transformed: bool = False,
    probe: Callable, overrides: dict | None = None, host_id: str | None = None, host_pack: str | None = None,
    frame_changed: bool = False, frame_conflict: bool = False, fit_cache: dict | None = None, fit_cache_id: str | None = None,
    fused_parts: tuple | None = None,
) -> dict:
    """``{"mounts": block, "problems": [str], "child_extents": {...}, "host_feats": {...}}`` for one eligible host (spec 4).

    ``verts`` are the host's own decoded vertices (what ``geometry`` measured), ``axes`` its ``{forward, up}`` signed
    axes, ``transformed`` the NB-15 flag of the selected node, ``probe`` the A0 muzzle probe
    (``geometry.muzzle_probe``; passed in because geometry imports this module), ``overrides`` the categorical mount
    overrides ``{slot: {"source": "child_node", "child": name} | {"source": "none"}}`` (W8c loads them; None = no
    override). ``host_id`` is the host's asset id (A3: ``attach_host_never`` and the baked-child classes read its name tokens;
    the GLB file stem when None). ``host_pack`` (A6) is the host's pack id, so the sight probe finds the host's ``"<pack>/<host id>"`` key in
    ``receiver_tol_by_host``; without it no per-host tolerance applies. ``problems`` lists what could not be honoured (``child_not_found: <slot>: <name>``), never silently dropped.

    G1 (S7): ``frame_changed`` / ``frame_conflict`` are the frame vote's state (``geometry.frame_vote``); ``fit_cache`` / ``fit_cache_id`` cache the
    host's detector features (``fit_geometry.host_features``, ``_fit_cache.json``); ``fused_parts`` is the preset's part set, ``(key, load)`` (dropped
    when the host is not an ``attach_filled_hosts`` host: only a preset is searched for fused parts, spec 3.2). ``host_feats`` in the result is that
    function's result (the empty shape when the rules carry no ``fit_geometry`` block).
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
        measured = measured_by_slot[slot] = _measure_children(vertices, slot, by_slot[slot] + ([forced] if forced else []),
                                                              tables.get("anchor"))
        if forced is not None and forced not in measured:
            problems.append(f"child_unmeasured: {slot}: {forced}")
            forced = None
        listed = sorted(n for n in by_slot[slot] if n in measured)
        override_rung = child_rung = None
        if forced is not None:
            override_rung = _child_mount(slot, forced, sorted(set(listed) | {forced}), measured, axes,
                                         _child_cap(cap, candidates, forced), "override", False)
        if listed:
            middle = mirrored_point(listed, measured, vertices, axes)  # A4 item 5: a mirrored pair seats at its midpoint, on the lower name
            seat = listed[0] if middle is not None else _seat({n: measured[n] for n in listed})
            child_rung = _child_mount(slot, seat, listed, measured, axes, _child_cap(cap, candidates, seat),
                                      "child_node", len(listed) > 1)
            if middle is not None:
                child_rung["point"] = middle
        mounts[slot] = resolve_slot(override_rung, child_rung, None)
    fused_post = _probe_sights(mounts, path, glb_node, scale, axes, tables, cap, verts, f"{host_pack}/{host_id}" if host_pack else None)
    found = baked_children(candidates, host_id, tables, vertices, verts, axes, host_volume)
    refuse_baked(mounts, found, fused_post)
    feats = _empty_features()
    if tables.get("fit_geometry"):
        mesh_memo: dict[frozenset, tuple | None] = {}

        def mesh(drop: frozenset):
            if drop not in mesh_memo:
                mesh_memo[drop] = _load_mesh(path, glb_node, scale, drop)
            return mesh_memo[drop]

        def child_mesh(name: str):
            got = load_triangles(path, name, exclude=_collision, scale=scale)
            if got is None or not len(got[0]) or not len(got[1]):
                return None
            return np.asarray(got[0], dtype=np.float64), np.asarray(got[1])

        cache_key = None
        if fit_cache is not None and fit_cache_id is not None:  # spec 3.11: the cache key (the fit code digests join it inside host_features)
            from . import geometry as _geometry  # call time: geometry imports this module
            cache_key = {"sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(), "glb_node": node_cache_tag(glb_node),
                         "glb_scale": scale_cache_tag(scale), "geometry_version": _pkg.WEAPON_GEOMETRY_VERSION,
                         "attach_version": _pkg.WEAPON_ATTACH_VERSION, "attach_rules_digest": attach_rules_digest(rules),
                         "mounts_code": _MOUNTS_CODE_DIGEST,  # E3.2: the stripped probe below is mounts code, not a fit module
                         # S11 finding 1: stripped_muzzle_face runs geometry.muzzle_probe (the one A0 algorithm), so geometry.py is part of the
                         # result too and is in neither digest above. The whole file, not the one function: the same coarse granularity as
                         # mounts_code. Read at call time (the import above).
                         "geometry_code": _geometry._CODE_DIGEST}
        feats = _fit.host_features(
            tables["fit_geometry"], axes=axes, mounts=mounts, mesh=mesh, child_mesh=child_mesh,
            fused_parts=fused_parts if is_filled_host(host_id, tables) else None, frame_changed=frame_changed, frame_conflict=frame_conflict,
            cache=fit_cache, cache_id=fit_cache_id, cache_key=cache_key, stripped_probe=stripped_muzzle_face)
    _apply_features(mounts, feats, axes, cap, frame_conflict)
    refuse_filled(mounts, found, host_id, tables, feats["located"])
    return {"mounts": mounts, "problems": problems, "host_feats": feats,
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
    matching children. ``mount_estimated`` (A2): a sight slot seated by the probe, and (G1) a rail or flat seat (the muzzle probe is a measurement, not an estimate). ``mount_missing``: a ``none`` slot that is in ``compatible_slots``, the slots with at least one
    inferred-compatible attachment. Compatibility inference is W8c, so the directory passes the empty default until
    then and the reason cannot fire from a build yet.
    """
    reasons: set[str] = set()
    for slot, m in (mounts or {}).items():
        if slot != "muzzle" and m["source"] == "child_node" and len(m["occupied_by"]) > 1:
            reasons.add("mount_ambiguous")
        if m["source"] == "probe" and (slot in SIGHT_SLOTS or m.get("feature") in ("rail_teeth", "rail_flat")):
            reasons.add("mount_estimated")
        if m["source"] == "none" and slot in compatible_slots:
            reasons.add("mount_missing")
    return reasons
