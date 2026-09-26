"""CLI wiring tests for ``pack-profile`` / ``packs suggest`` / ``packs
contact-sheet`` (spec §3.3). Fixture catalogs only."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from synty_inventory.catalog import write_catalog
from synty_inventory.cli import build_parser, main


def _clear_synti_env(monkeypatch):
    for key in (
        "SYNTI_CONFIG",
        "SYNTI_UNITY_ROOT",
        "SYNTI_EXTRACTED_ROOT",
        "SYNTI_THREEJS_V2",
        "SYNTI_VIEWER_DATA",
        "SYNTI_CATALOGS",
        "SYNTI_GODOT_ROOT",
        "SYNTI_UNREAL_ROOT",
        "SYNTI_SYNTY_GLB_ROOT",
    ):
        monkeypatch.delenv(key, raising=False)


def _fixture_catalog(pack_id: str, n: int = 50) -> dict:
    assets = [
        {
            "id": f"{pack_id}_a{i}",
            "type": "prop",
            "semantic_role": "exterior_prop",
            "placeable": True,
            "module": {"family": None},
            "files": {"glb": None},
        }
        for i in range(n)
    ]
    return {"pack_id": pack_id, "assets": assets}


def _write_config(tmp_path: Path, catalogs_dir: Path) -> Path:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "\n".join(
            [
                f'unity_root: "{tmp_path.as_posix()}/unity"',
                f'extracted_root: "{tmp_path.as_posix()}/extracted"',
                f'catalogs: "{catalogs_dir.as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return cfg_file


# --- parser wiring -----------------------------------------------------------------


def test_parser_registers_pack_profile_and_packs_subcommands():
    parser = build_parser()
    choices = parser._subparsers._group_actions[0].choices
    assert "pack-profile" in choices
    assert "packs" in choices
    packs_sub = choices["packs"]
    packs_choices = packs_sub._subparsers._group_actions[0].choices
    assert set(packs_choices) == {"suggest", "contact-sheet"}


def test_pack_profile_requires_exactly_one_of_pack_or_all():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["pack-profile"])
    with pytest.raises(SystemExit):
        parser.parse_args(["pack-profile", "--pack", "POLYGON_City", "--all"])


def test_contact_sheet_out_flag_is_distinct_from_global_out(tmp_path: Path, monkeypatch):
    """The regression this guards: cli.main() does
    ``if args.out: cfg["catalogs"] = Path(args.out)`` -- `packs contact-sheet -o`
    must land in ``args.sheet_out``, never collide with the global ``--out``."""
    _clear_synti_env(monkeypatch)
    catalogs_dir = tmp_path / "catalogs"
    catalogs_dir.mkdir()
    write_catalog(catalogs_dir / "PACK_A.json", _fixture_catalog("PACK_A", 5))
    cfg_file = _write_config(tmp_path, catalogs_dir)
    png = tmp_path / "out" / "sheet.png"

    code = main(
        [
            "--config",
            str(cfg_file),
            "packs",
            "contact-sheet",
            "--packs",
            "PACK_A",
            "-o",
            str(png),
        ]
    )
    assert code == 0
    assert png.is_file()
    # the global catalogs dir was never overwritten with the PNG path
    assert catalogs_dir.is_dir()
    assert (catalogs_dir / "PACK_A.json").is_file()


# --- cmd_pack_profile -----------------------------------------------------------------


def test_cmd_pack_profile_all_writes_one_file_per_pack(tmp_path: Path):
    from synty_inventory.cli import cmd_pack_profile

    catalogs_dir = tmp_path / "catalogs"
    catalogs_dir.mkdir()
    write_catalog(catalogs_dir / "PACK_A.json", _fixture_catalog("PACK_A", 5))
    write_catalog(catalogs_dir / "PACK_B.json", _fixture_catalog("PACK_B", 5))

    args = SimpleNamespace(
        out=None,
        pack=None,
        all=True,
        vlm=None,
        no_vlm=False,
        human_override=None,
        config=None,
    )
    code = cmd_pack_profile(args, {"catalogs": catalogs_dir})
    assert code == 0
    out_dir = catalogs_dir / "pack_profiles"
    written = sorted(p.stem for p in out_dir.glob("*.json"))
    assert written == ["PACK_A", "PACK_B"]
    profile = json.loads((out_dir / "PACK_A.json").read_text(encoding="utf-8"))
    assert profile["schema"] == "pack-profile/1"
    assert profile["pack_class"] == "addon"  # 5 assets < 40


def test_cmd_pack_profile_single_pack_not_found_reports_error(tmp_path: Path):
    from synty_inventory.cli import cmd_pack_profile

    catalogs_dir = tmp_path / "catalogs"
    catalogs_dir.mkdir()
    args = SimpleNamespace(
        out=None, pack="NOT_THERE", all=False, vlm=None, no_vlm=False, human_override=None, config=None
    )
    code = cmd_pack_profile(args, {"catalogs": catalogs_dir})
    assert code == 2


def test_cmd_pack_profile_human_override_applied(tmp_path: Path):
    from synty_inventory.cli import cmd_pack_profile

    catalogs_dir = tmp_path / "catalogs"
    catalogs_dir.mkdir()
    write_catalog(catalogs_dir / "PACK_A.json", _fixture_catalog("PACK_A", 5))
    override_file = tmp_path / "override.yaml"
    override_file.write_text("PACK_A:\n  setting: horror\n  era: modern\n", encoding="utf-8")

    args = SimpleNamespace(
        out=None,
        pack="PACK_A",
        all=False,
        vlm=None,
        no_vlm=False,
        human_override=str(override_file),
        config=None,
    )
    code = cmd_pack_profile(args, {"catalogs": catalogs_dir})
    assert code == 0
    profile = json.loads((catalogs_dir / "pack_profiles" / "PACK_A.json").read_text(encoding="utf-8"))
    assert profile["setting"] == "horror"
    assert profile["provenance"]["setting"] == "human"


# --- cmd_packs_suggest -----------------------------------------------------------------


def test_cmd_packs_suggest_missing_profiles_dir_fails(tmp_path: Path):
    from synty_inventory.cli import cmd_packs_suggest

    catalogs_dir = tmp_path / "catalogs"
    catalogs_dir.mkdir()
    brief = tmp_path / "brief.yaml"
    brief.write_text("schema: game-brief/1\nsetting: scifi_frontier\n", encoding="utf-8")
    args = SimpleNamespace(out=None, brief=str(brief), engine="godot", max=12)
    code = cmd_packs_suggest(args, {"catalogs": catalogs_dir})
    assert code == 2


def test_cmd_packs_suggest_happy_path(tmp_path: Path, capsys):
    from synty_inventory.cli import cmd_packs_suggest

    catalogs_dir = tmp_path / "catalogs"
    profiles_dir = catalogs_dir / "pack_profiles"
    profiles_dir.mkdir(parents=True)
    (profiles_dir / "PACK_A.json").write_text(
        json.dumps(
            {
                "pack_id": "PACK_A",
                "pack_class": "environment",
                "setting": "scifi_frontier",
                "era": "far_future",
                "role_counts": {"exterior_prop": 200},
                "godot_ready": True,
                "grammar_available": True,
                "characters_rig": None,
            }
        ),
        encoding="utf-8",
    )
    brief = tmp_path / "brief.yaml"
    brief.write_text("schema: game-brief/1\nsetting: scifi_frontier\nera: far_future\n", encoding="utf-8")
    args = SimpleNamespace(out=None, brief=str(brief), engine="godot", max=12)
    code = cmd_packs_suggest(args, {"catalogs": catalogs_dir})
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["packs"][0]["pack_id"] == "PACK_A"
