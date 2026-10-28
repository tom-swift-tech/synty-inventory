"""The arithmetic of ``weapons attach-calibrate``: does each literal of the fit gate cover its positives? (docs/weapon_attach_geometry.md 3.2, 3.11,
4.2; G1 errata E1.1; INV-24, AC137; plan slice S9.)

The oracle (spec 3.2) is the set of authored assemblies: a preset's fused parts (found by translation), the A1 twins seated on the child they match,
and the baked children of the four slots. ``cli`` gathers it from a built directory and the GLBs and hands this module plain data, so nothing here
opens a file, reads the clock or touches ``geometry``, ``mounts``, ``compat``, ``directory`` or ``cli`` (the AC144 dependency rule: the standard
library, numpy and the sibling ``fit_*`` detectors only). It is deliberately not a ``fit_*.py``: that glob keys the fit caches
(``fit_geometry.FIT_CODE_DIGESTS``), and an edit to this reporting tool must not rebuild every host (G1 S9b).

Two layers, both pure:

* ``observe_positive`` runs the detectors on ONE positive (a dict ``cli`` builds, shape below) and returns its observations: the measure of each
  literal the positive bears on, in the literal's own unit (a length in metres, a ratio, a share, degrees). It calls the same detectors the
  verdict does, with the same rules block, so a positive is judged by the code that will judge a pair.
* ``calibrate`` folds the observations into one row per literal of spec 4.2 (the positives by class, the extreme observed value, the margin and the
  literal), enforces INV-24 (an upper bound at or above the largest observed value, a lower bound at or below the smallest, a band around both),
  and names every literal that has no positives. ``sheet_pairs`` picks the two pair lists ``attach-preview --pairs`` takes.

A positive (``pos``): ``cls`` (``preset`` | ``twin`` | ``baked``), ``slot``, ``host`` and ``part`` (ids, for the report), optional ``tags``, and per slot

* optic, underbarrel: ``mesh`` = ``(verts, tris)`` of the host minus the slot's children and the located slot parts, in the host's (f, s, u) frame;
  ``s0`` the centreline side coordinate; ``seat`` = the part's contact point ``(f, s, u)``; ``foot_length_m`` / ``foot_width_m``; ``sight_f`` (or None)
  the probe front sight's f, which clips the run as the seat does (spec 3.4 step 4);
* muzzle: ``mesh`` as above (minus the muzzle devices), ``bore_source`` the host muzzle mount's, ``seat`` the device's mating-face centre in (f, s, u),
  ``axis_fsu`` its bore direction in the same frame, ``mate_d_m``, and ``device`` = ``{"verts", "anchor"}`` for the inner ring (``device_inner_d``);
* magazine: ``ref_host`` = ``(verts, tris)`` of the host minus the reference magazine, ``ref_mag`` = the reference magazine's ``(verts, tris)``, and
  ``part_mesh`` = the candidate magazine placed on that seat, all in (f, s, u).

Readings of the spec (each is a choice where 4.2 is silent; the slice report lists them):

* **Overhang and ratio** are read on a toothed run that holds the contact (the run after the sight clip, as the verdict reads it); a positive on an
  untoothed seat bears on neither. Both rails (optic, underbarrel) feed them. ``rail.zone`` and ``depth`` are optic-only (the contact's share of the
  host's f extent from the butt; the contact's u minus the run's tooth tops).
* **Tilt** is the angle between the device's bore axis and the host's forward axis; **offset** is the distance of the device's mating-face centre from
  the barrel end's centre in (s, u). Both are zero on an authored, axis-aligned assembly, which is what the spec's table records.
* **circ_min** is enforced on the positives whose host barrel end is proved by a face ring (evidence (ii), errata E1.1): the hull share of the end slab.
* **well.tol** is the larger of the length and width deviations of the candidate's entry section from the reference.
* **Populations (S10a).** Each row carries ``spec_n``, the count its 4.2 line states (``SPEC_N``), beside ``n``, the tool's own. ``n`` counts
  observations: a twin seated on the child it twins is a second observation of that seat. A difference of count is read from the classes and reported,
  never tuned away.
* **depth** is a review list (spec 3.9): it never fails the check, and its pairs outside ``depth.lo_m`` .. ``depth.hi_m`` are listed.
* ``rules['exceptions']`` lists class keys (strings ``<slot>:<class>``, e.g. ``optic:preset``, no asset ids); an observation whose tags (its own ``<slot>:<class>``) hit one is counted apart and bounds nothing.
"""

from __future__ import annotations

import math

import numpy as np

from .fit_bore import _hull_area, _used_vertices, barrel_end, device_inner_d
from .fit_rails import clip_run, rail_runs
from .fit_well import entry_section, well_reference

_EPS = 1e-9
_DECIMALS = 4  # printed values (spec 4.3 rounds stored measures to 1e-4)
_NOISE = 6  # an observation is rounded here first: a difference of two 1e-4 values carries float noise far below any literal
_SAMPLE = 5  # violating or outside positives listed per row

FRAME_ROW = "geometry._FRAME_BORE_MAX_M"

# The count of positives each row of spec 4.2 states (column "positives (n)"), by row id: a literal table, so a population that drifts from the spec
# shows beside the tool's own count. None where 4.2 states no number (rail.zone: "all optic positives"). bore.circ_min is the 4 of errata E1.1's table
# (the bore positives proved by a face ring, evidence (ii)); 4.2 itself has no such row.
SPEC_N = {
    "clamp.overhang_max_m": 16, "clamp.ratio_min": 16, "rail.zone": None, "depth": 16, "bore.od_ratio": 11, "bore.inner_ratio": 6,
    "bore.axis_offset_max_m": 11, "bore.axis_tilt_max_deg": 11, "bore.circ_min": 4, "well.tol": 15, FRAME_ROW: 3,
}

# The locator placements AC131 counts on the 14 Military presets (errata E1-Q1: 163, "other" 117), by the part's attachment-block slot ("other": no slot).
PLACEMENTS_SPEC = {
    "total": 163,
    "by_slot": {"optic": 14, "magazine": 15, "muzzle": 4, "underbarrel": 4, "laser_light": 3, "sight_front": 6, "other": 117},
}

# (row id, measure, kind, literal from (rules, frame_bore_max_m)). kind: upper (literal >= max), lower (literal <= min), band (literal interval
# around [min, max]) or review (a band that is only listed, never enforced).
_ROWS = (
    ("clamp.overhang_max_m", "overhang", "upper", lambda r, f: r["clamp"]["overhang_max_m"]),
    ("clamp.ratio_min", "ratio", "lower", lambda r, f: r["clamp"]["ratio_min"]),
    ("rail.zone", "zone", "band", lambda r, f: list(r["rail"]["zone"])),
    ("depth", "depth", "review", lambda r, f: [r["depth"]["lo_m"], r["depth"]["hi_m"]]),
    ("bore.od_ratio", "od_ratio", "band", lambda r, f: list(r["bore"]["od_ratio"])),
    ("bore.inner_ratio", "inner_ratio", "band", lambda r, f: list(r["bore"]["inner_ratio"])),
    ("bore.axis_offset_max_m", "axis_offset", "upper", lambda r, f: r["bore"]["axis_offset_max_m"]),
    ("bore.axis_tilt_max_deg", "axis_tilt", "upper", lambda r, f: r["bore"]["axis_tilt_max_deg"]),
    ("bore.circ_min", "circ", "lower", lambda r, f: r["bore"]["circ_min"]),
    ("well.tol", "well_off", "upper", lambda r, f: r["well"]["tol"]),
    (FRAME_ROW, "frame_ring", "upper", lambda r, f: f),
)
ROW_IDS = tuple(row[0] for row in _ROWS)


def _round(x, digits: int = _DECIMALS) -> float:
    return round(float(x), digits) + 0.0


def _obs(key: str, value, pos: dict) -> dict:
    return {"key": key, "value": None if value is None else _round(value, _NOISE), "cls": pos["cls"], "slot": pos.get("slot"),
            "host": pos.get("host", ""), "part": pos.get("part", ""), "tags": sorted(pos.get("tags") or ())}


def _unmeasured(pos: dict, reason: str) -> dict:
    return {**_obs("unmeasured", None, pos), "reason": reason}


def slab_fill(verts_fsu, tris, rules: dict) -> float | None:
    """The share of the host's end slab (``bore.end_slab_m`` behind the forward extreme) that fills its circle: hull area over the disc of diameter
    ``od_m`` -- the quantity ``barrel_end`` compares with ``bore.circ_min`` (errata E1.1). None for an empty mesh or a slab with no extent."""
    v = _used_vertices(verts_fsu, tris)
    if not len(v):
        return None
    face = float(v[:, 0].max())
    lat = v[v[:, 0] >= face - rules["bore"]["end_slab_m"] - _EPS][:, 1:]
    centre = (lat.min(axis=0) + lat.max(axis=0)) / 2.0
    od = 2.0 * float(np.linalg.norm(lat - centre, axis=1).max())
    if od <= _EPS:
        return None
    return _hull_area(lat) / (math.pi * (od / 2.0) ** 2)


def centreline(muzzle_mesh, whole_mesh, muzzle_point_s, bore_source, rules: dict) -> float | None:
    """The centreline side coordinate the rail detectors use (spec 3.4 step 1): the muzzle seat's, when the muzzle has a barrel end, else the middle of
    the host's side extent. ``muzzle_mesh`` / ``whole_mesh`` are ``(verts, tris)`` in (f, s, u) or None."""
    if muzzle_mesh is not None and muzzle_point_s is not None:
        if barrel_end(muzzle_mesh[0], muzzle_mesh[1], {"bore_source": bore_source}, rules) is not None:
            return float(muzzle_point_s)
    if whole_mesh is not None and len(whole_mesh[0]):
        v = np.asarray(whole_mesh[0], dtype=np.float64).reshape(-1, 3)
        return float(v[:, 1].min() + v[:, 1].max()) / 2.0
    return None


def toothed(mesh, side: str, s0: float | None, rules: dict) -> bool:
    """Does the host (reduced as for that slot) carry a toothed run on ``side`` (``top`` | ``bottom``)? Used to pick the toothed-host sheet."""
    if mesh is None or s0 is None or not len(mesh[0]):
        return False
    return bool(rail_runs(mesh[0], mesh[1], side, s0, rules))


# -- one positive -------------------------------------------------------------------------------------------


def _observe_rail(pos: dict, rules: dict) -> list[dict]:
    slot = pos["slot"]
    side = "top" if slot == "optic" else "bottom"
    v = np.asarray(pos["mesh"][0], dtype=np.float64).reshape(-1, 3)
    if not len(v) or pos.get("s0") is None:
        return [_unmeasured(pos, "no_host_mesh")]
    f, _s, u = (float(c) for c in pos["seat"])
    out: list[dict] = []
    if slot == "optic":
        lo, hi = float(v[:, 0].min()), float(v[:, 0].max())
        if hi - lo > _EPS:
            out.append(_obs("zone", (f - lo) / (hi - lo), pos))
    on = [r for r in rail_runs(v, pos["mesh"][1], side, pos["s0"], rules) if r.f0 - _EPS <= f <= r.f1 + _EPS]
    if not on:
        return out or [_unmeasured(pos, "no_toothed_run")]
    run = max(on, key=lambda r: (r.f1 - r.f0, -r.f0))
    if side == "top" and pos.get("sight_f") is not None:
        run = clip_run(run, float(pos["sight_f"]), rules["rail"]["sight_clear_m"])
        if run is None:
            return out
    if pos.get("foot_length_m") is not None:
        out.append(_obs("overhang", pos["foot_length_m"] - (run.f1 - run.f0), pos))
    if pos.get("foot_width_m") is not None and run.width_m > 0:
        out.append(_obs("ratio", pos["foot_width_m"] / run.width_m, pos))
    if slot == "optic":
        out.append(_obs("depth", u - run.top_u, pos))
    return out


def _observe_muzzle(pos: dict, rules: dict) -> list[dict]:
    v, t = pos["mesh"]
    end = barrel_end(v, t, {"bore_source": pos.get("bore_source")}, rules)
    if end is None:
        return [_unmeasured(pos, "no_barrel_end")]
    out: list[dict] = []
    if pos.get("mate_d_m"):
        out.append(_obs("od_ratio", pos["mate_d_m"] / end.od_m, pos))
    device = pos.get("device")
    inner = device_inner_d(device["verts"], device["anchor"], rules) if device else None
    if inner is not None:
        out.append(_obs("inner_ratio", inner / end.od_m, pos))
    _f, s, u = (float(c) for c in pos["seat"])
    out.append(_obs("axis_offset", math.hypot(s - end.centre_su[0], u - end.centre_su[1]), pos))
    axis = np.asarray(pos["axis_fsu"], dtype=np.float64).reshape(3)
    norm = float(np.linalg.norm(axis))
    if norm > _EPS:
        out.append(_obs("axis_tilt", math.degrees(math.acos(min(1.0, abs(float(axis[0])) / norm))), pos))
    if end.evidence == "face_ring":  # errata E1.1: the enforced positives are the ones proved by a face ring
        fill = slab_fill(v, t, rules)
        if fill is not None:
            out.append(_obs("circ", fill, pos))
    return out


def _observe_magazine(pos: dict, rules: dict) -> list[dict]:
    ref = well_reference(pos["ref_host"][0], pos["ref_host"][1], pos["ref_mag"][0], pos["ref_mag"][1], rules)
    if ref is None:
        return [_unmeasured(pos, "no_well_reference")]
    section = entry_section(pos["part_mesh"][0], pos["part_mesh"][1], ref.u_rb - rules["well"]["entry_depth_m"])
    if section is None:
        return [_unmeasured(pos, "no_entry_section")]
    off = max(abs(section[0] - ref.length_m) / ref.length_m, abs(section[1] - ref.width_m) / ref.width_m)
    return [_obs("well_off", off, pos)]


def observe_positive(pos: dict, rules: dict) -> list[dict]:
    """The observations of one positive (see the module docstring for its shape). A positive a detector cannot read gives one ``unmeasured``
    record with the reason; it bounds nothing and is reported."""
    slot = pos["slot"]
    if slot in ("optic", "underbarrel"):
        return _observe_rail(pos, rules)
    if slot == "muzzle":
        return _observe_muzzle(pos, rules)
    if slot == "magazine":
        return _observe_magazine(pos, rules)
    raise ValueError(f"slot {slot!r} is not a geometry slot")


def frame_observation(host: str, ring_d_m: float) -> dict:
    """The observation of one frame-changed host: the bore ring at the muzzle end that confirmed its body axis (spec 3.3 step 3, Q-G4)."""
    return _obs("frame_ring", ring_d_m, {"cls": "frame", "slot": None, "host": host, "part": ""})


# -- the rows -----------------------------------------------------------------------------------------------


def _who(o: dict) -> dict:
    return {"cls": o["cls"], "host": o["host"], "part": o["part"]}


def _row(rid: str, measure: str, kind: str, literal, observations: list[dict], excepted_tags: set[str]) -> dict:
    mine = [o for o in observations if o["key"] == measure]
    used = [o for o in mine if not excepted_tags & set(o["tags"])]
    by_class: dict[str, list[dict]] = {}
    for o in used:
        by_class.setdefault(o["cls"], []).append(o)
    row: dict = {
        "literal": rid, "kind": kind, "value": literal, "n": len(used), "spec_n": SPEC_N.get(rid), "excepted": len(mine) - len(used),
        "positives": {cls: {"n": len(v), "min": _round(min(o["value"] for o in v)), "max": _round(max(o["value"] for o in v))}
                      for cls, v in sorted(by_class.items())},
    }
    if not used:
        row.update(observed=None, margin=None, ok=kind == "review", covered=False)
        return row
    lo, hi = min(o["value"] for o in used), max(o["value"] for o in used)
    if kind == "upper":
        bad = [o for o in used if o["value"] > literal + _EPS]
        row.update(observed=_round(hi), margin=_round(literal - hi), worst=_who(max(used, key=lambda o: o["value"])))
    elif kind == "lower":
        bad = [o for o in used if o["value"] < literal - _EPS]
        row.update(observed=_round(lo), margin=_round(lo - literal), worst=_who(min(used, key=lambda o: o["value"])))
    else:  # band, review
        bad = [o for o in used if o["value"] < literal[0] - _EPS or o["value"] > literal[1] + _EPS]
        row.update(observed=[_round(lo), _round(hi)], margin=[_round(lo - literal[0]), _round(literal[1] - hi)])
    row["covered"] = True
    if kind == "review":
        row["ok"] = True
        row["outside"] = [{**_who(o), "value": _round(o["value"])} for o in bad[:_SAMPLE]]
        row["outside_n"] = len(bad)
    else:
        row["ok"] = not bad
        if bad:
            row["violations"] = [{**_who(o), "value": _round(o["value"])} for o in bad[:_SAMPLE]]
            row["violations_n"] = len(bad)
    return row


def calibrate(observations: list[dict], rules: dict, *, frame_bore_max_m: float) -> dict:
    """``{"ok", "rows", "failed", "unmeasured"}``: one row per literal of spec 4.2 (``ROW_IDS``) and the literals that fail INV-24.

    ``rules`` is the ``attachment_rules.fit_geometry`` block. A literal fails when it has no positives (``no_positives``; the review row ``depth`` is
    exempt) or when a positive lies beyond it (``exceeded``). ``frame_bore_max_m`` is ``geometry._FRAME_BORE_MAX_M``, which is not in the rules.
    """
    excepted = set(rules.get("exceptions") or ())
    rows = [_row(rid, measure, kind, get(rules, frame_bore_max_m), observations, excepted) for rid, measure, kind, get in _ROWS]
    failed = [{"literal": r["literal"], "reason": "no_positives" if not r["covered"] else "exceeded"} for r in rows if not r["ok"]]
    unmeasured: dict[str, int] = {}
    for o in observations:
        if o["key"] == "unmeasured":
            name = f"{o['slot']}:{o['cls']}:{o['reason']}"
            unmeasured[name] = unmeasured.get(name, 0) + 1
    return {"ok": not failed, "rows": rows, "failed": failed, "unmeasured": dict(sorted(unmeasured.items()))}


def parameters(rules: dict) -> dict:
    """The detector parameters (spec 4.2: not tolerances on a pair), as the rules block carries them."""
    return {"locator": dict(rules["locator"]), "flat": dict(rules["flat"]), "well_entry_depth_m": rules["well"]["entry_depth_m"],
            "rail": {k: v for k, v in rules["rail"].items() if k != "zone"},
            "bore": {k: rules["bore"][k] for k in ("end_slab_m", "round_min", "barrel_od_max_m")}}


# -- the sheets ---------------------------------------------------------------------------------------------


def _pick(directory: dict, host: str, slots: tuple[str, ...], signal: str | None, tier_order: tuple[str, ...]) -> dict | None:
    """One pair on ``host`` for the parts of ``slots``: a LISTED pair (carrying ``signal`` when one is given), the smallest part id first, else the
    best-tier PENDING pair (``tier_order`` is best first, ties by part id). None when the host has no pair of those slots."""
    listed, pending = [], []
    for w in directory["weapons"]:
        att = w.get("attachment")
        if not att or att["slot"] not in slots:
            continue
        for e in att["compatible_hosts"]:
            if e["host"] == host and (signal is None or signal in (e.get("signals") or ())):
                listed.append((w["id"], e["tier"]))
        for e in att["pending_hosts"]:
            if e["host"] == host:
                pending.append((w["id"], e["tier"]))
    if listed:
        return {"part": min(listed)[0], "host": host}
    if pending:
        rank = {t: i for i, t in enumerate(tier_order)}
        part, _ = min(pending, key=lambda p: (rank.get(p[1], len(rank)), p[0]))
        return {"part": part, "host": host}
    return None


def sheet_pairs(directory: dict, toothed_hosts, frame_hosts, tier_order: tuple[str, ...]) -> dict:
    """``{"toothed": [...], "frame": [...]}``, each a list of ``{"part", "host"}`` (the pair list ``attach-preview --pairs`` takes), by host id.

    ``toothed``: for every toothed host, one listed ``rail_teeth`` pair (optic or underbarrel part), or when none is listed the host's best pending pair
    of those slots. ``frame``: for every frame-changed host, one muzzle pair, listed first, else the best pending one. A host with no such pair is
    left out."""
    toothed = [p for h in sorted(toothed_hosts) if (p := _pick(directory, h, ("optic", "underbarrel"), "rail_teeth", tier_order))]
    frame = [p for h in sorted(frame_hosts) if (p := _pick(directory, h, ("muzzle",), None, tier_order))]
    return {"toothed": toothed, "frame": frame}
