"""AC16 (miner half): ``mine_pack``/``write_grammar`` orchestration --
duplicate-scene detection, schema validation, and determinism (AC7)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures" / "scene_mine"))

import build_fixture  # noqa: E402

from synty_inventory.scene_mine.mine import _load_schema, mine_pack, write_grammar  # noqa: E402


@pytest.fixture
def fixture_pack(tmp_path: Path) -> dict:
    return build_fixture.build(tmp_path / "extracted")


def _catalog_path(fixture_pack, tmp_path):
    p = tmp_path / f"{build_fixture.PACK_ID}.json"
    p.write_text(json.dumps(fixture_pack["catalog"]), encoding="utf-8")
    return p


# The fixture Demo has 8 placements -- below the 100-placement statistics floor -- so every test that wants
# statistics out of it lowers the floor explicitly; `test_stats_floor_*` below cover the default.
FLOOR_OFF = {"min_stats_placements": 1}


def test_duplicate_layout_scene_marked_duplicate_of(fixture_pack, tmp_path):
    scenes = [fixture_pack["demo_scene"], fixture_pack["demo_copy_scene"]]
    grammar = mine_pack(
        build_fixture.PACK_ID,
        scenes,
        fixture_pack["catalog"],
        catalog_path=_catalog_path(fixture_pack, tmp_path),
        **FLOOR_OFF,
    )
    scene_rows = grammar.doc["scenes"]
    assert scene_rows[0]["duplicate_of"] is None
    assert scene_rows[1]["duplicate_of"] == 0
    assert [r["stats_excluded"] for r in scene_rows] == [False, False]
    # A duplicate scene contributes nothing to placements/histogram/etc --
    # the pack's 8 unique placements appear exactly once, not twice.
    assert len(grammar.doc["placements"]) == 8


def test_stats_floor_excludes_a_small_scene_but_keeps_its_look_and_cameras(fixture_pack, tmp_path):
    scenes = [fixture_pack["demo_scene"]]
    catalog_path = _catalog_path(fixture_pack, tmp_path)
    with_stats = mine_pack(build_fixture.PACK_ID, scenes, fixture_pack["catalog"], catalog_path=catalog_path, **FLOOR_OFF)
    floored = mine_pack(build_fixture.PACK_ID, scenes, fixture_pack["catalog"], catalog_path=catalog_path)  # default 100

    row = floored.doc["scenes"][0]
    assert row["stats_excluded"] is True and row["duplicate_of"] is None
    assert row["resolved"] == 8 == with_stats.doc["scenes"][0]["resolved"]  # the row still carries its counts
    # nothing from the scene reaches placements[] or any statistics block ...
    assert floored.doc["placements"] == []
    assert floored.doc["histogram"] == {}
    assert floored.doc["adjacency"]["pairs"] == []
    assert floored.doc["density"] != with_stats.doc["density"]
    # ... but the look and the cameras are exactly what the unfloored run extracted
    assert floored.doc["look"] == with_stats.doc["look"] and floored.doc["look"] is not None
    assert floored.doc["cameras"] == with_stats.doc["cameras"]
    jsonschema.validate(floored.doc, _load_schema())


def test_stats_floor_is_reported_per_scene(fixture_pack, tmp_path):
    scenes = [fixture_pack["demo_scene"], fixture_pack["demo_copy_scene"]]
    grammar = mine_pack(build_fixture.PACK_ID, scenes, fixture_pack["catalog"], catalog_path=_catalog_path(fixture_pack, tmp_path))
    rows = grammar.report["scenes"]
    # the duplicate is still detected first (it is a duplicate of a floored scene), and both are floored
    assert [(r["duplicate_of"], r["stats_excluded"]) for r in rows] == [(None, True), (0, True)]


def test_schema_validation_passes_on_fixture_output(fixture_pack, tmp_path):
    scenes = [fixture_pack["demo_scene"]]
    grammar = mine_pack(
        build_fixture.PACK_ID,
        scenes,
        fixture_pack["catalog"],
        catalog_path=_catalog_path(fixture_pack, tmp_path),
        **FLOOR_OFF,
    )
    jsonschema.validate(grammar.doc, _load_schema())  # raises on any violation


def test_write_grammar_is_deterministic_modulo_generated_at(fixture_pack, tmp_path):
    scenes = [fixture_pack["demo_scene"], fixture_pack["demo_copy_scene"]]
    catalog_path = _catalog_path(fixture_pack, tmp_path)

    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    grammar_a = mine_pack(build_fixture.PACK_ID, scenes, fixture_pack["catalog"], catalog_path=catalog_path, **FLOOR_OFF)
    grammar_b = mine_pack(build_fixture.PACK_ID, scenes, fixture_pack["catalog"], catalog_path=catalog_path, **FLOOR_OFF)
    dest_a = write_grammar(grammar_a, out_a)
    dest_b = write_grammar(grammar_b, out_b)

    def _mask(text: str) -> str:
        doc = json.loads(text)
        doc["provenance"]["generated_at"] = "MASKED"
        return json.dumps(doc, sort_keys=True)

    text_a = dest_a.read_text(encoding="utf-8")
    text_b = dest_b.read_text(encoding="utf-8")
    # generated_at has one-second resolution, so two runs in the same test
    # may or may not land on the same second -- the determinism guarantee
    # (AC7) is that nothing *else* differs, checked by masking it out.
    assert _mask(text_a) == _mask(text_b)
