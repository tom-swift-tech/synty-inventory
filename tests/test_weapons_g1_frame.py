"""G1 S1: the body-axis frame vote and the record frame, geometry version 6 (docs/weapon_attach_geometry.md 3.3, 3.11, 4.5, 4.6; AC147 record side).

The synthetic hosts are in ``fixtures/weapons/g1_frame_world.py``: the Uzi (a magazine longer than the barrel, a 15 mm ring at the muzzle end
only), the both-rings host, a plain rifle, the Uzi mesh as a part and with a guessed kind, and a host whose bounding box says z while its body
says y. Every expected number is a literal worked out by hand from those dimensions, never read from the code under test: the 25 mm and 10 mm
bounds below are written out here, not taken from ``geometry._FRAME_BORE_MAX_M`` / ``_FRAME_END_SLAB_M``.

Deliberate breaks (AC147), and the tests that fail on each:

* the bounding-box frame used for the record and the detectors: ``test_the_uzi_record_frame_is_the_barrel_axis_toward_the_ring``,
  ``test_the_uzi_muzzle_seat_is_at_the_ring_not_at_the_magazine_bottom``;
* the vote applied to the mounts only: ``test_the_uzi_muzzle_mount_equals_geometry_muzzle`` (AC67 parity) and the record-frame test above;
* a ``forward`` override applied before the axis is chosen: ``test_frame_axis_sets_the_axis_and_forward_then_the_sign``,
  ``test_a_forward_override_on_another_axis_is_ignored_with_the_warning``;
* pass 2 reading the voted frame: ``test_pass2_inputs_are_the_pre_vote_values``, ``test_a_guessed_kind_record_converges_on_the_pre_vote_long_axis``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

_FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("g1_frame_world", _FIX / "g1_frame_world.py")
F = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(F)

from synty_inventory import weapons as pkg  # noqa: E402
from synty_inventory.weapons import digest, geometry, mount_probe  # noqa: E402
from synty_inventory.weapons.directory import build_directory_report  # noqa: E402
from synty_inventory.weapons.overrides import effective_override, empty_overrides, load_overrides, validate_overrides  # noqa: E402
from synty_inventory.weapons.rules import load_rules, weapon_rules_digest  # noqa: E402

W = F.W
SLAB = 0.010  # the end slab of the frame vote, written out (geometry._FRAME_END_SLAB_M is 0.010)

# worked out by hand from the fixture dimensions
IDENTITY = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
BUILD_BASIS = [[1, 0, 0], [0, 0, 1], [0, -1, 0]]  # forward -y, up +z: cross(up, forward) = +x


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    directory, _excluded, cat, root = W.build(tmp_path_factory.mktemp("g1_frame"), F.frame_world(), overrides=F.overrides())
    return {"directory": directory, "by_id": {w["id"]: w for w in directory["weapons"]}, "cat": cat, "root": root}


@pytest.fixture(scope="module")
def rules():
    return load_rules()


def glb(world, host):
    return world["root"] / "glb" / F.PACK / f"{host}.glb"


def detail(world, rules, host, *, archetype="smg", kind="ranged", role="whole", hold="long_gun", with_mounts=True, **kw):
    return geometry.measure_weapon_detail(
        glb(world, host), None, 1.0, archetype, kind, role, rules, hold_class=hold, genre="modern", with_mounts=with_mounts,
        host_id=host, host_pack=F.PACK, **kw)


def v5_geometry(world, rules, host, **kw):
    """The same GLB measured as a record that is not an eligible host (hold class none): exactly the version 5 path, no vote."""
    return detail(world, rules, host, hold="none", with_mounts=False, **kw)["geometry"]


def is_signed_permutation(m) -> bool:
    a = np.abs(np.array(m))
    return a.shape == (3, 3) and set(a.ravel().tolist()) <= {0, 1} and (a.sum(axis=0) == 1).all() and (a.sum(axis=1) == 1).all()


def ring(axis, pos, radius, n=8, centre=(0.0, 0.04)):
    """``n`` vertices on a circle of ``radius`` at ``pos`` along ``axis``."""
    lat = [i for i in range(3) if i != axis]
    pts = []
    for k in range(n):
        a = 2 * np.pi * k / n
        p = [0.0, 0.0, 0.0]
        p[axis], p[lat[0]], p[lat[1]] = pos, centre[0] + radius * np.cos(a), centre[1] + radius * np.sin(a)
        pts.append(p)
    return np.array(pts)


# --- end_ring_d (mount_probe, section 3.6 (ii)) ------------------------------------------------------------------------------


def test_end_ring_d_reads_the_bore_ring_of_the_end_face():
    v = ring(2, 0.20, 0.012)
    v = np.vstack([v, ring(2, 0.20, 0.0075)])  # the annulus: an outer ring and a 15 mm ring on one face
    assert mount_probe.end_ring_d(v, 2, 1, SLAB) == pytest.approx(0.015, abs=1e-4)


def test_end_ring_d_picks_the_end_by_axis_and_sign():
    body = F.uzi_body()[0]
    assert mount_probe.end_ring_d(body, 2, 1, SLAB) == pytest.approx(0.015, abs=1e-4)  # the muzzle face at z 0.20
    assert mount_probe.end_ring_d(body, 2, -1, SLAB) is None  # the stock face is a 4-vertex box face
    along_x = F.tube(0, 0.0, 0.1, (0.0, 0.04))[0]
    assert mount_probe.end_ring_d(along_x, 0, 1, SLAB) == pytest.approx(0.015, abs=1e-4)
    assert mount_probe.end_ring_d(along_x, 0, -1, SLAB) == pytest.approx(0.015, abs=1e-4)  # a closed tube: an annulus at both ends


def test_end_ring_d_needs_six_vertices_in_the_ring_bin():
    outer = ring(2, 0.20, 0.012)
    assert mount_probe.end_ring_d(np.vstack([outer, ring(2, 0.20, 0.0075, n=5)]), 2, 1, SLAB) is None
    assert mount_probe.end_ring_d(np.vstack([outer, ring(2, 0.20, 0.0075, n=6)]), 2, 1, SLAB) == pytest.approx(0.015, abs=1e-4)


def test_end_ring_d_is_not_fooled_by_the_outer_edge_of_a_solid_end():
    assert mount_probe.end_ring_d(ring(2, 0.20, 0.012), 2, 1, SLAB) is None  # only the outer circle: nothing inside 0.75 of it
    inner_too_big = np.vstack([ring(2, 0.20, 0.012), ring(2, 0.20, 0.0095)])  # 0.0095 / 0.012 = 0.79 > 0.75
    assert mount_probe.end_ring_d(inner_too_big, 2, 1, SLAB) is None
    inner_ok = np.vstack([ring(2, 0.20, 0.012), ring(2, 0.20, 0.0085)])  # 0.708
    assert mount_probe.end_ring_d(inner_ok, 2, 1, SLAB) == pytest.approx(0.017, abs=1e-4)


def test_end_ring_d_honours_the_slab_width():
    stepped = np.vstack([ring(2, 0.20, 0.012), ring(2, 0.185, 0.0075)])  # the 15 mm ring sits 15 mm behind the face
    assert mount_probe.end_ring_d(stepped, 2, 1, 0.010) is None
    assert mount_probe.end_ring_d(stepped, 2, 1, 0.020) == pytest.approx(0.015, abs=1e-4)


def test_end_ring_d_returns_the_diameter_whatever_its_size_and_none_for_nothing():
    big = np.vstack([ring(2, 0.20, 0.025), ring(2, 0.20, 0.015)])
    assert mount_probe.end_ring_d(big, 2, 1, SLAB) == pytest.approx(0.030, abs=1e-4)  # the 25 mm limit is the vote's, not the estimator's
    assert mount_probe.end_ring_d(np.zeros((0, 3)), 2, 1, SLAB) is None


# --- frame_vote (geometry, section 3.3 and 3.11) ----------------------------------------------------------------------------


def uzi_verts():
    body = F.uzi_body()[0]
    return np.vstack([body, F.mag(-0.30)[0]]), body


def both_verts():
    body = F.both_body()[0]
    return np.vstack([body, F.mag(-0.45)[0]]), body


def test_the_vote_agrees_when_the_body_axis_is_the_build_axis():
    body = F.rifle_body()[0]
    vote = geometry.frame_vote(body, body, (2, 1))
    assert (vote.forward, vote.up, vote.changed, vote.conflict) == (("z", 1), ("y", 1), False, False)


def test_the_vote_follows_a_single_ring_to_its_end_in_both_signs():
    whole, body = uzi_verts()
    plus = geometry.frame_vote(whole, body, (1, -1))
    assert (plus.forward, plus.up, plus.changed, plus.conflict) == (("z", 1), ("y", 1), True, False)
    flip = np.array([1.0, 1.0, -1.0])  # the same gun facing -z: the ring end is now at the minus end
    minus = geometry.frame_vote(whole * flip, body * flip, (1, -1))
    assert (minus.forward, minus.up, minus.changed, minus.conflict) == (("z", -1), ("y", 1), True, False)


def test_the_vote_up_is_the_ranged_up_rule_on_the_new_forward():
    whole, body = uzi_verts()
    onto_x = body[:, [2, 1, 0]]  # the barrel axis swapped onto x: forward x, so up y
    assert geometry.frame_vote(onto_x, onto_x, (1, -1)).up == ("y", 1)
    onto_y = body[:, [1, 2, 0]]  # barrel along y: up is z (the ranged rule: 2 if forward is y else 1)
    assert geometry.frame_vote(onto_y, onto_y, (2, 1)).up == ("z", 1)


def test_no_ring_at_either_end_is_a_conflict_that_keeps_the_build_frame():
    body = F.box((-0.02, 0.0, -0.10), (0.02, 0.08, 0.20))
    vote = geometry.frame_vote(body[0], body[0], (1, -1))
    assert (vote.forward, vote.up, vote.changed, vote.conflict) == (("y", -1), ("z", 1), False, True)


def test_rings_at_both_ends_are_a_conflict_that_keeps_the_build_frame():
    whole, body = both_verts()
    vote = geometry.frame_vote(whole, body, (1, -1))
    assert (vote.forward, vote.up, vote.changed, vote.conflict) == (("y", -1), ("z", 1), False, True)


def test_a_ring_over_25_mm_does_not_confirm_and_one_at_25_mm_does():
    body = F.box((-0.02, 0.0, -0.10), (0.02, 0.08, 0.05))[0]
    big = F.tube(2, 0.05, 0.20, (0.0, 0.04), r_out=0.02, r_in=0.0130)[0]  # 26 mm
    edge = F.tube(2, 0.05, 0.20, (0.0, 0.04), r_out=0.02, r_in=0.0125)[0]  # 25 mm
    assert geometry.frame_vote(np.vstack([body, big]), np.vstack([body, big]), (1, -1)).conflict
    vote = geometry.frame_vote(np.vstack([body, edge]), np.vstack([body, edge]), (1, -1))
    assert (vote.forward, vote.changed, vote.conflict) == (("z", 1), True, False)


def test_frame_axis_decides_the_axis_and_the_ring_still_gives_the_sign():
    whole, body = both_verts()
    named = geometry.frame_vote(whole, body, (1, -1), frame_axis="z")  # both ends ring: no sign from the body
    assert (named.forward[0], named.changed, named.conflict, named.sign_by_fallback) == ("z", True, False, True)
    assert named.forward[1] == 1 and named.up == ("y", 1)
    uzi_whole, uzi_body = uzi_verts()
    one_ring = geometry.frame_vote(uzi_whole, uzi_body, (1, -1), frame_axis="z")
    assert (one_ring.forward, one_ring.sign_by_fallback) == (("z", 1), False)


def test_frame_axis_outranks_the_body_axis_and_resolves_a_conflict_on_the_build_axis():
    whole, body = uzi_verts()
    same = geometry.frame_vote(whole, body, (1, -1), frame_axis="y")  # the body says z, the override says the build axis y
    assert (same.forward, same.changed, same.conflict) == (("y", -1), False, False)
    both_whole, both_body = both_verts()
    resolved = geometry.frame_vote(both_whole, both_body, (1, -1), frame_axis="y")
    assert (resolved.changed, resolved.conflict) == (False, False)


# --- the record: the Uzi -------------------------------------------------------------------------------------------------------


def test_the_uzi_record_frame_is_the_barrel_axis_toward_the_ring(world, rules):
    d = detail(world, rules, F.UZI)
    g = d["geometry"]
    assert g["axes"] == {"forward": "+z", "up": "+y", "forward_source": "body", "up_source": "fixed"}
    assert g["item_basis"] == IDENTITY and is_signed_permutation(g["item_basis"])
    assert g["long_axis"] == "y"  # the bounding-box axis: a measurement of the mesh, not of the frame
    assert g["bounds"]["size"] == [0.04, 0.38, 0.3]
    assert (g["length_m"], g["pivot_frac"]) == (0.3, 0.3333)  # along the barrel axis z: -0.10..0.20, the origin a third in
    assert g["tip"] is None and g["butt"] == [0.0, 0.04, -0.1]
    assert g["muzzle"] == [0.0, 0.04, 0.2] and g["muzzle_source"] == "face"
    assert d["flags"] == [] and "axes_unexpected" not in d["reasons"]  # the voted forward is the pack convention +z
    assert d["frame_vote"]["changed"] is True and d["frame_vote"]["conflict"] is False


def test_the_uzi_muzzle_seat_is_at_the_ring_not_at_the_magazine_bottom(world, rules):
    mount = detail(world, rules, F.UZI)["mounts"]["muzzle"]
    assert mount["point"] == [0.0, 0.04, 0.2] and mount["up"] == [0.0, 0.0, 1.0]
    assert mount["bore_d_m"] == 0.015 and mount["bore_source"] == "ring"
    assert v5_geometry(world, rules, F.UZI)["muzzle"] == [0.0, -0.3, -0.03]  # version 5: the magazine bottom, the fault this fixes


def test_the_uzi_muzzle_mount_equals_geometry_muzzle(world, rules):
    """AC67 parity on a feature-frame host (INV-28): occupied_by is empty, so the A0 probe runs on the same mesh in the same frame."""
    d = detail(world, rules, F.UZI)
    assert d["mounts"]["muzzle"]["occupied_by"] == []
    assert d["mounts"]["muzzle"]["point"] == d["geometry"]["muzzle"] == [0.0, 0.04, 0.2]


def test_the_build_measures_the_uzi_record_in_the_voted_frame(world):
    rec = world["by_id"][F.pid(F.UZI)]
    g = rec["geometry"]
    assert g["axes"]["forward"] == "+z" and g["axes"]["forward_source"] == "body" and g["item_basis"] == IDENTITY
    assert g["mounts"]["muzzle"]["point"] == g["muzzle"] == [0.0, 0.04, 0.2]
    assert g["frame"] == "asset" and "frame" not in rec and "conflict" not in g  # the frame state is beside the geometry in the detail, not a record key
    assert "axes_unexpected" not in rec["review"]["reasons"]
    assert (rec["archetype"], rec["kind"], rec["hold_class"]) == ("smg", "ranged", "long_gun")


def test_classification_reads_the_pre_vote_values_so_the_confidence_keeps_the_bounding_box_penalty(world):
    # the review reason is judged from the voted forward and drops; the classifier's confidence was computed from the pre-vote
    # axes_unexpected and does not move (section 3.3: the vote never feeds kind, archetype, hold class or the loop's convergence)
    assert world["by_id"][F.pid(F.UZI)]["review"]["confidence"] == 0.77


def test_pass2_inputs_are_the_pre_vote_values(world, rules):
    # S7 fold-in 1: rename detail key frame to frame_vote (the mounts block reads the vote through it)
    d = detail(world, rules, F.UZI)
    assert geometry.pass2_inputs(d) == {"length_m": 0.38, "long_axis": "y", "forward_by_fallback": False, "axes_unexpected": True}
    assert d["geometry"]["length_m"] == 0.3  # the record's own length follows the voted frame
    assert d["frame_vote"] == {"changed": True, "conflict": False, "length_m": 0.38, "axes_unexpected": True, "forward_by_fallback": False}


def test_the_vote_runs_whatever_with_mounts_says(world, rules):
    bare = detail(world, rules, F.UZI, with_mounts=False)
    assert bare["geometry"]["axes"]["forward_source"] == "body" and "mounts" not in bare and "frame_vote" not in bare


# --- the record: no change ------------------------------------------------------------------------------------------------------


def test_the_plain_rifle_is_unchanged(world, rules):
    d = detail(world, rules, F.RIFLE, archetype="rifle", hold="one_hand")  # one_hand: eligible, and no support point to differ by
    assert d["geometry"]["axes"] == {"forward": "+z", "up": "+y", "forward_source": "pivot", "up_source": "fixed"}
    assert d["frame_vote"] == {"changed": False, "conflict": False, "length_m": 0.85, "axes_unexpected": False, "forward_by_fallback": False}
    assert d["geometry"] == v5_geometry(world, rules, F.RIFLE, archetype="rifle")  # every key is the version 5 value


def test_a_record_that_is_not_an_eligible_host_is_measured_exactly_as_in_version_5(world, rules):
    part = detail(world, rules, F.UZI_PART, archetype="unknown", kind=None, role="part", hold="none")
    assert "frame" not in part and "mounts" not in part
    assert part["geometry"]["axes"] == {"forward": "-y", "up": "+z", "forward_source": "pivot", "up_source": "width_axis"}
    assert part["geometry"]["item_basis"] == BUILD_BASIS and part["geometry"]["length_m"] == 0.38
    same_mesh_as_host = v5_geometry(world, rules, F.UZI)
    assert same_mesh_as_host["axes"]["forward"] == "-y" and same_mesh_as_host["length_m"] == 0.38  # the vote is the only difference
    rec = world["by_id"][F.pid(F.UZI_PART)]
    assert rec["role"] == "part" and rec["geometry"]["axes"]["forward"] == "-y" and rec["geometry"]["axes"]["forward_source"] == "pivot"


def test_no_other_record_of_the_world_has_a_body_frame(world):
    sources = {r["id"]: r["geometry"]["axes"]["forward_source"] for r in world["directory"]["weapons"]}
    assert {i for i, s in sources.items() if s == "body"} == {F.pid(F.UZI), F.pid(F.REVERSE)}


# --- the record: a frame conflict and frame_axis -----------------------------------------------------------------------------


def test_the_both_rings_host_keeps_its_build_frame_and_reports_the_conflict(world, rules):
    d = detail(world, rules, F.BOTH, hold="one_hand")
    assert d["frame_vote"]["conflict"] is True and d["frame_vote"]["changed"] is False
    assert d["geometry"] == v5_geometry(world, rules, F.BOTH)  # the build frame, every key
    g = d["geometry"]
    assert g["axes"] == {"forward": "-y", "up": "+z", "forward_source": "pivot", "up_source": "fixed"}
    assert g["item_basis"] == BUILD_BASIS and g["length_m"] == 0.53


def test_frame_axis_sets_the_axis_and_forward_then_the_sign(world, rules):
    named = detail(world, rules, F.BOTH, frame_axis="z")
    assert named["frame_vote"]["conflict"] is False and named["frame_vote"]["changed"] is True
    g = named["geometry"]
    assert g["axes"]["forward"] == "+z" and g["axes"]["forward_source"] == "body" and g["axes"]["up"] == "+y"
    assert g["item_basis"] == IDENTITY and g["length_m"] == 0.4
    assert "forward_by_fallback" in named["flags"]  # no ring separates the ends: the sign is the default +, flagged for review
    signed = detail(world, rules, F.BOTH, frame_axis="z", forward_override="-z")
    gs = signed["geometry"]
    assert gs["axes"]["forward"] == "-z" and gs["axes"]["forward_source"] == "override" and gs["axes"]["up"] == "+y"
    assert gs["item_basis"] == [[-1, 0, 0], [0, 1, 0], [0, 0, -1]] and is_signed_permutation(gs["item_basis"])
    assert "forward_by_fallback" not in signed["flags"] and signed["warning"] is None
    assert gs["muzzle"] == signed["mounts"]["muzzle"]["point"]  # the mounts follow the record's frame (AC67)
    assert gs["length_m"] == 0.4 and gs["butt"] == [0.0, 0.04, 0.2]


def test_a_forward_override_on_another_axis_is_ignored_with_the_warning(world, rules):
    d = detail(world, rules, F.BOTH, frame_axis="z", forward_override="-y")  # -y is the build axis; frame_axis moved the axis to z
    assert d["geometry"]["axes"]["forward"] == "+z" and d["geometry"]["axes"]["forward_source"] == "body"
    assert d["warning"] is not None and "'-y' ignored" in d["warning"] and "+z" in d["warning"]


def test_a_forward_override_on_the_build_axis_does_not_pick_the_axis_the_vote_does(world, rules):
    d = detail(world, rules, F.UZI, forward_override="-y")  # -y is the bounding-box axis; the body says z, and the override only signs an axis
    assert d["geometry"]["axes"]["forward"] == "+z" and d["geometry"]["axes"]["forward_source"] == "body"
    assert d["warning"] is not None and "'-y' ignored" in d["warning"]
    assert d["geometry"]["length_m"] == 0.3 and d["frame_vote"]["changed"] is True


def test_frame_axis_on_the_build_axis_keeps_the_build_frame(world, rules):
    d = detail(world, rules, F.UZI, frame_axis="y")
    assert d["geometry"]["axes"]["forward"] == "-y" and d["geometry"]["axes"]["forward_source"] == "pivot"
    assert d["frame_vote"]["changed"] is False and d["frame_vote"]["conflict"] is False


def test_a_forward_override_on_the_voted_axis_sets_the_sign_as_today(world, rules):
    d = detail(world, rules, F.UZI, forward_override="-z")
    assert d["geometry"]["axes"]["forward"] == "-z" and d["geometry"]["axes"]["forward_source"] == "override"
    assert d["warning"] is None and d["geometry"]["muzzle"] == d["mounts"]["muzzle"]["point"]


# --- convergence ----------------------------------------------------------------------------------------------------------------


def test_a_guessed_kind_record_converges_on_the_pre_vote_long_axis(tmp_path):
    world = {F.PACK: {"hosts": {F.REVERSE: F.frame_world()[F.PACK]["hosts"][F.REVERSE]}}}
    directory, _excl, report = _build_report(tmp_path, world)
    rec = {w["id"]: w for w in directory["weapons"]}[F.pid(F.REVERSE)]
    # the kind is taken from the bounding-box long axis z (ranged), measured as melee first and as ranged second, then stable
    assert (rec["kind"], rec["hold_class"]) == ("ranged", "long_gun") and "kind_guessed" in rec["review"]["reasons"]
    assert report["geometry_stats"] == {"decoded": 2, "cached": 0}
    g = rec["geometry"]
    assert g["long_axis"] == "z"
    assert g["axes"] == {"forward": "+y", "up": "+z", "forward_source": "body", "up_source": "fixed"}
    assert g["length_m"] == 0.45 and g["item_basis"] == [[-1, 0, 0], [0, 0, 1], [0, 1, 0]]  # cross(up +z, forward +y) = -x
    assert is_signed_permutation(g["item_basis"])
    again, _e, rep2 = _build_report(tmp_path / "again", world)
    assert json.dumps(again, sort_keys=True) == json.dumps(directory, sort_keys=True) and rep2["geometry_stats"] == {"decoded": 2, "cached": 0}


def _build_report(tmp_path, world):
    cat, root = W.write_world(tmp_path, world)
    return build_directory_report(cat, overrides=F.overrides(), pack_settings=W.pack_settings(world), rules=W.sight_rules(),
                                  threejs_v2_dir=root, geometry_cache={})


def test_a_guessed_kind_uzi_stays_melee_and_never_votes(world):
    rec = world["by_id"][F.pid(F.UZI_GUESSED)]
    assert (rec["kind"], rec["hold_class"]) == ("melee", "none") and "kind_guessed" in rec["review"]["reasons"]
    assert rec["geometry"]["axes"]["forward"] == "-y" and rec["geometry"]["axes"]["forward_source"] == "pivot"
    assert rec["geometry"]["mounts"] is None


# --- cache, digests, fingerprint, overrides -----------------------------------------------------------------------------------


def test_the_geometry_version_is_6():
    assert pkg.WEAPON_GEOMETRY_VERSION == 6 and isinstance(pkg.WEAPON_GEOMETRY_VERSION, int)


def test_ac78_a_bump_to_7_misses_the_cache_and_a_hit_equals_a_recompute(world, rules, monkeypatch):
    cache: dict = {}
    args = (world["root"], f"glb/{F.PACK}/{F.UZI}.glb", None, 1.0, "smg", "ranged", "whole", rules, cache)
    kw = {"hold_class": "long_gun", "genre": "modern", "host_id": F.UZI, "host_pack": F.PACK}
    first, was_cached = geometry.measure_cached(*args, **kw)
    assert was_cached is False and first["geometry"]["axes"]["forward_source"] == "body"
    hit, was_cached = geometry.measure_cached(*args, **kw)
    assert was_cached is True and hit == first
    revived, was_cached = geometry.measure_cached(*args[:-1], json.loads(json.dumps(cache)), **kw)
    assert was_cached is True and revived == first  # through a JSON round trip too
    fresh, _ = geometry.measure_cached(*args[:-1], {}, **kw)
    assert fresh == first  # a hit equals a recompute
    monkeypatch.setattr(pkg, "WEAPON_GEOMETRY_VERSION", 7)
    again, was_cached = geometry.measure_cached(*args, **kw)
    assert was_cached is False and again == first


def test_frame_axis_joins_the_fingerprint_only_when_it_is_set(rules):
    base = geometry._inputs_fingerprint("smg", "ranged", "whole", "long_gun", "modern", rules)
    assert geometry._inputs_fingerprint("smg", "ranged", "whole", "long_gun", "modern", rules, frame_axis=None) == base
    z = geometry._inputs_fingerprint("smg", "ranged", "whole", "long_gun", "modern", rules, frame_axis="z")
    x = geometry._inputs_fingerprint("smg", "ranged", "whole", "long_gun", "modern", rules, frame_axis="x")
    assert len({base, z, x}) == 3


def test_a_cached_result_is_not_served_across_frame_axis_values(world, rules):
    cache: dict = {}
    args = (world["root"], f"glb/{F.PACK}/{F.BOTH}.glb", None, 1.0, "smg", "ranged", "whole", rules, cache)
    kw = {"hold_class": "long_gun", "genre": "modern", "host_id": F.BOTH, "host_pack": F.PACK}
    plain, _ = geometry.measure_cached(*args, **kw)
    named, was_cached = geometry.measure_cached(*args, frame_axis="z", **kw)
    assert was_cached is False and plain["geometry"]["axes"]["forward"] == "-y" and named["geometry"]["axes"]["forward"] == "+z"
    assert geometry.measure_cached(*args, frame_axis="z", **kw)[1] is True


def test_ac146_the_rules_and_overrides_digests_are_unchanged(rules):
    assert weapon_rules_digest(rules) == "7b9829af37328fe7"
    assert digest(empty_overrides()) == "7d8dd8ce21b0f42b"
    # the committed file, by path (conftest points the default at an empty one): no frame_axis entry is written to it
    shipped = Path(pkg.__file__).resolve().parent.parent / "data" / "weapon_overrides.json"
    # Tom's decision 2(i) (2026-10-28) disables the S optic and the T underbarrel by id; E3.18 amends AC146's "unchanged"
    assert digest(load_overrides(shipped)) == "17d4e771a785a4b2"


def test_the_build_digests_are_the_w7_literals_and_the_geometry_version_is_6(world):
    d = world["directory"]
    assert d["rules_digest"] == "7b9829af37328fe7" and d["geometry_version"] == 6


def _doc(entry):
    return {"schema": "weapon-overrides/1", "ids": {"FAKE_G1/SM_Wep_SMG_Both_01": entry}, "globs": {}}


@pytest.mark.parametrize("axis", ["x", "y", "z"])
def test_frame_axis_is_a_valid_id_override_and_effective_override_returns_it(axis):
    doc = _doc({"frame_axis": axis})
    assert validate_overrides(doc) == []
    assert effective_override("FAKE_G1/SM_Wep_SMG_Both_01", doc)["frame_axis"] == axis
    assert effective_override("FAKE_G1/SM_Wep_SMG_Uzi_01", doc) is None


@pytest.mark.parametrize("bad", ["w", "+z", "Z", "zz", "", None, 2, True])
def test_frame_axis_rejects_anything_but_x_y_z(bad):
    errors = validate_overrides(_doc({"frame_axis": bad}))
    assert len(errors) == 1 and "frame_axis" in errors[0] and "not in ['x', 'y', 'z']" in errors[0]


def test_frame_axis_is_id_only_and_absent_when_not_written():
    glob = {"schema": "weapon-overrides/1", "ids": {}, "globs": {"FAKE_G1/*": {"frame_axis": "z"}}}
    errors = validate_overrides(glob)
    assert len(errors) == 1 and "frame_axis" in errors[0]
    assert effective_override("FAKE_G1/SM_Wep_SMG_Both_01", _doc({"note": "n"}))["frame_axis"] is None


def test_a_frame_axis_entry_moves_the_overrides_digest_and_the_build_picks_it_up(tmp_path):
    world = {F.PACK: {"hosts": {F.BOTH: F.frame_world()[F.PACK]["hosts"][F.BOTH]}}}
    plain, _, _ = _build_report(tmp_path / "a", world)
    named_doc = F.overrides({F.pid(F.BOTH): {"frame_axis": "z"}})
    cat, root = W.write_world(tmp_path / "b", world)
    named, _, _ = build_directory_report(cat, overrides=named_doc, pack_settings=W.pack_settings(world), rules=W.sight_rules(),
                                         threejs_v2_dir=root, geometry_cache={})
    assert plain["overrides_digest"] != named["overrides_digest"]
    assert plain["weapons"][0]["geometry"]["axes"]["forward"] == "-y"
    assert named["weapons"][0]["geometry"]["axes"]["forward"] == "+z" and named["weapons"][0]["geometry"]["axes"]["forward_source"] == "body"
