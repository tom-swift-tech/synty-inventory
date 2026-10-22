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
    CARRIER_KINDS,
    COMPONENT_SLOTS,
    EMPLACED_ARCHETYPES,
    EXCLUDE_REASONS,
    FLAGS,
    GENRES,
    HOLD_CLASSES,
    KINDS,
    ROLES,
    SchemaError,
    WEIGHT_CLASSES,
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
REQUIRED_TOP = (
    "version", "token_aliases", "candidates", "rules", "hold_by_archetype", "genre_by_archetype",
    "plausible_length_m", "axes_expected", "grip_proportion", "size_class_cuts_m", "weight_by_archetype",
    "tier_base", "ammo_by_archetype", "pack_flags", "family_strip_tokens",
)
# keys beyond spec 4.4 (judgment calls, reported): see weapon_rules.yaml for each.
OPTIONAL_TOP = (
    "hold_exceptions", "id_flags", "tier_tokens", "unknown_confidence", "ammo_token_overrides",
    "head_lead_tokens", "icon_albedo_from_material",  # W7: both default to empty (spec 4.4)
)
_ALBEDO_KEYS = ("name", "packs_any", "id_regex")

_AXIS_RE = re.compile(r"^[+-][xyz]$")


def default_rules_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "weapon_rules.yaml"


@lru_cache(maxsize=256)
def compile_regex(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


def match_conditions(match: dict, ctx: dict) -> bool:
    """True when every key present in ``match`` holds for ``ctx`` (keys are ANDed).

    ctx: id, tokens (set), pack, gear_two_handed (bool|None), long_m (float|None), asset_kind (str|None).
    A ``long_m`` condition never matches in pass 1 (``ctx['long_m'] is None``).
    """
    tokens = ctx["tokens"]
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
