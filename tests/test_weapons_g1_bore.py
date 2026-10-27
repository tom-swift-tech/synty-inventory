"""G1 S5: the bore detector (docs/weapon_attach_geometry.md 3.6, AC135 fixture part, AC138 barrel-end part).

``fit_bore.barrel_end`` finds the barrel end of a host mesh, ``fit_bore.device_inner_d`` the inner ring of a muzzle device's mating face. The
band tests go through ``fit_geometry.verdict`` fed the detector's own output, so the bands are exercised on measured values.

Every bound below is a literal of this file: ``RULES`` is a copy of the spec 4.1 block (not loaded from ``weapon_rules.yaml``), and no number is
imported from the module under test (AC137).

Deliberate breaks, in a scratch copy of the branch (reported with the slice):
* measuring the unreduced mesh (the baked device's face read as the barrel): ``test_a_baked_device_is_not_read_as_the_barrel`` goes red when
  ``reduced`` is replaced by ``unreduced``;
* ``od_ratio`` lo 0.85 -> 0.80 or hi 2.00 -> 2.10 in ``RULES``: ``test_the_od_ratio_band`` goes red;
* ``inner_ratio`` lo 0.47 -> 0.40 or hi 1.21 -> 1.30: ``test_the_inner_ratio_band`` goes red;
* ``round_min`` 0.8 -> 0.5: ``test_a_rectangular_end_gives_none`` and ``test_the_roundness_edge`` go red;
* ``barrel_od_max_m`` 0.060 -> 0.080: ``test_the_od_cap`` goes red.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "weapons"))
import g1_bore_meshes as M  # noqa: E402

from synty_inventory.weapons import fit_geometry  # noqa: E402
from synty_inventory.weapons.fit_bore import barrel_end, device_inner_d  # noqa: E402

# A literal copy of the spec 4.1 block (attachment_rules.fit_geometry).
RULES = {
    "slots": ["optic", "muzzle", "underbarrel", "magazine"],
    "locator": {"grid_m": 0.0005, "sample_n": 24, "hit_min": 1.0, "merge_m": 0.002},
    "rail": {
        "window_m": 0.010, "bin_m": 0.0005, "tooth_amp_min_m": 0.0008, "tooth_merge_m": 0.0025, "pitch_min_m": 0.005,
        "pitch_max_m": 0.040, "pitch_cv_max": 0.25, "tooth_min_count": 4, "tooth_h_tol_m": 0.0015, "zone": [0.15, 0.85],
        "default_seat_len_m": 0.20, "sight_clear_m": 0.010,
    },
    "flat": {"band_m": 0.005, "close_m": 0.015, "min_m": 0.060},
    "clamp": {"overhang_max_m": 0.010, "ratio_min": 1.0},
    "depth": {"lo_m": -0.026, "hi_m": 0.003},
    "bore": {
        "end_slab_m": 0.010, "round_min": 0.8, "barrel_od_max_m": 0.060, "od_ratio": [0.85, 2.00], "inner_ratio": [0.47, 1.21],
        "axis_offset_max_m": 0.005, "axis_tilt_max_deg": 2,
    },
    "well": {"entry_depth_m": 0.002, "tol": 0.15},
    "exceptions": [],
}
RING = {"bore_source": "ring"}
NO_RING = {"bore_source": "face_extent"}


def find(mesh, mount=NO_RING, rules=RULES):
    return barrel_end(mesh[0], mesh[1], mount, rules)


def feats_of(end):
    return {"barrel_end": None if end is None else {"od_m": end.od_m, "evidence": end.evidence}}


def part(mate, inner=None):
    return {"anchor_measured": True, "mate_d_m": mate, "device_inner_d": inner}


# -- the ends the detector finds (AC135, fixture) ------------------------------------------------------------------


def test_a_ringed_end_is_found_with_its_od():
    end = find(M.tube(0.0, 0.50, 0.015, inner_r=0.006))
    assert end is not None
    assert end.evidence == "face_ring"
    assert end.od_m == pytest.approx(0.030, abs=0.0005)
    assert end.face_f == pytest.approx(0.50, abs=1e-4)
    assert end.centre_su == pytest.approx((0.0, 0.0), abs=1e-4)


def test_a_round_end_is_found_with_its_od_and_centre():
    end = find(M.tube(0.0, 0.50, 0.012, centre=(0.004, -0.003)))
    assert end is not None
    assert end.evidence == "round_section"
    assert end.od_m == pytest.approx(0.024, abs=0.0005)
    assert end.centre_su == pytest.approx((0.004, -0.003), abs=0.0005)
    assert end.face_f == pytest.approx(0.50, abs=1e-4)


def test_the_mounts_ring_bore_is_the_first_evidence():
    # (i) wins over (ii) and (iii): the mount's bore_source says the A0 probe found a ring, the slab still gives the OD.
    for mesh in (M.tube(0.0, 0.50, 0.015, inner_r=0.006), M.tube(0.0, 0.50, 0.015)):
        end = find(mesh, RING)
        assert end is not None and end.evidence == "ring"
        assert end.od_m == pytest.approx(0.030, abs=0.0005)


@pytest.mark.parametrize("mount", [None, {}, {"bore_source": None}, {"bore_source": "face_extent"}])
def test_a_mount_without_a_ring_bore_does_not_claim_one(mount):
    end = find(M.tube(0.0, 0.50, 0.015), mount)
    assert end is not None and end.evidence == "round_section"


def test_a_rectangular_end_gives_none():
    # 0.050 x 0.030: roundness 0.6. (A box with equal sides reads as round under the spec rule, see the report; this is the flat-cut end.)
    assert find(M.box(0.0, 0.50, 0.025, 0.015)) is None


def test_a_70_mm_round_end_gives_none():
    assert find(M.tube(0.0, 0.50, 0.035)) is None


def test_the_od_cap():
    inside = find(M.tube(0.0, 0.50, 0.0295))  # OD 0.059
    assert inside is not None and inside.evidence == "round_section"
    assert inside.od_m == pytest.approx(0.059, abs=0.0005)
    assert find(M.tube(0.0, 0.50, 0.0305)) is None  # OD 0.061


def test_the_roundness_edge():
    # extents 0.040 x 0.0316 (roundness 0.79) is out, 0.040 x 0.0324 (0.81) is in; OD is the larger extent
    assert find(M.tube(0.0, 0.50, (0.020, 0.0158))) is None
    end = find(M.tube(0.0, 0.50, (0.020, 0.0162)))
    assert end is not None and end.evidence == "round_section"
    assert end.od_m == pytest.approx(0.040, abs=0.0005)


def test_an_empty_mesh_has_no_end():
    assert barrel_end(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), RING, RULES) is None


# -- the reduced mesh (AC135 break: a baked device's face read as the barrel) --------------------------------------------


def test_a_baked_device_is_not_read_as_the_barrel():
    # The caller hands in the host minus the baked device. The barrel's own end is the barrel end.
    h = M.host_with_baked_device("round")
    end = find(h["reduced"])
    assert end is not None
    assert end.evidence == "round_section"
    assert end.od_m == pytest.approx(0.030, abs=0.0005)
    assert end.face_f == pytest.approx(0.40, abs=1e-4)


def test_a_baked_device_on_a_host_without_a_barrel_end_gives_none():
    h = M.host_with_baked_device("box")
    assert find(h["reduced"]) is None


def test_the_unreduced_mesh_reads_the_device_face_as_the_barrel():
    # Why the caller must reduce: the same detector on the unreduced mesh measures the device (OD 0.045 at f 0.55), on both hosts.
    for body in ("round", "box"):
        end = find(M.host_with_baked_device(body)["unreduced"])
        assert end is not None
        assert end.evidence == "face_ring"
        assert end.od_m == pytest.approx(0.045, abs=0.0005)
        assert end.face_f == pytest.approx(0.55, abs=1e-4)


def test_vertices_no_triangle_uses_do_not_count():
    # A reduction that leaves the device's vertices in the array but drops its triangles: the orphans are not the host.
    h = M.host_with_baked_device("round")
    end = barrel_end(h["unreduced"][0], h["reduced"][1], NO_RING, RULES)
    assert end is not None
    assert end.od_m == pytest.approx(0.030, abs=0.0005)
    assert end.face_f == pytest.approx(0.40, abs=1e-4)


# -- determinism (spec 4.3) ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("mesh_args", [((0.0, 0.5, 0.015), {"inner_r": 0.006}), ((0.0, 0.5, 0.015), {})])
def test_vertex_order_does_not_change_the_result(mesh_args):
    args, kwargs = mesh_args
    mesh = M.tube(*args, **kwargs)
    first = find(mesh)
    assert first is not None
    for seed in (1, 2, 3):
        assert find(M.shuffled(mesh, seed)) == first


def test_stored_measures_are_rounded_to_a_tenth_of_a_millimetre():
    end = find(M.tube(0.0, 0.50123456, 0.0123456, centre=(0.0041234, -0.0031234)))
    assert end is not None
    for x in (*end.centre_su, end.face_f, end.od_m):
        assert x == round(x, 4)


# -- the muzzle verdict on the detector's own output (AC135 bands, AC138) --------------------------------------------------


@pytest.mark.parametrize(
    ("mate", "expected"),
    [(0.0252, "no_fit"), (0.0258, "fit"), (0.0597, "fit"), (0.0603, "no_fit")],  # ratios 0.84, 0.86, 1.99, 2.01 on an OD of 0.030
)
def test_the_od_ratio_band(mate, expected):
    for mesh, mount in ((M.tube(0.0, 0.50, 0.015, inner_r=0.006), NO_RING), (M.tube(0.0, 0.50, 0.015), NO_RING), (M.tube(0.0, 0.50, 0.015), RING)):
        end = find(mesh, mount)
        assert fit_geometry.verdict("muzzle", feats_of(end), part(mate), None, RULES).value == expected


@pytest.mark.parametrize(
    ("inner_d", "expected"),
    [(0.0138, "no_fit"), (0.0144, "fit"), (0.0360, "fit"), (0.0366, "no_fit")],  # inner/OD 0.46, 0.48, 1.20, 1.22 on an OD of 0.030
)
def test_the_inner_ratio_band(inner_d, expected):
    end = find(M.tube(0.0, 0.50, 0.015, inner_r=0.006))
    anchor = {"up": [0.0, 1.0, 0.0]}
    measured = device_inner_d(M.device_mesh(0.080, inner_d), anchor, RULES)
    assert measured == pytest.approx(inner_d, abs=0.0001)
    assert fit_geometry.verdict("muzzle", feats_of(end), part(0.045, measured), None, RULES).value == expected


def test_a_device_without_an_inner_ring_is_judged_on_the_od_ratio_alone():
    end = find(M.tube(0.0, 0.50, 0.015, inner_r=0.006))
    assert device_inner_d(M.device_mesh(0.045, None), {"up": [0.0, 1.0, 0.0]}, RULES) is None
    assert fit_geometry.verdict("muzzle", feats_of(end), part(0.045, None), None, RULES).value == "fit"


def test_the_verdict_signals_follow_the_evidence():
    ring = find(M.tube(0.0, 0.50, 0.015, inner_r=0.006))
    round_end = find(M.tube(0.0, 0.50, 0.015))
    mounted = find(M.tube(0.0, 0.50, 0.015), RING)
    assert fit_geometry.verdict("muzzle", feats_of(ring), part(0.045), None, RULES).signals == ("barrel_ring",)
    assert fit_geometry.verdict("muzzle", feats_of(round_end), part(0.045), None, RULES).signals == ("barrel_round",)
    assert fit_geometry.verdict("muzzle", feats_of(mounted), part(0.045), None, RULES).signals == ("barrel_ring",)


def test_a_host_with_no_barrel_end_gives_no_fit_for_muzzle():
    # AC138, barrel-end part
    for mesh in (M.box(0.0, 0.50, 0.025, 0.015), M.tube(0.0, 0.50, 0.035), M.host_with_baked_device("box")["reduced"]):
        end = find(mesh)
        assert end is None
        verdict = fit_geometry.verdict("muzzle", feats_of(end), part(0.030), None, RULES)
        assert (verdict.value, verdict.signals) == ("no_fit", ())


# -- device_inner_d ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("axis", "sign"), [(0, 1), (0, -1), (1, 1), (1, -1), (2, 1), (2, -1)])
def test_the_inner_ring_is_read_on_the_mating_face_whichever_the_bore_direction(axis, sign):
    up = [0.0, 0.0, 0.0]
    up[axis] = float(sign)
    d = device_inner_d(M.device_mesh(0.060, 0.020, axis, sign), {"up": up}, RULES)
    assert d == pytest.approx(0.020, abs=0.0001)


def test_the_far_end_of_the_device_is_not_the_mating_face():
    # `up` points from the mating face to the free end: reversed, the estimator looks at the solid far end and finds no ring.
    assert device_inner_d(M.device_mesh(0.060, 0.020, 1, 1), {"up": [0.0, -1.0, 0.0]}, RULES) is None


def test_a_ring_too_close_to_the_edge_is_the_edges_own_circle():
    # inner 0.040 in an OD 0.050 device: 0.80 of the outer radius, outside the 0.75 rule of the shared estimator
    assert device_inner_d(M.device_mesh(0.050, 0.040), {"up": [0.0, 1.0, 0.0]}, RULES) is None


@pytest.mark.parametrize("anchor", [None, {}, {"up": None}, {"up": [0.0, 0.0, 0.0]}, {"up": [0.7, 0.7, 0.0]}])
def test_an_unusable_anchor_gives_none(anchor):
    assert device_inner_d(M.device_mesh(0.060, 0.020), anchor, RULES) is None


def test_device_inner_d_of_an_empty_mesh_is_none():
    assert device_inner_d(np.zeros((0, 3)), {"up": [0.0, 1.0, 0.0]}, RULES) is None
