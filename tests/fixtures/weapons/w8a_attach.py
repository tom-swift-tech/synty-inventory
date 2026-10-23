"""FAKE_Attach: synthetic attachment fixtures for the W8a tests (docs/weapon_attachments.md section 11).

Not part of make_catalogs.py on purpose: ``wfx.make_catalogs_dir`` copies every committed catalog into every weapon test, so a
sixth pack there would shift the whole W7 suite (literal counts in test_weapons_review.py and expected.json). The pack is
written by ``write_world`` into a temp folder, with its own GLBs, and built with ``PACK_SETTINGS``.

Every mesh is a handful of lofts from make_glbs (Y-up, metres, nothing from a real pack). The expected values below are
LITERALS worked out by hand from the stations, never read from the code under test.

optic (foot at -Y): foot box x -0.005..0.015, y 0..0.01, z 0.02..0.08 (centre (0.005, 0, 0.05), deliberately off the AABB centre
of the whole mesh); body box x +-0.015, y 0.01..0.04, z -0.1..0.06; flare cone z 0.06..0.1 growing to x +-0.03, y 0.02..0.08. The
objective flare faces +z: end sections 9e-4 (rear) against 4.2e-3 (front), ratio 4.7. Footprint: length 0.2, width 0.06, height
0.08, foot 0.06 long and 0.02 wide.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


G = _load("make_glbs")
MC = _load("make_catalogs")
WFX = _load("wfx")

PACK = "FAKE_Attach"
PACK_SETTINGS = {PACK: {"setting": "military", "era": "modern"}}

# the offset foot of OPTIC: centre of the contact patch, and the extents of the patch
FOOT_CENTRE = (0.005, 0.0, 0.05)
FOOT_LENGTH_M, FOOT_WIDTH_M = 0.06, 0.02
OPTIC_SIZE = {"length_m": 0.2, "width_m": 0.06, "height_m": 0.08}
# the suppressor tube: square rings of half-width h, so the four corners lie h * sqrt(2) from the axis
MUZZLE_NARROW_H, MUZZLE_WIDE_H = 0.0092, 0.02
MUZZLE_MATE_D_M = 0.0260  # 2 * 0.0092 * sqrt(2) = 0.02602
MUZZLE_POINT = (0.0, 0.0, -0.1)


# -- meshes ----------------------------------------------------------------------------------------------


def optic(foot_x: float = 0.005, foot_z: float = 0.05):
    """Tube with a flare, foot at -Y, objective bell toward +z."""
    foot = G.box((foot_x - 0.01, 0.0, foot_z - 0.03), (foot_x + 0.01, 0.01, foot_z + 0.03))
    body = G.box((-0.015, 0.01, -0.1), (0.015, 0.04, 0.06))
    flare = G.loft(2, [(0.06, 0.015, 0.015, 0.0, 0.025), (0.1, 0.03, 0.03, 0.0, 0.05)])
    return G.merge(foot, body, flare)


def symmetric_box():
    """A box optic: both ends are identical rings, so the forward sign is a coin flip."""
    return G.merge(G.box((-0.015, 0.0, -0.05), (0.015, 0.03, 0.05)))


def upside_down_optic():
    """Authored upside down: an apex at the bottom, the flat foot (x +-0.015, z +-0.06) at y 0.03."""
    return G.loft(1, [(0.0, 0.0, 0.0, 0.0, 0.0), (0.03, 0.015, 0.06, 0.0, 0.0)])


def footless():
    """Apex at both ends: neither end holds three distinct points."""
    return G.loft(1, [(0.0, 0.0, 0.0), (0.02, 0.02, 0.02), (0.04, 0.0, 0.0)])


def suppressor():
    """Narrow mating end at -z (z -0.1), wide free end at +z (z 0.1)."""
    return G.loft(2, [(-0.1, MUZZLE_NARROW_H, MUZZLE_NARROW_H), (0.1, MUZZLE_WIDE_H, MUZZLE_WIDE_H)])


def flip_y(mesh):
    """Mirror in Y: a foot at the bottom becomes a foot at the top with the body hanging below (underbarrel, magazine)."""
    v, t = mesh
    return v * np.array([1.0, -1.0, 1.0]), t


def flip_z(mesh):
    v, t = mesh
    return v * np.array([1.0, 1.0, -1.0]), t


def yaw(mesh, quarter_turns: int):
    """Rotate about Y by ``quarter_turns`` * 90 degrees: (x, z) -> (z, -x) per turn."""
    v, t = mesh
    for _ in range(quarter_turns % 4):
        v = np.stack([v[:, 2], v[:, 1], -v[:, 0]], axis=1)
    return v, t


def yaw_vec(vec, quarter_turns: int) -> list[float]:
    """The same rotation on a point or direction."""
    x, y, z = vec
    for _ in range(quarter_turns % 4):
        x, z = z, -x
    return [x, y, z]


# -- the catalog -----------------------------------------------------------------------------------------

# asset id -> (mesh key, expected (slot, kind) or None). Every id is a `part` (Mod_/optic/magazine/grip/... part rules).
PARTS = {
    "SM_Wep_Sniper_Scope_01": ("bottom", ("optic", "sniper_scope")),
    "SM_Wep_Rifle_Scope_01": ("bottom", ("optic", "scope")),
    "SM_Wep_CarryHandle_Scope_01": ("bottom", ("optic", "carry_handle_scope")),
    "SM_Wep_RedDot_01": ("bottom", ("optic", "reflex")),
    "SM_Wep_Reflex_01": ("bottom", ("optic", "reflex")),
    "SM_Wep_Holo_01": ("bottom", ("optic", "reflex")),
    "SM_Wep_IronSight_01": ("bottom", ("optic", "iron")),
    "SM_Wep_Iron_Rear_Sight_01": ("bottom", ("optic", "iron")),  # `iron` and `sight` not adjacent: the pair row, not the joined one
    "SM_Wep_Silencer_01": ("muzzle", ("muzzle", "suppressor")),
    "SM_Wep_Pistol_Suppressor_01": ("muzzle", ("muzzle", "suppressor")),
    "SM_Wep_Foregrip_01": ("top", ("underbarrel", "foregrip")),
    "SM_Wep_Vert_Grip_01": ("top", ("underbarrel", "foregrip")),
    "SM_Wep_Mod_Bipod_01": ("top", ("underbarrel", "bipod")),
    "SM_Wep_Mod_Laser_01": ("bottom", ("laser_light", "laser")),
    "SM_Wep_Flashlight_01": ("bottom", ("laser_light", "light")),
    "SM_Wep_DrumMag_01": ("top", ("magazine", "drum")),
    "SM_Wep_Drum_Big_Mag_01": ("top", ("magazine", "drum")),  # `drum` and `mag` not adjacent: the pair row
    "SM_Wep_Rifle_Mag_01": ("top", ("magazine", "standard")),
    "SM_Wep_Pistol_Magazine_01": ("top", ("magazine", "standard")),
    "SM_Wep_Mod_Cell_01": ("top", ("magazine", "cell")),
    "SM_Wep_Mod_Mag_Cell_01": ("top", ("magazine", "cell")),  # `mag` with `cell`: the standard row refuses, the cell row takes it
    # parts that are NOT attachments
    "SM_Wep_Veh_Attach_Laser_01": ("bottom", None),  # would be laser_light/laser, but it is a vehicle accessory (never list)
    "SM_Wep_Mod_Mining_Laser_01": ("bottom", None),  # laser with `mining`
    "SM_Wep_Mod_Mining_Cell_01": ("top", None),
    "SM_Wep_Mod_Rail_01": ("bottom", None),  # no row
    "SM_Wep_Mod_Handle_01": ("bottom", None),  # a handle without a scope
    "SM_Wep_Rifle_Stock_01": ("bottom", None),
    "SM_Wep_Rifle_Bayonet_01": ("bottom", None),
    # for the measurement tests
    "SM_Wep_Symmetric_Scope_01": ("symmetric", ("optic", "scope")),
    "SM_Wep_Upside_Scope_01": ("upside", ("optic", "scope")),
    "SM_Wep_Footless_Scope_01": ("footless", ("optic", "scope")),
}
# eligible hosts (whole, ranged, one_hand / long_gun) and two that are not
HOSTS = {
    "SM_Wep_Rifle_Assault_01": "long_gun", "SM_Wep_Pistol_01": "one_hand",
    "SM_Wep_Grenade_Frag_01": "thrown", "SM_Wep_Sword_Long_01": "melee_one",
}

MESHES = {
    "bottom": optic, "top": lambda: flip_y(optic()), "muzzle": suppressor, "symmetric": symmetric_box,
    "upside": upside_down_optic, "footless": footless,
}


def _catalog_doc() -> dict:
    assets = [MC._asset(PACK, aid) for aid in sorted({**PARTS, **HOSTS})]
    return {
        "pack_id": PACK, "engine": "Unity", "origin": "fixture", "style": "synthetic", "units": "meters",
        "version": MC.S.CATALOG_VERSION, "scanned_at": MC.SCANNED_AT, "grid": dict(MC.S.DEFAULT_GRID),
        "conventions": dict(MC.S.DEFAULT_CONVENTIONS), "asset_count": len(assets), "assets": assets,
    }


def write_world(tmp_path: Path, *, meshes: dict | None = None) -> tuple[Path, Path]:
    """``(catalogs_dir, threejs_v2_root)`` for FAKE_Attach; ``meshes`` overrides ``{asset id: (verts, tris)}``."""
    cat, root = tmp_path / "catalogs", tmp_path / "threejs"
    cat.mkdir(parents=True, exist_ok=True)
    (cat / f"{PACK}.json").write_bytes((json.dumps(_catalog_doc(), indent=2, sort_keys=True) + "\n").encode("utf-8"))
    host_mesh = G.gun()
    for aid in sorted({**PARTS, **HOSTS}):
        mesh = host_mesh if aid in HOSTS else MESHES[PARTS[aid][0]]()
        mesh = (meshes or {}).get(aid, mesh)
        G.write_glb(root / "glb" / PACK / f"{aid}.glb", [{"name": aid, "mesh": mesh}])
    return cat, root


def build(tmp_path: Path, *, meshes: dict | None = None, cache: dict | None = None, **kw):
    """``(directory, excluded, catalogs_dir, threejs_root)``: FAKE_Attach built with geometry and the fixture pack settings."""
    cat, root = write_world(tmp_path, meshes=meshes)
    kw.setdefault("threejs_v2_dir", root)
    kw.setdefault("geometry_cache", {} if cache is None else cache)
    directory, excluded = WFX.build(cat, pack_settings=PACK_SETTINGS, **kw)
    return directory, excluded, cat, root


# -- W8b: host mounts (docs/weapon_attachments.md 4 and the AC66 to AC68, AC84 fixtures) -----------------------------
#
# A second pack, FAKE_Mount, written by ``write_mount_world`` next to the W8a one (the W8a counts stay as they were). Every
# host is a Z-long gun, z -0.25..0.65 with the origin at z 0 (so +z is forward and +y is up): a body box x +-0.02, y 0..0.10,
# z -0.25..0.35 and a barrel of 0.30 m ending at z 0.65, centred on (x 0, y 0.055). Children are baked as child nodes of the
# host's root node, moved by a translation only (a rotation only in the NB-15 host). The expected seats are LITERALS worked out
# by hand: a child's foot centre (its own mesh) plus the child node's translation.
#
#   scope    optic(): foot centre (0.005, 0, 0.05), foot 0.06 long   -> at (0, 0.10, 0.10): seat (0.005, 0.10, 0.15), span 0.06
#   mag      box x +-0.01, y -0.12..0, z +-0.02: top face centre (0, 0, 0), 0.04 long -> at (0, 0, -0.05): seat (0, 0, -0.05)
#   trigger  a small box, never a mount (child_never)
#   round barrel: outer ring r 0.0125 (16 points), bore ring r 0.0065 (12 points) at the muzzle face -> bore_d 0.0130 (the
#            outer ring alone would give 0.025); the square barrel of the plain host has four corners at r 0.01414: no ring,
#            face extent 2 * 0.01414 = 0.0283
#   brake    a 0.08 m round tube from z 0.65 to 0.73 on the barrel end: the bare-gun muzzle is its face (z 0.73), the seat
#            (barrel end) is z 0.65

MOUNT_PACK = "FAKE_Mount"
MOUNT_SETTINGS = {MOUNT_PACK: {"setting": "military", "era": "modern"}}
MOUNT_SHARED_GLB = f"glb/{MOUNT_PACK}/shared.glb"
BORE_D_M, FACE_EXTENT_M, BRAKE_LENGTH_M = 0.0130, 0.0283, 0.08
BARREL_END_Z, BRAKE_FACE_Z = 0.65, 0.73
UP, DOWN, FORWARD = [0.0, 1.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, 1.0]

SCOPE_AT, SCOPE_SEAT, SCOPE_SPAN = (0.0, 0.10, 0.10), (0.005, 0.10, 0.15), 0.06
MAG_AT, MAG_SEAT, MAG_SPAN = (0.0, 0.0, -0.05), (0.0, 0.0, -0.05), 0.04
BIG_MAG_AT, BIG_MAG_SEAT, BIG_MAG_SPAN = (0.0, 0.0, 0.10), (0.0, 0.0, 0.10), 0.06  # x +-0.012, y -0.14..0, z +-0.03
SMALL_MAG_AT, SMALL_MAG_SEAT, SMALL_MAG_SPAN = (0.0, 0.0, -0.10), (0.0, 0.0, -0.10), 0.04  # x +-0.01, y -0.08..0, z +-0.02
FOREGRIP_AT, FOREGRIP_SEAT = (0.0, 0.0, 0.03), (0.005, 0.0, 0.08)  # flip_y(optic()): foot at the top, centre (0.005, 0, 0.05)
LASER_AT, LASER_SEAT = (0.0, 0.04, 0.0), (0.005, 0.04, 0.05)
YAWED_SCOPE_AT, YAWED_SCOPE_SEAT = (0.0, 0.10, 0.0), (0.05, 0.10, -0.005)  # optic() yawed +90 degrees: (x, z) -> (z, -x)
_ROT_Y_90 = [0.0, 0.7071067811865476, 0.0, 0.7071067811865476]

# host asset id -> expected hold class
MOUNT_HOSTS = {
    "SM_Wep_Rifle_Mount_01": "long_gun",   # (a) scope + mag + trigger children, round barrel with a bore ring
    "SM_Wep_Rifle_Double_01": "long_gun",  # two magazines: a small one that sorts first, a large one that sorts last
    "SM_Wep_Rifle_Plain_01": "long_gun",   # (c) no child at all; a square barrel (no ring)
    "SM_Wep_Pistol_Mount_01": "one_hand",  # foregrip and laser children
    "SM_Wep_Grenade_Mount_01": "thrown",   # (d) not a host, whatever its children are called
    "SM_Wep_Rifle_Muzz_01": "long_gun",    # (g) a baked brake child 0.08 m long
    "SM_Wep_Rifle_Fall_01": "long_gun",    # the barrel ends in one apex: the muzzle probe falls back to the bounds
    "SM_Wep_Rifle_Hull_01": "long_gun",    # its only "optic" child is a collision hull
    "SM_Wep_Rifle_Tilt_01": "long_gun",    # the scope child is yawed 90 degrees (NB-15)
    "SM_Wep_Rifle_Shared_01": "long_gun",  # lives in the shared GLB under glb_node "Rifle_Shared"
}


def tube(z0: float, z1: float, r_out: float = 0.0125, r_in: float = 0.0065, n_out: int = 16, n_in: int = 12,
         centre=(0.0, 0.055)):
    """A round barrel along z: an outer ring at each end and a bore ring at ``z1`` (the muzzle face)."""
    cx, cy = centre

    def ring(z, r, n):
        return [(cx + r * np.cos(2 * np.pi * k / n), cy + r * np.sin(2 * np.pi * k / n), z) for k in range(n)]

    verts = np.array(ring(z0, r_out, n_out) + ring(z1, r_out, n_out) + ring(z1, r_in, n_in), dtype=np.float64)
    a, b, c = 0, n_out, 2 * n_out  # first index of the rings at z0, the outer ring at z1 and the bore ring
    tris = []
    for k in range(n_out):
        k2 = (k + 1) % n_out
        tris += [[a + k, a + k2, b + k2], [a + k, b + k2, b + k]]
        tris.append([b + k, b + k2, c + (k * n_in) // n_out])
    tris += [[c + j, c + (j + 1) % n_in, b + (j * n_out) // n_in] for j in range(n_in)]
    return verts, np.array(tris, dtype=np.int64)


def host_body(muzzle: str = "round"):
    """Body box plus a barrel: ``round`` (bore ring), ``square`` (four corners) or ``apex`` (one vertex at the end)."""
    body = G.box((-0.02, 0.0, -0.25), (0.02, 0.10, 0.35))
    if muzzle == "round":
        barrel = tube(0.35, BARREL_END_Z)
    elif muzzle == "square":
        barrel = G.loft(2, [(0.35, 0.01, 0.01, 0, 0.055), (BARREL_END_Z, 0.01, 0.01, 0, 0.055)])
    else:
        barrel = G.loft(2, [(0.35, 0.01, 0.01, 0, 0.055), (BARREL_END_Z, 0, 0, 0, 0.055)])
    return G.merge(body, barrel)


def mag_box(x: float, y: float, z: float):
    """A magazine hanging from a flat top at y 0: x +-x, y -y..0, z +-z."""
    return G.box((-x, -y, -z), (x, 0.0, z))


def _child(host: str, suffix: str, mesh, at=(0.0, 0.0, 0.0), rotation=None) -> dict:
    node = {"name": f"{host}_{suffix}", "mesh": mesh, "translation": list(at)}
    if rotation is not None:
        node["rotation"] = rotation
    return node


def mount_roots(host: str) -> list[dict]:
    """The GLB root nodes of one mount host: its own node (the body mesh) with the baked children below it."""
    def body(muzzle="round"):
        return {"name": host, "mesh": host_body(muzzle)}

    if host == "SM_Wep_Rifle_Mount_01":
        kids = [_child(host, "Scope", optic(), SCOPE_AT), _child(host, "Mag", mag_box(0.01, 0.12, 0.02), MAG_AT),
                _child(host, "Trigger", G.box((-0.003, -0.03, -0.01), (0.003, 0.0, 0.01)), (0.0, 0.0, 0.12))]
        return [{**body(), "children": kids}]
    if host == "SM_Wep_Rifle_Double_01":
        kids = [_child(host, "Mag_A_Small", mag_box(0.01, 0.08, 0.02), SMALL_MAG_AT),
                _child(host, "Mag_B_Large", mag_box(0.012, 0.14, 0.03), BIG_MAG_AT)]
        return [{**body(), "children": kids}]
    if host == "SM_Wep_Rifle_Plain_01":
        return [body("square")]
    if host == "SM_Wep_Pistol_Mount_01":
        kids = [_child(host, "Foregrip", flip_y(optic()), FOREGRIP_AT), _child(host, "Laser", optic(), LASER_AT)]
        return [{**body("square"), "children": kids}]
    if host == "SM_Wep_Grenade_Mount_01":
        return [{"name": host, "mesh": G.box((-0.03, 0.0, -0.04), (0.03, 0.09, 0.04)),
                 "children": [_child(host, "Scope", optic(), (0.0, 0.09, 0.0))]}]
    if host == "SM_Wep_Rifle_Muzz_01":
        return [{**body(), "children": [_child(host, "Brake", tube(BARREL_END_Z, BRAKE_FACE_Z))]}]
    if host == "SM_Wep_Rifle_Fall_01":
        return [body("apex")]
    if host == "SM_Wep_Rifle_Hull_01":
        return [{**body(), "children": [_child(host, "Scope_Collision", optic(), SCOPE_AT)]}]
    if host == "SM_Wep_Rifle_Tilt_01":
        return [{**body(), "children": [_child(host, "Scope", optic(), YAWED_SCOPE_AT, _ROT_Y_90)]}]
    raise KeyError(host)


def shared_mount_roots() -> list[dict]:
    """Two rifles in one GLB. ``Rifle_Shared`` (selected) is an empty parent with a body and a scope child; ``Other_Rifle``
    carries a magazine and a scope that the selected host must not see."""
    return [
        {"name": "Rifle_Shared", "translation": [1.0, 0.0, 0.0], "children": [
            {"name": "Rifle_Shared_Body", "mesh": host_body()},
            {"name": "Rifle_Shared_Scope", "mesh": optic(), "translation": list(SCOPE_AT)}]},
        {"name": "Other_Rifle", "translation": [-1.0, 0.0, 0.0], "children": [
            {"name": "Other_Rifle_Body", "mesh": host_body()},
            {"name": "Other_Rifle_Scope", "mesh": optic(), "translation": list(SCOPE_AT)},
            {"name": "Other_Rifle_Mag", "mesh": mag_box(0.01, 0.12, 0.02), "translation": list(MAG_AT)}]},
    ]


def _mount_catalog_doc() -> dict:
    assets = []
    for aid in sorted(MOUNT_HOSTS):
        shared = aid == "SM_Wep_Rifle_Shared_01"
        asset = MC._asset(MOUNT_PACK, aid, glb=MOUNT_SHARED_GLB if shared else "own")
        if shared:
            asset["files"]["glb_node"] = "Rifle_Shared"
        assets.append(asset)
    return {
        "pack_id": MOUNT_PACK, "engine": "Unity", "origin": "fixture", "style": "synthetic", "units": "meters",
        "version": MC.S.CATALOG_VERSION, "scanned_at": MC.SCANNED_AT, "grid": dict(MC.S.DEFAULT_GRID),
        "conventions": dict(MC.S.DEFAULT_CONVENTIONS), "asset_count": len(assets), "assets": assets,
    }


def write_mount_world(tmp_path: Path, *, roots: dict | None = None) -> tuple[Path, Path]:
    """``(catalogs_dir, threejs_v2_root)`` for FAKE_Mount; ``roots`` overrides ``{host id: [root node specs]}``."""
    cat, root = tmp_path / "catalogs", tmp_path / "threejs"
    cat.mkdir(parents=True, exist_ok=True)
    (cat / f"{MOUNT_PACK}.json").write_bytes((json.dumps(_mount_catalog_doc(), indent=2, sort_keys=True) + "\n").encode("utf-8"))
    for aid in sorted(MOUNT_HOSTS):
        if aid == "SM_Wep_Rifle_Shared_01":
            G.write_glb(root / MOUNT_SHARED_GLB, shared_mount_roots())
            continue
        G.write_glb(root / "glb" / MOUNT_PACK / f"{aid}.glb", (roots or {}).get(aid) or mount_roots(aid))
    return cat, root


def build_mount_world(tmp_path: Path, *, roots: dict | None = None, cache: dict | None = None, **kw):
    """``(directory, excluded, catalogs_dir, threejs_root)``: FAKE_Mount built with geometry."""
    cat, root = write_mount_world(tmp_path, roots=roots)
    kw.setdefault("threejs_v2_dir", root)
    kw.setdefault("geometry_cache", {} if cache is None else cache)
    directory, excluded = WFX.build(cat, pack_settings=MOUNT_SETTINGS, **kw)
    return directory, excluded, cat, root
