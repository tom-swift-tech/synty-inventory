"""W8f part A: a twin pair seats on the baked child it matches (docs/weapon_attachments.md amendment A1, AC85).

World ``seat`` of ``fixtures/weapons/w8f_world.py`` (hand-derived numbers in its docstring): the upright host TWIN with two
magazine children (a small one that sorts first and a large one that owns the mount's own seat) and one scope child, and SPIN,
the same children on a body turned about X, whose ``item_basis`` is rows (-1,0,0), (0,0,1), (0,1,0) (item = (-x, z, y)).
Every number below is a literal worked out from those meshes, never read from the code under test.
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

from synty_inventory.weapons import export, preview  # noqa: E402
from synty_inventory.weapons.schema import validate_record  # noqa: E402

TWIN, SPIN = W.ID[W.TWIN], W.ID[W.SPIN]
SMALL, LARGE = f"{W.TWIN}_Mag_A_Small", f"{W.TWIN}_Mag_B_Large"
S_SMALL, S_LARGE = f"{W.SPIN}_Mag_A_Small", f"{W.SPIN}_Mag_B_Large"
MAG_SMALL, MAG_LARGE = W.ID[W.MAG_SMALL], W.ID[W.MAG_LARGE]
DOWN, FWD = [0.0, -1.0, 0.0], [0.0, 0.0, 1.0]


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    cache: dict = {}
    directory, excluded, cat, root = W.build(tmp_path_factory.mktemp("w8f_seats"), "seat", cache=cache)
    return {"directory": directory, "by_id": W.by_id(directory), "root": root, "cache": cache}


def mag_mount(world, host):
    return world["by_id"][host]["geometry"]["mounts"]["magazine"]


# --- the mount carries one frame per listed child ---------------------------------------------------------------


def test_a_slot_with_two_children_carries_a_frame_per_child_and_keeps_the_larger_as_the_seat(world):
    m = mag_mount(world, TWIN)
    assert m["occupied_by"] == [SMALL, LARGE]
    assert m["child_node"] == LARGE and m["point"] == [0.0, 0.0, 0.1] and m["span_m"] == 0.06  # the mount's own seat: the larger
    assert sorted(m["seats"]) == [SMALL, LARGE]
    assert m["seats"][SMALL] == {"point": [0.0, 0.0, -0.1], "forward": FWD, "up": DOWN, "span_m": 0.04}
    assert m["seats"][LARGE] == {"point": [0.0, 0.0, 0.1], "forward": FWD, "up": DOWN, "span_m": 0.06}
    assert m["seats"][LARGE] == {k: m[k] for k in ("point", "forward", "up", "span_m")}  # the larger child's frame IS the mount's


def test_the_turned_host_seats_are_in_its_asset_frame(world):
    m = mag_mount(world, SPIN)  # body turned (x, y, z) -> (x, z, -y): forward +y, up +z, so a magazine takes up -z
    assert m["child_node"] == S_LARGE and sorted(m["seats"]) == [S_SMALL, S_LARGE]
    assert m["seats"][S_SMALL] == {"point": [0.0, -0.1, 0.0], "forward": [0.0, 1.0, 0.0], "up": [0.0, 0.0, -1.0], "span_m": 0.04}
    assert m["seats"][S_LARGE] == {"point": [0.0, 0.1, 0.0], "forward": [0.0, 1.0, 0.0], "up": [0.0, 0.0, -1.0], "span_m": 0.06}


def test_a_slot_with_one_child_a_none_slot_and_the_muzzle_have_no_seats_key(world):
    for host in (TWIN, SPIN):
        for slot, m in world["by_id"][host]["geometry"]["mounts"].items():
            if slot == "magazine":
                continue
            assert "seats" not in m, (host, slot)  # optic: one child; muzzle: probe; underbarrel / laser_light: none
    assert world["by_id"][TWIN]["geometry"]["mounts"]["optic"]["source"] == "child_node"
    assert world["by_id"][TWIN]["geometry"]["mounts"]["underbarrel"]["source"] == "none"


def test_the_child_extents_evidence_carries_extents_axes_and_the_seat_frame_beside_the_record(world):
    entries = [d for e in world["cache"].values() for d in e["by_inputs"].values() if "child_extents" in d]
    ev = next(d["child_extents"] for d in entries if "magazine" in d["child_extents"] and d["mounts"]["magazine"]["child_node"] == LARGE)
    rows = ev["magazine"]
    assert sorted(rows) == [SMALL, LARGE]
    assert rows[SMALL]["extents"] == [0.02, 0.04, 0.08] and rows[SMALL]["axes"] == [0.02, 0.08, 0.04]  # sorted / x, y, z
    assert rows[LARGE]["extents"] == [0.024, 0.06, 0.14] and rows[LARGE]["axes"] == [0.024, 0.14, 0.06]
    assert rows[SMALL]["seat"] == {"point": [0.0, 0.0, -0.1], "forward": FWD, "up": DOWN, "span_m": 0.04}
    assert rows[LARGE]["seat"]["point"] == [0.0, 0.0, 0.1]
    assert rows[SMALL]["seat"] == mag_mount(world, TWIN)["seats"][SMALL]
    assert "child_extents" not in world["by_id"][TWIN] and "child_extents" not in world["by_id"][TWIN]["geometry"]  # never in the record


# --- compatibility: a twin entry names the child it matches -----------------------------------------------------------


def entry(world, part, host):
    return next(e for e in world["by_id"][part]["attachment"]["compatible_hosts"] if e["host"] == host)


def test_a_twin_entry_replaces_the_one_child_it_matches_not_the_whole_slot(world):
    assert entry(world, MAG_SMALL, TWIN)["tier"] == "twin" and entry(world, MAG_SMALL, TWIN)["replaces"] == [SMALL]
    assert entry(world, MAG_LARGE, TWIN)["tier"] == "twin" and entry(world, MAG_LARGE, TWIN)["replaces"] == [LARGE]
    assert entry(world, MAG_SMALL, SPIN)["replaces"] == [S_SMALL]
    assert entry(world, MAG_LARGE, SPIN)["replaces"] == [S_LARGE]
    for rec in world["by_id"].values():
        assert validate_record(rec) == [], rec["id"]


# --- placement: the pair sits on its own child's frame ---------------------------------------------------------------


def job_of(world, part, host):
    pair = next(p for p in preview.plan_pairs(world["directory"], ids={part})[0] if p["host"] == host)
    return preview.build_job(pair, world["by_id"][part], world["by_id"][host], world["root"])


def placed_box(job, mesh):
    verts = mesh[0]
    return W.aabb((np.c_[verts, np.ones(len(verts))] @ np.asarray(job["matrix"]).T)[:, :3])


# the baked child's AABB in the host frame: its mesh (x +-hx, y -h..0, z +-hz) moved by the node translation
CHILD_BOX = {
    MAG_SMALL: ((-0.01, -0.08, -0.12), (0.01, 0.0, -0.08)),
    MAG_LARGE: ((-0.012, -0.14, 0.07), (0.012, 0.0, 0.13)),
}


@pytest.mark.parametrize("part", [MAG_SMALL, MAG_LARGE])
def test_the_twin_is_placed_on_its_own_child_centre_within_0_1_mm_and_iou_99(world, part):
    job = job_of(world, part, TWIN)
    mesh = W.PART_MESHES[part.split("/")[1]]()
    box = placed_box(job, mesh)
    want = (np.array(CHILD_BOX[part][0]), np.array(CHILD_BOX[part][1]))
    assert np.all(np.abs((box[0] + box[1]) / 2 - (want[0] + want[1]) / 2) <= 0.0001), (box, want)
    assert W.iou(box, want) >= 0.99
    assert job["hide"] == sorted([SMALL, LARGE])  # E1: the whole slot is hidden, whichever child the twin is seated on


def test_a_pair_that_is_not_a_twin_keeps_the_mount_seat_and_hides_the_whole_slot(world):
    part, host = world["by_id"][MAG_SMALL], world["by_id"][TWIN]
    pair = {"part": MAG_SMALL, "host": TWIN, "slot": "magazine", "tier": "same_pack_fit", "score": 0.7, "twin": False}
    job = preview.build_job(pair, part, host, world["root"])
    assert job["hide"] == sorted([SMALL, LARGE])
    m = np.asarray(job["matrix"])
    assert np.allclose((m @ np.append(part["attachment"]["anchor"]["point"], 1.0))[:3], [0.0, 0.0, 0.1], atol=1e-6)  # the mount's seat


def test_a_twin_on_a_single_child_slot_places_on_the_mount_and_hides_that_child(world):
    part = copy.deepcopy(world["by_id"][MAG_SMALL])
    host = copy.deepcopy(world["by_id"][TWIN])
    m = host["geometry"]["mounts"]["magazine"]
    del m["seats"]
    m.update(occupied_by=[SMALL], child_node=SMALL, point=[0.0, 0.0, -0.1], span_m=0.04)
    part["attachment"]["compatible_hosts"] = [dict(entry(world, MAG_SMALL, TWIN), replaces=[SMALL])]
    pair = {"part": MAG_SMALL, "host": TWIN, "slot": "magazine", "tier": "twin", "score": 0.95, "twin": True}
    job = preview.build_job(pair, part, host, world["root"])
    assert job["hide"] == [SMALL]
    box = placed_box(job, W.small_mag())
    assert np.allclose(box[0], CHILD_BOX[MAG_SMALL][0], atol=1e-4) and np.allclose(box[1], CHILD_BOX[MAG_SMALL][1], atol=1e-4)


# --- export: every seat is baked through the record's own item_basis ------------------------------------------------


def snapshot(world, **kw):
    args = dict(game="g", pack_ids={W.PACK}, ids=None, roles={"whole", "part"}, engines={"all"}, frame="item", profile="private",
                pack_meta={}, rules_digest="0123456789abcdef", overrides_digest="fedcba9876543210", attachments=True)
    return export.export_snapshot(world["directory"], **{**args, **kw})


def test_the_item_frame_export_bakes_every_seat_through_the_hosts_own_basis(world):
    before = copy.deepcopy(world["directory"])
    doc = snapshot(world)
    spin = next(w for w in doc["weapons"] if w["id"] == SPIN)
    assert spin["geometry"]["item_basis"] == [[-1, 0, 0], [0, 0, 1], [0, 1, 0]]  # item = (-x, z, y)
    m = spin["geometry"]["mounts"]["magazine"]
    # asset (0, -0.1, 0) / forward (0, 1, 0) / up (0, 0, -1)  ->  item (0, 0, -0.1) / (0, 0, 1) / (0, -1, 0)
    assert m["seats"][S_SMALL] == {"point": [0.0, 0.0, -0.1], "forward": [0.0, 0.0, 1.0], "up": [0.0, -1.0, 0.0], "span_m": 0.04}
    assert m["seats"][S_LARGE] == {"point": [0.0, 0.0, 0.1], "forward": [0.0, 0.0, 1.0], "up": [0.0, -1.0, 0.0], "span_m": 0.06}
    assert (m["point"], m["forward"], m["up"]) == (m["seats"][S_LARGE]["point"], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0])  # the mount alike
    assert world["directory"] == before  # the baked copy shares nothing with the directory
    assert world["by_id"][SPIN]["geometry"]["mounts"]["magazine"]["seats"][S_SMALL]["point"] == [0.0, -0.1, 0.0]
    assert export.check_snapshot(doc) == []  # the snapshot validator accepts `seats`


def test_the_asset_frame_export_keeps_the_seats_as_measured_and_the_default_export_has_none(world):
    doc = snapshot(world, frame="asset")
    spin = next(w for w in doc["weapons"] if w["id"] == SPIN)
    assert spin["geometry"]["mounts"]["magazine"]["seats"][S_SMALL]["point"] == [0.0, -0.1, 0.0]
    plain = snapshot(world, attachments=False, roles={"whole"})
    assert "seats" not in str(plain)


# --- schema ------------------------------------------------------------------------------------------------------------


def broken(world, mutate):
    rec = copy.deepcopy(world["by_id"][TWIN])
    mutate(rec["geometry"]["mounts"]["magazine"]["seats"])
    return validate_record(rec)


def test_the_schema_validates_each_seat_like_a_frame(world):
    assert validate_record(world["by_id"][TWIN]) == []
    # structural: the directory schema reports these as one `geometry` error
    assert broken(world, lambda s: s[SMALL].__setitem__("point", [0.0, 0.0]))  # not a 3-vector
    assert broken(world, lambda s: s[SMALL].__setitem__("span_m", "wide"))
    assert broken(world, lambda s: s[SMALL].__setitem__("extra", 1))
    assert broken(world, lambda s: s[SMALL].pop("up"))
    assert broken(world, lambda s: s.__setitem__(SMALL, "not a frame"))
    assert broken(world, lambda s: s[SMALL].__setitem__("span_m", None)) == []  # span_m is a number or null
    # cross-field, named by seat: INV-18 like the mount's own frame, and a seat is a node the mount lists
    assert any(f"seats.{SMALL}.up" in e and "unit" in e for e in broken(world, lambda s: s[SMALL].__setitem__("up", [0.0, -2.0, 0.0])))
    assert any(f"seats.{SMALL}" in e and "orthogonal" in e for e in broken(world, lambda s: s[SMALL].__setitem__("up", [0.0, -0.6, 0.8])))
    assert any("Not_A_Child" in e and "occupied_by" in e for e in broken(world, lambda s: s.__setitem__("Not_A_Child", dict(s[SMALL]))))
