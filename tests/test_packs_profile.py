"""Unit tests for ``packs.profile`` (spec §4.3 ``pack-profile/1``) -- small
fixture catalogs only, no VLM, no real machine trees (AC1 is exercised for
real in the live run, not here)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from synty_inventory.packs.profile import (
    ERAS,
    SETTINGS,
    build_pack_profile,
    characters_rig,
    classify_pack,
    godot_ready,
    grammar_available,
    kit_families,
    load_settings_table,
    measure_palette,
    role_counts,
    setting_and_era,
)


def _asset(id_, *, type_="prop", role="exterior_prop", placeable=True, family=None, glb=None) -> dict:
    return {
        "id": id_,
        "type": type_,
        "semantic_role": role,
        "placeable": placeable,
        "module": {"family": family},
        "files": {"glb": glb},
    }


# --- classify_pack -----------------------------------------------------------


def test_classify_pack_small_pack_is_addon_even_with_interface_prefix():
    assets = [_asset(f"a{i}") for i in range(10)]
    assert classify_pack("INTERFACE_Tiny_HUD", assets) == "addon"


def test_classify_pack_animation_prefix():
    assets = [_asset(f"a{i}", type_="animation", role="animation_clip", placeable=False) for i in range(50)]
    assert classify_pack("ANIMATION_Base_Locomotion", assets) == "animation"


def test_classify_pack_interface_prefix():
    assets = [_asset(f"a{i}", type_="ui", role="ui_element", placeable=False) for i in range(50)]
    assert classify_pack("INTERFACE_SciFi_Menus", assets) == "interface"


def test_classify_pack_sidekick_prefix():
    assets = [_asset(f"a{i}", type_="character/part", role="character_part") for i in range(50)]
    assert classify_pack("SIDEKICK_SciFi_Soldiers", assets) == "characters"


def test_classify_pack_map_suffix():
    assets = [_asset(f"a{i}") for i in range(200)]
    assert classify_pack("POLYGON_SciFi_Outpost_Map", assets) == "map_demo"


def test_classify_pack_fx():
    assets = [_asset(f"a{i}", type_="fx", role="visual_effect") for i in range(80)]
    assert classify_pack("POLYGON_Particle_FX", assets) == "fx"


def test_classify_pack_environment_needs_size_and_role():
    big_no_role = [_asset(f"a{i}") for i in range(200)]  # all exterior_prop, no shell/ground
    assert classify_pack("POLYGON_Props_Only", big_no_role) == "addon"

    below_threshold = [_asset(f"a{i}") for i in range(148)] + [_asset("shell", role="building_shell")]
    assert len(below_threshold) == 149  # < 150 placeable -> addon
    assert classify_pack("POLYGON_Small_Kit", below_threshold) == "addon"

    at_threshold = [_asset(f"a{i}") for i in range(149)] + [_asset("shell", role="building_shell")]
    assert len(at_threshold) == 150  # >= 150 placeable + a shell -> environment
    assert classify_pack("POLYGON_Real_Kit", at_threshold) == "environment"


def test_classify_pack_default_catch_all_is_addon():
    assets = [_asset(f"a{i}", role="exterior_prop") for i in range(60)]  # 60 >= 40 but no env role
    assert classify_pack("POLYGON_Trinkets", assets) == "addon"


# --- role_counts / kit_families -----------------------------------------------


def test_role_counts_keys_by_semantic_role_falls_back_to_type():
    assets = [
        _asset("a", role="exterior_prop"),
        _asset("b", role="exterior_prop"),
        {"id": "c", "type": "weapon", "placeable": True, "module": {}, "files": {}},
    ]
    counts = role_counts(assets)
    assert counts == {"exterior_prop": 2, "weapon": 1}


def test_kit_families_unique_sorted_non_null():
    assets = [_asset("a", family="Base"), _asset("b", family="Bridge"), _asset("c", family=None), _asset("d", family="Base")]
    assert kit_families(assets) == ["Base", "Bridge"]


# --- settings table ------------------------------------------------------------


def test_load_settings_table_covers_all_126_real_catalogs_if_present():
    """Not a hard requirement for CI (catalogs may not be on this machine),
    but if they are, every cataloged pack_id must have a table entry --
    pack-profile refuses to guess (AC1 requires non-null setting)."""
    from synty_inventory.paths import ConfigError, load_config

    try:
        cfg = load_config(require=False)
    except ConfigError:
        pytest.skip("no config on this machine")
    catalogs_dir = cfg.get("catalogs")
    if catalogs_dir is None or not catalogs_dir.is_dir():
        pytest.skip("no real catalogs on this machine")
    from synty_inventory.paths import is_pack_catalog_file

    table = load_settings_table()
    real_ids = {p.stem for p in catalogs_dir.glob("*.json") if is_pack_catalog_file(p)}
    missing = real_ids - set(table)
    assert missing == set(), f"pack_settings.yaml is missing entries for {sorted(missing)}"


def test_setting_and_era_known_pack():
    setting, era = setting_and_era("POLYGON_SciFi_Worlds")
    assert setting == "scifi_frontier"
    assert era in ERAS
    assert setting in SETTINGS


def test_setting_and_era_unknown_pack_returns_none():
    assert setting_and_era("NOT_A_REAL_PACK") == (None, None)


# --- grammar_available ---------------------------------------------------------


def test_grammar_available_true_for_package_recipe_pack():
    assert grammar_available("POLYGON_Mech", None) is True  # mech_kit.json


def test_grammar_available_true_for_scene_grammar_sidecar(tmp_path: Path):
    (tmp_path / "POLYGON_Foo.scene_grammar.json").write_text("{}", encoding="utf-8")
    assert grammar_available("POLYGON_Foo", tmp_path) is True


def test_grammar_available_true_for_user_recipe(tmp_path: Path):
    recipes_dir = tmp_path / "recipes"
    recipes_dir.mkdir()
    (recipes_dir / "custom.json").write_text(
        json.dumps({"id": "custom", "packs": ["POLYGON_Foo"]}), encoding="utf-8"
    )
    assert grammar_available("POLYGON_Foo", tmp_path) is True


def test_grammar_available_false_when_nothing_matches(tmp_path: Path):
    assert grammar_available("POLYGON_Nothing_Here", tmp_path) is False
    assert grammar_available("POLYGON_Nothing_Here", None) is False


# --- godot_ready ----------------------------------------------------------------


def test_godot_ready_false_when_not_registered():
    assert godot_ready("POLYGON_Not_Registered_Ever", None) is False


def test_godot_ready_true_when_registered_and_no_root_configured():
    assert godot_ready("POLYGON_City", None) is True


def test_godot_ready_true_when_report_missing(tmp_path: Path):
    (tmp_path / "polygon-city-01").mkdir()
    assert godot_ready("POLYGON_City", tmp_path) is True


def test_godot_ready_true_when_report_clean(tmp_path: Path):
    pack_dir = tmp_path / "polygon-mech-01"
    pack_dir.mkdir()
    report = {"validate": {"import_exit_code": 0, "log_error_count": 0, "dangling_ref_count": 0}}
    (pack_dir / "conversion_report.json").write_text(json.dumps(report), encoding="utf-8")
    assert godot_ready("POLYGON_Mech", tmp_path) is True


def test_godot_ready_false_when_report_has_fatal_errors(tmp_path: Path):
    pack_dir = tmp_path / "polygon-mech-01"
    pack_dir.mkdir()
    report = {"validate": {"import_exit_code": 1, "log_error_count": 3, "dangling_ref_count": 0}}
    (pack_dir / "conversion_report.json").write_text(json.dumps(report), encoding="utf-8")
    assert godot_ready("POLYGON_Mech", tmp_path) is False


# --- characters_rig --------------------------------------------------------------


def test_characters_rig_sidekick():
    assert characters_rig("SIDEKICK_SciFi_Soldiers", []) == "sidekick"


def test_characters_rig_polygon_humanoid_when_placeable_character_present():
    assets = [_asset("BR_Hero", type_="character", role="character")]
    assert characters_rig("POLYGON_SciFi_City", assets) == "polygon_humanoid"


def test_characters_rig_none_when_no_character_type():
    assets = [_asset("a")]
    assert characters_rig("POLYGON_City", assets) is None


# --- palette --------------------------------------------------------------------


def test_measure_palette_none_without_catalogs_dir():
    assert measure_palette("POLYGON_Foo", None) == (None, "rules")


def test_measure_palette_none_without_preview_dir(tmp_path: Path):
    assert measure_palette("POLYGON_Foo", tmp_path) == (None, "rules")


def test_measure_palette_measured_from_preview_png(tmp_path: Path):
    from PIL import Image

    preview_dir = tmp_path / "previews" / "POLYGON_Foo"
    preview_dir.mkdir(parents=True)
    im = Image.new("RGB", (8, 8), color=(200, 50, 50))
    im.save(preview_dir / "asset_01.png")

    palette, prov = measure_palette("POLYGON_Foo", tmp_path)
    assert prov == "measured"
    assert palette is not None
    assert 0.0 <= palette["saturation"] <= 1.0
    assert 0.0 <= palette["brightness"] <= 1.0
    r, g, b = palette["dominant_rgb"][0]
    assert r > g and r > b  # a red swatch


# --- build_pack_profile (integration) --------------------------------------------


def _doc(pack_id, assets):
    return {"pack_id": pack_id, "assets": assets}


def test_build_pack_profile_schema_and_defaults():
    assets = [_asset(f"a{i}") for i in range(10)]
    profile = build_pack_profile(_doc("POLYGON_SciFi_Worlds", assets))
    assert profile["schema"] == "pack-profile/1"
    assert profile["pack_id"] == "POLYGON_SciFi_Worlds"
    assert profile["pack_class"] == "addon"  # < 40 assets
    assert profile["setting"] == "scifi_frontier"
    assert profile["era"] == "far_future"
    assert profile["palette"] is None
    assert profile["provenance"]["setting"] == "rules"
    assert profile["provenance"]["palette"] == "rules"
    assert set(profile["role_counts"]) == {"exterior_prop"}


def test_build_pack_profile_human_override_wins():
    assets = [_asset(f"a{i}") for i in range(10)]
    profile = build_pack_profile(
        _doc("POLYGON_SciFi_Worlds", assets),
        human_override={"setting": "post_apoc", "era": "near_future"},
    )
    assert profile["setting"] == "post_apoc"
    assert profile["era"] == "near_future"
    assert profile["provenance"]["setting"] == "human"
    assert profile["provenance"]["era"] == "human"


def test_build_pack_profile_vlm_refine_only_applies_valid_vocab():
    assets = [_asset(f"a{i}") for i in range(10)]

    def refine(pack_id, assets_):
        return {"setting": "not_a_real_setting", "era": "far_future"}

    profile = build_pack_profile(_doc("POLYGON_SciFi_Worlds", assets), vlm_refine=refine)
    assert profile["setting"] == "scifi_frontier"  # rejected: not in controlled vocab
    assert profile["provenance"]["setting"] == "rules"
    assert profile["era"] == "far_future"
    assert profile["provenance"]["era"] == "vlm"


def test_build_pack_profile_vlm_refine_none_stays_on_rules():
    assets = [_asset(f"a{i}") for i in range(10)]
    profile = build_pack_profile(_doc("POLYGON_SciFi_Worlds", assets), vlm_refine=lambda pid, a: None)
    assert profile["provenance"]["setting"] == "rules"
    assert profile["provenance"]["era"] == "rules"


def test_build_pack_profile_unknown_pack_id_reports_null_setting_era():
    assets = [_asset(f"a{i}") for i in range(10)]
    profile = build_pack_profile(_doc("POLYGON_Definitely_Not_In_Table", assets))
    assert profile["setting"] is None
    assert profile["era"] is None
