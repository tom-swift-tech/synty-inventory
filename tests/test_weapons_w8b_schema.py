"""W8b: the ``geometry.mounts`` block in the directory schema (INV-15 to INV-18, D-9; docs/weapon_attachments.md 4.1).

``weapons validate --directory`` exits 0 on the good FAKE_Mount directory and 6 on each hand-broken variant. The slot,
source and reason names below are literals, not imports of the constants under test.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("w8a_attach", Path(__file__).parent / "fixtures" / "weapons" / "w8a_attach.py")
A = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A)

from synty_inventory.cli import main  # noqa: E402
from synty_inventory.weapons import guards  # noqa: E402
from synty_inventory.weapons.schema import validate_record  # noqa: E402

P = A.MOUNT_PACK
MOUNT, DOUBLE, PLAIN = (f"{P}/SM_Wep_Rifle_{n}_01" for n in ("Mount", "Double", "Plain"))
MUZZ, GRENADE = f"{P}/SM_Wep_Rifle_Muzz_01", f"{P}/SM_Wep_Grenade_Mount_01"


@pytest.fixture(autouse=True)
def _no_other_inventory_runner(monkeypatch):
    monkeypatch.setattr(guards, "other_inventory_processes", lambda: [])


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return A.build_mount_world(tmp_path_factory.mktemp("w8b_schema"))


def rec_of(doc, rid):
    return next(w for w in doc["weapons"] if w["id"] == rid)


def slot_of(doc, rid, slot):
    return rec_of(doc, rid)["geometry"]["mounts"][slot]


def validate_via_cli(tmp_path, monkeypatch, capsys, doc, excluded):
    for key in ("SYNTI_CONFIG", "SYNTI_UNITY_ROOT", "SYNTI_EXTRACTED_ROOT", "SYNTI_THREEJS_V2", "SYNTI_VIEWER_DATA",
                "SYNTI_CATALOGS", "SYNTI_GODOT_ROOT", "SYNTI_UNREAL_ROOT", "SYNTI_SYNTY_GLB_ROOT"):
        monkeypatch.delenv(key, raising=False)
    folder = tmp_path / "v"
    folder.mkdir(exist_ok=True)
    (folder / "directory.json").write_text(json.dumps(doc), encoding="utf-8")
    (folder / "excluded.json").write_text(json.dumps(excluded), encoding="utf-8")
    cfg = tmp_path / "config.yaml"
    cfg.write_text("\n".join([f'unity_root: "{tmp_path.as_posix()}/unity"', f'extracted_root: "{tmp_path.as_posix()}/extracted"',
                              f'catalogs: "{(tmp_path / "cat").as_posix()}"']) + "\n", encoding="utf-8")
    capsys.readouterr()
    code = main(["--config", str(cfg), "weapons", "validate", "--directory", str(folder / "directory.json")])
    return code, json.loads(capsys.readouterr().out)


def test_the_good_mount_directory_validates_with_exit_0(built, tmp_path, monkeypatch, capsys):
    code, out = validate_via_cli(tmp_path, monkeypatch, capsys, copy.deepcopy(built[0]), built[1])
    assert code == 0 and out["ok"] is True and out["directory"] == "ok", out


def test_every_built_record_passes_the_record_check(built):
    for rec in built[0]["weapons"]:
        assert validate_record(rec) == [], rec["id"]


def test_a_w7_record_without_the_mounts_key_is_still_valid(built):
    rec = copy.deepcopy(rec_of(built[0], MOUNT))
    del rec["geometry"]["mounts"]
    assert validate_record(rec) == []


# --- hand-broken variants, each exit 6 ------------------------------------------------------------------------------


def none_with_a_point(d):  # INV-15
    slot_of(d, PLAIN, "optic")["point"] = [0.0, 0.1, 0.0]


def none_without_a_reason(d):  # INV-15
    slot_of(d, PLAIN, "optic")["reason"] = None


def seated_with_a_null_point(d):  # INV-15, the other way round
    slot_of(d, MOUNT, "optic")["point"] = None


def occupied_by_on_a_none_slot(d):  # INV-16
    slot_of(d, PLAIN, "magazine")["occupied_by"] = ["SM_Wep_Rifle_Plain_01_Mag"]


def child_node_missing_from_occupied_by(d):  # INV-16
    slot_of(d, MOUNT, "optic")["occupied_by"] = ["Some_Other_Node"]


def occupied_by_not_sorted(d):  # INV-16
    slot_of(d, DOUBLE, "magazine")["occupied_by"] = list(reversed(slot_of(d, DOUBLE, "magazine")["occupied_by"]))


def up_not_a_unit_vector(d):  # INV-18
    slot_of(d, MOUNT, "optic")["up"] = [0.0, 2.0, 0.0]


def forward_not_orthogonal_to_up(d):  # INV-18
    slot_of(d, MOUNT, "optic")["forward"] = [0.0, 0.7071, 0.7071]


def mounts_null_on_a_host(d):  # D-9
    rec_of(d, MOUNT)["geometry"]["mounts"] = None


def mounts_on_a_grenade(d):  # D-9
    rec_of(d, GRENADE)["geometry"]["mounts"] = copy.deepcopy(rec_of(d, MOUNT)["geometry"]["mounts"])


def muzzle_off_the_a0_point(d):  # AC67 parity
    slot_of(d, MOUNT, "muzzle")["point"] = [0.0, 0.055, 0.651]


def muzzle_up_off_the_host_forward(d):
    slot_of(d, MOUNT, "muzzle")["up"] = [0.0, 1.0, 0.0]


def unknown_source(d):
    slot_of(d, MOUNT, "optic")["source"] = "guess"


def a_slot_missing(d):
    del rec_of(d, MOUNT)["geometry"]["mounts"]["laser_light"]


VARIANTS = {
    "none_with_a_point": (none_with_a_point, "INV-15"),
    "none_without_a_reason": (none_without_a_reason, "INV-15"),
    "seated_with_a_null_point": (seated_with_a_null_point, "INV-15"),
    "occupied_by_on_a_none_slot": (occupied_by_on_a_none_slot, "INV-16"),
    "child_node_missing_from_occupied_by": (child_node_missing_from_occupied_by, "INV-16"),
    "occupied_by_not_sorted": (occupied_by_not_sorted, "INV-16"),
    "up_not_a_unit_vector": (up_not_a_unit_vector, "not a unit vector"),
    "forward_not_orthogonal_to_up": (forward_not_orthogonal_to_up, "not orthogonal"),
    "mounts_null_on_a_host": (mounts_null_on_a_host, "D-9"),
    "mounts_on_a_grenade": (mounts_on_a_grenade, "D-9"),
    "muzzle_off_the_a0_point": (muzzle_off_the_a0_point, "geometry.muzzle exactly"),
    "muzzle_up_off_the_host_forward": (muzzle_up_off_the_host_forward, "axes.forward"),
    "unknown_source": (unknown_source, "geometry"),
    "a_slot_missing": (a_slot_missing, "geometry"),
}


def test_there_are_at_least_six_variants():
    assert len(VARIANTS) >= 6


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_each_hand_broken_variant_exits_6_with_its_own_message(name, built, tmp_path, monkeypatch, capsys):
    mutate, message = VARIANTS[name]
    doc = copy.deepcopy(built[0])
    mutate(doc)
    code, out = validate_via_cli(tmp_path, monkeypatch, capsys, doc, built[1])
    assert code == 6 and out["ok"] is False and out["directory"] == "invalid", out
    assert any(message in e for e in out["directory_errors"]), out["directory_errors"]


def test_the_probe_muzzle_with_a_brake_may_list_occupied_by(built):
    # the INV-16 exception: the muzzle slot of a probe source carries the baked device node names
    d = copy.deepcopy(built[0])
    assert slot_of(d, MUZZ, "muzzle")["source"] == "probe" and slot_of(d, MUZZ, "muzzle")["occupied_by"]
    assert validate_record(rec_of(d, MUZZ)) == []
