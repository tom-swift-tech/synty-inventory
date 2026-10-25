"""W8o: the muzzle face peel (docs/weapon_attachments.md 13.8 A7-3; AC120, AC123).

Synthetic muzzle faces handed to ``mounts._muzzle_mount`` through a fake probe. Every size, count and bound below is a LITERAL
(millimetres worked out from the construction of each face), never read from ``mounts`` or the shipped rules, so a loosened constant
cannot loosen a case.
"""

from __future__ import annotations

import importlib.util
import math
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from synty_inventory.weapons import mounts
from synty_inventory.weapons.geometry import _inputs_fingerprint
from synty_inventory.weapons.rules import attach_rules_digest, load_rules, validate_rules, weapon_rules_digest

_spec = importlib.util.spec_from_file_location("w8a_attach", Path(__file__).parent / "fixtures" / "weapons" / "w8a_attach.py")
A = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A)

MM = 0.001
RANGE = [0.006, 0.035]  # a literal copy of the shipped range
# forward axis index -> the host axes; the face is built in (lat0, lat1) columns plus a forward column and mapped onto the axes
AXES = {2: {"forward": "+z", "up": "+y"}, 0: {"forward": "+x", "up": "+z"}, 1: {"forward": "+y", "up": "+x"}}
SLIDE_X = (-9, -6, -3, 0, 3, 6, 9)


def ring(n, r_mm, cx=0.0, cy=0.0):
    return [(cx + r_mm * MM * math.cos(2 * math.pi * k / n), cy + r_mm * MM * math.sin(2 * math.pi * k / n)) for k in range(n)]


def face_of(points2d, f_i, z=0.6499):
    """[N,3] face: ``points2d`` are the two lateral coordinates in axis order, ``z`` the forward coordinate."""
    lat = [i for i in range(3) if i != f_i]
    out = np.zeros((len(points2d), 3))
    for row, (a, b) in zip(out, points2d):
        row[lat[0]], row[lat[1]], row[f_i] = a, b, z
    return out


def probe_of(face, f_i, forward_point=0.6512):
    """A fake A0 probe: the mean of the face laterally, ``forward_point`` forward (NOT the face's own forward coordinate, 0.6499)."""
    def probe(_verts, _forward, _up):
        p = face.mean(axis=0)
        p[f_i] = forward_point
        return [float(c) for c in p], "face", face
    return probe


def seat(face, f_i, peel, *, source="face"):
    probe = probe_of(face, f_i)
    if source != "face":
        def probe(_v, _f, _u):
            return [0.0, 0.055, 0.65], source, np.zeros((0, 3))
    return mounts._muzzle_mount(None, None, 1.0, np.zeros((1, 3)), AXES[f_i], [], None, probe, peel)


def d21_face(f_i):
    """AC120: a 13-point ring of 9 mm diameter around the origin and 7 points of a slide front 14 mm below the ring (y = -18.5 mm)."""
    return face_of(ring(13, 4.5) + [(x * MM, -18.5 * MM) for x in SLIDE_X], f_i)


def lateral(point, f_i):
    return [point[i] for i in range(3) if i != f_i]


@pytest.mark.parametrize("f_i", [2, 0, 1])
def test_ac120_the_peel_moves_the_point_to_the_ring_centroid_and_changes_nothing_else(f_i):
    face = d21_face(f_i)
    before = seat(face, f_i, None)
    after = seat(face, f_i, RANGE)
    # the fixture is what the spec says: no ring on the full face (extent 2 * sqrt(9^2 + 12.025^2) = 30.0 mm), the face mean 6.475 mm from the ring centre
    assert before["bore_source"] == "face_extent" and before["bore_d_m"] == 0.03
    assert abs(math.hypot(*lateral(before["point"], f_i)) - 0.006475) <= 0.0001
    lat = [i for i in range(3) if i != f_i]
    want = face[:13][:, lat].mean(axis=0)  # the 13 ring points come first in face_of
    got = lateral(after["point"], f_i)
    assert max(abs(g - w) for g, w in zip(got, want)) <= 0.0005
    assert after["point"][f_i] == before["point"][f_i] == 0.6512  # bit-identical, the probe point's own value (the face's forward is 0.6499)
    assert after["bore_source"] == "face_extent" and after["bore_d_m"] == before["bore_d_m"]
    assert {k: v for k, v in after.items() if k != "point"} == {k: v for k, v in before.items() if k != "point"}
    assert after["point"] != before["point"]


def test_ac120_all_13_ring_points_remain_and_the_7_slide_points_are_the_ones_dropped():
    # the ring is centred on the origin: the centroid of exactly the 13 ring points is (0, 0) to 4 decimals; keeping even one slide point
    # would put it at least 0.9 mm (18.5 mm / 14) off
    got = seat(d21_face(2), 2, RANGE)["point"]
    assert got[0] == 0.0 and got[1] == 0.0


def test_the_point_is_rounded_like_every_other_frame_coordinate():
    shifted = face_of(ring(13, 4.5, 0.01234567, -0.00098765) + [(0.0123 + x * MM, -18.5 * MM) for x in SLIDE_X], 2)
    got = seat(shifted, 2, RANGE)["point"]
    assert got[:2] == [0.0123, -0.001] and all(round(c, 4) == c for c in got)


def test_a_four_point_face_is_not_accepted():
    face = face_of([(0.0, 0.0), (0.004, 0.0), (0.0, 0.004), (0.02, 0.02)], 2)
    assert seat(face, 2, RANGE) == seat(face, 2, None)


def test_a_five_point_face_is_not_accepted():
    face = face_of(ring(5, 4.5) + [(0.03, 0.03)], 2)
    assert seat(face, 2, RANGE) == seat(face, 2, None)


def test_a_ring_of_40_millimetres_is_not_accepted_and_the_range_is_the_reason():
    face = face_of(ring(13, 20.0) + [(x * MM, -70 * MM) for x in (-30, -20, -10, 0, 10, 20, 30)], 2)
    unpeeled = seat(face, 2, None)
    assert unpeeled["bore_source"] == "face_extent"
    assert seat(face, 2, RANGE) == unpeeled
    assert seat(face, 2, [0.006, 0.05])["point"] != unpeeled["point"]  # the same face IS peeled when 40 mm is in range


def test_a_ring_of_5_millimetres_is_not_accepted_below_the_range():
    face = face_of(ring(13, 2.5) + [(x * MM, -14 * MM) for x in (-6, -4, -2, 0, 2, 4, 6)], 2)
    unpeeled = seat(face, 2, None)
    assert unpeeled["bore_source"] == "face_extent"
    assert seat(face, 2, RANGE) == unpeeled
    assert seat(face, 2, [0.004, 0.035])["point"] != unpeeled["point"]


def test_the_range_ends_are_inclusive():
    face = d21_face(2)  # the ring is 9 mm
    moved = seat(face, 2, None)["point"]
    assert seat(face, 2, [0.009, 0.02])["point"] != moved
    assert seat(face, 2, [0.003, 0.009])["point"] != moved
    assert seat(face, 2, [0.0091, 0.02])["point"] == moved
    assert seat(face, 2, [0.003, 0.0089])["point"] == moved


def clutter_face(n_outer):
    """A 6-point ring of 9 mm diameter and ``n_outer`` points around it: radius 20 mm + 3 mm per point, at golden-angle steps (no 1 mm bin fills up)."""
    outer = [((20 + 3 * k) * MM * math.cos(2.399963 * k), (20 + 3 * k) * MM * math.sin(2.399963 * k)) for k in range(n_outer)]
    return face_of(ring(6, 4.5) + outer, 2)


def test_a_ring_that_shows_only_after_dropping_more_than_70_percent_is_not_accepted(monkeypatch):
    face = clutter_face(18)  # 24 points, 18 dropped = 75 %
    unpeeled = seat(face, 2, None)
    assert unpeeled["bore_source"] == "face_extent"
    assert seat(face, 2, RANGE) == unpeeled
    # the drop share is the reason: with the cap lifted the same face peels onto the 6 ring points
    monkeypatch.setattr(mounts, "_PEEL_MAX_DROP", 0.80)
    peeled = seat(face, 2, RANGE)["point"]
    assert peeled != unpeeled["point"] and abs(peeled[0]) <= 0.0005 and abs(peeled[1]) <= 0.0005


def test_the_drop_share_is_inclusive_at_70_percent():
    face = clutter_face(14)  # 20 points, 14 dropped = exactly 70 %
    unpeeled = seat(face, 2, None)
    assert unpeeled["bore_source"] == "face_extent"
    assert seat(face, 2, RANGE)["point"] != unpeeled["point"]


def test_a_healthy_ring_host_is_bit_identical_in_every_key():
    face = face_of(ring(13, 4.5) + [(0.5 * MM, 0.0), (-0.5 * MM, 0.0)], 2)
    plain = seat(face, 2, None)
    assert plain["bore_source"] == "ring"  # the first test already sees a ring
    assert seat(face, 2, RANGE) == plain


def test_a_bounds_fallback_muzzle_is_never_peeled():
    assert seat(d21_face(2), 2, RANGE, source="bounds_fallback") == seat(d21_face(2), 2, None, source="bounds_fallback")


def test_with_no_table_nothing_is_peeled():
    assert seat(d21_face(2), 2, None)["point"][:2] != [0.0, 0.0]


# --- build_mounts: the table is read from the rules --------------------------------------------------------------------


def test_build_mounts_reads_the_peel_from_the_rules_table(tmp_path):
    _, root = A.write_mount_world(tmp_path)
    glb = root / "glb" / A.MOUNT_PACK / "SM_Wep_Rifle_Plain_01.glb"
    face = d21_face(2)

    def build(rules):
        return mounts.build_mounts(glb, None, 1.0, rules, verts=np.zeros((1, 3)), axes=AXES[2], probe=probe_of(face, 2),
                                   host_id="SM_Wep_Rifle_Plain_01")["mounts"]["muzzle"]

    rules = load_rules()
    assert rules["attachment_rules"]["attach_mount"] == {"peel_bore_d_m": [0.006, 0.035]}
    bare = deepcopy(rules)
    del bare["attachment_rules"]["attach_mount"]
    peeled, plain = build(rules), build(bare)
    assert peeled["point"][:2] == [0.0, 0.0] and plain["point"][:2] != [0.0, 0.0]
    assert peeled["point"][2] == plain["point"][2] == 0.6512
    assert {k: v for k, v in peeled.items() if k != "point"} == {k: v for k, v in plain.items() if k != "point"}
    narrow = deepcopy(rules)
    narrow["attachment_rules"]["attach_mount"]["peel_bore_d_m"] = [0.01, 0.035]  # the 9 mm ring is out
    assert build(narrow) == plain


# --- the rules table ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("value", [{"peel_bore_d_m": [0.006, 0.035]}, {"peel_bore_d_m": [0.001, 0.2]}, {"peel_bore_d_m": [0.05, 0.1]},
                                   {"peel_bore_d_m": [0.0001, 0.0002]}])
def test_the_table_accepts_good_ranges(value):
    rules = deepcopy(load_rules())
    rules["attachment_rules"]["attach_mount"] = value
    assert validate_rules(rules) == []


@pytest.mark.parametrize("value", [
    [], "x", 5, {}, {"peel_bore_d_m": None}, {"peel_bore_d_m": [0.006]}, {"peel_bore_d_m": [0.006, 0.035, 0.05]},
    {"peel_bore_d_m": [0.035, 0.006]}, {"peel_bore_d_m": [0.02, 0.02]}, {"peel_bore_d_m": [0, 0.035]}, {"peel_bore_d_m": [-0.001, 0.035]},
    {"peel_bore_d_m": [0.006, 0.2001]}, {"peel_bore_d_m": ["a", "b"]}, {"peel_bore_d_m": [True, 0.035]}, {"peel_bore_d_m": 0.02},
    {"peel_bore_d_m": [0.006, 0.035], "surprise": 1}, {"surprise": 1},
])
def test_the_table_rejects_a_bad_shape(value):
    rules = deepcopy(load_rules())
    rules["attachment_rules"]["attach_mount"] = value
    errors = validate_rules(rules)
    assert errors and any("attach_mount" in e for e in errors), errors


def test_the_table_moves_the_attach_digest_and_not_the_rules_digest():
    base = load_rules()
    assert "attach_mount" in base["attachment_rules"]
    for mutate in (lambda t: t["attach_mount"].update(peel_bore_d_m=[0.006, 0.03]), lambda t: t.pop("attach_mount")):
        rules = deepcopy(base)
        mutate(rules["attachment_rules"])
        assert weapon_rules_digest(rules) == weapon_rules_digest(base) and attach_rules_digest(rules) != attach_rules_digest(base)


def test_a_table_without_attach_mount_is_valid():
    rules = deepcopy(load_rules())
    del rules["attachment_rules"]["attach_mount"]
    assert validate_rules(rules) == []


def test_the_mounts_cache_key_follows_the_peel_range_for_eligible_hosts_only():
    rules = load_rules()
    args = ("rifle", "ranged", "whole", "long_gun", "modern")
    other = ("sword", "melee", "whole", "melee_one", "modern")
    base, sword = _inputs_fingerprint(*args, rules), _inputs_fingerprint(*other, rules)
    edited = deepcopy(rules)
    edited["attachment_rules"]["attach_mount"]["peel_bore_d_m"] = [0.006, 0.03]
    assert _inputs_fingerprint(*args, edited) != base
    gone = deepcopy(rules)
    del gone["attachment_rules"]["attach_mount"]
    assert _inputs_fingerprint(*args, gone) != base
    assert _inputs_fingerprint(*other, edited) == sword and _inputs_fingerprint(*other, gone) == sword


# --- the schema: the AC67 parity gives way for a face_extent muzzle, sideways only ---------------------------------------


@pytest.fixture(scope="module")
def mount_world(tmp_path_factory):
    return A.build_mount_world(tmp_path_factory.mktemp("w8o_peel_schema"))[0]


def _muzzle_errors(doc, host_n, edit):
    from synty_inventory.weapons.schema import validate_record
    d = deepcopy(doc)
    rec = next(w for w in d["weapons"] if w["id"] == f"{A.MOUNT_PACK}/SM_Wep_Rifle_{host_n}_01")
    edit(rec["geometry"]["mounts"]["muzzle"])
    return validate_record(rec)


def test_schema_a_face_extent_muzzle_may_sit_sideways_of_geometry_muzzle(mount_world):
    sideways = lambda m: m.update(point=[m["point"][0] + 0.004, m["point"][1] - 0.003, m["point"][2]])  # noqa: E731
    assert _muzzle_errors(mount_world, "Plain", lambda m: None) == []  # the ring-less fixture host: face_extent
    assert _muzzle_errors(mount_world, "Plain", sideways) == []


def test_schema_the_forward_coordinate_of_a_face_extent_muzzle_may_not_move(mount_world):
    ahead = lambda m: m.update(point=[m["point"][0], m["point"][1], m["point"][2] + 0.001])  # noqa: E731
    errors = _muzzle_errors(mount_world, "Plain", ahead)
    assert any("geometry.muzzle exactly" in e for e in errors), errors


def test_schema_a_ring_muzzle_still_has_to_equal_geometry_muzzle(mount_world):
    sideways = lambda m: m.update(point=[m["point"][0] + 0.004, m["point"][1], m["point"][2]])  # noqa: E731
    errors = _muzzle_errors(mount_world, "Mount", sideways)
    assert any("geometry.muzzle exactly" in e for e in errors), errors
