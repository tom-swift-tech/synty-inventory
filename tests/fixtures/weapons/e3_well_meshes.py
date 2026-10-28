"""FAKE_E3W pack: synthetic hosts and magazine parts for the E3.6 well-plane tests (docs/weapon_attach_geometry.md 3.7 step 1; errata E3.6).

Written into a temp folder by ``w8h_world.write_world`` (``world()`` is the ``{pack: {"hosts", "parts"}}`` spec it takes). Nothing is from a real pack:
every mesh is a box, a loft or a tube generated from the literals below, and every expected number in a test is a LITERAL worked out by hand from them,
never read from the code under test. Y-up, metres, +z forward (the host frame is forward +z, up +y, side +x): the (f, s, u) frame of the detectors reads
f = z, s = x, u = y.

The receiver of every host is the same block (x +-0.02, y 0..0.10, z -0.12..0.10, so its bottom, the receiver bottom, is u = 0) with a barrel tube
z 0.10..0.20 on its front. A magazine child is a box that hangs from a flat top, moved by its node translation (``A.mag_box`` / ``mag_at``):

  TWO_SEAT   a drum and a stick magazine that OVERLAP in (f, s).
             Mag_Drum   x +-0.04, y -0.10..0.02, z -0.08..0.02 (0.10 along f, 0.08 across): its top-face centre is (f, s) = (-0.03, 0), top 2 cm
                        inside the receiver. The larger by volume (9.6e-4 against 2.0e-4 m3), so it is the mount's own seat (``child_node``).
             Mag_Stick  x +-0.012, y -0.155..0.01, z -0.045..0.005 (0.05 along f, 0.024 across): its top-face centre is (-0.02, 0), top 1 cm inside the
                        receiver. It stands lower than the drum (-0.155 against -0.10) and covers the drum's centre line (f -0.03 lies in
                        -0.045..0.005, s 0 in +-0.012).
             Today the host minus the drum alone still holds the stick: the lowest crossing on the drum's centre line is the stick's bottom,
             u = -0.155, the plane (-0.157) lies under the whole drum (bottom -0.10) and meets no edge: no reference. With the stick removed too
             the lowest crossing is the receiver bottom 0, the plane is -0.002 (0.098 over the drum's bottom, 0.022 under its top), and the drum
             section there is 0.10 x 0.08.
  ONE_SEAT   the same receiver with the drum alone: the guard that cannot change (nothing else to remove).
  APART      the same receiver with the drum and a stick that do not overlap in (f, s): the stick is moved 0.07 forward, z 0.025..0.075 (its centre
             line f = 0.05 is 8 cm from the drum's, and the drum's line, f -0.03, is outside its z range), so the drum's line meets only the receiver and
             the reference is the same with or without the stick removed.

Parts (the pack's separate magazines; the A1 twin test is the sorted AABB extents, so a part twins the child it matches):

  TWIN_STICK   the stick again as a part (x +-0.012, y -0.155..0, z +-0.025 about its own origin): a twin of Mag_Stick.
  TWIN_DRUM    the drum again as a part: a twin of Mag_Drum.
  ODD          a 0.030 x 0.140 x 0.020 box, a twin of nothing.
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
W, A, G = F.W, F.A, F.G

PACK = "FAKE_E3W"

TWO_SEAT = "SM_Wep_Rifle_TwoSeat_01"
ONE_SEAT = "SM_Wep_Rifle_OneSeat_01"
APART = "SM_Wep_Rifle_Apart_01"
TWIN_STICK = "SM_Wep_Zulu_Mag_Stick_01"
TWIN_DRUM = "SM_Wep_Zulu_Mag_Drum_01"
ODD = "SM_Wep_Zulu_Mag_Odd_01"

DRUM_AT = (0.0, 0.02, -0.03)  # the drum node's origin: its flat top (y 0 of the mesh) lands at y 0.02, its centre at f -0.03
STICK_AT = (0.0, 0.01, -0.02)  # the stick's: top at y 0.01, centre f -0.02
STICK_APART_AT = (0.0, 0.01, 0.05)


def drum_mag():
    return A.mag_box(0.04, 0.12, 0.05)


def stick_mag():
    return A.mag_box(0.012, 0.165, 0.025)


def receiver():
    """The receiver block and its barrel tube."""
    return G.merge(G.box((-0.02, 0.0, -0.12), (0.02, 0.10, 0.10)), F.tube(2, 0.10, 0.20, (0.0, 0.05)))


def world() -> dict:
    hosts = {
        TWO_SEAT: W.host_node(TWO_SEAT, receiver(), [
            W.kid(TWO_SEAT, "Mag_Drum", drum_mag(), DRUM_AT), W.kid(TWO_SEAT, "Mag_Stick", stick_mag(), STICK_AT)]),
        ONE_SEAT: W.host_node(ONE_SEAT, receiver(), [W.kid(ONE_SEAT, "Mag_Drum", drum_mag(), DRUM_AT)]),
        APART: W.host_node(APART, receiver(), [
            W.kid(APART, "Mag_Drum", drum_mag(), DRUM_AT), W.kid(APART, "Mag_Stick", stick_mag(), STICK_APART_AT)]),
    }
    parts = {TWIN_STICK: stick_mag, TWIN_DRUM: drum_mag, ODD: lambda: A.mag_box(0.015, 0.14, 0.010)}
    return {PACK: {"hosts": hosts, "parts": parts}}


def pid(name: str) -> str:
    return f"{PACK}/{name}"
