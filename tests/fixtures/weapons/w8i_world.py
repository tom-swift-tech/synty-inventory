"""FAKE_* packs: synthetic hosts for the W8i tests (docs/weapon_attachments.md 4.6 items 1 and 7, 5.1 A3, 7; AC94-AC98).

Written into a temp folder through ``w8h_world.write_world`` (not part of make_catalogs.py, for the reason stated in w8a_attach.py).
Meshes are boxes, the W8h box rifle / slide pistol / prism and the W8a optic scaled down to a sight; nothing is from a real pack.
Every expected number in the tests is a LITERAL worked out by hand from the dimensions below, never read from the code under test.

Hosts are +z forward, +y up, centred on x 0 (child nodes are moved by a translation only; a child's name is ``<host>_<suffix>``):

  box rifle  receiver top y 0.10 over z -0.2525..0.0475, handguard top y 0.075 to z 0.4012, barrel to z 0.65. Its axial extent along
             +z is -0.2525..0.65, so the middle is z 0.19875: a child centred above it is on the muzzle half, below it on the rear half.
  slide      a pistol slide x +-0.015, y 0.03..0.075, z -0.09..0.09 over a grip (the W8h host). Top y 0.075.
  prism      the W8h tent the sight probe refuses (its top run is under 3 bins): both sight slots are ``probe_unavailable``.

Children used here (each a box, ``block``): a sight post of 8 x 20 x 8 mm, a 40 mm long carry handle, a 12 mm tall suppressor
that stands 20 mm over the slide top, and so on; the tests state each child's translation next to its use.
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


W = _load("w8h_world")
A, G = W.A, W.G

SIGHT_FRONT, SIGHT_REAR = "SM_Wep_IronSight_Front_01", "SM_Wep_IronSight_Rear_01"  # the two parts of one set (sight_front / sight_rear)

# the middle of the box rifle along +z (-0.2525..0.65): a child centred above it is on the muzzle half
RIFLE_MID_Z = 0.19875
FRONT_HALF_Z, REAR_HALF_Z = 0.45, -0.20


def block(hx: float, hy: float, hz: float):
    """A box of half extents (hx, hy, hz) centred on its node origin."""
    return G.box((-hx, -hy, -hz), (hx, hy, hz))


def sight_post():
    """A baked sight post: 8 x 4 x 8 mm, to be moved to y 0.102 so it stands 4 mm over the receiver top (y 0.10). It is low on purpose:
    an unsided baked sight stays in the probe mesh (4.6 item 7 leaves item 1 alone), and a taller post would be the top of the profile."""
    return block(0.004, 0.002, 0.004)


def rifle(name: str, kids=()):
    """Root nodes of a box-rifle host with ``kids`` = [(suffix, mesh, translation)] baked below it."""
    return W.host_node(name, W.box_rifle(), [W.kid(name, s, m, at) for s, m, at in kids])


def pistol(name: str, kids=()):
    return W.host_node(name, W.slide_pistol(), [W.kid(name, s, m, at) for s, m, at in kids])


def prism(name: str, kids=()):
    return W.host_node(name, W.prism(), [W.kid(name, s, m, at) for s, m, at in kids])


def seat(rec, slot):
    return rec["geometry"]["mounts"][slot]


def entries(rec, key="compatible_hosts"):
    return {e["host"]: e for e in rec["attachment"][key]}
