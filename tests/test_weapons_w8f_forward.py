"""W8f part B: a twin corrects its part's forward (docs/weapon_attachments.md 3.4 step 3a, amendment A1, AC86).

Worlds ``rev``, ``dis`` and ``muz`` of ``fixtures/weapons/w8f_world.py`` (hand-derived numbers in its docstring), built through the
whole directory pipeline. Literals are worked out from the meshes: optic() is x -0.03..0.03, y 0..0.08, z -0.1..0.1 with its
foot centre at (0.005, 0, 0.05) and the flare at +z, so its z-mirror has the flare at -z and the foot centre at (0.005, 0, -0.05).
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import numpy as np
import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8f_world", FIX / "w8f_world.py")
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)

import synty_inventory.weapons as pkg  # noqa: E402
from synty_inventory.weapons import compat, preview  # noqa: E402
from synty_inventory.weapons.attach import measure_anchor  # noqa: E402
from synty_inventory.weapons.rules import load_rules, weapon_rules_digest  # noqa: E402

SCOPE, OVR, DRUM, SCOPE_TILT = (W.ID[n] for n in (W.SCOPE_REV, W.SCOPE_OVR, W.DRUM, W.SCOPE_TILT))
REV, TILT, DIS_U, DIS_Y, MUZ = (W.ID[n] for n in (W.REV, W.TILT, W.DIS_U, W.DIS_Y, W.MUZ))
SCOPE_DIS, BRAKE = W.ID[W.SCOPE_DIS], W.ID[W.BRAKE]
OVERRIDES = W.overrides_doc(ids={OVR: {"forward": "-z"}})


def make(tmp_path_factory, name, **kw):
    cache: dict = {}
    directory, excluded, cat, root = W.build(tmp_path_factory.mktemp(f"w8f_{name}"), name, cache=cache, **kw)
    return {"directory": directory, "by_id": W.by_id(directory), "root": root, "cache": cache, "overrides": kw.get("overrides")}


@pytest.fixture(scope="module")
def rev(tmp_path_factory):
    return make(tmp_path_factory, "rev", overrides=OVERRIDES)


@pytest.fixture(scope="module")
def dis(tmp_path_factory):
    return make(tmp_path_factory, "dis")


@pytest.fixture(scope="module")
def muz(tmp_path_factory):
    return make(tmp_path_factory, "muz")


def anchor_of(world, part):
    return world["by_id"][part]["attachment"]["anchor"]


def foot_of(world, part):
    return world["by_id"][part]["attachment"]["footprint"]


def tier_of(world, part, host):
    return next(e["tier"] for e in world["by_id"][part]["attachment"]["compatible_hosts"] if e["host"] == host)


def placed_box(world, part, host, mesh):
    pair = next(p for p in preview.plan_pairs(world["directory"], ids={part})[0] if p["host"] == host)
    job = preview.build_job(pair, world["by_id"][part], world["by_id"][host], world["root"])
    verts = mesh[0]
    return W.aabb((np.c_[verts, np.ones(len(verts))] @ np.asarray(job["matrix"]).T)[:, :3]), job


def assert_lands_on(box, want_lo, want_hi):
    want = (np.array(want_lo), np.array(want_hi))
    assert np.all(np.abs((box[0] + box[1]) / 2 - (want[0] + want[1]) / 2) <= 0.0001), (box, want)  # centre <= 0.1 mm
    assert W.iou(box, want) >= 0.99


# --- case 2: the section prior picked the rear ------------------------------------------------------------------------


def test_a_reversed_part_is_corrected_to_its_hosts_forward_and_its_footprint_is_unchanged(rev):
    assert anchor_of(rev, SCOPE) == {
        "point": [0.005, 0.0, -0.05], "forward": [0.0, 0.0, 1.0], "up": [0.0, 1.0, 0.0],
        "foot_source": "authored_up", "forward_source": "twin", "symmetric": False}
    # a sign flip alone changes no number
    assert foot_of(rev, SCOPE) == {"length_m": 0.2, "width_m": 0.06, "height_m": 0.08, "foot_length_m": 0.06,
                                   "foot_width_m": 0.02, "mate_d_m": None}


def test_the_corrected_part_lands_on_its_twin_child(rev):
    assert tier_of(rev, SCOPE, REV) == "twin"
    box, job = placed_box(rev, SCOPE, REV, W.reversed_scope())
    assert_lands_on(box, (-0.03, 0.10, 0.0), (0.03, 0.18, 0.20))  # the child: the mirrored optic moved by (0, 0.10, 0.10)
    assert job["hide"] == [f"{W.REV}_Scope"]


# --- case 3: a near-round drum measured along the wrong axis ------------------------------------------------------------


def test_a_part_measured_along_another_axis_is_corrected_and_its_footprint_is_swapped(rev):
    # measured: forward +x (the longer horizontal axis, 0.14 against 0.11), so length 0.14 / width 0.11; the host points along z
    assert anchor_of(rev, DRUM) == {
        "point": [0.0, 0.0, 0.0], "forward": [0.0, 0.0, 1.0], "up": [0.0, -1.0, 0.0],
        "foot_source": "authored_up", "forward_source": "twin", "symmetric": False}
    assert foot_of(rev, DRUM) == {"length_m": 0.11, "width_m": 0.14, "height_m": 0.09, "foot_length_m": 0.11,
                                  "foot_width_m": 0.14, "mate_d_m": None}


def test_the_corrected_drum_lands_on_its_twin_child(rev):
    assert tier_of(rev, DRUM, REV) == "twin"
    box, _ = placed_box(rev, DRUM, REV, W.drum_mag())
    assert_lands_on(box, (-0.07, -0.09, -0.175), (0.07, 0.0, -0.065))


def test_the_uncorrected_measurement_would_not_land_which_gives_the_placement_tests_teeth():
    # the drum measured alone: forward +x. Placed on the host's z seat it turns 90 degrees about the foot point and misses
    from synty_inventory.weapons.attach import place
    verts = W.drum_mag()[0]
    measured = measure_anchor(verts, "magazine")["anchor"]
    assert measured["forward"] == [1.0, 0.0, 0.0]
    mount = {"point": [0.0, 0.0, -0.12], "forward": [0.0, 0.0, 1.0], "up": [0.0, -1.0, 0.0]}
    box = W.aabb((np.c_[verts, np.ones(len(verts))] @ place(measured, mount).T)[:, :3])
    assert W.iou(box, (np.array([-0.07, -0.09, -0.175]), np.array([0.07, 0.0, -0.065]))) < 0.9


# --- case 4: left alone ---------------------------------------------------------------------------------------------


def measured(mesh, slot, forward=None):
    got = measure_anchor(mesh[0], slot, forward)
    return got["anchor"], got["footprint"]


def test_an_explicit_forward_override_is_kept_byte_for_byte(rev):
    # the human wins: -z by override, though the host's twin child says +z
    assert tier_of(rev, OVR, REV) == "twin"
    assert anchor_of(rev, OVR) == {"point": [0.005, 0.0, -0.05], "forward": [0.0, 0.0, -1.0], "up": [0.0, 1.0, 0.0],
                                   "foot_source": "authored_up", "forward_source": "override", "symmetric": False}
    assert (anchor_of(rev, OVR), foot_of(rev, OVR)) == tuple(measured(W.reversed_scope(), "optic", "-z"))


def test_a_part_whose_twin_hosts_disagree_keeps_its_measurement(dis):
    # DisU points along +z, DisY (yawed body) along +x: the part is a twin of both children and no forward satisfies both
    assert tier_of(dis, SCOPE_DIS, DIS_U) == tier_of(dis, SCOPE_DIS, DIS_Y) == "twin"
    assert dis["by_id"][DIS_U]["geometry"]["mounts"]["optic"]["forward"] == [0.0, 0.0, 1.0]
    assert dis["by_id"][DIS_Y]["geometry"]["mounts"]["optic"]["forward"] == [1.0, 0.0, 0.0]
    assert anchor_of(dis, SCOPE_DIS)["forward"] == [0.0, 0.0, -1.0] and anchor_of(dis, SCOPE_DIS)["forward_source"] == "section"
    assert (anchor_of(dis, SCOPE_DIS), foot_of(dis, SCOPE_DIS)) == tuple(measured(W.reversed_scope(), "optic"))


def test_a_muzzle_device_is_left_as_measured(muz):
    # the host's muzzle mount has forward = the host's up (+z), the device's roll reference is +y: a correction WOULD change it
    assert tier_of(muz, BRAKE, MUZ) == "twin"
    assert muz["by_id"][MUZ]["geometry"]["mounts"]["muzzle"]["forward"] == [0.0, 0.0, 1.0]
    assert anchor_of(muz, BRAKE) == {"point": [0.0, 0.055, 0.65], "forward": [0.0, 1.0, 0.0], "up": [0.0, 0.0, 1.0],
                                     "foot_source": "measured", "forward_source": "authored", "symmetric": True}
    assert (anchor_of(muz, BRAKE), foot_of(muz, BRAKE)) == tuple(measured((W.A.tube(W.A.BARREL_END_Z, W.A.BRAKE_FACE_Z)), "muzzle"))


def test_a_yawed_twin_child_gives_no_evidence_and_the_part_keeps_its_measurement(rev):
    # a sorted-extents twin (tier twin) of a child turned 90 degrees: the per-axis extents differ, so there is no yaw-free match
    assert tier_of(rev, SCOPE_TILT, TILT) == "twin"
    assert anchor_of(rev, SCOPE_TILT)["forward"] == [0.0, 0.0, -1.0] and anchor_of(rev, SCOPE_TILT)["forward_source"] == "section"
    assert (anchor_of(rev, SCOPE_TILT), foot_of(rev, SCOPE_TILT)) == tuple(measured(W.big_reversed_scope(), "optic"))


# --- case 5: confidence and reasons --------------------------------------------------------------------------------


def test_a_correction_never_touches_confidence_or_reasons(rev):
    scope, drum = rev["by_id"][SCOPE]["review"], rev["by_id"][DRUM]["review"]
    assert (scope["confidence"], scope["reasons"]) == (0.9, ["colourway_unknown"])  # decided by the section prior: not unsure
    # the drum was symmetric when measured: it keeps the cap and the reason although `symmetric` is now false
    assert (drum["confidence"], drum["reasons"]) == (0.59, ["anchor_forward_unsure", "colourway_unknown", "low_confidence"])
    assert anchor_of(rev, DRUM)["symmetric"] is False


def test_the_attach_version_is_8_and_nothing_else_about_the_identity_moved(rev):
    assert pkg.WEAPON_ATTACH_VERSION == 10 and rev["directory"]["attach_version"] == 10
    assert pkg.WEAPON_GEOMETRY_VERSION == 5 and rev["directory"]["geometry_version"] == 5
    assert weapon_rules_digest(load_rules()) == "7b9829af37328fe7"
    assert pkg.ANCHOR_FORWARD_SOURCES == ("section", "authored", "twin", "override", "free_end")  # A4 (W8l) appends free_end


# --- case 6: idempotence ---------------------------------------------------------------------------------------------


def child_extents_of(world):
    """``{host id: child_extents}`` from the geometry cache (the evidence the build handed to apply_compat)."""
    out = {}
    for cache_id, entry in world["cache"].items():
        for detail in entry["by_inputs"].values():
            if "child_extents" in detail:
                out[f"{W.PACK}/{Path(cache_id).stem}"] = detail["child_extents"]
    return out


def test_apply_compat_twice_gives_identical_records(rev):
    records = copy.deepcopy(rev["directory"]["weapons"])
    evidence = child_extents_of(rev)
    assert sorted(evidence) == [REV, TILT]
    rules = load_rules()
    first = copy.deepcopy(records)
    compat.apply_compat(first, rules, OVERRIDES, child_extents=evidence)
    assert first == records  # the build already ran it once: a second run changes nothing
    compat.apply_compat(first, rules, OVERRIDES, child_extents=evidence)
    assert first == records
    # a partial build hands the pass no evidence for a carried host: the stored twin relation and the corrected anchor survive
    carried = copy.deepcopy(records)
    compat.apply_compat(carried, rules, OVERRIDES, child_extents={})
    assert carried == records
