"""Role / kind / archetype / hold_class / genre / family / flags / confidence (spec 3.4.2-3.4.5).

Pass 1 uses the name and catalog signals only. Pass 2 runs when ``classify`` is called again with ``measured=``
(the geometry summary of ``geometry.pass2_inputs``): ``long_m`` rules may fill a still-unknown archetype at
confidence <= 0.4, the ``min_length_m`` hold exceptions can fire, and the plausibility / forward-axis penalties
join the confidence. Without ``measured`` nothing length-dependent fires.

``kind`` is never None for a whole/emplaced record (spec 3.4.2 PATCH W7b). When the rules and the overrides leave it
null, ``_infer_kind`` fills it: ``kind_hints`` tokens, then (pass 2) the measured long axis, then ``melee``.
"""

from __future__ import annotations

import re
from fnmatch import fnmatchcase

from . import ARCHETYPE_KIND, NON_WEAPON_ROLES
from .overrides import effective_override
from .rules import attachment_rules, compile_regex, kind_hints, load_rules, match_conditions

_SEGMENT_SPLIT_RE = re.compile(r"[^A-Za-z0-9]+")
# camelCase boundaries: "RecurveBow" -> Recurve, Bow; "SMGun" -> SM, Gun; digits are separate runs
_CAMEL_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
_NUMERIC_SUFFIX_RE = re.compile(r"^\d+[a-z]?$")
_MAX_ALIAS_NGRAM = 3

# rules dict -> variant lookup; the dict is kept in the value so its id() can never be reused while cached
_ALIAS_CACHE: dict[int, tuple[dict, dict[str, str]]] = {}
_DEFAULT_RULES: dict | None = None


def _default_rules() -> dict:
    global _DEFAULT_RULES
    if _DEFAULT_RULES is None:
        _DEFAULT_RULES = load_rules()
    return _DEFAULT_RULES


def _alias_lookup(rules: dict) -> dict[str, str]:
    hit = _ALIAS_CACHE.get(id(rules))
    if hit is not None and hit[0] is rules:
        return hit[1]
    lookup: dict[str, str] = {}
    for target, variants in (rules.get("token_aliases") or {}).items():
        for v in variants:
            lookup[v] = target
    _ALIAS_CACHE[id(rules)] = (rules, lookup)
    return lookup


def tokenize_id(asset_id: str, rules: dict | None = None) -> list[str]:
    """Split on ``_`` and camelCase, lower-case, drop pure-digit tokens, apply ``rules['token_aliases']``.

    Aliases are looked up on the whole lower-cased ``_`` segment first (so ``SubMGun`` becomes ``smg`` before a
    camelCase split could shred it), then per camelCase token, then on 2-3 token joins (so ``Nail_Gun`` hits the
    ``nailgun`` alias).
    """
    lookup = _alias_lookup(rules if rules is not None else _default_rules())
    tokens: list[str] = []
    for segment in _SEGMENT_SPLIT_RE.split(asset_id):
        if not segment:
            continue
        whole = segment.lower()
        if whole in lookup:
            tokens.append(lookup[whole])
            continue
        for part in _CAMEL_RE.findall(segment):
            tok = part.lower()
            if tok.isdigit():
                continue
            tokens.append(lookup.get(tok, tok))
    # n-gram joins, longest first, left to right
    i = 0
    out: list[str] = []
    while i < len(tokens):
        for n in range(min(_MAX_ALIAS_NGRAM, len(tokens) - i), 1, -1):
            joined = "".join(tokens[i : i + n])
            if joined in lookup:
                out.append(lookup[joined])
                i += n
                break
        else:
            out.append(tokens[i])
            i += 1
    return out


def raw_tokens(asset_id: str) -> set[str]:
    """Lower-cased `_`/camelCase tokens of an id with NO alias step, digits dropped, plus the joins of 2-3 neighbours.

    The attachment table (docs/weapon_attachments.md 3.3) needs the words the alias table folds together (scope versus
    reflex, drum versus mag), and the joins let `Red_Dot` / `RedDot` reach `reddot` and `Fore_Grip` reach `foregrip`.
    """
    seq: list[str] = []
    for segment in _SEGMENT_SPLIT_RE.split(asset_id):
        for part in _CAMEL_RE.findall(segment):
            tok = part.lower()
            if not tok.isdigit():
                seq.append(tok)
    out = set(seq)
    for n in (2, 3):
        out.update("".join(seq[i : i + n]) for i in range(len(seq) - n + 1))
    return out


def classify_attachment(asset_id: str, pack_id: str, role: str, component: dict | None, rules: dict) -> dict | None:
    """``{slot, kind, rule}`` when a `part` record is a user-swappable accessory (docs/weapon_attachments.md 3.3), else None.

    Runs on the final classification (after the part rules and any override), reads only the id tokens, the pack and
    ``component.slot``, and never changes ``component``. A part matching a ``never`` row (vehicle accessories) is not an
    attachment whatever else it matches; a part no row matches stays None (rack and rail segments, bayonets, stocks).
    """
    if role != "part":
        return None
    table = attachment_rules(rules)
    ctx = {"id": asset_id, "tokens": raw_tokens(asset_id), "pack": pack_id,
           "component_slot": (component or {}).get("slot")}
    if any(match_conditions(row["match"], ctx) for row in table["never"]):
        return None
    for row in table["rows"]:
        if match_conditions(row["match"], ctx):
            return {"slot": row["set"]["slot"], "kind": row["set"]["kind"], "rule": row["name"]}
    return None


# spec 3.4.3
_GENRE_BY_SETTING = {
    "military": "modern", "modern_city": "modern", "post_apoc": "modern", "nature": "modern",
    "scifi_city": "scifi", "scifi_frontier": "scifi", "space": "scifi",
    "fantasy": "fantasy",
    "western": "western",
}


def genre_for_pack(setting: str | None, era: str | None) -> str | None:
    """Genre from the curated pack_settings row; None = undetermined (``generic`` or unknown)."""
    if setting in _GENRE_BY_SETTING:
        return _GENRE_BY_SETTING[setting]
    if setting == "horror":
        if era == "modern":
            return "modern"
        if era in ("near_future", "far_future"):
            return "scifi"
    return None


def family_of(asset_id: str, rules: dict) -> str:
    """Lower-cased id with trailing numbering and the ``family_strip_tokens`` removed, joined with ``_``."""
    strip = set(rules.get("family_strip_tokens") or ())
    segs = [s for s in asset_id.lower().split("_") if s]
    while segs and (segs[-1] in strip or _NUMERIC_SUFFIX_RE.match(segs[-1])):
        segs.pop()
    return "_".join(segs) if segs else asset_id.lower()


def asset_flags(asset: dict, pack_id: str, rules: dict, candidate_source: str) -> list[str]:
    """Flags knowable from the catalog alone (spec 3.4.5). Geometry-derived flags join in W2."""
    flags: set[str] = set()
    if candidate_source == "name_token":
        flags.add("token_candidate")
    for pattern, pack_flags in (rules.get("pack_flags") or {}).items():
        if fnmatchcase(pack_id, pattern):
            flags.update(pack_flags)
    for row in rules.get("id_flags") or ():
        if compile_regex(row["id_regex"]).search(asset["id"]):
            flags.add(row["flag"])
    files = asset.get("files") or {}
    if files.get("glb_node"):
        flags.add("shared_glb_node")
    if files.get("unity_prefab") and not files.get("glb") and not files.get("unity_mesh"):
        flags.add("prefab_only")
    return sorted(flags)


def derive_hold(
    role: str, kind: str | None, archetype: str, flags, gear_two_handed, rules: dict, long_m: float | None = None
) -> str:
    """hold_class from the archetype table + documented exceptions (spec 3.4.2).

    ``long_m`` is the measured length (pass 2); an exception with ``min_length_m`` needs it and is skipped without.
    """
    if role != "whole" or "mech_scale" in flags or archetype == "unknown":
        return "none"
    hold = rules["hold_by_archetype"][archetype]
    for ex in rules.get("hold_exceptions") or ():
        if "min_length_m" in ex and (long_m is None or long_m < ex["min_length_m"]):
            continue
        if "archetypes" in ex and archetype not in ex["archetypes"]:
            continue
        if "kind" in ex and kind != ex["kind"]:
            continue
        if "gear_two_handed" in ex and gear_two_handed != ex["gear_two_handed"]:
            continue
        return ex["hold"]
    return hold


_TWO_HAND_HOLDS = ("long_gun", "melee_two")
_ONE_HAND_HOLDS = ("one_hand", "melee_one", "melee_bat")


def _infer_kind(tokens: set[str], measured: dict | None, rules: dict) -> tuple[str, str, bool]:
    """``(kind, provenance, guessed)`` for a whole/emplaced record whose rules and overrides left ``kind`` null.

    Spec 3.4.2 PATCH W7b, in order: a ``kind_hints`` list that shares a token with the id (provenance ``rules``, not a
    guess); in pass 2 the measured long axis (``z`` -> ranged, else melee; provenance ``measured``); otherwise ``melee``
    (provenance ``rules``). The last two are guesses: the caller adds the review reason ``kind_guessed``.
    """
    for kind, hint_tokens in kind_hints(rules):
        if tokens & hint_tokens:
            return kind, "rules", False
    if measured is not None:
        return ("ranged" if measured.get("long_axis") == "z" else "melee"), "measured", True
    return "melee", "rules", True


def _sub_objects(role: str, rule_set: dict) -> tuple[dict | None, dict | None, dict | None]:
    component = {"slot": rule_set.get("component") or "misc", "fits": None} if role == "part" else None
    carrier = {"kind": rule_set["carrier"]} if role == "carrier" and rule_set.get("carrier") else None
    ammo = {"projectile": rule_set["ammo"]} if role == "ammo" and rule_set.get("ammo") else None
    return component, carrier, ammo


def classify(
    asset: dict,
    pack_id: str,
    rules: dict,
    overrides: dict | None,
    pack_setting: dict | None,
    *,
    candidate_source: str = "catalog",
    measured: dict | None = None,
) -> dict:
    """Classify one candidate asset.

    Returns role, kind, archetype, hold_class, component, carrier, ammo, genre, genre_source, family, flags,
    confidence, matched_rule, status (auto|reviewed|overridden), provenance and reasons.
    ``candidate_source`` is an addition to the spec signature: the name_token confidence cap needs it.
    ``measured`` (pass 2) is ``{'length_m', 'long_axis', 'forward_by_fallback', 'axes_unexpected'}`` from the geometry
    pass. The long axis is the one of the latest measurement (it can differ between two kinds only on a near tie of two
    axes, see ``directory._measure_record``).
    """
    asset_id = asset["id"]
    full_id = f"{pack_id}/{asset_id}"
    gear = asset.get("gear") or {}
    two_handed = gear.get("twoHanded")
    ctx = {
        "id": asset_id,
        "tokens": set(tokenize_id(asset_id, rules)),
        "pack": pack_id,
        "gear_two_handed": two_handed if isinstance(two_handed, bool) else None,
        "long_m": None,
        "asset_kind": asset.get("kind"),
    }
    long_m = measured["length_m"] if measured else None
    matches = [r for r in rules["rules"] if match_conditions(r["match"], ctx)]
    first = matches[0] if matches else None
    # pass 2: a still-unknown archetype may be filled by the first `long_m` rule that now matches (spec 3.4.2)
    filled = False
    if long_m is not None and (first is None or (first["set"]["role"] == "whole" and first["set"].get("archetype") in (None, "unknown"))):
        ctx2 = {**ctx, "long_m": long_m}
        fill = next((r for r in rules["rules"] if "long_m" in r["match"] and match_conditions(r["match"], ctx2)
                     and r["set"]["role"] == "whole" and r["set"].get("archetype") not in (None, "unknown")), None)
        if fill is not None:
            first, matches, filled = fill, [fill], True

    if first is not None:
        s = first["set"]
        role = s["role"]
        archetype = s.get("archetype") or "unknown"
        kind = s.get("kind") or ARCHETYPE_KIND.get(archetype)
        component, carrier, ammo = _sub_objects(role, s)
        base = float(first["confidence"])
    else:
        role, archetype, kind = "whole", "unknown", None
        component = carrier = ammo = None
        base = float(rules.get("unknown_confidence", 0.2))
    if role in NON_WEAPON_ROLES:
        kind = None

    flags = asset_flags(asset, pack_id, rules, candidate_source)
    prov = {"archetype": "rules", "kind": "rules", "hold_class": "rules"}
    if filled:
        prov["archetype"] = prov["kind"] = "measured"

    # genre: pack_settings, else the archetype table (spec 3.4.3)
    setting = (pack_setting or {}).get("setting")
    era = (pack_setting or {}).get("era")
    genre = genre_for_pack(setting, era)
    if genre is not None:
        genre_source, prov["genre"] = "pack", "pack_settings"
    else:
        by_arch = rules["genre_by_archetype"]
        genre = by_arch.get(archetype, by_arch["default"])
        genre_source, prov["genre"] = "archetype", "rules"

    # overrides (exact id > longest glob, merged per field in overrides.effective_override)
    eff = effective_override(full_id, overrides) if overrides else None
    set_ = (eff or {}).get("set") or {}
    hold_overridden = "hold_class" in set_
    if set_:
        if "role" in set_:
            role = set_["role"]
            prov["kind"] = "override"
        if "archetype" in set_:
            archetype = set_["archetype"]
            prov["archetype"] = "override"
            prov["kind"] = "override"
            kind = ARCHETYPE_KIND.get(archetype, kind)
        if "kind" in set_:
            kind = set_["kind"]
            prov["kind"] = "override"
        if "genre" in set_:
            genre, genre_source, prov["genre"] = set_["genre"], "override", "override"
        if role in NON_WEAPON_ROLES:
            kind = None
        elif kind is None and archetype in ARCHETYPE_KIND:
            kind = ARCHETYPE_KIND[archetype]
        component, carrier, ammo = _sub_objects(role, {
            "component": _slot_of(set_.get("component"), component),
            "carrier": _carrier_of(set_.get("carrier"), carrier),
            "ammo": _projectile_of(set_.get("ammo"), ammo),
        })
        if role == "part" and isinstance(set_.get("component"), dict):
            component = {"slot": set_["component"]["slot"], "fits": set_["component"].get("fits")}

    # W7b: kind is never null for whole/emplaced. This runs after the overrides on purpose: an override of kind (or of
    # archetype, which carries its own kind) has already filled it, so the guess and its reason never apply to it.
    guessed = False
    if role in ("whole", "emplaced") and kind is None:
        kind, prov["kind"], guessed = _infer_kind(ctx["tokens"], measured, rules)

    hold = (set_["hold_class"] if hold_overridden
            else derive_hold(role, kind, archetype, flags, ctx["gear_two_handed"], rules, long_m))
    if hold_overridden:
        prov["hold_class"] = "override"

    # confidence (spec 3.4.2), deterministic, 2 dp
    conf = base
    if role == "whole" and ctx["gear_two_handed"] is not None:
        if (ctx["gear_two_handed"] and hold in _TWO_HAND_HOLDS) or (not ctx["gear_two_handed"] and hold in _ONE_HAND_HOLDS):
            conf += 0.05
    if first is not None and first["set"].get("archetype") not in (None, "unknown"):
        for later in matches[1:]:
            la = later["set"].get("archetype")
            if la not in (None, "unknown") and la != first["set"]["archetype"]:
                conf -= 0.10
    if measured and role in ("whole", "emplaced"):
        lo_hi = (rules.get("plausible_length_m") or {}).get(archetype)
        if lo_hi and not (lo_hi[0] <= long_m <= lo_hi[1]):
            conf -= 0.25  # measured length outside the archetype's plausible range
        if measured.get("forward_by_fallback"):
            conf -= 0.15  # forward sign from the cross-section fallback or the bow rule
        if measured.get("axes_unexpected"):
            conf -= 0.15  # forward axis differs from the pack-genre convention
    if candidate_source == "name_token":
        conf = min(conf - 0.20, 0.60)
    if filled:
        conf = min(conf, 0.40)  # a guess from length alone never rates above 0.4
    conf = min(max(conf, 0.05), 0.99)

    status = "auto"
    if eff and (eff.get("set") or eff.get("confirm")):
        status = "overridden" if eff.get("set") else "reviewed"
        conf = 1.0
    cap = (eff or {}).get("confidence_cap")
    if cap is not None:
        # id-only review nudge (spec 4.5, W2e): applied last so it also lowers an override's 1.0; it never sets status
        conf = min(conf, cap)
    conf = round(conf, 2)

    reasons: list[str] = []
    if conf < 0.6:
        reasons.append("low_confidence")
    if role in ("whole", "emplaced") and archetype == "unknown":
        reasons.append("unknown_archetype")
    if guessed:
        reasons.append("kind_guessed")

    return {
        "role": role,
        "kind": kind,
        "archetype": archetype,
        "hold_class": hold,
        "component": component,
        "carrier": carrier,
        "ammo": ammo,
        "genre": genre,
        "genre_source": genre_source,
        "family": family_of(asset_id, rules),
        "flags": flags,
        "confidence": conf,
        "matched_rule": first["name"] if first is not None else None,
        "status": status,
        "provenance": prov,
        "reasons": reasons,
    }


def _slot_of(value, current):
    if isinstance(value, dict):
        return value.get("slot")
    if isinstance(value, str):
        return value
    return (current or {}).get("slot")


def _carrier_of(value, current):
    if isinstance(value, dict):
        return value.get("kind")
    if isinstance(value, str):
        return value
    return (current or {}).get("kind")


def _projectile_of(value, current):
    if isinstance(value, dict):
        return value.get("projectile")
    if isinstance(value, str):
        return value
    return (current or {}).get("projectile")
