"""The W8d synthetic world: every weapon fixture pack in ONE catalogs dir, for the export, review and regression tests.

Packs (all synthetic, generated at test time, nothing from a real pack):

* the W4 review world (``review_helpers``: FAKE_Fantasy, FAKE_Modern, FAKE_Review and the shared-GLB pack FAKE_Shared),
* FAKE_Attach (``w8a_attach.write_world``: the parts of every token row, the symmetric and the footless scope),
* FAKE_Mount (``w8a_attach.write_mount_world``: hosts with children, the ambiguous and the NB-15 host),
* FAKE_CompA / FAKE_CompB (``w8c_compat.write_world``: twins, tiers, a pack with no same-pack part).

One host is rotated on purpose: ``ROT_HOST`` (FAKE_CompA Alpha) has its body turned a quarter turn about X, so its barrel
points along +Y and its ``item_basis`` is not the identity. The parts' bases already differ from the hosts' (a scope's
forward is -z, a magazine's -y), so the export tests see both a rotated host and rotated parts.

The same module is loaded by ``w8d_gen_reference.py`` under the untouched W7 tree to build the W7 reference files; it
therefore reaches engine code only through ``wfx.build`` (``synty_inventory.weapons.directory.build_directory``), which
exists unchanged in both trees.
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


H = _load("review_helpers")
A = _load("w8a_attach")
C = _load("w8c_compat")

PACK_SETTINGS = {**H.pack_settings(), **A.PACK_SETTINGS, **A.MOUNT_SETTINGS, **C.PACK_SETTINGS}
ROT_HOST = C.H[C.ALPHA]  # FAKE_CompA/SM_Wep_Rifle_Alpha_01
ATTACH_PACKS = (A.PACK, A.MOUNT_PACK, C.PACK_A, C.PACK_B)  # the packs that carry attachment parts and hosts


def _turn_x(mesh):
    """A quarter turn about X: (x, y, z) -> (x, z, -y). A proper rotation, so the mesh keeps its handedness."""
    v, t = mesh
    return np.stack([v[:, 0], v[:, 2], -v[:, 1]], axis=1), t


def _turn_vec(vec):
    x, y, z = vec
    return [x, z, -y]


def rotated_alpha_roots() -> list[dict]:
    """ALPHA's GLB with the body turned about X. The baked children keep their authored (Y-up) meshes, because the anchor
    algorithm reads that prior, and only their placement turns with the body."""
    host = C.ALPHA
    node = {"name": host, "mesh": _turn_x(A.host_body("round"))}
    kids = [
        A._child(host, "Scope", A.optic(), _turn_vec(C.SCOPE_AT)),
        A._child(host, "Mag", C.mag_mesh(), _turn_vec(C.MAG_AT)),
    ]
    return [{**node, "children": kids}]


def write_world(tmp: Path) -> tuple[Path, Path]:
    """``(catalogs_dir, threejs_v2_root)`` of the whole world, written below ``tmp``."""
    cat = H.make_catalogs(tmp, shared=True)
    root = H.make_threejs(tmp, cat)  # before the other packs: it builds the stand-ins for the catalogs that exist now
    A.write_world(tmp)
    A.write_mount_world(tmp)
    C.write_world(tmp, roots={C.ALPHA: rotated_alpha_roots()})
    return cat, root


def build(tmp: Path, **kw):
    """``(directory, excluded, catalogs_dir, threejs_root)`` with geometry, built with empty overrides."""
    cat, root = write_world(tmp)
    kw.setdefault("threejs_v2_dir", root)
    kw.setdefault("geometry_cache", {})
    kw.setdefault("pack_settings", PACK_SETTINGS)
    directory, excluded = H.build(cat, **kw)
    return directory, excluded, cat, root


def write_config(tmp: Path, cat: Path, root: Path | None = None, extra: list[str] | None = None) -> Path:
    lines = list(extra or [])
    if root is not None:
        lines.append(f'threejs_v2: "{root.as_posix()}"')
    return H.write_config(tmp, cat, lines)
