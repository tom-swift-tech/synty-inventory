"""T7: the additive-only guarantee (spec AC7 / INV-6)."""

from __future__ import annotations

import copy
import json
import os
import zipfile
from pathlib import Path

from synty_inventory.tools.diff_catalog import (
    DEFAULT_ALLOWED,
    diff_asset,
    diff_catalogs,
    load_side,
    main,
    walk,
)

FOOTPRINT = {
    "polygon_m": [[0.0, 0.0], [5.0, 0.0], [5.0, 5.0], [0.0, 5.0]],
    "area_m2": 25.0,
    "class": "compact",
    "source": "measured",
    "version": 1,
}


def asset(aid="SM_A_01"):
    return {
        "id": aid,
        "name": "Thing",
        "tags": ["a", "b"],
        "bounds": {"size": [5.0, 3.0, 5.0], "pivot": "corner", "source": "measured"},
        "module": {"family": "Apartment", "role": "floor"},
        "provenance": {"name": "vlm_reviewed"},
        "_auto": {"name": "abc123"},
    }


def catalog(*assets):
    return {"pack_id": "PACK", "version": 2, "assets": list(assets)}


def enriched(a):
    """What the footprint pass is allowed to do to a record."""
    out = copy.deepcopy(a)
    out["footprint"] = copy.deepcopy(FOOTPRINT)
    out["provenance"]["footprint"] = "measured"
    out["_auto"]["footprint"] = "def456"
    return out


# --- walk / diff_asset --------------------------------------------------------


def test_walk_yields_nested_paths():
    paths = dict(walk(asset()))
    assert "provenance.name" in paths
    assert "bounds.size" in paths
    assert paths["module.role"] == "floor"


def test_lists_compare_whole():
    """A reordered list is a change. For a catalog that is what we want."""
    a = asset()
    b = copy.deepcopy(a)
    b["tags"] = ["b", "a"]
    assert [d["kind"] for d in diff_asset(a, b)] == ["changed"]


def test_enriched_record_is_all_additions():
    deltas = diff_asset(asset(), enriched(asset()))
    assert {d["kind"] for d in deltas} == {"added"}
    assert sorted(d["path"] for d in deltas) == [
        "_auto.footprint",
        "footprint.area_m2",
        "footprint.class",
        "footprint.polygon_m",
        "footprint.source",
        "footprint.version",
        "provenance.footprint",
    ]


# --- diff_catalogs ------------------------------------------------------------


def test_footprint_pass_passes():
    before = {"PACK": catalog(asset("SM_A_01"), asset("SM_B_01"))}
    after = {"PACK": catalog(enriched(asset("SM_A_01")), enriched(asset("SM_B_01")))}
    report = diff_catalogs(before, after)
    assert report["ok"] is True
    assert report["records"] == 2
    assert report["allowed_additions"] == 14
    assert report["violations"] == []


def test_null_footprint_is_a_single_allowed_addition():
    a = asset()
    b = copy.deepcopy(a)
    b["footprint"] = None
    report = diff_catalogs({"PACK": catalog(a)}, {"PACK": catalog(b)})
    assert report["ok"] is True
    assert report["allowed_additions"] == 1


def test_any_other_added_field_is_a_violation():
    a = asset()
    b = copy.deepcopy(a)
    b["street_side"] = "+z"
    report = diff_catalogs({"PACK": catalog(a)}, {"PACK": catalog(b)})
    assert report["ok"] is False
    assert report["violations"][0]["path"] == "street_side"


def test_changed_existing_field_is_a_violation():
    a = asset()
    b = enriched(asset())
    b["module"]["role"] = "roof"
    report = diff_catalogs({"PACK": catalog(a)}, {"PACK": catalog(b)})
    assert report["ok"] is False
    assert [v["path"] for v in report["violations"]] == ["module.role"]


def test_removed_field_is_a_violation():
    a = asset()
    b = enriched(asset())
    del b["name"]
    report = diff_catalogs({"PACK": catalog(a)}, {"PACK": catalog(b)})
    assert report["ok"] is False
    assert any(v["kind"] == "removed" and v["path"] == "name" for v in report["violations"])


def test_changing_a_footprint_is_still_a_violation():
    """Allowed means allowed to be ADDED. Overwriting a footprint that was
    already there is the pass trampling a prior value."""
    a = enriched(asset())
    b = copy.deepcopy(a)
    b["footprint"]["area_m2"] = 99.0
    report = diff_catalogs({"PACK": catalog(a)}, {"PACK": catalog(b)})
    assert report["ok"] is False
    assert report["violations"][0]["path"] == "footprint.area_m2"


def test_dropped_or_added_record_is_a_violation():
    before = {"PACK": catalog(asset("SM_A_01"), asset("SM_B_01"))}
    after = {"PACK": catalog(enriched(asset("SM_A_01")))}
    report = diff_catalogs(before, after)
    assert report["ok"] is False
    assert report["packs"][0]["ids_only_before"] == ["SM_B_01"]


def test_missing_pack_is_a_violation():
    report = diff_catalogs({"PACK": catalog(asset())}, {})
    assert report["ok"] is False
    assert report["packs_only_before"] == ["PACK"]


def test_allowed_paths_are_configurable():
    a = asset()
    b = copy.deepcopy(a)
    b["street_side"] = "+z"
    assert diff_catalogs({"PACK": catalog(a)}, {"PACK": catalog(b)}, ("street_side",))["ok"]


# --- load_side ----------------------------------------------------------------


def test_reads_from_a_zip_and_skips_the_v1_baseline(tmp_path):
    """The backup archive carries an Aug-19 v1 snapshot alongside the live
    catalogs; diffing against that would produce thousands of false deltas."""
    zpath = tmp_path / "backup.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("synty_catalogs/PACK.json", json.dumps(catalog(asset())))
        z.writestr("synty_catalogs/index.json", json.dumps({"totals": {}}))
        z.writestr("synty_catalogs/_baseline_v1/PACK.json", json.dumps(catalog(asset("OLD_01"))))
    side = load_side(zpath)
    assert list(side) == ["PACK"]
    assert [a["id"] for a in side["PACK"]["assets"]] == ["SM_A_01"]


def test_reads_from_a_directory(tmp_path):
    (tmp_path / "PACK.json").write_text(json.dumps(catalog(asset())), encoding="utf-8")
    (tmp_path / "index.json").write_text(json.dumps({"totals": {}}), encoding="utf-8")
    assert list(load_side(tmp_path)) == ["PACK"]


# --- CLI ----------------------------------------------------------------------


def test_cli_exit_codes(tmp_path, capsys):
    before = tmp_path / "before"
    after = tmp_path / "after"
    before.mkdir()
    after.mkdir()
    (before / "PACK.json").write_text(json.dumps(catalog(asset())), encoding="utf-8")
    (after / "PACK.json").write_text(json.dumps(catalog(enriched(asset()))), encoding="utf-8")

    report_path = tmp_path / "report.json"
    assert main(["--before", str(before), "--after", str(after), "--report", str(report_path)]) == 0
    capsys.readouterr()
    assert json.loads(report_path.read_text(encoding="utf-8"))["ok"] is True

    bad = copy.deepcopy(enriched(asset()))
    bad["name"] = "Renamed"
    (after / "PACK.json").write_text(json.dumps(catalog(bad)), encoding="utf-8")
    assert main(["--before", str(before), "--after", str(after)]) == 1
    capsys.readouterr()


def test_default_allowed_is_the_three_paths():
    assert DEFAULT_ALLOWED == ("footprint", "provenance.footprint", "_auto.footprint")


def test_real_backup_shape_if_present():
    """Smoke the operator's actual archive when SYNTI_CATALOGS points at a
    machine that has one. Path comes from the environment, never the source
    (tests/test_paths.py forbids machine paths in this repo)."""
    root = os.environ.get("SYNTI_CATALOGS")
    if not root:
        return
    zpath = Path(root).with_suffix(".zip")
    if not zpath.is_file():
        return
    side = load_side(zpath)
    assert side
    assert all("_baseline_v1" not in p for p in side)
