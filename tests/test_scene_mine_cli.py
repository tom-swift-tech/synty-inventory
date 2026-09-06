"""AC16 (miner half): the ``scene-mine`` subcommand end-to-end through
``cli.main`` -- exit codes and the on-disk grammar file."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures" / "scene_mine"))

import build_fixture  # noqa: E402

from synty_inventory.cli import main  # noqa: E402
from synty_inventory.paths import CONFIG_KEYS  # noqa: E402


def _clear_synti_env(monkeypatch):
    monkeypatch.delenv("SYNTI_CONFIG", raising=False)
    for env in CONFIG_KEYS.values():
        monkeypatch.delenv(env, raising=False)


def _write_config(path: Path, **keys: str) -> Path:
    lines = [f'{k}: "{v}"' for k, v in keys.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def fixture_env(tmp_path: Path, monkeypatch):
    _clear_synti_env(monkeypatch)
    info = build_fixture.build(tmp_path / "extracted")
    catalogs = tmp_path / "catalogs"
    catalogs.mkdir()
    (catalogs / f"{build_fixture.PACK_ID}.json").write_text(json.dumps(info["catalog"]), encoding="utf-8")
    cfg = _write_config(
        tmp_path / "config.yaml",
        unity_root=str(tmp_path / "unity").replace("\\", "/"),
        extracted_root=str(tmp_path / "extracted_root_unused").replace("\\", "/"),
        catalogs=str(catalogs).replace("\\", "/"),
    )
    return {"info": info, "catalogs": catalogs, "cfg": cfg, "tmp_path": tmp_path}


def test_scene_mine_success_writes_grammar(fixture_env, capsys):
    info, cfg = fixture_env["info"], fixture_env["cfg"]
    out_dir = fixture_env["tmp_path"] / "sg_out"
    code = main(
        [
            "--config",
            str(cfg),
            "scene-mine",
            "--pack",
            build_fixture.PACK_ID,
            "--scene",
            str(info["demo_scene"]),
            "--out",
            str(out_dir),
        ]
    )
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["schema"] == "scene-mine-report/1"
    assert report["resolve_rate"] == 1.0
    dest = out_dir / f"{build_fixture.PACK_ID}.scene_grammar.json"
    assert dest.is_file()
    doc = json.loads(dest.read_text(encoding="utf-8"))
    assert doc["schema"] == "scene-grammar/1"
    assert len(doc["placements"]) == 8


def test_scene_mine_overview_scene_exits_3(fixture_env, capsys):
    info, cfg = fixture_env["info"], fixture_env["cfg"]
    out_dir = fixture_env["tmp_path"] / "sg_out_overview"
    code = main(
        [
            "--config",
            str(cfg),
            "scene-mine",
            "--pack",
            build_fixture.PACK_ID,
            "--scene",
            str(info["overview_scene"]),
            "--out",
            str(out_dir),
        ]
    )
    assert code == 3
    err = capsys.readouterr().err
    assert "Overview" in err
    assert not out_dir.exists() or not any(out_dir.iterdir())


def test_scene_mine_missing_catalogs_dir_exits_2(fixture_env, capsys):
    cfg = fixture_env["cfg"]
    missing = fixture_env["tmp_path"] / "no-such-catalogs"
    code = main(
        [
            "--config",
            str(cfg),
            "scene-mine",
            "--pack",
            build_fixture.PACK_ID,
            "--catalogs",
            str(missing),
        ]
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "catalogs directory not found" in err
