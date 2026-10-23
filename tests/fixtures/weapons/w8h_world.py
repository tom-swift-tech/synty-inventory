"""FAKE_Sight* packs: synthetic sight fixtures for the W8h tests (docs/weapon_attachments.md 3.3, 3.5, 4.2, 4.3, 4.6, 5.1; AC87-AC93).

Written into a temp folder by ``write_world`` (not part of make_catalogs.py, for the reason stated in w8a_attach.py). Meshes are
boxes, prisms and the W8a optic, Y-up, metres, +z forward; nothing is from a real pack. Every expected number in the tests is a
LITERAL worked out by hand from the dimensions below, never read from the code under test.

``world`` spec: ``{pack: {"hosts": {asset id: [root node specs]}, "parts": {asset id: mesh}}}``.

Hosts (all +z forward, +y up, centred on x 0):

  box rifle  receiver x +-0.02, y 0..0.10, z -0.2525..0.0475 (top 0.10); lower handguard x +-0.02, y 0..0.075, z 0.0475..0.4012;
             thin barrel x +-0.006, y 0.04..0.052, z 0.4012..0.65. Hand-worked 4.6 seats: rear (0, 0.10, -0.2425) (receiver rear end
             plus 10 mm), front (0, 0.075, 0.3932) (handguard front end minus 8 mm; the 5 mm bins put the probe 1.3 mm further out).
  slide      a pistol: slide x +-0.015, y 0.03..0.075, z -0.09..0.09 over a grip. Whatever the probe decides, both seats or none.
  prism      a tent: a ridge across x, base z +-0.1, apex y 0.2: slope 2, so the bins within 6 mm of the top are 6 mm wide, under
             the 3 bins the probe needs.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def _load(name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


A = _load("w8a_attach")
G, MC, WFX = A.G, A.MC, A.WFX


def sight_rules(genre_by_pack: dict | None = None, **probe) -> dict:
    """The shipped rules with ``attach_genre_by_pack`` replaced by ``genre_by_pack`` (default: empty, so every pack is a setting of its
    own) and the given ``sight_probe`` parameters overridden."""
    from synty_inventory.weapons.rules import load_rules

    rules = deepcopy(load_rules())
    rules["attachment_rules"]["attach_genre_by_pack"] = dict(genre_by_pack or {})
    rules["attachment_rules"]["sight_probe"].update(probe)
    return rules


# -- meshes --------------------------------------------------------------------------------------------------


def sight_part():
    """An iron-sight stand-in: the W8a optic at a fifth of its size (foot centre (0.001, 0, 0.01), foot 0.012 long)."""
    v, t = A.optic()
    return v * 0.2, t


def sight_scaled(k: float):
    v, t = A.optic()
    return v * k, t


def box_rifle():
    return G.merge(G.box((-0.02, 0.0, -0.2525), (0.02, 0.10, 0.0475)), G.box((-0.02, 0.0, 0.0475), (0.02, 0.075, 0.4012)),
                   G.box((-0.006, 0.04, 0.4012), (0.006, 0.052, 0.65)))


def slide_pistol():
    return G.merge(G.box((-0.015, 0.03, -0.09), (0.015, 0.075, 0.09)), G.box((-0.012, -0.08, -0.07), (0.012, 0.03, -0.02)))


def prism():
    """Triangular prism: cross-section (z, y) = (-0.1, 0), (0.1, 0), (0, 0.2), extruded x +-0.02."""
    v = np.array([[x, y, z] for x in (-0.02, 0.02) for z, y in ((-0.1, 0.0), (0.1, 0.0), (0.0, 0.2))], dtype=np.float64)
    # indices: x=-0.02 -> 0,1,2 ; x=+0.02 -> 3,4,5
    t = np.array([[0, 2, 1], [3, 4, 5], [0, 1, 4], [0, 4, 3], [1, 2, 5], [1, 5, 4], [2, 0, 3], [2, 3, 5]], dtype=np.int64)
    return v, t


def kid(host: str, suffix: str, mesh, at):
    return A._child(host, suffix, mesh, at)


def host_node(host: str, mesh, kids=()):
    node = {"name": host, "mesh": mesh}
    return [{**node, "children": list(kids)}] if kids else [node]


# -- writing -------------------------------------------------------------------------------------------------


def _catalog_doc(pack: str, ids) -> dict:
    assets = [MC._asset(pack, aid) for aid in sorted(ids)]
    return {
        "pack_id": pack, "engine": "Unity", "origin": "fixture", "style": "synthetic", "units": "meters",
        "version": MC.S.CATALOG_VERSION, "scanned_at": MC.SCANNED_AT, "grid": dict(MC.S.DEFAULT_GRID),
        "conventions": dict(MC.S.DEFAULT_CONVENTIONS), "asset_count": len(assets), "assets": assets,
    }


def write_world(tmp_path: Path, world: dict) -> tuple[Path, Path]:
    """``(catalogs_dir, threejs_v2_root)`` for the packs of ``world``."""
    cat, root = tmp_path / "catalogs", tmp_path / "threejs"
    cat.mkdir(parents=True, exist_ok=True)
    for pack, spec in sorted(world.items()):
        hosts, parts = spec.get("hosts") or {}, spec.get("parts") or {}
        (cat / f"{pack}.json").write_bytes((json.dumps(_catalog_doc(pack, [*hosts, *parts]), indent=2, sort_keys=True) + "\n").encode("utf-8"))
        for aid, nodes in sorted(hosts.items()):
            G.write_glb(root / "glb" / pack / f"{aid}.glb", nodes)
        for aid, mesh in sorted(parts.items()):
            G.write_glb(root / "glb" / pack / f"{aid}.glb", [{"name": aid, "mesh": mesh() if callable(mesh) else mesh}])
    return cat, root


def pack_settings(world: dict) -> dict:
    return {pack: {"setting": "military", "era": "modern"} for pack in world}


def build(tmp_path: Path, world: dict, *, rules: dict | None = None, overrides: dict | None = None, cache: dict | None = None):
    """``(directory, excluded, catalogs_dir, threejs_root)`` for ``world`` with geometry."""
    from synty_inventory.weapons.directory import build_directory
    from synty_inventory.weapons.overrides import empty_overrides

    cat, root = write_world(tmp_path, world)
    directory, excluded = build_directory(
        cat, overrides=overrides if overrides is not None else empty_overrides(), pack_settings=pack_settings(world),
        rules=rules if rules is not None else sight_rules(), threejs_v2_dir=root,
        geometry_cache={} if cache is None else cache)
    return directory, excluded, cat, root


def by_id(directory: dict) -> dict:
    return {w["id"]: w for w in directory["weapons"]}


def overrides_doc(ids: dict | None = None, globs: dict | None = None) -> dict:
    return WFX.overrides_doc(ids, globs)
