"""FAKE_G1 tools world: the oracle of ``attach-calibrate`` and the directory the spot-check, eval and preview tests read (docs/weapon_attach_geometry.md
3.2, 3.10, 3.11, 4.2; slice S9). Nothing is from a real pack: every mesh is a box, a loft or a tube built from the literals below, and every expected
number in a test is a LITERAL worked out by hand from them, never read from the code under test. Y-up, metres, +z forward.

It is ``g1_world.cross_world()`` (the S7/S8 hosts and parts) plus three hosts, so that every row of the 4.2 table has positives:

  SCOPED_RAIL   the toothed carbine (CARBINE of ``g1_world``: 8 teeth, run z -0.088 .. 0.100, 17 mm wide, crests at y 0.105, a front sight the probe
                seats inside the run) with a baked scope child (the W8a optic: foot 0.06 long and 0.02 wide) standing on the rail. It is the toothed
                optic positive (overhang, ratio, zone, depth); the FAKE_G1 and FAKE_G1_OTHER scopes are its twins.
  PRESET_HEX    a preset (``Preset`` token) whose barrel is a HEXAGONAL tube (circumradius 12 mm, a bore ring of 6 vertices at radius 7.5 mm, three of
                them 4 mm behind the end face) with the pack's plain device (a 25 mm square loft) FUSED onto its end. The probe sees the device's
                solid front face (no ring, ``face_extent``), the locator finds the device and the strip removes it, and the host end that is left is
                proved by a face ring (spec 3.6 (ii), errata E1.1): the circ_min positive, a regular hexagon filling 3 sqrt(3) / (2 pi) = 0.8270 of its circle.
  RINGED        a rifle whose barrel is a tube of OD 21 mm with a bore ring (radius 6.5 mm) and a baked ring device on it (the pack's RING_DEVICE: a
                25 mm annulus with a 15 mm inner ring on its mating face): the bore positive with an inner ring; the RING_DEVICE part is its twin.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GW = _load("g1_world")
FW, W, A, G = GW.FW, GW.W, GW.A, GW.G

PACK, OTHER = GW.PACK, GW.OTHER
SCOPED_RAIL = "SM_Wep_Rifle_Notched_Scoped_01"
PRESET_HEX = "SM_Wep_Preset_Carbine_02"
RINGED = "SM_Wep_Rifle_Ringed_01"

LONG_FOOT_LEN_M = 0.196  # the toothed carbine's run is 0.188 long (8 teeth at 23.5 mm pitch): an overhang of 8 mm, 2 mm inside the 10 mm literal
HEX_R_OUT, HEX_R_IN, HEX_STAGGER = 0.012, 0.0075, 0.004
RING_BARREL_R_OUT, RING_BARREL_R_IN = 0.0105, 0.0065
MUZZLE_AT = (0.0, 0.05, 0.30)  # a muzzle device's origin: its mating face (z -0.1 of the mesh) lands on the barrel end at z 0.20
SCOPE_ON_RAIL = (0.0, 0.105, 0.006)  # the long-foot scope child's origin: its foot underside on the crests (y 0.105), centred on the run (z 0.006)


def long_foot_optic(foot_len: float = LONG_FOOT_LEN_M):
    """The W8a optic with a long foot: 0.02 wide, ``foot_len`` long from z - foot_len / 2 to + foot_len / 2, so it stands 8 mm longer than the
    carbine's 0.188 run. The body and flare of the W8a optic sit on the foot unchanged."""
    foot = G.box((-0.01, 0.0, -foot_len / 2), (0.01, 0.01, foot_len / 2))
    body = G.box((-0.015, 0.01, -0.1), (0.015, 0.04, 0.06))
    return G.merge(foot, body)


def short_mag():
    """The carbine's magazine box, 0.14 long instead of 0.20: the host's height (the optic on the rail included) then stays under its 0.32 length, so
    the long axis stays z and the build's frame is the bounding box's (the 0.20 magazine plus the optic made y the longest axis: a frame change)."""
    return G.box((-0.01, -0.14, -0.06), (0.01, 0.0, -0.03))


def hex_barrel(z0: float = 0.10, z1: float = 0.20, centre=(0.0, 0.05)):
    """A hexagonal tube z0..z1 whose bore ring is staggered: of its six vertices at the end face every second one stands 4 mm behind it.

    The probe's face window (1 mm) then holds three ring vertices, too few for a bore (six), so the probe says ``face_extent``; the 10 mm end slab
    of the detector holds all six, so the detector finds the ring (evidence ``face_ring``). Rings are built outer-back, outer-front, inner-back,
    inner-front, six vertices each: the inner-front ring starts at index 18."""
    v, t = FW.tube(2, z0, z1, centre, r_out=HEX_R_OUT, r_in=HEX_R_IN, sides=6)
    v = v.copy()
    for k in (1, 3, 5):
        v[18 + k, 2] -= HEX_STAGGER
    return v, t


def preset_hex_body():
    plain = GW.plain_device()
    return G.merge(G.box((-0.02, 0.0, -0.12), (0.02, 0.10, 0.10)), hex_barrel(), (plain[0] + np.array(MUZZLE_AT), plain[1]))


def ringed_body():
    return G.merge(G.box((-0.02, 0.0, -0.12), (0.02, 0.10, 0.10)),
                   FW.tube(2, 0.10, 0.20, (0.0, 0.05), r_out=RING_BARREL_R_OUT, r_in=RING_BARREL_R_IN))


def tools_world() -> dict:
    """``cross_world()`` plus the three hosts above."""
    both = GW.cross_world()
    hosts = both[PACK]["hosts"]
    hosts[SCOPED_RAIL] = W.host_node(SCOPED_RAIL, GW.carbine_body(), [
        W.kid(SCOPED_RAIL, "Mag", short_mag(), (0.0, 0.0, 0.0)), W.kid(SCOPED_RAIL, "Scope", long_foot_optic(), SCOPE_ON_RAIL)])
    hosts[PRESET_HEX] = W.host_node(PRESET_HEX, preset_hex_body())
    hosts[RINGED] = W.host_node(RINGED, ringed_body(), [W.kid(RINGED, "Silencer", GW.ring_device(), MUZZLE_AT)])
    return both


def tools_rules() -> dict:
    return GW.cross_rules()


def build(tmp: Path):
    """``(catalogs dir, threejs_v2 root, directory, excluded)``: the world written under ``tmp``, its directory built (cold caches) and stored."""
    from synty_inventory.weapons import directory as D
    from synty_inventory.weapons.overrides import empty_overrides

    world = tools_world()
    cat, root = W.write_world(tmp, world)
    directory, excluded, _report = D.build_directory_report(
        cat, overrides=empty_overrides(), pack_settings=W.pack_settings(world), rules=tools_rules(), threejs_v2_dir=root, geometry_cache={})
    D.write_directory(cat, directory, excluded)
    return cat, root, directory, excluded


def pid(name: str, pack: str = PACK) -> str:
    return GW.pid(name, pack)
