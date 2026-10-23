"""W8g (erratum E1): a preview hides the whole slot, whichever child a twin is seated on (docs/weapon_attachments.md E1).

The runtime hides EVERY node of the slot's ``occupied_by`` while a part is mounted. World ``seat`` of
``fixtures/weapons/w8f_world.py``: the host TWIN has a small and a large magazine child (the larger owns the mount's own seat),
one scope child and no other. Node names and boxes below are literals worked out from those meshes, never read from the code
under test; a twin entry's ``replaces`` chooses the seat only.
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

from synty_inventory.weapons import preview  # noqa: E402

TWIN, SPIN = W.ID[W.TWIN], W.ID[W.SPIN]
MAG_SMALL, MAG_LARGE = W.ID[W.MAG_SMALL], W.ID[W.MAG_LARGE]
SMALL, LARGE = f"{W.TWIN}_Mag_A_Small", f"{W.TWIN}_Mag_B_Large"
BOTH = [SMALL, LARGE]  # sorted: "..._Mag_A_Small" < "..._Mag_B_Large"
# the small baked magazine's AABB in the host frame (mesh x +-0.01, y -0.08..0, z +-0.02 moved by the node translation)
SMALL_BOX = ((-0.01, -0.08, -0.12), (0.01, 0.0, -0.08))


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    directory, excluded, cat, root = W.build(tmp_path_factory.mktemp("w8g_hide"), "seat")
    return {"directory": directory, "by_id": W.by_id(directory), "root": root}


def job_of(world, part, host):
    pair = next(p for p in preview.plan_pairs(world["directory"], ids={part})[0] if p["host"] == host)
    return preview.build_job(pair, world["by_id"][part], world["by_id"][host], world["root"])


def placed_box(job, mesh):
    verts = mesh[0]
    return W.aabb((np.c_[verts, np.ones(len(verts))] @ np.asarray(job["matrix"]).T)[:, :3])


def test_the_twin_of_the_smaller_magazine_hides_both_baked_magazines_and_stays_on_its_own_seat(world):
    job = job_of(world, MAG_SMALL, TWIN)
    assert job["twin"] is True
    assert job["hide"] == BOTH  # E1: not just the small child it matches
    box = placed_box(job, W.PART_MESHES[MAG_SMALL.split("/")[1]]())
    want = (np.array(SMALL_BOX[0]), np.array(SMALL_BOX[1]))
    assert np.all(np.abs((box[0] + box[1]) / 2 - (want[0] + want[1]) / 2) <= 0.0001), (box, want)  # centre within 0.1 mm
    assert W.iou(box, want) >= 0.99  # still the twin-seat placement


def test_the_twin_of_the_larger_magazine_hides_both_baked_magazines_too(world):
    assert job_of(world, MAG_LARGE, TWIN)["hide"] == BOTH


def test_a_pair_that_is_not_a_twin_hides_both_magazines_on_the_mount_seat(world):
    part, host = world["by_id"][MAG_SMALL], world["by_id"][TWIN]
    pair = {"part": MAG_SMALL, "host": TWIN, "slot": "magazine", "tier": "same_pack_fit", "score": 0.7, "twin": False}
    assert preview.build_job(pair, part, host, world["root"])["hide"] == BOTH


def test_a_twin_on_a_one_child_slot_still_hides_exactly_that_child(world):
    part = copy.deepcopy(world["by_id"][MAG_SMALL])
    host = copy.deepcopy(world["by_id"][TWIN])
    m = host["geometry"]["mounts"]["magazine"]
    del m["seats"]
    m.update(occupied_by=[SMALL], child_node=SMALL, point=[0.0, 0.0, -0.1], span_m=0.04)
    entry = next(e for e in part["attachment"]["compatible_hosts"] if e["host"] == TWIN)
    part["attachment"]["compatible_hosts"] = [dict(entry, replaces=[SMALL])]
    pair = {"part": MAG_SMALL, "host": TWIN, "slot": "magazine", "tier": "twin", "score": 0.95, "twin": True}
    assert preview.build_job(pair, part, host, world["root"])["hide"] == [SMALL]


def test_no_pair_of_the_world_hides_less_than_its_slots_occupied_by_and_child_node(world):
    pairs = preview.plan_pairs(world["directory"])[0]
    assert any(p["twin"] for p in pairs)
    for pair in pairs:
        job = preview.build_job(pair, world["by_id"][pair["part"]], world["by_id"][pair["host"]], world["root"])
        mount = world["by_id"][pair["host"]]["geometry"]["mounts"][pair["slot"]]
        whole = set(mount.get("occupied_by") or []) | ({mount["child_node"]} if mount.get("child_node") else set())
        assert set(job["hide"]) >= whole, (pair["part"], pair["host"], job["hide"], sorted(whole))
        assert job["hide"] == sorted(whole)
    twin_two = [p for p in pairs if p["twin"] and p["host"] in (TWIN, SPIN) and p["slot"] == "magazine"]
    assert len(twin_two) >= 4  # both magazine parts on both two-magazine hosts were looked at
