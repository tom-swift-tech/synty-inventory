"""Lead follow-ups after the W5 merge: numeric ``files.glb_scale`` in the schema (AC37), ``weapons build`` handing the
configured ``extracted_root`` to variant discovery (spec 3.7) and ``gauntlet --strict`` (AC30).

Each test fails against the code before the follow-up commit. Expected values are literals.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

_FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("wfx", _FIX / "wfx.py")
wfx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wfx)
_spec = importlib.util.spec_from_file_location("atlas_alt_helpers", _FIX / "atlas_alt" / "helpers.py")
AA = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(AA)

from synty_inventory.cli import main  # noqa: E402
from synty_inventory.weapons.directory import write_directory  # noqa: E402
from synty_inventory.weapons.schema import validate_directory, validate_record  # noqa: E402

_ENV = ("SYNTI_CONFIG", "SYNTI_UNITY_ROOT", "SYNTI_EXTRACTED_ROOT", "SYNTI_THREEJS_V2", "SYNTI_VIEWER_DATA",
        "SYNTI_CATALOGS", "SYNTI_GODOT_ROOT", "SYNTI_UNREAL_ROOT", "SYNTI_SYNTY_GLB_ROOT")


def _config(tmp_path: Path, catalogs: Path, extracted: Path) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text("\n".join([f'unity_root: "{tmp_path.as_posix()}/unity"', f'extracted_root: "{extracted.as_posix()}"',
                              f'catalogs: "{catalogs.as_posix()}"']) + "\n", encoding="utf-8")
    return cfg


def _clear_env(monkeypatch):
    for key in _ENV:
        monkeypatch.delenv(key, raising=False)


# --- AC37: a real glb_scale is a number, and the directory that carries it must still validate and write -----------------

def test_a_numeric_glb_scale_validates_and_writes(tmp_path):
    directory, excluded = wfx.build(wfx.make_catalogs_dir(tmp_path))
    directory = copy.deepcopy(directory)
    directory["weapons"][0]["files"]["glb_scale"] = 0.01
    assert validate_record(directory["weapons"][0]) == []
    assert validate_directory(directory) == []
    dpath, _ = write_directory(tmp_path / "out_catalogs", directory, excluded)
    assert json.loads(dpath.read_text(encoding="utf-8"))["weapons"][0]["files"]["glb_scale"] == 0.01


def test_a_boolean_or_object_files_value_is_still_rejected(tmp_path):
    directory, _ = wfx.build(wfx.make_catalogs_dir(tmp_path))
    for bad in ({"a": 1}, [1, 2]):
        rec = copy.deepcopy(directory["weapons"][0])
        rec["files"]["glb_scale"] = bad
        assert validate_record(rec) != [], bad


# --- weapons build uses the configured extracted_root --------------------------------------------------------------------

def test_cli_build_lists_variants_from_the_configured_extracted_root(tmp_path, monkeypatch, capsys):
    _clear_env(monkeypatch)
    import synty_inventory.packs.profile as profile

    monkeypatch.setattr(profile, "load_settings_table", lambda *a, **k: AA.PACK_SETTINGS)
    cat = AA.make_catalogs(tmp_path)
    cfg = _config(tmp_path, cat, AA.EXTRACTED)
    capsys.readouterr()
    code = main(["--config", str(cfg), "weapons", "build", "--no-geometry"])
    out = capsys.readouterr().out
    assert code == 0, out
    directory = json.loads((cat / "weapons" / "directory.json").read_text(encoding="utf-8"))
    by_id = {w["id"]: w for w in directory["weapons"]}
    sword = by_id["FAKE_AtlasAlt/SM_Wep_Sword_Atlas_01"]["visuals"]["variants"]
    assert [v["variant_id"] for v in sword] == ["A", "B", "C"]
    assert [v["is_default"] for v in sword] == [True, False, False]


# --- gauntlet --strict ---------------------------------------------------------------------------------------------------

def _gauntlet_calls(tmp_path, monkeypatch, capsys, argv):
    _clear_env(monkeypatch)
    cat = tmp_path / "catalogs"
    cat.mkdir()
    cfg = _config(tmp_path, cat, tmp_path / "extracted")
    seen = []

    def fake(catalogs_dir, **kw):
        seen.append(kw)
        return {"ok": True, "gates": []}

    monkeypatch.setattr("synty_inventory.cli.run_gauntlet", fake)
    capsys.readouterr()
    code = main(["--config", str(cfg), "gauntlet", *argv])
    capsys.readouterr()
    return code, seen


def test_gauntlet_strict_flag_reaches_run_gauntlet(tmp_path, monkeypatch, capsys):
    code, seen = _gauntlet_calls(tmp_path, monkeypatch, capsys, ["--strict"])
    assert code == 0 and len(seen) == 1 and seen[0]["strict"] is True


def test_gauntlet_is_not_strict_by_default(tmp_path, monkeypatch, capsys):
    code, seen = _gauntlet_calls(tmp_path, monkeypatch, capsys, [])
    assert code == 0 and len(seen) == 1 and seen[0]["strict"] is False



# --- the Alts textures of a pack may sit in Textures/Alt (singular) -----------------------------------------------------

def test_the_resolver_finds_an_atlas_in_a_singular_alt_textures_folder(tmp_path):
    from synty_inventory.weapons.variants import resolve_variant_texture

    mat = tmp_path / "Assets/Synty/PolyX/Materials/Alts/PolyX_01_B.mat"
    mat.parent.mkdir(parents=True)
    mat.write_text("%YAML 1.1", encoding="utf-8")
    tex = tmp_path / "Assets/Synty/PolyX/Textures/Alt/PolyX_01_B.png"
    tex.parent.mkdir(parents=True)
    tex.write_bytes(b"png")
    got = resolve_variant_texture(tmp_path, "Assets/Synty/PolyX/Materials/Alts/PolyX_01_B.mat")
    assert got == tex
