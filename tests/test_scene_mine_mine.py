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


def test_duplicate_layout_scene_marked_duplicate_of(fixture_pack, tmp_path):
    scenes = [fixture_pack["demo_scene"], fixture_pack["demo_copy_scene"]]
    grammar = mine_pack(
        build_fixture.PACK_ID,
        scenes,
        fixture_pack["catalog"],
        catalog_path=_catalog_path(fixture_pack, tmp_path),
    )
    scene_rows = grammar.doc["scenes"]
    assert scene_rows[0]["duplicate_of"] is None
    assert scene_rows[1]["duplicate_of"] == 0
    # A duplicate scene contributes nothing to placements/histogram/etc --
    # the pack's 8 unique placements appear exactly once, not twice.
    assert len(grammar.doc["placements"]) == 8


def test_schema_validation_passes_on_fixture_output(fixture_pack, tmp_path):
    scenes = [fixture_pack["demo_scene"]]
    grammar = mine_pack(
        build_fixture.PACK_ID,
        scenes,
        fixture_pack["catalog"],
        catalog_path=_catalog_path(fixture_pack, tmp_path),
    )
    jsonschema.validate(grammar.doc, _load_schema())  # raises on any violation


def test_write_grammar_is_deterministic_modulo_generated_at(fixture_pack, tmp_path):
    scenes = [fixture_pack["demo_scene"], fixture_pack["demo_copy_scene"]]
    catalog_path = _catalog_path(fixture_pack, tmp_path)

    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    grammar_a = mine_pack(build_fixture.PACK_ID, scenes, fixture_pack["catalog"], catalog_path=catalog_path)
    grammar_b = mine_pack(build_fixture.PACK_ID, scenes, fixture_pack["catalog"], catalog_path=catalog_path)
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
