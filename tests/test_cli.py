import json
from pathlib import Path
from types import SimpleNamespace

from synty_inventory.catalog import write_catalog
from synty_inventory.cli import (
    _optional_root,
    _viewer,
    attach_extracted_previews,
    cmd_validate,
    emit_json,
    main,
)
from synty_inventory.paths import CONFIG_KEYS
from synty_inventory.schema import migrate_catalog, validate_catalog


class _LegacyStdout:
    """Mimic a Windows console that cannot encode arrows."""

    def __init__(self, encoding: str = "cp1252"):
        self.encoding = encoding
        self.chunks: list[str] = []

    def write(self, text: str) -> int:
        text.encode(self.encoding)
        self.chunks.append(text)
        return len(text)


def test_emit_json_survives_legacy_console():
    stream = _LegacyStdout("cp1252")
    emit_json({"detail": "police->x; note: cafe\u2192bar"}, stream)
    assert stream.chunks
    joined = "".join(stream.chunks)
    assert "police" in joined


def test_validate_missing_dir_fails(tmp_path: Path, capsys):
    missing = tmp_path / "no-such-catalogs"
    code = cmd_validate(SimpleNamespace(out=missing, pack=None), {})
    assert code != 0
    err = capsys.readouterr().err
    assert "not found" in err


def test_validate_empty_dir_fails(tmp_path: Path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    code = cmd_validate(SimpleNamespace(out=empty, pack=None), {})
    assert code != 0
    err = capsys.readouterr().err
    assert "no catalogs" in err


def test_attach_extracted_previews_overwrites_placeholder(tmp_path: Path):
    dest = tmp_path / "previews" / "FakePack"
    dest.mkdir(parents=True)
    written = dest / "SM_Prop_Sign_Police_01.png"
    written.write_bytes(b"png")
    assets = [
        {
            "id": "SM_Prop_Sign_Police_01",
            "thumbnail": "previews/SM_Prop_Sign_Police_01.png",
        }
    ]
    attach_extracted_previews(assets, [str(written)], tmp_path)
    assert assets[0]["thumbnail"] == "previews/FakePack/SM_Prop_Sign_Police_01.png"


# --- optional roots (H2) and command surface (M4) --------------------------------


def _clear_synti_env(monkeypatch):
    monkeypatch.delenv("SYNTI_CONFIG", raising=False)
    for env in CONFIG_KEYS.values():
        monkeypatch.delenv(env, raising=False)


def _write_config(path: Path, **keys: str) -> Path:
    lines = [f'{k}: "{v}"' for k, v in keys.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _tiny_city_catalog(catalogs: Path) -> Path:
    city = migrate_catalog(
        {
            "pack_id": "POLYGON_City",
            "engine": "Unity",
            "origin": "Synty",
            "style": "lowpoly_modern_city",
            "units": "meters",
            "version": 1,
            "scanned_at": "2026-08-18T00:00:00+00:00",
            "assets": [
                {
                    "id": "SM_Prop_Sign_Police_01",
                    "name": "Police Sign",
                    "type": "prop/signage",
                    "category": ["sign"],
                    "tags": ["police", "facade", "station"],
                    "description": "Police station identity plaque " + "x" * 80,
                    "semantic_role": "identifies_building_as_police_station",
                    "placement": {
                        "mount": "wall",
                        "height": "eye_level",
                        "orientation": "outward_facing",
                        "attachment": "back_side",
                        "preferred_floors": [1, 2],
                        "constraints": ["exterior_only"],
                        "preferred_contexts": ["police_station"],
                    },
                    "dimensions": {"approx": [1.0, 0.6, 0.1], "units": "meters"},
                    "paths": {
                        "prefab": "Prefabs/Props/SM_Prop_Sign_Police_01.prefab",
                        "mesh": None,
                        "materials": [],
                    },
                    "thumbnail": None,
                    "ai_notes": "Use on the matching facade. " + "y" * 20,
                }
            ],
        }
    )
    assert validate_catalog(city) == []
    dest = catalogs / "POLYGON_City.json"
    write_catalog(dest, city)
    return dest


def test_optional_root_missing_path_returns_none(tmp_path: Path):
    missing = tmp_path / "no-such-viewer"
    cfg = {"viewer_data": missing}
    assert _optional_root(cfg, "viewer_data") is None
    assert _viewer(cfg) is None


def test_optional_root_existing_path_returns_it(tmp_path: Path):
    root = tmp_path / "viewer_data"
    root.mkdir()
    cfg = {"viewer_data": root}
    assert _optional_root(cfg, "viewer_data") == root
    assert _viewer(cfg) == root


def test_optional_root_unset_returns_none():
    assert _optional_root({}, "viewer_data") is None
    assert _viewer({}) is None


def test_cmd_recipes_missing_viewer_data_still_lists_package_recipes(tmp_path: Path, monkeypatch, capsys):
    """A configured-but-missing viewer_data must behave as unset (H2)."""
    _clear_synti_env(monkeypatch)
    unity = tmp_path / "unity"
    extracted = tmp_path / "extracted"
    catalogs = tmp_path / "catalogs"
    unity.mkdir()
    extracted.mkdir()
    catalogs.mkdir()
    cfg = _write_config(
        tmp_path / "config.yaml",
        unity_root=str(unity).replace("\\", "/"),
        extracted_root=str(extracted).replace("\\", "/"),
        catalogs=str(catalogs).replace("\\", "/"),
        viewer_data=str(tmp_path / "ghost-viewer").replace("\\", "/"),
    )
    code = main(["--config", str(cfg), "--out", str(catalogs), "recipes"])
    assert code == 0
    rows = json.loads(capsys.readouterr().out)
    ids = {r["id"] for r in rows}
    assert "ship_kit" in ids


def test_main_config_exit_codes(tmp_path: Path, monkeypatch, capsys):
    _clear_synti_env(monkeypatch)
    incomplete = _write_config(tmp_path / "partial.yaml", threejs_v2="C:/optional")
    assert main(["--config", str(incomplete), "config"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert "paths" in payload

    unity = tmp_path / "unity"
    extracted = tmp_path / "extracted"
    catalogs = tmp_path / "catalogs"
    unity.mkdir()
    extracted.mkdir()
    catalogs.mkdir()
    complete = _write_config(
        tmp_path / "full.yaml",
        unity_root=str(unity).replace("\\", "/"),
        extracted_root=str(extracted).replace("\\", "/"),
        catalogs=str(catalogs).replace("\\", "/"),
    )
    assert main(["--config", str(complete), "config"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["paths"]["unity_root"]["exists"] is True
    assert payload["paths"]["catalogs"]["exists"] is True


def test_main_search_details_recipe(tmp_path: Path, monkeypatch, capsys):
    _clear_synti_env(monkeypatch)
    unity = tmp_path / "unity"
    extracted = tmp_path / "extracted"
    catalogs = tmp_path / "catalogs"
    unity.mkdir()
    extracted.mkdir()
    catalogs.mkdir()
    _tiny_city_catalog(catalogs)
    cfg = _write_config(
        tmp_path / "config.yaml",
        unity_root=str(unity).replace("\\", "/"),
        extracted_root=str(extracted).replace("\\", "/"),
        catalogs=str(catalogs).replace("\\", "/"),
    )

    code = main(["--config", str(cfg), "--out", str(catalogs), "search", "police"])
    assert code == 0
    hits = json.loads(capsys.readouterr().out)
    assert hits[0]["id"] == "SM_Prop_Sign_Police_01"
    assert hits[0]["pack"] == "POLYGON_City"
    assert "file" in hits[0]

    code = main(["--config", str(cfg), "--out", str(catalogs), "details", "SM_Prop_Sign_Police_01"])
    assert code == 0
    rec = json.loads(capsys.readouterr().out)
    assert rec["id"] == "SM_Prop_Sign_Police_01"

    code = main(["--config", str(cfg), "--out", str(catalogs), "details", "NO_SUCH_ASSET"])
    assert code == 3
    capsys.readouterr()

    code = main(["--config", str(cfg), "--out", str(catalogs), "recipe", "ship_kit"])
    assert code == 4
    out = json.loads(capsys.readouterr().out)
    assert out["complete"] is False


def test_scan_and_enrich_warn_unmapped_engine_folders(tmp_path: Path, capsys, monkeypatch):
    """cmd_scan/cmd_enrich must actually invoke the godot/unreal warning
    helpers — pins the operator-visibility guarantee, not just the
    underlying sources.* functions."""
    from synty_inventory.cli import cmd_enrich, cmd_scan
    from synty_inventory.sources import unreal

    unity = tmp_path / "unity"
    catalogs = tmp_path / "catalogs"
    godot_root = tmp_path / "godot"
    unreal_root = tmp_path / "unreal"
    for d in (unity, catalogs, godot_root, unreal_root):
        d.mkdir()
    (godot_root / "polygon-scifi-city-02").mkdir()
    (unreal_root / "polygon-city-01").mkdir()
    (unreal_root / "POLYGON_City").mkdir()
    (unreal_root / "unreal-city").mkdir()
    monkeypatch.setitem(unreal.SLUG_PACK_OVERRIDES, "unreal-city", "POLYGON_City")

    cfg = {
        "unity_root": unity,
        "catalogs": catalogs,
        "godot_root": godot_root,
        "unreal_root": unreal_root,
    }
    args = SimpleNamespace(index=False, path=None, pack=None, out=None)

    assert cmd_scan(args, cfg) != 0  # no packs under the empty unity root
    err = capsys.readouterr().err
    assert "unmapped Godot export folder 'polygon-scifi-city-02'" in err
    assert "unmapped Unreal export folder 'polygon-city-01'" in err
    assert "collide on pack_id 'POLYGON_City'" in err
    assert "kept 'unreal-city', skipped 'POLYGON_City'" in err

    assert cmd_enrich(args, cfg) != 0  # no catalogs to enrich
    err = capsys.readouterr().err
    assert "unmapped Godot export folder" in err
    assert "unmapped Unreal export folder" in err
    assert "collide on pack_id 'POLYGON_City'" in err
