"""G1 S5 and errata E1.1: the bore detector (docs/weapon_attach_geometry.md 3.6, AC135 fixture part, AC138 barrel-end part).

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
* ``barrel_od_max_m`` 0.060 -> 0.080: ``test_the_od_cap`` goes red;
* E1.1, ``circ_min`` 0.75 -> 0.60 in ``RULES`` (or the hull test dropped from (iii)): ``test_a_square_end_gives_none`` goes red (the square, hull
  ratio 0.637, reads as a round section);
* E1.1, ``circ_min`` 0.75 -> 0.85: ``test_a_hexagonal_and_an_octagonal_end_are_round_sections`` goes red (the hexagon, 0.827, is lost).
* E2-Q2 (errata E2.6), the ring rule left out of ``mounts.bore_diameter``: the rod and the centre-bin fixtures go red; the rule aligned with
  ``end_ring_d``'s 0.75: the thin-wall tube goes red; a rule that calls an end solid when its outermost bin holds 6 or more points: the tube goes red;
  "two bins of six": the square face goes red.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "weapons"))
import g1_bore_meshes as M  # noqa: E402

from synty_inventory.weapons import fit_geometry, geometry, mounts  # noqa: E402
from synty_inventory.weapons.fit_bore import barrel_end, device_inner_d  # noqa: E402
from synty_inventory.weapons.mount_probe import end_ring_d  # noqa: E402

_spec = importlib.util.spec_from_file_location("g1_world", Path(__file__).resolve().parent / "fixtures" / "weapons" / "g1_world.py")
GW = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(GW)

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
        "end_slab_m": 0.010, "round_min": 0.8, "circ_min": 0.75, "barrel_od_max_m": 0.060, "od_ratio": [0.85, 2.00], "inner_ratio": [0.47, 1.21],
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
    # 0.050 x 0.030: roundness 0.6, the flat-cut end the extent ratio alone rejects
    assert find(M.box(0.0, 0.50, 0.025, 0.015)) is None


def test_a_square_end_gives_none():
    # E1.1: 0.040 x 0.040 has extent ratio 1.0 and OD 0.0566 (its diagonal), so the extent ratio and the OD cap both pass it; the hull fills
    # 0.637 of its circle, under 0.75. Today it reads `round_section`. (A mount with a ring bore still proves its own end, see below.)
    assert find(M.box(0.0, 0.50, 0.020, 0.020)) is None
    assert find(M.box(0.0, 0.50, 0.010, 0.010)) is None  # the size does not matter, the ratio is scale free
    assert find(M.box(0.0, 0.50, 0.020, 0.020), {"bore_source": None}) is None


def test_a_square_end_on_a_mount_with_a_ring_bore_is_still_the_mounts_ring():
    # evidence (i) is checked first and never reads the hull: the mount's A0 probe found a ring, the slab still gives the OD (the diagonal)
    end = find(M.box(0.0, 0.50, 0.020, 0.020), RING)
    assert end is not None and end.evidence == "ring"
    assert end.od_m == pytest.approx(0.0566, abs=0.0005)


@pytest.mark.parametrize("n", [6, 8])
def test_a_hexagonal_and_an_octagonal_end_are_round_sections(n):
    # E1.1 guard against an over-tight circ_min: hull ratios 0.827 (hexagon) and 0.900 (octagon), radius 15 mm
    end = find(M.tube(0.0, 0.50, 0.015, n=n))
    assert end is not None and end.evidence == "round_section"
    assert end.od_m == pytest.approx(0.030, abs=0.0005)
    assert end.centre_su == pytest.approx((0.0, 0.0), abs=1e-4)
    assert end.face_f == pytest.approx(0.50, abs=1e-4)


def test_a_hexagonal_end_is_found_whatever_the_vertex_order():
    mesh = M.tube(0.0, 0.50, 0.015, n=6)
    first = find(mesh)
    assert first is not None
    for seed in (1, 2, 3):
        assert find(M.shuffled(mesh, seed)) == first


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


# -- E2-Q2: a ring needs two radii (errata E2.6, AC135) ----------------------------------------------------------------------
# Each mount comes from the probe path (geometry.muzzle_probe, then mounts.bore_diameter on its face, as mounts._muzzle_mount runs it), never a
# hand-set bore_source. The meshes are asset coordinates (z forward, y up), as the rod rifle is.
ASSET_AXES = {"forward": "+z", "up": "+y"}


def probe_bore(verts):
    """``(bore_d_m, bore_source)`` of the A0 face of ``verts``."""
    _point, _source, face = geometry.muzzle_probe(verts, "+z", "+y")
    return mounts.bore_diameter(face, 2)


def muzzle_features(mesh):
    """``(bore_d_m, bore_source, host_features)`` of a host mesh whose muzzle mount is the probe's."""
    point, _source, face = geometry.muzzle_probe(mesh[0], "+z", "+y")
    bore, bore_source = mounts.bore_diameter(face, 2)
    muzzle = {**mounts.none_mount("x"), "source": "probe", "point": point, "reason": None, "bore_d_m": bore, "bore_source": bore_source}
    mts = {"muzzle": muzzle, **{slot: mounts.none_mount("no_child_no_probe") for slot in ("optic", "underbarrel", "magazine")}}
    feats = fit_geometry.host_features(RULES, axes=ASSET_AXES, mounts=mts, mesh=lambda drop: mesh, child_mesh=lambda name: None)
    return bore, bore_source, feats


def face_points(radii_and_counts, z=0.5):
    """Points of a muzzle face (z forward) at the given radii around the origin, plus one vertex 0.2 m behind it (not in the face)."""
    pts = [[r * np.cos(2.0 * np.pi * k / n), r * np.sin(2.0 * np.pi * k / n), z] for r, n in radii_and_counts for k in range(n)]
    return np.array(pts + [[0.0, 0.0, z - 0.2]])


def test_e2_q2_a_solid_round_rod_has_no_ring_bore_and_is_barrel_round():
    # The solid 32-sided rod (radius 8.5 mm, a fan to one centre vertex): 32 points in the 8 mm bin, the centre alone in bin 0, nothing beyond the rim.
    # Before E2-Q2 that read as a ring (0.017, "ring"), evidence (i), barrel_ring. Now it is the face extent, and end_ring_d finds no ring (the rim is
    # the outer radius), so (iii) calls it a round section.
    rod = GW.rod_rifle()
    bore, bore_source, feats = muzzle_features(rod)
    assert (bore, bore_source) == (0.017, "face_extent")
    assert end_ring_d(rod[0][:, [2, 0, 1]], 0, 1, 0.010) is None
    end = feats["slots"]["muzzle"]["barrel_end"]
    assert (end["evidence"], feats["seats"]["muzzle"]) == ("round_section", {"feature": "barrel_round"})
    assert end["od_m"] == pytest.approx(0.017, abs=5e-4)


def test_e2_q2_a_lone_ring_of_six_points_near_the_centre_with_a_rim_is_the_face_extent():
    # The estimator unit case: 6 points within 1 mm of the centre (bin 0, the centre bin, never a ring) and a 12-point rim at 10 mm. The rim bin
    # holds 12 points but nothing lies beyond it. Before E2-Q2 the bin 0 six read as a ring: bore_d_m 0.001.
    assert probe_bore(face_points([(0.0005, 6), (0.010, 12)])) == (0.020, "face_extent")


def test_e2_q2_guard_a_thin_wall_tube_keeps_its_ring():
    # A GUARD: it passes on the base (fbb5c52) and cannot fail there, because the base reads every bin of six as a ring, a true bore included.
    # It guards the rule against over-reach. OD 20 mm, modelled bore 16 mm (bore/OD 0.8, outside end_ring_d's 0.75): the bore bin has the outer
    # rim beyond it, so it is a ring, evidence (i), barrel_ring. The rule aligned with end_ring_d's 0.75, or "solid when the outermost bin
    # holds 6 or more", would fail it.
    tube = GW.fsu_to_xyz(M.tube(0.0, 0.25, 0.010, 0.008))
    bore, bore_source, feats = muzzle_features(tube)
    assert (bore, bore_source) == (0.016, "ring")
    assert end_ring_d(tube[0][:, [2, 0, 1]], 0, 1, 0.010) is None  # (ii) cannot rescue it: only the mount's ring proves this end
    end = feats["slots"]["muzzle"]["barrel_end"]
    assert (end["evidence"], feats["seats"]["muzzle"]) == ("ring", {"feature": "barrel_ring"})


def test_e2_q2_guard_a_ring_inside_a_sparse_square_outline_keeps_its_ring():
    # A GUARD: it passes on the base and cannot fail there, for the same reason. A 12-point ring at 6.5 mm inside a 30 x 30 mm square face of
    # four corners: the outline beyond the ring is sparse (4 points in one bin, under 6), but a point lies beyond the ring, so it is a ring.
    # The "two bins of six" reading would fail it.
    corners = [[sx * 0.015, su * 0.015, 0.5] for sx in (-1, 1) for su in (-1, 1)]
    verts = np.concatenate([face_points([(0.0065, 12)])[:-1], np.array(corners), [[0.0, 0.0, 0.3]]])
    assert probe_bore(verts) == (0.013, "ring")
