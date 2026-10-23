"""FAKE_W8M* packs: synthetic settle-to-contact fixtures for the W8m tests (docs/weapon_attachments.md 5.4; AC112, AC113, AC114).

Written into a temp folder by ``w8h_world.write_world`` (nothing is from a real pack). Every host is a box body with ONE baked child that gives
the optic (or underbarrel) mount, and every expected number in the tests is a LITERAL worked out by hand from the dimensions below.

Y-up, metres, +z forward, x centred on 0. The mount of a ``child_node`` seat is the baked child's foot centre, and the part's anchor is its own
foot centre, so the part's foot lands exactly on the child's foot: the gap between the part and the host body is the child's foot height minus
the body top (an optic; the body bottom minus the child's foot height for an underbarrel part), set per host below.

  body        x +-0.02, y 0..0.10, z -0.25..0.35 (top face y 0.10, bottom face y 0)
  scope child x +-0.01, y 0..0.04, z +-0.03 (20 x 40 x 60 mm), foot centre (0, bottom, 0); the part below is NOT its twin
  Scope part  x +-0.015, y 0..0.05, z +-0.04 (30 x 50 x 80 mm): foot centre (0, 0, 0), forward +z, up +y; its bottom face is the contact face
  grip child  x +-0.005, y -0.08..0, z +-0.01, hanging from its foot centre (0, top, 0)
  Grip part   x +-0.015, y -0.10..0, z +-0.015: foot centre (0, 0, 0); its top face (y 0) is the contact face; the mount's up is -y

The optic mount's up is +y, so ``seat_shift_m`` > 0 raises the part; an underbarrel mount's up is -y, so ``seat_shift_m`` > 0 lowers it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("w8h_world", HERE / "w8h_world.py")
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)
G = W.G

PACK = "FAKE_W8M"
BODY = ((-0.02, 0.0, -0.25), (0.02, 0.10, 0.35))
SCOPE_CHILD = ((-0.01, 0.0, -0.03), (0.01, 0.04, 0.03))
GRIP_CHILD = ((-0.005, -0.08, -0.01), (0.005, 0.0, 0.01))

SCOPE_PART = "SM_Wep_Rifle_Scope_01"  # shares the family token rifle with every host: same_pack_fit
TAB_PART = "SM_Wep_Rifle_Scope_Tab_01"
GRIP_PART = "SM_Wep_Zulu_Foregrip_01"  # underbarrel is family-free
MAG_PART = "SM_Wep_Rifle_Mag_01"
LASER_PART = "SM_Wep_Mod_Misc_Laser_01"
SILENCER_PART = "SM_Wep_Silencer_01"
SIGHT_PART = "SM_Wep_IronSight_Front_01"
OTHER_PARTS = (MAG_PART, LASER_PART, SILENCER_PART, SIGHT_PART)  # (xi): slots that never get a key


def host_id(case: str) -> str:
    return f"SM_Wep_Rifle_{case}_01"


def pid(name: str) -> str:
    return f"{PACK}/{name}"


def hid(case: str) -> str:
    return f"{PACK}/{host_id(case)}"


def scope_part():
    return G.box((-0.015, 0.0, -0.04), (0.015, 0.05, 0.04))


def tab_part():
    """A 3 mm tab under a body (the contact face), a canopy that overhangs on the sides. The 4 mm foot slab is the tab plus 1 mm of body.

    tab x +-0.005, y 0..0.003, z +-0.01; body x +-0.015, y 0.003..0.043, z +-0.04; canopy x +-0.04, y 0.043..0.053, z +-0.04.
    """
    return G.merge(G.box((-0.005, 0.0, -0.01), (0.005, 0.003, 0.01)), G.box((-0.015, 0.003, -0.04), (0.015, 0.043, 0.04)),
                   G.box((-0.04, 0.043, -0.04), (0.04, 0.053, 0.04)))


def grip_part():
    return G.box((-0.015, -0.10, -0.015), (0.015, 0.0, 0.015))


def mag_part():
    """Hangs from a foot at y 0 (30 x 120 x 60 mm): not a twin of the 20 x 100 x 40 mm child below."""
    return G.box((-0.015, -0.12, -0.03), (0.015, 0.0, 0.03))


def laser_part():
    """Stands on a foot at y 0 (30 x 40 x 60 mm): not a twin of the 20 x 30 x 40 mm child below."""
    return G.box((-0.015, 0.0, -0.03), (0.015, 0.04, 0.03))


def silencer_part():
    return G.box((-0.015, -0.015, 0.0), (0.015, 0.015, 0.2))


def sight_part():
    return W.sight_part()


def body_mesh(*boxes):
    return G.merge(*[G.box(*b) for b in (boxes or (BODY,))])


def host(case: str, kids=(), mesh=None):
    """A host named for ``case``; ``kids`` are ``(suffix, mesh, translation)``; ``mesh`` replaces the box body."""
    name = host_id(case)
    return W.host_node(name, mesh if mesh is not None else body_mesh(), [W.kid(name, suffix, m, at) for suffix, m, at in kids])


def scope_kid(bottom: float, x: float = 0.0, box=SCOPE_CHILD, suffix: str = "Scope"):
    return (suffix, G.box(*box), (x, bottom, 0.0))


def grip_kid(top: float, suffix: str = "Foregrip"):
    return (suffix, G.box(*GRIP_CHILD), (0.0, top, 0.0))


def tube_mesh():
    """The body with a hollow in its top: outer box y 0..0.10, a cavity shell x +-0.015, y 0.085..0.098, z +-0.2. A column down through it meets
    y 0.100 (outer top), 0.098 (cavity ceiling), 0.085 (cavity floor) and 0 (outer bottom)."""
    return G.merge(G.box(*BODY), G.box((-0.015, 0.085, -0.2), (0.015, 0.098, 0.2)))


def wing_mesh():
    """The body plus two rails beside the optic seat: x +-(0.026..0.034), y 0..0.16, z +-0.1."""
    return G.merge(G.box(*BODY), G.box((0.026, 0.0, -0.1), (0.034, 0.16, 0.1)), G.box((-0.034, 0.0, -0.1), (-0.026, 0.16, 0.1)))


def shoulder_mesh():
    """A body whose right half (x > 0) is 20 mm lower: left block x -0.02..0, y 0..0.10; right block x 0..0.02, y 0..0.08."""
    return G.merge(G.box((-0.02, 0.0, -0.25), (0.0, 0.10, 0.35)), G.box((0.0, 0.0, -0.25), (0.02, 0.08, 0.35)))


def hosts() -> dict:
    out = {
        # (i)-(v): the scope child's foot height IS the part's foot height; the body top is 0.10
        "Hover": host("Hover", [scope_kid(0.111)]),         # gap 11.0 mm
        "Sunk": host("Sunk", [scope_kid(0.092)]),           # sunk 8.0 mm
        "Near": host("Near", [scope_kid(0.1029)]),          # gap 2.9 mm: inside the dead zone
        "Far": host("Far", [scope_kid(0.1031)]),            # gap 3.1 mm
        "Far90": host("Far90", [scope_kid(0.19)]),          # gap 90 mm: the clamp binds
        "Far59": host("Far59", [scope_kid(0.159)]),         # gap 59 mm
        "Tube": host("Tube", [scope_kid(0.0865)], tube_mesh()),   # the cavity floor is 1.5 mm under the part, the outer top 13.5 mm over it
        # (vii): a hidden child 20 mm taller than the receiver; a collision node 20 mm above the receiver
        "Tall": host("Tall", [scope_kid(0.08)]),            # the child's own box reaches 0.12 (hidden); the part is sunk 20 mm into the body
        "Collide": host("Collide", [scope_kid(0.09), ("Collision", G.box((-0.02, 0.10, -0.1), (0.02, 0.12, 0.1)), (0.0, 0.0, 0.0))]),
        # (ix): the seat is beside the body: no host under the face
        "Aside": host("Aside", [scope_kid(0.111, x=0.10)]),
        # (x): half the face touches, the other half is 20 mm up
        "Shoulder": host("Shoulder", [scope_kid(0.10)], shoulder_mesh()),
        # (viii): rails beside the seat reach 0.16; the tab part's tab bottom is 7 mm over the body top
        "Wing": host("Wing", [scope_kid(0.107)], wing_mesh()),
        # (xi): a magazine hanging 15 mm under the body and a laser standing 15 mm over it would be 15 mm gaps if the rule applied to their slots
        "Misc": host("Misc", [("Mag", G.box((-0.01, -0.10, -0.02), (0.01, 0.0, 0.02)), (0.0, -0.015, 0.1)),
                              ("Laser", G.box((-0.01, 0.0, -0.02), (0.01, 0.03, 0.02)), (0.0, 0.115, -0.1))]),
        # (iv): underbarrel children; the body bottom is y 0 and the mount's up is -y
        "UbGap": host("UbGap", [grip_kid(-0.012)]),         # the grip's top is 12.0 mm under the body
        "UbSunk": host("UbSunk", [grip_kid(0.0377)]),       # sunk 37.7 mm into the body
    }
    return {host_id(case): node for case, node in out.items()}


def world() -> dict:
    return {PACK: {"hosts": hosts(), "parts": {SCOPE_PART: scope_part, TAB_PART: tab_part, GRIP_PART: grip_part, MAG_PART: mag_part,
                                                LASER_PART: laser_part, SILENCER_PART: silencer_part, SIGHT_PART: sight_part}}}


# -- AC113: authored placements never move ---------------------------------------------------------------------------
# Every host below seats its scope child's foot 20 mm over the body top (y 0.12), so a pair placed on it is 20 mm off the host's mesh.

TWIN_PART = "SM_Wep_Rifle_Scope_Dup_01"  # the scope child's own box: an exact dimensional twin of every baked scope child here
ZETA_PART = "SM_Wep_Zeta_Scope_01"  # shares no family token with any host: listed only through an override
SMALL_CHILD = ((-0.01, 0.0, -0.02), (0.01, 0.03, 0.02))


def twin_part():
    return G.box(*SCOPE_CHILD)


def zeta_part():
    return G.box((-0.02, 0.0, -0.05), (0.02, 0.06, 0.05))


def authored_hosts() -> dict:
    out = {
        "Plain": host("Plain", [scope_kid(0.12)]),            # the control: a natural pair, 20 mm over, keyed -0.0200
        "NoOvr": host("NoOvr", [scope_kid(0.12, suffix="Scope_A"), scope_kid(0.12, x=0.0, box=SMALL_CHILD, suffix="Scope_B")]),
        "MountOvr": host("MountOvr", [scope_kid(0.12, suffix="Scope_A"), scope_kid(0.12, x=0.0, box=SMALL_CHILD, suffix="Scope_B")]),
    }
    return {host_id(case): node for case, node in out.items()}


def authored_world() -> dict:
    return {PACK: {"hosts": authored_hosts(), "parts": {SCOPE_PART: scope_part, TWIN_PART: twin_part, ZETA_PART: zeta_part}}}


def authored_overrides() -> dict:
    """The Zeta scope is listed on Plain by an override (tier ``override``); MountOvr's optic seat is its Scope_B child (source ``override``)."""
    return W.overrides_doc(ids={
        pid(ZETA_PART): {"compatible": {"add": [hid("Plain")]}},
        hid("MountOvr"): {"mounts": {"optic": {"source": "child_node", "child": f"{host_id('MountOvr')}_Scope_B"}}},
    })
