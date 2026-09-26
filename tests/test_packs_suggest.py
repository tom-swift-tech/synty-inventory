"""Unit tests for ``packs.suggest`` (spec §3.3 ``packs suggest``) with small
fixture profiles, plus AC2 against the real catalogs when present."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from synty_inventory.packs.suggest import (
    era_affinity,
    setting_affinity,
    suggest_packs,
)

FIXTURE_BRIEF = Path(__file__).parent / "fixtures" / "packs" / "dustline_brief.yaml"


def _profile(pack_id, *, setting, era, pack_class="environment", godot_ready=False, grammar=False, size=200, rig=None):
    return {
        "pack_id": pack_id,
        "pack_class": pack_class,
        "setting": setting,
        "era": era,
        "role_counts": {"exterior_prop": size},
        "godot_ready": godot_ready,
        "grammar_available": grammar,
        "characters_rig": rig,
    }


# --- affinity helpers -----------------------------------------------------------


def test_setting_affinity_exact_match():
    assert setting_affinity("scifi_frontier", "scifi_frontier") == 1.0


def test_setting_affinity_generic_pack_gets_partial_credit():
    assert setting_affinity("scifi_frontier", "generic") == 0.5


def test_setting_affinity_documented_neighbor():
    assert setting_affinity("scifi_frontier", "scifi_city") == 0.6
    assert setting_affinity("scifi_city", "scifi_frontier") == 0.6  # symmetric


def test_setting_affinity_unrelated_is_zero():
    assert setting_affinity("scifi_frontier", "western") == 0.0


def test_setting_affinity_missing_values():
    assert setting_affinity(None, "scifi_frontier") == 0.0
    assert setting_affinity("scifi_frontier", None) == 0.0


def test_era_affinity_exact():
    assert era_affinity("far_future", "far_future") == 1.0


def test_era_affinity_adjacent_is_partial():
    assert era_affinity("far_future", "near_future") == 0.5


def test_era_affinity_far_apart_is_zero():
    assert era_affinity("far_future", "prehistoric") == 0.0


# --- suggest_packs ----------------------------------------------------------------


def test_suggest_packs_ranks_exact_setting_above_neighbor():
    brief = {"setting": "scifi_frontier", "era": "far_future"}
    profiles = [
        _profile("EXACT", setting="scifi_frontier", era="far_future"),
        _profile("NEIGHBOR", setting="scifi_city", era="far_future"),
        _profile("UNRELATED", setting="western", era="industrial"),
    ]
    result = suggest_packs(brief, profiles, max_results=10)
    ranked_ids = [p["pack_id"] for p in result["packs"]]
    assert ranked_ids.index("EXACT") < ranked_ids.index("NEIGHBOR") < ranked_ids.index("UNRELATED")


def test_suggest_packs_must_pack_forced_to_top():
    brief = {"setting": "scifi_frontier", "must_packs": ["LOW_SCORE_BUT_FORCED"]}
    profiles = [
        _profile("LOW_SCORE_BUT_FORCED", setting="western", era="industrial", pack_class="addon", size=1),
        _profile("BEST_NATURAL", setting="scifi_frontier", era="far_future", godot_ready=True, grammar=True),
    ]
    result = suggest_packs(brief, profiles, max_results=10)
    assert result["packs"][0]["pack_id"] == "LOW_SCORE_BUT_FORCED"


def test_suggest_packs_ban_pack_never_appears():
    brief = {"setting": "scifi_frontier", "ban_packs": ["BANNED"]}
    profiles = [
        _profile("BANNED", setting="scifi_frontier", era="far_future"),
        _profile("OTHER", setting="scifi_frontier", era="far_future"),
    ]
    result = suggest_packs(brief, profiles, max_results=10)
    ids = [p["pack_id"] for p in result["packs"]]
    assert "BANNED" not in ids
    assert "OTHER" in ids


def test_suggest_packs_godot_ready_and_grammar_bonus():
    brief = {"setting": "scifi_frontier", "era": "far_future", "engine": "godot"}
    profiles = [
        _profile("READY", setting="scifi_frontier", era="far_future", godot_ready=True, grammar=True),
        _profile("NOT_READY", setting="scifi_frontier", era="far_future", godot_ready=False, grammar=False),
    ]
    result = suggest_packs(brief, profiles, engine="godot", max_results=10)
    scores = {p["pack_id"]: p["score"] for p in result["packs"]}
    assert scores["READY"] > scores["NOT_READY"]


def test_suggest_packs_max_results_caps_output():
    brief = {"setting": "generic"}
    profiles = [_profile(f"P{i}", setting="generic", era="modern") for i in range(20)]
    result = suggest_packs(brief, profiles, max_results=5)
    assert len(result["packs"]) == 5


def test_suggest_packs_coverage_gaps_reports_missing_roles():
    brief = {"setting": "scifi_frontier"}
    profiles = [_profile("ENV_ONLY", setting="scifi_frontier", era="far_future", pack_class="environment")]
    result = suggest_packs(brief, profiles, max_results=5)
    assert "characters" in result["coverage_gaps"]
    assert "animation" in result["coverage_gaps"]
    assert "env_structure" not in result["coverage_gaps"]  # environment covers it


def test_suggest_packs_reasons_are_non_empty_for_top_hit():
    brief = {"setting": "scifi_frontier", "era": "far_future"}
    profiles = [_profile("A", setting="scifi_frontier", era="far_future")]
    result = suggest_packs(brief, profiles, max_results=5)
    assert result["packs"][0]["reasons"]


# --- AC2 fixture brief itself -------------------------------------------------


def test_dustline_brief_fixture_matches_game_brief_schema():
    brief = yaml.safe_load(FIXTURE_BRIEF.read_text(encoding="utf-8"))
    assert brief["schema"] == "game-brief/1"
    assert brief["setting"] == "scifi_frontier"
    assert brief["era"] == "far_future"
    assert set(brief["mood"]) >= {"dusty", "isolated", "industrial"}
    assert brief["perspective"] == "third_person"
    assert brief["engine"] == "godot"
    assert brief["world"]["size_m"] == 2048
    assert brief["world"]["biome"] == "rocky_remote"
    poi_types = {p["type"] for p in brief["poi_types"]}
    assert {"spaceport", "outpost", "research_station", "crash_site"} <= poi_types


# --- AC2 against the real catalogs, if present ---------------------------------


def _real_catalogs_dir():
    from synty_inventory.paths import ConfigError, load_config

    try:
        cfg = load_config(require=False)
    except ConfigError:
        return None
    catalogs_dir = cfg.get("catalogs")
    return catalogs_dir if catalogs_dir and catalogs_dir.is_dir() else None


@pytest.mark.live
def test_ac2_dustline_suggest_ranks_pilot_packs_in_real_catalogs():
    catalogs_dir = _real_catalogs_dir()
    if catalogs_dir is None:
        pytest.skip("no real catalogs configured on this machine")

    from synty_inventory.catalog import catalog_path, load_catalog
    from synty_inventory.packs.profile import build_pack_profile
    from synty_inventory.paths import is_pack_catalog_file

    from synty_inventory.paths import ConfigError, load_config

    godot_root = None
    try:
        cfg = load_config(require=False)
        godot_root = cfg.get("godot_root")
    except ConfigError:
        pass

    pack_ids = sorted(p.stem for p in catalogs_dir.glob("*.json") if is_pack_catalog_file(p))
    profiles = []
    for pack_id in pack_ids:
        doc = load_catalog(catalog_path(catalogs_dir, pack_id))
        if doc is not None:
            profiles.append(build_pack_profile(doc, catalogs_dir=catalogs_dir, godot_root=godot_root))

    brief = yaml.safe_load(FIXTURE_BRIEF.read_text(encoding="utf-8"))
    result = suggest_packs(brief, profiles, engine="godot", max_results=10)
    ranked_ids = [p["pack_id"] for p in result["packs"]]

    top5 = set(ranked_ids[:5])
    top10 = set(ranked_ids[:10])
    for wanted in ("POLYGON_SciFi_Worlds", "POLYGON_SciFi_City", "POLYGON_SciFi_Space"):
        assert wanted in top5, f"{wanted} not in top 5: {ranked_ids}"
    for banned in ("POLYGON_Apocalypse", "POLYGON_Gang_Warfare"):
        assert banned not in top10, f"{banned} leaked into top 10: {ranked_ids}"
