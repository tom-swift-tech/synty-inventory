"""T4/T5: footprint CLI + report, and the slim-row projection guard."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures" / "glb"))

from build_glb import box_mesh, write_mesh_glb  # noqa: E402

from synty_inventory import cli  # noqa: E402
from synty_inventory.project import slim_row  # noqa: E402
from synty_inventory.query import _match_v2_filters  # noqa: E402

FOOTPRINT = {
    "polygon_m": [[0.0, 0.0], [5.0, 0.0], [5.0, 5.0], [0.0, 5.0]],
    "components": 1,
    "area_m2": 25.0,
    "grade_area_m2": 25.0,
    "overhang_ratio": 0.0,
    "fill_ratio": 1.0,
    "class": "compact",
    "radius_m": None,
    "tile_cells": [1, 1],
    "snap_m": 0.25,
    "grade_band_m": [0.0, 0.5],
    "source": "measured",
    "version": 1,
}


# --- T5: projection guard (INV-7) --------------------------------------------


def record(**over):
    a = {
        "id": "SM_Bld_Test_01",
        "type": "building/shell",
        "semantic_role": "building_shell",
        "placeable": True,
        "bounds": {"size": [5.0, 3.0, 5.0]},
        "files": {"glb": "PACK/models/SM_Bld_Test_01.glb"},
        "module": {},
        "part": {},
        "footprint": dict(FOOTPRINT),
    }
    a.update(over)
    return a


def test_footprint_never_in_a_default_slim_row():
    """INV-7. A ring on every search hit would spend the token budget's
    remaining headroom on data no ranking step reads."""
    row = slim_row("PACK", record())
    assert "footprint" not in row
    assert "polygon_m" not in json.dumps(row)


def test_footprint_reachable_via_fields():
    row = slim_row("PACK", record(), fields=["footprint"])
    assert row["footprint"]["class"] == "compact"


def test_slim_row_stays_small_with_a_footprint_present():
    """The row's size must not move at all because a footprint exists."""
    with_fp = len(json.dumps(slim_row("PACK", record())))
    without = len(json.dumps(slim_row("PACK", record(footprint=None))))
    assert with_fp == without


def test_footprint_class_filter():
    keep = record()
    drop = record(footprint=dict(FOOTPRINT, **{"class": "radial"}))
    none = record(footprint=None)
    kw = dict(types=None, roles=None, module_roles=None, part_classes=None, include_nonplaceable=False)
    assert _match_v2_filters(keep, footprint_classes=["compact"], **kw)
    assert not _match_v2_filters(drop, footprint_classes=["compact"], **kw)
    assert not _match_v2_filters(none, footprint_classes=["compact"], **kw)
    assert _match_v2_filters(drop, footprint_classes=["radial", "compact"], **kw)


def test_no_footprint_filter_passes_everything():
    kw = dict(types=None, roles=None, module_roles=None, part_classes=None, include_nonplaceable=False)
    assert _match_v2_filters(record(footprint=None), footprint_classes=None, **kw)


# --- T4: CLI + report ---------------------------------------------------------


@pytest.fixture
def workspace(tmp_path):
    """A catalogs dir + a threejs-v2 root with one good and one broken GLB."""
    catalogs = tmp_path / "catalogs"
    catalogs.mkdir()
    threejs = tmp_path / "threejs-v2"
    models = threejs / "PACK" / "models"
    models.mkdir(parents=True)
    verts, tris = box_mesh([0, 0, 0], [5, 3, 5])
    write_mesh_glb(models / "SM_Good_01.glb", verts, tris)
    (models / "SM_Bad_01.glb").write_bytes(b"not a glb")

    doc = {
        "pack_id": "PACK",
        "engine": "Unity",
        "origin": "Synty",
        "style": "test",
        "units": "meters",
        "version": 2,
        "scanned_at": "2026-08-26T00:00:00+00:00",
        "grid": {"snap": 0.25, "module": 2.5, "tile": 5.0, "story": 3.0},
        "conventions": {"street_axis": "+z", "rotate_deg": 90, "scale": 1, "up_axis": "+y"},
        "asset_count": 3,
        "assets": [
            {"id": "SM_Good_01", "placeable": True, "files": {"glb": "PACK/models/SM_Good_01.glb"}},
            {"id": "SM_Bad_01", "placeable": True, "files": {"glb": "PACK/models/SM_Bad_01.glb"}},
            {"id": "CLIP_01", "placeable": False, "files": {}},
        ],
    }
    (catalogs / "PACK.json").write_text(json.dumps(doc), encoding="utf-8")
    return catalogs, threejs


def test_report_shape(workspace, capsys, monkeypatch):
    # The fixture is deliberately 50 % coverage (one good GLB, one broken),
    # so the threshold is lowered here; test_coverage_below_threshold_exits_4
    # is what pins the gate itself.
    code, report = _invoke(workspace, capsys, monkeypatch, "--dry-run", "--min-coverage", "0.4")
    assert code == 0
    pack = report["packs"][0]
    assert pack["pack_id"] == "PACK"
    assert pack["eligible"] == 2, "non-placeable records are not eligible"
    assert pack["measured"] == 1
    assert pack["undecodable"] == 1
    assert pack["class_histogram"] == {"compact": 1}
    assert report["footprint_version"] >= 1
    assert report["dry_run"] is True


def test_every_failure_row_has_a_detail(workspace, capsys, monkeypatch):
    """AC8's second clause: a shortfall without a reason is not reportable."""
    _, report = _invoke(workspace, capsys, monkeypatch, "--dry-run", "--min-coverage", "0.4")
    failures = report["packs"][0]["failures"]
    assert failures
    for row in failures:
        assert row["id"] and row["reason"] and row["detail"]


def test_dry_run_writes_no_catalog(workspace, capsys, monkeypatch):
    catalogs, _ = workspace
    before = (catalogs / "PACK.json").read_text(encoding="utf-8")
    _invoke(workspace, capsys, monkeypatch, "--dry-run", "--min-coverage", "0.4")
    assert (catalogs / "PACK.json").read_text(encoding="utf-8") == before
    assert not (catalogs / "_footprint_cache.json").exists()


def test_write_persists_footprint_and_cache(workspace, capsys, monkeypatch):
    catalogs, _ = workspace
    code, _ = _invoke(workspace, capsys, monkeypatch, "--min-coverage", "0.4")
    assert code == 0
    doc = json.loads((catalogs / "PACK.json").read_text(encoding="utf-8"))
    good = next(a for a in doc["assets"] if a["id"] == "SM_Good_01")
    assert good["footprint"]["area_m2"] == pytest.approx(25.0, abs=0.01)
    assert good["provenance"]["footprint"] == "measured"
    bad = next(a for a in doc["assets"] if a["id"] == "SM_Bad_01")
    assert bad["footprint"] is None
    clip = next(a for a in doc["assets"] if a["id"] == "CLIP_01")
    assert "footprint" not in clip, "non-placeable records stay untouched"
    assert (catalogs / "_footprint_cache.json").is_file()


def test_report_file_written(workspace, capsys, monkeypatch, tmp_path):
    dest = tmp_path / "out" / "fp.json"
    _invoke(workspace, capsys, monkeypatch, "--dry-run", "--report", str(dest), "--min-coverage", "0.4")
    assert json.loads(dest.read_text(encoding="utf-8"))["packs"][0]["pack_id"] == "PACK"


def test_coverage_below_threshold_exits_4(workspace, capsys, monkeypatch):
    code, report = _invoke(workspace, capsys, monkeypatch, "--dry-run", "--min-coverage", "0.99")
    assert code == 4
    assert report["packs"][0]["coverage"] == pytest.approx(0.5)


def test_unknown_pack_exits_2(workspace, capsys, monkeypatch):
    code, _ = _invoke(workspace, capsys, monkeypatch, "--pack", "NOPE", "--dry-run", "--min-coverage", "0.4")
    assert code == 2


def test_ids_restricts_scope(workspace, capsys, monkeypatch):
    _, report = _invoke(workspace, capsys, monkeypatch, "--dry-run", "--ids", "SM_Good_01", "--min-coverage", "0.4")
    assert report["packs"][0]["eligible"] == 1
    assert not report["packs"][0]["failures"]


def test_warm_run_decodes_nothing(workspace, capsys, monkeypatch):
    """AC6 through the CLI: the report's own decode counter proves it."""
    _invoke(workspace, capsys, monkeypatch, "--min-coverage", "0.4")
    _, report = _invoke(workspace, capsys, monkeypatch, "--min-coverage", "0.4")
    assert report["decodes"] == 0
    assert report["packs"][0]["cached"] >= 1


def _invoke(workspace, capsys, monkeypatch, *argv):
    """Drive the subcommand with config resolution stubbed to the fixture."""
    catalogs, threejs = workspace
    monkeypatch.setattr(cli, "_catalogs", lambda args, cfg: catalogs)
    monkeypatch.setattr(cli, "_threejs_v2", lambda cfg: threejs)

    parser_args = _parse(argv)
    code = cli.cmd_footprint(parser_args, {})
    out = capsys.readouterr().out
    return code, json.loads(out) if out.strip() else None


def _parse(argv):
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--pack", default=None)
    p.add_argument("--ids", default=None)
    p.add_argument("--rebuild", action="store_true")
    p.add_argument("--dry-run", dest="dry_run", action="store_true")
    p.add_argument("--report", default=None)
    p.add_argument("--min-coverage", dest="min_coverage", type=float, default=0.95)
    return p.parse_args(list(argv))
