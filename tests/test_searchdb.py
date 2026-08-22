"""search.db (Phase 2): derived FTS5 index under search_assets.

Pins: rebuild_index builds the DB; row counts mirror the catalogs; the DB
path actually serves search (no catalog walk) when fresh; a stale DB falls
back to the linear walk; porter stemming finds prose the substring scorer
misses; empty-query facet search works from the DB; ranking pins from
test_query still hold on the DB path.
"""

from pathlib import Path

from synty_inventory import searchdb
from synty_inventory.catalog import rebuild_index, write_catalog
from synty_inventory.query import search_assets
from synty_inventory.schema import migrate_catalog


def _asset(aid, name, **kwargs):
    rec = {
        "id": aid,
        "name": name,
        "type": kwargs.get("type", "prop/signage"),
        "category": kwargs.get("category", ["sign"]),
        "tags": kwargs.get("tags", []),
        "description": kwargs.get("description", name + " description " + "x" * 80),
        "semantic_role": kwargs.get("semantic_role", "identifies_building_as_police_station"),
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
        "paths": {"prefab": f"Prefabs/{aid}.prefab", "mesh": None, "materials": []},
        "thumbnail": None,
        "ai_notes": "Use on the matching facade. " + "y" * 20,
    }
    rec.update(kwargs.get("extra", {}))
    return rec


def _write_fixture(tmp_path: Path) -> Path:
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
                _asset(
                    "SM_Prop_Sign_Police_01",
                    "Police Sign",
                    tags=["police", "facade", "station"],
                ),
                _asset(
                    "SM_Prop_Awning_01",
                    "Shop Awning",
                    tags=["awning"],
                    semantic_role="storefront_dressing",
                    description="A striped canvas canopy that shelters shopfront entrances from rain.",
                ),
                _asset(
                    "SM_Clip_Wave_01",
                    "Wave Clip",
                    type="animation/clip",
                    category=[],
                    extra={"placeable": False},
                ),
            ],
        }
    )
    write_catalog(tmp_path / "POLYGON_City.json", city)
    rebuild_index(tmp_path)
    return tmp_path


def test_rebuild_index_builds_db_and_counts(tmp_path: Path):
    _write_fixture(tmp_path)
    db = searchdb.db_path(tmp_path)
    assert db.is_file()
    assert searchdb.is_fresh(tmp_path)
    counts = searchdb.row_counts(tmp_path)
    assert counts == {"assets": 3, "placeable": 2, "fts": 3}


def test_search_uses_db_not_catalog_walk(tmp_path: Path, monkeypatch):
    _write_fixture(tmp_path)

    def boom(*a, **k):
        raise AssertionError("linear catalog walk used despite fresh search.db")

    monkeypatch.setattr("synty_inventory.query._iter_assets", boom)
    hits = search_assets(tmp_path, "police")
    assert hits and hits[0]["id"] == "SM_Prop_Sign_Police_01"
    # slim-row contract unchanged on the DB path
    assert "description" not in hits[0] and hits[0]["pack"] == "POLYGON_City"


def test_stale_db_falls_back_to_linear(tmp_path: Path):
    _write_fixture(tmp_path)
    import os
    import time

    # make the catalog newer than the DB (mtime bump beats FS granularity)
    cat = tmp_path / "POLYGON_City.json"
    future = time.time() + 60
    os.utime(cat, (future, future))
    assert not searchdb.is_fresh(tmp_path)
    assert searchdb.candidates(tmp_path, "police") is None
    hits = search_assets(tmp_path, "police")  # linear fallback still serves
    assert hits and hits[0]["id"] == "SM_Prop_Sign_Police_01"


def test_fts_stemming_beats_substring(tmp_path: Path):
    _write_fixture(tmp_path)
    # "sheltering"/"canopies" only stem-match the awning description —
    # the linear substring scorer cannot see these.
    hits = search_assets(tmp_path, "canopies sheltering entrance")
    assert any(h["id"] == "SM_Prop_Awning_01" for h in hits)


def test_empty_query_facets_from_db(tmp_path: Path):
    _write_fixture(tmp_path)
    hits = search_assets(tmp_path, "", types=["prop/signage"])
    ids = {h["id"] for h in hits}
    assert ids == {"SM_Prop_Sign_Police_01", "SM_Prop_Awning_01"}
    # nonplaceable excluded by default, included on request
    all_hits = search_assets(tmp_path, "", include_nonplaceable=True)
    assert "SM_Clip_Wave_01" in {h["id"] for h in all_hits}


def test_kits_and_sockets_tables(tmp_path: Path):
    city = migrate_catalog(
        {
            "pack_id": "POLYGON_Test",
            "engine": "Unity",
            "origin": "Synty",
            "style": "lowpoly",
            "units": "meters",
            "version": 1,
            "scanned_at": "2026-08-18T00:00:00+00:00",
            "assets": [
                _asset(
                    "SM_Bld_Wall_01",
                    "Wall",
                    type="building/module",
                    extra={
                        "module": {"family": "Apartment", "role": "wall"},
                        "part": {
                            "class": "hull",
                            "sockets": [
                                {
                                    "role": "hull",
                                    "axis": "+x",
                                    "position": [1.0, 0.0, 0.0],
                                    "normal": [1.0, 0.0, 0.0],
                                    "source": "measured",
                                }
                            ],
                        },
                    },
                ),
            ],
        }
    )
    write_catalog(tmp_path / "POLYGON_Test.json", city)
    rebuild_index(tmp_path)
    import sqlite3

    con = sqlite3.connect(searchdb.db_path(tmp_path))
    kits = con.execute("SELECT pack, family, role, asset_id FROM kits").fetchall()
    socks = con.execute("SELECT role, axis, source FROM sockets").fetchall()
    con.close()
    assert kits == [("POLYGON_Test", "Apartment", "wall", "SM_Bld_Wall_01")]
    assert socks == [("hull", "+x", "measured")]
