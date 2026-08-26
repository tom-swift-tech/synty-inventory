"""T2: cache + enrichment wiring for sources.footprint (spec AC6, AC11)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures" / "glb"))

from build_glb import box_mesh, write_mesh_glb  # noqa: E402

from synty_inventory.sources.footprint import (  # noqa: E402
    CACHE_NAME,
    FOOTPRINT_VERSION,
    analyze_cached,
    apply_footprint,
    decode_count,
    footprint_cache_path,
    reset_decode_count,
)


@pytest.fixture
def pack(tmp_path):
    """A threejs-v2-shaped root with one measurable GLB."""
    root = tmp_path / "threejs-v2"
    models = root / "PACK" / "models"
    models.mkdir(parents=True)
    verts, tris = box_mesh([0, 0, 0], [5, 3, 5])
    write_mesh_glb(models / "SM_Test_01.glb", verts, tris)
    return root


def asset(glb="PACK/models/SM_Test_01.glb", **over):
    a = {"id": "SM_Test_01", "placeable": True, "files": {"glb": glb}}
    a.update(over)
    return a


def test_cache_path_is_measure_cache_sibling(tmp_path):
    assert footprint_cache_path(tmp_path).name == CACHE_NAME
    assert footprint_cache_path(tmp_path).parent == tmp_path


def test_cold_then_warm_run_decodes_once(pack):
    """AC6: a second run over unchanged GLBs decodes nothing."""
    cache: dict = {}
    stats: dict = {}

    reset_decode_count()
    a = asset()
    assert apply_footprint(a, pack, cache, stats) == "measured"
    assert decode_count() == 1
    assert a["footprint"]["area_m2"] == pytest.approx(25.0, abs=0.01)
    assert a["provenance"]["footprint"] == "measured"

    reset_decode_count()
    b = asset()
    assert apply_footprint(b, pack, cache, stats) == "cached"
    assert decode_count() == 0
    assert b["footprint"] == a["footprint"]

    assert stats["footprint_measured"] == 1
    assert stats["footprint_cached"] == 1


def test_force_bypasses_cache(pack):
    cache: dict = {}
    stats: dict = {}
    apply_footprint(asset(), pack, cache, stats)
    reset_decode_count()
    assert apply_footprint(asset(), pack, cache, stats, force=True) == "measured"
    assert decode_count() == 1


def test_version_bump_invalidates(pack):
    cache: dict = {}
    stats: dict = {}
    apply_footprint(asset(), pack, cache, stats)
    for entry in cache.values():
        entry["version"] = FOOTPRINT_VERSION - 1
    reset_decode_count()
    assert apply_footprint(asset(), pack, cache, stats) == "measured"
    assert decode_count() == 1


def test_edited_glb_invalidates(pack):
    """The key carries mtime and size, so a re-export re-analyses.

    Note the shared ``glb_measure._cache_key`` is ``int(mtime):size`` --
    second granularity. A rewrite inside the same second that happens to
    produce a byte-identical size will NOT invalidate. That is pre-existing
    behaviour of the measure cache, so this test changes the vertex count to
    move the size rather than pretending the mtime alone is sufficient.
    """
    cache: dict = {}
    stats: dict = {}
    apply_footprint(asset(), pack, cache, stats)

    v1, t1 = box_mesh([0, 0, 0], [9, 3, 9])
    v2, t2 = box_mesh([12, 0, 0], [14, 3, 2])
    verts = v1 + v2
    tris = t1 + [[i + len(v1) for i in tri] for tri in t2]
    write_mesh_glb(pack / "PACK" / "models" / "SM_Test_01.glb", verts, tris)

    reset_decode_count()
    a = asset()
    assert apply_footprint(a, pack, cache, stats) == "measured"
    assert decode_count() == 1
    assert a["footprint"]["components"] == 2
    assert a["footprint"]["area_m2"] == pytest.approx(85.0, abs=0.1)


def test_failures_are_cached_too(pack):
    """An undecodable mesh can never succeed; re-decoding it every scan
    would cost most on exactly the assets that always fail.

    A cached failure still reports *why* rather than ``cached`` -- the
    report's failures[] needs the reason, and the saving shows up as a zero
    decode count.
    """
    bad = pack / "PACK" / "models" / "SM_Bad_01.glb"
    bad.write_bytes(b"not a glb")
    cache: dict = {}
    stats: dict = {}
    a = asset(glb="PACK/models/SM_Bad_01.glb")
    assert apply_footprint(a, pack, cache, stats) == "undecodable"
    assert a["footprint"] is None
    reset_decode_count()
    b = asset(glb="PACK/models/SM_Bad_01.glb")
    assert apply_footprint(b, pack, cache, stats) == "undecodable"
    assert decode_count() == 0
    assert b["footprint"] is None


def test_missing_glb_is_not_a_failure(pack):
    stats: dict = {}
    a = asset()
    a["files"] = {}
    assert apply_footprint(a, pack, {}, stats) == "missing_glb"
    assert "footprint" not in a


def test_non_placeable_skipped(pack):
    stats: dict = {}
    a = asset(placeable=False)
    assert apply_footprint(a, pack, {}, stats) == "skipped"
    assert "footprint" not in a


def test_human_locked_record_untouched(pack):
    """AC11: a human value survives, and is reported as skipped."""
    stats: dict = {}
    keep = {"polygon_m": [[0, 0], [1, 0], [1, 1], [0, 1]], "source": "human"}
    a = asset(footprint=keep, provenance={"footprint": "human"})
    assert apply_footprint(a, pack, {}, stats) == "skipped"
    assert a["footprint"] is keep


def test_locked_fields_respected(pack):
    stats: dict = {}
    keep = {"polygon_m": [[0, 0], [2, 0], [2, 2], [0, 2]]}
    a = asset(footprint=keep, locked_fields=["footprint"])
    assert apply_footprint(a, pack, {}, stats) == "skipped"
    assert a["footprint"] is keep


def test_tile_cells_from_pack_grid(pack):
    stats: dict = {}
    a = asset()
    apply_footprint(a, pack, {}, stats, tile_m=5.0)
    assert a["footprint"]["tile_cells"] == [1, 1]


def test_analyze_cached_reports_cache_hit(pack):
    cache: dict = {}
    _, _, was_cached = analyze_cached(pack, "PACK/models/SM_Test_01.glb", cache)
    assert was_cached is False
    _, _, was_cached = analyze_cached(pack, "PACK/models/SM_Test_01.glb", cache)
    assert was_cached is True
