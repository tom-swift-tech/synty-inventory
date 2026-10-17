"""Weapon directory W5: ``files.glb_scale`` survives the threejs export and its validator (AC26 amendment, AC37).

The exported geometry is measured after ``glb_scale``, but the GLB on disk is not scaled, so a threejs consumer needs
the factor to size the mesh. ``--engine threejs`` therefore keeps ``glb_scale`` (when the record has one) next to
``glb`` and ``glb_node``; godot and unity snapshots never carry it; ``validate --snapshot`` accepts it under the glb
engine filter (and ``all``) and rejects it anywhere else.

The fixture records get a non-1.0 ``glb_scale`` in memory, after the directory is built: the weapon/1 JSON schema
(weapons/schema.py, not part of this slice) types every ``files.*`` value as null/string/list, so a numeric scale
cannot yet pass ``write_directory`` or the ``export`` verb's directory load. The export function and the snapshot
validator are what AC37 specifies and are tested directly. Bounds are literals.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

_spec = importlib.util.spec_from_file_location(
    "review_helpers", Path(__file__).parent / "fixtures" / "weapons" / "review_helpers.py")
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)
wfx = H.wfx

from synty_inventory.weapons import export as X  # noqa: E402
from synty_inventory.weapons import to_text  # noqa: E402

SCALED = {H.SWORD_02: 0.01, H.SWORD_01: 2.5}  # two records with a non-1.0 glb_scale
PLAIN = "FAKE_Fantasy/SM_Wep_Axe_01"  # a record of the same pack without one


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("scale")
    cat = H.make_catalogs(tmp)
    root = H.make_threejs(tmp, cat)
    directory, _ = H.build(cat, threejs_v2_dir=root)
    directory = copy.deepcopy(directory)
    for rec in directory["weapons"]:
        if rec["id"] in SCALED:
            rec["files"]["glb_scale"] = SCALED[rec["id"]]
    return SimpleNamespace(tmp=tmp, directory=directory, cfg=H.write_config(tmp, cat), n=iter(range(1, 10**6)))


def snapshot(world, engines: set[str], *, frame: str = "item") -> dict:
    d = world.directory
    return X.export_snapshot(
        d, game="district7", pack_ids={"FAKE_Fantasy"}, ids=None, roles={"whole"}, engines=engines, frame=frame,
        profile="private", pack_meta={p["pack"]: p for p in d["packs"]}, rules_digest=d["rules_digest"],
        overrides_digest=d["overrides_digest"])


def files(doc: dict) -> dict[str, dict]:
    return {w["id"]: w["files"] for w in doc["weapons"]}


def write(world, doc: dict) -> Path:
    path = world.tmp / f"snap_{next(world.n)}.json"
    path.write_bytes(to_text(doc).encode("utf-8"))
    return path


def validate(world, capsys, path: Path):
    return H.run(world.cfg, capsys, ["weapons", "validate", "--snapshot", str(path)])


# --- export: which engines keep the scale --------------------------------------------------------------------------


def test_the_fixture_records_really_carry_a_non_unit_scale(world):
    by_id = wfx.records_by_id(world.directory)
    assert by_id[H.SWORD_02]["files"]["glb_scale"] == 0.01 and by_id[H.SWORD_01]["files"]["glb_scale"] == 2.5
    assert "glb_scale" not in by_id[PLAIN]["files"]


def test_threejs_keeps_glb_scale_with_glb_and_glb_node(world):
    f = files(snapshot(world, {"threejs"}))
    assert f[H.SWORD_02] == {"glb": "glb/FAKE_Fantasy/SM_Wep_Sword_02.glb", "glb_node": None, "glb_scale": 0.01}
    assert f[H.SWORD_01]["glb_scale"] == 2.5
    assert f[PLAIN] == {"glb": "glb/FAKE_Fantasy/SM_Wep_Axe_01.glb", "glb_node": None}  # no scale, none invented


@pytest.mark.parametrize("engine", ["godot", "unity"])
def test_godot_and_unity_never_carry_the_scale(world, engine):
    for key_set in files(snapshot(world, {engine})).values():
        assert "glb_scale" not in key_set and "glb" not in key_set


def test_all_keeps_every_key_including_the_scale(world):
    f = files(snapshot(world, {"all"}))
    assert f[H.SWORD_02]["glb_scale"] == 0.01 and "godot_scene" in f[H.SWORD_02] and "unity_prefab" in f[H.SWORD_02]


def test_the_scale_is_copied_unchanged_in_both_frames(world):
    for frame in ("item", "asset"):
        assert files(snapshot(world, {"threejs"}, frame=frame))[H.SWORD_02]["glb_scale"] == 0.01


# --- validate --snapshot ------------------------------------------------------------------------------------------


def test_validate_accepts_the_scale_under_the_glb_filter_and_all(world, capsys):
    for engines in ({"threejs"}, {"all"}):
        code, out = validate(world, capsys, write(world, snapshot(world, engines)))
        assert (code, out["ok"], out["errors"]) == (0, True, []), (engines, out)


def test_validate_accepts_a_hand_written_scale_under_the_threejs_filter(world, capsys):
    doc = snapshot(world, {"threejs"})
    for w in doc["weapons"]:
        w["files"]["glb_scale"] = 0.01  # written here, not by the exporter: the validator alone decides
    code, out = validate(world, capsys, write(world, doc))
    assert (code, out["ok"], out["errors"]) == (0, True, [])


def test_validate_rejects_the_scale_in_godot_and_unity_snapshots(world, capsys):
    for engine, keep in (("godot", "godot_scene"), ("unity", "unity_prefab")):
        doc = snapshot(world, {engine})
        assert keep in doc["weapons"][0]["files"]
        for w in doc["weapons"]:
            if w["id"] == H.SWORD_02:
                w["files"]["glb_scale"] = 0.01  # a hand-edited snapshot
        code, out = validate(world, capsys, write(world, doc))
        assert code == 6 and out["ok"] is False
        assert any("glb_scale" in e and "outside the engine filter" in e for e in out["errors"]), (engine, out)


def test_validate_rejects_a_scale_that_is_not_a_positive_number(world, capsys):
    for bad in (0, -1.5, "0.01", True, None):
        doc = snapshot(world, {"threejs"})
        for w in doc["weapons"]:
            if w["id"] == H.SWORD_02:
                w["files"]["glb_scale"] = bad
        code, out = validate(world, capsys, write(world, doc))
        assert code == 6 and any("glb_scale" in e and "greater than 0" in e for e in out["errors"]), (bad, out)


def test_the_scale_check_does_not_hide_other_record_errors(world, capsys):
    doc = snapshot(world, {"threejs"})
    for w in doc["weapons"]:
        if w["id"] == H.SWORD_02:
            w["archetype"] = "not_an_archetype"
    code, out = validate(world, capsys, write(world, doc))
    assert code == 6 and any("archetype" in e for e in out["errors"]) and not any("glb_scale" in e for e in out["errors"])


def test_old_snapshots_without_a_scale_still_validate(world, capsys):
    doc = snapshot(world, {"threejs"})
    for w in doc["weapons"]:
        w["files"].pop("glb_scale", None)
    code, out = validate(world, capsys, write(world, doc))
    assert (code, out["errors"]) == (0, [])
    assert json.loads(Path(write(world, doc)).read_text(encoding="utf-8"))["schema_version"] == 1
