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


def loft(axis: int, stations: list[tuple], step: float | None = None, stagger: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """A rectangular loft along ``axis``. A station is ``(pos, half_a, half_b[, centre_a, centre_b])`` over the two
    lateral axes in x,y,z order; ``half_a == half_b == 0`` makes an apex (one vertex). ``step`` inserts linearly
    interpolated stations so a vertex exists at least every ``step`` metres (the handle detector bins at 1 cm).
    ``stagger`` slides corner ``k`` of every ring ``k * stagger`` along the axis, so a ring's four vertices fall in four
    different bins (a vertex-sparse haft: see ``sparse_haft``)."""
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
        for k, (sa, sb) in enumerate(corners):
            p = [0.0, 0.0, 0.0]
            p[axis], p[lat[0]], p[lat[1]] = pos + k * stagger, ca + sa * ha, cb + sb * hb
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


def gun(forend=(0.04, 0.10), *, magazine_and_scope=False, cone_front=False, stepped_muzzle=False):
    """Z-long rifle, z -0.25..0.65 (length 0.9), origin 27.8 % from the rear, +Z barrel.

    Stations: stock/receiver x +-0.02, y 0..0.10; a forend ring at z = 0.308 of ``forend`` (width, height) centred on
    y 0.05 -- exactly 0.62 of the length from the butt, so the support slice (z 0.298..0.318) holds only that ring and
    its smaller lateral extent is ``min(forend)``; a barrel x +-0.01, y 0.045..0.065 ending in a 4-vertex muzzle face
    at z = 0.65 (or, with ``cone_front``, a single apex). ``magazine_and_scope`` hangs a magazine to y = -0.30 and
    stands a scope up to y = 0.20, inflating the bounds so the bounds-centre muzzle rule is 0.105 m off.
    ``stepped_muzzle`` ends the barrel in three stations that fall in different muzzle tolerance windows: a single apex
    at z = 0.65 (1 point in the 0.001 window), a ring at 0.6485 (4 more, the 0.002 window holds 5) and a ring at 0.646
    centred 0.02 higher (4 more, the 0.005 window holds 9). Lateral means: 0.002 -> y 0.055, 0.005 -> y 0.063889.
    """
    fw, fh = forend
    body = loft(2, [(-0.25, 0.02, 0.05, 0, 0.05), (0.29, 0.02, 0.05, 0, 0.05), (0.308, fw / 2, fh / 2, 0, 0.05),
                    (0.327, 0.02, 0.05, 0, 0.05), (0.35, 0.02, 0.05, 0, 0.05)])
    if stepped_muzzle:
        stations = [(0.35, 0.01, 0.01, 0, 0.055), (0.646, 0.01, 0.01, 0, 0.075), (0.6485, 0.01, 0.01, 0, 0.055),
                    (0.65, 0, 0, 0, 0.055)]
    elif cone_front:
        stations = [(0.35, 0.01, 0.01, 0, 0.055), (0.65, 0, 0, 0, 0.055)]
    else:
        stations = [(0.35, 0.01, 0.01, 0, 0.055), (0.65, 0.01, 0.01, 0, 0.055)]
    barrel = loft(2, stations)
    parts = [body, barrel]
    if magazine_and_scope:
        parts.append(loft(1, [(-0.30, 0.01, 0.04, 0, 0.04), (0.0, 0.01, 0.04, 0, 0.04)]))
        parts.append(loft(2, [(0.05, 0.02, 0.05, 0, 0.15), (0.25, 0.02, 0.05, 0, 0.15)]))
    return merge(*parts)


def pistol():
    """Z-long one-hand gun, z -0.05..0.15 (length 0.2), origin 25 % from the rear; grip hangs to y = -0.10."""
    return merge(loft(2, [(-0.05, 0.015, 0.02, 0, 0.02), (0.15, 0.015, 0.02, 0, 0.02)]),
                 loft(1, [(-0.10, 0.012, 0.02, 0, 0.0), (0.0, 0.012, 0.02, 0, 0.0)]))


def rifle_mid_origin():
    """Z-long rifle, z -0.45..0.45 (length 0.9), origin dead centre (so the pivot rule has no say), a fat stock at -z.

    End cross-sections over the outer 10 % (0.09 m): the -z window holds the stock ring (x +-0.03, y +-0.10 =
    0.012 m2), the +z window the barrel ring (x +-0.01, y +-0.01 = 0.0004 m2). The smaller end is the muzzle: +z.
    """
    return merge(loft(2, [(-0.45, 0.03, 0.10, 0, 0.0), (-0.30, 0.03, 0.10, 0, 0.0), (-0.20, 0.02, 0.05, 0, 0.05)]),
                 loft(2, [(-0.20, 0.02, 0.05, 0, 0.05), (0.0, 0.02, 0.05, 0, 0.05), (0.0, 0.01, 0.01, 0, 0.055),
                          (0.45, 0.01, 0.01, 0, 0.055)]))


def smg_fat_handguard():
    """Z-long submachine gun, z -0.45..0.45, origin dead centre, with a slim wire stock at -z and a fat handguard at +z
    (a magazine hangs to y = -0.20 under the middle): the smaller end cross-section is the STOCK, so the end-section
    rule alone points to -z although the barrel end is +z.

    Outer 10 % windows: -z holds the stock ring (x +-0.01, y +-0.01 = 0.0004 m2), +z the handguard ring (x +-0.04,
    y +-0.04 = 0.0064 m2).
    """
    return merge(loft(2, [(-0.45, 0.01, 0.01, 0, 0.05), (-0.20, 0.01, 0.01, 0, 0.05)]),
                 loft(2, [(-0.20, 0.02, 0.05, 0, 0.05), (0.10, 0.02, 0.05, 0, 0.05)]),
                 loft(2, [(0.10, 0.04, 0.04, 0, 0.05), (0.45, 0.04, 0.04, 0, 0.05)]),
                 loft(1, [(-0.20, 0.01, 0.015, 0, 0.0), (0.0, 0.01, 0.015, 0, 0.0)]))


def pistol_mid_origin():
    """Z-long one-hand gun, z -0.10..0.10, origin dead centre, with a bulky weapon light at the +z end: the +z
    window (0.02 m) holds a ring x +-0.025, y +-0.025 (0.0025 m2) against the slide's x +-0.015, y +-0.02 (0.0012 m2)
    at -z, so the end-section rule points to -z although the muzzle is the +z end."""
    return merge(loft(2, [(-0.10, 0.015, 0.02, 0, 0.02), (0.07, 0.015, 0.02, 0, 0.02)]),
                 loft(2, [(0.07, 0.025, 0.025, 0, 0.02), (0.10, 0.025, 0.025, 0, 0.02)]),
                 loft(1, [(-0.10, 0.012, 0.02, 0, 0.0), (0.0, 0.012, 0.02, 0, -0.04)]))


def shoulder_launcher():
    """Z-long tube x +-0.05, y +-0.05, z -0.63..0.37 (length 1.0): the origin sits 63 % from the -z end, which is the
    pivot rule's 'forward is away from the origin' = -z."""
    return loft(2, [(-0.63, 0.05, 0.05), (0.37, 0.05, 0.05)])


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


def bow(depth_axis=2, centre=(0.0, 0.0, 0.0), belly=1.0):
    """Y-long bow, y -0.8..0.8, curve depth 0.16 vs 0.02 thickness along ``depth_axis``: the riser at +0.15 and the
    limb tips at 0, so the belly bulges toward ``+depth_axis`` and the tips and string toward the archer (spec 3.5.2
    item 3: forward = the belly side, here +``depth_axis``). ``belly=-1`` mirrors it (belly toward -``depth_axis``)."""
    lat = [i for i in range(3) if i != 1]
    d = lat.index(depth_axis)

    def stations(ys, bulges):
        out = []
        for y, b in zip(ys, bulges):
            c = [0.0, 0.0]
            c[d] = b
            out.append((y, 0.01, 0.01, c[0], c[1]))
        return out

    m = merge(loft(1, stations([-0.8, -0.4, -0.1, 0.1, 0.4, 0.8],
                               [0.0, 0.09 * belly, 0.15 * belly, 0.15 * belly, 0.09 * belly, 0.0])))
    return m[0] + np.array(centre), m[1]


def bow_with_belly(belly_z):
    """Y-long stave y -0.8..0.8 whose middle (stations at +-0.1) stands ``belly_z`` along +z of its tip stations
    (+-0.7, +-0.8), 0.02 thick. The bow rule's belly = ``belly_z / (|belly_z| + 0.02)`` of the 0.02 + |belly_z| depth, so
    0.003 -> 0.13 (under the 0.15 threshold) and 0.0045 -> 0.184 (over it); negative values mirror."""
    st = [(-0.8, 0.01, 0.01, 0.0, 0.0), (-0.7, 0.01, 0.01, 0.0, 0.0), (-0.1, 0.01, 0.01, 0.0, belly_z),
          (0.1, 0.01, 0.01, 0.0, belly_z), (0.7, 0.01, 0.01, 0.0, 0.0), (0.8, 0.01, 0.01, 0.0, 0.0)]
    return loft(1, st)


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


def shield_bowl_handle():
    """Front-toward-+z by the handle, -z by the dish (a lid-style bowl, like the Kids shields): a pyramid on a 0.6 x 0.8
    base at z = 0 with its apex at z = -0.1 (the plate's centre lies on the BACK side of its rim) and one flat bar
    handle x +-0.1, y +-0.02, z -0.144..-0.1 behind it. The bar is a separate piece: aspect 5.0, depth 0.044 = 1.10x its
    0.04 width (under the 1.5 a strap normally needs), centre 0.5 of the 0.144 thickness behind the plate's mid-plane,
    about 3.7 % of the surface."""
    return merge(loft(2, [(0.0, 0.3, 0.4), (-0.1, 0.0, 0.0)]), box((-0.1, -0.02, -0.144), (0.1, 0.02, -0.1)))


def shield_front_bar():
    """A thick flat plate x +-0.3, y +-0.4, z 0..0.1 with an elongated bar standing on its FRONT (+z) face, embedded
    0.04 into it: x +-0.1, y +-0.02, z 0.06..0.108 (aspect 5.0, depth 1.2x its 0.04 width, centre 0.31 of the 0.108
    thickness off the mid-plane). Nothing here is a handle: the bar is too shallow for 1.5 and too near the plate for
    the outer-handle test, so the origin (on the z = 0 arm face) decides: front +z."""
    return merge(box((-0.3, -0.4, 0.0), (0.3, 0.4, 0.1)), box((-0.1, -0.02, 0.06), (0.1, 0.02, 0.108)))


def zigzag():
    """Y-long club-like mesh whose width alternates 0.02 / 0.10 every centimetre, y -0.15..0.35, origin 30 % from the
    butt. Its VERTICES alternate, but the edges between the rings cross every bin, so the surface width profile sits at
    0.092 / 0.100 and the whole window is one thin run: a handle under the W2d rule (it was 'no handle' under the
    vertex-only rule). The mesh with no handle is ``banded``."""
    return loft(1, [(-0.15 + 0.01 * i, 0.01 if i % 2 == 0 else 0.05, 0.01) for i in range(51)])


def bar(y0, y1, ha, hb, ca=0.0, cb=0.0):
    """A y-long box section y0..y1 with half widths ``ha`` (x) and ``hb`` (z)."""
    return loft(1, [(y0, ha, hb, ca, cb), (y1, ha, hb, ca, cb)])


def banded():
    """Y-long mesh with NO handle: ten periods of a 2.5 cm thin band (e 0.02) and a 1.5 cm fat band (e 0.10), butt at
    y = 0, length 0.4995, origin at the butt. Each band is its own box, and its rings sit in the middle of the bins they
    occupy (the 0.0505 period drifts 0.5 mm per band so no ring lies on a bin boundary): thin bands cover 3 bins, fat
    bands 2, so 60 % of the window is thin (p20 = 0.02) but no thin run reaches the 6 cm minimum."""
    parts = []
    for k in range(10):
        y = 0.0505 * k
        parts.append(bar(y, y + 0.025, 0.01, 0.01))
        parts.append(bar(y + 0.03, y + 0.045, 0.05, 0.01))
    return merge(*parts)


# -- the W2d melee grip set (AC40) -------------------------------------------------------------------------
#
# Ten Y-long melee meshes, butt at y = 0 and forward +y, each with a hand-labelled handle. Every transition ring sits in
# the MIDDLE of a 1 cm bin (x.5 cm from the butt), the first section starts at the butt ring (y = 0), and no two
# sections share a bin, so each bin is wholly one section and the handle run is read off the section table below
# (bins are 1 cm from the butt: bin b = y in [b, b+1) cm). The labels are literals worked out by hand; ``W2D_SET`` below
# is the table the tests read. Windows are the butt-side 60 % of the length; w_ref is p20 of the bin widths in it.
#
# Each mesh is used three ways (see ``W2D_ORIGINS``): the origin at the butt and at 20 % of the length (the pivot rule
# gives forward +y), and at the middle of the length, where the pivot rule is silent and the forward sign comes from the
# END-SECTION rule (smaller end = tip for a pointed archetype, larger end = head for axe / hammer / club / mace). So every
# mesh carries a tip that is clearly smaller than its butt (pointed archetypes) or a head clearly larger than its butt
# (headed ones), and the sign resolves to +y.


def w2d_sword():
    """L 1.0. Pommel bins 0-3 (e 0.05), HILT bins 4-20 (y 0.045..0.205, e 0.03), guard 21-23 (e 0.20), blade 24-98 (e 0.05,
    to an apex at 1.0). Window 60 bins; 17 hilt bins >= 12 so p20 = 0.03 and the pommel and blade (0.05 > 0.039) are not
    thin. Run bins 4-20 (17 bins, under the 30 cm cap): grip = (4 + 17 / 2) cm = 0.125, r 0.015."""
    return merge(bar(0.0, 0.035, 0.025, 0.025), bar(0.045, 0.205, 0.015, 0.015), bar(0.215, 0.235, 0.1, 0.015),
                 loft(1, [(0.245, 0.025, 0.004), (0.985, 0.025, 0.004), (1.0, 0.0, 0.0)]))


def w2d_axe():
    """L 0.9. HAFT bins 0-70 (e 0.03, y 0..0.705), head bins 71-90 (0.24 x 0.06). Window 54 bins, all haft: one run of 54,
    capped to its first 30 bins: grip = 15 cm = 0.15, r 0.015. Headed: the head (+y) is the larger end."""
    return merge(bar(0.0, 0.705, 0.015, 0.015), bar(0.715, 0.9, 0.12, 0.03))


def w2d_hammer():
    """L 0.4. HAFT bins 0-30 (e 0.03, y 0..0.305), head bins 31-40 (0.10 x 0.06). Window 24 bins, all haft: one run of 24
    (under the cap): grip = 12 cm = 0.12, r 0.015."""
    return merge(bar(0.0, 0.305, 0.015, 0.015), bar(0.315, 0.4, 0.05, 0.03))


def w2d_bat():
    """L 0.85. One taper, half width 0.012 at the butt to 0.035 at the head (e 0.024 .. 0.07); the bin width is that of its
    top sample (corner edges sampled every 4.97 mm). Window 51 bins, w_ref = p20 = 0.0299, threshold 0.0389: bins 0-26 are
    thin (bin 26 tops out at y 0.27: e 0.0388), bin 27 is not. Run bins 0-26 (27 bins): grip = 13.5 cm = 0.135, r
    = mean(e) / 2 = 0.0158. Labelled handle: the butt 27 cm, y 0..0.27."""
    return loft(1, [(0.0, 0.012, 0.012), (0.85, 0.035, 0.035)])


def w2d_crowbar():
    """L 0.8. Hook end at the butt bins 0-7 (0.06 x 0.03), SHAFT bins 8-71 (e 0.02, y 0.085..0.715), chisel bins 72-80
    (0.04 x 0.008). Window 48 bins: 40 shaft bins, p20 = 0.02, hook (0.06) not thin. Run bins 8-47 (40), capped to bins
    8-37: grip = (8 + 15) cm = 0.23, r 0.01. Archetype crowbar is pointed: the chisel (smaller section than the hook) is the
    tip, so mid-origin resolves to +y."""
    return merge(bar(0.0, 0.075, 0.03, 0.015), bar(0.085, 0.715, 0.01, 0.01), bar(0.725, 0.8, 0.02, 0.004))


def short_blade(length, handle_bins):
    """A y-long knife / dagger of the given ``length`` whose HANDLE fills bins 0..handle_bins-1 (e 0.02, y 0..(handle_bins -
    0.5) cm), followed by a 2-bin guard (e 0.06) and a blade (e 0.04) to an apex at ``length``. The minimum run is
    max(2, min(6, 0.2 * length)) cm rounded up to whole bins: 6 bins for a 28 cm knife (5.6 cm), 4 for an 18 cm dagger
    (3.6 cm)."""
    top = (handle_bins - 0.5) * 0.01
    return merge(bar(0.0, top, 0.01, 0.01), bar(top + 0.01, top + 0.02, 0.03, 0.008),
                 loft(1, [(top + 0.03, 0.02, 0.003), (length - 0.015, 0.02, 0.003), (length, 0.0, 0.0)]))


def w2d_knife():
    """L 0.28, ``short_blade(0.28, 12)``: HANDLE bins 0-11 (y 0..0.115, e 0.02), guard 12-13 (e 0.06), blade 14-26 (e 0.04).
    Window 17 bins; 12 handle bins, p20 = 0.02, threshold 0.026. The run (12 bins) beats the minimum 5.6 cm -> 6 bins.
    Grip = 6 cm = 0.06, r 0.01."""
    return short_blade(0.28, 12)


def w2d_spear():
    """L 2.0. Ferrule bins 0-4 (e 0.05), SHAFT bins 5-190 (y 0.055..1.905, e 0.03), leaf head 191-199 (e 0.05, apex at 2.0).
    Window 120 bins: shaft bins 5-119 are one run of 115, capped to its first 30 bins 5-34: grip = (5 + 15) cm = 0.20 (the
    uncapped centre would be 0.625), r 0.015."""
    return merge(bar(0.0, 0.045, 0.025, 0.025), bar(0.055, 1.905, 0.015, 0.015),
                 loft(1, [(1.915, 0.025, 0.006), (1.97, 0.025, 0.006), (2.0, 0.0, 0.0)]))


def sparse_haft():
    """L 1.0 club. A 3 cm square haft made only of rings of 4 vertices every 12 cm, each ring's corners staggered 2.3 cm
    along the axis (corner k at y = 0.12 i + 0.023 k, i = 0..7, last vertex 0.909), so every occupied bin holds ONE vertex
    and the rest are empty: the vertex-only profile is 0 everywhere (the live failure), while the long edges still run
    through every bin. Surface profile: bin 0 and 1 are partial (<0.03), bins 2.. are 0.03. Window 60 bins, p20 = 0.03,
    one run of 60 capped to bins 0-29: grip = 15 cm = 0.15, r = mean(e) / 2 = 0.0146. Head: a 10 cm cube y 0.93..1.0."""
    shaft = loft(1, [(0.12 * i, 0.015, 0.015) for i in range(8)], stagger=0.023)
    return merge(shaft, bar(0.93, 1.0, 0.05, 0.05))


def w2d_tang():
    """L 0.6. HILT bins 0-11 (y 0..0.115, e 0.03), guard 12-13 (e 0.12), TANG bins 14-58 (0.03 x 0.01, to an apex at 0.6).
    Window 36 bins: hilt 0-11 and tang 14-35 are both thin (e 0.03), the tang run (22 bins in the window) is LONGER than the
    hilt (12). The handle is the one nearest the butt: bins 0-11, grip = 6 cm = 0.06, r 0.015 (the longest run would put the
    grip at (14 + 11) cm = 0.25)."""
    return merge(bar(0.0, 0.115, 0.015, 0.015), bar(0.125, 0.135, 0.06, 0.015),
                 loft(1, [(0.145, 0.015, 0.005), (0.585, 0.015, 0.005), (0.6, 0.0, 0.0)]))


def w2d_wire():
    """L 0.6, a whip-like mesh that pins the 3 mm floor of w_ref: a 3.5 mm GRIP WIRE bins 0-9 (y 0..0.095), a 2 cm bead
    bins 10-12, a 1 mm filament bins 13-60 (to y 0.6). Window 36 bins; 23 filament bins make p20 = 0.001, so only the
    floor (w_ref = 0.003, threshold 0.0039) lets the 3.5 mm wire count as thin. With the floor: the nearest run is the wire,
    bins 0-9, grip = 5 cm = 0.05, r 0.00175. With no floor the threshold is 0.0013 and the filament run (bins 13-35,
    grip 0.245) wins. This is the only honest way to reach the floor: it needs >= 20 % of the window thinner than 2.3 mm
    ahead of a handle thicker than that, which no hand-held shaft is, but a whip's lash is."""
    return merge(bar(0.0, 0.095, 0.00175, 0.00175), bar(0.105, 0.125, 0.01, 0.01), bar(0.135, 0.6, 0.0005, 0.0005))


# Origins used for every set member: fraction of the length from the butt, and the forward source it must give.
W2D_ORIGINS = {"butt": (0.0, "pivot"), "fifth": (0.2, "pivot"), "mid": (0.5, "section")}

# name -> (builder, archetype, length, handle span (lo, hi) in y from the butt, handle radius, grip y from the butt).
# The span is the labelled hand-holdable part (the whole haft / hilt / shaft); the grip y is the hand-worked centre of the
# first 30 cm of the handle run (docstrings above).
W2D_SET = {
    "sword": (w2d_sword, "sword", 1.0, (0.045, 0.205), 0.015, 0.125),
    "axe": (w2d_axe, "axe", 0.9, (0.0, 0.705), 0.015, 0.15),
    "hammer": (w2d_hammer, "hammer", 0.4, (0.0, 0.305), 0.015, 0.12),
    "bat": (w2d_bat, "club", 0.85, (0.0, 0.27), 0.0158, 0.135),
    "crowbar": (w2d_crowbar, "crowbar", 0.8, (0.085, 0.715), 0.01, 0.23),
    "knife": (w2d_knife, "knife", 0.28, (0.0, 0.115), 0.01, 0.06),
    "spear": (w2d_spear, "spear", 2.0, (0.055, 1.905), 0.015, 0.2),
    "sparse_haft": (sparse_haft, "club", 1.0, (0.0, 0.909), 0.015, 0.15),
    "tang": (w2d_tang, "sword", 0.6, (0.0, 0.115), 0.015, 0.06),
    "wire": (w2d_wire, "whip", 0.6, (0.0, 0.095), 0.00175, 0.05),
}


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
    limb_up = loft(1, [(0.0, 0.01, 0.01, 0.15, 0.0), (0.4, 0.01, 0.01, 0.09, 0.0), (0.8, 0.01, 0.01, 0.0, 0.0)])
    limb_dn = loft(1, [(-0.8, 0.01, 0.01, 0.0, 0.0), (-0.4, 0.01, 0.01, 0.09, 0.0), (0.0, 0.01, 0.01, 0.15, 0.0)])
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
    put("gun_stepped_muzzle", gun(stepped_muzzle=True), collision=True)
    put("pistol", pistol())
    # ranged guns whose origin is mid-length (the pivot rule is silent), one per shape the end sections get wrong
    put("rifle_mid_origin", rifle_mid_origin())  # z -0.45..0.45 ; fat stock at -z ; section says +z
    put("smg_fat_handguard", smg_fat_handguard())  # z -0.45..0.45 ; slim stock at -z ; section says -z
    put("pistol_mid_origin", pistol_mid_origin())  # z -0.10..0.10 ; bulky light at +z ; section says -z
    put("shoulder_launcher", shoulder_launcher())  # z -0.63..0.37 ; origin 63 % from -z ; pivot says -z
    # the same tube slid 0.26 along +z (z -0.37..0.63, origin 37 % from -z): the pivot says +z, i.e. what a forward
    # "+z" override on shoulder_launcher must reproduce (W2e)
    put("shoulder_launcher_pz", shifted(shoulder_launcher(), (0.0, 0.0, 0.26)))
    put("sword", sword())
    put("knife", knife())
    put("axe", axe())
    put("spear", spear())
    put("bow", bow())
    # the origin sits past the belly, so the old "away from the origin" sign was wrong (the belly rule disagrees with it)
    put("bow_origin_past_belly_pz", shifted(bow(), (0.0, 0.0, -0.2)))  # z -0.21..-0.04 ; belly +z, old rule said -z
    put("bow_origin_past_belly_nz", shifted(bow(belly=-1.0), (0.0, 0.0, 0.2)))  # z 0.04..0.21 ; belly -z, old rule said +z
    put("shield", shield())
    # shield fronts (spec 3.5.2 item 4): the origin sits on the FRONT side of the body (and so a pivot rule that
    # points away from the origin would pick the back), one fixture per orientation of the face normal
    put("shield_strap_pz", shifted(shield_strapped(), (0.0, 0.0, -0.04)))  # z -0.12..0 ; front +z
    put("shield_strap_nz", shifted(_reorient(shield_strapped(), flip_z=True), (0.0, 0.0, 0.04)))  # z 0..0.12 ; front -z
    put("shield_strap_px", shifted(_reorient(shield_strapped(), axes=(2, 1, 0)), (-0.04, 0.0, 0.0)))  # x -0.12..0 ; +x
    put("shield_dish_pz", shifted(shield_dished(), (0.0, 0.0, -0.1)))  # z -0.1..0 ; front +z
    put("shield_dish_nz", shifted(_reorient(shield_dished(), flip_z=True), (0.0, 0.0, 0.1)))  # z 0..0.1 ; front -z
    put("shield_strap_over_dish", shield_strap_over_dish())  # z -0.14..0 ; front +z
    put("shield_bowl_handle", shield_bowl_handle())  # z -0.144..0 ; front +z (handle), the dish says -z
    put("shield_front_bar", shield_front_bar())  # z 0..0.108 ; no handle: the origin decides, front +z
    put("zlong_melee", sword(axis=2))
    put("zigzag", zigzag())
    put("banded", banded())
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
