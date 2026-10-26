"""W8c placement: AC69 (the placement maths, twin ground truth, the shared oracle) and AC70 (no intrusion).

docs/weapon_attachments.md 4.3 (C-21) and 11. ``place(anchor, mount) = T(mount) * T(anchor)^-1``.

Shared oracle provenance. ``tests/fixtures/weapons/mount_place.json`` is a byte-for-byte copy (sha256 pinned below) of
``addons/sit_weapons/fixtures/mount_place.json`` of the sit-capabilities repo (D:/Projects/games/sit-capabilities), branch
``build/sit-weapons-T4W4``, commit ``5cd92cd40ed67d8c68794e65c992a443f9cc1aa5``, copied on 2026-10-22; refreshed on 2026-10-26 (W8p, AC130)
from sit-capabilities ``96810c713d89c64ce04e7f6953159c08a23d67f8`` (``sit_weapons`` 0.4.0), which added ``optic_shift`` and ``muzzle_setback``.
No case is edited here; a disagreement with the oracle is reported to the lead, never fixed in the copy. The file carries six cases (the spec
names the first three; DM-B added ``three_cycle``, the only one whose rotation is not its own transpose; 0.4.0 added the two ``seat_offset_m``
cases), and every case in the file is run, whatever their number. ``seat_offset_m`` is a translation along the host frame's ``up`` applied after
``place`` (positive = the pair's ``seat_shift_m``, negative = minus its ``seat_setback_m``; ``preview.build_job`` does the same arithmetic).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8c_compat", FIX / "w8c_compat.py")
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)

from synty_inventory.weapons.attach import place  # noqa: E402

ORACLE_PATH = FIX / "mount_place.json"
ORACLE_SHA256 = "43c8cf3b76d358caae34015482fac2e820e9b0adae0818c1d1b2c71cb529482e"  # sit-capabilities 96810c7 (W8p, AC130)
ORACLE = json.loads(ORACLE_PATH.read_text(encoding="utf-8"))
TOL_M, TOL_DEG = 0.0005, 0.1  # literals: 0.5 mm and 0.1 degrees (AC69)

# (part, host, slot, child suffix) and the child's AABB in the host frame, worked out by hand from the fixture meshes:
#   optic() spans x -0.03..0.03, y 0..0.08, z -0.1..0.1; mag_box x +-0.01, y -0.12..0, z +-0.02; flip_y(optic()) y -0.08..0;
#   upside_down_optic() x +-0.015, y 0..0.03, z +-0.06; the brake tube r 0.0125 about (x 0, y 0.055), z 0.65..0.73
SLOT_CASES = {
    "optic": (W.SCOPE, W.ALPHA, ((-0.03, 0.10, 0.0), (0.03, 0.18, 0.20))),  # optic() at (0, 0.10, 0.10)
    "magazine": (W.MAG, W.ALPHA, ((-0.01, -0.12, -0.07), (0.01, 0.0, -0.03))),  # mag_box at (0, 0, -0.05)
    "underbarrel": (W.GRIP, W.GAMMA, ((-0.03, -0.08, -0.07), (0.03, 0.0, 0.13))),  # flip_y(optic()) at (0, 0, 0.03)
    "laser_light": (W.LASER, W.GAMMA, ((-0.015, -0.03, -0.06), (0.015, 0.0, 0.06))),  # upside_down_optic() at (0, -0.03, 0)
    "muzzle": (W.SIL_BRAKE, W.EPSILON, ((-0.0125, 0.0425, 0.65), (0.0125, 0.0675, 0.73))),  # the brake tube, no offset
}
BODY = (np.array([-0.02, 0.0, -0.25]), np.array([0.02, 0.10, 0.35]))  # the host body box of every fixture host


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return W.build(tmp_path_factory.mktemp("w8c_place"))[0]


def angle_deg(a, b) -> float:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return float(np.degrees(np.arccos(np.clip(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)), -1.0, 1.0))))


def placed(directory, slot, anchor_shift_m: float = 0.0):
    """``(placed part vertices, anchor, mount, matrix)`` for the twin pair of ``slot``; the anchor point can be shifted along its up."""
    part, host, _ = SLOT_CASES[slot]
    recs = W.by_id(directory)
    anchor = dict(recs[W.P[part]]["attachment"]["anchor"])
    mount = recs[W.H[host]]["geometry"]["mounts"][slot]
    anchor["point"] = list(np.asarray(anchor["point"]) + anchor_shift_m * np.asarray(anchor["up"]))
    matrix = place(anchor, mount)
    verts, _ = W.PART_MESHES[part]()
    return (np.c_[verts, np.ones(len(verts))] @ matrix.T)[:, :3], anchor, mount, matrix


# --- the shared oracle ----------------------------------------------------------------------------------------------


def test_the_oracle_copy_is_byte_for_byte_the_committed_file():
    assert hashlib.sha256(ORACLE_PATH.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == ORACLE_SHA256  # autocrlf-proof
    assert ORACLE["schema"] == "sit_mount_place/1"
    assert (ORACLE["tolerance_m"], ORACLE["tolerance_deg"]) == (TOL_M, TOL_DEG)


def test_the_oracle_holds_the_three_named_cases_of_the_spec():
    assert {"muzzle_identity", "optic_part_authored_on_its_side", "underbarrel_hangs_down"} <= {c["name"] for c in ORACLE["cases"]}


def test_ac130_the_oracle_carries_the_two_seat_offset_cases_of_sit_weapons_0_4_0():
    cases = {c["name"]: c for c in ORACLE["cases"]}
    assert {"optic_shift", "muzzle_setback"} <= set(cases)
    assert (cases["optic_shift"]["seat_offset_m"], cases["muzzle_setback"]["seat_offset_m"]) == (0.005, -0.04)


@pytest.mark.parametrize("case", ORACLE["cases"], ids=lambda c: c["name"])
def test_ac69_place_reproduces_every_case_of_the_oracle(case):
    m = place(case["part"], case["host"])
    m[:3, 3] += case.get("seat_offset_m", 0.0) * np.asarray(case["host"]["up"], dtype=float)  # sit_weapons 0.4.0 (AC130)
    assert np.allclose(m[:3, 3], case["origin"], atol=TOL_M, rtol=0)
    for k, column in enumerate(case["basis"]):  # `basis` lists the COLUMNS of the part transform
        assert angle_deg(m[:3, k], column) <= TOL_DEG, (case["name"], k)
    assert np.allclose(m[3], [0, 0, 0, 1])


# --- the directory's own cases: every slot --------------------------------------------------------------------------


@pytest.mark.parametrize("slot", sorted(SLOT_CASES))
def test_ac69_place_maps_the_anchor_onto_the_mount_for_every_slot(built, slot):
    _, anchor, mount, m = placed(built, slot)
    assert np.allclose((m @ np.append(anchor["point"], 1.0))[:3], mount["point"], atol=TOL_M, rtol=0)
    for key in ("up", "forward"):
        assert angle_deg(m[:3, :3] @ anchor[key], mount[key]) <= TOL_DEG, key


@pytest.mark.parametrize("slot", sorted(SLOT_CASES))
def test_ac69_the_standalone_twin_lands_on_the_baked_child(built, slot):
    verts, *_ = placed(built, slot)
    child = (np.array(SLOT_CASES[slot][2][0]), np.array(SLOT_CASES[slot][2][1]))
    part = W.aabb(verts)
    assert np.all(np.abs((part[0] + part[1]) / 2 - (child[0] + child[1]) / 2) <= 0.003)
    assert W.iou(part, child) >= 0.90


# --- AC70: no intrusion into the host body ---------------------------------------------------------------------------


def penetration_m(verts, mount) -> float:
    """How far the part reaches behind the contact plane (against the mount's up)."""
    return max(0.0, float(np.max((np.asarray(mount["point"]) - verts) @ np.asarray(mount["up"]))))


def overlap_fraction(verts, mount) -> float:
    """Volume of the part's AABB beyond its 4 mm foot slab that lies inside the host body box, over the AABB volume."""
    lo, hi = W.aabb(verts)
    up, point = np.asarray(mount["up"]), np.asarray(mount["point"])
    axis = int(np.argmax(np.abs(up)))
    if up[axis] > 0:
        lo = lo.copy()
        lo[axis] = max(lo[axis], point[axis] + 0.004)
    else:
        hi = hi.copy()
        hi[axis] = min(hi[axis], point[axis] - 0.004)
    free = (lo, hi)
    full = float(np.prod(W.aabb(verts)[1] - W.aabb(verts)[0]))
    inter = np.clip(np.minimum(free[1], BODY[1]) - np.maximum(free[0], BODY[0]), 0.0, None)
    return float(np.prod(inter)) / full


@pytest.mark.parametrize("slot", sorted(SLOT_CASES))
def test_ac70_a_fit_attachment_does_not_intrude(built, slot):
    verts, _, mount, _ = placed(built, slot)
    assert penetration_m(verts, mount) <= 0.003
    assert overlap_fraction(verts, mount) <= 0.05


@pytest.mark.parametrize("slot", sorted(SLOT_CASES))
def test_ac70_the_check_has_teeth_a_10_mm_anchor_shift_intrudes(built, slot):
    verts, _, mount, _ = placed(built, slot, anchor_shift_m=0.01)
    assert penetration_m(verts, mount) == pytest.approx(0.01, abs=1e-6)
    assert penetration_m(verts, mount) > 0.003
