"""FAKE_W8N* packs: synthetic fixtures for the W8n tests (docs/weapon_attachments.md 13.7 A6-1 to A6-4; nothing is from a real pack).

Written into a temp folder by ``w8h_world.write_world``. Every expected number in the tests is a LITERAL worked out by hand from the dimensions
below, never read from the code under test. Y-up, metres, +z forward.

``class_world``   one family word (``Zulu``) on every host and part, so the name-overlap slots (optic, magazine, laser_light) list on a firearm host.
                  Hosts are the W8h box rifle (a receiver, a handguard and a thin barrel); only the NAME differs, and the name decides the class.
``mag_world``     a rifle, a pistol and a sniper host, each with one big baked magazine child (the well), and magazines of various shapes.
``muzzle_world``  hosts built from a receiver, a thin barrel (x +-0.006, y 0.040..0.052: axis y 0.046) running to a tip at z 0.65, and bands CENTRED ON
                  THE AXIS (``band``): a shroud or a brake. The probe puts the muzzle mount at (0, 0.046, 0.65) with up +z (the bore); distances
                  below are measured back from the tip. A face at an ODD millimetre sits in the middle of a 2 mm bin, so the bin edge it reads
                  as is certain (a box face on an even millimetre is a coin flip of float noise).
``sight_world``   two hosts with a raised strip on the receiver top (``tooth_host``), for the per-host receiver tolerance.
``cap_world``     the W8m boxes with gaps of 25, 30, 31 and 40 mm and sunk depths of 25 and 40 mm, for the settle cap.
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
M = _load("w8m_world")
A, G = W.A, W.G

PACK = "FAKE_W8N"
OTHER = "FAKE_W8N_OTHER"  # another pack, so another setting: a part from it is no candidate unless an override adds it


def pid(name: str, pack: str = PACK) -> str:
    return f"{pack}/{name}"


# -- A6-1: host classes --------------------------------------------------------------------------------------------------------

NAILGUN, PISTOL, ROCKET = "SM_Wep_Zulu_Nailgun_01", "SM_Wep_Zulu_Pistol_01", "SM_Wep_Zulu_Rocket_Launcher_01"
FLAME, STUN, PROP, RIFLE = "SM_Wep_Zulu_Flamethrower_01", "SM_Wep_Zulu_Stungun_01", "SM_Wep_Zulu_Rifle_Prop_01", "SM_Wep_Zulu_Rifle_01"
MINIGUN = "SM_Wep_Zulu_Minigun_01"
CLASS_HOSTS = (NAILGUN, PISTOL, ROCKET, FLAME, STUN, PROP, RIFLE, MINIGUN)
C_SILENCER, C_MAG, C_LASER, C_FOREGRIP, C_SCOPE, C_SIGHT = (
    "SM_Wep_Zulu_Silencer_01", "SM_Wep_Zulu_Mag_01", "SM_Wep_Zulu_Flashlight_01", "SM_Wep_Zulu_Foregrip_01", "SM_Wep_Zulu_Scope_01",
    "SM_Wep_Zulu_IronSight_Front_01")
CLASS_PARTS = (C_SILENCER, C_MAG, C_LASER, C_FOREGRIP, C_SCOPE, C_SIGHT)


def class_world() -> dict:
    """The Nailgun host also bakes a magazine child (``Nailgun_01_Mag``): refused by its class, it is no seat until an id override names it."""
    hosts = {n: W.host_node(n, W.box_rifle()) for n in CLASS_HOSTS}
    hosts[NAILGUN] = W.host_node(NAILGUN, W.box_rifle(), [W.kid(NAILGUN, "Mag", A.mag_box(0.01, 0.12, 0.02), (0.0, 0.0, -0.1))])
    return {PACK: {
        "hosts": hosts,
        "parts": {C_SILENCER: A.suppressor, C_MAG: lambda: A.mag_box(0.01, 0.12, 0.02), C_LASER: lambda: A.flip_y(A.optic()),
                  C_FOREGRIP: M.grip_part, C_SCOPE: A.optic, C_SIGHT: W.sight_part},
    }}


# -- A6-3: magazines -----------------------------------------------------------------------------------------------------------
# Each host seats ONE big baked magazine child (x +-0.07, y -0.20..0, z +-0.075, a 0.15 m well along the host's forward z) at (0, 0, -0.10). A part is a
# box hanging from a foot at y 0: its foot is the top face, so foot_length_m is its extent along z (the forward: the longer horizontal side).
#   MAG_DRUM   x +-0.06, z +-0.065 (0.12 x 0.13 body: the smaller side, 0.12, is over 0.11 m), 0.15 tall; standard name; foot 0.13 -> 0.13 / 0.15 = 0.867
#   MAG_SLIM   x +-0.01, z +-0.065 (0.02 x 0.13): the same foot, not a drum
#   MAG_BOARD  x +-0.01, z +-0.045 (0.02 x 0.09): foot 0.09 / 0.15 = 0.60, under the 0.75 bound
#   MAG_FAIR   x +-0.01, z +-0.060 (0.02 x 0.12): foot 0.12 / 0.15 = 0.80, over it

MAG_RIFLE, MAG_PISTOL, MAG_SNIPER = "SM_Wep_Zulu_Rifle_Well_01", "SM_Wep_Zulu_Pistol_Well_01", "SM_Wep_Zulu_Sniper_Well_01"
MAG_DRUM, MAG_SLIM, MAG_BOARD, MAG_FAIR = "SM_Wep_Zulu_Mag_Big_01", "SM_Wep_Zulu_Mag_Slim_01", "SM_Wep_Zulu_Mag_Board_01", "SM_Wep_Zulu_Mag_Fair_01"


def _well_host(name: str):
    return W.host_node(name, W.box_rifle(), [W.kid(name, "Mag", A.mag_box(0.07, 0.20, 0.075), (0.0, 0.0, -0.10))])


def mag_world() -> dict:
    return {PACK: {
        "hosts": {n: _well_host(n) for n in (MAG_RIFLE, MAG_PISTOL, MAG_SNIPER)},
        "parts": {MAG_DRUM: lambda: A.mag_box(0.06, 0.15, 0.065), MAG_SLIM: lambda: A.mag_box(0.01, 0.15, 0.065),
                  MAG_BOARD: lambda: A.mag_box(0.01, 0.15, 0.045), MAG_FAIR: lambda: A.mag_box(0.01, 0.15, 0.060)},
    }}


# -- A6-4: the settle cap ------------------------------------------------------------------------------------------------------
# w8m_world's boxes: the body top is y 0.10, the scope part's foot centre sits on its host's baked scope child, whose foot is at the given height, so
# the gap is that height minus 0.10. An underbarrel child hangs from a foot at the given height under the body bottom (y 0).

CAP_GAPS = {"Gap25": 0.125, "Gap30": 0.130, "Gap31": 0.131, "Gap40": 0.140, "Sunk25": 0.075, "Sunk40": 0.060}


def cap_world() -> dict:
    hosts = {case: M.host(case, [M.scope_kid(bottom)]) for case, bottom in CAP_GAPS.items()}
    hosts["TwinGap40"] = M.host("TwinGap40", [M.scope_kid(0.14)])  # a 40 mm gap, and the part below twins its child
    hosts["UbGap25"] = M.host("UbGap25", [M.grip_kid(-0.025)])
    hosts["UbGap40"] = M.host("UbGap40", [M.grip_kid(-0.040)])
    hosts["UbSunk40"] = M.host("UbSunk40", [M.grip_kid(0.040)])
    return {M.PACK: {"hosts": {M.host_id(c): n for c, n in hosts.items()},
                     "parts": {M.SCOPE_PART: M.scope_part, M.GRIP_PART: M.grip_part, M.TWIN_PART: M.twin_part}}}


# -- A6-2: the silencer seat ---------------------------------------------------------------------------------------------------
# Hosts: a receiver (x +-0.02, y 0..0.10, z -0.25..0.05) and a thin barrel (x +-0.006, y 0.040..0.052, z 0.05..0.65: axis y 0.046, tip z 0.65) plus
# bands centred on the axis. Distances are measured back from the tip. The silencer parts are x +-0.015, y +-0.015 boxes from z 0 (the mating end) to
# z L, L = 0.2 (SILENCER) or 0.12 (SILENCER_SHORT); the footprint height_m is L.
#   Bare       the bare barrel: no device, no shroud, no key
#   Shroud     a shroud band(0.05..0.589, 0.02): its front face is 61 mm behind the tip. stub 0.061 (the 2 mm bin edge reads 0.062).
#              d = min(0.062, max(0.4 * L, 0 + 0.005), 0.75 * L): L 0.2 -> 0.062; L 0.12 -> min(0.062, 0.048, 0.09) = 0.048
#   Brake      a shroud band(0.05..0.549) and a brake band(0.595..0.635, 0.015): the brake's rear face is 55 mm behind the tip (device within the 80 mm
#              reach), the shroud's front face 101 mm. stub 0.102 (bin edge), device rear 0.055.
#              d = min(0.102, max(0.4 * L, 0.055 + 0.005), 0.75 * L): L 0.2 -> min(0.102, 0.08, 0.15) = 0.080; L 0.12 -> max(0.048, 0.060) = 0.060
#   FarBrake   no shroud, a brake band(0.505..0.529, 0.015): front face 121 mm, rear face 145 mm behind the tip, beyond the 80 mm reach: not a brake of
#              the tip. dev_rear_near 0, so d = min(stub, 0.4 * L, 0.75 * L): L 0.2 -> 0.080, L 0.12 -> 0.048. With the reach raised to 0.2 the device
#              counts (rear face 0.145 + 0.005) and L 0.2 gives min(stub, 0.150, 0.15) = 0.150
#   Baked      a baked silencer child (0.12 long) at the tip. The muzzle seat is ALWAYS the probe's (a baked child only fills occupied_by), so the
#              mount is a probe seat with a non-empty occupied_by: the part replaces the child, and no key (SILENCER is a same_pack_fit here, SHORT a twin)
#   Twin       a baked silencer child that is an exact twin of SILENCER (0.2 long): the tier is twin; no key

SH_BARE, SH_SHROUD, SH_BRAKE = "SM_Wep_Rifle_Bare_01", "SM_Wep_Rifle_Shroud_01", "SM_Wep_Rifle_Brake_01"
SH_FAR, SH_BAKED, SH_TWIN = "SM_Wep_Rifle_FarBrake_01", "SM_Wep_Rifle_Baked_01", "SM_Wep_Rifle_Twin_01"
SILENCER, SILENCER_SHORT, SILENCER_X = "SM_Wep_Silencer_01", "SM_Wep_Silencer_Short_01", "SM_Wep_Zulu_Silencer_Ext_01"
AXIS = 0.046


def silencer_box(length: float):
    return G.box((-0.015, -0.015, 0.0), (0.015, 0.015, length))


def band(z0: float, z1: float, half: float):
    return G.box((-half, AXIS - half, z0), (half, AXIS + half, z1))


def barrel_host(*extra):
    return G.merge(G.box((-0.02, 0.0, -0.25), (0.02, 0.10, 0.05)), G.box((-0.006, 0.040, 0.05), (0.006, 0.052, 0.65)), *extra)


def muzzle_hosts() -> dict:
    out = {
        SH_BARE: barrel_host(),
        SH_SHROUD: barrel_host(band(0.05, 0.589, 0.02)),
        SH_BRAKE: barrel_host(band(0.05, 0.549, 0.02), band(0.595, 0.635, 0.015)),
        SH_FAR: barrel_host(band(0.505, 0.529, 0.015)),
    }
    nodes = {n: W.host_node(n, m) for n, m in out.items()}
    # the shroud shape under the baked silencer (the child is not part of the probed host: it is dropped from the probe mesh)
    kid_at = (0.0, AXIS, 0.65)
    nodes[SH_BAKED] = W.host_node(SH_BAKED, barrel_host(band(0.05, 0.589, 0.02)), [W.kid(SH_BAKED, "Silencer", silencer_box(0.12), kid_at)])
    nodes[SH_TWIN] = W.host_node(SH_TWIN, barrel_host(band(0.05, 0.589, 0.02)), [W.kid(SH_TWIN, "Silencer", silencer_box(0.2), kid_at)])
    return nodes


def muzzle_world() -> dict:
    return {PACK: {"hosts": muzzle_hosts(), "parts": {SILENCER: lambda: silencer_box(0.2), SILENCER_SHORT: lambda: silencer_box(0.12)}},
            OTHER: {"parts": {SILENCER_X: lambda: silencer_box(0.2)}}}


def muzzle_overrides() -> dict:
    """SILENCER_X (another pack) is listed on the Shroud host by an override (tier ``override``)."""
    return W.overrides_doc(ids={pid(SILENCER_X, OTHER): {"compatible": {"add": [pid(SH_SHROUD)]}}})


# -- A6-4 d2: the per-host receiver tolerance ----------------------------------------------------------------------------------
# A deck x +-0.02, y 0..0.10, z -0.30..0.10; a strip of crests on it x +-0.02, y 0.10..0.111, z -0.2575..-0.2025 (11 mm over the deck); a lower
# handguard x +-0.02, y 0..0.075, z 0.10..0.40; the thin barrel to z 0.65. At 6 mm the receiver run is the bins within 6 mm of the highest point
# (0.111): the strip alone, so the rear seat sits at the strip's rear end (z -0.2575) plus 10 mm = about -0.2475 (a 5 mm bin: within 0.005).
# At 14 mm (0.097 and up) the whole deck is the run: its rear end -0.30 plus 10 mm = -0.29.

TOOTH_HOST, TOOTH_TWIN = "SM_Wep_Rifle_Tooth_01", "SM_Wep_Rifle_Tooth_02"


def tooth_host():
    return G.merge(G.box((-0.02, 0.0, -0.30), (0.02, 0.10, 0.10)), G.box((-0.02, 0.10, -0.2575), (0.02, 0.111, -0.2025)),
                   G.box((-0.02, 0.0, 0.10), (0.02, 0.075, 0.40)), G.box((-0.006, 0.04, 0.40), (0.006, 0.052, 0.65)))


def sight_world() -> dict:
    return {PACK: {"hosts": {n: W.host_node(n, tooth_host()) for n in (TOOTH_HOST, TOOTH_TWIN)}, "parts": {C_SIGHT: W.sight_part}}}


# -- A6: presets refuse the slots their built-in parts fill -------------------------------------------------------------------
# Tom, 2026-10-24: "presets only refuse the slots their built-in parts already fill; other slots stay open." Synthetic hosts, one family word
# (Zulu), the W8h box rifle. A Preset_* host bakes children by name (the child names are the shipped child_tokens: Mag, Silencer, Foregrip, Scope).

PRE_FULL, PRE_MAG, PRE_BARE = "SM_Wep_Zulu_Preset_Rifle_01", "SM_Wep_Zulu_Preset_Rifle_02", "SM_Wep_Zulu_Preset_Rifle_03"
PRE_CONTROL = "SM_Wep_Zulu_Rifle_Full_01"  # the same four children on a host that is not a preset
PRESET_HOSTS = (PRE_FULL, PRE_MAG, PRE_BARE, PRE_CONTROL)
PRESET_PARTS = (C_SILENCER, C_MAG, C_LASER, C_FOREGRIP, C_SCOPE)


def _pre_kids(host: str, which=("Mag", "Silencer", "Foregrip", "Scope")):
    meshes = {"Mag": (A.mag_box(0.01, 0.12, 0.02), (0.0, 0.0, -0.1)), "Silencer": (A.suppressor(), (0.0, 0.046, 0.65)),
              "Foregrip": (M.grip_part(), (0.0, 0.0, 0.2)), "Scope": (A.optic(), (0.0, 0.10, 0.1))}
    return [W.kid(host, name, *meshes[name]) for name in which]


def preset_world() -> dict:
    """Four hosts: a preset with a magazine, a suppressor, a foregrip and a scope baked on; a preset with only a magazine; a bare preset; and a
    control that bakes the first preset's four children but is not a preset."""
    hosts = {PRE_FULL: W.host_node(PRE_FULL, W.box_rifle(), _pre_kids(PRE_FULL)),
             PRE_MAG: W.host_node(PRE_MAG, W.box_rifle(), _pre_kids(PRE_MAG, ("Mag",))),
             PRE_BARE: W.host_node(PRE_BARE, W.box_rifle()),
             PRE_CONTROL: W.host_node(PRE_CONTROL, W.box_rifle(), _pre_kids(PRE_CONTROL))}
    return {PACK: {"hosts": hosts,
                   "parts": {C_SILENCER: A.suppressor, C_MAG: lambda: A.mag_box(0.01, 0.12, 0.02), C_LASER: lambda: A.flip_y(A.optic()),
                             C_FOREGRIP: M.grip_part, C_SCOPE: A.optic}}}
