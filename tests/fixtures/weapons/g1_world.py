"""FAKE_G1 pack world: the synthetic hosts and parts of the G1 geometry fit gate (docs/weapon_attach_geometry.md 3.2 to 3.8; slice S7).

Written into a temp folder by ``w8h_world.write_world`` (``world()`` is the ``{pack: {"hosts", "parts"}}`` spec it takes). S8 (verdicts in compat)
and S9 (calibration) reuse it, so every host says what it is for. Nothing is from a real pack: the meshes are boxes, lofts, tubes and a rail
generated from the literals below, and every expected number in a test is a LITERAL worked out by hand from them, never read from the code under
test. Y-up, metres, +z forward (the host record frame is forward +z, up +y, side +x), except where a host says it is a frame case.

The frame hosts come from ``g1_frame_world`` (S1) and are kept as they are there: ``UZI`` (the body axis is z, the bounding box says y: the
voted frame, forward +z) and ``BOTH`` (a 15 mm bore ring at both ends: a frame conflict). ``RIFLE_PLAIN`` is S1's plain rifle (no vote).

Hosts of the seat tests (S7)
----------------------------
  CARBINE   a toothed carbine: body x +-0.02, y 0..0.10, z -0.12..0.10, a rail of 8 teeth on its top (pitch 0.0235, crest 0.010, 4 mm tall on a
            floor 1 mm above the body top: crests at y 0.105, run z -0.088..0.100, 0.188 long, 17 mm wide), a barrel tube z 0.10..0.20 (ring face
            at 0.20, bore ring 15 mm, axis y 0.05) and a baked magazine (Mag) under the receiver. The sight probe seats a front sight in the last
            10 mm of the receiver: that is INSIDE the run, so the sight clip (3.4 step 4) is what keeps the optic span off it. The run is shorter
            than the 0.20 default seat length, so the seat is centred on the run and the span is the whole run: without the clip the front sight
            lies inside the span (gate 6(c) of A 4.6 fails), with it the span ends 10 mm behind the sight.
  LOWRAIL   the carbine turned upside down about its body middle (y -> 0.10 - y, winding kept outward): the same 8-tooth rail now hangs from the
            underside (crests at y -0.005, run z -0.088..0.100), the top is smooth, the barrel tube is unchanged (axis y 0.05). The underbarrel gets
            a ``rail_teeth`` seat (up -u) and the optic a ``rail_flat`` one; no magazine child.
  FLATTOP   a plain flat-top receiver: body x +-0.02, y 0..0.10, z -0.20..0.20 (a smooth top 0.40 long at y 0.10, no handguard and no teeth) and
            a barrel tube z 0.20..0.40 (ring face at 0.40, bore ring 15 mm, axis y 0.05). The optic gets a ``rail_flat`` seat on the whole top
            (the run starts where the detector zone does, 15 % along the 0.60 m host: z -0.11; the seat is centred on its rearmost 0.20 m, at
            z -0.01, and its span, the whole run, ends 10 mm behind the front sight).
  FLAT      the W8h box rifle (receiver top y 0.10 flat from z -0.2525 to 0.0475, a lower handguard, a thin barrel): no teeth, a flat top far over
            60 mm, so the optic gets a ``rail_flat`` seat; the underbarrel has no bottom teeth and gets none.
  SCOPED    the box rifle with a baked scope child (Scope) on its receiver: an authored optic seat, untoothed: ``seat_ref``, the flat run under
            the contact is the reference.
  STEPPED   a staircase top (tread 40 mm, riser 10 mm, no flat 60 mm run under the contact) with a baked scope child on one tread: ``seat_ref``
            by the child's own foot length (a stepped seat).
  PRESET    a preset: the box rifle with a scope part and a silencer part FUSED into the mesh (the same vertices as the pack's ``SCOPE`` and
            ``SILENCER`` parts, moved by PRESET_SCOPE_AT and PRESET_SILENCER_AT) and a baked magazine (Mag). The locator finds both parts; the optic
            and muzzle slots are filled (Q-G11), the magazine stays open (``attach_filled_open``).
  PRESET_MAG  a preset with a magazine FUSED into the mesh (MAG_RIFLE moved by PRESET_MAG_AT under the receiver, no baked Mag child): the locator
            finds it, the magazine has a located well reference (``source`` "located", S7 fold-in 4) and no seat.
  UZI, BOTH, RIFLE_PLAIN   see ``g1_frame_world``.
  ROCKET, SHOTGUN, NAILGUN, MINIGUN   a launcher with a baked optic, a shotgun, a tool and a minigun on the box rifle mesh: the host classes
            (A6) refuse their slots; S7 only needs them to build, S8 needs them for the veto.

Parts (the pack's separate attachments)
---------------------------------------
  SCOPE, SILENCER           the W8a optic and suppressor meshes (also the fused parts of PRESET).
  MAG_RIFLE / MAG_PISTOL    two magazine families (``Zulu`` and ``Alfa``) of one size; MAG_DRUM a drum (a big prism).
  RING_DEVICE / PLAIN_DEVICE   two muzzle devices: an 8-sided annulus with a 15 mm inner ring on its mating face, and a solid loft with none.
  OTHER pack: TWIN_SCOPE    the scope mesh again, in another pack (a cross-pack twin of the baked scope children).
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


FW = _load("g1_frame_world")
RM = _load("g1_rail_meshes")
W = FW.W
A, G = W.A, W.G

PACK = FW.PACK  # "FAKE_G1"
OTHER = "FAKE_G1_OTHER"

UZI, BOTH, RIFLE_PLAIN = FW.UZI, FW.BOTH, FW.RIFLE
CARBINE = "SM_Wep_Rifle_Notched_01"
FLAT = "SM_Wep_Rifle_Flat_01"
SCOPED = "SM_Wep_Rifle_Scoped_01"
STEPPED = "SM_Wep_Rifle_Stepped_01"
PRESET = "SM_Wep_Preset_Rifle_01"
FLATTOP = "SM_Wep_Rifle_FlatTop_01"
LOWRAIL = "SM_Wep_Rifle_Lowrail_01"
PRESET_MAG = "SM_Wep_Preset_Carbine_01"
ROCKET, SHOTGUN, NAILGUN, MINIGUN = (
    "SM_Wep_Zulu_Rocket_Launcher_01", "SM_Wep_Zulu_Shotgun_01", "SM_Wep_Zulu_Nailgun_01", "SM_Wep_Zulu_Minigun_01")
SCOPE, SILENCER = "SM_Wep_Zulu_Scope_01", "SM_Wep_Zulu_Silencer_01"
MAG_RIFLE, MAG_PISTOL, MAG_DRUM = "SM_Wep_Zulu_Mag_Rifle_01", "SM_Wep_Alfa_Mag_Pistol_01", "SM_Wep_Zulu_Mag_Drum_01"
RING_DEVICE, PLAIN_DEVICE = "SM_Wep_Zulu_Silencer_Ring_01", "SM_Wep_Zulu_Silencer_Plain_01"
TWIN_SCOPE = "SM_Wep_Zulu_Scope_01"  # in OTHER

# -- the toothed carbine ----------------------------------------------------------------------------------------
TOOTH_PITCH, TOOTH_N, TOOTH_START = 0.0235, 8, -0.088  # 8 teeth: the run is z -0.088 .. 0.100 (0.188 long)
RAIL_TOP_U = 0.105  # crest height


def fsu_to_xyz(mesh):
    """A mesh given in the (f, s, u) frame, in asset coordinates (x = s, y = u, z = f): a cyclic permutation, so the winding stays outward."""
    v, t = mesh
    return v[:, [1, 2, 0]].copy(), t.copy()


def carbine_body():
    body = G.box((-0.02, 0.0, -0.12), (0.02, 0.10, 0.10))
    profile = RM.tooth_profile(TOOTH_START, TOOTH_N, TOOTH_PITCH, 0.010, 0.101, 0.004)
    rail = fsu_to_xyz(RM.prism(profile, -0.0085, 0.0085, 0.10))
    return G.merge(body, rail, FW.tube(2, 0.10, 0.20, (0.0, 0.05)))


def lowrail_body():
    """The carbine's body and rail turned over about y 0.05 (the winding is reversed so the faces stay outward); the barrel tube stays."""
    body = G.merge(G.box((-0.02, 0.0, -0.12), (0.02, 0.10, 0.10)),
                   fsu_to_xyz(RM.prism(RM.tooth_profile(TOOTH_START, TOOTH_N, TOOTH_PITCH, 0.010, 0.101, 0.004), -0.0085, 0.0085, 0.10)))
    v, t = body
    v = v.copy()
    v[:, 1] = 0.10 - v[:, 1]
    return G.merge((v, t[:, [0, 2, 1]]), FW.tube(2, 0.10, 0.20, (0.0, 0.05)))


def carbine_mag():
    return G.box((-0.01, -0.20, -0.06), (0.01, 0.0, -0.03))


# -- the box-rifle family ------------------------------------------------------------------------------------------
SCOPE_AT = (0.0, 0.10, -0.10)  # a scope child's origin: its foot (y 0..0.01) sits on the receiver top, 0.10 behind the origin


def scope_kid(host: str, at=SCOPE_AT):
    return W.kid(host, "Scope", A.optic(), at)


def stepped_body():
    """A box rifle whose top is a staircase: the f (z) profile of ``staircase_host`` in asset coordinates, 1.0 long."""
    return fsu_to_xyz(RM.staircase_host(f_plateau=0.42, plateau_len=0.080, length=1.0))


# -- the preset ----------------------------------------------------------------------------------------------------
PRESET_SCOPE_AT = (0.0, 0.10, -0.05)  # the pack's scope part, moved here, is fused into the preset mesh
PRESET_SILENCER_AT = (0.0, 0.046, 0.75)  # the silencer part, centred on the barrel axis, behind which the barrel ends at z 0.65
PRESET_MAG_AT = (0.0, 0.0, -0.10)  # the magazine part (y -0.12..0, z +-0.02) moved under the receiver: it hangs from the receiver bottom at y 0


def preset_body():
    base = W.box_rifle()
    scope, silencer = A.optic(), A.suppressor()
    return G.merge(base, (scope[0] + np.array(PRESET_SCOPE_AT), scope[1]), (silencer[0] + np.array(PRESET_SILENCER_AT), silencer[1]))


def preset_mag_body():
    mag = A.mag_box(0.01, 0.12, 0.02)
    return G.merge(W.box_rifle(), (mag[0] + np.array(PRESET_MAG_AT), mag[1]))


def flattop_body():
    return G.merge(G.box((-0.02, 0.0, -0.20), (0.02, 0.10, 0.20)), FW.tube(2, 0.20, 0.40, (0.0, 0.05)))


# -- parts -----------------------------------------------------------------------------------------------------------
def ring_device():
    """An annulus along z: outer radius 0.0125, inner 0.0075, from z -0.1 to 0.1 (the mating face is the one at -0.1)."""
    return FW.tube(2, -0.1, 0.1, (0.0, 0.0), r_out=0.0125, r_in=0.0075)


def plain_device():
    return G.loft(2, [(-0.1, 0.0125, 0.0125), (0.1, 0.0125, 0.0125)])


def world() -> dict:
    """The FAKE_G1 pack and its cross-pack twin pack. See the module docstring for every host."""
    hosts = {
        UZI: FW.host_nodes(UZI, FW.uzi_body(), "Mag", FW.mag(-0.30)),
        BOTH: FW.host_nodes(BOTH, FW.both_body(), "Mag", FW.mag(-0.45, -0.05, -0.01)),
        RIFLE_PLAIN: FW.host_nodes(RIFLE_PLAIN, FW.rifle_body(), "Mag", FW.mag(-0.10, -0.2, -0.16)),
        CARBINE: W.host_node(CARBINE, carbine_body(), [W.kid(CARBINE, "Mag", carbine_mag(), (0.0, 0.0, 0.0))]),
        FLAT: W.host_node(FLAT, W.box_rifle()),
        FLATTOP: W.host_node(FLATTOP, flattop_body()),
        LOWRAIL: W.host_node(LOWRAIL, lowrail_body()),
        SCOPED: W.host_node(SCOPED, W.box_rifle(), [scope_kid(SCOPED)]),
        STEPPED: W.host_node(STEPPED, stepped_body(), [scope_kid(STEPPED, (0.0, -0.05, 0.10))]),
        PRESET: W.host_node(PRESET, preset_body(), [W.kid(PRESET, "Mag", A.mag_box(0.01, 0.12, 0.02), (0.0, 0.0, -0.1))]),
        PRESET_MAG: W.host_node(PRESET_MAG, preset_mag_body()),
        ROCKET: W.host_node(ROCKET, W.box_rifle(), [scope_kid(ROCKET)]),
        SHOTGUN: W.host_node(SHOTGUN, W.box_rifle()),
        NAILGUN: W.host_node(NAILGUN, W.box_rifle()),
        MINIGUN: W.host_node(MINIGUN, W.box_rifle()),
    }
    parts = {
        SCOPE: A.optic, SILENCER: A.suppressor,
        MAG_RIFLE: lambda: A.mag_box(0.01, 0.12, 0.02), MAG_PISTOL: lambda: A.mag_box(0.01, 0.08, 0.02),
        MAG_DRUM: lambda: A.mag_box(0.06, 0.15, 0.065),
        RING_DEVICE: ring_device, PLAIN_DEVICE: plain_device,
    }
    return {PACK: {"hosts": hosts, "parts": parts}, OTHER: {"parts": {TWIN_SCOPE: A.optic}}}


def pid(name: str, pack: str = PACK) -> str:
    return f"{pack}/{name}"
