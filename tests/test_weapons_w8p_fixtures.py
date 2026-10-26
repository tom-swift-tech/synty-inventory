"""W8p: consumer fixture parity with ``sit_weapons`` 0.4.0 (docs/weapon_attachments.md 13.9; AC130).

``mount_place.json`` and ``muzzle_golden.json`` are byte-for-byte copies (line endings normalised, so a CRLF checkout counts) of the files of the
sit-capabilities repo at commit ``96810c713d89c64ce04e7f6953159c08a23d67f8`` (``addons/sit_weapons/fixtures/mount_place.json`` and
``tools/probes/muzzle_golden.json``). The sha256 values below are LITERALS read from that commit; a stale copy fails here. If the directory's own placement
code cannot reproduce a case, the case is reported to the lead and never edited.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from synty_inventory.weapons import preview
from synty_inventory.weapons.attach import place
from synty_inventory.weapons.geometry import muzzle_point

FIX = Path(__file__).parent / "fixtures" / "weapons"
SC_COMMIT = "96810c713d89c64ce04e7f6953159c08a23d67f8"
MOUNT_PLACE_SHA256 = "43c8cf3b76d358caae34015482fac2e820e9b0adae0818c1d1b2c71cb529482e"
MUZZLE_GOLDEN_SHA256 = "b263e7804ce086f84da7485188943ef39e8bf60ce4d5c7e94b2b2e9320c42374"
SIBLING = Path("D:/Projects/games/sit-capabilities")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def angle_deg(a, b) -> float:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return float(np.degrees(np.arccos(np.clip(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)), -1.0, 1.0))))


def test_ac130_both_fixtures_are_the_copies_of_the_0_4_0_commit():
    assert sha(FIX / "mount_place.json") == MOUNT_PLACE_SHA256
    assert sha(FIX / "muzzle_golden.json") == MUZZLE_GOLDEN_SHA256


@pytest.mark.skipif(not (SIBLING / "addons/sit_weapons/fixtures/mount_place.json").is_file(), reason="the sibling repo is not on this machine; the pins above carry the gate")
def test_ac130_the_copies_equal_the_sibling_working_files_when_it_is_present():
    assert sha(FIX / "mount_place.json") == sha(SIBLING / "addons/sit_weapons/fixtures/mount_place.json")
    assert sha(FIX / "muzzle_golden.json") == sha(SIBLING / "tools/probes/muzzle_golden.json")


def test_ac130_mount_place_carries_the_six_cases_with_the_two_new_seat_offsets():
    doc = json.loads((FIX / "mount_place.json").read_text(encoding="utf-8"))
    names = [c["name"] for c in doc["cases"]]
    assert names == ["muzzle_identity", "optic_part_authored_on_its_side", "underbarrel_hangs_down", "three_cycle", "optic_shift", "muzzle_setback"]
    cases = {c["name"]: c for c in doc["cases"]}
    assert cases["optic_shift"]["seat_offset_m"] == 0.005 and cases["optic_shift"]["origin"] == [0.01, 0.045, 0.18]
    assert cases["muzzle_setback"]["seat_offset_m"] == -0.04 and cases["muzzle_setback"]["origin"] == [0, 0.05, 0.46]
    assert all("seat_offset_m" not in cases[n] for n in names[:4])  # the four A-series cases are unchanged


@pytest.mark.parametrize("name", ["optic_shift", "muzzle_setback"])
def test_ac130_the_directorys_own_placement_reproduces_the_two_new_cases(name):
    """Both ways the directory places a pair: ``attach.place`` plus the offset along the host frame's up (tolerances are the file's own, 0.5 mm / 0.1 degree)
    and ``preview.build_job`` with the offset carried as the entry's ``seat_shift_m`` (positive) or ``seat_setback_m`` (negative)."""
    doc = json.loads((FIX / "mount_place.json").read_text(encoding="utf-8"))
    case = next(c for c in doc["cases"] if c["name"] == name)
    tol_m, tol_deg = doc["tolerance_m"], doc["tolerance_deg"]
    offset = case["seat_offset_m"]
    m = place(case["part"], case["host"])
    m[:3, 3] += offset * np.asarray(case["host"]["up"], dtype=float)
    assert np.allclose(m[:3, 3], case["origin"], atol=tol_m, rtol=0)
    for k, column in enumerate(case["basis"]):
        assert angle_deg(m[:3, k], column) <= tol_deg, (name, k)
    entry = {"host": "h", **({"seat_shift_m": offset} if offset > 0 else {"seat_setback_m": -offset})}
    part = {"attachment": {"anchor": case["part"], "compatible_hosts": [entry]}, "files": {"glb": "p.glb", "glb_node": None}}
    host = {"geometry": {"mounts": {"optic": case["host"]}, "item_basis": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}, "files": {"glb": "h.glb", "glb_node": None}}
    pair = {"part": "p", "host": "h", "slot": "optic", "tier": "twin", "score": 1.0, "twin": True}
    job = np.asarray(preview.build_job(pair, part, host, Path("."))["matrix"])
    assert np.allclose(job[:3, 3], case["origin"], atol=tol_m, rtol=0)
    for k, column in enumerate(case["basis"]):
        assert angle_deg(job[:3, k], column) <= tol_deg, (name, k)


def test_ac130_the_muzzle_golden_is_the_0_4_0_one_and_the_python_muzzle_point_matches_every_case():
    doc = json.loads((FIX / "muzzle_golden.json").read_text(encoding="utf-8"))
    assert doc["schema"] == "sit_muzzle_golden/1" and doc["source"]["version"] == "0.4.0"
    assert [c["name"] for c in doc["cases"]] == ["plain", "inflated_bounds", "edge2_widened", "edge3_face", "cone_apex"]
    for case in doc["cases"]:
        point, source = muzzle_point(case["vertices"], "+z", "+y")
        assert np.allclose(point, case["muzzle"], atol=0.0005, rtol=0), case["name"]
        assert (source == "bounds_fallback") == bool(case["fallback"]), case["name"]
