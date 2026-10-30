"""E3.22: the two S12 pose fixes (docs/weapon_attach_geometry_errata.md E3.22, ACs 150 and 151).

Pure synthetic fixtures, no catalog and no directory build. Every expected value is a LITERAL worked out from the fixture dimensions below, never
read from the module under test; the fixture bounds are this file's own numbers, not the rule's constants.

AC150 (step 3c, the raked foregrip's forward). Every fixture has its foot plate at +y, its larger end section at +z and its free end leaning toward
+z. A 6 mm neck separates the foot plate from the body: a body that touches the 4 mm foot slab drags the slab midpoint and reads the lean under 10 mm.

Step 3c applies to PARTS only: a kind is passed and it is not a bipod. A host's baked child, measured without a kind, keeps step 3.
(Measured on the base, v14: the raked-foregrip case is red; the bipod and the non-raked cases are green controls.)

AC151 (the closed tip step, A6-2). Suppressor fixture length L = 0.120 m. Bin convention: a run's front and rear are measured from the tip at the
bins' lower edges. The 50 mm run's bins have lower edges -0.050 to -0.002 m, so its front is 0.002 and its rear 0.050.

The 8 mm shroud case, as measured (red-first, E3.22): it is green on v14 (no key is written there) and green on the full three-clause rule, and red
only with clause (iii), the closed-step test, removed: with clauses (i) and (ii) alone the 50 mm run plus a wide bin 8 mm behind its rear face
writes 0.055, and the test fails with "assert 0.055 is None". The 50 mm closed run is red on v14 (Obtained: None, expected 0.055 +- 0.002); the 30 mm
device is a v14-value control (0.040 on v14 and on the rule).
"""

from __future__ import annotations

import numpy as np
import pytest

from synty_inventory.weapons import attach
from synty_inventory.weapons.rules import load_rules

PLUS_Z, MINUS_Z = [0.0, 0.0, 1.0], [0.0, 0.0, -1.0]


# --- AC150 ------------------------------------------------------------------------------------------------------------


def _box(x0, x1, y0, y1, z0, z1, d=0.002):
    g = lambda a, b: np.linspace(a, b, max(2, int(round((b - a) / d)) + 1))  # noqa: E731
    X, Y, Z = np.meshgrid(g(x0, x1), g(y0, y1), g(z0, z1), indexing="ij")
    return np.c_[X.ravel(), Y.ravel(), Z.ravel()]


def underbarrel_fixture(lean):
    """Foot plate at +y (y 0.036 to 0.040, centred on z = 0), a 6 mm neck (y 0.030 to 0.036), then the body (y -0.040 to 0.030) whose free end
    (-y) leans to +z by ``lean``. The body is 30 mm long in z, centred on the lean; its +z 65 % is the wide (larger) end section, its -z 35 % narrow."""
    plate = _box(-0.01, 0.01, 0.036, 0.040, -0.015, 0.015)
    neck = _box(-0.004, 0.004, 0.030, 0.036, -0.005, 0.005)
    z0, z1 = lean - 0.015, lean + 0.015
    third = z0 + (z1 - z0) * 0.35
    narrow = _box(-0.004, 0.004, -0.040, 0.030, z0, third)
    wide = _box(-0.012, 0.012, -0.040, 0.030, third, z1)
    return np.vstack([plate, neck, narrow, wide])


def _anchor(v, kind):
    a = attach.measure_anchor(v, "underbarrel", None, kind=kind)["anchor"]
    return a["forward"], a["forward_source"], a["symmetric"]


def test_ac150_a_raked_foregrip_with_a_15_mm_lean_takes_forward_minus_z_from_the_free_end():
    assert _anchor(underbarrel_fixture(0.015), "foregrip") == (MINUS_Z, "free_end", False)


def test_ac150_a_bipod_with_the_same_lean_keeps_plus_z_from_the_free_end_step_3b():
    assert _anchor(underbarrel_fixture(0.015), "bipod") == (PLUS_Z, "free_end", False)


def test_ac150_a_non_raked_foregrip_with_a_5_mm_lean_keeps_plus_z_from_the_section():
    assert _anchor(underbarrel_fixture(0.005), "foregrip") == (PLUS_Z, "section", False)


# --- AC151 ------------------------------------------------------------------------------------------------------------

L = 0.120
BIN, RANGE, AHEAD = 0.002, 0.30, 0.10  # this file's literals: the silhouette's bin, the reach behind the tip and the reach past it
N_BINS = 200
BARREL_R, WIDE_R = 0.010, 0.025  # 2.5x the barrel: wide against ref_ratio 1.4
NEW_KEYS = {"tip_front_m": 0.010, "tip_rear_margin_m": 0.010, "step_clear_bins": 5}  # the rule's three keys, as the errata states them


def _params():
    p = dict(load_rules()["attachment_rules"]["muzzle_seat"])
    assert (p["bin_m"], p["range_m"]) == (BIN, RANGE)  # the fixture's bin arithmetic is for these
    p.update(NEW_KEYS)  # a build before E3.22 ignores them
    return p


def _silhouette(run_lo, run_hi, extra=()):
    """Barrel up to the bin whose lower edge is 0 (the tip), wide bins with lower edges ``run_lo`` .. ``run_hi`` (m from the tip, negative behind)
    inclusive, plus single wide bins at the lower edges in ``extra``; nothing beyond the tip bin."""
    idx = lambda s: int(round((s + RANGE) / BIN))  # noqa: E731
    sil = np.zeros(N_BINS)
    sil[: idx(0.0) + 1] = BARREL_R
    for j in range(idx(run_lo), idx(run_hi) + 1):
        sil[j] = WIDE_R
    for s in extra:
        sil[idx(s)] = WIDE_R
    return sil


def _setback(sil):
    p = _params()
    got = attach.muzzle_stub(sil, p)
    assert got is not None
    stub, near = got
    return attach.setback_of(stub, near, L, p)


def test_ac151_a_50_mm_closed_tip_run_writes_seat_setback_055():
    # run front 0.002, rear 0.050, a step down to the barrel behind it, no other wide bin: a device at any length.
    # d = min(stub 0.060, max(0.4 * 0.120 = 0.048, 0.050 + 0.005 = 0.055), 0.75 * 0.120 = 0.090) = 0.055
    assert _setback(_silhouette(-0.050, -0.002)) == pytest.approx(0.055, abs=0.002)


def test_ac151_a_30_mm_tip_device_writes_seat_setback_040():
    # a device by the length cut already (30 mm < 45 mm): stub = rear 0.030 + 0.010 = 0.040 binds
    assert _setback(_silhouette(-0.030, -0.002)) == pytest.approx(0.040, abs=0.002)


def test_ac151_the_same_50_mm_run_with_a_wide_bin_8_mm_behind_its_rear_face_is_a_shroud_and_writes_no_key():
    # the bin's lower edge is -0.058: 8 mm behind the rear face (-0.050), inside step_clear_bins (5 bins = 10 mm), outside the single-bin bridge (< 6 mm).
    # The run does not end in a step, so the length cut stands: it is the shroud, the stub is its front 0.002, under dead_m (0.003): no key.
    assert _setback(_silhouette(-0.050, -0.002, extra=[-0.058])) is None
