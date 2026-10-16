"""Role / kind / archetype / hold_class / genre / family / flags / confidence (spec 3.4.2-3.4.5).

Pass 1 only (name + catalog signals). Pass 2 (measurement fallback, ``long_m`` rules, plausibility penalty) lands
with geometry in W2; the hooks it needs (``long_m`` in the match context, ``min_length_m`` hold exceptions) are
parsed here and simply never fire while no length is known.
"""

from __future__ import annotations

import re
from fnmatch import fnmatchcase

from . import ARCHETYPE_KIND, NON_WEAPON_ROLES
from .overrides import effective_override
from .rules import compile_regex, load_rules, match_conditions

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


def derive_hold(role: str, kind: str | None, archetype: str, flags, gear_two_handed, rules: dict) -> str:
    """hold_class from the archetype table + documented exceptions (spec 3.4.2)."""
    if role != "whole" or "mech_scale" in flags or archetype == "unknown":
        return "none"
    hold = rules["hold_by_archetype"][archetype]
    for ex in rules.get("hold_exceptions") or ():
        if "min_length_m" in ex:
            continue  # needs a measured length: pass 2 (W2)
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
) -> dict:
    """Classify one candidate asset.

    Returns role, kind, archetype, hold_class, component, carrier, ammo, genre, genre_source, family, flags,
    confidence, matched_rule, status (auto|reviewed|overridden), provenance and reasons.
    ``candidate_source`` is an addition to the spec signature: the name_token confidence cap needs it.
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
    matches = [r for r in rules["rules"] if match_conditions(r["match"], ctx)]
    first = matches[0] if matches else None

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

    hold = set_["hold_class"] if hold_overridden else derive_hold(role, kind, archetype, flags, ctx["gear_two_handed"], rules)
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
    if candidate_source == "name_token":
        conf = min(conf - 0.20, 0.60)
    conf = min(max(conf, 0.05), 0.99)

    status = "auto"
    if eff and (eff.get("set") or eff.get("confirm")):
        status = "overridden" if eff.get("set") else "reviewed"
        conf = 1.0
    conf = round(conf, 2)

    reasons: list[str] = []
    if conf < 0.6:
        reasons.append("low_confidence")
    if role in ("whole", "emplaced") and archetype == "unknown":
        reasons.append("unknown_archetype")

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
