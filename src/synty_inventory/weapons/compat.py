"""Attachment compatibility: which guns a part fits, tiered and explained (docs/weapon_attachments.md 5, slice W8c).

Everything here is a pure function of the directory records (and the categorical overrides): no files, no clock, no
randomness. ``apply_compat`` is the post-pass ``directory.py`` runs once every record is measured; it fills
``attachment.compatible_hosts`` / ``pending_hosts`` of every attachment part and adds the review reasons ``twin_multi``,
``compat_cross_pack`` (parts) and ``mount_missing`` (hosts). The relation is stored on the part only (5.3, INV-14).

Tiers, strongest first (D-7): ``override > twin > same_pack_fit > cross_pack_fit``.

G1 (docs/weapon_attach_geometry.md 3.1, 3.8). For the four geometry slots (``fit_types.FIT_SLOTS``: optic, muzzle, underbarrel, magazine) the
label-era test sequence below is replaced by ``fit_geometry.verdict`` (``pair_verdict``): POLICY runs first and is unchanged (the setting gate, a
disabled slot, ``mech_scale``, R-c ``suppressor_never``, an override), a ``twin`` is listed as before, and every other pair takes its tier from the
PACK RELATION alone (``same_pack_fit`` in one pack, ``cross_pack_fit`` across two); the verdict then decides the list: ``fit`` is listed (A8-1 first
routes a cross-pack pair of a ``cross_pack_unverified_slots`` slot to ``pending_hosts``), ``unverified`` and ``not_judged`` are pending, ``no_fit`` is
neither. The score is the tier base alone and ``signals`` is the geometry vocabulary of 3.1 step 5 (plus the tier mark of a twin or override). The
retired rules (``family_overlap``, ``attach_affinity``, the span and bore bonuses, R-a, R-b, ``fit_span_min``, the tokenless waiver) are not consulted for
these four slots; they stay in force, unchanged, for laser_light, sight_front and sight_rear. The verdict reads carried maps and no file: the host
features (``host_features``), the part's measures and the well sections of the pair pass are passed in (``compute``), so this module stays pure.

A2 (W8h). The SETTING GATE runs before any tier: a candidate that is not an ``override`` needs the part's pack and the host's pack
in one setting (``attachment_rules.attach_genre_by_pack``; a pack absent from the map is a setting of its own). It covers twin,
same_pack_fit, cross_pack_fit and the pending list, which are one candidate list (D-8); only a ``compatible.add`` crosses it
(INV-21). An ``optic`` entry also carries ``hides_slots: ["sight_rear"]`` when the placed optic covers the host's rear sight seat
(spec 4.3); the key is absent otherwise.

* ``override``: an ``compatible.add`` of the committed override file names the host (score 1.0).
* ``twin``: the host has a baked child of the part's slot whose SORTED AABB extents equal the part's within
  ``max(3 %, 0.8 mm)`` per axis (``is_twin``; score 0.95). A part twinning the children of several hosts is a twin of
  each of them and gets the review reason ``twin_multi``.
* ``same_pack_fit``: same pack, ``family_overlap`` AND ``affinity``, no veto (0.6 to 0.9). A3 (W8i): for the two sight slots
  ``family_overlap`` is not required (an iron sight is pack-generic: Military's name no gun); the span-less probe seat counts as
  neutral (``fit_span`` is None: no bonus, no veto), so the score is the tier base. Every other slot is unchanged.
  A4 (W8l, item 2): the slots that need no name overlap are the table ``attachment_rules.family_free_slots`` (shipped: the two
  sight slots, ``muzzle`` and ``underbarrel``: a silencer or a foregrip names no gun), read through ``_params``; nothing else changes (every
  veto, ``fit_span`` and ``fit_bore`` stay), and ``magazine`` / ``optic`` / ``laser_light`` keep the name test.
* ``cross_pack_fit``: another pack, ``affinity`` AND a measured fit, no veto (0.3 to 0.6, reason ``compat_cross_pack``).
* A7 (W8o, 13.8). (A7-1) ``cross_pack_fit`` joins ``DEFAULT_TIERS``; ``DEFAULT_PENDING_TIERS`` (override, twin, same_pack_fit) is the default cut of
  the export's ``pending_hosts`` and keeps the old meaning of the ``mount_missing`` loop. (A7-2) three precision rules on the ``cross_pack_fit`` tier
  only: R-a, a part on a slot of ``attach_compat.cross_pack_size_tol`` whose sorted extents deviate from the smallest-deviation baked child its seat
  replaces by more than the slot's tolerance is dropped (listed or pending: a pending pair has no seat, so it is not checked); R-b, a part named
  after a gun class (``GUN_CLASS_WORDS``) is vetoed on a host of the other group (``HANDGUN_CLASSES`` or not), a handgun-named part staying
  allowed on an ``smg``; R-c (A7; symmetric since A8-2, below), ``attachment_rules.suppressor_never`` (slot -> host archetypes) vetoes a ``suppressor`` part. (A7-4) a part with NO
  name tokens passes the ``same_pack_fit`` family test on a slot of ``tokenless_family_free_slots`` when its seat is a ``child_node`` and its
  deviation from the baked child is within the slot's ``cross_pack_size_tol``; every other test of the tier is unchanged.
* A8 (W8p, 13.9). (A8-1) ``attach_compat.cross_pack_unverified_slots`` (shipped: ``magazine``): a ``cross_pack_fit`` pair on such a slot is routed to
  ``pending_hosts`` as ``{host, tier}`` AFTER R-a, R-b, R-c and the A6 foot test, so a pair those drop is dropped, not parked; ``reasons`` keeps
  ``compat_cross_pack`` and ``mount_missing`` does not move. Every other tier and slot is untouched. (A8-2) R-c is symmetric: ``suppressor_never`` vetoes
  a ``suppressor`` part at every tier but ``override`` (``twin`` and ``same_pack_fit``, listed and pending, included).
* A6 (W8n, 13.7 A6-3), magazines only: the drum-by-shape affinity row and the ``fit_span_min`` lower bound. RETIRED by G1 (magazine is a geometry slot).

Signals: ``family_overlap`` (the names share a token once generic ones are gone), ``affinity`` (the slot x kind table
``attach_affinity`` lists the host's archetype), ``mount_available`` (the host's seat is not ``none``), ``fit_span`` (the
part's foot against the seat's span) and ``fit_bore`` (a muzzle device's mating diameter against a RING-measured bore).
Vetoes: a host slot disabled by override or by A3's ``attach_host_never`` / baked-sight rules (``slot_disabled``), an override removal, a ``mech_scale`` host for a part that is
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
* A1 (W8f). A twin entry names the ONE baked child it matches in ``replaces`` (``matched_child``: the closest sorted extents,
  the lower node name on a tie), so a game hides that child and seats the part on ``mounts.<slot>.seats[child]``. A carried twin
  keeps the single name its stored entry has, else (none or several) the copy of ``occupied_by``. Only ``twin`` entries
  narrow ``replaces``: an override entry for the same pair stays a copy of the slot.
* A1 (W8f). ``twin_forward`` runs first, over the whole record set: a baked child sits as the game's own authoring put it, so
  where a part has a yaw-free twin child its forward must be the host's, whatever the step-3 section prior guessed. It takes the
  evidence as the host mount's ``forward``, never touches ``review`` and gives up (changes nothing) on an override, a muzzle
  device, hosts that disagree, a child turned against the part, or a host forward that would lie along the part's own up.
"""

from __future__ import annotations

from fnmatch import fnmatchcase

from . import ATTACH_SLOTS, COMPAT_TIERS, TWIN_ABS_TOL_M, TWIN_REL_TOL
from .classify import _CAMEL_RE, _SEGMENT_SPLIT_RE
from .fit_geometry import verdict as fit_verdict
from .fit_types import FIT_SLOTS, Verdict
from .mounts import eligible, excluded_slots, mount_reasons
from .overrides import compatible_verdict, effective_override
from .rules import attachment_rules

# -- the thresholds of the spec (5.1), named constants -----------------------------------------------------

# twin: sorted AABB extents agree within max(3 %, 0.8 mm) per axis (TWIN_REL_TOL / TWIN_ABS_TOL_M come from the package: mounts.py reads them too)
FIT_SPAN_FITS = 1.0  # foot_length / span <= 1.0 adds the span bonus
FIT_SPAN_NEUTRAL_MAX = 1.5  # up to 1.5 neutral; above it a PROBE span vetoes, a child_foot span stays neutral-or-worse
FIT_BORE_REL_TOL = 0.35  # |mate_d - bore_d| <= 0.35 * bore_d adds the bore bonus, otherwise it subtracts the penalty
SCORE_BANDS = {"same_pack_fit": (0.6, 0.9), "cross_pack_fit": (0.3, 0.6)}  # spec 5.1 table
DEFAULT_TIERS = ("override", "twin", "same_pack_fit", "cross_pack_fit")  # what the default export lists in compatible_hosts (A7-1; D-11 superseded)
DEFAULT_PENDING_TIERS = ("override", "twin", "same_pack_fit")  # the default cut of pending_hosts (A7-1, D-13) and what `mount_missing` counts
GUN_CLASS_WORDS = frozenset({"pistol", "revolver", "smg", "rifle", "shotgun", "sniper", "lmg"})  # A7-2 R-b: the archetype words a part's name can carry
HANDGUN_CLASSES = frozenset({"pistol", "revolver"})  # A7-2 R-b: the handgun group; every other archetype is "long"
COMPAT_REASONS = ("compat_cross_pack", "mount_missing", "twin_multi")  # the reasons this pass owns
HIDES_MARGIN_M = 0.010  # an optic hides the rear sight when its placed extent, widened by 10 mm each way, contains the seat (spec 4.3)

# parameters used when the rules carry no attach_compat table (the shipped YAML always does)
_DEFAULTS = {
    "tier_score": {"override": 1.0, "twin": 0.95}, "base": {"same_pack_fit": 0.7, "cross_pack_fit": 0.4},
    "fit_span_bonus": 0.1, "fit_bore_bonus": 0.1, "fit_bore_penalty": 0.1, "generic_tokens": [],
    "cross_pack_size_tol": {},  # A7-2 R-a: slot -> max per-axis deviation from the baked child; empty = no slot is checked (never a geometry slot, G1 3.8)
    "cross_pack_unverified_slots": (),  # A8-1: the slots whose cross_pack_fit pairs are routed to pending_hosts; empty = nothing moves
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


def matched_child(extents, children: dict) -> str | None:
    """The child of ``children`` (``{node: {"extents": sorted, ...}}``) the sorted ``extents`` twin, or None (A1).

    When several children match, the closest sorted extents win (smallest largest per-axis gap) and the lower node name
    breaks a tie, so the choice is deterministic and the same for the twin seat and for the forward correction.
    """
    if extents is None:
        return None
    gaps = [(max(abs(a - b) for a, b in zip(sorted(extents), row["extents"])), name)
            for name, row in children.items() if is_twin(extents, row["extents"])]
    return min(gaps)[1] if gaps else None


def child_deviation(part_extents, mount: dict | None, children: dict | None) -> float | None:
    """A7-2: how far a part's sorted extents are from the baked child its seat replaces, or None when no child has recorded extents.

    Per child named in ``mount["occupied_by"]`` that is a key of ``children`` (``{node: {"extents": sorted, ...}}``) the deviation is
    ``max over the three sorted extents of |part_i / child_i - 1|`` (a child with a zero extent is skipped); the SMALLEST over those children is returned.

    Each per-axis value is ROUNDED TO 2 DECIMALS before the max: every figure of docs 13.8 (the labelled deviations, the tolerances 0.35 / 0.45 and the
    live counts 121 optic removals and +15 waivers) was measured that way, and the live directory has two optic pairs at 0.3508 and 0.3521 that the
    spec counts as 0.35 (kept). R-a (``deviation > tol``) and the A7-4 waiver (``deviation <= tol``) both read this rounded value.
    """
    if part_extents is None or not mount or not children:
        return None
    best = None
    for node in mount.get("occupied_by") or ():
        row = children.get(node)
        if not row or len(row["extents"]) != 3 or any(c == 0 for c in row["extents"]):
            continue
        dev = max(round(abs(p / c - 1.0), 2) for p, c in zip(sorted(part_extents), row["extents"]))
        best = dev if best is None else min(best, dev)
    return best


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
    out = {k: got.get(k, v) if not isinstance(v, dict) else {**v, **(got.get(k) or {})} for k, v in _DEFAULTS.items()}
    out["family_free_slots"] = frozenset(tables.get("family_free_slots") or ())  # A4: the slots whose same_pack_fit needs no family_overlap
    out["tokenless_family_free_slots"] = frozenset(tables.get("tokenless_family_free_slots") or ())  # A7-4: the slots a name-less part passes the family test on, size-gated
    out["cross_pack_unverified_slots"] = frozenset(out["cross_pack_unverified_slots"] or ())  # A8-1: a set, whatever the YAML list (or the default) was
    out["suppressor_never"] = {slot: frozenset(archs or ()) for slot, archs in (tables.get("suppressor_never") or {}).items()}  # A8-2 R-c: slot -> host archetypes
    out["fit_rules"] = tables.get("fit_geometry")  # G1: the block ``fit_geometry.verdict`` reads (None: no geometry can be judged, every pair is not_judged)
    return out


def setting_of(genre_by_pack: dict | None, pack: str):
    """The setting of a pack for the gate (spec 5.1): its word in ``attach_genre_by_pack``, else a setting of its own."""
    word = (genre_by_pack or {}).get(pack)
    return ("setting", word) if word else ("pack", pack)


def _host_view(rec: dict, generic, genre_by_pack: dict | None = None, tables: dict | None = None, children: dict | None = None,
               feats: dict | None = None) -> dict:
    mounts = (rec.get("geometry") or {}).get("mounts") or {}
    # A6 (W8n, 13.7 A6-1): a host with no measured mounts (a prefab-only preset) has no `slot_disabled` seat to veto its pairs, so the slots its name
    # refuses (attach_host_never and the host classes) are carried here and read as disabled. A measured host already has them as its mounts.
    refused = frozenset(excluded_slots(rec["asset_id"], tables)) if tables and not mounts else frozenset()
    return {"id": rec["id"], "pack": rec["pack"], "archetype": rec["archetype"], "flags": set(rec["flags"]),
            "mounts": mounts, "tokens": name_tokens(rec["asset_id"], generic),
            "setting": setting_of(genre_by_pack, rec["pack"]), "refused": refused,
            "children": children or {},  # A7-2: {slot: {baked child node: {"extents": sorted, ...}}} of this build's measurement (empty: none recorded)
            "feats": feats}  # G1: ``fit_geometry.host_features`` of the host ({s0, slots, located}); None = never measured (every geometry pair is not_judged)


def forward_extent(rec: dict) -> tuple[float, float] | None:
    """The part's extent along its own anchor ``forward`` from the anchor point: ``(low, high)`` metres, or None.

    Taken from the record's mesh bounds (the frame the anchor is measured in), so a part whose body sits off its foot is
    placed right: the footprint alone carries lengths, not where they lie against the anchor point.
    """
    att, bounds = rec.get("attachment") or {}, ((rec.get("geometry") or {}).get("bounds"))
    anchor = att.get("anchor")
    if not anchor or not bounds:
        return None
    lo, hi, f, p = bounds["min"], bounds["max"], anchor["forward"], anchor["point"]
    ts = [sum((c[i] - p[i]) * f[i] for i in range(3))
          for c in ((x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2]))]
    return round(min(ts), 4), round(max(ts), 4)


def hides_slots(extent, seat: dict | None, rear: dict | None) -> list[str]:
    """``["sight_rear"]`` when an optic with forward ``extent`` seated on ``seat`` covers the host's ``rear`` sight seat, else [].

    Both mounts have to be measured. After placing the optic (spec 3.1) its extent along the host forward is the seat's
    coordinate plus the part's own extent; the rear seat counts as covered inside that, widened by ``HIDES_MARGIN_M`` each way.
    """
    if extent is None or not seat or not rear or seat.get("point") is None or rear.get("point") is None:
        return []
    fwd = seat["forward"]
    origin = sum(a * b for a, b in zip(seat["point"], fwd))
    at = sum(a * b for a, b in zip(rear["point"], fwd))
    return ["sight_rear"] if origin + extent[0] - HIDES_MARGIN_M <= at <= origin + extent[1] + HIDES_MARGIN_M else []


def pair_verdict(part: dict, host: dict, fit_rules: dict | None, seat: str | None = None) -> Verdict:
    """``V(P, H, X)`` of a part on a host in a geometry slot (spec 3.1 step 4), from the carried maps alone; pure.

    ``part`` is a ``compute`` part view (its geometry keys: ``anchor_measured``, ``foot_length_m``, ``foot_width_m``, ``mate_d_m``,
    ``device_inner_d`` and ``sections``, the well sections of the directory's pair pass as ``{host id: {seat key: [L, W] | None}}``), ``host`` a
    ``_host_view`` (``feats`` and ``mounts``), ``fit_rules`` the ``fit_geometry`` block. ``seat`` is the child a ``twin`` pair sits on (A1, 3.7 step 2):
    where the slot lists several seats the pair is judged against that seat's reference, else against the mount's own.

    A host that was never measured (no features), and a magazine on a host with no seat to place the part at (``mount`` none: no authored magazine,
    or a located one, errata E2.4), are ``not_judged``. A magazine whose pair section the pass did not measure reads like an unmeasured anchor:
    ``unverified``, never ``fit``.
    """
    slot = part["slot"]
    feats = ((host.get("feats") or {}).get("slots") or {}).get(slot)
    mount = host["mounts"].get(slot)
    if feats is None or (slot == "magazine" and (mount is None or mount["source"] == "none")):
        return Verdict("not_judged", ())
    if fit_rules is None:
        raise ValueError("host features without attachment_rules.fit_geometry: the geometry verdict has no tolerances")
    measure = {"anchor_measured": bool(part.get("anchor_measured")), "foot_length_m": part.get("foot_length_m"),
               "foot_width_m": part.get("foot_width_m"), "mate_d_m": part.get("mate_d_m"), "device_inner_d": part.get("device_inner_d")}
    pair_seat = None
    if seat is not None:
        if slot == "magazine" and seat in (feats.get("well_refs") or {}):
            pair_seat = {"well_ref": feats["well_refs"][seat]}
        elif slot in ("optic", "underbarrel") and seat in (feats.get("seat_refs") or {}):
            pair_seat = {"ref": feats["seat_refs"][seat]}
    if slot == "magazine":
        sections = (part.get("sections") or {}).get(host["id"]) or {}
        key = seat if pair_seat is not None else ""
        if key in sections:
            measure["entry_section"] = None if sections[key] is None else tuple(sections[key])
        else:
            measure["anchor_measured"] = False  # the pair pass measured no section (no part file now): unverified, never fit
    return fit_verdict(slot, feats, measure, pair_seat, fit_rules)


def _geometry_candidate(part: dict, host: dict, *, verdict: str | None, twin: bool, params: dict, twin_replaces: list[str] | None,
                        mount: dict | None, available: bool, disabled: bool) -> dict | None:
    """``candidate`` for a geometry slot (G1 3.1). Policy first, then the tier by pack relation, then the verdict; the retired rules are not read."""
    slot = part["slot"]
    veto = disabled or ("mech_scale" in host["flags"] and "mech_scale" not in part["flags"])
    if part["kind"] == "suppressor" and host["archetype"] in params["suppressor_never"].get(slot, ()):
        veto = True  # A8-2 R-c, symmetric: no suppressor on these hosts at any tier; only `add` (below) outranks it
    if verdict == "add":
        tier = "override"
    elif veto:
        return None
    elif twin:
        tier = "twin"
    elif host["pack"] == part["pack"]:
        tier = "same_pack_fit"  # the tier is the pack relation and nothing else (3.1 step 4): no name, family or kind decides it
    else:
        tier = "cross_pack_fit"
    seat = twin_replaces[0] if tier == "twin" and twin_replaces and len(twin_replaces) == 1 else None
    v = None if tier == "override" else pair_verdict(part, host, params["fit_rules"], seat)  # an override does not consult geometry (3.1 step 2)
    parked = False
    if tier in ("same_pack_fit", "cross_pack_fit"):
        if v.value == "no_fit":
            return None  # the mating feature is measured and the part does not match, or the host has none: neither listed nor pending
        # A8-1, AFTER the tier: a cross-pack pair of an unverified slot never lists, whatever its verdict. `parked` counts the fits it held back (AC140).
        parked = tier == "cross_pack_fit" and slot in params["cross_pack_unverified_slots"]
        listed = v.value == "fit" and available and not parked
    else:
        listed = available  # twin and override are listed as before; with no seat they are pending
    if tier == "override":
        signals = {"override"}
    elif tier == "twin":
        signals = {"twin"} | (set(v.signals) if v.value == "fit" else set())  # the verdict of a twin is calibration; only a fit names its evidence
    else:
        signals = set(v.signals)
    entry = {"host": host["id"], "tier": tier, "listed": listed}
    if listed:
        replaces = list(twin_replaces) if tier == "twin" and twin_replaces else list(mount["occupied_by"])
        entry.update(score=score_of(tier, None, None, params), signals=sorted(signals), replaces=replaces)  # the tier base alone: no span or bore term (3.1 step 5)
        if slot == "optic":  # a twin entry seats on the child it twins, as the game does (spec 4.3)
            seat_frame = (mount.get("seats") or {}).get(replaces[0]) if tier == "twin" and len(replaces) == 1 else None
            hidden = hides_slots(part.get("extent_m"), seat_frame or mount, host["mounts"].get("sight_rear"))
            if hidden:
                entry["hides_slots"] = hidden
    elif tier in ("same_pack_fit", "cross_pack_fit") and signals:
        entry["signals"] = sorted(signals)  # the pending form carries what was measured (4.4): `rail_flat`, `drum`, a parked fit's evidence
    if parked and v.value == "fit":
        entry["fit_parked"] = True  # transient: ``compute`` counts it and removes it
    return entry


def candidate(part: dict, host: dict, *, verdict: str | None, twin: bool, affinity: dict, params: dict,
              twin_replaces: list[str] | None = None) -> dict | None:
    """The compatibility entry of ``part`` on ``host`` or None; ``entry["listed"]`` says compatible (True) or pending (False).

    ``part`` is ``{id, pack, slot, kind, flags, tokens, foot_length_m, mate_d_m, setting, extent_m?}``, ``host`` a ``_host_view``. A geometry slot
    (``FIT_SLOTS``) takes ``_geometry_candidate`` (G1); the other slots take the label-era sequence below, unchanged.
    ``extents`` (A7) is the part's sorted footprint extents and the host's ``children`` the recorded baked children per slot; a part or host without
    them is simply not size-checked.
    ``verdict`` is the override verdict for this pair (``add`` / ``remove`` / None), ``twin`` whether the host has a twin child.
    ``twin_replaces`` (A1) is the one child a ``twin`` entry replaces; without it a twin entry copies the slot's ``occupied_by``.
    """
    if verdict == "remove":
        return None
    if verdict != "add" and part["setting"] != host["setting"]:
        return None  # A2 setting gate: before any tier, so a cross-setting twin is no candidate and does not count toward twin_multi
    slot = part["slot"]
    mount = host["mounts"].get(slot)
    available = mount is not None and mount["source"] != "none"
    disabled = (mount is not None and mount["source"] == "none" and mount.get("reason") == "slot_disabled") or slot in host.get("refused", ())
    if slot in FIT_SLOTS:
        return _geometry_candidate(part, host, verdict=verdict, twin=twin, params=params, twin_replaces=twin_replaces,
                                   mount=mount, available=available, disabled=disabled)
    deviation = child_deviation(part.get("extents"), mount, (host.get("children") or {}).get(slot)) if available else None  # A7: None without a recorded child
    size_tol = params["cross_pack_size_tol"].get(slot)  # A7: None = this slot is not size-checked
    span = fit_span(part["foot_length_m"], mount) if available else None
    bore = fit_bore(part["mate_d_m"], mount) if available else None
    same_pack = host["pack"] == part["pack"]
    family = bool(part["tokens"] & host["tokens"])
    affine = host["archetype"] in affinity_archetypes(affinity, slot, part["kind"])
    veto = disabled or span == "veto" or ("mech_scale" in host["flags"] and "mech_scale" not in part["flags"])
    if part["kind"] == "suppressor" and host["archetype"] in params["suppressor_never"].get(slot, ()):
        veto = True  # A8-2 R-c, symmetric: no suppressor on these hosts at any tier (twin and same_pack_fit, listed and pending, included); only `add` (below) outranks it

    if verdict == "add":
        tier = "override"
    elif veto:
        return None
    elif twin:
        tier = "twin"
    elif same_pack and (family or slot in params["family_free_slots"] or (  # A3 / A4: a sight, a muzzle device and a foregrip name no gun
            not part["tokens"] and slot in params["tokenless_family_free_slots"] and available and mount["source"] == "child_node"
            and deviation is not None and size_tol is not None and deviation <= size_tol)) and affine:  # A7-4: a name-less part, seat and size decide
        tier = "same_pack_fit"
    elif not same_pack and affine and (
            not available or (bore != "bad" and (span in ("fits", "neutral") or bore == "good"))):
        tier = "cross_pack_fit"  # no seat to measure against: pending on affinity alone (judgment call in the docstring)
    else:
        return None
    if tier == "cross_pack_fit":  # A7-2: three precision rules, this tier only (twin, override and same_pack_fit carry name or authored evidence)
        named = part["tokens"] & GUN_CLASS_WORDS
        if any((t in HANDGUN_CLASSES) != (host["archetype"] in HANDGUN_CLASSES)
               and not (t in HANDGUN_CLASSES and host["archetype"] == "smg") for t in named):
            return None  # R-b: a handgun part on a long gun or the reverse (a pistol part on an smg stays: machine pistols)
        if available and size_tol is not None and deviation is not None and deviation > size_tol:
            return None  # R-a: the wrong size for the baked child it replaces; a pending pair has no seat and is not checked
    if tier == "cross_pack_fit" and slot in params["cross_pack_unverified_slots"]:
        # A8-1: after R-a, R-b, R-c and the A6 foot test (a pair those drop is dropped, not parked). Routed on purpose, not by faking a missing seat:
        # the entry is the pending form {host, tier} (no score, signals or replaces) whatever the seat; the part still carries `compat_cross_pack`.
        return {"host": host["id"], "tier": tier, "listed": False}

    signals = {tier} if tier in ("override", "twin") else set()
    for name, holds in (("family_overlap", family), ("affinity", affine), ("mount_available", available),
                        ("fit_span", span == "fits"), ("fit_bore", bore == "good"), ("bore_mismatch", bore == "bad")):
        if holds:
            signals.add(name)
    entry = {"host": host["id"], "tier": tier, "listed": available}
    if available:
        replaces = list(twin_replaces) if tier == "twin" and twin_replaces else list(mount["occupied_by"])
        entry.update(score=score_of(tier, span, bore, params), signals=sorted(signals), replaces=replaces)
        if slot == "optic":  # a twin entry seats on the child it twins, as the game does (spec 4.3)
            seat = (mount.get("seats") or {}).get(replaces[0]) if tier == "twin" and len(replaces) == 1 else None
            hidden = hides_slots(part.get("extent_m"), seat or mount, host["mounts"].get("sight_rear"))
            if hidden:
                entry["hides_slots"] = hidden
    return entry


def compute(records: list[dict], rules: dict, overrides: dict | None = None, *, child_extents: dict | None = None,
            prev_twins: dict | None = None, host_feats: dict | None = None, part_fit: dict | None = None) -> dict:
    """``{"parts": {id: {compatible, pending, reasons}}, "host_slots": {id: {slot}}, "problems": [str], "parked_fit": {slot: n}}`` (pure).

    ``child_extents`` is ``{host id: {slot: {node: {"extents", "axes", "seat"}}}}`` of the hosts measured in this build; a host
    not in it falls back to ``prev_twins`` (``{(part id, host id): the replaces its stored twin entry had}``, the twin
    relations stored earlier). ``problems`` lists override patterns that name no eligible host (``child_not_found``), never
    silently dropped.

    G1: ``host_feats`` is ``{host id: fit_geometry.host_features(...)}`` and ``part_fit`` ``{part id: {"device_inner_d": float | None, "sections":
    {host id: {seat key: [L, W] | None}}}}`` (the pair pass of ``directory.py``; the seat key is "" for the mount's own seat, else a child node). A host
    or part without them is not measured: its geometry pairs are ``not_judged`` / ``unverified``. ``parked_fit`` counts, per slot, the cross-pack
    pairs the geometry judged ``fit`` and A8-1 routed to ``pending_hosts`` (AC140).
    """
    tables = attachment_rules(rules)
    params = _params(tables)
    affinity = tables.get("attach_affinity") or {}
    child_vocab = {t for toks in (tables.get("child_tokens") or {}).values() for t in toks}
    generic = frozenset(params["generic_tokens"]) | child_vocab
    genre_by_pack = tables.get("attach_genre_by_pack") or {}
    child_extents = child_extents or {}
    prev_twins = prev_twins or {}
    host_feats, part_fit = host_feats or {}, part_fit or {}
    hosts = [_host_view(r, generic, genre_by_pack, tables, child_extents.get(r["id"]), host_feats.get(r["id"]))
             for r in sorted(records, key=lambda r: r["id"]) if eligible(r["role"], r["kind"], r["hold_class"])]
    host_ids = [h["id"] for h in hosts]
    parts: dict[str, dict] = {}
    host_slots: dict[str, set[str]] = {}
    problems: list[str] = []
    parked_fit: dict[str, int] = {}
    for rec in sorted(records, key=lambda r: r["id"]):
        att = rec.get("attachment")
        if not att or att["slot"] not in ATTACH_SLOTS:
            continue
        part = {"id": rec["id"], "pack": rec["pack"], "slot": att["slot"], "kind": att["kind"], "flags": set(rec["flags"]),
                "tokens": name_tokens(rec["asset_id"], generic), "setting": setting_of(genre_by_pack, rec["pack"]),
                "foot_length_m": (att["footprint"] or {}).get("foot_length_m"),
                "mate_d_m": (att["footprint"] or {}).get("mate_d_m"),
                "extent_m": forward_extent(rec) if att["slot"] == "optic" else None,
                # G1: the part side of the geometry verdict (the anchor and footprint of the record, the mesh measures of the pair pass)
                "anchor_measured": att["anchor"] is not None, "foot_width_m": (att["footprint"] or {}).get("foot_width_m"),
                "device_inner_d": (part_fit.get(rec["id"]) or {}).get("device_inner_d"),
                "sections": (part_fit.get(rec["id"]) or {}).get("sections") or {}}
        extents = sorted_extents(att["footprint"])
        part["extents"] = extents  # A7-2: the size evidence against a host's baked child
        eff = effective_override(rec["id"], overrides) if overrides else None
        sources = (eff or {}).get("compat_sources") or []
        for src in sources:
            for kind in ("add", "remove"):
                problems += [f"{rec['id']}: child_not_found: compatible.{kind} {pat} (no eligible host)"
                             for pat in src[kind] if not any(fnmatchcase(h, pat) for h in host_ids)]
        listed, pending = [], []
        for host in hosts:
            if host["id"] in child_extents:
                matched = matched_child(extents, child_extents[host["id"]].get(part["slot"]) or {})
                twin, twin_replaces = matched is not None, ([matched] if matched is not None else None)
            else:  # a carried host has no evidence: the stored entry decides, and its single child name is kept
                twin = (rec["id"], host["id"]) in prev_twins
                stored = prev_twins.get((rec["id"], host["id"])) or []
                twin_replaces = list(stored) if len(stored) == 1 else None
            verdict = compatible_verdict(sources, rec["id"], host["id"]) if sources else None
            got = candidate(part, host, verdict=verdict, twin=twin, affinity=affinity, params=params,
                            twin_replaces=twin_replaces)
            if got is None:
                continue
            if got.pop("fit_parked", False):
                parked_fit[part["slot"]] = parked_fit.get(part["slot"], 0) + 1
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
            if e["tier"] in DEFAULT_PENDING_TIERS:  # A7-1: the old default set, so the `mount_missing` reasons do not move
                host_slots.setdefault(e["host"], set()).add(part["slot"])
    return {"parts": parts, "host_slots": host_slots, "problems": sorted(problems), "parked_fit": dict(sorted(parked_fit.items()))}


def _axis_of(vec) -> int | None:
    """The axis index of a unit axis vector (``[0, 0, -1]`` -> 2), or None when it is not one."""
    i = max(range(3), key=lambda k: abs(vec[k]))
    return i if abs(abs(vec[i]) - 1.0) < 1e-3 else None


def _part_axes(anchor: dict, footprint: dict) -> list[float] | None:
    """The part's AABB extents per axis x, y, z from its footprint (anchor frames are axis-aligned): ``length_m`` along
    ``forward``, ``height_m`` along ``up``, ``width_m`` along the third axis. None when the frame is not axis-aligned."""
    f, u = _axis_of(anchor["forward"]), _axis_of(anchor["up"])
    if f is None or u is None or f == u:
        return None
    out = [0.0, 0.0, 0.0]
    out[f], out[u], out[3 - f - u] = footprint["length_m"], footprint["height_m"], footprint["width_m"]
    return out


def _axes_equal(a, b) -> bool:
    """Per-axis (unsorted) extents agree within the twin tolerance: no yaw between the two meshes."""
    return all(abs(x - y) <= max(TWIN_REL_TOL * max(x, y), TWIN_ABS_TOL_M) for x, y in zip(a, b))


def twin_forward(records: list[dict], child_extents: dict) -> list[str]:
    """Correct the anchor forward of every part that has twin evidence (spec 3.4 step 3a, A1); returns the corrected ids.

    Steps 1 to 3 of the anchor measure a part alone, and their forward SIGN (and, for a near-round body, the forward AXIS) is
    a prior. A baked child that the part twins sits in its host as the game's own authoring put it, so its host's
    forward IS the gun-forward direction for that part: the evidence outranks the prior. For a part with a non-null anchor,
    a slot other than ``muzzle`` (its frame uses ``up`` as the bore, and every live muzzle twin already agrees) and no
    explicit ``forward`` override (the human wins), each host of ``child_extents`` whose mount for the slot is not ``none``
    is asked: does the part twin one of its children (``matched_child``) with the same PER-AXIS extents (a yawed child proves
    nothing about the part's forward)? If so the host mount's ``forward`` is the answer. Hosts that disagree: the part keeps
    its measurement. A forward along the part's own ``up`` would make an invalid frame and is never applied.

    On a change the anchor takes the forward with ``forward_source = "twin"`` and ``symmetric = False``; an axis change
    also swaps ``length_m`` / ``width_m`` and ``foot_length_m`` / ``foot_width_m`` (exact: the frames are axis-aligned). Point,
    up, height and mate diameter never change, and neither does ``review``: a correction never raises confidence. Running it
    again finds the forward already right and does nothing. Only ``child_extents`` is evidence: a host known only from a
    stored relation (``prev_twins``) proves nothing here.
    """
    hosts = {r["id"]: r for r in records}
    done: list[str] = []
    for rec in sorted(records, key=lambda r: r["id"]):
        att = rec.get("attachment")
        if not att or att["slot"] not in ATTACH_SLOTS or att["slot"] == "muzzle":
            continue
        anchor, foot = att["anchor"], att["footprint"]
        if anchor is None or foot is None or anchor["forward_source"] == "override":
            continue
        axes, extents = _part_axes(anchor, foot), sorted_extents(foot)
        if axes is None:
            continue
        wanted = set()
        for host_id in sorted(child_extents):
            mount = (((hosts.get(host_id) or {}).get("geometry") or {}).get("mounts") or {}).get(att["slot"])
            if not mount or mount["source"] == "none" or mount.get("forward") is None:
                continue
            rows = child_extents[host_id].get(att["slot"]) or {}
            name = matched_child(extents, rows)
            if name is not None and _axes_equal(axes, rows[name]["axes"]):
                wanted.add(tuple(mount["forward"]))
        if len(wanted) != 1:
            continue  # no evidence, or hosts that disagree
        want = list(next(iter(wanted)))
        new_axis, old_axis = _axis_of(want), _axis_of(anchor["forward"])
        if want == anchor["forward"] or new_axis is None or new_axis == _axis_of(anchor["up"]):
            continue
        anchor["forward"], anchor["forward_source"], anchor["symmetric"] = want, "twin", False
        if new_axis != old_axis:
            foot["length_m"], foot["width_m"] = foot["width_m"], foot["length_m"]
            foot["foot_length_m"], foot["foot_width_m"] = foot["foot_width_m"], foot["foot_length_m"]
        done.append(rec["id"])
    return done


def apply_compat(records: list[dict], rules: dict, overrides: dict | None = None, *, child_extents: dict | None = None,
                 host_feats: dict | None = None, part_fit: dict | None = None, stats: dict | None = None) -> list[str]:
    """Fill the compatibility fields of ``records`` in place; returns the warnings (override patterns that match no host).

    G1: ``host_feats`` and ``part_fit`` are the carried maps of ``compute`` (the geometry verdict reads them, no file); ``stats``, when given, is filled
    with ``parked_fit`` (``{slot: cross-pack pairs judged fit and routed to pending_hosts by A8-1}``).

    Runs over the WHOLE record set, carried-over records of a partial build included: it first forgets what an earlier run
    stored (the lists and the three reasons) and recomputes, so the result does not depend on how the directory got here.
    A1: the twin forward correction (``twin_forward``) runs first, so ``fit_span`` reads the corrected ``foot_length_m``.
    """
    twin_forward(records, child_extents or {})
    prev_twins = {
        (r["id"], e["host"]): e.get("replaces", []) for r in records if r.get("attachment")
        for e in r["attachment"]["compatible_hosts"] + r["attachment"]["pending_hosts"] if e["tier"] == "twin"}
    for rec in records:
        rec["review"]["reasons"] = [x for x in rec["review"]["reasons"] if x not in COMPAT_REASONS]
        if rec.get("attachment"):
            rec["attachment"]["compatible_hosts"], rec["attachment"]["pending_hosts"] = [], []
    got = compute(records, rules, overrides, child_extents=child_extents, prev_twins=prev_twins, host_feats=host_feats, part_fit=part_fit)
    if stats is not None:
        stats["parked_fit"] = got["parked_fit"]
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


def export_compatible(entries: list[dict], min_tier: str = "cross_pack_fit") -> list[dict]:
    """``compatible_hosts`` entries at or above ``min_tier`` (the order is kept)."""
    return [e for e in entries if tier_rank(e["tier"]) <= tier_rank(min_tier)]


def export_pending(entries: list[dict], min_tier: str = "same_pack_fit") -> list[str]:
    """``pending_hosts`` of the export: ids only, filtered by the SAME tier rule as ``compatible_hosts`` (a cross-pack
    candidate on a mountless host must not reach a game's ``fits`` list), sorted by ``(tier rank, host)``."""
    kept = [e for e in entries if tier_rank(e["tier"]) <= tier_rank(min_tier)]
    return [e["host"] for e in sorted(kept, key=lambda e: (tier_rank(e["tier"]), e["host"]))]
