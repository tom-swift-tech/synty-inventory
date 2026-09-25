"""Scene-mine sidecars (<PACK_ID>.scene_grammar.json) sit beside the pack
catalogs and carry a pack_id, so every loader must filter them by name —
the gauntlet once validated them as catalogs and failed schema_valid."""

import json
from pathlib import Path

from synty_inventory.catalog import load_all_catalogs
from synty_inventory.gauntlet import run_gauntlet
from synty_inventory.paths import is_pack_catalog_file
from synty_inventory.schema import CATALOG_VERSION


def _write_catalog(catalogs_dir: Path, pack_id: str) -> None:
    doc = {
        "pack_id": pack_id,
        "engine": "Unity",
        "origin": "Synty",
        "style": "toon",
        "units": "meters",
        "version": CATALOG_VERSION,
        "scanned_at": "2026-01-01T00:00:00+00:00",
        "grid": {"snap": 0.25, "module": 2.5, "tile": 5.0, "story": 3.0},
        "conventions": {"street_axis": "+z", "rotate_deg": 90, "scale": 1, "up_axis": "+y"},
        "asset_count": 0,
        "assets": [],
    }
    catalogs_dir.mkdir(parents=True, exist_ok=True)
    (catalogs_dir / f"{pack_id}.json").write_text(json.dumps(doc), encoding="utf-8")


def _write_grammar(catalogs_dir: Path, pack_id: str) -> None:
    doc = {"pack_id": pack_id, "scenes": [], "placements": []}
    (catalogs_dir / f"{pack_id}.scene_grammar.json").write_text(json.dumps(doc), encoding="utf-8")


def test_is_pack_catalog_file():
    assert is_pack_catalog_file(Path("POLYGON_City.json"))
    assert not is_pack_catalog_file(Path("POLYGON_City.scene_grammar.json"))
    assert not is_pack_catalog_file(Path("index.json"))
    assert not is_pack_catalog_file(Path("_measure_cache.json"))
    assert not is_pack_catalog_file(Path("search.db"))


def test_scene_grammar_sidecars_are_not_catalogs(tmp_path: Path):
    catalogs_dir = tmp_path / "catalogs"
    for pack in ("POLYGON_City", "POLYGON_Town"):
        _write_catalog(catalogs_dir, pack)
    _write_grammar(catalogs_dir, "POLYGON_City")

    assert [d["pack_id"] for d in load_all_catalogs(catalogs_dir)] == ["POLYGON_City", "POLYGON_Town"]

    gates = {g["gate"]: g for g in run_gauntlet(catalogs_dir)["gates"]}
    assert gates["catalogs_present"]["detail"] == "2 pack catalogs"
    assert gates["schema_valid"]["ok"] is True, gates["schema_valid"]["detail"]
