from pathlib import Path

from synty_inventory.catalog import load_catalog, rebuild_index, write_catalog
from synty_inventory.schema import CATALOG_VERSION


def _doc(pack_id: str, n: int = 1) -> dict:
    assets = []
    for i in range(n):
        assets.append(
            {
                "id": f"SM_Prop_{pack_id}_{i:02d}",
                "name": pack_id,
                "type": "prop",
                "category": [],
                "tags": [],
                "description": "x" * 80,
                "semantic_role": "dresses_scene",
                "placement": {
                    "mount": "ground",
                    "height": "grade",
                    "orientation": "upright",
                    "attachment": "base_to_ground",
                    "preferred_floors": [1],
                    "constraints": [],
                    "preferred_contexts": [],
                },
                "dimensions": {"approx": [1.0, 1.0, 1.0], "units": "meters"},
                "paths": {"prefab": f"{pack_id}.prefab", "mesh": None, "materials": []},
                "thumbnail": None,
                "ai_notes": "y" * 40,
            }
        )
    return {
        "pack_id": pack_id,
        "engine": "Unity",
        "origin": "Synty",
        "style": "lowpoly_synty",
        "units": "meters",
        "version": CATALOG_VERSION,
        "scanned_at": "2026-08-18T00:00:00+00:00",
        "asset_count": n,
        "assets": assets,
    }


def test_rebuild_index_keeps_other_packs(tmp_path: Path):
    write_catalog(tmp_path / "PackA.json", _doc("PackA", 2))
    write_catalog(tmp_path / "PackB.json", _doc("PackB", 3))
    rebuild_index(tmp_path)

    write_catalog(tmp_path / "PackA.json", _doc("PackA", 4))
    rebuild_index(
        tmp_path,
        [{"pack_id": "PackA", "errors": ["only this run"], "source": {"extracted": "a"}}],
    )

    index = load_catalog(tmp_path / "index.json")
    assert index is not None
    ids = [p["pack_id"] for p in index["packs"]]
    assert ids == ["PackA", "PackB"]
    by_id = {p["pack_id"]: p for p in index["packs"]}
    assert by_id["PackA"]["assets"] == 4
    assert by_id["PackA"]["errors"] == ["only this run"]
    assert by_id["PackB"]["assets"] == 3
    assert by_id["PackB"]["errors"] == []
    # discovery header (Phase 1): totals + per-pack stats + recipe ids
    assert index["totals"]["assets"] == 7
    assert index["totals"]["placeable"] == 7
    assert index["totals"]["reviewed"] == 0
    assert by_id["PackA"]["placeable"] == 4
    assert by_id["PackA"]["kits"] == []
    assert "ship_kit" in index["recipes"]
