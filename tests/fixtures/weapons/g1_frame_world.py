"""FAKE_G1 pack: synthetic fixtures for the G1 frame vote tests (docs/weapon_attach_geometry.md 3.3 and 3.11; nothing is from a real pack).

Written into a temp folder by ``w8h_world.write_world``. Every expected number in the tests is a LITERAL worked out by hand from the
dimensions below, never read from the code under test. Y-up, metres.

Why a ring needs a round loft: the bore ring estimator wants six vertices in one 1 mm radial bin, and ``make_glbs.loft`` gives four-vertex
stations. ``tube`` builds an eight-sided annulus instead: an outer ring (r_out 12 mm) and an inner ring (r_in 7.5 mm, the middle of the
7 mm bin, so float32 storage cannot move it across a bin edge). The end face carries both rings, the inner one at diameter 0.015.
Two stations of a tube are never closer than the 10 mm end slab, so only the face at the extreme enters it.

Hosts (the mesh is the root node; a baked child hangs below it and is named with a ``child_tokens`` word, here Mag or Silencer):

  UZI       receiver box x +-0.02, y 0..0.08, z -0.10..0.05; barrel tube along z, axis (x 0, y 0.04), z 0.05..0.20 (ring face at z 0.20).
            A magazine child x +-0.01, y -0.30..0, z -0.05..-0.01 hangs under the receiver. Whole mesh: y -0.30..0.08 (0.38), z -0.10..0.20
            (0.30): the bounding box says y (0.30 < 0.95 * 0.38). Body (minus the Mag child): z 0.30, y 0.08, x 0.04: the body says z.
            The z ends: +z carries the 15 mm ring, -z is the 4-vertex box face (no ring).
            Build frame: forward -y (the origin is 79 % up the y range, so away from it), up +z. Voted frame: forward +z, up +y.
  BOTH      the Uzi plus a second tube at the stock end, z -0.20..-0.10, ring face at z -0.20, and a magazine y -0.45..0. Whole mesh y 0.53,
            z 0.40 (0.40 < 0.95 * 0.53): bounding box y; body z with a 15 mm ring at BOTH ends: a frame conflict.
  RIFLE     receiver box x +-0.02, y 0..0.10, z -0.25..0.05, barrel tube z 0.05..0.60 (ring face at 0.60), a short Mag child y -0.10..0:
            body and bounding box both say z, forward +z (the origin is 29 % up the z range).
  REVERSE   a body long on y (box x +-0.02, y 0..0.30, z +-0.05, and a tube along y, y 0.30..0.45, ring face at y 0.45) and a Silencer child
            along z (x +-0.01, y 0.19..0.21, z 0..0.60), so the bounding box says z (0.65 against 0.45) and the body says y. The classifier
            guesses the kind of its id from the long axis: z, so ranged.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


W = _load("w8h_world")
A, G = W.A, W.G

PACK = "FAKE_G1"

UZI = "SM_Wep_SMG_Uzi_01"
BOTH = "SM_Wep_SMG_Both_01"
RIFLE = "SM_Wep_Rifle_Plain_01"
UZI_PART = "SM_Wep_Zulu_Silencer_Uzi_01"  # the Uzi mesh on a record whose role is part (a silencer)
UZI_GUESSED = "SM_Wep_Zulu_Gizmo_01"  # the Uzi mesh on a record whose rules leave the kind null: guessed
REVERSE = "SM_Wep_Zulu_Gizmo_02"  # guessed too, and its bounding box says z where its body says y

R_OUT, R_IN = 0.012, 0.0075  # the annulus of a barrel end: 24 mm outside, 15 mm bore ring
RING_SIDES = 8


def tube(axis: int, lo: float, hi: float, centre: tuple[float, float], r_out: float = R_OUT, r_in: float = R_IN, sides: int = RING_SIDES):
    """A closed eight-sided tube along ``axis`` from ``lo`` to ``hi``; ``centre`` is its centre over the two other axes (in x, y, z order).
    Both end faces are annuli, so each end carries a ring of ``sides`` vertices at radius ``r_in`` and one at ``r_out``."""
    lat = [i for i in range(3) if i != axis]
    verts, rings = [], {}
    for name, radius, pos in (("o0", r_out, lo), ("o1", r_out, hi), ("i0", r_in, lo), ("i1", r_in, hi)):
        ids = []
        for k in range(sides):
            ang = 2.0 * math.pi * k / sides
            p = [0.0, 0.0, 0.0]
            p[axis], p[lat[0]], p[lat[1]] = pos, centre[0] + radius * math.cos(ang), centre[1] + radius * math.sin(ang)
            ids.append(len(verts))
            verts.append(p)
        rings[name] = ids
    tris = []

    def band(a, b):
        for k in range(sides):
            j = (k + 1) % sides
            tris.extend([[a[k], a[j], b[j]], [a[k], b[j], b[k]]])

    band(rings["o0"], rings["o1"])  # outer wall
    band(rings["o1"], rings["i1"])  # the front annulus
    band(rings["i1"], rings["i0"])  # the bore wall
    band(rings["i0"], rings["o0"])  # the back annulus
    return np.array(verts, dtype=np.float64), np.array(tris, dtype=np.int64)


def box(lo, hi):
    return G.box(lo, hi)


def uzi_body():
    return G.merge(box((-0.02, 0.0, -0.10), (0.02, 0.08, 0.05)), tube(2, 0.05, 0.20, (0.0, 0.04)))


def both_body():
    return G.merge(uzi_body(), tube(2, -0.20, -0.10, (0.0, 0.04)))


def rifle_body():
    return G.merge(box((-0.02, 0.0, -0.25), (0.02, 0.10, 0.05)), tube(2, 0.05, 0.60, (0.0, 0.05)))


def reverse_body():
    return G.merge(box((-0.02, 0.0, -0.05), (0.02, 0.30, 0.05)), tube(1, 0.30, 0.45, (0.0, 0.0)))


def mag(lo_y: float, z0: float = -0.05, z1: float = -0.01):
    return box((-0.01, lo_y, z0), (0.01, 0.0, z1))


def silencer_along_z():
    return box((-0.01, 0.19, 0.0), (0.01, 0.21, 0.60))


def host_nodes(host: str, body, kid_name: str, kid_mesh) -> list[dict]:
    return W.host_node(host, body, [W.kid(host, kid_name, kid_mesh, (0.0, 0.0, 0.0))])


def frame_world() -> dict:
    """Six records: the Uzi, the both-rings host, a normal rifle, the Uzi mesh as a part, the Uzi mesh with a guessed kind, and the reverse host."""
    hosts = {
        UZI: host_nodes(UZI, uzi_body(), "Mag", mag(-0.30)),
        BOTH: host_nodes(BOTH, both_body(), "Mag", mag(-0.45, -0.05, -0.01)),
        RIFLE: host_nodes(RIFLE, rifle_body(), "Mag", mag(-0.10, -0.2, -0.16)),
        UZI_PART: host_nodes(UZI_PART, uzi_body(), "Mag", mag(-0.30)),
        UZI_GUESSED: host_nodes(UZI_GUESSED, uzi_body(), "Mag", mag(-0.30)),
        REVERSE: host_nodes(REVERSE, reverse_body(), "Silencer", silencer_along_z()),
    }
    return {PACK: {"hosts": hosts}}


def pid(name: str) -> str:
    return f"{PACK}/{name}"


def overrides(extra: dict | None = None) -> dict:
    """The REVERSE record has no archetype, so no hold class: an id override gives it one, which is what makes it an eligible host."""
    ids = {pid(REVERSE): {"set": {"hold_class": "long_gun"}}}
    ids.update(extra or {})
    return {"schema": "weapon-overrides/1", "ids": ids, "globs": {}}
