"""W8b: the muzzle mount (AC67, AC84; docs/weapon_attachments.md 4.1 probe, D-3, R1, C-22).

Every expected number is a literal worked out from the synthetic meshes of ``fixtures/weapons/w8a_attach.py`` (a round
barrel ending at z 0.65 with a bore ring of radius 6.5 mm, a baked brake from z 0.65 to 0.73), never read from the code
under test.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("w8a_attach", Path(__file__).parent / "fixtures" / "weapons" / "w8a_attach.py")
A = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A)

from synty_inventory.weapons import geometry as geo  # noqa: E402
from synty_inventory.weapons.rules import load_rules  # noqa: E402

P = A.MOUNT_PACK


def _id(n):
    return f"{P}/SM_Wep_Rifle_{n}_01"


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    directory, _, _, root = A.build_mount_world(tmp_path_factory.mktemp("w8b_muzzle"))
    return {w["id"]: w for w in directory["weapons"]}, root


def geom(world, n):
    return world[0][_id(n)]["geometry"]


def muzzle(world, n):
    return geom(world, n)["mounts"]["muzzle"]


def close(got, want, tol):
    assert len(got) == len(want) and all(abs(g - w) <= tol for g, w in zip(got, want)), (got, want)


# --- AC67 -------------------------------------------------------------------------------------------------------------


def test_ac67_with_no_baked_device_the_mount_point_is_the_a0_muzzle_exactly(world):
    for n in ("Mount", "Double", "Plain", "Fall", "Tilt", "Hull", "Shared"):
        g = geom(world, n)
        m = g["mounts"]["muzzle"]
        assert m["occupied_by"] == [], n
        assert m["point"] == g["muzzle"], n  # exactly, not within a tolerance
        assert g["axes"]["forward"] == "+z" and m["up"] == [0.0, 0.0, 1.0], n  # up is the unit vector of axes.forward
        assert m["source"] == "probe" and m["child_node"] is None and m["reason"] is None


def test_ac67_the_a0_muzzle_itself_is_the_barrel_end_of_the_fixture(world):
    close(geom(world, "Mount")["muzzle"], (0.0, 0.055, 0.65), 1e-4)  # literal: the barrel ends at z 0.65, centred at y 0.055
    close(geom(world, "Plain")["muzzle"], (0.0, 0.055, 0.65), 1e-4)


def test_ac67_the_mount_frame_is_orthonormal_and_forward_is_perpendicular_to_up(world):
    m = muzzle(world, "Mount")
    f, u = m["forward"], m["up"]
    assert abs(sum(a * a for a in f) - 1.0) <= 1e-6 and abs(sum(a * a for a in u) - 1.0) <= 1e-6
    assert abs(sum(a * b for a, b in zip(f, u))) <= 1e-6


def test_ac67_a_ring_fixture_gives_the_bore_diameter_within_one_millimetre(world):
    m = muzzle(world, "Mount")
    assert m["bore_source"] == "ring" and abs(m["bore_d_m"] - 0.0130) <= 1e-3  # bore ring r 6.5 mm; the outer ring would say 25 mm
    assert m["confidence"] == 0.8
    assert abs(muzzle(world, "Double")["bore_d_m"] - 0.0130) <= 1e-3


def test_ac67_a_ring_less_fixture_gives_the_face_extent_at_confidence_05(world):
    m = muzzle(world, "Plain")
    assert m["bore_source"] == "face_extent" and abs(m["bore_d_m"] - 0.0283) <= 1e-3  # four corners at r 14.14 mm
    assert m["confidence"] == 0.5
    assert "muzzle_fallback" not in world[0][_id("Plain")]["review"]["reasons"]


def test_ac67_a_bounds_fallback_gives_confidence_04_and_the_muzzle_fallback_reason(world):
    r = world[0][_id("Fall")]
    m = r["geometry"]["mounts"]["muzzle"]
    assert m["source"] == "probe" and m["confidence"] == 0.4 and m["bore_d_m"] is None and m["bore_source"] is None
    assert "muzzle_fallback" in r["review"]["reasons"]
    assert m["point"] == r["geometry"]["muzzle"]  # still parity with A0, even for the fallback


def test_ac67_the_ring_estimator_needs_six_points_and_reads_the_innermost_ring():
    import numpy as np

    from synty_inventory.weapons import mounts as M

    def ring(r, n, z=0.0):
        return [(r * np.cos(2 * np.pi * k / n), r * np.sin(2 * np.pi * k / n), z) for k in range(n)]

    got = M.bore_diameter(np.array(ring(0.02, 12) + ring(0.005, 8)), 2)
    assert got[1] == "ring" and abs(got[0] - 0.010) <= 1e-3
    assert M.bore_diameter(np.array(ring(0.005, 5)), 2)[1] == "face_extent"  # five points cannot make a ring
    assert M.bore_diameter(np.array(ring(0.005, 6)), 2)[1] == "ring"


def test_ac67_the_muzzle_probe_is_the_one_a0_function_not_a_second_algorithm(world):
    # the point the mount carries equals the point a direct call of the A0 entry returns for the same mesh
    root = world[1]
    glb = root / "glb/FAKE_Mount/SM_Wep_Rifle_Mount_01.glb"
    d = geo.measure_weapon_detail(glb, None, 1.0, "rifle", "ranged", "whole", load_rules(),
                                  hold_class="long_gun", genre="modern", with_mounts=True)
    assert d["mounts"]["muzzle"]["point"] == d["geometry"]["muzzle"]


# --- AC84 -------------------------------------------------------------------------------------------------------------


def test_ac84_a_baked_brake_is_listed_and_the_seat_is_the_barrel_end(world):
    m = muzzle(world, "Muzz")
    assert m["occupied_by"] == ["SM_Wep_Rifle_Muzz_01_Brake"]  # INV-16: the muzzle slot may carry a probe with occupied_by
    assert m["source"] == "probe"
    close(m["point"], (0.0, 0.055, 0.65), 5e-4)  # the A0 probe of the mesh minus the brake: the barrel end


def test_ac84_the_seat_sits_behind_the_device_face_by_the_brake_length(world):
    g = geom(world, "Muzz")
    close(g["muzzle"], (0.0, 0.055, 0.73), 1e-3)  # geometry.muzzle is still the bare-gun W7 value, the face of the brake
    behind = g["muzzle"][2] - g["mounts"]["muzzle"]["point"][2]
    assert abs(behind - 0.08) <= 1e-3


def test_ac84_the_seat_matches_a_host_without_the_brake_and_that_host_has_exact_parity(world):
    bare = geom(world, "Mount")
    assert muzzle(world, "Mount")["point"] == bare["muzzle"] and muzzle(world, "Mount")["occupied_by"] == []
    close(muzzle(world, "Muzz")["point"], bare["muzzle"], 5e-4)  # the same barrel with and without the baked device


def test_ac84_the_geometry_block_is_unchanged_by_the_mounts(world):
    # the brake stays part of the measured gun: the W7 bounds still reach its face
    assert abs(geom(world, "Muzz")["bounds"]["max"][2] - 0.73) <= 1e-3
    assert abs(geom(world, "Mount")["bounds"]["max"][2] - 0.65) <= 1e-3
