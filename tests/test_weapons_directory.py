"""Weapon directory W1: record shape, schema, ids across packs, and the ``weapons`` CLI verbs.

Covers AC7, AC10 and the CLI contract of docs/weapon_directory.md section 3.2. Enum lists below are literals
(spec 4.6), not imports of the constants under test.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("wfx", Path(__file__).parent / "fixtures" / "weapons" / "wfx.py")
wfx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wfx)

from synty_inventory.cli import build_parser, main  # noqa: E402
from synty_inventory.weapons.schema import validate_directory, validate_record  # noqa: E402

ROLES = {"whole", "part", "ammo", "carrier", "emplaced"}
KINDS = {"ranged", "melee", "thrown", "shield", None}
ARCHETYPES = {
    "pistol", "revolver", "smg", "rifle", "shotgun", "sniper", "lmg", "heavy_gun", "launcher", "flamethrower",
    "bow", "crossbow", "utility_gun", "knife", "sword", "axe", "mace", "hammer", "club", "spear", "polearm",
    "staff", "wand", "whip", "fist_weapon", "tool", "grenade", "bomb", "mine", "throwing_blade", "shield",
    "turret", "cannon", "siege_engine", "mortar", "unknown",
}
HOLDS = {"one_hand", "long_gun", "melee_one", "melee_two", "melee_bat", "bow", "crossbow", "thrown", "shield", "none"}
GENRES = {"modern", "scifi", "fantasy", "western", "other"}
GENRE_SOURCES = {"pack", "archetype", "override"}
STATUSES = {"auto", "reviewed", "overridden"}
FLAGS = {
    "token_candidate", "preset", "prefab_only", "shared_glb_node", "mech_scale", "origin_outside_bounds",
    "forward_by_fallback", "unmeasured", "duplicate_mesh", "needs_scale_check",
}
SOURCES = {"catalog", "name_token"}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return wfx.build(wfx.make_catalogs_dir(tmp_path_factory.mktemp("dir")))


# --- AC7 ---------------------------------------------------------------------------------------------------

def test_ac7_five_stems_over_three_packs_give_fifteen_distinct_records(built):
    directory, _ = built
    group = wfx.expected()["stem_group"]
    assert len(group["packs"]) == 3 and len(group["stems"]) == 5
    ids = [f"{p}/{s}" for p in group["packs"] for s in group["stems"]]
    assert len(ids) == len(set(ids)) == 15
    by_id = wfx.records_by_id(directory)
    assert all(i in by_id for i in ids)
    all_ids = [w["id"] for w in directory["weapons"]]
    assert len(all_ids) == len(set(all_ids))  # 0 id collisions overall
    for stem in group["stems"]:
        owners = [w["pack"] for w in directory["weapons"] if w["asset_id"] == stem]
        assert len(owners) == len(set(owners)) >= 3  # one record per owning pack, never merged
        assert set(group["packs"]) <= set(owners)


def test_ac7_show_of_a_bare_stem_exits_2_listing_the_qualified_ids(tmp_path, monkeypatch, capsys):
    cat = _built_catalogs(tmp_path, monkeypatch, capsys)
    code, out = _run(tmp_path, capsys, ["weapons", "show", "SM_Wep_Pistol_01"])
    assert code == 2
    assert out["ok"] is False
    assert "ambiguous" in out["error"]
    assert out["candidates"] == [
        "FAKE_Fantasy/SM_Wep_Pistol_01", "FAKE_Generic/SM_Wep_Pistol_01", "FAKE_Modern/SM_Wep_Pistol_01",
        "FAKE_SciFi/SM_Wep_Pistol_01",
    ]
    assert all(c.endswith("/SM_Wep_Pistol_01") for c in out["candidates"])
    assert len(out["candidates"]) >= 3
    assert (cat / "weapons" / "directory.json").is_file()


# --- AC10 --------------------------------------------------------------------------------------------------

def test_ac10_every_enum_field_is_closed(built):
    directory, _ = built
    for rec in directory["weapons"]:
        assert rec["role"] in ROLES, rec["id"]
        assert rec["kind"] in KINDS, rec["id"]
        assert rec["archetype"] in ARCHETYPES, rec["id"]
        assert rec["hold_class"] in HOLDS, rec["id"]
        assert rec["genre"] in GENRES, rec["id"]
        assert rec["genre_source"] in GENRE_SOURCES, rec["id"]
        assert rec["review"]["status"] in STATUSES, rec["id"]
        assert rec["review"]["candidate_source"] in SOURCES, rec["id"]
        assert set(rec["flags"]) <= FLAGS, rec["id"]
        assert rec["flags"] == sorted(rec["flags"])
        assert rec["schema_version"] == 1


def test_ac10_the_built_documents_validate_clean(built):
    directory, excluded = built
    assert validate_directory(directory, excluded) == []
    for rec in directory["weapons"]:
        assert validate_record(rec) == []
    assert directory["schema"] == "weapon-directory/1"
    assert excluded["schema"] == "weapon-excluded/1"
    assert [w["id"] for w in directory["weapons"]] == sorted(w["id"] for w in directory["weapons"])
    assert [e["id"] for e in excluded["excluded"]] == sorted(e["id"] for e in excluded["excluded"])


def test_ac10_a_hints_damage_key_fails_validation(built):
    directory, excluded = built
    bad = copy.deepcopy(directory)
    bad["weapons"][0]["hints"]["damage"] = 12
    errors = validate_directory(bad, excluded)
    assert errors and any("damage" in e for e in errors)
    rec = copy.deepcopy(directory["weapons"][0])
    assert validate_record(rec) == []
    rec["hints"]["damage"] = 12
    assert validate_record(rec)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.__setitem__("archetype", "laser_pistol"),
        lambda r: r.__setitem__("role", "gizmo"),
        lambda r: r.__setitem__("genre", "steampunk"),
        lambda r: r.__setitem__("hold_class", "two_hand"),
        lambda r: r["review"].__setitem__("status", "approved"),
        lambda r: r["review"].__setitem__("confidence", 1.7),
        lambda r: r["flags"].append("shiny"),
        lambda r: r.__setitem__("flags", ["unmeasured", "preset"]),  # unsorted
        lambda r: r.__setitem__("extra_field", 1),
        lambda r: r.__setitem__("geometry", {}),  # measured but flag unmeasured is set
        lambda r: r.__setitem__("id", "no_slash"),
        lambda r: r.__setitem__("kind", "melee") if r["role"] in ("part", "ammo", "carrier") else r.__setitem__("kind", "gizmo"),
    ],
)
def test_ac10_invalid_records_are_rejected(built, mutate):
    directory, _ = built
    rec = copy.deepcopy(next(w for w in directory["weapons"] if w["role"] == "whole" and w["flags"] == ["unmeasured"]))
    assert validate_record(rec) == []
    mutate(rec)
    assert validate_record(rec) != []


def test_document_level_violations_are_reported(built):
    directory, excluded = built
    dup = copy.deepcopy(directory)
    dup["weapons"].append(copy.deepcopy(dup["weapons"][0]))
    assert any("duplicate" in e or "sorted" in e for e in validate_directory(dup, excluded))

    unsorted = copy.deepcopy(directory)
    unsorted["weapons"].reverse()
    assert any("sorted" in e for e in validate_directory(unsorted, excluded))

    also_excluded = copy.deepcopy(excluded)
    also_excluded["excluded"].append({"id": directory["weapons"][0]["id"], "reason": "scenery", "matched": "x",
                                      "source": "catalog"})
    assert any("INV-3" in e for e in validate_directory(directory, also_excluded))

    renamed = copy.deepcopy(directory)
    renamed["weapons"][0]["renamed_from"] = [renamed["weapons"][1]["id"]]
    assert any("live record id" in e for e in validate_directory(renamed, excluded))

    skewed = copy.deepcopy(directory)
    skewed["packs"][0]["records"] += 1
    assert validate_directory(skewed, excluded)


# --- record content ----------------------------------------------------------------------------------------

def test_role_sub_objects_appear_exactly_for_their_role(built):
    directory, _ = built
    roles = set()
    for rec in directory["weapons"]:
        roles.add(rec["role"])
        assert (rec["component"] is not None) == (rec["role"] == "part")
        assert (rec["carrier"] is not None) == (rec["role"] == "carrier")
        assert (rec["ammo"] is not None) == (rec["role"] == "ammo")
        if rec["role"] in ("part", "ammo", "carrier"):
            assert rec["kind"] is None
    assert roles == {"whole", "part", "ammo", "carrier", "emplaced"}


def test_duplicate_mesh_points_at_the_first_record_sharing_the_glb(built):
    directory, _ = built
    dups = [w for w in directory["weapons"] if w["duplicate_of"]]
    assert len(dups) >= 1
    by_id = wfx.records_by_id(directory)
    for rec in dups:
        first = by_id[rec["duplicate_of"]]
        assert first["duplicate_of"] is None
        assert first["files"]["glb"] == rec["files"]["glb"]
        assert first["id"] < rec["id"]
        assert "duplicate_mesh" in rec["flags"]
        assert "duplicate_mesh" not in first["flags"]
    assert {w["id"]: w["duplicate_of"] for w in dups} == {
        i: w["duplicate_of"] for i, w in wfx.expected()["weapons"].items() if w["duplicate_of"]
    }


def test_directory_header_and_pack_rows(built):
    directory, _ = built
    assert directory["weapon_version"] == 1
    assert directory["geometry_version"] == 3
    assert len(directory["rules_digest"]) == 16 and len(directory["overrides_digest"]) == 16
    assert [p["pack"] for p in directory["packs"]] == sorted(p["pack"] for p in directory["packs"])
    assert {p["pack"] for p in directory["packs"]} == {
        "FAKE_Fantasy", "FAKE_Generic", "FAKE_Mech", "FAKE_Modern", "FAKE_SciFi",
    }
    assert sum(directory["counts"]["by_role"].values()) == len(directory["weapons"])
    assert sum(directory["counts"]["by_archetype"].values()) == len(directory["weapons"])
    assert sum(directory["counts"]["by_status"].values()) == len(directory["weapons"])
    assert "scanned_at" in directory["packs"][0]


# --- CLI ---------------------------------------------------------------------------------------------------

def _clear_env(monkeypatch):
    for key in ("SYNTI_CONFIG", "SYNTI_UNITY_ROOT", "SYNTI_EXTRACTED_ROOT", "SYNTI_THREEJS_V2", "SYNTI_VIEWER_DATA",
                "SYNTI_CATALOGS", "SYNTI_GODOT_ROOT", "SYNTI_UNREAL_ROOT", "SYNTI_SYNTY_GLB_ROOT"):
        monkeypatch.delenv(key, raising=False)


def _write_config(tmp_path: Path, catalogs_dir: Path) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "\n".join([f'unity_root: "{tmp_path.as_posix()}/unity"', f'extracted_root: "{tmp_path.as_posix()}/extracted"',
                   f'catalogs: "{catalogs_dir.as_posix()}"']) + "\n", encoding="utf-8")
    return cfg


def _run(tmp_path, capsys, argv):
    capsys.readouterr()
    code = main(["--config", str(tmp_path / "config.yaml"), *argv])
    return code, json.loads(capsys.readouterr().out)


def _built_catalogs(tmp_path, monkeypatch, capsys, pack_settings_file=True):
    """Fixture catalogs + config + a full ``weapons build``; the pack_settings table is patched to the fixture's."""
    _clear_env(monkeypatch)
    cat = wfx.make_catalogs_dir(tmp_path)
    _write_config(tmp_path, cat)
    import synty_inventory.packs.profile as profile

    monkeypatch.setattr(profile, "load_settings_table", lambda *a, **k: wfx.pack_settings())
    code, out = _run(tmp_path, capsys, ["weapons", "build"])
    assert code == 0, out
    return cat


def test_cli_build_writes_directory_and_excluded_under_weapons_only(tmp_path, monkeypatch, capsys):
    _clear_env(monkeypatch)
    cat = wfx.make_catalogs_dir(tmp_path)
    _write_config(tmp_path, cat)
    import synty_inventory.packs.profile as profile

    monkeypatch.setattr(profile, "load_settings_table", lambda *a, **k: wfx.pack_settings())
    before = {p.name for p in cat.iterdir()}
    code, out = _run(tmp_path, capsys, ["weapons", "build"])
    assert code == 0 and out["ok"] is True
    assert {p.name for p in cat.iterdir()} == before | {"weapons"}
    assert sorted(p.name for p in (cat / "weapons").iterdir()) == ["directory.json", "excluded.json"]
    report = out["report"]
    assert report["records"] == 147 and report["excluded"] == 22
    assert report["packs_built"] == sorted(report["packs_built"]) and len(report["packs_built"]) == 5
    assert report["stale_overrides"] == []
    raw = (cat / "weapons" / "directory.json").read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    doc = json.loads(raw)
    assert validate_directory(doc, json.loads((cat / "weapons" / "excluded.json").read_bytes())) == []


def test_cli_build_report_file_and_coverage_gate(tmp_path, monkeypatch, capsys):
    _clear_env(monkeypatch)
    cat = wfx.make_catalogs_dir(tmp_path)
    _write_config(tmp_path, cat)
    rpt = tmp_path / "out" / "report.json"
    code, out = _run(tmp_path, capsys, ["weapons", "build", "--report", str(rpt), "--no-geometry"])
    assert code == 0
    assert json.loads(rpt.read_text(encoding="utf-8"))["records"] == out["report"]["records"]
    # W1 measures no geometry, so any positive coverage target is missed: exit 4
    code, out = _run(tmp_path, capsys, ["weapons", "build", "--min-coverage", "0.9"])
    assert code == 4
    assert out["ok"] is False
    assert (cat / "weapons" / "directory.json").is_file()  # the build itself still completed


def test_cli_show_and_list(tmp_path, monkeypatch, capsys):
    _built_catalogs(tmp_path, monkeypatch, capsys)
    code, out = _run(tmp_path, capsys, ["weapons", "show", "FAKE_Modern/SM_Wep_Pistol_01"])
    assert code == 0 and out["ok"] is True
    assert out["weapon"]["archetype"] == "pistol" and out["weapon"]["geometry"] is None
    code, out = _run(tmp_path, capsys, ["weapons", "show", "SM_Wep_Ballista_02"])  # unique bare id resolves
    assert code == 0 and out["weapon"]["id"] == "FAKE_Fantasy/SM_Wep_Ballista_02"
    code, out = _run(tmp_path, capsys, ["weapons", "show", "FAKE_Modern/Nope_01"])
    assert code == 2 and out["ok"] is False
    code, out = _run(tmp_path, capsys, ["weapons", "show", "Nope_01"])
    assert code == 2

    code, out = _run(tmp_path, capsys, ["weapons", "list"])
    assert code == 0 and out["total"] == 147 and out["count"] == 147
    assert [w["id"] for w in out["weapons"]] == sorted(w["id"] for w in out["weapons"])
    code, out = _run(tmp_path, capsys, ["weapons", "list", "--archetype", "pistol", "--pack", "FAKE_Modern,FAKE_SciFi"])
    assert code == 0 and out["total"] >= 2
    assert all(w["archetype"] == "pistol" and w["id"].split("/")[0] in ("FAKE_Modern", "FAKE_SciFi") for w in out["weapons"])
    code, out = _run(tmp_path, capsys, ["weapons", "list", "--kind", "shield", "--limit", "2"])
    assert out["count"] == 2 and out["total"] > 2
    code, out = _run(tmp_path, capsys, ["weapons", "list", "--max-confidence", "0.3"])
    assert code == 0 and out["total"] >= 1 and all(w["confidence"] <= 0.3 for w in out["weapons"])
    code, out = _run(tmp_path, capsys, ["weapons", "list", "--status", "reviewed"])
    assert out["total"] == 0


def test_cli_show_without_a_directory_exits_2(tmp_path, monkeypatch, capsys):
    _clear_env(monkeypatch)
    _write_config(tmp_path, wfx.make_catalogs_dir(tmp_path))
    code, out = _run(tmp_path, capsys, ["weapons", "show", "FAKE_Modern/SM_Wep_Pistol_01"])
    assert code == 2 and "weapons build" in out["error"]


def test_cli_validate_checks_the_built_directory(tmp_path, monkeypatch, capsys):
    cat = _built_catalogs(tmp_path, monkeypatch, capsys)
    code, out = _run(tmp_path, capsys, ["weapons", "validate"])
    assert code == 0 and out["ok"] is True and out["directory"] == "ok"
    path = cat / "weapons" / "directory.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["weapons"][0]["hints"]["damage"] = 3
    path.write_text(json.dumps(doc), encoding="utf-8")
    code, out = _run(tmp_path, capsys, ["weapons", "validate"])
    assert code == 6 and out["ok"] is False and out["directory"] == "invalid"
    assert any("damage" in e for e in out["directory_errors"])
    code, out = _run(tmp_path, capsys, ["weapons", "validate", "--directory", str(tmp_path / "absent.json")])
    assert code == 2


def test_cli_partial_pack_build_merges_into_the_existing_directory(tmp_path, monkeypatch, capsys):
    cat = _built_catalogs(tmp_path, monkeypatch, capsys)
    full = (cat / "weapons" / "directory.json").read_bytes()
    full_excl = (cat / "weapons" / "excluded.json").read_bytes()
    code, out = _run(tmp_path, capsys, ["weapons", "build", "--pack", "FAKE_Modern"])
    assert code == 0, out
    assert out["report"]["packs_built"] == ["FAKE_Modern"]
    assert (cat / "weapons" / "directory.json").read_bytes() == full  # same result as the full build
    assert (cat / "weapons" / "excluded.json").read_bytes() == full_excl
    code, out = _run(tmp_path, capsys, ["weapons", "build", "--pack", "FAKE_Nope"])
    assert code == 2 and "FAKE_Nope" in out["error"]


def test_cli_partial_build_without_an_existing_directory_exits_2(tmp_path, monkeypatch, capsys):
    _clear_env(monkeypatch)
    cat = wfx.make_catalogs_dir(tmp_path)
    _write_config(tmp_path, cat)
    code, out = _run(tmp_path, capsys, ["weapons", "build", "--pack", "FAKE_Modern"])
    assert code == 2 and not (cat / "weapons").exists()


def test_cli_build_on_a_missing_or_empty_catalogs_dir_exits_2(tmp_path, monkeypatch, capsys):
    _clear_env(monkeypatch)
    _write_config(tmp_path, tmp_path / "no_such_dir")
    code, out = _run(tmp_path, capsys, ["weapons", "build"])
    assert code == 2 and out["ok"] is False
    empty = tmp_path / "empty"
    empty.mkdir()
    _write_config(tmp_path, empty)
    code, out = _run(tmp_path, capsys, ["weapons", "build"])
    assert code == 2


def test_cli_unreadable_catalog_exits_2_and_writes_nothing(tmp_path, monkeypatch, capsys):
    _clear_env(monkeypatch)
    cat = wfx.make_catalogs_dir(tmp_path)
    (cat / "FAKE_Broken.json").write_text("{ not json", encoding="utf-8")
    _write_config(tmp_path, cat)
    code, out = _run(tmp_path, capsys, ["weapons", "build"])
    assert code == 2 and "FAKE_Broken" in out["error"]
    assert not (cat / "weapons").exists()


def test_parser_registers_the_whole_verb_group():
    parser = build_parser()
    for argv in (
        ["weapons", "build", "--pack", "A,B", "--rebuild", "--no-geometry", "--report", "r.json",
         "--min-coverage", "0.97", "--strict"],
        ["weapons", "show", "A/B"],
        ["weapons", "list", "--kind", "ranged", "--role", "whole", "--archetype", "rifle", "--genre", "modern",
         "--status", "auto", "--max-confidence", "0.5", "--limit", "5"],
        ["weapons", "icons", "--ids", "A/B", "--size", "64", "--rebuild", "--variants"],
        ["weapons", "review", "--out", "d", "--only-unreviewed", "--max-confidence", "0.5"],
        ["weapons", "apply-corrections", "f.json", "--dry-run"],
        ["weapons", "export", "--game", "g", "--packs", "A", "--out", "o.json", "--roles", "whole", "--engine", "godot",
         "--frame", "item", "--icons-dir", "i", "--profile", "public"],
        ["weapons", "validate", "--directory", "d.json"],
    ):
        assert parser.parse_args(argv).func is not None


def test_weapons_out_options_do_not_collide_with_the_global_out():
    parser = build_parser()
    args = parser.parse_args(["--out", "global_dir", "weapons", "export", "--game", "g", "--packs", "A", "--out", "snap.json"])
    assert str(args.out) == "global_dir"
    assert args.export_out == "snap.json"
    args = parser.parse_args(["--out", "global_dir", "weapons", "review", "--out", "page_dir"])
    assert str(args.out) == "global_dir" and args.review_out == "page_dir"


def test_the_global_out_option_still_picks_the_catalogs_directory(tmp_path, monkeypatch, capsys):
    _clear_env(monkeypatch)
    cat = wfx.make_catalogs_dir(tmp_path)
    cfg = _write_config(tmp_path, tmp_path / "config_catalogs_unused")
    capsys.readouterr()
    code = main(["--config", str(cfg), "--out", str(cat), "weapons", "build"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0, out
    assert (cat / "weapons" / "directory.json").is_file()


# --- asset ids with spaces ---------------------------------------------------------------------------------
# Real Synty ids can contain a space ("POLYGON_War_Map/FX_Bullet_Trail 1"). The id is `<pack>/<asset_id>`: the
# pack part has no whitespace or slash, the asset part has no slash but may hold spaces.

SPACED_ASSET = "SM_Wep_Sword_02 1"
SPACED_ID = "FAKE_Fantasy/SM_Wep_Sword_02 1"
SPACED_OLD = "FAKE_Fantasy/SM_Wep_Sword_02 0"


def _catalogs_with_a_spaced_asset(tmp_path):
    cat = wfx.make_catalogs_dir(tmp_path)
    path = cat / "FAKE_Fantasy.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    base = next(a for a in doc["assets"] if a["id"] == "SM_Wep_Sword_02")
    clone = json.loads(json.dumps(base).replace("SM_Wep_Sword_02", SPACED_ASSET).replace("SM Wep Sword 02", SPACED_ASSET))
    doc["assets"].append(clone)
    doc["asset_count"] = len(doc["assets"])
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return cat


def test_asset_ids_with_a_space_build_validate_and_keep_the_space(tmp_path):
    cat = _catalogs_with_a_spaced_asset(tmp_path)
    ovr_doc = wfx.overrides_doc(ids={SPACED_ID: {"renamed_from": [SPACED_OLD]}})
    directory, excluded = wfx.build(cat, overrides=ovr_doc)  # schema-validates internally; raises on any violation
    rec = wfx.records_by_id(directory)[SPACED_ID]
    assert rec["asset_id"] == SPACED_ASSET and rec["pack"] == "FAKE_Fantasy"
    assert rec["renamed_from"] == [SPACED_OLD]
    assert validate_record(rec) == []
    assert validate_directory(directory, excluded) == []
    # the whole-id shape stays strict: a space in the pack part, a missing or doubled slash, an empty half
    for bad in ("FAKE Fantasy/x", "FAKE_Fantasy/", "/x", "FAKE_Fantasy", "FAKE_Fantasy/a/b"):
        broken = copy.deepcopy(rec)
        broken["id"] = bad
        assert validate_record(broken) != [], bad


def test_cli_show_finds_an_asset_id_with_a_space(tmp_path, monkeypatch, capsys):
    _clear_env(monkeypatch)
    cat = _catalogs_with_a_spaced_asset(tmp_path)
    _write_config(tmp_path, cat)
    import synty_inventory.packs.profile as profile

    monkeypatch.setattr(profile, "load_settings_table", lambda *a, **k: wfx.pack_settings())
    code, out = _run(tmp_path, capsys, ["weapons", "build"])
    assert code == 0, out
    code, out = _run(tmp_path, capsys, ["weapons", "show", SPACED_ID])
    assert code == 0 and out["weapon"]["id"] == SPACED_ID
    code, out = _run(tmp_path, capsys, ["weapons", "show", SPACED_ASSET])  # the bare asset id (with its space) too
    assert code == 0 and out["weapon"]["id"] == SPACED_ID
    code, out = _run(tmp_path, capsys, ["weapons", "validate"])
    assert code == 0, out
