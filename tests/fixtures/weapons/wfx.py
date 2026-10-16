"""Shared helpers for tests/test_weapons_*.py (loaded by path: tests/fixtures is not a package)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

CATALOGS = HERE / "catalogs"
EXPECTED = HERE / "expected.json"


def expected() -> dict:
    return json.loads(EXPECTED.read_text(encoding="utf-8"))


def pack_settings() -> dict:
    return expected()["pack_settings"]


def catalog_assets() -> dict[str, dict]:
    """full id -> catalog asset (all five fixture packs)."""
    out = {}
    for path in sorted(CATALOGS.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for a in doc["assets"]:
            out[f"{doc['pack_id']}/{a['id']}"] = (doc["pack_id"], a)
    return out


def make_catalogs_dir(tmp_path: Path, name: str = "catalogs") -> Path:
    """Copy the committed fixture catalogs into a fresh catalogs dir, with the neighbours a real one has.

    index.json and search.db are dummies: they exist so the AC28 hash check really covers them, and so
    the build must provably ignore them.
    """
    dest = tmp_path / name
    dest.mkdir(parents=True, exist_ok=True)
    for path in sorted(CATALOGS.glob("*.json")):
        shutil.copyfile(path, dest / path.name)
    (dest / "index.json").write_bytes(b'{"version": 2, "packs": []}\n')
    (dest / "search.db").write_bytes(b"SQLite format 3\x00 dummy")
    (dest / "_measure_cache.json").write_bytes(b'{"x": 1}\n')
    (dest / "FAKE_Modern.scene_grammar.json").write_bytes(b'{"pack_id": "FAKE_Modern", "scenes": []}\n')
    return dest


def build(catalogs_dir: Path, **kw):
    """build_directory with the fixture pack settings and (unless given) an empty overrides table."""
    from synty_inventory.weapons.directory import build_directory
    from synty_inventory.weapons.overrides import empty_overrides

    kw.setdefault("overrides", empty_overrides())
    kw.setdefault("pack_settings", pack_settings())
    return build_directory(catalogs_dir, **kw)


def overrides_doc(ids: dict | None = None, globs: dict | None = None) -> dict:
    return {"schema": "weapon-overrides/1", "ids": ids or {}, "globs": globs or {}}


def records_by_id(directory: dict) -> dict[str, dict]:
    return {w["id"]: w for w in directory["weapons"]}
