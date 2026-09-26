"""``packs suggest``: rank cataloged packs against a ``game-brief/1`` (spec
§4.1) using nothing but ``pack_profile/1`` records (§4.3) -- deterministic,
no VLM, no network.

Score = sum of independently-documented terms below. Every term is capped so
no single signal can dominate; weights were picked, then checked against the
Dustline fixture (AC2: POLYGON_SciFi_Worlds/City/Space in the top 5,
POLYGON_Apocalypse/POLYGON_Gang_Warfare not in the top 10) and are not
claimed optimal beyond that (spec §6 AC2 note).
"""

from __future__ import annotations

import re

W_SETTING = 40.0
W_ERA = 10.0
W_GODOT_READY = 8.0
W_GRAMMAR = 6.0
W_SIZE = 10.0
W_MOOD_TOKEN = 2.0
MUST_PACK_SCORE = 1_000_000.0
SIZE_SATURATES_AT = 200  # role_counts total at which the size term maxes out

# pack_class weight: "environment" is the structural core of a packset (a
# brief's POIs are built from it), so it outweighs the supporting classes --
# otherwise a small, exact-setting-match SIDEKICK_*/INTERFACE_* pack can
# outrank the big environment packs a brief actually needs (observed while
# tuning against AC2: without this split, Dustline's own SIDEKICK_/
# INTERFACE_/*_Map picks crowded POLYGON_SciFi_City out of the top 5).
_CLASS_WEIGHT = {
    "environment": 25.0,
    "characters": 12.0,
    "map_demo": 10.0,
    "animation": 8.0,
    "interface": 8.0,
    "fx": 8.0,
    "addon": 0.0,
}

# setting affinity: exact match -> 1.0; "generic" packs are theme-agnostic
# utility (interface/animation/fx skeletons, starter kits) so they always
# get partial credit; everything else is 0 unless listed as a documented
# neighbor below (packs that could plausibly dress the same brief).
_NEIGHBORS: dict[frozenset[str], float] = {
    frozenset({"scifi_frontier", "scifi_city"}): 0.6,
    frozenset({"scifi_frontier", "space"}): 0.6,
    frozenset({"scifi_city", "space"}): 0.5,
    frozenset({"scifi_frontier", "military"}): 0.25,
    frozenset({"scifi_frontier", "post_apoc"}): 0.25,
    frozenset({"modern_city", "military"}): 0.3,
    frozenset({"modern_city", "post_apoc"}): 0.3,
    frozenset({"western", "post_apoc"}): 0.2,
    frozenset({"fantasy", "horror"}): 0.2,
    frozenset({"nature", "western"}): 0.2,
}

# Ordered low -> high, used only to give "one step off" a half-credit era
# term rather than an all-or-nothing one (pack_settings.yaml header owns
# the canonical list).
_ERA_ORDER = [
    "prehistoric",
    "ancient",
    "colonial",
    "medieval",
    "industrial",
    "modern",
    "near_future",
    "far_future",
]

# pack_class -> the game-brief roles (packset.yaml §4.2 vocab) it plausibly
# fills. Used both for scoring and for coverage_gaps.
_CLASS_ROLES = {
    "environment": {"env_structure", "env_props"},
    "characters": {"characters"},
    "animation": {"animation"},
    "interface": {"ui"},
    "fx": {"fx"},
    "map_demo": {"grammar_reference"},
    "addon": set(),
}
REQUIRED_ROLES = frozenset({"env_structure", "characters", "animation", "ui", "fx"})

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def setting_affinity(brief_setting: str | None, pack_setting: str | None) -> float:
    if not brief_setting or not pack_setting:
        return 0.0
    if pack_setting == brief_setting:
        return 1.0
    if pack_setting == "generic":
        return 0.5
    return _NEIGHBORS.get(frozenset({brief_setting, pack_setting}), 0.0)


def era_affinity(brief_era: str | None, pack_era: str | None) -> float:
    if not brief_era or not pack_era or brief_era == pack_era:
        return 1.0 if brief_era and brief_era == pack_era else 0.0
    try:
        gap = abs(_ERA_ORDER.index(brief_era) - _ERA_ORDER.index(pack_era))
    except ValueError:
        return 0.0
    return 0.5 if gap == 1 else 0.0


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _pack_size(profile: dict) -> int:
    return sum((profile.get("role_counts") or {}).values())


def _roles_covered(profile: dict) -> set[str]:
    roles = set(_CLASS_ROLES.get(profile.get("pack_class") or "", set()))
    if profile.get("characters_rig"):
        roles.add("characters")
    if profile.get("grammar_available"):
        roles.add("grammar_reference")
    return roles


def score_pack(brief: dict, profile: dict, *, engine: str | None) -> tuple[float, list[str], set[str]]:
    """Returns ``(score, reasons, roles_covered)``."""
    reasons: list[str] = []
    pack_id = profile["pack_id"]

    if pack_id in (brief.get("must_packs") or []):
        return MUST_PACK_SCORE, ["must_pack (brief-forced)"], _roles_covered(profile)

    setting = setting_affinity(brief.get("setting"), profile.get("setting"))
    score = setting * W_SETTING
    if setting >= 1.0:
        reasons.append(f"setting {profile.get('setting')!r} matches brief exactly")
    elif setting > 0:
        reasons.append(f"setting {profile.get('setting')!r} is a partial match for {brief.get('setting')!r}")

    era = era_affinity(brief.get("era"), profile.get("era"))
    score += era * W_ERA
    if era >= 1.0:
        reasons.append(f"era {profile.get('era')!r} matches brief")

    role_bonus = _CLASS_WEIGHT.get(profile.get("pack_class") or "", 0.0)
    score += role_bonus
    if role_bonus:
        reasons.append(f"pack_class {profile.get('pack_class')!r} fills a brief role")

    ready = bool(profile.get("godot_ready"))
    if (engine or "godot").lower() == "godot" and ready:
        score += W_GODOT_READY
        reasons.append("godot_ready")

    if profile.get("grammar_available"):
        score += W_GRAMMAR
        reasons.append("grammar_available")

    size = min(_pack_size(profile) / SIZE_SATURATES_AT, 1.0) * W_SIZE
    score += size

    mood_tokens = set()
    for m in brief.get("mood") or []:
        mood_tokens |= _tokens(str(m))
    pack_tokens = _tokens(pack_id.replace("_", " "))
    hits = mood_tokens & pack_tokens
    if hits:
        score += W_MOOD_TOKEN * len(hits)
        reasons.append(f"pack name matches mood token(s) {sorted(hits)}")

    return score, reasons, _roles_covered(profile)


def suggest_packs(
    brief: dict,
    profiles: list[dict],
    *,
    engine: str | None = "godot",
    max_results: int = 12,
) -> dict:
    """spec §3.3: ``{packs:[{pack_id, score, roles_covered[], godot_ready,
    grammar_available, reasons[]}], coverage_gaps:[]}``."""
    banned = set(brief.get("ban_packs") or [])
    ranked = []
    for profile in profiles:
        pack_id = profile["pack_id"]
        if pack_id in banned:
            continue
        score, reasons, roles = score_pack(brief, profile, engine=engine)
        ranked.append(
            {
                "pack_id": pack_id,
                "score": round(score, 2),
                "roles_covered": sorted(roles),
                "godot_ready": bool(profile.get("godot_ready")),
                "grammar_available": bool(profile.get("grammar_available")),
                "reasons": reasons,
            }
        )
    ranked.sort(key=lambda r: (-r["score"], r["pack_id"]))
    top = ranked[: max(max_results, 0)]

    covered: set[str] = set()
    for row in top:
        covered |= set(row["roles_covered"])
    gaps = sorted(REQUIRED_ROLES - covered)

    return {"packs": top, "coverage_gaps": gaps}
