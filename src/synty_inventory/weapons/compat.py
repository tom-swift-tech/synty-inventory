"""Attachment compatibility: which guns a part fits, tiered and explained (docs/weapon_attachments.md 5, slice W8c).

Everything here is a pure function of the directory records (and the categorical overrides): no files, no clock, no
randomness. ``apply_compat`` is the post-pass ``directory.py`` runs once every record is measured; it fills
``attachment.compatible_hosts`` / ``pending_hosts`` of every attachment part and adds the review reasons ``twin_multi``,
``compat_cross_pack`` (parts) and ``mount_missing`` (hosts). The relation is stored on the part only (5.3, INV-14).

Tiers, strongest first (D-7): ``override > twin > same_pack_fit > cross_pack_fit``.

* ``override``: an ``compatible.add`` of the committed override file names the host (score 1.0).
* ``twin``: the host has a baked child of the part's slot whose SORTED AABB extents equal the part's within
  ``max(3 %, 0.8 mm)`` per axis (``is_twin``; score 0.95). A part twinning the children of several hosts is a twin of
  each of them and gets the review reason ``twin_multi``.
* ``same_pack_fit``: same pack, ``family_overlap`` AND ``affinity``, no veto (0.6 to 0.9).
* ``cross_pack_fit``: another pack, ``affinity`` AND a measured fit, no veto (0.3 to 0.6, reason ``compat_cross_pack``).

Signals: ``family_overlap`` (the names share a token once generic ones are gone), ``affinity`` (the slot x kind table
``attach_affinity`` lists the host's archetype), ``mount_available`` (the host's seat is not ``none``), ``fit_span`` (the
part's foot against the seat's span) and ``fit_bore`` (a muzzle device's mating diameter against a RING-measured bore).
Vetoes: a host slot disabled by override (``slot_disabled``), an override removal, a ``mech_scale`` host for a part that is
not, and a foot more than 1.5 times a PROBE span. A ``child_foot`` span is a lower bound, so it can never veto.

A candidate whose host seat is ``none`` is not listed in ``compatible_hosts`` but in ``pending_hosts`` (D-8): a game overlay
may supply its own mount. An empty ``compatible_hosts`` means the part fits nothing.

Judgment calls, stated once:

* ``cross_pack_fit`` needs "a measured fit": when the host's seat exists, the foot must measure at most 1.5 times the span
  (or the bore must be a good ring match) and no bore may be a mismatch. When the seat is ``none`` there is nothing to
  measure against and the candidate goes to ``pending_hosts`` on affinity alone (AC75 needs the cross-pack pending case).
* ``mount_missing`` counts only the default-export tiers (override, twin, same_pack_fit): cross-pack candidates exist for
  nearly every pair and would flag every mountless host.
* An override ``add`` beats a disabled host slot (the user said it fits; the seat is ``none`` so it lands in
  ``pending_hosts``); an inferred candidate does not.
* Twin evidence is the host's ``child_extents`` from this build's measurement. A host carried over from a partial build has
  none, so a carried part keeps the twin relation it already stored for a carried host (``prev_twins``).
"""

from __future__ import annotations

from fnmatch import fnmatchcase

from . import ATTACH_SLOTS, COMPAT_TIERS
from .classify import _CAMEL_RE, _SEGMENT_SPLIT_RE
from .mounts import eligible, mount_reasons
from .overrides import compatible_verdict, effective_override
from .rules import attachment_rules

# -- the thresholds of the spec (5.1), named constants -----------------------------------------------------

TWIN_REL_TOL = 0.03  # twin: sorted AABB extents agree within max(3 %, 0.8 mm) per axis
TWIN_ABS_TOL_M = 0.0008
FIT_SPAN_FITS = 1.0  # foot_length / span <= 1.0 adds the span bonus
FIT_SPAN_NEUTRAL_MAX = 1.5  # up to 1.5 neutral; above it a PROBE span vetoes, a child_foot span stays neutral-or-worse
FIT_BORE_REL_TOL = 0.35  # |mate_d - bore_d| <= 0.35 * bore_d adds the bore bonus, otherwise it subtracts the penalty
SCORE_BANDS = {"same_pack_fit": (0.6, 0.9), "cross_pack_fit": (0.3, 0.6)}  # spec 5.1 table
DEFAULT_TIERS = ("override", "twin", "same_pack_fit")  # what the default export lists (D-11)
COMPAT_REASONS = ("compat_cross_pack", "mount_missing", "twin_multi")  # the reasons this pass owns

# parameters used when the rules carry no attach_compat table (the shipped YAML always does)
_DEFAULTS = {
    "tier_score": {"override": 1.0, "twin": 0.95}, "base": {"same_pack_fit": 0.7, "cross_pack_fit": 0.4},
    "fit_span_bonus": 0.1, "fit_bore_bonus": 0.1, "fit_bore_penalty": 0.1, "generic_tokens": [],
}


def tier_rank(tier: str) -> int:
    return COMPAT_TIERS.index(tier) + 1


# -- pure signals -------------------------------------------------------------------------------------------


def sorted_extents(footprint: dict | None) -> list[float] | None:
    """The sorted AABB extents of a part from its footprint (anchor axes are axis-aligned), or None without a footprint."""
    if not footprint:
        return None
    return sorted((footprint["length_m"], footprint["width_m"], footprint["height_m"]))


def is_twin(a, b) -> bool:
    """Spec 5.1 / AC71: the sorted extents agree within ``max(3 % of the larger, 0.8 mm)`` on every axis."""
    xs, ys = sorted(a), sorted(b)
    return len(xs) == len(ys) == 3 and all(abs(x - y) <= max(TWIN_REL_TOL * max(x, y), TWIN_ABS_TOL_M) for x, y in zip(xs, ys))


def fit_span(foot_length_m, mount: dict | None) -> str | None:
    """How the part's foot sits in the seat's span: ``fits`` (<= 1.0), ``neutral`` (<= 1.5), ``over`` (a child_foot span, a
    lower bound, that the foot exceeds by more than 1.5: not a veto), ``veto`` (the same excess against a probe span), or
    None when either length is unknown."""
    span = (mount or {}).get("span_m")
    if foot_length_m is None or not span:
        return None
    ratio = foot_length_m / span
    if ratio <= FIT_SPAN_FITS:
        return "fits"
    if ratio <= FIT_SPAN_NEUTRAL_MAX:
        return "neutral"
    return "veto" if mount.get("span_source") == "probe" else "over"


def fit_bore(mate_d_m, mount: dict | None) -> str | None:
    """``good`` / ``bad`` for a muzzle device against a ring-measured bore; None (ignored) for a ``face_extent`` bore,
    whose extent is polluted by slides and shrouds (spec 4.4), and when either diameter is unknown."""
    if mount is None or mate_d_m is None or mount.get("bore_source") != "ring" or not mount.get("bore_d_m"):
        return None
    bore = mount["bore_d_m"]
    return "good" if abs(mate_d_m - bore) <= FIT_BORE_REL_TOL * bore else "bad"


def name_tokens(asset_id: str, generic) -> frozenset[str]:
    """Lower-case name tokens of an asset id, no joins, no numbers, minus the generic ones (``family_overlap``)."""
    out = set()
    for segment in _SEGMENT_SPLIT_RE.split(asset_id):
        for part in _CAMEL_RE.findall(segment):
            tok = part.lower()
            if not tok.isdigit() and tok not in generic:
                out.add(tok)
    return frozenset(out)


def affinity_archetypes(table: dict, slot: str, kind: str) -> frozenset[str]:
    """The host archetypes the ``attach_affinity`` table allows for a slot x kind (its ``default`` row for other kinds)."""
    rows = (table or {}).get(slot) or {}
    return frozenset(rows.get(kind, rows.get("default", ())))


def score_of(tier: str, span: str | None, bore: str | None, params: dict) -> float:
    """Tier score: fixed for override / twin, otherwise the tier's base plus the fit signals, clamped to its band."""
    if tier in ("override", "twin"):
        return round(float(params["tier_score"][tier]), 2)
    score = params["base"][tier]
    score += params["fit_span_bonus"] if span == "fits" else 0.0
    score += params["fit_bore_bonus"] if bore == "good" else 0.0
    score -= params["fit_bore_penalty"] if bore == "bad" else 0.0
    lo, hi = SCORE_BANDS[tier]
    return round(min(max(score, lo), hi), 2)


# -- candidates ---------------------------------------------------------------------------------------------


def _params(tables: dict) -> dict:
    got = tables.get("attach_compat") or {}
    return {k: got.get(k, v) if not isinstance(v, dict) else {**v, **(got.get(k) or {})} for k, v in _DEFAULTS.items()}


def _host_view(rec: dict, generic) -> dict:
    mounts = (rec.get("geometry") or {}).get("mounts") or {}
    return {"id": rec["id"], "pack": rec["pack"], "archetype": rec["archetype"], "flags": set(rec["flags"]),
            "mounts": mounts, "tokens": name_tokens(rec["asset_id"], generic)}


def candidate(part: dict, host: dict, *, verdict: str | None, twin: bool, affinity: dict, params: dict) -> dict | None:
    """The compatibility entry of ``part`` on ``host`` or None; ``entry["listed"]`` says compatible (True) or pending (False).

    ``part`` is ``{id, pack, slot, kind, flags, tokens, foot_length_m, mate_d_m}``, ``host`` a ``_host_view``.
    ``verdict`` is the override verdict for this pair (``add`` / ``remove`` / None), ``twin`` whether the host has a twin child.
    """
    if verdict == "remove":
        return None
    slot = part["slot"]
    mount = host["mounts"].get(slot)
    available = mount is not None and mount["source"] != "none"
    disabled = mount is not None and mount["source"] == "none" and mount.get("reason") == "slot_disabled"
    span = fit_span(part["foot_length_m"], mount) if available else None
    bore = fit_bore(part["mate_d_m"], mount) if available else None
    same_pack = host["pack"] == part["pack"]
    family = bool(part["tokens"] & host["tokens"])
    affine = host["archetype"] in affinity_archetypes(affinity, slot, part["kind"])
    veto = disabled or span == "veto" or ("mech_scale" in host["flags"] and "mech_scale" not in part["flags"])

    if verdict == "add":
        tier = "override"
    elif veto:
        return None
    elif twin:
        tier = "twin"
    elif same_pack and family and affine:
        tier = "same_pack_fit"
    elif not same_pack and affine and (
            not available or (bore != "bad" and (span in ("fits", "neutral") or bore == "good"))):
        tier = "cross_pack_fit"  # no seat to measure against: pending on affinity alone (judgment call in the docstring)
    else:
        return None

    signals = {tier} if tier in ("override", "twin") else set()
    for name, holds in (("family_overlap", family), ("affinity", affine), ("mount_available", available),
                        ("fit_span", span == "fits"), ("fit_bore", bore == "good"), ("bore_mismatch", bore == "bad")):
        if holds:
            signals.add(name)
    entry = {"host": host["id"], "tier": tier, "listed": available}
    if available:
        entry.update(score=score_of(tier, span, bore, params), signals=sorted(signals),
                     replaces=list(mount["occupied_by"]))
    return entry


def compute(records: list[dict], rules: dict, overrides: dict | None = None, *, child_extents: dict | None = None,
            prev_twins: frozenset = frozenset()) -> dict:
    """``{"parts": {id: {compatible, pending, reasons}}, "host_slots": {id: {slot}}, "problems": [str]}`` (pure).

    ``child_extents`` is ``{host id: {slot: {node: sorted extents}}}`` of the hosts measured in this build; a host not in it
    falls back to ``prev_twins`` (``{(part id, host id)}`` twin relations stored earlier). ``problems`` lists override
    patterns that name no eligible host (``child_not_found``), never silently dropped.
    """
    tables = attachment_rules(rules)
    params = _params(tables)
    affinity = tables.get("attach_affinity") or {}
    child_vocab = {t for toks in (tables.get("child_tokens") or {}).values() for t in toks}
    generic = frozenset(params["generic_tokens"]) | child_vocab
    child_extents = child_extents or {}
    hosts = [_host_view(r, generic) for r in sorted(records, key=lambda r: r["id"])
             if eligible(r["role"], r["kind"], r["hold_class"])]
    host_ids = [h["id"] for h in hosts]
    parts: dict[str, dict] = {}
    host_slots: dict[str, set[str]] = {}
    problems: list[str] = []
    for rec in sorted(records, key=lambda r: r["id"]):
        att = rec.get("attachment")
        if not att or att["slot"] not in ATTACH_SLOTS:
            continue
        part = {"id": rec["id"], "pack": rec["pack"], "slot": att["slot"], "kind": att["kind"], "flags": set(rec["flags"]),
                "tokens": name_tokens(rec["asset_id"], generic),
                "foot_length_m": (att["footprint"] or {}).get("foot_length_m"),
                "mate_d_m": (att["footprint"] or {}).get("mate_d_m")}
        extents = sorted_extents(att["footprint"])
        eff = effective_override(rec["id"], overrides) if overrides else None
        sources = (eff or {}).get("compat_sources") or []
        for src in sources:
            for kind in ("add", "remove"):
                problems += [f"{rec['id']}: child_not_found: compatible.{kind} {pat} (no eligible host)"
                             for pat in src[kind] if not any(fnmatchcase(h, pat) for h in host_ids)]
        listed, pending = [], []
        for host in hosts:
            if host["id"] in child_extents:
                twin = extents is not None and any(
                    is_twin(extents, e) for e in (child_extents[host["id"]].get(part["slot"]) or {}).values())
            else:
                twin = (rec["id"], host["id"]) in prev_twins
            verdict = compatible_verdict(sources, rec["id"], host["id"]) if sources else None
            got = candidate(part, host, verdict=verdict, twin=twin, affinity=affinity, params=params)
            if got is None:
                continue
            if got.pop("listed"):
                listed.append(got)
            else:
                pending.append(got)
        listed.sort(key=lambda e: (tier_rank(e["tier"]), -e["score"], e["host"]))
        pending.sort(key=lambda e: (tier_rank(e["tier"]), e["host"]))
        tiers = [e["tier"] for e in listed + pending]
        reasons = set()
        if tiers.count("twin") > 1:
            reasons.add("twin_multi")
        if "cross_pack_fit" in tiers:
            reasons.add("compat_cross_pack")
        parts[rec["id"]] = {"compatible": listed, "pending": pending, "reasons": reasons}
        for e in pending:
            if e["tier"] in DEFAULT_TIERS:
                host_slots.setdefault(e["host"], set()).add(part["slot"])
    return {"parts": parts, "host_slots": host_slots, "problems": sorted(problems)}


def apply_compat(records: list[dict], rules: dict, overrides: dict | None = None, *, child_extents: dict | None = None) -> list[str]:
    """Fill the compatibility fields of ``records`` in place; returns the warnings (override patterns that match no host).

    Runs over the WHOLE record set, carried-over records of a partial build included: it first forgets what an earlier run
    stored (the lists and the three reasons) and recomputes, so the result does not depend on how the directory got here.
    """
    prev_twins = frozenset(
        (r["id"], e["host"]) for r in records if r.get("attachment")
        for e in r["attachment"]["compatible_hosts"] + r["attachment"]["pending_hosts"] if e["tier"] == "twin")
    for rec in records:
        rec["review"]["reasons"] = [x for x in rec["review"]["reasons"] if x not in COMPAT_REASONS]
        if rec.get("attachment"):
            rec["attachment"]["compatible_hosts"], rec["attachment"]["pending_hosts"] = [], []
    got = compute(records, rules, overrides, child_extents=child_extents, prev_twins=prev_twins)
    for rec in records:
        reasons = set()
        if rec["id"] in got["parts"]:
            fields = got["parts"][rec["id"]]
            rec["attachment"]["compatible_hosts"], rec["attachment"]["pending_hosts"] = fields["compatible"], fields["pending"]
            reasons |= fields["reasons"]
        mounts = (rec.get("geometry") or {}).get("mounts")
        if mounts and rec["id"] in got["host_slots"]:
            reasons |= mount_reasons(mounts, got["host_slots"][rec["id"]]) & {"mount_missing"}
        if reasons:
            rec["review"]["reasons"] = sorted(set(rec["review"]["reasons"]) | reasons)
    return got["problems"]


# -- the export view (W8d wires these behind --attachments; D-11, C-23) -------------------------------------


def export_compatible(entries: list[dict], min_tier: str = "same_pack_fit") -> list[dict]:
    """``compatible_hosts`` entries at or above ``min_tier`` (the order is kept)."""
    return [e for e in entries if tier_rank(e["tier"]) <= tier_rank(min_tier)]


def export_pending(entries: list[dict], min_tier: str = "same_pack_fit") -> list[str]:
    """``pending_hosts`` of the export: ids only, filtered by the SAME tier rule as ``compatible_hosts`` (a cross-pack
    candidate on a mountless host must not reach a game's ``fits`` list), sorted by ``(tier rank, host)``."""
    kept = [e for e in entries if tier_rank(e["tier"]) <= tier_rank(min_tier)]
    return [e["host"] for e in sorted(kept, key=lambda e: (tier_rank(e["tier"]), e["host"]))]
