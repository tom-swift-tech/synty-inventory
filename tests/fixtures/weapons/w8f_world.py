"""FAKE_W8F: synthetic twin-evidence fixtures for the W8f tests (docs/weapon_attachments.md amendment A1, AC85, AC86).

One pack, four small worlds (each written into its own temp folder, so a part only ever sees the hosts of its own world). Every
mesh comes from w8a_attach / make_glbs (boxes and lofts, Y-up, metres, nothing from a real pack). The expected values in the
tests are LITERALS worked out by hand from the numbers below, never read from the code under test.

Upright hosts are Z-long guns as in the W8b world (+z forward, +y up, body x +-0.02, y 0..0.10, z -0.25..0.35). A baked child is a
mesh node moved by a translation only, so its foot centre in the host is its own foot centre plus the node translation.

``seat`` world
  TWIN   upright host: Mag_A_Small (mag_box 0.01 / 0.08 / 0.02 at (0, 0, -0.10): seat (0, 0, -0.10), span 0.04), Mag_B_Large
         (mag_box 0.012 / 0.14 / 0.03 at (0, 0, 0.10): seat (0, 0, 0.10), span 0.06, the larger by volume so it owns the mount's
         own seat) and Scope (optic() at (0, 0.10, 0.10): one child in its slot, so no ``seats``).
  SPIN   the same children on a body turned a quarter turn about X, (x, y, z) -> (x, z, -y): its item_basis is rows (-1,0,0),
         (0,0,1), (0,1,0), i.e. item = (-x, z, y). Forward +y, up +z; the magazine mount takes up -z.
  MAG_SMALL / MAG_LARGE   standalone twins of the two magazines.

``rev`` world
  REV    upright host: Scope (flip_z(optic()) at (0, 0.10, 0.10): the flare faces -z, foot centre (0.005, 0.10, 0.05)), Mag_Drum
         (mag_box 0.07 / 0.09 / 0.055 at (0, 0, -0.12): x 0.14 long, z 0.11, y 0.09, foot centre (0, 0, -0.12)) and nothing else.
  TILT   upright host whose Scope child (flip_z(optic()) x 1.3, at (0, 0.10, 0)) is yawed 90 degrees, so its per-axis extents are
         0.26 / 0.104 / 0.078 (x / y / z) against the part's 0.078 / 0.104 / 0.26.
  SCOPE_REV   flip_z(optic()): measured forward -z, the host's is +z.
  SCOPE_OVR   the same mesh with a categorical ``forward: -z`` override.
  DRUM        mag_box 0.07 / 0.09 / 0.055: measured along x (longer), the host's forward is z.
  SCOPE_TILT  flip_z(optic()) x 1.3: a sorted-extents twin of the yawed child, not a per-axis one.

``dis`` world
  DIS_U  upright host (forward +z) with a Scope child (flip_z(optic())); DIS_Y the same on a body yawed 90 degrees (forward +x).
  SCOPE_DIS   flip_z(optic()): a twin of both children, with two different needed forwards.

``muz`` world
  MUZ    the turned host (forward +y, up +z) with a baked Brake child (the 0.08 m round tube on the barrel end).
  BRAKE  the brake tube as a standalone part: a twin of the child. Its muzzle anchor has forward +y (the authored up) while the
         host's muzzle mount has forward = the host's up (+z), so applying the correction to a muzzle device WOULD change it.
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


A = _load("w8a_attach")
G, MC, WFX = A.G, A.MC, A.WFX

PACK = "FAKE_W8F"
PACK_SETTINGS = {PACK: {"setting": "military", "era": "modern"}}

TWIN, SPIN = "SM_Wep_Rifle_Twin_01", "SM_Wep_Rifle_Spin_01"
REV, TILT = "SM_Wep_Rifle_Rev_01", "SM_Wep_Rifle_Tilt_01"
DIS_U, DIS_Y = "SM_Wep_Rifle_DisU_01", "SM_Wep_Rifle_DisY_01"
MUZ = "SM_Wep_Rifle_Muz_01"
MAG_SMALL, MAG_LARGE = "SM_Wep_Rifle_Mag_01", "SM_Wep_Rifle_Mag_Big_01"
SCOPE_REV, SCOPE_OVR, SCOPE_TILT, SCOPE_DIS = ("SM_Wep_Rifle_Scope_01", "SM_Wep_Rifle_Scope_Ovr_01",
                                                "SM_Wep_Rifle_Scope_Tilt_01", "SM_Wep_Rifle_Scope_Dis_01")
DRUM = "SM_Wep_DrumMag_01"
BRAKE = "SM_Wep_Rifle_Silencer_Brake_01"
ID = {n: f"{PACK}/{n}" for n in (TWIN, SPIN, REV, TILT, DIS_U, DIS_Y, MUZ, MAG_SMALL, MAG_LARGE, SCOPE_REV, SCOPE_OVR, SCOPE_TILT,
                                 SCOPE_DIS, DRUM, BRAKE)}

SCOPE_AT = (0.0, 0.10, 0.10)
SMALL_AT, LARGE_AT = (0.0, 0.0, -0.10), (0.0, 0.0, 0.10)
DRUM_AT = (0.0, 0.0, -0.12)
TILT_AT = (0.0, 0.10, 0.0)
_ROT_Y_90 = [0.0, 0.7071067811865476, 0.0, 0.7071067811865476]


# -- meshes -----------------------------------------------------------------------------------------------


def small_mag():
    return A.mag_box(0.01, 0.08, 0.02)


def large_mag():
    return A.mag_box(0.012, 0.14, 0.03)


def drum_mag():
    return A.mag_box(0.07, 0.09, 0.055)


def reversed_scope():
    """optic() mirrored in z: the objective flare faces -z, the foot centre is (0.005, 0, -0.05)."""
    return A.flip_z(A.optic())


def big_reversed_scope():
    v, t = reversed_scope()
    return v * 1.3, t


def turn_x(mesh):
    """A quarter turn about X: (x, y, z) -> (x, z, -y). A proper rotation."""
    v, t = mesh
    return np.stack([v[:, 0], v[:, 2], -v[:, 1]], axis=1), t


def turn_vec(vec):
    x, y, z = vec
    return [x, z, -y]


def _kid(host, suffix, mesh, at, rotation=None):
    return A._child(host, suffix, mesh, at, rotation)


def host_roots(host: str) -> list[dict]:
    """The GLB root nodes of one host: its body with the baked children below it (the children keep their authored meshes)."""
    body = A.host_body("round")
    if host == TWIN:
        kids = [_kid(host, "Mag_A_Small", small_mag(), SMALL_AT), _kid(host, "Mag_B_Large", large_mag(), LARGE_AT),
                _kid(host, "Scope", A.optic(), SCOPE_AT)]
        return [{"name": host, "mesh": body, "children": kids}]
    if host == SPIN:
        kids = [_kid(host, "Mag_A_Small", small_mag(), turn_vec(SMALL_AT)),
                _kid(host, "Mag_B_Large", large_mag(), turn_vec(LARGE_AT)),
                _kid(host, "Scope", A.optic(), turn_vec(SCOPE_AT))]
        return [{"name": host, "mesh": turn_x(body), "children": kids}]
    if host == REV:
        kids = [_kid(host, "Scope", reversed_scope(), SCOPE_AT), _kid(host, "Mag_Drum", drum_mag(), DRUM_AT)]
        return [{"name": host, "mesh": body, "children": kids}]
    if host == TILT:
        return [{"name": host, "mesh": body, "children": [_kid(host, "Scope", big_reversed_scope(), TILT_AT, _ROT_Y_90)]}]
    if host == DIS_U:
        return [{"name": host, "mesh": body, "children": [_kid(host, "Scope", reversed_scope(), SCOPE_AT)]}]
    if host == DIS_Y:
        kids = [_kid(host, "Scope", reversed_scope(), A.yaw_vec(SCOPE_AT, 1))]
        return [{"name": host, "mesh": A.yaw(body, 1), "children": kids}]
    if host == MUZ:
        return [{"name": host, "mesh": turn_x(body), "children": [_kid(host, "Brake", A.tube(A.BARREL_END_Z, A.BRAKE_FACE_Z), (0.0, 0.0, 0.0))]}]
    raise KeyError(host)


PART_MESHES = {
    MAG_SMALL: small_mag, MAG_LARGE: large_mag, SCOPE_REV: reversed_scope, SCOPE_OVR: reversed_scope, SCOPE_DIS: reversed_scope,
    SCOPE_TILT: big_reversed_scope, DRUM: drum_mag, BRAKE: lambda: A.tube(A.BARREL_END_Z, A.BRAKE_FACE_Z),
}

WORLDS = {  # world name -> (hosts, parts)
    "seat": ((TWIN, SPIN), (MAG_SMALL, MAG_LARGE)),
    "rev": ((REV, TILT), (SCOPE_REV, SCOPE_OVR, DRUM, SCOPE_TILT)),
    "dis": ((DIS_U, DIS_Y), (SCOPE_DIS,)),
    "muz": ((MUZ,), (BRAKE,)),
}


def _catalog_doc(ids) -> dict:
    assets = [MC._asset(PACK, aid) for aid in sorted(ids)]
    return {
        "pack_id": PACK, "engine": "Unity", "origin": "fixture", "style": "synthetic", "units": "meters",
        "version": MC.S.CATALOG_VERSION, "scanned_at": MC.SCANNED_AT, "grid": dict(MC.S.DEFAULT_GRID),
        "conventions": dict(MC.S.DEFAULT_CONVENTIONS), "asset_count": len(assets), "assets": assets,
    }


def write_world(tmp_path: Path, world: str, *, roots: dict | None = None) -> tuple[Path, Path]:
    """``(catalogs_dir, threejs_v2_root)`` of one world; ``roots`` overrides ``{host asset id: [root node specs]}``."""
    hosts, parts = WORLDS[world]
    cat, root = tmp_path / "catalogs", tmp_path / "threejs"
    cat.mkdir(parents=True, exist_ok=True)
    (cat / f"{PACK}.json").write_bytes((json.dumps(_catalog_doc((*hosts, *parts)), indent=2, sort_keys=True) + "\n").encode("utf-8"))
    for aid in (*hosts, *parts):
        nodes = ((roots or {}).get(aid) or host_roots(aid)) if aid in hosts else [{"name": aid, "mesh": PART_MESHES[aid]()}]
        G.write_glb(root / "glb" / PACK / f"{aid}.glb", nodes)
    return cat, root


def build(tmp_path: Path, world: str, *, overrides: dict | None = None, cache: dict | None = None, **kw):
    """``(directory, excluded, catalogs_dir, threejs_root)`` of one world, built with geometry."""
    cat, root = write_world(tmp_path, world)
    kw.setdefault("threejs_v2_dir", root)
    kw.setdefault("geometry_cache", {} if cache is None else cache)
    if overrides is not None:
        kw["overrides"] = overrides
    directory, excluded = WFX.build(cat, pack_settings=PACK_SETTINGS, **kw)
    return directory, excluded, cat, root


def overrides_doc(ids: dict | None = None, globs: dict | None = None) -> dict:
    return WFX.overrides_doc(ids, globs)


def by_id(directory: dict) -> dict:
    return {w["id"]: w for w in directory["weapons"]}


def aabb(verts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return verts.min(axis=0), verts.max(axis=0)


def iou(a, b) -> float:
    lo, hi = np.maximum(a[0], b[0]), np.minimum(a[1], b[1])
    inter = float(np.prod(np.clip(hi - lo, 0.0, None)))
    union = float(np.prod(a[1] - a[0])) + float(np.prod(b[1] - b[0])) - inter
    return inter / union if union > 0 else 0.0


def child_box(mesh, at) -> tuple[np.ndarray, np.ndarray]:
    """AABB of a baked child: its own mesh moved by the node translation (the children here have no rotation)."""
    lo, hi = aabb(mesh[0])
    return lo + np.asarray(at), hi + np.asarray(at)
