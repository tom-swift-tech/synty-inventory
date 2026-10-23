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
