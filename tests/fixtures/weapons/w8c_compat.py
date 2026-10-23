"""FAKE_CompA / FAKE_CompB: synthetic compatibility fixtures for the W8c tests (docs/weapon_attachments.md section 5, AC69-AC75, AC79).

Written by ``write_world`` into a temp folder (not part of make_catalogs.py, for the reason stated in w8a_attach.py) and built with
``PACK_SETTINGS``. Meshes come from w8a_attach (lofts and boxes, Y-up, metres, nothing from a real pack). The expected tiers,
scores and signals in the tests are LITERALS worked out by hand from the rules below, never read from the code under test.

Hosts (every one is a Z-long gun as in the W8b world: +z forward, +y up, body x +-0.02, y 0..0.10, z -0.25..0.35):

  ALPHA   FAKE_CompA  rifle    round barrel (bore ring 0.0130); baked children Scope (optic(), at SCOPE_AT: seat span 0.06) and Mag
                               (mag_box 0.02 x 0.12 x 0.04 at MAG_AT: seat span 0.04). Underbarrel and laser_light: no child, no seat.
  BETA    FAKE_CompA  rifle    square barrel (face extent, no ring); one child "Aux" (an optic() scaled 1.1, node name that no slot
                               claims) so every child slot has no seat; the mount override of the tests seats the optic on it.
  GAMMA   FAKE_CompA  pistol   square body; children Foregrip (flip_y(optic())) and Laser (upside_down_optic(): see below).
  EPSILON FAKE_CompA  rifle    round barrel; children Scope (optic()) and Brake (a round tube on the barrel end, 0.08 m).
  DELTA   FAKE_CompB  rifle    round barrel, no child at all: another pack, so it can only be cross_pack_fit.

Parts (the name tokens that count for family_overlap are the ones left once the generic and the child-vocabulary words are gone):

  Rifle_Scope_01          optic/scope    optic() x1.0   twin of the Scope child of ALPHA and EPSILON (foot 0.06 long)
  Rifle_Scope_Tight_01    optic/scope    optic() x0.95  extents 5 % under the Scope child: not a twin; foot 0.057
  Rifle_Scope_Wide_01     optic/scope    optic() x1.2   foot 0.072 = 1.2 x the 0.06 span
  Rifle_Scope_Giant_01    optic/scope    optic() x1.8   foot 0.108 = 1.8 x the 0.06 span
  Rifle_Silencer_01       muzzle         narrow end h 0.0092 -> mating diameter 0.0260 (twice the bore ring 0.0130)
  Rifle_Silencer_Slim_01  muzzle         narrow end h 0.0046 -> mating diameter 0.0130 (the bore ring)
  Rifle_Silencer_Brake_01 muzzle         the brake tube itself: a twin of the Brake child of EPSILON
  Rifle_Mag_01            magazine       mag_box(0.01, 0.12, 0.02): a twin of the Mag child of ALPHA
  Gamma_Foregrip_01       underbarrel    flip_y(optic()): a twin of the Foregrip child of GAMMA
  Mod_Gamma_Laser_01      laser_light    upside_down_optic(): a twin of the Laser child of GAMMA. It is authored HANGING (apex at
                               the bottom, flat foot on top) on purpose: the anchor prior wants a laser foot at -Y and takes the
                               other end when that end is an apex, and the mount's up is -host up, so only a part whose foot is on
                               top lands on its baked twin (a laser authored foot-down, like an optic, comes out upside down)
  FAKE_CompB/Alt_Scope_01 optic/scope    optic() x1.0, no family token ("alt" is generic): the cross-pack twin
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

PACK_A, PACK_B = "FAKE_CompA", "FAKE_CompB"
PACK_SETTINGS = {PACK_A: {"setting": "military", "era": "modern"}, PACK_B: {"setting": "military", "era": "modern"}}

ALPHA, BETA, GAMMA, EPSILON = ("SM_Wep_Rifle_Alpha_01", "SM_Wep_Rifle_Beta_01", "SM_Wep_Pistol_Gamma_01", "SM_Wep_Rifle_Epsilon_01")
DELTA = "SM_Wep_Rifle_Delta_01"
HOSTS_A = (ALPHA, BETA, GAMMA, EPSILON)
HOSTS_B = (DELTA,)
H = {name: f"{PACK_A}/{name}" for name in HOSTS_A} | {DELTA: f"{PACK_B}/{DELTA}"}

SCOPE, SCOPE_TIGHT, SCOPE_WIDE, SCOPE_GIANT = ("SM_Wep_Rifle_Scope_01", "SM_Wep_Rifle_Scope_Tight_01",
                                               "SM_Wep_Rifle_Scope_Wide_01", "SM_Wep_Rifle_Scope_Giant_01")
SIL, SIL_SLIM, SIL_BRAKE = "SM_Wep_Rifle_Silencer_01", "SM_Wep_Rifle_Silencer_Slim_01", "SM_Wep_Rifle_Silencer_Brake_01"
MAG, GRIP, LASER = "SM_Wep_Rifle_Mag_01", "SM_Wep_Gamma_Foregrip_01", "SM_Wep_Mod_Gamma_Laser_01"
ALT_SCOPE = "SM_Wep_Alt_Scope_01"  # FAKE_CompB
P = {name: f"{PACK_A}/{name}" for name in (SCOPE, SCOPE_TIGHT, SCOPE_WIDE, SCOPE_GIANT, SIL, SIL_SLIM, SIL_BRAKE, MAG, GRIP, LASER)}
P[ALT_SCOPE] = f"{PACK_B}/{ALT_SCOPE}"

SCOPE_AT, MAG_AT, FOREGRIP_AT = A.SCOPE_AT, A.MAG_AT, A.FOREGRIP_AT
LASER_AT = (0.0, -0.03, 0.0)  # the flat foot (top of the hanging mesh, y 0.03 in its own frame) lands on the body underside, y 0
BRAKE_Z0, BRAKE_Z1 = A.BARREL_END_Z, A.BRAKE_FACE_Z
BORE_D_M, FACE_EXTENT_M = A.BORE_D_M, A.FACE_EXTENT_M
SLIM_H = 0.0046  # 2 * 0.0046 * sqrt(2) = 0.01301


def scaled(mesh, k: float):
    v, t = mesh
    return v * k, t


def slim_suppressor():
    return G.loft(2, [(-0.1, SLIM_H, SLIM_H), (0.1, A.MUZZLE_WIDE_H, A.MUZZLE_WIDE_H)])


def brake_tube():
    return A.tube(BRAKE_Z0, BRAKE_Z1)


def mag_mesh():
    return A.mag_box(0.01, 0.12, 0.02)


# asset id -> mesh builder of a standalone part (the GLB is a single mesh node)
PART_MESHES = {
    SCOPE: A.optic, SCOPE_TIGHT: lambda: scaled(A.optic(), 0.95), SCOPE_WIDE: lambda: scaled(A.optic(), 1.2),
    SCOPE_GIANT: lambda: scaled(A.optic(), 1.8), SIL: A.suppressor, SIL_SLIM: slim_suppressor, SIL_BRAKE: brake_tube,
    MAG: mag_mesh, GRIP: lambda: A.flip_y(A.optic()), LASER: A.upside_down_optic, ALT_SCOPE: A.optic,
}
PARTS_A = (SCOPE, SCOPE_TIGHT, SCOPE_WIDE, SCOPE_GIANT, SIL, SIL_SLIM, SIL_BRAKE, MAG, GRIP, LASER)
# the (slot, kind) the classifier must give each part
PART_CLASS = {
    SCOPE: ("optic", "scope"), SCOPE_TIGHT: ("optic", "scope"), SCOPE_WIDE: ("optic", "scope"), SCOPE_GIANT: ("optic", "scope"),
    SIL: ("muzzle", "suppressor"), SIL_SLIM: ("muzzle", "suppressor"), SIL_BRAKE: ("muzzle", "suppressor"),
    MAG: ("magazine", "standard"), GRIP: ("underbarrel", "foregrip"), LASER: ("laser_light", "laser"),
    ALT_SCOPE: ("optic", "scope"),
}


def host_roots(host: str) -> list[dict]:
    """The GLB root nodes of one host: its own body node with the baked children below it."""
    def kid(suffix, mesh, at):
        return A._child(host, suffix, mesh, at)

    square = host in (BETA, GAMMA)
    node = {"name": host, "mesh": A.host_body("square" if square else "round")}
    kids: list[dict] = []
    if host == ALPHA:
        kids = [kid("Scope", A.optic(), SCOPE_AT), kid("Mag", mag_mesh(), MAG_AT)]
    elif host == BETA:
        kids = [kid("Aux", scaled(A.optic(), 1.1), SCOPE_AT)]
    elif host == GAMMA:
        kids = [kid("Foregrip", A.flip_y(A.optic()), FOREGRIP_AT), kid("Laser", A.upside_down_optic(), LASER_AT)]
    elif host == EPSILON:
        kids = [kid("Scope", A.optic(), SCOPE_AT), kid("Brake", brake_tube(), (0.0, 0.0, 0.0))]
    return [{**node, "children": kids}] if kids else [node]


def _catalog_doc(pack: str, ids) -> dict:
    assets = [MC._asset(pack, aid) for aid in sorted(ids)]
    return {
        "pack_id": pack, "engine": "Unity", "origin": "fixture", "style": "synthetic", "units": "meters",
        "version": MC.S.CATALOG_VERSION, "scanned_at": MC.SCANNED_AT, "grid": dict(MC.S.DEFAULT_GRID),
        "conventions": dict(MC.S.DEFAULT_CONVENTIONS), "asset_count": len(assets), "assets": assets,
    }


def write_world(tmp_path: Path, *, roots: dict | None = None, meshes: dict | None = None, drop: tuple = ()) -> tuple[Path, Path]:
    """``(catalogs_dir, threejs_v2_root)``; ``roots`` overrides ``{host id: [root node specs]}``, ``meshes`` ``{part id: mesh}``,
    ``drop`` removes assets (by asset id) from both packs."""
    cat, root = tmp_path / "catalogs", tmp_path / "threejs"
    cat.mkdir(parents=True, exist_ok=True)
    in_a = [a for a in (*HOSTS_A, *PARTS_A) if a not in drop]
    in_b = [a for a in (*HOSTS_B, ALT_SCOPE) if a not in drop]
    for pack, ids in ((PACK_A, in_a), (PACK_B, in_b)):
        (cat / f"{pack}.json").write_bytes((json.dumps(_catalog_doc(pack, ids), indent=2, sort_keys=True) + "\n").encode("utf-8"))
        for aid in sorted(ids):
            if aid in HOSTS_A or aid in HOSTS_B:
                nodes = (roots or {}).get(aid) or host_roots(aid)
            else:
                nodes = [{"name": aid, "mesh": (meshes or {}).get(aid) or PART_MESHES[aid]()}]
            G.write_glb(root / "glb" / pack / f"{aid}.glb", nodes)
    return cat, root


def build(tmp_path: Path, *, roots: dict | None = None, meshes: dict | None = None, drop: tuple = (), cache: dict | None = None,
          **kw):
    """``(directory, excluded, catalogs_dir, threejs_root)``: both packs built with geometry."""
    cat, root = write_world(tmp_path, roots=roots, meshes=meshes, drop=drop)
    kw.setdefault("threejs_v2_dir", root)
    kw.setdefault("geometry_cache", {} if cache is None else cache)
    directory, excluded = WFX.build(cat, pack_settings=PACK_SETTINGS, **kw)
    return directory, excluded, cat, root


def by_id(directory: dict) -> dict:
    return {w["id"]: w for w in directory["weapons"]}


def hosts_of(rec: dict, key: str = "compatible_hosts") -> list[tuple]:
    """``[(host id, tier, score or None)]`` of one list of a part, in stored order."""
    return [(e["host"], e["tier"], e.get("score")) for e in rec["attachment"][key]]


def aabb(verts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return verts.min(axis=0), verts.max(axis=0)


def iou(a, b) -> float:
    lo, hi = np.maximum(a[0], b[0]), np.minimum(a[1], b[1])
    inter = float(np.prod(np.clip(hi - lo, 0.0, None)))
    union = float(np.prod(a[1] - a[0])) + float(np.prod(b[1] - b[0])) - inter
    return inter / union if union > 0 else 0.0


def build_report(tmp_path: Path, *, overrides: dict | None = None, rules: dict | None = None, roots: dict | None = None,
                 meshes: dict | None = None, drop: tuple = (), cache: dict | None = None):
    """``(directory, excluded, report, catalogs_dir, threejs_root)``: like ``build`` but with the build report (warnings)."""
    from synty_inventory.weapons.directory import build_directory_report
    from synty_inventory.weapons.overrides import empty_overrides

    cat, root = write_world(tmp_path, roots=roots, meshes=meshes, drop=drop)
    directory, excluded, report = build_directory_report(
        cat, overrides=overrides if overrides is not None else empty_overrides(), rules=rules, pack_settings=PACK_SETTINGS,
        threejs_v2_dir=root, geometry_cache={} if cache is None else cache)
    return directory, excluded, report, cat, root


def overrides_doc(ids: dict | None = None, globs: dict | None = None) -> dict:
    return WFX.overrides_doc(ids, globs)
