import re
from pathlib import Path

import pytest

from synty_inventory.paths import (
    CONFIG_KEYS,
    ConfigError,
    example_file,
    find_config_file,
    load_config,
    posix,
    resolve_config,
    skill_file,
)


SRC_ROOT = Path(__file__).resolve().parents[1] / "src"


def _clear_synti_env(monkeypatch):
    monkeypatch.delenv("SYNTI_CONFIG", raising=False)
    for env in CONFIG_KEYS.values():
        monkeypatch.delenv(env, raising=False)


def test_source_has_no_machine_paths():
    """Tracked text must not contain a host drive-letter root.

    The private library folder name is assembled so this test file itself
    never contains that host path as a single literal.
    """
    root = SRC_ROOT.parent
    lib = "_".join(("game", "assets", "library"))
    host_abs = re.compile(
        rf"(?i)[A-Za-z]:[/\\](?:Users[/\\]|{re.escape(lib)})"
    )
    offenders = []
    checked = (
        list(SRC_ROOT.rglob("*.py"))
        + list((root / "tests").rglob("*.py"))
        + [
            root / "README.md",
            root / "skill" / "SKILL.md",
            root / "config.example.yaml",
        ]
    )
    for path in checked:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if host_abs.search(text):
            offenders.append(str(path.relative_to(root)))
    assert offenders == []


def test_load_config_from_explicit_file(tmp_path: Path, monkeypatch):
    _clear_synti_env(monkeypatch)
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "\n".join(
            [
                'unity_root: "C:/lib/Unity"',
                'extracted_root: "C:/lib/extracted"',
                'catalogs: "C:/lib/catalogs"',
                'viewer_data: "viewer/data"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert posix(cfg["unity_root"]) == "C:/lib/Unity"
    assert posix(cfg["extracted_root"]) == "C:/lib/extracted"
    assert posix(cfg["catalogs"]) == "C:/lib/catalogs"
    assert cfg["viewer_data"] == (tmp_path / "viewer" / "data")
    assert "threejs_v2" not in cfg


def test_env_overrides_file(tmp_path: Path, monkeypatch):
    _clear_synti_env(monkeypatch)
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        'unity_root: "C:/from-file/Unity"\n'
        'extracted_root: "C:/from-file/extracted"\n'
        'catalogs: "C:/from-file/catalogs"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("SYNTI_CATALOGS", "C:/from-env/catalogs")
    cfg = load_config(cfg_file)
    assert posix(cfg["catalogs"]) == "C:/from-env/catalogs"
    assert posix(cfg["unity_root"]) == "C:/from-file/Unity"


def test_missing_required_raises(tmp_path: Path, monkeypatch):
    _clear_synti_env(monkeypatch)
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("threejs_v2: C:/optional\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="missing required path"):
        load_config(cfg_file)
    cfg = load_config(cfg_file, require=False)
    assert posix(cfg["threejs_v2"]) == "C:/optional"
    assert "unity_root" not in cfg


def test_missing_explicit_config_raises(tmp_path: Path, monkeypatch):
    _clear_synti_env(monkeypatch)
    with pytest.raises(ConfigError, match="not found"):
        find_config_file(tmp_path / "nope.yaml")


def test_resolve_config_reports_sources(tmp_path: Path, monkeypatch):
    _clear_synti_env(monkeypatch)
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        'unity_root: "C:/lib/Unity"\n'
        'extracted_root: "C:/lib/extracted"\n'
        'catalogs: "C:/lib/catalogs"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("SYNTI_UNITY_ROOT", "C:/env/Unity")
    meta = resolve_config(cfg_file)
    assert meta["sources"]["unity_root"] == "env"
    assert meta["sources"]["catalogs"] == "file"
    assert meta["sources"]["viewer_data"] == "unset"
    assert meta["config_file"] == cfg_file


def test_packaged_example_and_skill_exist():
    ex = example_file()
    assert ex.is_file(), ex
    assert "unity_root" in ex.read_text(encoding="utf-8")
    sk = skill_file()
    assert sk.is_file(), sk
    assert "synty-inventory" in sk.read_text(encoding="utf-8")
    root = SRC_ROOT.parent
    assert ex.read_text(encoding="utf-8") == (root / "config.example.yaml").read_text(
        encoding="utf-8"
    )
    assert sk.read_text(encoding="utf-8") == (root / "skill" / "SKILL.md").read_text(
        encoding="utf-8"
    )
