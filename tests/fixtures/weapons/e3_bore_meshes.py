"""Synthetic hosts for the E3.1 / E3.2 barrel-face tests (errata E3.1 and E3.2; tests/test_weapons_e3_bore.py).

Pure numpy on top of ``g1_bore_meshes`` (tubes and boxes built from literals), no GLB of a pack and no pack data. Every host is built in the host's
(f, s, u) frame (barrel along +f); ``to_asset`` turns it into the asset axes the tests give ``mounts.build_mounts`` (forward +z, up +y, so side is +x
and an (f, s, u) point is the asset point (s, u, f)). A fused device is a part in asset coordinates plus a translation that is a multiple of 1e-4 (the
precision the locator stores), merged into the host the way a preset is assembled.

The dimensions are the ones the errata fixture tables state:

* ``slide_face()``: a 60 x 30 mm block ending flush at f = 0.200, with a tube (outer 22 mm, bore 15 mm) proud of it by 3 mm and 5 mm off the block's
  centre, so the slab centre (the block's) and the tube axis differ;
* ``rod_barrel()``: a solid 32-sided rod, outer 24 mm, no bore ring, ending at f = 0.250;
* ``ringed_barrel()``: a tube with its own 30 mm / 16 mm ring, ending at f = 0.250;
* ``block_behind_barrel()``: a 60 x 30 mm block ending 5 mm behind a 22 mm / 15 mm ringed barrel's end (inside the 10 mm end slab);
* ``recessed_bore_barrel()``: a 30 mm rod capped flat with a bore ring 5 mm behind the cap, so the A0 face holds one radius (``face_extent``) and the
  10 mm slab holds a ring (evidence (ii));
* ``device()``: the fused muzzle device, a tube of outer 40 mm and bore 12 mm, fused at f = 0.250 (``DEVICE_AT``).
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


M = _load("g1_bore_meshes")
WRITE_GLB = _load("make_glbs").write_glb

AXES = {"forward": "+z", "up": "+y"}
SAFE_M = 1e-5  # see ``mm``
DEVICE_AT = (0.0, 0.0, 0.25)  # the fused device's translation, asset coordinates (x = s, y = u, z = f)
DEVICE_PART = "device_part"


def mm(x: float) -> float:
    """A radius of ``x`` millimetres, 10 micrometres inside its 1 mm radial bin. The bore estimator (``mounts.bore_diameter``) bins the face at 1 mm
    from the face centre; a whole-millimetre radius sits ON a bin edge, where the 1e-9 m a GLB's float32 storage moves a vertex decides the bin and a
    solid end reads as a ring. The names below keep the errata's round numbers (a 22 mm tube): they are 22.01 mm here."""
    return x * 1e-3 + SAFE_M


def to_asset(verts: np.ndarray) -> np.ndarray:
    """(f, s, u) -> asset (x, y, z) = (s, u, f)."""
    return np.asarray(verts, dtype=np.float64)[:, [1, 2, 0]]


def bore_tube(f0: float, f1: float, radius: float, centre: tuple[float, float] = (0.0, 0.0)) -> tuple[np.ndarray, np.ndarray]:
    """A bare cylinder wall of ``radius`` between two rings, at f0 and f1 (no end faces): a recessed bore."""
    n = M.N_RING
    verts = np.concatenate([M._ring(f, centre, radius, radius) for f in (f0, f1)])
    return verts, np.array(M._band(0, n), dtype=np.int64)


def slide_face() -> tuple[np.ndarray, np.ndarray]:
    return M.merge(M.box(0.10, 0.200, 0.030, 0.015), M.tube(0.150, 0.203, mm(11), mm(7.5), centre=(0.005, -0.003)))


SLIDE_TUBE_CENTRE = (0.005, -0.003)


def rod_barrel() -> tuple[np.ndarray, np.ndarray]:
    return M.tube(0.0, 0.25, mm(12))


def ringed_barrel() -> tuple[np.ndarray, np.ndarray]:
    return M.tube(0.0, 0.25, mm(15), mm(8))


def block_behind_barrel() -> tuple[np.ndarray, np.ndarray]:
    return M.merge(M.box(0.10, 0.245, 0.030, 0.015), M.tube(0.20, 0.25, mm(11), mm(7.5)))


def recessed_bore_barrel() -> tuple[np.ndarray, np.ndarray]:
    return M.merge(M.tube(0.0, 0.25, mm(15)), bore_tube(0.2400, 0.2450, mm(6)))


def square_barrel() -> tuple[np.ndarray, np.ndarray]:
    """A 40 x 40 mm block: no ring and not round (E1.1), so it has no barrel end without a ring bore."""
    return M.box(0.0, 0.25, 0.020, 0.020)


def device() -> tuple[np.ndarray, np.ndarray]:
    """The fused device in its own frame: f 0 .. 0.06, outer 40 mm, bore 12 mm (its end face at f = 0.06)."""
    return M.tube(0.0, 0.06, mm(20), mm(6))


def device_part() -> dict:
    v, t = device()
    return {"id": DEVICE_PART, "slot": "muzzle", "verts": to_asset(v), "tris": t}


def fused(barrel: tuple[np.ndarray, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """``barrel`` (f, s, u) with the device fused over its end, as asset-coordinate ``(verts, tris)``."""
    v, t = device()
    moved = to_asset(v) + np.array(DEVICE_AT)
    bv, bt = barrel
    return M.merge((to_asset(bv), bt), (moved, t))


def plain(barrel: tuple[np.ndarray, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    return to_asset(barrel[0]), barrel[1]


def write_host(path: Path, mesh: tuple[np.ndarray, np.ndarray]) -> Path:
    """The host as a one-mesh GLB (node ``Body``, asset axes)."""
    return WRITE_GLB(path, [{"name": "Body", "mesh": mesh}])
