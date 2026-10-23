"""W8m: authored placements never move (docs/weapon_attachments.md 5.4 "Which pairs"; AC113).

World: ``w8m_world.authored_world`` (pack FAKE_W8M). Every host seats its scope child's foot 20 mm over the body top (y 0.12 against 0.10), so a
pair placed there floats 20 mm off the host's mesh. The control (a natural pair) is keyed -0.0200; a twin, an override-tier entry and a pair on an
override-source mount must carry no key and must place byte-identically to ``place(anchor, frame)``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8m_world", FIX / "w8m_world.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)
W = M.W

from synty_inventory.weapons import preview  # noqa: E402
from synty_inventory.weapons.attach import place  # noqa: E402


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    directory, _, _, root = W.build(tmp_path_factory.mktemp("w8m_authored"), M.authored_world(), overrides=M.authored_overrides())
    return SimpleNamespace(directory=directory, by_id=W.by_id(directory), root=root)


def entry(built, part: str, case: str) -> dict:
    return next(e for e in built.by_id[M.pid(part)]["attachment"]["compatible_hosts"] if e["host"] == M.hid(case))


def matrix_of(built, part: str, case: str):
    p, h = built.by_id[M.pid(part)], built.by_id[M.hid(case)]
    e = entry(built, part, case)
    pair = {"part": p["id"], "host": h["id"], "slot": "optic", "tier": e["tier"], "score": e["score"], "twin": e["tier"] == "twin"}
    return pair, p, h, np.asarray(preview.build_job(pair, p, h, built.root)["matrix"])


def test_the_control_is_a_natural_pair_20_mm_over_and_is_keyed(built):
    e = entry(built, M.SCOPE_PART, "Plain")
    assert e["tier"] == "same_pack_fit" and e["seat_shift_m"] == -0.02
    assert built.by_id[M.hid("Plain")]["geometry"]["mounts"]["optic"]["point"] == [0.0, 0.12, 0.0]  # 20 mm over the body top at 0.10


@pytest.mark.parametrize("case", ["Plain", "NoOvr", "MountOvr"])
def test_a_twin_entry_has_no_key_and_places_byte_identically(built, case):
    e = entry(built, M.TWIN_PART, case)
    assert e["tier"] == "twin" and "seat_shift_m" not in e
    pair, p, h, got = matrix_of(built, M.TWIN_PART, case)
    mount = h["geometry"]["mounts"]["optic"]
    frame = mount["seats"][e["replaces"][0]] if len(e["replaces"]) == 1 and e["replaces"][0] in (mount.get("seats") or {}) else mount
    assert np.array_equal(got, np.asarray(place(p["attachment"]["anchor"], frame)))
    assert frame["point"] == [0.0, 0.12, 0.0] and got[1, 3] != 0.0  # it really sits 20 mm up: the point is the child's, not the body's


def test_an_entry_of_tier_override_has_no_key(built):
    e = entry(built, M.ZETA_PART, "Plain")
    assert e["tier"] == "override" and "seat_shift_m" not in e
    _, p, h, got = matrix_of(built, M.ZETA_PART, "Plain")
    assert np.array_equal(got, np.asarray(place(p["attachment"]["anchor"], h["geometry"]["mounts"]["optic"])))


def test_a_pair_on_an_override_source_mount_has_no_key(built):
    mount = built.by_id[M.hid("MountOvr")]["geometry"]["mounts"]["optic"]
    assert mount["source"] == "override" and mount["point"] == [0.0, 0.12, 0.0]
    e = entry(built, M.SCOPE_PART, "MountOvr")
    assert e["tier"] == "same_pack_fit" and "seat_shift_m" not in e  # the natural scope fits it, 20 mm up, and is left alone
    _, p, h, got = matrix_of(built, M.SCOPE_PART, "MountOvr")
    assert np.array_equal(got, np.asarray(place(p["attachment"]["anchor"], mount)))


def test_the_same_scope_on_a_geometry_seat_next_door_is_keyed(built):
    # NoOvr is MountOvr's twin host with no override: only the mount source differs, and the natural pair is keyed there
    assert built.by_id[M.hid("NoOvr")]["geometry"]["mounts"]["optic"]["source"] == "child_node"
    assert entry(built, M.SCOPE_PART, "NoOvr")["seat_shift_m"] == -0.02
