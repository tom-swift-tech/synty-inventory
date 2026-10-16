"""Weapon directory W1: determinism (AC27, INV-4) and additivity (AC28, INV-5).

A build is a pure function of the catalogs, the rules, the overrides and ``WEAPON_VERSION``: no clock, no cwd, no
file order. It reads catalogs and writes only under ``<catalogs>/weapons/``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import time
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("wfx", Path(__file__).parent / "fixtures" / "weapons" / "wfx.py")
wfx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wfx)

_mk = importlib.util.spec_from_file_location("make_catalogs", Path(__file__).parent / "fixtures" / "weapons" / "make_catalogs.py")
make_catalogs = importlib.util.module_from_spec(_mk)
_mk.loader.exec_module(make_catalogs)

import synty_inventory.weapons as weapons_pkg  # noqa: E402
from synty_inventory.cli import main  # noqa: E402
from synty_inventory.weapons import to_text  # noqa: E402
from synty_inventory.weapons.directory import build_directory, write_directory  # noqa: E402


def _bytes(directory, excluded) -> tuple[bytes, bytes]:
    return to_text(directory).encode("utf-8"), to_text(excluded).encode("utf-8")


def _hash_tree(root: Path, skip: str = "weapons") -> dict[str, str]:
    out = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_file() and not rel.startswith(skip + "/"):
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _write_config(tmp_path: Path, catalogs_dir: Path) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "\n".join([f'unity_root: "{tmp_path.as_posix()}/unity"', f'extracted_root: "{tmp_path.as_posix()}/extracted"',
                   f'catalogs: "{catalogs_dir.as_posix()}"']) + "\n", encoding="utf-8")
    return cfg


def _cli_build(tmp_path, monkeypatch, capsys, cat):
    for key in ("SYNTI_CONFIG", "SYNTI_CATALOGS"):
        monkeypatch.delenv(key, raising=False)
    import synty_inventory.packs.profile as profile

    monkeypatch.setattr(profile, "load_settings_table", lambda *a, **k: wfx.pack_settings())
    capsys.readouterr()
    code = main(["--config", str(_write_config(tmp_path, cat)), "weapons", "build"])
    capsys.readouterr()
    return code


# --- AC27 --------------------------------------------------------------------------------------------------

def test_ac27_two_builds_are_byte_identical(tmp_path):
    cat = wfx.make_catalogs_dir(tmp_path)
    first = _bytes(*wfx.build(cat))
    second = _bytes(*wfx.build(cat))
    assert first == second
    assert len(first[0]) > 10_000 and first[0].endswith(b"\n") and b"\r" not in first[0]


def test_ac27_written_files_are_byte_identical_across_runs_and_dirs(tmp_path):
    outs = []
    for name in ("one", "two"):
        cat = wfx.make_catalogs_dir(tmp_path / name)
        directory, excluded = wfx.build(cat)
        dpath, epath = write_directory(cat, directory, excluded)
        outs.append((dpath.read_bytes(), epath.read_bytes()))
        assert sorted(p.name for p in dpath.parent.iterdir()) == ["directory.json", "excluded.json"]  # no .tmp left
    assert outs[0] == outs[1]  # a different catalogs path changes nothing


def test_ac27_touching_an_unrelated_file_changes_nothing(tmp_path):
    cat = wfx.make_catalogs_dir(tmp_path)
    before = _bytes(*wfx.build(cat))
    (cat / "notes.txt").write_text("scratch", encoding="utf-8")
    (cat / "FAKE_Modern.scene_grammar.json").write_bytes(b'{"pack_id": "FAKE_Modern", "scenes": [1, 2, 3]}\n')
    (cat / "index.json").write_bytes(b'{"version": 2, "packs": ["x"]}\n')
    (cat / "search.db").write_bytes(b"SQLite format 3\x00 changed")
    (cat / "_measure_cache.json").write_bytes(b'{"y": 2}\n')
    assert _bytes(*wfx.build(cat)) == before


def test_ac27_catalog_asset_order_does_not_matter(tmp_path):
    cat = wfx.make_catalogs_dir(tmp_path)
    before = _bytes(*wfx.build(cat))
    for path in sorted(cat.glob("FAKE_*.json")):
        if path.name.endswith(".scene_grammar.json"):
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["assets"].reverse()
        path.write_text(json.dumps(doc), encoding="utf-8")
    assert _bytes(*wfx.build(cat)) == before


def test_ac27_weapon_version_bump_changes_only_weapon_version(tmp_path, monkeypatch):
    cat = wfx.make_catalogs_dir(tmp_path)
    old_dir, old_excl = wfx.build(cat)
    assert old_dir["weapon_version"] == 1
    monkeypatch.setattr(weapons_pkg, "WEAPON_VERSION", 2)
    new_dir, new_excl = wfx.build(cat)
    assert new_dir["weapon_version"] == 2
    rest_old = {k: v for k, v in old_dir.items() if k != "weapon_version"}
    rest_new = {k: v for k, v in new_dir.items() if k != "weapon_version"}
    assert rest_old == rest_new  # records, counts, packs, digests: all identical
    assert new_excl == old_excl
    assert to_text(rest_old) == to_text(rest_new)


def test_ac27_the_build_reads_no_clock(tmp_path, monkeypatch):
    cat = wfx.make_catalogs_dir(tmp_path)
    ticks = iter(range(1_000_000, 2_000_000))
    first = _bytes(*wfx.build(cat))
    monkeypatch.setattr(time, "time", lambda: next(ticks))
    monkeypatch.setattr(time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(time, "perf_counter", lambda: next(ticks))
    second = _bytes(*wfx.build(cat))
    assert first == second
    text = first[0].decode("utf-8")
    assert "1000000" not in text and "1000001" not in text


def test_ac27_scanned_at_is_copied_from_the_catalog_never_generated(tmp_path):
    cat = wfx.make_catalogs_dir(tmp_path)
    directory, _ = wfx.build(cat)
    for row in directory["packs"]:
        doc = json.loads((cat / f"{row['pack']}.json").read_text(encoding="utf-8"))
        assert row["scanned_at"] == doc.get("scanned_at")


def test_ac27_cli_build_twice_is_byte_identical(tmp_path, monkeypatch, capsys):
    cat = wfx.make_catalogs_dir(tmp_path)
    assert _cli_build(tmp_path, monkeypatch, capsys, cat) == 0
    first = [(cat / "weapons" / n).read_bytes() for n in ("directory.json", "excluded.json")]
    assert _cli_build(tmp_path, monkeypatch, capsys, cat) == 0
    second = [(cat / "weapons" / n).read_bytes() for n in ("directory.json", "excluded.json")]
    assert first == second


# --- AC28 --------------------------------------------------------------------------------------------------

def test_ac28_build_leaves_every_catalog_index_and_searchdb_untouched(tmp_path, monkeypatch, capsys):
    cat = wfx.make_catalogs_dir(tmp_path)
    before = _hash_tree(cat)
    assert {"index.json", "search.db", "FAKE_Modern.json", "FAKE_Fantasy.json"} <= set(before)
    assert _cli_build(tmp_path, monkeypatch, capsys, cat) == 0
    assert _hash_tree(cat) == before
    assert (cat / "weapons" / "directory.json").is_file()
    after_dirs = {p.name for p in cat.iterdir() if p.is_dir()}
    assert after_dirs == {"weapons"}


def test_ac28_library_build_without_write_touches_nothing(tmp_path):
    cat = wfx.make_catalogs_dir(tmp_path)
    before = _hash_tree(cat)
    wfx.build(cat)
    assert _hash_tree(cat) == before
    assert not (cat / "weapons").exists()


def test_ac28_a_rejected_directory_writes_nothing(tmp_path):
    from synty_inventory.weapons import SchemaError

    cat = wfx.make_catalogs_dir(tmp_path)
    directory, excluded = wfx.build(cat)
    directory["weapons"][0]["hints"]["damage"] = 1
    with pytest.raises(SchemaError):
        write_directory(cat, directory, excluded)
    assert not (cat / "weapons").exists()


def test_a_second_build_over_a_stale_directory_replaces_it_whole(tmp_path):
    cat = wfx.make_catalogs_dir(tmp_path)
    directory, excluded = wfx.build(cat)
    write_directory(cat, directory, excluded)
    (cat / "weapons" / "directory.json").write_text("stale", encoding="utf-8")
    directory2, excluded2 = build_directory(cat, overrides=wfx.overrides_doc(), pack_settings=wfx.pack_settings())
    dpath, _ = write_directory(cat, directory2, excluded2)
    assert dpath.read_bytes() == to_text(directory).encode("utf-8")


# --- fixtures ----------------------------------------------------------------------------------------------

def test_committed_fixtures_are_what_the_generator_writes(tmp_path):
    here = Path(__file__).parent / "fixtures" / "weapons"
    written = make_catalogs.write_all(tmp_path)
    assert len(written) == 6
    for path in written:
        rel = path.relative_to(tmp_path)
        # a Windows checkout with core.autocrlf rewrites the committed (LF) blobs to CRLF: compare modulo that
        committed = (here / rel).read_bytes().replace(b"\r\n", b"\n")
        assert committed == path.read_bytes(), f"{rel} drifted: rerun tests/fixtures/weapons/make_catalogs.py"
    on_disk = sorted(p.name for p in (here / "catalogs").glob("*.json"))
    assert on_disk == sorted(p.name for p in (tmp_path / "catalogs").glob("*.json"))
