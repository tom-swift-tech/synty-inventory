"""The geometry fit gate G1: the facade (docs/weapon_attach_geometry.md 3.1, 3.5 to 3.7, 3.11, 4.3).

Callers import from here only. The types live in ``fit_types`` and the detectors in ``fit_locate``, ``fit_rails``, ``fit_bore`` and
``fit_well``; all are re-exported, so the detector modules never import this one (no import cycle). This module holds the two pure
functions that need none of them:

* ``verdict`` decides ``V(P, H, X)`` from host features the detectors measured and the part's anchor and footprint. The shapes of
  ``host_feats``, ``part`` and ``pair_seat`` are documented in ``fit_types``. Every tolerance is read from ``rules`` (the
  ``attachment_rules.fit_geometry`` block, spec 4.1) and none is written here.
* ``fit_digest`` hashes the measure records (spec 4.3).

Imports: the standard library and ``synty_inventory`` only (AC144).
"""

from __future__ import annotations

import hashlib
import json
import math

from .fit_bore import barrel_end, device_inner_d
from .fit_locate import locate_by_translation, strip
from .fit_rails import flat_seat, rail_runs
from .fit_types import FIT_SLOTS, SIGNALS, VERDICT_VALUES, BarrelEnd, Placement, RailRun, Verdict, WellRef
from .fit_well import entry_section, well_reference

__all__ = [
    "BarrelEnd", "FIT_SLOTS", "Placement", "RailRun", "SIGNALS", "VERDICT_VALUES", "Verdict", "WellRef",
    "barrel_end", "device_inner_d", "entry_section", "fit_digest", "flat_seat", "locate_by_translation", "rail_runs", "strip",
    "verdict", "well_reference",
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
