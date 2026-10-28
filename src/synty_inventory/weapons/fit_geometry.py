"""The geometry fit gate G1: the facade (docs/weapon_attach_geometry.md 3.1, 3.5 to 3.7, 3.11, 4.3).

Callers import from here only. The types live in ``fit_types`` and the detectors in ``fit_locate``, ``fit_rails``, ``fit_bore`` and
``fit_well``; all are re-exported, so the detector modules never import this one (no import cycle). This module holds the two pure
functions that need none of them:

* ``verdict`` decides ``V(P, H, X)`` from host features the detectors measured and the part's anchor and footprint. The shapes of
  ``host_feats``, ``part`` and ``pair_seat`` are documented in ``fit_types``. Every tolerance is read from ``rules`` (the
  ``attachment_rules.fit_geometry`` block, spec 4.1) and none is written here.
* ``fit_digest`` hashes the measure records (spec 4.3).
* ``host_features`` (G1 slice S7) runs the detectors once per eligible host, in the record frame, and caches the result (spec 3.11). See the
  section "Host features" below for what it takes, what it returns and every reading it makes.

Imports: the standard library, ``numpy`` and the sibling ``fit_*`` modules only (AC144, and the S2 test that keeps this facade out of
``geometry``, ``mounts``, ``compat`` and ``directory``: the loading of meshes, the versions and the digests of the rules are ARGUMENTS).
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import math
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .fit_bore import barrel_end, device_inner_d
from .fit_locate import locate_by_translation, strip
from .fit_rails import clip_run, flat_seat, rail_runs, seat_point
from .fit_types import FIT_SLOTS, SIGNALS, VERDICT_VALUES, BarrelEnd, Placement, RailRun, Verdict, WellRef
from .fit_well import entry_section, well_reference

__all__ = [
    "BarrelEnd", "FIT_CACHE_NAME", "FIT_CODE_DIGESTS", "FIT_SLOTS", "Placement", "RailRun", "SIGNALS", "VERDICT_VALUES", "Verdict", "WellRef",
    "barrel_end", "clip_run", "device_inner_d", "entry_section", "fit_digest", "flat_seat", "frame_basis", "from_fsu", "host_features",
    "load_fit_cache", "locate_by_translation", "rail_runs", "save_fit_cache", "seat_point", "strip", "to_fsu", "verdict", "well_reference",
]

# Every bound of the tables below is inclusive (spec 3.5 to 3.7 write them with <= and >=). A measure is rounded to 1e-4 m (spec 4.3), so a
# comparison that lands exactly on a bound in decimal must not lose to binary rounding (0.1 + 0.01 > 0.11): the slack is far below a measure.
_EPS = 1e-9
_RAIL_SLOTS = ("optic", "underbarrel")
_DIGEST_DECIMALS = 4  # spec 4.3: stored measures are rounded to 1e-4 m


def verdict(slot: str, host_feats: dict, part: dict, pair_seat: dict | None, rules: dict) -> Verdict:
    """``V(P, H, X)`` for one pair (spec 3.1 step 4 and the tables of 3.5, 3.6, 3.7 step 3). Pure: no I/O, deterministic.

    ``slot`` is one of the four slots of ``rules['slots']``; ``rules`` is the ``fit_geometry`` block. ``host_feats``, ``part`` and
    ``pair_seat`` are the dicts documented in ``fit_types``. Order of decision:

    1. A host with a frame conflict (3.3 step 4) is ``not_judged`` in every slot.
    2. The host side. Optic and underbarrel: a toothed run, else an authored reference seat, else (optic only) a flat seat, else
       ``not_judged``. Muzzle: no barrel end is ``no_fit`` (3.6). Magazine: no well reference is ``not_judged`` (3.7 step 1).
    3. The part side. An unmeasured anchor, or a measure the table needs that is None, is ``unverified`` (3.5, and 7 "A part with an unmeasured anchor").
       A magazine with an empty entry section is ``unverified`` with signal ``drum`` (3.7 step 2).
    4. The table: ``fit`` or ``no_fit``.

    The signals name the evidence that was measured. A ``not_judged`` verdict has none. ``frame_body`` is appended to every other verdict
    of a host whose ``frame_body`` flag is set (3.1 step 5).
    """
    if slot not in FIT_SLOTS or slot not in rules["slots"]:
        raise ValueError(f"slot {slot!r} is not a geometry slot (rules.slots: {list(rules['slots'])})")
    feats = host_feats or {}
    if feats.get("frame_conflict"):
        return Verdict("not_judged", ())
    if slot in _RAIL_SLOTS:
        value, signals = _rail_verdict(slot, feats, part, pair_seat, rules)
    elif slot == "muzzle":
        value, signals = _muzzle_verdict(feats, part, rules)
    else:
        value, signals = _magazine_verdict(feats, part, pair_seat, rules)
    if value == "not_judged":
        return Verdict(value, ())
    return Verdict(value, signals + (("frame_body",) if feats.get("frame_body") else ()))


def _rail_verdict(slot: str, feats: dict, part: dict, pair_seat: dict | None, rules: dict) -> tuple[str, tuple[str, ...]]:
    """Optic and underbarrel (spec 3.5). Width is checked on a toothed run only: an untoothed clamp has no calibration."""
    run = feats.get("toothed_run")
    ref = (pair_seat or {}).get("ref") or feats.get("ref")
    ref_len = None
    if run is None and ref is not None:
        ref_len = ref.get("flat_run_m") if ref.get("flat_run_m") is not None else ref.get("child_foot_length_m")
    measured = bool(part.get("anchor_measured"))
    foot_l, foot_w = part.get("foot_length_m"), part.get("foot_width_m")
    overhang = rules["clamp"]["overhang_max_m"]
    if run is not None:
        if not measured or foot_l is None or foot_w is None:
            return "unverified", ("rail_teeth",)
        fits = foot_l <= run["length_m"] + overhang + _EPS and foot_w + _EPS >= rules["clamp"]["ratio_min"] * run["width_m"]
        return ("fit" if fits else "no_fit"), ("rail_teeth",)
    if ref_len is not None:
        if not measured or foot_l is None:
            return "unverified", ("seat_ref",)
        return ("fit" if foot_l <= ref_len + overhang + _EPS else "no_fit"), ("seat_ref",)
    if slot == "optic" and feats.get("flat_seat"):
        return "unverified", ("rail_flat",)  # a flat seat places a seat and lists nothing (3.4 step 3)
    return "not_judged", ()


def _muzzle_verdict(feats: dict, part: dict, rules: dict) -> tuple[str, tuple[str, ...]]:
    """Muzzle (spec 3.6). The inner-ring band applies only when the device has an inner ring."""
    end = feats.get("barrel_end")
    if end is None or not end["od_m"] > 0:
        return "no_fit", ()
    evidence = end["evidence"]
    if evidence not in ("ring", "face_ring", "round_section"):
        raise ValueError(f"barrel_end.evidence {evidence!r} is not a BarrelEnd evidence")
    signals = ("barrel_round",) if evidence == "round_section" else ("barrel_ring",)
    mate = part.get("mate_d_m")
    if not part.get("anchor_measured") or mate is None:
        return "unverified", signals
    od = end["od_m"]
    lo, hi = rules["bore"]["od_ratio"]
    if not lo - _EPS <= mate / od <= hi + _EPS:
        return "no_fit", signals
    inner = part.get("device_inner_d")
    if inner is not None:
        ilo, ihi = rules["bore"]["inner_ratio"]
        if not ilo - _EPS <= inner / od <= ihi + _EPS:
            return "no_fit", signals
    return "fit", signals


def _magazine_verdict(feats: dict, part: dict, pair_seat: dict | None, rules: dict) -> tuple[str, tuple[str, ...]]:
    """Magazine (spec 3.7). A reference section of zero length or width is no usable reference, so the pair is ``not_judged``."""
    ref = (pair_seat or {}).get("well_ref") or feats.get("well_ref")
    if ref is None or not ref["length_m"] > 0 or not ref["width_m"] > 0:
        return "not_judged", ()
    if not part.get("anchor_measured"):
        return "unverified", ("well_entry",)
    section = part.get("entry_section")
    if section is None:
        return "unverified", ("drum",)  # an empty section: a drum, or a part that does not reach the plane
    tol = rules["well"]["tol"]
    off_l = abs(section[0] - ref["length_m"]) / ref["length_m"]
    off_w = abs(section[1] - ref["width_m"]) / ref["width_m"]
    return ("fit" if off_l <= tol + _EPS and off_w <= tol + _EPS else "no_fit"), ("well_entry",)


def _canon(obj):
    """``obj`` as plain JSON values with every float rounded to 1e-4 (spec 4.3). ``-0.0`` becomes ``0.0``; a non-finite float is an error."""
    if isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return obj
    if isinstance(obj, int):
        return int(obj)
    if hasattr(obj, "item") and not isinstance(obj, (dict, list, tuple)):  # a numpy scalar
        return _canon(obj.item())
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ValueError("fit_digest: a measure is not finite")
        return round(obj, _DIGEST_DECIMALS) + 0.0
    if isinstance(obj, (list, tuple)):
        return [_canon(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _canon(v) for k, v in obj.items()}
    raise TypeError(f"fit_digest: cannot hash a {type(obj).__name__}")


def _dump(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def fit_digest(measure_records: list[dict]) -> str:
    """First 16 hex characters of the sha256 of the canonical JSON of the measure records (spec 4.3).

    A record with a ``host`` key is a host-feature record (it must also carry ``slot``); one with a ``part`` key is a part-feature record.
    Host records come first, sorted by ``(host, slot)``; part records follow, sorted by ``part``. Floats are rounded to 1e-4. The JSON has
    sorted keys and no spaces, so the digest depends on neither dict order, set order nor ``PYTHONHASHSEED``.
    """
    hosts, parts = [], []
    for rec in measure_records:
        if "host" in rec and "part" not in rec:
            hosts.append(rec)
        elif "part" in rec and "host" not in rec:
            parts.append(rec)
        else:
            raise ValueError("fit_digest: a measure record carries exactly one of 'host' and 'part'")
    hosts, parts = [_canon(r) for r in hosts], [_canon(r) for r in parts]
    # the record's own JSON breaks a tie on equal keys, so the input order never reaches the output
    ordered = sorted(hosts, key=lambda r: (str(r["host"]), str(r.get("slot", "")), _dump(r))) + sorted(parts, key=lambda r: (str(r["part"]), _dump(r)))
    text = _dump(ordered)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# -- Host features (spec 3.4 step 4, 3.5 to 3.7, 3.11; plan slice S7) ---------------------------------------------------------------------------
#
# ``host_features`` is the one place the detectors meet a host. It is pure over what it is handed: it opens no file and imports neither
# ``geometry`` nor ``mounts`` (the S2 test forbids it), so the caller (``mounts.build_mounts``) loads the meshes and passes the versions and
# digests. Everything it returns is plain JSON (lists, floats, strings, bools), so a value read back from ``_fit_cache.json`` equals a fresh one.
#
# Frame. All detector input is in the RECORD frame (f, s, u) = (forward, side, up). ``frame_basis(axes)`` has the unit vectors of those three
# axes in asset coordinates as its rows, with side = cross(up, forward): that is row 0 of ``item_basis`` (``geometry``). ``to_fsu`` maps asset
# coordinates into the frame and ``from_fsu`` back.
#
# Inputs (keyword arguments):
#   rules          the ``attachment_rules.fit_geometry`` block.
#   axes           the record's ``{"forward": "+z", "up": "+y"}``.
#   mounts         the host's mounts as ``build_mounts`` has them after the child and sight-probe rungs and ``refuse_baked``, before
#                  ``refuse_filled``. Read per slot: ``source``, ``reason``, ``point``, ``span_m``, ``child_node``, ``occupied_by``, ``seats`` and
#                  (muzzle) ``bore_source``; and the ``sight_front`` probe seat for the sight clip.
#   mesh(drop)     ``(verts, tris)`` of the host minus the nodes in the frozenset ``drop`` (collision already dropped), asset coordinates, or None.
#   child_mesh(n)  ``(verts, tris)`` of the child node ``n`` alone, or None.
#   fused_parts    None, or ``(key, load)``: the host is a preset, ``key`` names the part set (it is an input of the cache), and ``load()`` lists
#                  ``{"id", "slot", "verts", "tris"}`` for every part of the host's pack (spec 3.2: the locator runs on presets only).
#   frame_changed  the record frame is the voted body frame (``frame_body`` goes on every slot); ``frame_conflict`` the vote failed (3.3 step 4).
#
# Result::
#
#   {"s0": float | None,                      # the centreline side coordinate the rail detectors used
#    "slots": {slot: host_feats},             # the four FIT_SLOTS; each value is what ``verdict`` reads as ``host_feats``
#    "seats": {slot: {"feature", ...}},       # what ``mounts`` writes (see below); a slot with no detector seat is absent
#    "located": [{"part", "slot", "t", "hit"}]}  # the placements of fused parts on a preset (Q-G11 reads "slot")
#
# ``slots[slot]`` follows the shapes of ``fit_types`` (``frame_conflict``, ``frame_body``, ``toothed_run``, ``ref``, ``flat_seat``, ``barrel_end``,
# ``well_ref``) and adds keys ``verdict`` ignores: ``barrel_end.centre_su`` / ``face_f``, ``well_ref.u_rb`` / ``source``, and, on a slot whose
# mount lists several seats (A1, ``seats``), ``seat_refs`` / ``well_refs`` = ``{child node: ref}``, which the caller picks from as ``pair_seat``.
# ``seats[slot]`` is ``{"feature": ...}`` plus, for a rail seat, ``{"f", "s", "u", "span_m"}`` (the seat point in the record frame and the run
# length). A slot with an authored seat (``child_node`` / ``override``) has ``{"feature": "seat_ref"}`` (optic, underbarrel) or
# ``{"feature": "well_ref"}`` (magazine) and nothing else. The muzzle has ``{"feature": "barrel_ring" | "barrel_round"}``.
#
# Readings of the spec (each is a choice where it is silent; the slice report lists them):
# * Which run. A detector seat takes the LONGEST toothed run after the sight clip (the rearmost on a tie). An authored seat's ``toothed_run`` is the
#   longest run whose f extent (unclipped) contains the seat's f, with the clipped length; when none contains it there is no ``toothed_run`` and the
#   verdict falls to ``ref``.
# * The flat run of ``ref``. ``fit_rails.flat_seat`` returns the longest flat run of the zone (and None on a host with a toothed top run), so
#   ``ref.flat_run_m`` is that run's length when it contains the reference contact's f, and None otherwise (a stepped seat, or an underbarrel).
# * A slot refused by policy before the detectors (``none`` / ``slot_disabled``) is skipped: nothing reads its features.

FIT_CACHE_NAME = "_fit_cache.json"
_AUTHORED = ("child_node", "override")
_MOUNT_KEYS = ("source", "reason", "point", "span_m", "child_node", "occupied_by", "seats", "bore_source")
_CACHE_KEEP = 8  # fingerprints kept per host entry (the oldest go first)


def _code_digest(data: bytes) -> str:
    """First 12 hex characters of the sha256 of source text with CRLF turned into LF (a CRLF worktree and the LF blob agree)."""
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()[:12]


def _fit_code_digests() -> dict[str, str]:
    """``{module: digest}`` of every ``fit_*.py`` and of ``mount_probe.py`` (the ring estimator the detectors call): the code of the fit gate."""
    here = Path(__file__).resolve().parent
    names = sorted(p.stem for p in here.glob("fit_*.py")) + ["mount_probe"]
    return {name: _code_digest((here / f"{name}.py").read_bytes()) for name in names}


# Computed once at import. The geometry cache fingerprint (``fd``) and the fit cache key both read it at CALL time, so a test can swap it.
FIT_CODE_DIGESTS = _fit_code_digests()


def _unit(signed: str) -> np.ndarray:
    v = np.zeros(3)
    v["xyz".index(signed[1])] = 1.0 if signed[0] == "+" else -1.0
    return v


def frame_basis(axes: dict) -> np.ndarray:
    """(3, 3) with the unit vectors of forward, side and up, in asset coordinates, as rows; side = cross(up, forward) (see the section header)."""
    fwd, up = _unit(axes["forward"]), _unit(axes["up"])
    return np.array([fwd, np.cross(up, fwd), up])


def to_fsu(basis: np.ndarray, verts) -> np.ndarray:
    """Asset coordinates (N, 3) in the (f, s, u) frame of ``basis``."""
    return np.asarray(verts, dtype=np.float64).reshape(-1, 3) @ basis.T


def from_fsu(basis: np.ndarray, f: float, s: float, u: float) -> list[float]:
    """The asset-coordinate point of ``(f, s, u)``."""
    return [float(c) for c in np.array([f, s, u], dtype=np.float64) @ basis]


def _r(x) -> float:
    return round(float(x), _DIGEST_DECIMALS) + 0.0


def _fp(obj) -> str:
    """First 16 hex characters of the sha256 of the canonical JSON of ``obj`` (floats rounded to 1e-4)."""
    return hashlib.sha256(_dump(_canon(obj)).encode("utf-8")).hexdigest()[:16]


def load_fit_cache(path: Path) -> dict:
    """The fit cache, or an empty one when the file is absent or unreadable."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return doc if isinstance(doc, dict) else {}


def save_fit_cache(path: Path, cache: dict) -> None:
    """Write the fit cache with LF line endings (sorted keys, no spaces), as the geometry cache is."""
    data = json.dumps(cache, sort_keys=True, separators=(",", ":")) + "\n"
    with open(path, "wb") as fh:
        fh.write(data.encode("utf-8"))


def _disabled(mount: dict) -> bool:
    return mount["source"] == "none" and mount["reason"] == "slot_disabled"


def _ref(flat: RailRun | None, seat_f: float, span_m: float | None) -> dict:
    """The authored reference of an optic or underbarrel seat (spec 3.5): the flat run under its contact (None when no flat run covers it),
    and the reference child's own foot length."""
    covered = flat is not None and flat.f0 - _EPS <= seat_f <= flat.f1 + _EPS
    return {"flat_run_m": _r(flat.f1 - flat.f0) if covered else None, "child_foot_length_m": None if span_m is None else _r(span_m)}


def _ref_usable(ref: dict) -> bool:
    return ref["flat_run_m"] is not None or ref["child_foot_length_m"] is not None


def _well_dict(ref: WellRef) -> dict:
    return {"length_m": ref.length_m, "width_m": ref.width_m, "u_rb": ref.u_rb, "source": ref.source}


def _compute(rules, *, axes, mounts, mesh, child_mesh, fused_parts, frame_changed, frame_conflict) -> dict:
    out = {"s0": None, "slots": {slot: {} for slot in FIT_SLOTS}, "seats": {}, "located": []}
    if frame_conflict:
        # spec 3.3 step 4 and INV-27: no detector runs on a host whose frame could not be decided, and every pair on it is not_judged
        out["slots"] = {slot: {"frame_conflict": True} for slot in FIT_SLOTS}
        return out
    basis = frame_basis(axes)
    slots, seats = out["slots"], out["seats"]
    if frame_changed:
        for feats in slots.values():
            feats["frame_body"] = True

    # -- presets: locate the fused parts (translation only), then every host mesh below is stripped of the slot parts (spec 3.2, E1.3) -----------------------
    placements: list[Placement] = []
    part_meshes: dict[str, np.ndarray] = {}
    part_slot: dict[str, str | None] = {}
    if fused_parts is not None:
        full = mesh(frozenset())
        if full is not None:
            for part in sorted(fused_parts[1](), key=lambda p: p["id"]):
                pv = np.asarray(part["verts"], dtype=np.float64).reshape(-1, 3)
                found = locate_by_translation(full[0], pv, rules)
                for pl in found:
                    placements.append(dataclasses.replace(pl, part=part["id"]))
                    out["located"].append({"part": part["id"], "slot": part.get("slot"), "t": [_r(c) for c in pl.t], "hit": _r(pl.hit)})
                if found:
                    part_meshes[part["id"]], part_slot[part["id"]] = pv, part.get("slot")

    # G1 errata E1.3: "minus the located parts" is minus the parts that FILL A SLOT (the scope, the silencer, a magazine). A preset's own body parts
    # (receiver, rail, barrel, handguard) are located too, but stripping them would empty the host the detectors measure.
    filling = [pl for pl in placements if part_slot.get(pl.part)]

    memo: dict[frozenset, tuple[np.ndarray, np.ndarray] | None] = {}

    def reduced(drop: frozenset):
        """The host minus the nodes in ``drop`` and minus the located slot parts (errata E1.3), in the (f, s, u) frame."""
        if drop not in memo:
            got = mesh(drop)
            if got is None:
                memo[drop] = None
            else:
                v, t = np.asarray(got[0], dtype=np.float64).reshape(-1, 3), np.asarray(got[1], dtype=np.int64).reshape(-1, 3)
                if filling:
                    v, t = strip(v, t, filling, part_meshes, rules)
                memo[drop] = (to_fsu(basis, v), t)
        return memo[drop]

    # -- muzzle: the barrel end (spec 3.6). It gates the slot and names the feature; the seat stays the A0 probe's ----------------------------
    m_muz = mounts["muzzle"]
    end = None
    if not _disabled(m_muz):
        got = reduced(frozenset(m_muz["occupied_by"]))
        if got is not None:
            end = barrel_end(got[0], got[1], m_muz, rules)
    if end is not None:
        slots["muzzle"]["barrel_end"] = {"od_m": end.od_m, "evidence": end.evidence, "centre_su": [end.centre_su[0], end.centre_su[1]],
                                         "face_f": end.face_f}
        if m_muz["source"] == "probe":
            seats["muzzle"] = {"feature": "barrel_round" if end.evidence == "round_section" else "barrel_ring"}

    # -- the centreline: the muzzle seat's side coordinate when the muzzle has a barrel end, else the middle of the host's side extent (3.4 step 1)
    s0 = None
    if end is not None and m_muz.get("point") is not None:
        s0 = float(np.dot(m_muz["point"], basis[1]))
    else:
        whole = reduced(frozenset())
        if whole is not None and len(whole[0]):
            s0 = float(whole[0][:, 1].min() + whole[0][:, 1].max()) / 2.0
    out["s0"] = None if s0 is None else _r(s0)

    # -- optic (top) and underbarrel (bottom): rails, flat seat, sight clip (spec 3.4) -------------------------------------------------------
    rail = rules["rail"]
    seat_len = rail["default_seat_len_m"]
    sight = mounts.get("sight_front")
    sight_f = float(np.dot(sight["point"], basis[0])) if sight and sight["source"] == "probe" and sight["point"] is not None else None

    def rail_slot(slot: str, side: str) -> None:
        m, feats = mounts[slot], slots[slot]
        if _disabled(m) or s0 is None:
            return
        got = reduced(frozenset(m["occupied_by"]))
        if got is None:
            return
        vf, tf = got
        runs = rail_runs(vf, tf, side, s0, rules)

        def clipped(run: RailRun) -> RailRun | None:
            # spec 3.4 step 4: an optic span ends sight_clear_m behind a probe front sight. The underbarrel hangs below and never covers it.
            return run if side == "bottom" or sight_f is None else clip_run(run, sight_f, rail["sight_clear_m"])

        flat = flat_seat(vf, tf, s0, rules) if side == "top" and not runs else None
        if m["source"] in _AUTHORED:
            seat_f = float(np.dot(m["point"], basis[0]))
            feats["ref"] = _ref(flat, seat_f, m["span_m"])
            if m.get("seats"):
                feats["seat_refs"] = {node: _ref(flat, float(np.dot(s["point"], basis[0])), s["span_m"]) for node, s in sorted(m["seats"].items())}
            on = [r for r in runs if r.f0 - _EPS <= seat_f <= r.f1 + _EPS]
            if on:
                run = max(on, key=lambda r: (r.f1 - r.f0, -r.f0))
                cut = clipped(run)
                if cut is not None:
                    feats["toothed_run"] = {"length_m": _r(cut.f1 - cut.f0), "width_m": run.width_m}
            if _ref_usable(feats["ref"]):
                seats[slot] = {"feature": "seat_ref"}
            return
        if m["source"] != "none" or m["reason"] != "no_child_no_probe":
            return
        picked = None
        picks = [(c, r) for r in runs for c in (clipped(r),) if c is not None]
        if picks:
            cut, run = max(picks, key=lambda p: (p[0].f1 - p[0].f0, -p[0].f0))
            feats["toothed_run"] = {"length_m": _r(cut.f1 - cut.f0), "width_m": run.width_m}
            picked = (cut, "rail_teeth")
        elif flat is not None:
            cut = clipped(flat)
            if cut is not None:
                feats["flat_seat"] = True
                picked = (cut, "rail_flat")
        if picked is not None:
            f, u = seat_point(picked[0], seat_len)
            seats[slot] = {"feature": picked[1], "f": f, "s": _r(s0), "u": u, "span_m": _r(picked[0].f1 - picked[0].f0)}

    rail_slot("optic", "top")
    rail_slot("underbarrel", "bottom")

    # -- magazine: the authored magazine's entry section (spec 3.7 step 1) ---------------------------------------------------------------------
    m_mag = mounts["magazine"]

    def well(node: str) -> WellRef | None:
        host, mag = reduced(frozenset({node})), child_mesh(node)
        if host is None or mag is None:
            return None
        return well_reference(host[0], host[1], to_fsu(basis, mag[0]), mag[1], rules)

    if not _disabled(m_mag):
        if m_mag["source"] in _AUTHORED and m_mag.get("child_node"):
            ref = well(m_mag["child_node"])
            if ref is not None:
                slots["magazine"]["well_ref"] = _well_dict(ref)
                seats["magazine"] = {"feature": "well_ref"}
            if m_mag.get("seats"):
                refs = {node: well(node) for node in sorted(m_mag["seats"])}
                slots["magazine"]["well_refs"] = {node: _well_dict(r) for node, r in refs.items() if r is not None}
        # E2-Q3: no else. A fused magazine with no baked child gets no well reference (S7 fold-in 4 is retired), so its pairs are not_judged.

    out["located"].sort(key=lambda p: (p["part"], p["t"]))
    return json.loads(json.dumps(out))


def host_features(
    rules: dict, *, axes: dict, mounts: dict, mesh: Callable, child_mesh: Callable, fused_parts: tuple | None = None,
    frame_changed: bool = False, frame_conflict: bool = False, cache: dict | None = None, cache_id: str | None = None,
    cache_key: dict | None = None,
) -> dict:
    """The features of one eligible host, computed once and cached (spec 3.11). See the section header for the arguments and the result.

    With ``cache`` (a plain dict the caller owns and persists with ``load_fit_cache`` / ``save_fit_cache``), ``cache_id`` (the host's GLB id) and
    ``cache_key`` (the host's GLB sha256, ``glb_node``, ``glb_scale``, ``WEAPON_GEOMETRY_VERSION``, ``WEAPON_ATTACH_VERSION`` and
    ``attach_rules_digest``, which holds the ``fit_geometry`` block: spec 3.11) the result is read from or stored in ``cache[cache_id]``. The entry
    is valid while its key matches the ``cache_key`` plus ``FIT_CODE_DIGESTS`` read now; inside it one result is kept per fingerprint of the other
    inputs (axes, the frame flags, the mounts the detectors read, the preset part set), because the record frame, a mount override or the part
    set change the features of the same file. A hit equals a recompute. Without a cache nothing is stored.
    """
    kwargs = dict(axes=axes, mounts=mounts, mesh=mesh, child_mesh=child_mesh, fused_parts=fused_parts, frame_changed=frame_changed,
                  frame_conflict=frame_conflict)
    if cache is None or cache_id is None or cache_key is None:
        return _compute(rules, **kwargs)
    key = _fp({**cache_key, "code": FIT_CODE_DIGESTS})
    entry = cache.get(cache_id)
    if not isinstance(entry, dict) or entry.get("key") != key:
        entry = {"key": key, "by_inputs": {}}
        cache[cache_id] = entry
    view = {slot: {k: mounts[slot].get(k) for k in _MOUNT_KEYS} for slot in FIT_SLOTS}
    view["sight_front"] = {k: (mounts.get("sight_front") or {}).get(k) for k in ("source", "point")}
    fp = _fp({"axes": axes, "mounts": view, "changed": bool(frame_changed), "conflict": bool(frame_conflict),
              "parts": fused_parts[0] if fused_parts is not None else None})
    hit = entry["by_inputs"].get(fp)
    if hit is not None:
        return copy.deepcopy(hit)
    feats = _compute(rules, **kwargs)
    entry["by_inputs"][fp] = copy.deepcopy(feats)
    while len(entry["by_inputs"]) > _CACHE_KEEP:
        del entry["by_inputs"][next(iter(entry["by_inputs"]))]
    return feats
