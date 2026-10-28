"""FAKE_E3 pack: synthetic fixtures for the guard tests of the frame-derived fields (docs/weapon_attach_geometry.md 3.3, errata E3.4; nothing is
from a real pack).

Written into a temp folder by ``w8h_world.write_world``. The parts are built from ``g1_frame_world`` (read-only: its tube, box and magazine
helpers); every expected number in the tests is a LITERAL worked out by hand from the dimensions below, never read from the code under test.
Y-up, metres.

The old frame. A frame-changed host is measured twice: voted (no override) and with ``frame_axis`` set to its bounding-box axis
(``old_frame_overrides``). ``frame_axis`` on the build axis keeps the build frame and runs no ring test (see the g1 frame test
``test_frame_axis_on_the_build_axis_keeps_the_build_frame``), which is the version 5 record a host had before the vote. Everything else about the
two builds is the same, so the default-export records differ in the fields the vote moved and in nothing else.

Hosts (the mesh is the root node; a baked ``Mag`` child hangs below it). The first two are SMG-shaped bodies whose magazine is longer than the body,
so the bounding box says y while the body (minus the magazine) says z, with a 15 mm ring at the +z end only (a closed eight-sided tube,
``g1_frame_world.tube``):

  ALPHA    receiver box x +-0.02, y 0..0.08, z -0.20..0.05; barrel tube z 0.05..0.20 (axis x 0, y 0.04); magazine x +-0.01, y -0.47..0, z -0.05..-0.01.
           Whole mesh y -0.47..0.08 (0.55), z -0.20..0.20 (0.40): the bounding box says y (0.40 < 0.95 * 0.55), the body (z 0.40, y 0.08) says z.
           The origin is 85 % up the y range: a pivot sign, forward -y, up +z. Pre-vote length 0.55 (medium, 2 cells), voted 0.40 (small, 2 cells).
           Voted: forward +z, up +y.
  BRAVO    receiver box x +-0.02, y 0..0.30, z -0.20..0.05; barrel tube z 0.05..0.20 (axis x 0, y 0.15); magazine y -0.30..0, same z. Whole y -0.30..0.30
           (0.60), z 0.40 (0.40 < 0.95 * 0.60); body z 0.40, y 0.30 (0.30 < 0.95 * 0.40): the body says z. The origin is at 50 % of the y range: no
           pivot, so the pre-vote forward sign is a section guess and the record carries ``forward_by_fallback``. The ring at +z confirms the sign.
           Pre-vote length 0.60 (medium, 2 cells), voted 0.40 (small, 2 cells).
  DELTA    the Uzi-shaped host of AC147 (the dimensions of ``g1_frame_world.UZI``): receiver box x +-0.02, y 0..0.08, z -0.10..0.05; barrel tube
           z 0.05..0.20 (axis x 0, y 0.04); magazine y -0.30..0. Whole y -0.30..0.08 (0.38), z -0.10..0.20 (0.30). Pre-vote length 0.38 (small,
           2 cells), voted 0.30 (small, 1 cell): the length crosses a cell step (0.30 m) and no size-class cut.
  ECHO     like ALPHA with a short body: receiver z -0.10..0.03, barrel tube z 0.03..0.08, magazine y -0.32..0. Whole y -0.32..0.08 (0.40), z 0.18
           (0.18 < 0.95 * 0.40); body z 0.18, y 0.08. Pre-vote length 0.40 (small, 2 cells), voted 0.18 (tiny, 1 cell): the length crosses a cell step
           and the 0.20 m cut to tiny, which steps the weight class down once.
  CHARLIE  the plain rifle of ``g1_frame_world`` (body and bounding box both say z): no frame change.

Size classes, cells and weight are from the shipped rules, written out here as literals: tiny is under 0.20 m, small 0.20 m to under 0.45 m, medium
0.45 m to under 0.90 m; one cell of length per 0.30 m (rounded up); the weight class of an SMG is medium, one step lighter when the size is tiny
and one heavier when it is huge. ALPHA and BRAVO sit so that the class moves and the cell count does not; DELTA so that the cell count moves and
the class does not; ECHO so that both move and the weight class with them.
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

PACK = "FAKE_E3"

ALPHA = "SM_Wep_SMG_Alpha_01"
BRAVO = "SM_Wep_SMG_Bravo_01"
DELTA = "SM_Wep_SMG_Delta_01"
ECHO = "SM_Wep_SMG_Echo_01"
CHARLIE = "SM_Wep_Rifle_Charlie_01"


def alpha_body():
    return G.merge(F.box((-0.02, 0.0, -0.20), (0.02, 0.08, 0.05)), F.tube(2, 0.05, 0.20, (0.0, 0.04)))


def bravo_body():
    return G.merge(F.box((-0.02, 0.0, -0.20), (0.02, 0.30, 0.05)), F.tube(2, 0.05, 0.20, (0.0, 0.15)))


def delta_body():
    return F.uzi_body()


def echo_body():
    return G.merge(F.box((-0.02, 0.0, -0.10), (0.02, 0.08, 0.03)), F.tube(2, 0.03, 0.08, (0.0, 0.04)))


def frame_world() -> dict:
    """Five records: four frame-changed hosts (ALPHA, BRAVO, DELTA, ECHO) and a host with no frame change (CHARLIE)."""
    hosts = {
        ALPHA: F.host_nodes(ALPHA, alpha_body(), "Mag", F.mag(-0.47)),
        BRAVO: F.host_nodes(BRAVO, bravo_body(), "Mag", F.mag(-0.30)),
        DELTA: F.host_nodes(DELTA, delta_body(), "Mag", F.mag(-0.30)),
        ECHO: F.host_nodes(ECHO, echo_body(), "Mag", F.mag(-0.32)),
        CHARLIE: F.host_nodes(CHARLIE, F.rifle_body(), "Mag", F.mag(-0.10, -0.2, -0.16)),
    }
    return {PACK: {"hosts": hosts}}


def pid(name: str) -> str:
    return f"{PACK}/{name}"


def overrides(extra: dict | None = None) -> dict:
    return {"schema": "weapon-overrides/1", "ids": dict(extra or {}), "globs": {}}


def old_frame_overrides() -> dict:
    """``frame_axis`` y on the frame-changed hosts (their bounding-box and build axis), and z on CHARLIE (its own axis): the build frame
    everywhere, as version 5 had it. CHARLIE's entry is a no-op by construction (its body axis is its build axis); it is there so the no-change
    guard compares a build that went through the override path with one that did not."""
    return overrides({pid(ALPHA): {"frame_axis": "y"}, pid(BRAVO): {"frame_axis": "y"},
                      pid(DELTA): {"frame_axis": "y"}, pid(ECHO): {"frame_axis": "y"}, pid(CHARLIE): {"frame_axis": "z"}})
