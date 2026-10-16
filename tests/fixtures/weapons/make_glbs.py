"""Procedural GLB fixtures for the weapon geometry tests (spec 4.8). Standard library + numpy only; nothing here is
Synty geometry and nothing generated is committed: ``generate_all(dir)`` writes the files at test time.

Every shape is a handful of rectangular lofts (rings of four vertices joined into quads, apex stations collapse a ring
to one vertex). Vertices exist only where a loft has a station, and the handle / support / muzzle measurements read
vertices, so each fixture states where its stations are. ``LABELS`` holds the expected axes, handle and support values
as LITERALS (the tests do not import them from the code under test); they were worked out by hand from the stations
below, not by running the code.

Units are metres, Y-up. The ``_COLLISION`` node in the gun GLBs is a 2 m box that the measurement must ignore.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

_GLB_MAGIC = 0x46546C67
_JSON, _BIN = 0x4E4F534A, 0x004E4942


# -- writer ----------------------------------------------------------------------------------------------


def _pad(b: bytes, fill: bytes) -> bytes:
    return b + fill * (-len(b) % 4)


def write_glb(path: Path, roots: list[dict]) -> Path:
    """Write ``roots`` as the default scene. A node is ``{name, translation?, rotation?, mesh?, children?}`` where
    ``mesh`` is ``(vertices [N,3], triangles [M,3])``."""
    nodes: list[dict] = []
    meshes: list[dict] = []
    accessors: list[dict] = []
    views: list[dict] = []
    blob = bytearray()

    def add_node(spec: dict) -> int:
        node: dict = {"name": spec["name"]}
        for k in ("translation", "rotation", "scale"):
            if k in spec:
                node[k] = [float(c) for c in spec[k]]
        if spec.get("mesh") is not None:
            verts, tris = spec["mesh"]
            verts = np.asarray(verts, dtype="<f4").reshape(-1, 3)
            tris = np.asarray(tris, dtype="<u4").reshape(-1)
            vb, ib = len(blob), None
            blob.extend(verts.tobytes())
            views.append({"buffer": 0, "byteOffset": vb, "byteLength": verts.nbytes})
            ib = len(blob)
            blob.extend(tris.tobytes())
            views.append({"buffer": 0, "byteOffset": ib, "byteLength": tris.nbytes})
            accessors.append({"bufferView": len(views) - 2, "componentType": 5126, "count": len(verts), "type": "VEC3",
                              "min": verts.min(axis=0).tolist(), "max": verts.max(axis=0).tolist()})
            accessors.append({"bufferView": len(views) - 1, "componentType": 5125, "count": len(tris), "type": "SCALAR"})
            meshes.append({"primitives": [{"attributes": {"POSITION": len(accessors) - 2}, "indices": len(accessors) - 1,
                                           "mode": 4}]})
            node["mesh"] = len(meshes) - 1
        idx = len(nodes)
        nodes.append(node)
        kids = [add_node(c) for c in spec.get("children", [])]
        if kids:
            node["children"] = kids
        return idx

    scene = [add_node(r) for r in roots]
    doc: dict = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": scene}], "nodes": nodes}
    if meshes:
        doc.update(meshes=meshes, accessors=accessors, bufferViews=views, buffers=[{"byteLength": len(blob)}])
    js = _pad(json.dumps(doc, separators=(",", ":")).encode("utf-8"), b" ")
    bn = _pad(bytes(blob), b"\0")
    body = struct.pack("<II", len(js), _JSON) + js
    if meshes:
        body += struct.pack("<II", len(bn), _BIN) + bn
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<III", _GLB_MAGIC, 2, 12 + len(body)) + body)
    return path


# -- shapes ----------------------------------------------------------------------------------------------


def loft(axis: int, stations: list[tuple], step: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """A rectangular loft along ``axis``. A station is ``(pos, half_a, half_b[, centre_a, centre_b])`` over the two
    lateral axes in x,y,z order; ``half_a == half_b == 0`` makes an apex (one vertex). ``step`` inserts linearly
    interpolated stations so a vertex exists at least every ``step`` metres (the handle detector bins at 1 cm)."""
    st = [tuple(s) + (0.0,) * (5 - len(s)) for s in stations]
    if step:
        dense = [st[0]]
        for a, b in zip(st, st[1:]):
            n = max(1, int(np.ceil(abs(b[0] - a[0]) / step - 1e-9)))
            for k in range(1, n + 1):
                t = k / n
                dense.append(tuple(a[i] + (b[i] - a[i]) * t for i in range(5)))
        st = dense
    lat = [i for i in range(3) if i != axis]
    verts: list[list[float]] = []
    rings: list[list[int]] = []
    for pos, ha, hb, ca, cb in st:
        ids = []
        corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)] if (ha or hb) else [(0, 0)]
        for sa, sb in corners:
            p = [0.0, 0.0, 0.0]
            p[axis], p[lat[0]], p[lat[1]] = pos, ca + sa * ha, cb + sb * hb
            ids.append(len(verts))
            verts.append(p)
        rings.append(ids)
    tris: list[list[int]] = []
    for r0, r1 in zip(rings, rings[1:]):
        if len(r0) == 4 and len(r1) == 4:
            for k in range(4):
                a, b, c, d = r0[k], r0[(k + 1) % 4], r1[(k + 1) % 4], r1[k]
                tris += [[a, b, c], [a, c, d]]
        else:
            big, small = (r0, r1) if len(r0) == 4 else (r1, r0)
            for k in range(4):
                tris.append([big[k], big[(k + 1) % 4], small[0]])
    for ring in (rings[0], rings[-1]):
        if len(ring) == 4:
            tris += [[ring[0], ring[1], ring[2]], [ring[0], ring[2], ring[3]]]
    return np.array(verts, dtype=np.float64), np.array(tris, dtype=np.int64)


def merge(*meshes: tuple[np.ndarray, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    verts, tris, base = [], [], 0
    for v, t in meshes:
        verts.append(v)
        tris.append(t + base)
        base += len(v)
    return np.vstack(verts), np.vstack(tris)


def box(lo, hi) -> tuple[np.ndarray, np.ndarray]:
    return loft(2, [(lo[2], (hi[0] - lo[0]) / 2, (hi[1] - lo[1]) / 2, (hi[0] + lo[0]) / 2, (hi[1] + lo[1]) / 2),
                    (hi[2], (hi[0] - lo[0]) / 2, (hi[1] - lo[1]) / 2, (hi[0] + lo[0]) / 2, (hi[1] + lo[1]) / 2)])


def _collision() -> dict:
    return {"name": "SM_Fixture_Collision", "mesh": box((-1, -1, -1), (1, 1, 1))}


def gun(forend=(0.04, 0.10), *, magazine_and_scope=False, cone_front=False):
    """Z-long rifle, z -0.25..0.65 (length 0.9), origin 27.8 % from the rear, +Z barrel.

    Stations: stock/receiver x +-0.02, y 0..0.10; a forend ring at z = 0.308 of ``forend`` (width, height) centred on
    y 0.05 -- exactly 0.62 of the length from the butt, so the support slice (z 0.298..0.318) holds only that ring and
    its smaller lateral extent is ``min(forend)``; a barrel x +-0.01, y 0.045..0.065 ending in a 4-vertex muzzle face
    at z = 0.65 (or, with ``cone_front``, a single apex). ``magazine_and_scope`` hangs a magazine to y = -0.30 and
    stands a scope up to y = 0.20, inflating the bounds so the bounds-centre muzzle rule is 0.105 m off.
    """
    fw, fh = forend
    body = loft(2, [(-0.25, 0.02, 0.05, 0, 0.05), (0.29, 0.02, 0.05, 0, 0.05), (0.308, fw / 2, fh / 2, 0, 0.05),
                    (0.327, 0.02, 0.05, 0, 0.05), (0.35, 0.02, 0.05, 0, 0.05)])
    barrel = loft(2, [(0.35, 0.01, 0.01, 0, 0.055), (0.65, 0, 0, 0, 0.055)] if cone_front
                  else [(0.35, 0.01, 0.01, 0, 0.055), (0.65, 0.01, 0.01, 0, 0.055)])
    parts = [body, barrel]
    if magazine_and_scope:
        parts.append(loft(1, [(-0.30, 0.01, 0.04, 0, 0.04), (0.0, 0.01, 0.04, 0, 0.04)]))
        parts.append(loft(2, [(0.05, 0.02, 0.05, 0, 0.15), (0.25, 0.02, 0.05, 0, 0.15)]))
    return merge(*parts)


def pistol():
    """Z-long one-hand gun, z -0.05..0.15 (length 0.2), origin 25 % from the rear; grip hangs to y = -0.10."""
    return merge(loft(2, [(-0.05, 0.015, 0.02, 0, 0.02), (0.15, 0.015, 0.02, 0, 0.02)]),
                 loft(1, [(-0.10, 0.012, 0.02, 0, 0.0), (0.0, 0.012, 0.02, 0, 0.0)]))


def sword(axis=1):
    """Long on ``axis`` (default Y), length 1.0: -0.15..0.85, origin 15 % from the butt. Stations (dense, every 1 cm
    in the handle): pommel -0.15..-0.12 (e 0.05), HANDLE -0.12..0.08 (hx = hz = 0.015, e 0.03), guard 0.09..0.11
    (width 0.2), blade 0.11..0.84 (hx 0.025, thickness 0.008) to an apex at 0.85. The hand-worked handle run is bins
    4..23 (the pommel's top ring shares bin 3), centre -0.01 along the axis, radius 0.015."""
    return merge(
        loft(axis, [(-0.15, 0.025, 0.025), (-0.12, 0.025, 0.025)], step=0.01),
        loft(axis, [(-0.12, 0.015, 0.015), (0.08, 0.015, 0.015)], step=0.01),
        loft(axis, [(0.09, 0.1, 0.015), (0.11, 0.1, 0.015)], step=0.01),
        loft(axis, [(0.11, 0.025, 0.004), (0.84, 0.025, 0.004), (0.85, 0, 0)], step=0.01),
    )


def knife():
    """Y-long, -0.10..0.19 (length 0.29), handle -0.10..0.02 with e 0.02 (run bins 0..12, centre -0.035, r 0.01)."""
    return merge(
        loft(1, [(-0.10, 0.01, 0.01), (0.02, 0.01, 0.01)], step=0.01),
        loft(1, [(0.03, 0.03, 0.008), (0.035, 0.03, 0.008)], step=0.01),
        loft(1, [(0.035, 0.02, 0.003), (0.18, 0.02, 0.003), (0.19, 0, 0)], step=0.01),
    )


def axe():
    """Y-long, -0.45..0.45 (length 0.9), origin dead centre, heavy head (0.24 x 0.06) on the +Y end, 3 cm shaft."""
    return merge(loft(1, [(-0.45, 0.015, 0.015), (0.30, 0.015, 0.015)], step=0.01),
                 loft(1, [(0.30, 0.12, 0.03), (0.45, 0.12, 0.03)], step=0.01))


def spear():
    """Y-long, -1.0..1.0 (length 2.0), origin mid-length; a 5 cm butt ferrule at -Y, a 3 cm shaft, a tapered head to
    an apex at +Y. Pointed archetype: the smaller (+Y) end section is the tip."""
    return merge(loft(1, [(-1.0, 0.025, 0.025), (-0.95, 0.025, 0.025)], step=0.01),
                 loft(1, [(-0.95, 0.015, 0.015), (0.85, 0.015, 0.015)], step=0.05),
                 loft(1, [(0.85, 0.015, 0.015), (1.0, 0, 0)], step=0.01))


def bow(depth_axis=2, centre=(0.0, 0.0, 0.0)):
    """Y-long bow, y -0.8..0.8, limbs bulging 0.15 along ``depth_axis`` (curve depth 0.16 vs 0.02 thickness)."""
    lat = [i for i in range(3) if i != 1]
    d = lat.index(depth_axis)

    def stations(ys, bulges):
        out = []
        for y, b in zip(ys, bulges):
            c = [0.0, 0.0]
            c[d] = b
            out.append((y, 0.01, 0.01, c[0], c[1]))
        return out

    m = merge(loft(1, stations([-0.8, -0.4, -0.1, 0.1, 0.4, 0.8], [0.15, 0.06, 0.0, 0.0, 0.06, 0.15])))
    return m[0] + np.array(centre), m[1]


def shield():
    """Face-on shield: x +-0.3, y +-0.4, plate z 0..0.04 plus a boss to z = 0.08; the arm face is z = 0 (the origin)."""
    return merge(loft(2, [(0.0, 0.3, 0.4), (0.04, 0.3, 0.4)]), loft(2, [(0.04, 0.05, 0.05), (0.08, 0.05, 0.05)]))


def _reorient(mesh, axes=(0, 1, 2), flip_z=False):
    """Permute the axes (``axes[i]`` = the source axis that becomes axis i) and optionally mirror z, so one canonical
    front-toward-+z shield yields the other orientations. The handedness change does not matter: the measurement
    reads positions only."""
    v = mesh[0][:, list(axes)].copy()
    if flip_z:
        v[:, 2] *= -1.0
    return v, mesh[1]


def shield_strapped():
    """Canonical front-toward-+z shield with arm straps behind it: a flat plain plate x +-0.3, y +-0.4, z 0..0.04
    (the front is z = 0.04) and two straps (x +-0.1 +- 0.015, y +-0.1) standing from the back face to z = -0.08.
    The straps are separate pieces with their own vertices: elongated 6.7:1 across the face, 2.7x deeper than wide,
    4.5 % of the surface each, centred 0.5 of the thickness behind the plate's mid-plane."""
    plate = box((-0.3, -0.4, 0.0), (0.3, 0.4, 0.04))
    straps = [box((cx - 0.015, -0.1, -0.08), (cx + 0.015, 0.1, 0.0)) for cx in (-0.1, 0.1)]
    return merge(plate, *straps)


def shield_dished():
    """Canonical front-toward-+z shield that is only a convex dish: a pyramid on a 0.6 x 0.8 base at z = 0 with its
    apex at z = 0.1 (centre of the dish 0.1 in front of the rim), no straps."""
    return loft(2, [(0.0, 0.3, 0.4), (0.1, 0.0, 0.0)])


def shield_strap_over_dish():
    """Front-toward-+z by the straps, -z by the dish: the pyramid's apex points at -z (z = -0.1), and the straps
    stand behind it too (z -0.14..-0.04). The straps are the stronger signal, so the front is +z."""
    dish = loft(2, [(0.0, 0.3, 0.4), (-0.1, 0.0, 0.0)])
    straps = [box((cx - 0.015, -0.1, -0.14), (cx + 0.015, 0.1, -0.04)) for cx in (-0.1, 0.1)]
    return merge(dish, *straps)


def zigzag():
    """Y-long club-like mesh whose width alternates 0.02 / 0.10 every centimetre: no 6 cm run stays near the p10
    extent, so handle detection finds nothing. y -0.15..0.35, origin 30 % from the butt."""
    return loft(1, [(-0.15 + 0.01 * i, 0.01 if i % 2 == 0 else 0.05, 0.01) for i in range(51)])


def shifted(mesh, offset):
    return mesh[0] + np.asarray(offset, dtype=np.float64), mesh[1]


def box_part(size=(0.04, 0.04, 0.12)):
    """A small z-long box (magazine, arrow, quiver stand-ins) centred on the origin."""
    h = [s / 2 for s in size]
    return box((-h[0], -h[1], -h[2]), (h[0], h[1], h[2]))


def mesh_for(archetype: str, kind: str | None, role: str):
    """The synthetic stand-in the end-to-end test generates for a fixture record."""
    if role in ("part", "ammo", "carrier") or archetype == "unknown":
        return box_part()
    if archetype == "bow":
        return bow()
    if kind == "shield":
        return shield()
    if kind == "ranged":
        return pistol() if archetype in ("pistol", "revolver", "utility_gun") else gun()
    if kind == "melee":
        return sword()
    return box_part((0.06, 0.12, 0.06))  # thrown


# -- the named set -----------------------------------------------------------------------------------------

# Rotation of 90 degrees about +Z (x, y, z, w).
_ROT_Z_90 = (0.0, 0.0, 0.7071067811865476, 0.7071067811865476)
SHARED_BOW_B_OFFSET = (2.0, 0.3, 0.5)
SHARED_QUIVER_B_OFFSET = (2.5, 0.0, 0.5)


def _quiver():
    return loft(1, [(0.0, 0.05, 0.05), (0.5, 0.05, 0.05)])


def shared_roots() -> list[dict]:
    """One GLB, three nodes: Bow_A at the origin; Bow_B (an empty parent at (2.0, 0.3, 0.5) with two limb children);
    Quiver_B at (2.5, 0, 0.5) rotated 90 degrees about Z."""
    limb_up = loft(1, [(0.0, 0.01, 0.01, 0.0, 0.0), (0.4, 0.01, 0.01, 0.06, 0.0), (0.8, 0.01, 0.01, 0.15, 0.0)])
    limb_dn = loft(1, [(-0.8, 0.01, 0.01, 0.15, 0.0), (-0.4, 0.01, 0.01, 0.06, 0.0), (0.0, 0.01, 0.01, 0.0, 0.0)])
    return [
        {"name": "Bow_A", "mesh": bow(depth_axis=0)},
        {"name": "Bow_B", "translation": SHARED_BOW_B_OFFSET,
         "children": [{"name": "Bow_B_limb_up", "mesh": limb_up}, {"name": "Bow_B_limb_dn", "mesh": limb_dn}]},
        {"name": "Quiver_B", "translation": SHARED_QUIVER_B_OFFSET, "rotation": _ROT_Z_90, "mesh": _quiver()},
    ]


def generate_all(dest: Path) -> dict[str, Path]:
    """Write every named fixture under ``dest``; returns name -> path."""
    dest.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}

    def put(name: str, mesh, *, collision=False):
        roots = [{"name": name, "mesh": mesh}] + ([_collision()] if collision else [])
        out[name] = write_glb(dest / f"{name}.glb", roots)

    put("gun", gun(), collision=True)
    put("gun_wide", gun(forend=(0.14, 0.16)), collision=True)
    put("gun_inflated", gun(magazine_and_scope=True), collision=True)
    put("gun_cone", gun(cone_front=True), collision=True)
    put("pistol", pistol())
    put("sword", sword())
    put("knife", knife())
    put("axe", axe())
    put("spear", spear())
    put("bow", bow())
    put("shield", shield())
    # shield fronts (spec 3.5.2 item 4): the origin sits on the FRONT side of the body (and so a pivot rule that
    # points away from the origin would pick the back), one fixture per orientation of the face normal
    put("shield_strap_pz", shifted(shield_strapped(), (0.0, 0.0, -0.04)))  # z -0.12..0 ; front +z
    put("shield_strap_nz", shifted(_reorient(shield_strapped(), flip_z=True), (0.0, 0.0, 0.04)))  # z 0..0.12 ; front -z
    put("shield_strap_px", shifted(_reorient(shield_strapped(), axes=(2, 1, 0)), (-0.04, 0.0, 0.0)))  # x -0.12..0 ; +x
    put("shield_dish_pz", shifted(shield_dished(), (0.0, 0.0, -0.1)))  # z -0.1..0 ; front +z
    put("shield_dish_nz", shifted(_reorient(shield_dished(), flip_z=True), (0.0, 0.0, 0.1)))  # z 0..0.1 ; front -z
    put("shield_strap_over_dish", shield_strap_over_dish())  # z -0.14..0 ; front +z
    put("zlong_melee", sword(axis=2))
    put("zigzag", zigzag())
    put("origin_outside", shifted(gun(), (0.0, 0.5, 0.9)))
    put("degenerate", (np.zeros((3, 3)), np.array([[0, 1, 2]])))
    out["shared"] = write_glb(dest / "shared.glb", shared_roots())
    out["zero_tri"] = write_glb(dest / "zero_tri.glb", [{"name": "Empty"}])
    garbage = dest / "garbage.glb"
    garbage.write_bytes(b"this is not a glb file at all")
    out["garbage"] = garbage
    return out


# Hand-worked expectations (literals; see the docstrings above for where each number comes from).
LABELS = {
    "gun": {"archetype": "rifle", "kind": "ranged", "forward": "+z", "up": "+y", "long_axis": "z",
            "forward_source": "pivot", "length": 0.9, "muzzle": [0.0, 0.055, 0.65], "support_z": 0.308,
            "support_r": 0.02},
    "gun_wide": {"support_r": 0.07},
    "sword": {"archetype": "sword", "kind": "melee", "forward": "+y", "up": "+x", "long_axis": "y",
              "forward_source": "pivot", "length": 1.0, "grip_y": -0.02, "grip_r": 0.015},
    "knife": {"archetype": "knife", "kind": "melee", "forward": "+y", "up": "+x", "long_axis": "y", "grip_y": -0.04,
              "grip_r": 0.01},
    "axe": {"archetype": "axe", "kind": "melee", "forward": "+y", "up": "+x", "long_axis": "y",
            "forward_source": "section", "length": 0.9},
    "spear": {"archetype": "spear", "kind": "melee", "forward": "+y", "up": "+x", "long_axis": "y",
              "forward_source": "section", "length": 2.0},
    "bow": {"archetype": "bow", "kind": "ranged", "forward": "+z", "up": "+y", "long_axis": "y",
            "forward_source": "bow_rule", "length": 1.6},
    "shield": {"archetype": "shield", "kind": "shield", "forward": "+z", "up": "+y", "long_axis": "y",
               "forward_source": "shield_rule", "length": 0.8},
    "zlong_melee": {"archetype": "sword", "kind": "melee", "forward": "+z", "up": "+x", "long_axis": "z",
                    "forward_source": "pivot", "length": 1.0},
}
