"""FAKE_G1 pack: synthetic fixtures for the frame-changed sight-slot clause (docs/weapon_attach_geometry.md 3.8; AC139, AC149; errata E3.5).

Reads ``g1_frame_world.py`` (the Uzi, the both-rings host, the plain rifle) and edits nothing in it. Y-up, metres. Nothing is from a real pack.
Every expected number in the tests is a LITERAL worked out by hand from the dimensions below, never read from the code under test.

POST      the Uzi of AC147 (receiver x +-0.02, y 0..0.08, z -0.10..0.05; barrel tube along z, axis (x 0, y 0.04), z 0.05..0.20, its top at
          y 0.052; a magazine child y -0.30..0) with a fused front post on the barrel, near the muzzle: a box x +-0.005, y 0.04..0.076,
          z 0.160..0.185. It is 25 mm wide along the barrel and stands 0.076 - 0.052 = 24 mm over it. The post stops 15 mm short of the muzzle
          face (z 0.20), so it never enters the 10 mm end slab of the ring estimator: the 15 mm bore ring, and with it the frame vote, is the
          Uzi's own.
          Voted frame: forward +z over the extent -0.10..0.20. The detector finds one raised run, the post: centre at 0.1675 (bins of 5 mm), position
          0.89 of the extent (the detector wants 0.6 or more), 25 mm wide (10 to 30 mm) and 24 mm over its baseline (8 mm): a fused front post.
          The probe seats both sight slots there (separation 0.287, over the 0.06 minimum); the post turns them into slot_disabled.
          Build frame: forward -y over the extent -0.08..0.30 (the magazine bottom is the far end). The profile exists and the detector still
          finds one raised run (30 mm wide, 15 mm over its baseline: the same box seen along y), but at position 0.105 of the extent, far under
          0.6, so it is no front post; the probe refuses (no seats): both slots stay probe_unavailable. (Both measured by calling sight_profile,
          fused_runs and sight_seats on the fixture mesh in each frame.)
RIFLE     the plain rifle of g1_frame_world: its body axis is the build axis, so the vote leaves its frame alone.
BOTH      the both-rings host of g1_frame_world: a frame conflict, which keeps the build frame; the vote changes nothing either.
SIGHT_*   a front and a rear iron sight part (the W8h sight stand-in), so that the hosts have listed and pending pairs to count.
PLAIN     the Uzi of g1_frame_world as it is, with no post (added to the world on request only, ``sight_world(with_plain=True)``). Its frame
          changes with the vote, and its sight probe finds no seat in the build frame but seats both slots in the voted frame (separation
          0.287, over the 0.06 minimum), with no fused post to refuse them: a frame-changed host that GAINS a seat. The clause of AC139 and
          AC149 does not cover that; the live pin of ``test_weapons_e3_sight_clause.py`` counts such hosts in the real directory.

The "old frame" of the tests is the ``frame_axis: y`` id override on POST (the build axis; ``test_frame_axis_on_the_build_axis_keeps_the_build_frame``
in test_weapons_g1_frame.py): the same mesh, measured and probed in the build frame, as the label-era directory had it. The voted build is the
same world with no override.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


F = _load("g1_frame_world")
W, G = F.W, F.G

PACK = F.PACK
POST = "SM_Wep_SMG_Post_01"
RIFLE, BOTH, PLAIN = F.RIFLE, F.BOTH, F.UZI
SIGHT_FRONT, SIGHT_REAR = "SM_Wep_IronSight_Front_01", "SM_Wep_IronSight_Rear_01"

POST_Z = (0.160, 0.185)  # the post along the barrel: 25 mm
POST_TOP = 0.076  # 24 mm over the barrel top at 0.052
POST_HALF_X = 0.005


def post_body():
    """The Uzi body plus the fused front post (a box over the barrel)."""
    return G.merge(F.uzi_body(), F.box((-POST_HALF_X, 0.04, POST_Z[0]), (POST_HALF_X, POST_TOP, POST_Z[1])))


def sight_world(with_plain: bool = False) -> dict:
    """Three hosts (POST, RIFLE, BOTH) and the two iron sight parts, in the one pack FAKE_G1; PLAIN too when ``with_plain``."""
    hosts = {
        POST: F.host_nodes(POST, post_body(), "Mag", F.mag(-0.30)),
        RIFLE: F.host_nodes(RIFLE, F.rifle_body(), "Mag", F.mag(-0.10, -0.2, -0.16)),
        BOTH: F.host_nodes(BOTH, F.both_body(), "Mag", F.mag(-0.45)),
    }
    if with_plain:
        hosts[PLAIN] = F.host_nodes(PLAIN, F.uzi_body(), "Mag", F.mag(-0.30))
    return {PACK: {"hosts": hosts, "parts": {SIGHT_FRONT: W.sight_part, SIGHT_REAR: W.sight_part}}}


def pid(name: str) -> str:
    return F.pid(name)


def voted_overrides() -> dict:
    """The feature frame: the frame vote applies, so POST gets the body axis z."""
    return F.overrides()


def build_frame_overrides(with_plain: bool = False) -> dict:
    """The old frame: ``frame_axis: y`` names the build axis for POST (and PLAIN), so its frame, and with it the sight probe, stays the build frame."""
    ids = {pid(POST): {"frame_axis": "y"}}
    if with_plain:
        ids[pid(PLAIN)] = {"frame_axis": "y"}
    return F.overrides(ids)
