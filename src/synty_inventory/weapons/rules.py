"""Load and validate ``data/weapon_rules.yaml``; the shared match engine; shadowed-rule analysis.

The rules file is data, not code (spec 3.4.1, 4.4): ordered first-match-wins tables. A schema violation is a
``SchemaError`` (exit 6) raised at load time, never at match time (spec section 7).
"""

from __future__ import annotations

import re
from fnmatch import fnmatchcase
from functools import lru_cache
from pathlib import Path

import yaml

from . import (
    AMMO_FAMILIES,
    AMMO_PROJECTILES,
    ARCHETYPE_KIND,
    ARCHETYPES,
    ATTACH_KINDS,
    ATTACH_SLOTS,
    CARRIER_KINDS,
    COMPONENT_SLOTS,
    EMPLACED_ARCHETYPES,
    EXCLUDE_REASONS,
    FLAGS,
    GENRES,
    HOLD_CLASSES,
    KINDS,
    ROLES,
    SEAT_SETBACK_MAX_M,
    SEAT_SHIFT_MAX_M,
    SchemaError,
    WEIGHT_CLASSES,
    digest,
)

# match keys valid in a classification rule / a candidate pattern (spec 3.4.2)
RULE_MATCH_KEYS = (
    "tokens_any", "tokens_all", "tokens_none", "id_regex", "packs_any", "packs_none", "gear_two_handed", "long_m",
)
CANDIDATE_MATCH_KEYS = (
    "tokens_any", "tokens_all", "tokens_none", "id_regex", "id_contains_any", "packs_any", "packs_none",
    "asset_kind_any",
)
RULE_SET_KEYS = ("role", "kind", "archetype", "component", "carrier", "ammo")
# attachment_rules rows (docs/weapon_attachments.md 3.3): the same match engine, raw (un-aliased) tokens, plus the part's
# existing component slot. The spec calls the negative list `not_tokens`; the engine's key is `tokens_none`, kept here.
ATTACH_MATCH_KEYS = ("tokens_any", "tokens_all", "tokens_none", "component_slot")
ATTACH_NEVER_KEYS = ("tokens_any", "packs_any")
ATTACH_TOP_KEYS = ("never", "rows", "child_tokens", "child_never", "attach_affinity", "attach_compat",
                   "attach_genre_by_pack", "sight_probe",  # A2: the setting-gate map and the sight seat probe parameters
                   "attach_host_never", "baked_sights",  # A3 (W8i): hosts that get no seat for a slot, and the baked-sight child tokens
                   "anchor", "family_free_slots",  # A4 (W8l): the foot ladder and free-end forward, the name-generic slots
                   "contact",  # A5 (W8m): settle to contact (spec 5.4)
                   "attach_host_class", "attach_class_never", "muzzle_seat")  # A6 (W8n): host classes (13.7 A6-1), the silencer seat (A6-2)
BAKED_SIGHT_KEYS = ("tokens", "not_tokens", "rear_tokens")  # attachment_rules.baked_sights (docs/weapon_attachments.md 4.6 item 7): required
# A3 addendum 3 (W8j, item 8): optional name-token lists (empty allowed, an absent list switches that part of the rule off), the carry-handle
# height fraction and the fused front post parameters (name -> (type, minimum, maximum); metres unless a count or a fraction)
BAKED_OPTIC_LISTS = ("glass_tokens", "body_tokens", "handle_tokens", "handle_not_tokens")
BAKED_SIGHT_OPTIONAL = BAKED_OPTIC_LISTS + ("handle_min_height_frac", "fused_post")
FUSED_POST_PARAMS = {
    "bin_m": (float, 0.001, 0.05), "half_bins": (int, 1, 100), "rise_m": (float, 0.0005, 0.1),
    "width_min_m": (float, 0.001, 0.2), "width_max_m": (float, 0.001, 0.5), "min_pos": (float, 0.0, 1.0),
}
# A row may carry a `reason` (a review reason) instead of a `set`: it classifies no slot (iron sight with no decided side, spec 3.3)
ATTACH_ROW_REASONS = ("sight_side_unsure",)
# sight_probe parameters (docs/weapon_attachments.md 4.6): name -> (type, minimum, maximum); metres unless a count
SIGHT_PROBE_PARAMS = {
    "bin_m": (float, 0.001, 0.05), "receiver_tol_m": (float, 0.0, 0.05), "rail_tol_m": (float, 0.0, 0.2),
    "rear_inset_m": (float, 0.0, 0.1), "front_inset_m": (float, 0.0, 0.1), "min_receiver_bins": (int, 1, 100),
    "min_separation_m": (float, 0.0, 1.0), "side_min_m": (float, 0.0, 0.1), "side_frac": (float, 0.0, 1.0),
    "ridge_tol_m": (float, 0.0, 0.1), "seat_ray_m": (float, 0.0, 0.05), "seat_flat_tol_m": (float, 0.0, 0.1),  # live-calibrated (4.6 item 6)
}
SIGHT_PROBE_RECEIVER_TOL_BY_HOST_MAX_M = 0.03  # A6 (W8n): the largest per-host receiver tolerance (the optional `receiver_tol_by_host` map)
# A4 (W8l) anchor parameters (docs/weapon_attachments.md 3.4 steps 1a and 3b): name -> (minimum, maximum), every one required; metres unless a ratio.
ANCHOR_PARAMS = {"lip_min_m": (0.0, 0.05), "lip_max_m": (0.0, 0.05), "lip_growth": (1.0, 100.0)}
ANCHOR_FREE_END_KEYS = ("min_displacement_m", "kinds")
ANCHOR_MAX_RUNGS = 8  # foot_depths_m is a short ladder, not a profile
# A5 (W8m) contact parameters (docs/weapon_attachments.md 5.4): name -> (minimum, maximum) in metres, every one required. The clamp's upper bound is
# the schema's bound for the entry key `seat_shift_m` (SEAT_SHIFT_MAX_M), so a table can never write a value the export check refuses.
CONTACT_SLOTS = ("optic", "underbarrel")  # the only slots the rule can name: the key lives on these parts' entries
CONTACT_PARAMS = {"slab_m": (0.0005, 0.05), "pitch_m": (0.0005, 0.05), "dead_m": (0.0, 0.05), "clamp_m": (0.0005, SEAT_SHIFT_MAX_M), "reach_m": (0.01, 5.0),
                  "cap_m": (0.0005, SEAT_SHIFT_MAX_M)}  # A6 (W8n): cap_m, an entry settled further than this is not listed (cap_m <= clamp_m)
# A6 (W8n) silencer seat parameters (docs/weapon_attachments.md 13.7 A6-2): name -> (type, minimum, maximum), every one required. `window_m` is the stretch behind
# the tip the shroud walk covers; the key it makes (`seat_setback_m`, bound SEAT_SETBACK_MAX_M) can never be longer than the window plus 10 mm.
MUZZLE_SEAT_PARAMS = {
    "cover": (float, 0.01, 1.0), "device_cover_m": (float, 0.0, 0.05), "device_reach_m": (float, 0.0, 0.3), "max_frac": (float, 0.01, 1.0),
    "dead_m": (float, 0.0, 0.05), "window_m": (float, 0.01, 0.18), "bin_m": (float, 0.0005, 0.02), "ref_ratio": (float, 1.0, 10.0),
    "run_min_bins": (int, 1, 50), "device_max_m": (float, 0.0, 0.2), "sample_pitch_m": (float, 0.0005, 0.02), "range_m": (float, 0.05, 1.0),
    "radius_cap_m": (float, 0.005, 0.2),
}
# W8c compatibility tables (docs/weapon_attachments.md 5.1). The score bands per tier are the spec's; the tunable base and
# bonus values must keep every reachable score inside the band of their tier (checked at load).
COMPAT_SCORE_BANDS = {"same_pack_fit": (0.6, 0.9), "cross_pack_fit": (0.3, 0.6)}
COMPAT_FIXED_TIERS = ("override", "twin")
COMPAT_NUMBER_KEYS = ("fit_span_bonus", "fit_bore_bonus", "fit_bore_penalty")
# A6 (W8n) magazine parameters (13.7 A6-3), optional in the table (compat.py has the defaults): name -> (minimum, maximum), metres or a ratio
COMPAT_MAGAZINE_KEYS = {"drum_min_m": (0.01, 1.0), "fit_span_min": (0.0, 1.0)}
REQUIRED_TOP = (
    "version", "token_aliases", "candidates", "rules", "hold_by_archetype", "genre_by_archetype",
    "plausible_length_m", "axes_expected", "grip_proportion", "size_class_cuts_m", "weight_by_archetype",
    "tier_base", "ammo_by_archetype", "pack_flags", "family_strip_tokens",
)
# keys beyond spec 4.4 (judgment calls, reported): see weapon_rules.yaml for each.
OPTIONAL_TOP = (
    "hold_exceptions", "id_flags", "tier_tokens", "unknown_confidence", "ammo_token_overrides",
    "head_lead_tokens", "icon_albedo_from_material",  # W7: both default to empty (spec 4.4)
    "kind_hints",  # W7b: defaults to empty (spec 4.4)
    "attachment_rules",  # W8a: absent = no part is an attachment (docs/weapon_attachments.md 3.3)
)
# the kinds a hint list can name, in the order the lists are consulted when an id matches more than one (never a
# conflict at load time: the loader rejects a token that sits in two lists). `shield` has an archetype of its own.
HINT_KINDS = ("ranged", "melee", "thrown")
_ALBEDO_KEYS = ("name", "packs_any", "id_regex")

_AXIS_RE = re.compile(r"^[+-][xyz]$")


def default_rules_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "weapon_rules.yaml"


@lru_cache(maxsize=256)
def compile_regex(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


def match_conditions(match: dict, ctx: dict) -> bool:
    """True when every key present in ``match`` holds for ``ctx`` (keys are ANDed).

    ctx: id, tokens (set), pack, gear_two_handed (bool|None), long_m (float|None), asset_kind (str|None),
    component_slot (str|None, attachment rows only).
    A ``long_m`` condition never matches in pass 1 (``ctx['long_m'] is None``).
    """
    tokens = ctx["tokens"]
    if "component_slot" in match:  # attachment rows only: a str or a list of the part's component.slot values
        want = match["component_slot"]
        if ctx.get("component_slot") not in ([want] if isinstance(want, str) else want):
            return False
    if "tokens_any" in match and not any(t in tokens for t in match["tokens_any"]):
        return False
    if "tokens_all" in match and not all(t in tokens for t in match["tokens_all"]):
        return False
    if "tokens_none" in match and any(t in tokens for t in match["tokens_none"]):
        return False
    if "id_regex" in match and not compile_regex(match["id_regex"]).search(ctx["id"]):
        return False
    if "id_contains_any" in match:
        low = ctx["id"].lower()
        if not any(s.lower() in low for s in match["id_contains_any"]):
            return False
    if "packs_any" in match and not any(fnmatchcase(ctx["pack"], p) for p in match["packs_any"]):
        return False
    if "packs_none" in match and any(fnmatchcase(ctx["pack"], p) for p in match["packs_none"]):
        return False
    if "asset_kind_any" in match and ctx.get("asset_kind") not in match["asset_kind_any"]:
        return False
    if match.get("gear_two_handed") is not None and ctx.get("gear_two_handed") != match["gear_two_handed"]:
        return False
    if "long_m" in match:
        length = ctx.get("long_m")
        lo, hi = match["long_m"]
        if length is None or not (lo <= length <= hi):
            return False
    return True


# -- shadowing ---------------------------------------------------------------------------------------


def _required_tokens(m: dict) -> set[str]:
    req = set(m.get("tokens_all", ()))
    any_ = m.get("tokens_any")
    if any_ is not None and len(any_) == 1:
        req.add(any_[0])
    return req


def subsumes(a: dict, b: dict) -> bool:
    """True when every id matched by ``b`` is also matched by ``a`` (so ``b`` after ``a`` is shadowed).

    Conservative: it only claims subsumption when it can prove it from the declared conditions.
    """
    b_req = _required_tokens(b)
    if "component_slot" in a:
        a_c = {a["component_slot"]} if isinstance(a["component_slot"], str) else set(a["component_slot"])
        b_c = b.get("component_slot")
        if b_c is None or not ({b_c} if isinstance(b_c, str) else set(b_c)) <= a_c:
            return False
    if "tokens_any" in a:
        a_any = set(a["tokens_any"])
        b_any = b.get("tokens_any")
        if not ((b_any is not None and set(b_any) <= a_any) or (b_req & a_any)):
            return False
    if "tokens_all" in a and not set(a["tokens_all"]) <= b_req:
        return False
    if "tokens_none" in a and not set(a["tokens_none"]) <= set(b.get("tokens_none", ())):
        return False
    if "id_regex" in a and a["id_regex"] != b.get("id_regex"):
        return False
    if "id_contains_any" in a:
        b_c = b.get("id_contains_any")
        if b_c is None or not {s.lower() for s in b_c} <= {s.lower() for s in a["id_contains_any"]}:
            return False
    if "packs_any" in a:
        b_p = b.get("packs_any")
        if b_p is None or not set(b_p) <= set(a["packs_any"]):
            return False
    if "packs_none" in a and not set(a["packs_none"]) <= set(b.get("packs_none", ())):
        return False
    if "asset_kind_any" in a:
        b_k = b.get("asset_kind_any")
        if b_k is None or not set(b_k) <= set(a["asset_kind_any"]):
            return False
    if a.get("gear_two_handed") is not None and a["gear_two_handed"] != b.get("gear_two_handed"):
        return False
    if "long_m" in a:
        b_l = b.get("long_m")
        if b_l is None or not (a["long_m"][0] <= b_l[0] and b_l[1] <= a["long_m"][1]):
            return False
    return True


def shadowed_rules(rules: dict) -> list[dict]:
    """Static shadow analysis over the three ordered tables. One row per shadowed entry."""
    rows: list[dict] = []
    cand = rules.get("candidates") or {}
    tables = (
        ("rules", rules.get("rules") or []),
        ("candidates.include", cand.get("include") or []),
        ("candidates.exclude", cand.get("exclude") or []),
        ("attachment_rules.rows", (rules.get("attachment_rules") or {}).get("rows") or []),
    )
    for table, entries in tables:
        for i, later in enumerate(entries):
            for earlier in entries[:i]:
                if subsumes(earlier["match"], later["match"]):
                    rows.append({"table": table, "rule": later["name"], "shadowed_by": earlier["name"]})
                    break
    return rows


# -- validation ---------------------------------------------------------------------------------------


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_str_list(v, where: str, errors: list[str], *, lower: bool = False) -> None:
    if not isinstance(v, list) or not v or not all(isinstance(s, str) and s for s in v):
        errors.append(f"{where}: must be a non-empty list of non-empty strings")
    elif lower and any(s != s.lower() for s in v):
        errors.append(f"{where}: tokens must be lower-case")


def _check_match(match, where: str, allowed: tuple[str, ...], errors: list[str]) -> None:
    if not isinstance(match, dict) or not match:
        errors.append(f"{where}: match must be a non-empty mapping")
        return
    for key, val in match.items():
        if key not in allowed:
            errors.append(f"{where}.{key}: unknown match key (allowed: {', '.join(allowed)})")
            continue
        if key in ("tokens_any", "tokens_all", "tokens_none"):
            _check_str_list(val, f"{where}.{key}", errors, lower=True)
        elif key in ("packs_any", "packs_none", "id_contains_any", "asset_kind_any"):
            _check_str_list(val, f"{where}.{key}", errors)
        elif key == "id_regex":
            try:
                compile_regex(val)
            except (re.error, TypeError) as exc:
                errors.append(f"{where}.id_regex: invalid regex ({exc})")
        elif key == "gear_two_handed":
            if val is not None and not isinstance(val, bool):
                errors.append(f"{where}.gear_two_handed: must be true, false or null")
        elif key == "long_m":
            if not (isinstance(val, list) and len(val) == 2 and all(_is_num(x) for x in val) and val[0] <= val[1]):
                errors.append(f"{where}.long_m: must be [lo, hi] numbers")


def _check_table(rows, where: str, errors: list[str]) -> list[dict]:
    if not isinstance(rows, list) or not rows:
        errors.append(f"{where}: must be a non-empty list")
        return []
    good = []
    seen: set[str] = set()
    for i, row in enumerate(rows):
        here = f"{where}[{i}]"
        if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"]:
            errors.append(f"{here}: needs a non-empty name")
            continue
        if row["name"] in seen:
            errors.append(f"{here}: duplicate name {row['name']!r}")
        seen.add(row["name"])
        good.append(row)
    return good


def _check_enum_map(m, where: str, keys: tuple[str, ...], values: tuple[str, ...], errors: list[str],
                    *, complete: bool = False) -> None:
    if not isinstance(m, dict):
        errors.append(f"{where}: must be a mapping")
        return
    for k, v in m.items():
        if k not in keys:
            errors.append(f"{where}.{k}: unknown key")
        elif v not in values:
            errors.append(f"{where}.{k}: {v!r} not in {list(values)}")
    if complete:
        for k in keys:
            if k not in m:
                errors.append(f"{where}: missing {k}")


def _check_head_lead_tokens(val) -> list[str]:
    """``head_lead_tokens`` (W7, spec 3.5.2 R-H2): a list of lower-case canonical tokens; empty is allowed."""
    if not isinstance(val, list):
        return ["head_lead_tokens: must be a list of lower-case strings"]
    if not all(isinstance(s, str) and s and s == s.lower() for s in val):
        return ["head_lead_tokens: every entry must be a non-empty lower-case string"]
    return []


def _check_icon_albedo(val) -> list[str]:
    """``icon_albedo_from_material`` (W7, spec 3.8): ``[{name, packs_any?, id_regex}]``, names unique."""
    if not isinstance(val, list):
        return ["icon_albedo_from_material: must be a list of mappings"]
    errors: list[str] = []
    seen: set[str] = set()
    for i, row in enumerate(val):
        here = f"icon_albedo_from_material[{i}]"
        if not isinstance(row, dict):
            errors.append(f"{here}: must be a mapping with name, packs_any (optional) and id_regex")
            continue
        for key in row:
            if key not in _ALBEDO_KEYS:
                errors.append(f"{here}.{key}: unknown key (allowed: {', '.join(_ALBEDO_KEYS)})")
        name = row.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"{here}.name: must be a non-empty string")
        elif name in seen:
            errors.append(f"{here}.name: duplicate name {name!r}")
        else:
            seen.add(name)
        if "packs_any" in row:
            _check_str_list(row["packs_any"], f"{here}.packs_any", errors)
        pattern = row.get("id_regex")
        if not isinstance(pattern, str) or not pattern:
            errors.append(f"{here}.id_regex: must be a non-empty regex string")
        else:
            try:
                compile_regex(pattern)
            except re.error as exc:
                errors.append(f"{here}.id_regex: invalid regex ({exc})")
    return errors


def _check_kind_hints(val, aliases) -> list[str]:
    """``kind_hints`` (W7b, spec 3.4.2 PATCH W7b): ``{ranged|melee|thrown: [canonical lower-case tokens]}``.

    A token must be canonical (an alias variant could never match an id), and it may sit in one list only: the first
    kind whose list shares a token with the id wins, so a token in two lists would make the result depend on list order.
    """
    if not isinstance(val, dict):
        return ["kind_hints: must be a mapping kind -> [tokens]"]
    errors: list[str] = []
    owner: dict[str, str] = {}
    variants: dict[str, str] = {}
    if isinstance(aliases, dict):
        for target, vs in aliases.items():
            if isinstance(vs, list):
                variants.update({v: target for v in vs if isinstance(v, str)})
    for kind, tokens in val.items():
        if kind not in HINT_KINDS:
            errors.append(f"kind_hints.{kind}: unknown kind (allowed: {', '.join(HINT_KINDS)})")
            continue
        if not isinstance(tokens, list) or not all(isinstance(t, str) and t and t == t.lower() for t in tokens):
            errors.append(f"kind_hints.{kind}: must be a list of non-empty lower-case tokens")
            continue
        for t in tokens:
            if t in variants and variants[t] != t:
                errors.append(f"kind_hints.{kind}: token {t!r} is an alias variant of {variants[t]!r} and can never match")
            if t in owner and owner[t] != kind:
                errors.append(f"kind_hints: token {t!r} is in both {owner[t]!r} and {kind!r}")
            owner.setdefault(t, kind)
    return errors


def _check_attachment_rules(val) -> list[str]:
    """``attachment_rules`` (docs/weapon_attachments.md 3.3 and 4.2): ``{never, rows, child_tokens?, child_never?}``.

    Tokens here are RAW lower-case tokens (no ``token_aliases`` step: the alias table folds scope, sight, reddot and
    reflex into one ``optic`` token and mag, drum and clip into ``magazine``, which would erase the slot/kind
    distinction the table exists to make), so the alias-variant rejection of the other tables does not apply.
    ``never`` is an OR-list of ``{name, match}`` (a part matching any row is never an attachment, AC62); ``rows`` is the
    ordered first-match-wins table ``{name, match, set: {slot, kind}}``.
    """
    if not isinstance(val, dict):
        return ["attachment_rules: must be a mapping with never and rows"]
    errors: list[str] = []
    for key in val:
        if key not in ATTACH_TOP_KEYS:
            errors.append(f"attachment_rules.{key}: unknown key (allowed: {', '.join(ATTACH_TOP_KEYS)})")
    never = val.get("never")
    if not isinstance(never, list):
        errors.append("attachment_rules.never: must be a list of {name, match} rows (may be empty)")
    else:
        for row in _check_table(never, "attachment_rules.never", errors) if never else ():
            _check_match(row.get("match"), f"attachment_rules.never[{row['name']}].match", ATTACH_NEVER_KEYS, errors)
    rows = val.get("rows")
    if not isinstance(rows, list):
        errors.append("attachment_rules.rows: must be a list")
    else:
        for row in _check_table(rows, "attachment_rules.rows", errors) if rows else ():
            where = f"attachment_rules.rows[{row['name']}]"
            m = row.get("match")
            _check_match(m, where + ".match", ATTACH_MATCH_KEYS, errors)
            if isinstance(m, dict) and "component_slot" in m:
                cs = m["component_slot"]
                cs_list = [cs] if isinstance(cs, str) else cs
                if not (isinstance(cs_list, list) and cs_list and set(cs_list) <= set(COMPONENT_SLOTS)):
                    errors.append(f"{where}.match.component_slot: must be one or a list of {list(COMPONENT_SLOTS)}")
            s = row.get("set")
            if "reason" in row:  # a reason row sets no slot (A2): exactly one of `set` and `reason`
                if s is not None or row["reason"] not in ATTACH_ROW_REASONS:
                    errors.append(f"{where}: carries either set or reason, and a reason is one of {list(ATTACH_ROW_REASONS)}")
            elif not isinstance(s, dict) or set(s) != {"slot", "kind"}:
                errors.append(f"{where}.set: must be a mapping with exactly slot and kind")
            elif s["slot"] not in ATTACH_SLOTS:
                errors.append(f"{where}.set.slot: {s['slot']!r} not in {list(ATTACH_SLOTS)}")
            elif s["kind"] not in ATTACH_KINDS[s["slot"]]:
                errors.append(f"{where}.set.kind: {s['kind']!r} not in {list(ATTACH_KINDS[s['slot']])}")
    # W8b host-child vocabulary (docs/weapon_attachments.md 4.2): slot -> name tokens of the baked children that fill it
    ct = val.get("child_tokens")
    if ct is not None:
        if not isinstance(ct, dict):
            errors.append("attachment_rules.child_tokens: must be a mapping slot -> [tokens]")
        else:
            for slot, tokens in ct.items():
                if slot not in ATTACH_SLOTS:
                    errors.append(f"attachment_rules.child_tokens.{slot}: not in {list(ATTACH_SLOTS)}")
                else:
                    _check_str_list(tokens, f"attachment_rules.child_tokens.{slot}", errors, lower=True)
    if val.get("child_never") is not None:
        _check_str_list(val["child_never"], "attachment_rules.child_never", errors, lower=True)
    if val.get("attach_affinity") is not None:
        errors.extend(_check_attach_affinity(val["attach_affinity"]))
    if val.get("attach_compat") is not None:
        errors.extend(_check_attach_compat(val["attach_compat"]))
    if val.get("attach_genre_by_pack") is not None:
        errors.extend(_check_genre_by_pack(val["attach_genre_by_pack"]))
    if val.get("sight_probe") is not None:
        errors.extend(_check_sight_probe(val["sight_probe"]))
    if val.get("attach_host_never") is not None:
        errors.extend(_check_host_never(val["attach_host_never"]))
    if val.get("baked_sights") is not None:
        errors.extend(_check_baked_sights(val["baked_sights"]))
    if val.get("anchor") is not None:
        errors.extend(_check_anchor(val["anchor"]))
    if val.get("family_free_slots") is not None:
        errors.extend(_check_family_free_slots(val["family_free_slots"]))
    if val.get("contact") is not None:
        errors.extend(_check_contact(val["contact"]))
    if val.get("attach_host_class") is not None:
        errors.extend(_check_host_class(val["attach_host_class"]))
    if val.get("attach_class_never") is not None:
        errors.extend(_check_class_never(val["attach_class_never"], val.get("attach_host_class")))
    if val.get("muzzle_seat") is not None:
        errors.extend(_check_muzzle_seat(val["muzzle_seat"]))
    return errors


def _check_anchor(val) -> list[str]:
    """``anchor``: the foot ladder and the free-end forward of the anchor measurement (A4, spec 3.4 steps 1a and 3b); every key is required.

    ``foot_depths_m`` is an increasing list of positive depths (the first is the foot slab of step 1), ``lip_min_m`` must not exceed ``lip_max_m``,
    and ``free_end`` is ``{min_displacement_m, kinds: {slot: [kind]}}`` over foot slots (a muzzle device has no foot slab) and kinds of that slot.
    """
    where = "attachment_rules.anchor"
    if not isinstance(val, dict):
        return [f"{where}: must be a mapping"]
    errors: list[str] = []
    for key in val:
        if key not in ("foot_depths_m", "free_end") + tuple(ANCHOR_PARAMS):
            errors.append(f"{where}.{key}: unknown key (allowed: foot_depths_m, {', '.join(ANCHOR_PARAMS)}, free_end)")
    depths = val.get("foot_depths_m")
    if not isinstance(depths, list) or not 1 <= len(depths) <= ANCHOR_MAX_RUNGS or not all(_is_num(d) and 0 < d <= 0.1 for d in depths):
        errors.append(f"{where}.foot_depths_m: must be a list of 1 to {ANCHOR_MAX_RUNGS} depths in metres, each above 0 and at most 0.1")
    elif any(b <= a for a, b in zip(depths, depths[1:])):
        errors.append(f"{where}.foot_depths_m: must be strictly increasing")
    for key, (lo, hi) in ANCHOR_PARAMS.items():
        v = val.get(key)
        if not _is_num(v) or not (lo <= v <= hi):
            errors.append(f"{where}.{key}: must be a number from {lo} to {hi}")
    if not errors and val["lip_min_m"] > val["lip_max_m"]:
        errors.append(f"{where}: lip_min_m must not exceed lip_max_m")
    free = val.get("free_end")
    if not isinstance(free, dict):
        errors.append(f"{where}.free_end: must be a mapping with {', '.join(ANCHOR_FREE_END_KEYS)}")
        return errors
    for key in free:
        if key not in ANCHOR_FREE_END_KEYS:
            errors.append(f"{where}.free_end.{key}: unknown key (allowed: {', '.join(ANCHOR_FREE_END_KEYS)})")
    disp = free.get("min_displacement_m")
    if not _is_num(disp) or not (0 < disp <= 0.5):
        errors.append(f"{where}.free_end.min_displacement_m: must be a number above 0 and at most 0.5")
    kinds = free.get("kinds")
    if not isinstance(kinds, dict):
        errors.append(f"{where}.free_end.kinds: must be a mapping slot -> [kinds]")
        return errors
    for slot, names in kinds.items():
        if slot not in ATTACH_SLOTS or slot == "muzzle":
            errors.append(f"{where}.free_end.kinds.{slot}: must be a foot slot of {[s for s in ATTACH_SLOTS if s != 'muzzle']}")
        elif not isinstance(names, list) or not names or not all(n in ATTACH_KINDS[slot] for n in names):
            errors.append(f"{where}.free_end.kinds.{slot}: must be a non-empty list of kinds of that slot ({list(ATTACH_KINDS[slot])})")
    return errors


def _check_contact(val) -> list[str]:
    """``contact``: the parameters of settle to contact (A5, spec 5.4); every key is required.

    ``slots`` is a non-empty list of distinct slots of ``CONTACT_SLOTS``; the five lengths are in range, and the dead zone must stay below the clamp
    (otherwise a pair would be clamped to a value inside its own dead zone).
    """
    where = "attachment_rules.contact"
    if not isinstance(val, dict):
        return [f"{where}: must be a mapping with slots, {', '.join(CONTACT_PARAMS)}"]
    errors: list[str] = []
    for key in val:
        if key != "slots" and key not in CONTACT_PARAMS:
            errors.append(f"{where}.{key}: unknown key (allowed: slots, {', '.join(CONTACT_PARAMS)})")
    slots = val.get("slots")
    if not isinstance(slots, list) or not slots or not all(isinstance(s, str) and s in CONTACT_SLOTS for s in slots):
        errors.append(f"{where}.slots: must be a non-empty list of slots from {list(CONTACT_SLOTS)}")
    elif len(set(slots)) != len(slots):
        errors.append(f"{where}.slots: slots must be distinct")
    for key, (lo, hi) in CONTACT_PARAMS.items():
        v = val.get(key)
        if not _is_num(v) or not (lo <= v <= hi):
            errors.append(f"{where}.{key}: must be a number from {lo} to {hi}")
    if not errors and val["dead_m"] >= val["clamp_m"]:
        errors.append(f"{where}: dead_m must be below clamp_m")
    if not errors and val["cap_m"] > val["clamp_m"]:
        errors.append(f"{where}: cap_m must not exceed clamp_m")  # a pair settled past the clamp is clamped, so a larger cap could never bite
    return errors


def _check_muzzle_seat(val) -> list[str]:
    """``muzzle_seat``: the parameters of the silencer seat (A6, 13.7 A6-2); every key is required and in range."""
    where = "attachment_rules.muzzle_seat"
    if not isinstance(val, dict):
        return [f"{where}: must be a mapping with {', '.join(MUZZLE_SEAT_PARAMS)}"]
    errors: list[str] = []
    for key in val:
        if key not in MUZZLE_SEAT_PARAMS:
            errors.append(f"{where}.{key}: unknown key (allowed: {', '.join(MUZZLE_SEAT_PARAMS)})")
    for key, (typ, lo, hi) in MUZZLE_SEAT_PARAMS.items():
        v = val.get(key)
        ok = (isinstance(v, int) and not isinstance(v, bool)) if typ is int else _is_num(v)
        if not ok or not (lo <= v <= hi):
            errors.append(f"{where}.{key}: must be {'an integer' if typ is int else 'a number'} from {lo} to {hi}")
    if not errors:
        if val["window_m"] > val["range_m"]:
            errors.append(f"{where}: window_m must not exceed range_m")
        if val["window_m"] + 0.010 > SEAT_SETBACK_MAX_M:
            errors.append(f"{where}.window_m: the longest set-back (window_m + 10 mm) must stay within {SEAT_SETBACK_MAX_M}")
        if val["device_reach_m"] > val["window_m"]:
            errors.append(f"{where}: device_reach_m must not exceed window_m")
    return errors


def _check_host_class(val) -> list[str]:
    """``attach_host_class``: ``{class: [host name tokens]}`` (A6, 13.7 A6-1), tokens as in ``attach_host_never``. A host whose name has one of
    them is in the class; the class refuses the slots ``attach_class_never`` lists for it."""
    where = "attachment_rules.attach_host_class"
    if not isinstance(val, dict):
        return [f"{where}: must be a mapping class -> [host name tokens]"]
    errors: list[str] = []
    for name, tokens in val.items():
        if not isinstance(name, str) or not name or name != name.lower():
            errors.append(f"{where}.{name}: a class name must be a non-empty lower-case string")
        else:
            _check_str_list(tokens, f"{where}.{name}", errors, lower=True)
    return errors


def _check_class_never(val, classes) -> list[str]:
    """``attach_class_never``: ``{class: [refused slots]}`` (A6, 13.7 A6-1). Every class has to be one ``attach_host_class`` defines; the list may be
    empty (a class switched off), its slots are distinct slots."""
    where = "attachment_rules.attach_class_never"
    if not isinstance(val, dict):
        return [f"{where}: must be a mapping class -> [slots]"]
    errors: list[str] = []
    known = classes if isinstance(classes, dict) else {}
    for name, slots in val.items():
        if name not in known:
            errors.append(f"{where}.{name}: not a class of attach_host_class")
        elif not isinstance(slots, list) or not all(isinstance(s, str) and s in ATTACH_SLOTS for s in slots):
            errors.append(f"{where}.{name}: must be a list of slots from {list(ATTACH_SLOTS)} (may be empty)")
        elif len(set(slots)) != len(slots):
            errors.append(f"{where}.{name}: slots must be distinct")
    return errors


def _check_family_free_slots(val) -> list[str]:
    """``family_free_slots``: the slots whose same_pack_fit candidate needs no ``family_overlap`` (A4, spec 5.1); a list of distinct slots, may be empty."""
    where = "attachment_rules.family_free_slots"
    if not isinstance(val, list) or not all(isinstance(s, str) and s in ATTACH_SLOTS for s in val):
        return [f"{where}: must be a list of slots from {list(ATTACH_SLOTS)}"]
    return [f"{where}: slots must be distinct"] if len(set(val)) != len(val) else []


def _check_host_never(val) -> list[str]:
    """``attach_host_never``: ``{slot: [host name tokens]}`` (A3, spec 7). A host whose name has one of the tokens gets no seat for the slot."""
    where = "attachment_rules.attach_host_never"
    if not isinstance(val, dict):
        return [f"{where}: must be a mapping slot -> [host name tokens]"]
    errors: list[str] = []
    for slot, tokens in val.items():
        if slot not in ATTACH_SLOTS:
            errors.append(f"{where}.{slot}: not in {list(ATTACH_SLOTS)}")
        else:
            _check_str_list(tokens, f"{where}.{slot}", errors, lower=True)
    return errors


def _check_baked_sights(val) -> list[str]:
    """``baked_sights``: ``{tokens, not_tokens, rear_tokens}`` (A3, spec 4.6 item 7), lower-case child name tokens, plus the optional
    addendum 3 keys of item 8 (``glass_tokens``, ``body_tokens``, ``handle_tokens``, ``handle_not_tokens``, ``handle_min_height_frac``,
    ``fused_post``).

    ``tokens`` must name something; the other lists may be empty (no veto words, no carry-handle rule). A handle rule (non-empty
    ``handle_tokens``) needs its height fraction; a ``fused_post`` table needs all of its parameters, in range, with a width range that is
    not empty.
    """
    where = "attachment_rules.baked_sights"
    if not isinstance(val, dict):
        return [f"{where}: must be a mapping with {', '.join(BAKED_SIGHT_KEYS)}"]
    errors: list[str] = []
    for key in val:
        if key not in BAKED_SIGHT_KEYS + BAKED_SIGHT_OPTIONAL:
            errors.append(f"{where}.{key}: unknown key (allowed: {', '.join(BAKED_SIGHT_KEYS + BAKED_SIGHT_OPTIONAL)})")
    for key in BAKED_SIGHT_KEYS:
        tokens = val.get(key)
        if key != "tokens" and tokens == []:
            continue
        _check_str_list(tokens, f"{where}.{key}", errors, lower=True)
    for key in BAKED_OPTIC_LISTS:
        if key in val and val[key] != []:
            _check_str_list(val[key], f"{where}.{key}", errors, lower=True)
    frac = val.get("handle_min_height_frac")
    if frac is not None and not (_is_num(frac) and 0 <= frac <= 1):
        errors.append(f"{where}.handle_min_height_frac: must be a number from 0 to 1")
    if val.get("handle_tokens") and frac is None:
        errors.append(f"{where}.handle_min_height_frac: required with handle_tokens")
    if "fused_post" in val:
        errors.extend(_check_fused_post(val["fused_post"]))
    return errors


def _check_fused_post(val) -> list[str]:
    """``baked_sights.fused_post``: the numeric parameters of the fused front post detector (spec 4.6 item 8 D); every one is required."""
    where = "attachment_rules.baked_sights.fused_post"
    if not isinstance(val, dict):
        return [f"{where}: must be a mapping"]
    errors = []
    for key in val:
        if key not in FUSED_POST_PARAMS:
            errors.append(f"{where}.{key}: unknown key (allowed: {', '.join(FUSED_POST_PARAMS)})")
    for key, (typ, lo, hi) in FUSED_POST_PARAMS.items():
        v = val.get(key)
        ok = (isinstance(v, int) and not isinstance(v, bool)) if typ is int else _is_num(v)
        if not ok or not (lo <= v <= hi):
            errors.append(f"{where}.{key}: must be {'an integer' if typ is int else 'a number'} from {lo} to {hi}")
    if not errors and val["width_min_m"] > val["width_max_m"]:
        errors.append(f"{where}: width_min_m must not exceed width_max_m")
    return errors


def _check_genre_by_pack(val) -> list[str]:
    """``attach_genre_by_pack``: full pack id -> lower-case setting word (spec 5.1)."""
    where = "attachment_rules.attach_genre_by_pack"
    if not isinstance(val, dict):
        return [f"{where}: must be a mapping pack id -> setting word"]
    errors = []
    for pack, setting in val.items():
        if not isinstance(pack, str) or not pack:
            errors.append(f"{where}: pack ids must be non-empty strings")
        elif not isinstance(setting, str) or not setting or setting != setting.lower():
            errors.append(f"{where}.{pack}: the setting must be a non-empty lower-case word")
    return errors


def _check_sight_probe(val) -> list[str]:
    """``sight_probe``: the numeric parameters of the sight seat probe (spec 4.6); every one is required."""
    where = "attachment_rules.sight_probe"
    if not isinstance(val, dict):
        return [f"{where}: must be a mapping"]
    errors = []
    for key in val:
        if key not in SIGHT_PROBE_PARAMS and key != "receiver_tol_by_host":
            errors.append(f"{where}.{key}: unknown key (allowed: {', '.join(SIGHT_PROBE_PARAMS)}, receiver_tol_by_host)")
    for key, (typ, lo, hi) in SIGHT_PROBE_PARAMS.items():
        v = val.get(key)
        ok = (isinstance(v, int) and not isinstance(v, bool)) if typ is int else _is_num(v)
        if not ok or not (lo <= v <= hi):
            errors.append(f"{where}.{key}: must be {'an integer' if typ is int else 'a number'} from {lo} to {hi}")
    by_host = val.get("receiver_tol_by_host")
    if "receiver_tol_by_host" in val:  # A6 (W8n): optional, {"<pack>/<host id>": tolerance in metres}, the tolerance of that host only
        if not isinstance(by_host, dict):
            errors.append(f"{where}.receiver_tol_by_host: must be a mapping '<pack>/<host id>' -> metres")
        else:
            for host, tol in by_host.items():
                if not isinstance(host, str) or host.count("/") != 1 or not all(host.split("/")):
                    errors.append(f"{where}.receiver_tol_by_host.{host}: the key must be '<pack>/<host id>'")
                elif not _is_num(tol) or not (0 < tol <= SIGHT_PROBE_RECEIVER_TOL_BY_HOST_MAX_M):
                    errors.append(f"{where}.receiver_tol_by_host.{host}: must be a number above 0 and at most {SIGHT_PROBE_RECEIVER_TOL_BY_HOST_MAX_M}")
    return errors


def _check_attach_affinity(val) -> list[str]:
    """``attach_affinity``: ``{slot: {kind | default: [archetype, ...]}}`` (docs/weapon_attachments.md 5.1)."""
    if not isinstance(val, dict):
        return ["attachment_rules.attach_affinity: must be a mapping slot -> {kind -> [archetypes]}"]
    errors: list[str] = []
    for slot, kinds in val.items():
        where = f"attachment_rules.attach_affinity.{slot}"
        if slot not in ATTACH_SLOTS:
            errors.append(f"{where}: slot not in {list(ATTACH_SLOTS)}")
        elif not isinstance(kinds, dict) or not kinds:
            errors.append(f"{where}: must be a non-empty mapping kind -> [archetypes]")
        else:
            for kind, archetypes in kinds.items():
                if kind != "default" and kind not in ATTACH_KINDS[slot]:
                    errors.append(f"{where}.{kind}: not a kind of the slot (or 'default'): {list(ATTACH_KINDS[slot])}")
                elif not isinstance(archetypes, list) or not all(isinstance(a, str) for a in archetypes):
                    errors.append(f"{where}.{kind}: must be a list of archetypes")
                elif not set(archetypes) <= set(ARCHETYPES):
                    errors.append(f"{where}.{kind}: unknown archetype(s) {sorted(set(archetypes) - set(ARCHETYPES))}")
    return errors


def _check_attach_compat(val) -> list[str]:
    """``attach_compat``: the score parameters. Every reachable score has to stay inside its tier's band (spec 5.1 table)."""
    where = "attachment_rules.attach_compat"
    if not isinstance(val, dict):
        return [f"{where}: must be a mapping"]
    errors: list[str] = []
    for key in val:
        if key not in ("tier_score", "base", "generic_tokens", *COMPAT_NUMBER_KEYS, *COMPAT_MAGAZINE_KEYS):
            errors.append(f"{where}.{key}: unknown key")
    for key, (lo, hi) in COMPAT_MAGAZINE_KEYS.items():
        if key in val and not (_is_num(val[key]) and lo <= val[key] <= hi):
            errors.append(f"{where}.{key}: must be a number from {lo} to {hi}")
    nums = {}
    for key in COMPAT_NUMBER_KEYS:
        if key in val and not (_is_num(val[key]) and 0 <= val[key] <= 0.5):
            errors.append(f"{where}.{key}: must be a number from 0 to 0.5")
        nums[key] = val[key] if _is_num(val.get(key)) else 0.0
    ts, base = val.get("tier_score"), val.get("base")
    if ts is not None:
        if not (isinstance(ts, dict) and set(ts) <= set(COMPAT_FIXED_TIERS) and all(_is_num(v) and 0 <= v <= 1 for v in ts.values())):
            errors.append(f"{where}.tier_score: must map {list(COMPAT_FIXED_TIERS)} to numbers from 0 to 1")
    if base is not None:
        if not (isinstance(base, dict) and set(base) <= set(COMPAT_SCORE_BANDS) and all(_is_num(v) for v in base.values())):
            errors.append(f"{where}.base: must map {list(COMPAT_SCORE_BANDS)} to numbers")
        else:
            for tier, b in base.items():
                lo, hi = COMPAT_SCORE_BANDS[tier]
                top, bottom = b + nums["fit_span_bonus"] + nums["fit_bore_bonus"], b - nums["fit_bore_penalty"]
                if top > hi + 1e-9 or bottom < lo - 1e-9:
                    errors.append(f"{where}.base.{tier}: {b} with the fit signals reaches {round(bottom, 4)}..{round(top, 4)}, "
                                  f"outside the band {lo}-{hi}")
    if val.get("generic_tokens") is not None:
        _check_str_list(val["generic_tokens"], f"{where}.generic_tokens", errors, lower=True)
    return errors


def attachment_rules(rules: dict) -> dict:
    """The ``attachment_rules`` mapping; an empty table (nothing is an attachment) when the key is absent."""
    return rules.get("attachment_rules") or {"never": [], "rows": []}


def weapon_rules_digest(rules: dict) -> str:
    """``rules_digest`` of the directory header and of an export's ``generated_from``: the digest of every rule section
    W7 hashed, i.e. everything except ``attachment_rules``. The attachment table has its own ``attach_rules_digest``, so
    adding it to the shipped YAML leaves the default export byte-identical to W7's (docs/weapon_attachments.md D-10)."""
    return digest({k: v for k, v in rules.items() if k != "attachment_rules"})


def attach_rules_digest(rules: dict) -> str:
    """Digest of the ``attachment_rules`` table alone (rows, never, child_tokens, child_never and every other key of it, A3's
    ``attach_host_never`` and ``baked_sights`` included); an absent table hashes as empty."""
    return digest(attachment_rules(rules))


def kind_hints(rules: dict) -> list[tuple[str, frozenset[str]]]:
    """``[(kind, tokens)]`` for the non-empty ``kind_hints`` lists, in ``HINT_KINDS`` order; empty when the key is absent."""
    table = rules.get("kind_hints") or {}
    return [(k, frozenset(table[k])) for k in HINT_KINDS if table.get(k)]


def head_lead_tokens(rules: dict) -> frozenset[str]:
    """The tool tokens whose head leads (W7 R-H2); empty when the key is absent."""
    return frozenset(rules.get("head_lead_tokens") or ())


def icon_albedo_entries(rules: dict) -> list[dict]:
    """The ``icon_albedo_from_material`` entries (W7), in file order; empty when the key is absent."""
    return list(rules.get("icon_albedo_from_material") or ())


def validate_rules(rules) -> list[str]:
    """Every violation of the weapon_rules.yaml schema (spec 4.4), as readable messages naming the key."""
    errors: list[str] = []
    if not isinstance(rules, dict):
        return ["weapon_rules.yaml: top level must be a mapping"]
    for key in REQUIRED_TOP:
        if key not in rules:
            errors.append(f"missing top-level key: {key}")
    for key in rules:
        if key not in REQUIRED_TOP and key not in OPTIONAL_TOP:
            errors.append(f"unknown top-level key: {key}")
    if errors:
        return errors
    if rules["version"] != 1:
        errors.append(f"version: expected 1, got {rules['version']!r}")

    # token_aliases: target -> variants
    aliases = rules["token_aliases"]
    variants: dict[str, str] = {}
    if not isinstance(aliases, dict):
        errors.append("token_aliases: must be a mapping target -> [variants]")
    else:
        for target, vs in aliases.items():
            if target != str(target).lower():
                errors.append(f"token_aliases.{target}: target must be lower-case")
            if not isinstance(vs, list) or not all(isinstance(v, str) and v and v == v.lower() for v in vs):
                errors.append(f"token_aliases.{target}: variants must be lower-case strings")
                continue
            for v in vs:
                if v in variants and variants[v] != target:
                    errors.append(f"token_aliases: variant {v!r} maps to both {variants[v]!r} and {target!r}")
                variants[v] = target
        for t in aliases:
            if t in variants and variants[t] != t:
                errors.append(f"token_aliases: target {t!r} is also a variant of {variants[t]!r}")

    def check_token_use(tokens, where):
        for t in tokens or ():
            if t in variants and variants[t] != t:
                errors.append(f"{where}: token {t!r} is an alias variant of {variants[t]!r} and can never match")

    cand = rules["candidates"]
    if not isinstance(cand, dict) or not isinstance(cand.get("include"), list) or not isinstance(cand.get("exclude"), list):
        errors.append("candidates: needs include and exclude lists")
    else:
        for row in _check_table(cand["include"], "candidates.include", errors):
            where = f"candidates.include[{row['name']}]"
            _check_match(row.get("match"), where, CANDIDATE_MATCH_KEYS, errors)
            for k in ("tokens_any", "tokens_all", "tokens_none"):
                check_token_use((row.get("match") or {}).get(k), f"{where}.{k}")
        for row in _check_table(cand["exclude"], "candidates.exclude", errors):
            where = f"candidates.exclude[{row['name']}]"
            _check_match(row.get("match"), where, CANDIDATE_MATCH_KEYS, errors)
            if row.get("reason") not in EXCLUDE_REASONS or row.get("reason") == "override":
                errors.append(f"{where}.reason: {row.get('reason')!r} not a pattern reason in {list(EXCLUDE_REASONS)}")
            for k in ("tokens_any", "tokens_all", "tokens_none"):
                check_token_use((row.get("match") or {}).get(k), f"{where}.{k}")

    for row in _check_table(rules["rules"], "rules", errors):
        where = f"rules[{row['name']}]"
        m = row.get("match")
        _check_match(m, where + ".match", RULE_MATCH_KEYS, errors)
        for k in ("tokens_any", "tokens_all", "tokens_none"):
            check_token_use((m or {}).get(k), f"{where}.match.{k}")
        conf = row.get("confidence")
        if not _is_num(conf) or not (0.05 <= conf <= 0.99):
            errors.append(f"{where}.confidence: must be a number in [0.05, 0.99]")
        s = row.get("set")
        if not isinstance(s, dict):
            errors.append(f"{where}.set: must be a mapping")
            continue
        for k in s:
            if k not in RULE_SET_KEYS:
                errors.append(f"{where}.set.{k}: unknown key")
        role = s.get("role")
        if role not in ROLES:
            errors.append(f"{where}.set.role: {role!r} not in {list(ROLES)}")
        if s.get("kind") is not None and s["kind"] not in KINDS:
            errors.append(f"{where}.set.kind: {s['kind']!r} not in {list(KINDS)}")
        arch = s.get("archetype")
        if arch is not None and arch not in ARCHETYPES:
            errors.append(f"{where}.set.archetype: {arch!r} not in ARCHETYPES")
        if arch in ARCHETYPE_KIND and s.get("kind") not in (None, ARCHETYPE_KIND[arch]):
            errors.append(f"{where}.set: kind {s['kind']!r} contradicts archetype {arch!r}")
        if role == "whole" and arch is None:
            errors.append(f"{where}.set: role whole needs an archetype")
        if role == "emplaced" and arch not in EMPLACED_ARCHETYPES:
            errors.append(f"{where}.set: emplaced role needs an emplaced archetype")
        if role == "part" and s.get("component") not in COMPONENT_SLOTS:
            errors.append(f"{where}.set.component: {s.get('component')!r} not in {list(COMPONENT_SLOTS)}")
        if role == "carrier" and s.get("carrier") not in CARRIER_KINDS:
            errors.append(f"{where}.set.carrier: {s.get('carrier')!r} not in {list(CARRIER_KINDS)}")
        if role == "ammo" and s.get("ammo") not in AMMO_PROJECTILES:
            errors.append(f"{where}.set.ammo: {s.get('ammo')!r} not in {list(AMMO_PROJECTILES)}")

    _check_enum_map(rules["hold_by_archetype"], "hold_by_archetype", ARCHETYPES, HOLD_CLASSES, errors, complete=True)
    ex = rules.get("hold_exceptions", [])
    if not isinstance(ex, list):
        errors.append("hold_exceptions: must be a list")
    else:
        for i, row in enumerate(ex):
            here = f"hold_exceptions[{i}]"
            if not isinstance(row, dict) or row.get("hold") not in HOLD_CLASSES:
                errors.append(f"{here}: needs hold in {list(HOLD_CLASSES)}")
                continue
            for k in row:
                if k not in ("name", "archetypes", "kind", "gear_two_handed", "min_length_m", "hold"):
                    errors.append(f"{here}.{k}: unknown key")
            if "archetypes" in row and not (isinstance(row["archetypes"], list) and set(row["archetypes"]) <= set(ARCHETYPES)):
                errors.append(f"{here}.archetypes: must be a list of archetypes")
            if "kind" in row and row["kind"] not in KINDS:
                errors.append(f"{here}.kind: {row['kind']!r} not in {list(KINDS)}")
            if "gear_two_handed" in row and not isinstance(row["gear_two_handed"], bool):
                errors.append(f"{here}.gear_two_handed: must be a bool")
    gen = rules["genre_by_archetype"]
    if not isinstance(gen, dict):
        errors.append("genre_by_archetype: must be a mapping")
    else:
        _check_enum_map(gen, "genre_by_archetype", ARCHETYPES + ("default",), GENRES, errors)
        if "default" not in gen:
            errors.append("genre_by_archetype: needs a default")
    for name, table in (("plausible_length_m", rules["plausible_length_m"]), ("grip_proportion", rules["grip_proportion"])):
        if not isinstance(table, dict):
            errors.append(f"{name}: must be a mapping")
            continue
        for k, v in table.items():
            if k not in ARCHETYPES:
                errors.append(f"{name}.{k}: unknown archetype")
            elif not (isinstance(v, list) and len(v) == 2 and all(_is_num(x) for x in v)):
                errors.append(f"{name}.{k}: must be [a, b] numbers")
    ax = rules["axes_expected"]
    if not isinstance(ax, dict):
        errors.append("axes_expected: must be a mapping genre -> class -> axis")
    else:
        for g, by_class in ax.items():
            if g not in GENRES or not isinstance(by_class, dict):
                errors.append(f"axes_expected.{g}: genre must be one of {list(GENRES)} with a mapping value")
                continue
            for cls, axis in by_class.items():
                if cls not in KINDS or not (isinstance(axis, str) and _AXIS_RE.match(axis)):
                    errors.append(f"axes_expected.{g}.{cls}: kind in {list(KINDS)} with a signed axis like '+z'")
    cuts = rules["size_class_cuts_m"]
    if not (isinstance(cuts, list) and len(cuts) == 4 and all(_is_num(x) for x in cuts) and cuts == sorted(cuts)):
        errors.append("size_class_cuts_m: must be 4 ascending numbers")
    _check_enum_map(rules["weight_by_archetype"], "weight_by_archetype", ARCHETYPES, WEIGHT_CLASSES, errors)
    tb = rules["tier_base"]
    if not isinstance(tb, dict):
        errors.append("tier_base: must be a mapping")
    else:
        for k, v in tb.items():
            if k not in ARCHETYPES or k == "unknown":
                errors.append(f"tier_base.{k}: unknown archetype")
            elif not (isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 5):
                errors.append(f"tier_base.{k}: must be an int 1-5")
    _check_enum_map(rules["ammo_by_archetype"], "ammo_by_archetype", ARCHETYPES, AMMO_FAMILIES, errors)
    pf = rules["pack_flags"]
    if not isinstance(pf, dict):
        errors.append("pack_flags: must be a mapping pack-glob -> [flags]")
    else:
        for k, v in pf.items():
            if not (isinstance(v, list) and v and set(v) <= set(FLAGS)):
                errors.append(f"pack_flags.{k}: must be a list of flags from {list(FLAGS)}")
    idf = rules.get("id_flags", [])
    if not isinstance(idf, list):
        errors.append("id_flags: must be a list")
    else:
        for i, row in enumerate(idf):
            if not (isinstance(row, dict) and row.get("flag") in FLAGS and isinstance(row.get("id_regex"), str)):
                errors.append(f"id_flags[{i}]: needs flag in FLAGS and an id_regex")
                continue
            try:
                compile_regex(row["id_regex"])
            except re.error as exc:
                errors.append(f"id_flags[{i}].id_regex: invalid regex ({exc})")
    _check_str_list(rules["family_strip_tokens"], "family_strip_tokens", errors, lower=True)
    tt = rules.get("tier_tokens", {})
    if not isinstance(tt, dict) or any(k not in ("up", "down") for k in tt):
        errors.append("tier_tokens: must be a mapping with up/down lists")
    ato = rules.get("ammo_token_overrides", {})
    if not isinstance(ato, dict):
        errors.append("ammo_token_overrides: must be a mapping ammo family -> [tokens]")
    else:
        for family, words in ato.items():
            if family not in AMMO_FAMILIES:
                errors.append(f"ammo_token_overrides.{family}: not an ammo family in {list(AMMO_FAMILIES)}")
            else:
                _check_str_list(words, f"ammo_token_overrides.{family}", errors, lower=True)
    errors.extend(_check_head_lead_tokens(rules.get("head_lead_tokens", [])))
    errors.extend(_check_icon_albedo(rules.get("icon_albedo_from_material", [])))
    errors.extend(_check_kind_hints(rules.get("kind_hints", {}), rules["token_aliases"]))
    if "attachment_rules" in rules:
        errors.extend(_check_attachment_rules(rules["attachment_rules"]))
    uc = rules.get("unknown_confidence", 0.2)
    if not _is_num(uc) or not (0.05 <= uc <= 0.99):
        errors.append("unknown_confidence: must be a number in [0.05, 0.99]")
    return errors


def load_rules(path: Path | None = None) -> dict:
    """Read and validate the rules file. ``SchemaError`` (exit 6) names every offending key."""
    path = path or default_rules_path()
    if not path.is_file():
        raise SchemaError(f"weapon_rules.yaml missing: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SchemaError(f"weapon_rules.yaml is not valid YAML: {exc}") from exc
    errors = validate_rules(data)
    if errors:
        raise SchemaError(
            "weapon_rules.yaml violates its schema:\n  " + "\n  ".join(errors[:25]), details={"errors": errors}
        )
    return data
